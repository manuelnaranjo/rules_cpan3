#!/usr/bin/env python3
"""High-performance CPAN dependency resolver and lockfile generator for rules_cpan.

Resolves dependency closures from user requirements (e.g. deps.txt) using CPAN
mirror indices (02packages.details.txt.gz) and MetaCPAN bulk APIs, verifies SHA256
checksums, detects XS/C extensions, and emits a deterministic cpan.lock.json.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import gzip
import hashlib
import io
import json
import logging
import os
import re
import sys
import tarfile
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    from cpan.tools.resolver.core_modules import CORE_MODULES
except ImportError:
    try:
        from core_modules import CORE_MODULES
    except ImportError:
        CORE_MODULES = set()

logger = logging.getLogger("cpan_resolver")

# Standard core Perl modules and pragmas that are built into perl core
# and do not need to be downloaded from CPAN unless explicitly requested.
STANDARD_CORE_PRAGMAS: Set[str] = {
    "attributes",
    "autodie",
    "autouse",
    "base",
    "bigint",
    "bignum",
    "bigrat",
    "blib",
    "bytes",
    "charnames",
    "constant",
    "deprecate",
    "diagnostics",
    "encoding",
    "experimental",
    "feature",
    "fields",
    "filetest",
    "if",
    "integer",
    "less",
    "lib",
    "locale",
    "mro",
    "ok",
    "open",
    "ops",
    "overload",
    "overloading",
    "parent",
    "re",
    "sigtrap",
    "sort",
    "strict",
    "subs",
    "threads",
    "threads::shared",
    "utf8",
    "vars",
    "version",
    "vmsish",
    "warnings",
    "warnings::register",
}


@dataclass(frozen=True)
class Requirement:
    name: str  # Can be Distribution-Name or Module::Name
    version: Optional[str] = None
    is_module: bool = False


@dataclass
class ResolvedDistribution:
    name: str
    version: str
    download_url: str
    sha256: str
    is_xs: bool = False
    provides: List[str] = field(default_factory=list)
    dependencies: Dict[str, List[str]] = field(
        default_factory=lambda: {
            "build": [],
            "configure": [],
            "runtime": [],
            "test": [],
        }
    )


class CPANIndex:
    """Parses and queries 02packages.details.txt.gz mirror index."""

    def __init__(
        self,
        mirror_url: str = "https://cpan.metacpan.org",
        cache_dir: Optional[Path] = None,
        use_cache: bool = True,
    ) -> None:
        self.mirror_url = mirror_url.rstrip("/")
        self.cache_dir = cache_dir
        self.use_cache = use_cache
        self.package_to_path: Dict[str, str] = {}
        self.package_to_version: Dict[str, str] = {}
        self.dist_to_path: Dict[str, str] = {}
        self.dist_to_version: Dict[str, str] = {}
        self.dist_to_packages: Dict[str, Set[str]] = {}
        self.core_packages: Set[str] = set()

    def load(self, content_bytes: Optional[bytes] = None) -> None:
        """Loads index from raw bytes or downloads/caches 02packages.details.txt.gz."""
        if content_bytes is None:
            content_bytes = self._fetch_index_bytes()

        self._parse(content_bytes)

    def _fetch_index_bytes(self) -> bytes:
        index_url = f"{self.mirror_url}/modules/02packages.details.txt.gz"
        cache_file = self.cache_dir / "02packages.details.txt.gz" if self.cache_dir else None

        if self.use_cache and cache_file and cache_file.exists():
            logger.info("Using cached CPAN index: %s", cache_file)
            return cache_file.read_bytes()

        logger.info("Downloading CPAN index from %s ...", index_url)
        req = urllib.request.Request(index_url, headers={"User-Agent": "rules_cpan_resolver/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()

        if self.use_cache and cache_file:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_bytes(data)

        return data

    def _parse(self, gzipped_data: bytes) -> None:
        try:
            with gzip.GzipFile(fileobj=io.BytesIO(gzipped_data)) as gz:
                text = gz.read().decode("latin1", errors="replace")
        except gzip.BadGzipFile:
            text = gzipped_data.decode("latin1", errors="replace")

        lines = text.splitlines()
        in_header = True

        for line in lines:
            line = line.strip()
            if not line:
                if in_header:
                    in_header = False
                continue
            if in_header:
                continue

            parts = line.split()
            if len(parts) < 3:
                continue

            pkg, ver, path = parts[0], parts[1], parts[2]
            self.package_to_path[pkg] = path
            self.package_to_version[pkg] = ver

            # Path format: A/AU/AUTHOR/Foo-Bar-1.23.tar.gz
            dist_name, dist_ver = self.extract_dist_info_from_path(path)
            if dist_name:
                if dist_name == "perl" or "perl-5." in path:
                    self.core_packages.add(pkg)
                else:
                    self.dist_to_path[dist_name] = path
                    self.dist_to_version[dist_name] = dist_ver
                    self.dist_to_packages.setdefault(dist_name, set()).add(pkg)

        logger.info(
            "Parsed CPAN index: %d packages across %d distributions",
            len(self.package_to_path),
            len(self.dist_to_path),
        )

    @staticmethod
    def extract_dist_info_from_path(path: str) -> Tuple[Optional[str], Optional[str]]:
        """Extracts distribution name and version from an archive path."""
        filename = path.rsplit("/", 1)[-1]
        # Strip common archive extensions
        for ext in (".tar.gz", ".tgz", ".tar.bz2", ".zip", ".tar.xz"):
            if filename.endswith(ext):
                filename = filename[: -len(ext)]
                break

        # Standard CPAN archive pattern: Dist-Name-Version
        match = re.match(r"^(.+)-([vV]?\d[\d._]*(?:-TRIAL\d*)?)$", filename)
        if match:
            return match.group(1), match.group(2)
        # Fallback if no version is separated by hyphen
        return filename, None

    def find_dist_for_module(self, module_name: str) -> Optional[str]:
        """Maps a module name (e.g. Test::More) to its CPAN distribution name (e.g. Test-Simple)."""
        if module_name in self.package_to_path:
            path = self.package_to_path[module_name]
            dist_name, _ = self.extract_dist_info_from_path(path)
            return dist_name
        return None

    def is_core_module(self, module_name: str) -> bool:
        """Determines if a module is strictly built-in to perl core."""
        if module_name == "perl" or module_name in STANDARD_CORE_PRAGMAS:
            return True
        if module_name in self.core_packages:
            return True
        if module_name in CORE_MODULES:
            return True
        return False


class MetaCPANClient:
    """Client for MetaCPAN bulk query APIs."""

    def __init__(self, api_url: str = "https://fastapi.metacpan.org/v1") -> None:
        self.api_url = api_url.rstrip("/")

    def fetch_releases_bulk(self, dist_names: List[str]) -> Dict[str, Dict[str, Any]]:
        """Fetches latest release information for multiple distributions in bulk."""
        if not dist_names:
            return {}

        results: Dict[str, Dict[str, Any]] = {}
        batch_size = 100

        for i in range(0, len(dist_names), batch_size):
            chunk = dist_names[i : i + batch_size]
            query = {
                "query": {
                    "bool": {
                        "must": [
                            {"terms": {"distribution": chunk}},
                            {"term": {"status": "latest"}},
                        ]
                    }
                },
                "_source": [
                    "distribution",
                    "version",
                    "download_url",
                    "checksum_sha256",
                    "dependency",
                    "provides",
                    "main_module",
                ],
                "size": len(chunk) * 2,
            }

            url = f"{self.api_url}/release/_search"
            req = urllib.request.Request(
                url,
                data=json.dumps(query).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "rules_cpan_resolver/1.0",
                },
            )

            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    hits = data.get("hits", {}).get("hits", [])
                    for hit in hits:
                        source = hit.get("_source", {})
                        dist = source.get("distribution")
                        if dist:
                            results[dist] = source
            except urllib.error.URLError as err:
                logger.warning("Bulk query failed for chunk %s: %s", chunk, err)

        return results

    def fetch_release_exact(self, dist_name: str, version: str) -> Optional[Dict[str, Any]]:
        """Fetches release info for a specific distribution version."""
        clean_version = version.lstrip("v")
        query = {
            "query": {
                "bool": {
                    "must": [
                        {"term": {"distribution": dist_name}},
                        {"term": {"version": clean_version}},
                    ]
                }
            },
            "_source": [
                "distribution",
                "version",
                "download_url",
                "checksum_sha256",
                "dependency",
                "provides",
            ],
            "size": 1,
        }

        url = f"{self.api_url}/release/_search"
        req = urllib.request.Request(
            url,
            data=json.dumps(query).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "User-Agent": "rules_cpan_resolver/1.0",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                hits = data.get("hits", {}).get("hits", [])
                if hits:
                    return hits[0].get("_source")
        except urllib.error.URLError as err:
            logger.warning("Query for %s %s failed: %s", dist_name, version, err)

        return None


class ArchiveInspector:
    """Downloads archive, verifies SHA256 checksum, and inspects for XS/C extension files."""

    def __init__(
        self,
        cache_dir: Optional[Path] = None,
        use_cache: bool = True,
    ) -> None:
        self.cache_dir = cache_dir
        self.use_cache = use_cache

    def inspect_archive(
        self, download_url: str, expected_sha256: Optional[str] = None
    ) -> Tuple[str, bool, List[str]]:
        """Downloads archive, returns (computed_sha256, is_xs, member_names)."""
        filename = download_url.rsplit("/", 1)[-1]
        cache_file = self.cache_dir / "dist" / filename if self.cache_dir else None

        data: Optional[bytes] = None
        if self.use_cache and cache_file and cache_file.exists():
            data = cache_file.read_bytes()

        if data is None:
            logger.debug("Downloading %s ...", download_url)
            req = urllib.request.Request(
                download_url, headers={"User-Agent": "rules_cpan_resolver/1.0"}
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = resp.read()

            if self.use_cache and cache_file:
                cache_file.parent.mkdir(parents=True, exist_ok=True)
                cache_file.write_bytes(data)

        computed_sha256 = hashlib.sha256(data).hexdigest()
        if expected_sha256 and computed_sha256.lower() != expected_sha256.lower():
            raise ValueError(
                f"Checksum mismatch for {filename}: expected {expected_sha256}, got {computed_sha256}"
            )

        # Inspect tarball members for .xs files
        is_xs = False
        member_names: List[str] = []
        try:
            with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as tar:
                member_names = tar.getnames()
                for member in member_names:
                    if member.endswith(".xs") or member.endswith(".c") or member.endswith(".cc"):
                        # Distinguish top-level / src XS from test-only C files
                        parts = member.split("/")
                        if len(parts) > 1 and parts[1] == "t":
                            continue  # test file
                        if member.endswith(".xs"):
                            is_xs = True
                            break
        except Exception as err:
            logger.debug("Could not inspect tarball members for %s: %s", filename, err)

        return computed_sha256, is_xs, member_names


class CPANResolver:
    """Transitive dependency resolver and lockfile generator."""

    def __init__(
        self,
        index: CPANIndex,
        metacpan: MetaCPANClient,
        inspector: ArchiveInspector,
        phases: Optional[Set[str]] = None,
        verify_checksums: bool = True,
        max_workers: int = 16,
    ) -> None:
        self.index = index
        self.metacpan = metacpan
        self.inspector = inspector
        self.phases = phases or {"runtime", "configure", "build", "test"}
        self.verify_checksums = verify_checksums
        self.max_workers = max_workers

    def parse_deps_file(self, content_or_path: str) -> List[Requirement]:
        """Parses dependency specification file matching deps.txt format."""
        if "\n" not in content_or_path and os.path.exists(content_or_path):
            with open(content_or_path, "r", encoding="utf-8") as f:
                content = f.read()
        else:
            content = content_or_path

        requirements: List[Requirement] = []
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            # Strip inline comments
            if " #" in line:
                line = line.split(" #", 1)[0].strip()

            parts = line.split(None, 1)
            name = parts[0]
            version = parts[1].strip() if len(parts) > 1 else None

            # Clean version prefix (e.g. v3.4.0 -> 3.4.0, >= 1.0 -> 1.0)
            if version:
                version = re.sub(r"^[v>=<\s]+", "", version).strip()

            is_module = "::" in name
            requirements.append(Requirement(name=name, version=version, is_module=is_module))

        return requirements

    def resolve(self, requirements: List[Requirement]) -> Dict[str, ResolvedDistribution]:
        """Resolves transitive closure for requested requirements."""
        resolved: Dict[str, ResolvedDistribution] = {}
        # Map of provided module name -> distribution name
        provided_modules: Dict[str, str] = {}

        # Queue of (dist_name, requested_version)
        queue: List[Tuple[str, Optional[str]]] = []
        queued_dists: Set[str] = set()

        # Seed the queue from user requirements
        for req in requirements:
            dist_name: Optional[str] = None
            if req.is_module:
                dist_name = self.index.find_dist_for_module(req.name)
                if not dist_name:
                    dist_name = req.name.replace("::", "-")
            else:
                dist_name = req.name

            if dist_name and dist_name not in queued_dists:
                queued_dists.add(dist_name)
                queue.append((dist_name, req.version))

        # Iterative bulk resolution
        while queue:
            batch = queue[:]
            queue.clear()

            # Separate batch into latest vs exact version
            dists_for_bulk: List[str] = []
            exact_queries: List[Tuple[str, str]] = []

            for dist_name, version in batch:
                if dist_name in resolved:
                    continue
                if version:
                    exact_queries.append((dist_name, version))
                else:
                    dists_for_bulk.append(dist_name)

            # 1. Bulk query latest releases
            bulk_meta = self.metacpan.fetch_releases_bulk(dists_for_bulk)

            # 2. Query exact versions in parallel
            exact_meta: Dict[str, Dict[str, Any]] = {}
            if exact_queries:
                with concurrent.futures.ThreadPoolExecutor(
                    max_workers=self.max_workers
                ) as executor:
                    futures = {
                        executor.submit(
                            self.metacpan.fetch_release_exact, dist, ver
                        ): dist
                        for dist, ver in exact_queries
                    }
                    for fut in concurrent.futures.as_completed(futures):
                        dist = futures[fut]
                        try:
                            meta = fut.result()
                            if meta:
                                exact_meta[dist] = meta
                        except Exception as err:
                            logger.warning("Error fetching %s: %s", dist, err)

            # Combine metadata
            all_meta: Dict[str, Dict[str, Any]] = {**bulk_meta, **exact_meta}

            # Fallback for any distributions not returned by MetaCPAN API:
            # Use CPANIndex information
            for dist_name, _ in batch:
                if dist_name in resolved:
                    continue
                if dist_name not in all_meta:
                    if dist_name in self.index.dist_to_path:
                        path = self.index.dist_to_path[dist_name]
                        ver = self.index.dist_to_version.get(dist_name, "0")
                        all_meta[dist_name] = {
                            "distribution": dist_name,
                            "version": ver or "0",
                            "download_url": f"{self.index.mirror_url}/authors/id/{path}",
                            "checksum_sha256": None,
                            "dependency": [],
                            "provides": list(self.index.dist_to_packages.get(dist_name, [])),
                        }

            # Process metadata and discover new transitive dependencies
            new_modules_to_resolve: Set[str] = set()

            for dist_name, meta in all_meta.items():
                if dist_name in resolved:
                    continue

                version = str(meta.get("version", "0"))
                download_url = meta.get("download_url") or ""
                sha256 = meta.get("checksum_sha256") or ""
                raw_provides = meta.get("provides") or []
                provides: List[str] = []
                for p in raw_provides:
                    if isinstance(p, dict):
                        pkg = p.get("name") or p.get("package")
                        if pkg:
                            provides.append(pkg)
                    elif isinstance(p, str):
                        provides.append(p)

                # Track provided modules
                for pkg in provides:
                    provided_modules[pkg] = dist_name

                # Extract dependencies by phase
                dependencies: Dict[str, List[str]] = {
                    "build": [],
                    "configure": [],
                    "runtime": [],
                    "test": [],
                }

                raw_deps = meta.get("dependency", [])
                for dep in raw_deps:
                    phase = dep.get("phase", "runtime")
                    relationship = dep.get("relationship", "requires")
                    module = dep.get("module")

                    if not module or relationship != "requires":
                        continue
                    if phase not in self.phases:
                        continue

                    # Filter core perl modules
                    if self.index.is_core_module(module):
                        continue

                    dependencies[phase].append(module)
                    new_modules_to_resolve.add(module)

                resolved[dist_name] = ResolvedDistribution(
                    name=dist_name,
                    version=version,
                    download_url=download_url,
                    sha256=sha256,
                    provides=sorted(set(provides)),
                    dependencies={k: sorted(set(v)) for k, v in dependencies.items()},
                )

            # Map new modules to distributions and enqueue
            for module in new_modules_to_resolve:
                # Skip if already provided
                if module in provided_modules:
                    continue
                if self.index.is_core_module(module):
                    continue

                dep_dist = self.index.find_dist_for_module(module)
                if not dep_dist:
                    dep_dist = module.replace("::", "-")

                if dep_dist and dep_dist not in resolved and dep_dist not in queued_dists:
                    queued_dists.add(dep_dist)
                    queue.append((dep_dist, None))

        # Final pass: map module requirements to resolved distribution dependencies
        for dist_name, dist in resolved.items():
            mapped_deps: Dict[str, List[str]] = {
                "build": [],
                "configure": [],
                "runtime": [],
                "test": [],
            }
            for phase, modules in dist.dependencies.items():
                if phase not in mapped_deps:
                    mapped_deps[phase] = []
                for mod in modules:
                    target_dist = (
                        provided_modules.get(mod)
                        or self.index.find_dist_for_module(mod)
                        or mod.replace("::", "-")
                    )
                    if target_dist and target_dist != dist_name and target_dist in resolved:
                        mapped_deps[phase].append(target_dist)
            dist.dependencies = {
                phase: sorted(set(deps)) for phase, deps in mapped_deps.items()
            }

        # Checksum and XS verification pass
        self._verify_and_detect_xs(resolved)

        return resolved

    def _verify_and_detect_xs(self, resolved: Dict[str, ResolvedDistribution]) -> None:
        """Downloads/inspects distributions in parallel to verify SHA256 and detect XS."""
        dists_to_inspect = [
            dist for dist in resolved.values() if dist.download_url and self.verify_checksums
        ]

        if not dists_to_inspect:
            return

        logger.info(
            "Verifying checksums and detecting XS extensions for %d distributions...",
            len(dists_to_inspect),
        )

        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(
                    self.inspector.inspect_archive, dist.download_url, dist.sha256 or None
                ): dist
                for dist in dists_to_inspect
            }

            for fut in concurrent.futures.as_completed(futures):
                dist = futures[fut]
                try:
                    computed_sha256, is_xs, member_names = fut.result()
                    dist.sha256 = computed_sha256
                    dist.is_xs = is_xs
                    # If provides was empty, deduce from pm files in archive
                    if not dist.provides and member_names:
                        deduced: List[str] = []
                        for m in member_names:
                            if m.endswith(".pm"):
                                parts = m.split("/")
                                if len(parts) > 1 and parts[1] == "lib":
                                    pm_path = "/".join(parts[2:])
                                    mod_name = pm_path[: -len(".pm")].replace("/", "::")
                                    deduced.append(mod_name)
                        if deduced:
                            dist.provides = sorted(set(deduced))
                except Exception as err:
                    logger.warning("Error inspecting archive for %s: %s", dist.name, err)

    def generate_lockfile(
        self,
        requirements: List[Requirement],
        resolved: Dict[str, ResolvedDistribution],
        output_path: Optional[Path] = None,
    ) -> str:
        """Generates deterministic, human-readable lockfile JSON."""
        distributions_dict: Dict[str, Any] = {}

        for dist_name in sorted(resolved.keys()):
            dist = resolved[dist_name]
            distributions_dict[dist_name] = {
                "version": dist.version,
                "url": dist.download_url,
                "sha256": dist.sha256,
                "is_xs": dist.is_xs,
                "provides": dist.provides,
                "dependencies": dist.dependencies,
            }

        root_deps = [
            f"{req.name} {req.version}" if req.version else req.name
            for req in sorted(requirements, key=lambda r: r.name)
        ]

        lock_data = {
            "$schema": "https://raw.githubusercontent.com/manuelnaranjo/rules_cpan3/main/cpan.lock.schema.json",
            "lock_version": "1.0.0",
            "comment": "Auto-generated by rules_cpan resolver. DO NOT EDIT DIRECTLY.",
            "root_dependencies": root_deps,
            "distributions": distributions_dict,
        }

        content = json.dumps(lock_data, indent=2, sort_keys=True) + "\n"

        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(content, encoding="utf-8")
            logger.info("Emitted lockfile: %s (%d distributions)", output_path, len(resolved))

        return content


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fast bulk CPAN dependency resolver and lockfile generator for rules_cpan"
    )
    parser.add_argument(
        "-i",
        "--input",
        required=True,
        help="Path to dependency specification file (e.g. deps.txt)",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="cpan.lock.json",
        help="Output path for the generated lockfile (default: cpan.lock.json)",
    )
    parser.add_argument(
        "--cpan-mirror",
        default="https://cpan.metacpan.org",
        help="CPAN mirror base URL (default: https://cpan.metacpan.org)",
    )
    parser.add_argument(
        "--metacpan-api",
        default="https://fastapi.metacpan.org/v1",
        help="MetaCPAN API base URL (default: https://fastapi.metacpan.org/v1)",
    )
    parser.add_argument(
        "--cache-dir",
        default=None,
        help="Local cache directory for indices and archives (default: ~/.cache/rules_cpan)",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable disk caching",
    )
    parser.add_argument(
        "--no-verify-checksums",
        action="store_true",
        help="Skip downloading archives for SHA256 verification and XS detection",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=16,
        help="Number of concurrent download/query workers (default: 16)",
    )
    parser.add_argument(
        "--phases",
        default="runtime,configure,build,test",
        help="Comma-separated phases to include in closure (default: runtime,configure,build,test)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Resolve dependencies without writing lockfile to disk",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose debug logging",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="[cpan_resolver] %(levelname)s: %(message)s",
    )

    # Support Bazel run workspace directory
    workspace_root = os.environ.get("BUILD_WORKSPACE_DIRECTORY", "")
    input_path = Path(args.input)
    if workspace_root and not input_path.is_absolute():
        input_path = Path(workspace_root) / input_path

    output_path = Path(args.output)
    if workspace_root and not output_path.is_absolute():
        output_path = Path(workspace_root) / output_path

    if not input_path.exists():
        logger.error("Input file not found: %s", input_path)
        return 1

    cache_dir = Path(args.cache_dir) if args.cache_dir else Path.home() / ".cache" / "rules_cpan"

    phases = set(p.strip() for p in args.phases.split(",") if p.strip())

    cpan_index = CPANIndex(
        mirror_url=args.cpan_mirror,
        cache_dir=cache_dir,
        use_cache=not args.no_cache,
    )
    cpan_index.load()

    metacpan = MetaCPANClient(api_url=args.metacpan_api)
    inspector = ArchiveInspector(cache_dir=cache_dir, use_cache=not args.no_cache)

    resolver = CPANResolver(
        index=cpan_index,
        metacpan=metacpan,
        inspector=inspector,
        phases=phases,
        verify_checksums=not args.no_verify_checksums,
        max_workers=args.workers,
    )

    requirements = resolver.parse_deps_file(str(input_path))
    logger.info("Loaded %d root requirements from %s", len(requirements), input_path)

    resolved = resolver.resolve(requirements)
    logger.info("Resolved %d total distributions in dependency closure", len(resolved))

    if not args.dry_run:
        resolver.generate_lockfile(requirements, resolved, output_path=output_path)
    else:
        lock_content = resolver.generate_lockfile(requirements, resolved, output_path=None)
        print(lock_content)

    return 0


if __name__ == "__main__":
    sys.exit(main())
