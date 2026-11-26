#!/usr/bin/env python3
"""Out-of-build Gazelle-style indexer tool for rules_cpan.

Resolves CPAN dependencies against the local cpan-index BCR registry, refactors
older version ports, applies heuristics for new/unknown distributions, and
synchronizes workspace MODULE.bazel declarations.
"""

from __future__ import annotations

import argparse
import base64
import json
import logging
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# Enable running both within Bazel (with runfiles/package layout) and standalone
try:
    from cpan.tools.indexer.heuristics import (
        DistributionInspection,
        GeneratorMetadata,
        HeuristicsEngine,
        compute_output_loc,
        compute_sri_hash,
        hex_to_sri,
        is_manual_test,
        sanitize_module_name,
    )
except ImportError:
    try:
        from heuristics import (
            DistributionInspection,
            GeneratorMetadata,
            HeuristicsEngine,
            compute_output_loc,
            compute_sri_hash,
            hex_to_sri,
            is_manual_test,
            sanitize_module_name,
        )
    except ImportError:
        # Fallback to sys.path resolution
        sys.path.insert(0, str(Path(__file__).parent))
        from heuristics import (
            DistributionInspection,
            GeneratorMetadata,
            HeuristicsEngine,
            compute_output_loc,
            compute_sri_hash,
            hex_to_sri,
            is_manual_test,
            sanitize_module_name,
        )

logger = logging.getLogger("cpan_indexer")


def normalize_overlay_text(rel_name: str, data: bytes) -> bytes:
    """Normalizes line endings to LF and strips trailing whitespace for text overlay files."""
    text_extensions = (
        ".c", ".h", ".inc", ".pm", ".pod", ".pl", ".xs", ".xsi",
        ".txt", ".yaml", ".yml", ".json", ".bazel", ".t", ".sh",
    )
    if not rel_name.endswith(text_extensions):
        return data
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = data.decode("latin-1")
        except Exception:
            return data
    lines = [line.rstrip() for line in text.splitlines()]
    normalized = "\n".join(lines).strip()
    if normalized:
        normalized += "\n"
    return normalized.encode("utf-8")


def deduplicate_module_bazel_deps(content: str) -> str:
    """Removes duplicate bazel_dep declarations by dependency name."""
    lines = content.splitlines()
    seen = set()
    new_lines = []
    dep_pattern = re.compile(r'^\s*bazel_dep\(\s*name\s*=\s*"(?P<name>[^"]+)"')
    for line in lines:
        m = dep_pattern.match(line)
        if m:
            dep_name = m.group("name")
            if dep_name in seen:
                continue
            seen.add(dep_name)
        new_lines.append(line)
    return "\n".join(new_lines).strip() + "\n"


@dataclass
class IndexResolution:
    """Result of checking a distribution in the cpan-index."""

    dist_name: str
    module_name: str
    requested_version: str
    status: str  # EXACT_MATCH, OLDER_VERSION_EXISTS, NEW_DISTRIBUTION
    matched_version: Optional[str] = None
    source_template_version: Optional[str] = None
    target_version: Optional[str] = None


class IndexManager:
    """Manages queries, port refactoring, and indexing in cpan-index."""

    def __init__(self, index_dir: Path) -> None:
        self.index_dir = index_dir.resolve()
        self.modules_dir = self.index_dir / "modules"
        self.heuristics = HeuristicsEngine()
        self.lock_distributions: Dict[str, Dict[str, Any]] = {}
        self.lock_distributions_by_mod: Dict[str, Dict[str, Any]] = {}

    def load_lockfile(self, lockfile_path: Path) -> None:
        """Loads distribution dependency information from a cpan.lock.json file."""
        if not lockfile_path.exists():
            return
        try:
            data = json.loads(lockfile_path.read_text(encoding="utf-8"))
            dists = data.get("distributions", {})
            for d_name, d_info in dists.items():
                self.lock_distributions[d_name] = d_info
                self.lock_distributions_by_mod[sanitize_module_name(d_name)] = d_info
        except Exception as e:
            logger.warning("Failed loading lockfile %s: %s", lockfile_path, e)

    def get_module_dir(self, module_name: str) -> Path:
        return self.modules_dir / module_name

    def get_generator_metadata(self, module_name: str) -> Optional[GeneratorMetadata]:
        meta_file = self.get_module_dir(module_name) / "generator-metadata.yaml"
        if meta_file.exists():
            return GeneratorMetadata.from_yaml_file(meta_file)
        return None

    def list_existing_versions(self, module_name: str) -> List[Tuple[str, int, str]]:
        """Returns list of (upstream_version, build_id, full_version_str) sorted."""
        module_dir = self.get_module_dir(module_name)
        if not module_dir.exists():
            return []

        meta_file = module_dir / "metadata.json"
        versions_list: List[str] = []
        if meta_file.exists():
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
                versions_list = list(meta.get("versions", []))
            except Exception:
                pass

        # Also inspect directories
        for entry in module_dir.iterdir():
            if entry.is_dir() and entry.name not in versions_list:
                versions_list.append(entry.name)

        parsed: List[Tuple[str, int, str]] = []
        pattern = re.compile(r"^(?P<upstream>.+)\.cpan(?P<build_id>\d+)$")
        for v in versions_list:
            m = pattern.match(v)
            if m:
                upstream = m.group("upstream")
                build_id = int(m.group("build_id"))
                parsed.append((upstream, build_id, v))

        # Sort by upstream and build_id
        parsed.sort(key=lambda item: (self._version_key(item[0]), item[1]))
        return parsed

    def _version_key(self, ver: str) -> List[int]:
        """Simple numeric-aware version comparison key."""
        clean = ver.lstrip("v")
        parts = re.split(r"[\._-]", clean)
        key = []
        for p in parts:
            if p.isdigit():
                key.append(int(p))
            else:
                key.append(0)
        return key

    def resolve(self, dist_name: str, requested_version: str) -> IndexResolution:
        """Resolves distribution against cpan-index."""
        module_name = sanitize_module_name(dist_name)
        clean_version = requested_version.lstrip("v")
        existing_versions = self.list_existing_versions(module_name)

        if not existing_versions:
            return IndexResolution(
                dist_name=dist_name,
                module_name=module_name,
                requested_version=clean_version,
                status="NEW_DISTRIBUTION",
                target_version=f"{clean_version}.cpan1",
            )

        # Check for exact upstream version match
        matching_builds = [item for item in existing_versions if item[0] == clean_version]
        if matching_builds:
            highest_match = matching_builds[-1]
            return IndexResolution(
                dist_name=dist_name,
                module_name=module_name,
                requested_version=clean_version,
                status="EXACT_MATCH",
                matched_version=highest_match[2],
                target_version=highest_match[2],
            )

        # Older version exists; pick the latest available version as template
        template_item = existing_versions[-1]
        return IndexResolution(
            dist_name=dist_name,
            module_name=module_name,
            requested_version=clean_version,
            status="OLDER_VERSION_EXISTS",
            source_template_version=template_item[2],
            target_version=f"{clean_version}.cpan1",
        )

    def refactor_older_version(
        self,
        module_name: str,
        dist_name: str,
        source_version: str,
        target_version: str,
        upstream_version: str,
        archive_url: str,
        archive_sha256: str,
    ) -> Path:
        """Clones and refactors an older version port to the target upstream version."""
        module_dir = self.get_module_dir(module_name)
        src_dir = module_dir / source_version
        dest_dir = module_dir / target_version

        if not src_dir.exists():
            raise FileNotFoundError(f"Source version directory {src_dir} does not exist")

        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_overlay = dest_dir / "overlay"
        dest_overlay.mkdir(parents=True, exist_ok=True)

        # 1. Clone and update MODULE.bazel
        src_module = src_dir / "MODULE.bazel"
        if src_module.exists():
            content = src_module.read_text(encoding="utf-8")
            # Replace module version = "..." with target_version (only the first match for the module itself)
            updated_content = re.sub(
                r'version\s*=\s*"[^"]+"',
                f'version = "{target_version}"',
                content,
                count=1,
            )
            (dest_dir / "MODULE.bazel").write_text(updated_content, encoding="utf-8")
        else:
            # Generate minimal MODULE.bazel
            content = self.heuristics.generate_module_bazel(
                module_name,
                target_version,
                modules_dir=self.modules_dir,
            )
            (dest_dir / "MODULE.bazel").write_text(content, encoding="utf-8")

        # 2. Clone overlay/ directory
        src_overlay = src_dir / "overlay"
        overlay_sris: Dict[str, str] = {}
        if src_overlay.exists():
            for root, _, files in os.walk(src_overlay):
                for f in files:
                    p = Path(root) / f
                    rel_p = p.relative_to(src_overlay)
                    target_file = dest_overlay / rel_p
                    target_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(p, target_file)

                    # Compute SRI hash
                    overlay_sris[rel_p.as_posix()] = compute_sri_hash(target_file.read_bytes())

        # 3. Update source.json
        archive_sri = hex_to_sri(archive_sha256)
        src_source_json = src_dir / "source.json"
        preserved_prefix = None
        if src_source_json.exists():
            try:
                src_data = json.loads(src_source_json.read_text(encoding="utf-8"))
                old_prefix = src_data.get("strip_prefix", "")
                if old_prefix:
                    if old_prefix.endswith(f"-{source_version}"):
                        stem = old_prefix[:-len(f"-{source_version}")]
                        preserved_prefix = f"{stem}-{upstream_version}"
                    elif old_prefix.endswith(source_version):
                        stem = old_prefix[:-len(source_version)]
                        preserved_prefix = f"{stem}{upstream_version}"
            except Exception:
                pass

        strip_prefix = (
            preserved_prefix
            if preserved_prefix
            else self._compute_strip_prefix(archive_url, dist_name, upstream_version)
        )

        source_data = {
            "url": archive_url,
            "integrity": archive_sri,
            "strip_prefix": strip_prefix,
            "overlay": overlay_sris,
        }
        (dest_dir / "source.json").write_text(
            json.dumps(source_data, indent=4) + "\n", encoding="utf-8"
        )

        # 4. Update metadata.json
        self._add_version_to_metadata(module_dir, dist_name, target_version)
        logger.info("Refactored port %s: %s -> %s", module_name, source_version, target_version)
        return dest_dir

    def bump_build_id(self, module_name: str, upstream_version: str) -> str:
        """Increments build-id for an existing upstream version in cpan-index."""
        existing = [item for item in self.list_existing_versions(module_name) if item[0] == upstream_version]
        if not existing:
            raise ValueError(f"No existing version for {module_name} {upstream_version}")

        latest_item = existing[-1]
        next_build_id = latest_item[1] + 1
        new_version = f"{upstream_version}.cpan{next_build_id}"

        module_dir = self.get_module_dir(module_name)
        src_dir = module_dir / latest_item[2]
        dest_dir = module_dir / new_version

        # Check if generator-metadata exists and source.json is present
        generator_metadata = self.get_generator_metadata(module_name)
        source_json_file = src_dir / "source.json"
        if generator_metadata and source_json_file.exists():
            try:
                return self.regenerate_port(module_name, upstream_version, bump_build_id=True)
            except Exception as e:
                logger.warning("Could not fully regenerate port from tarball for %s: %s", module_name, e)

        shutil.copytree(src_dir, dest_dir)

        # Update MODULE.bazel
        dest_module = dest_dir / "MODULE.bazel"
        if dest_module.exists():
            content = dest_module.read_text(encoding="utf-8")
            updated = re.sub(
                r'version\s*=\s*"[^"]+"',
                f'version = "{new_version}"',
                content,
                count=1,
            )
            dest_module.write_text(updated, encoding="utf-8")

        self._add_version_to_metadata(module_dir, module_name, new_version)
        logger.info("Bumped build-id for %s: %s -> %s", module_name, latest_item[2], new_version)
        return new_version

    def regenerate_port(
        self,
        module_name: str,
        upstream_version: Optional[str] = None,
        bump_build_id: bool = True,
    ) -> str:
        """Regenerates a port using generator-metadata.yaml, bumping build-id if requested."""
        existing = self.list_existing_versions(module_name)
        if not existing:
            raise ValueError(f"No existing version for {module_name}")

        if upstream_version:
            matching = [item for item in existing if item[0] == upstream_version]
            if not matching:
                raise ValueError(f"Version {upstream_version} not found for {module_name}")
            source_item = matching[-1]
        else:
            source_item = existing[-1]

        target_upstream, current_build_id, current_full_ver = source_item
        next_build_id = (current_build_id + 1) if bump_build_id else current_build_id
        target_version = f"{target_upstream}.cpan{next_build_id}"

        module_dir = self.get_module_dir(module_name)
        src_ver_dir = module_dir / current_full_ver
        source_json_file = src_ver_dir / "source.json"
        if not source_json_file.exists():
            raise FileNotFoundError(f"source.json not found in {src_ver_dir}")

        source_data = json.loads(source_json_file.read_text(encoding="utf-8"))
        archive_url = source_data.get("url", "")
        # Extract dist_name from metadata or module_name
        dist_name = module_name.removeprefix("perl-")
        meta_file = module_dir / "metadata.json"
        if meta_file.exists():
            try:
                mdata = json.loads(meta_file.read_text(encoding="utf-8"))
                hp = mdata.get("homepage", "")
                if "/dist/" in hp:
                    dist_name = hp.split("/dist/")[-1]
            except Exception:
                pass

        existing_mb_text = None
        src_mb = src_ver_dir / "MODULE.bazel"
        if src_mb.exists():
            existing_mb_text = src_mb.read_text(encoding="utf-8")

        existing_overlay = src_ver_dir / "overlay"
        dest_dir = self.create_new_port(
            dist_name=dist_name,
            upstream_version=target_upstream,
            archive_url=archive_url,
            archive_sha256="",
            target_version=target_version,
            existing_overlay_dir=existing_overlay if existing_overlay.exists() else None,
        )

        # Preserve and update MODULE.bazel from source version if available
        dest_mb = dest_dir / "MODULE.bazel"
        new_mb_text = dest_mb.read_text(encoding="utf-8") if dest_mb.exists() else ""
        if existing_mb_text and new_mb_text:
            existing_deps = [
                line for line in existing_mb_text.splitlines()
                if line.strip().startswith("bazel_dep(")
            ]
            merged = new_mb_text.rstrip() + "\n" + "\n".join(existing_deps) + "\n"
            dest_mb.write_text(deduplicate_module_bazel_deps(merged), encoding="utf-8")
        elif dest_mb.exists():
            dest_mb.write_text(deduplicate_module_bazel_deps(new_mb_text), encoding="utf-8")

        return target_version

    def create_new_port(
        self,
        dist_name: str,
        upstream_version: str,
        archive_url: str,
        archive_sha256: str,
        archive_path: Optional[Path] = None,
        is_xs_hint: Optional[bool] = None,
        provides: Optional[List[str]] = None,
        runtime_deps: Optional[List[str]] = None,
        test_deps: Optional[List[str]] = None,
        target_version: Optional[str] = None,
        existing_overlay_dir: Optional[Path] = None,
    ) -> Path:
        """Creates a brand new BCR module port using heuristics engine."""
        module_name = sanitize_module_name(dist_name)
        if not target_version:
            target_version = f"{upstream_version.lstrip('v')}.cpan1"
        module_dir = self.get_module_dir(module_name)
        dest_dir = module_dir / target_version
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_overlay = dest_dir / "overlay"
        dest_overlay.mkdir(parents=True, exist_ok=True)

        if test_deps is None or runtime_deps is None or provides is None:
            if not self.lock_distributions:
                ws_root = self.index_dir.parent
                for candidate in [
                    ws_root / "e2e" / "deps_txt" / "cpan.lock.json",
                    ws_root / "e2e" / "pakket" / "cpan.lock.json",
                    ws_root / "tests" / "cpan.lock.json",
                    ws_root / "cpan.lock.json",
                ]:
                    if candidate.exists():
                        self.load_lockfile(candidate)

            lock_info = self.lock_distributions.get(dist_name) or self.lock_distributions_by_mod.get(module_name)
            if lock_info:
                deps = lock_info.get("dependencies", {})
                if test_deps is None:
                    test_deps = deps.get("test", [])
                if runtime_deps is None:
                    runtime_deps = deps.get("runtime", [])
                if provides is None:
                    provides = lock_info.get("provides", [])
                if is_xs_hint is None:
                    is_xs_hint = bool(lock_info.get("is_xs", False))

        generator_metadata = self.get_generator_metadata(module_name)

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            tar_file = archive_path
            if not tar_file or not tar_file.exists():
                cache_dirs = [
                    Path(os.environ.get("RULES_CPAN_CACHE_DIR", "")),
                    Path.home() / ".cache" / "rules_cpan" / "dist",
                ]
                filename = archive_url.split("/")[-1] if archive_url else ""
                found_in_cache = False
                if filename:
                    for c_dir in cache_dirs:
                        if str(c_dir) and (c_dir / filename).exists():
                            tar_file = c_dir / filename
                            found_in_cache = True
                            break

                if not found_in_cache:
                    if archive_url.startswith("file://"):
                        tar_file = Path(archive_url.removeprefix("file://"))
                    else:
                        tar_file = tmp_path / "dist.tar.gz"
                        logger.info("Downloading %s from %s ...", dist_name, archive_url)
                        req = urllib.request.Request(
                            archive_url,
                            headers={"User-Agent": "rules_cpan/indexer"},
                        )
                        with urllib.request.urlopen(req, timeout=60) as resp:
                            content = resp.read()
                            tar_file.write_bytes(content)
                            default_cache = Path.home() / ".cache" / "rules_cpan" / "dist"
                            if default_cache.exists() and filename:
                                try:
                                    (default_cache / filename).write_bytes(content)
                                except Exception:
                                    pass

            if not archive_sha256 and tar_file and tar_file.exists():
                import hashlib
                archive_sha256 = hashlib.sha256(tar_file.read_bytes()).hexdigest()

            extract_dir = tmp_path / "extract"
            extract_dir.mkdir(parents=True, exist_ok=True)
            try:
                with tarfile.open(tar_file, "r:*") as tar:
                    tar.extractall(extract_dir)
            except Exception as e:
                logger.warning("Failed to unpack tarball %s: %s", tar_file, e)

            # Strip root directory if single top-level folder
            entries = list(extract_dir.iterdir())
            top_dir = entries[0] if len(entries) == 1 and entries[0].is_dir() else extract_dir

            # Seed synthesized overlay with existing overlay files if available
            synthesized_overlay: Dict[str, bytes] = {}
            if existing_overlay_dir and existing_overlay_dir.is_dir():
                for fpath in existing_overlay_dir.rglob("*"):
                    if fpath.is_file() and fpath.name != "BUILD.bazel":
                        rel_str = fpath.relative_to(existing_overlay_dir).as_posix()
                        synthesized_overlay[rel_str] = fpath.read_bytes()

            # Apply patch_cmds if present
            deleted_c_files: List[str] = []
            if generator_metadata and (generator_metadata.patch_cmds or generator_metadata.patch_cmds_win):
                cmds = generator_metadata.patch_cmds_win if platform.system() == "Windows" and generator_metadata.patch_cmds_win else generator_metadata.patch_cmds
                pre_files = {p.relative_to(top_dir): p.read_bytes() for p in top_dir.rglob("*") if p.is_file()}
                for cmd in cmds:
                    try:
                        subprocess.run(cmd, shell=True, cwd=str(top_dir), check=True)
                    except Exception as e:
                        logger.warning("Failed executing patch_cmd '%s': %s", cmd, e)
                post_files = {p.relative_to(top_dir): p for p in top_dir.rglob("*") if p.is_file()}
                for rel_p, p in post_files.items():
                    rel_str = rel_p.as_posix()
                    if any(part in ["blib", ".git"] for part in rel_p.parts):
                        continue
                    if rel_p not in pre_files or pre_files[rel_p] != p.read_bytes():
                        synthesized_overlay[rel_str] = p.read_bytes()
                for rel_p in pre_files:
                    if rel_p not in post_files:
                        rel_str = rel_p.as_posix()
                        if rel_str.endswith((".c", ".xs")) and rel_str not in deleted_c_files:
                            deleted_c_files.append(rel_str)

            inspection = self.heuristics.inspect_directory(
                extract_dir=top_dir,
                dist_name=dist_name,
                provides=provides,
                is_xs_hint=is_xs_hint,
                generator_metadata=generator_metadata,
            )
            if existing_overlay_dir and existing_overlay_dir.exists():
                inspection.overlay_files = dict(synthesized_overlay)
            else:
                for s_rel, s_data in synthesized_overlay.items():
                    inspection.overlay_files[s_rel] = s_data
            for d_c in deleted_c_files:
                if d_c not in inspection.included_c_files:
                    inspection.included_c_files.append(d_c)

            # Write overlay files from inspection (constants.h, xssubs.c, etc.)
            overlay_sris: Dict[str, str] = {}
            for rel_name, data in inspection.overlay_files.items():
                target_f = dest_overlay / rel_name
                target_f.parent.mkdir(parents=True, exist_ok=True)
                clean_data = normalize_overlay_text(rel_name, data)
                target_f.write_bytes(clean_data)
                if clean_data.startswith(b"#!"):
                    try:
                        target_f.chmod(0o755)
                    except Exception:
                        pass
                overlay_sris[rel_name] = compute_sri_hash(clean_data)

            # Write overlay/BUILD.bazel
            build_bazel_content = self.heuristics.generate_build_bazel(
                inspection=inspection,
                module_name=module_name,
                runtime_deps=runtime_deps,
                test_deps=test_deps,
                generator_metadata=generator_metadata,
            )
            build_file = dest_overlay / "BUILD.bazel"
            build_file.write_text(build_bazel_content, encoding="utf-8")
            overlay_sris["BUILD.bazel"] = compute_sri_hash(build_file.read_bytes())

            # Write MODULE.bazel
            module_bazel_content = self.heuristics.generate_module_bazel(
                module_name=module_name,
                version=target_version,
                native_deps=inspection.native_deps,
                test_deps=test_deps if inspection.t_files else None,
                modules_dir=self.modules_dir,
            )
            (dest_dir / "MODULE.bazel").write_text(module_bazel_content, encoding="utf-8")

            # Write source.json
            archive_sri = hex_to_sri(archive_sha256)
            if generator_metadata and generator_metadata.strip_prefix:
                strip_prefix = generator_metadata.strip_prefix
            elif len(entries) == 1 and entries[0].is_dir():
                strip_prefix = entries[0].name
            elif len(entries) > 1:
                strip_prefix = ""
            else:
                strip_prefix = self._compute_strip_prefix(
                    archive_url, dist_name, upstream_version, tar_file
                )
            source_data = {
                "url": archive_url,
                "integrity": archive_sri,
                "strip_prefix": strip_prefix,
                "overlay": overlay_sris,
            }
            (dest_dir / "source.json").write_text(
                json.dumps(source_data, indent=4) + "\n", encoding="utf-8"
            )

            # Write/update metadata.json
            self._add_version_to_metadata(module_dir, dist_name, target_version)

        logger.info("Created new port %s %s in %s", module_name, target_version, dest_dir)
        return dest_dir

    def _compute_strip_prefix(
        self,
        url: str,
        dist_name: str,
        version: str,
        archive_path: Optional[Path] = None,
    ) -> str:
        if archive_path and archive_path.exists():
            try:
                with tarfile.open(archive_path, "r:*") as tar:
                    top_entries = set(n.split("/")[0] for n in tar.getnames() if n)
                    if len(top_entries) == 1:
                        return list(top_entries)[0]
                    if len(top_entries) > 1:
                        return ""
            except Exception:
                pass

        filename = url.split("/")[-1] if url else ""
        if filename:
            cache_dirs = [
                Path(os.environ.get("RULES_CPAN_CACHE_DIR", "")),
                Path.home() / ".cache" / "rules_cpan" / "dist",
            ]
            for c_dir in cache_dirs:
                c_tar = c_dir / filename
                if str(c_dir) and c_tar.exists():
                    try:
                        with tarfile.open(c_tar, "r:*") as tar:
                            top_entries = set(n.split("/")[0] for n in tar.getnames() if n)
                            if len(top_entries) == 1:
                                return list(top_entries)[0]
                            if len(top_entries) > 1:
                                return ""
                    except Exception:
                        pass
                    break

        for ext in [".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tar.xz", ".txz", ".zip"]:
            if filename.endswith(ext):
                return filename[: -len(ext)]
        return f"{dist_name}-{version}"

    def _add_version_to_metadata(self, module_dir: Path, dist_name: str, new_version: str) -> None:
        meta_file = module_dir / "metadata.json"
        if meta_file.exists():
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
            except Exception:
                meta = {}
        else:
            meta = {
                "homepage": f"https://metacpan.org/dist/{dist_name}",
                "maintainers": [
                    {
                        "name": "rules_cpan maintainers",
                        "github": "manuelnaranjo",
                    }
                ],
                "versions": [],
                "yanked_versions": {},
            }

        versions: List[str] = meta.get("versions", [])
        if new_version not in versions:
            versions.append(new_version)
            meta["versions"] = versions

        meta_file.write_text(json.dumps(meta, indent=4) + "\n", encoding="utf-8")


def sync_workspace_module_bazel(
    module_bazel_path: Path,
    dependencies: Dict[str, str],
) -> bool:
    """Synchronizes direct bazel_dep declarations in workspace MODULE.bazel.

    Args:
        module_bazel_path: Path to workspace MODULE.bazel.
        dependencies: Dictionary mapping module_name -> version string.

    Returns:
        True if MODULE.bazel was modified, False otherwise.
    """
    if not module_bazel_path.exists():
        logger.warning("MODULE.bazel not found at %s", module_bazel_path)
        return False

    content = module_bazel_path.read_text(encoding="utf-8")
    lines = content.splitlines()
    modified = False

    dep_regex = re.compile(
        r'^\s*bazel_dep\(\s*name\s*=\s*"(?P<name>[^"]+)"\s*,\s*version\s*=\s*"(?P<version>[^"]+)"(?P<rest>.*)\)\s*$'
    )

    remaining_deps = dict(dependencies)
    new_lines: List[str] = []

    for line in lines:
        m = dep_regex.match(line)
        if m:
            dep_name = m.group("name")
            current_ver = m.group("version")
            rest = m.group("rest")

            if dep_name in remaining_deps:
                target_ver = remaining_deps.pop(dep_name)
                if current_ver != target_ver:
                    line = f'bazel_dep(name = "{dep_name}", version = "{target_ver}"{rest})'
                    modified = True
            new_lines.append(line)
        else:
            new_lines.append(line)

    # Append any remaining new dependencies
    if remaining_deps:
        modified = True
        new_lines.append("")
        new_lines.append("# CPAN dependencies indexed by rules_cpan indexer")
        for dep_name, dep_ver in sorted(remaining_deps.items()):
            new_lines.append(f'bazel_dep(name = "{dep_name}", version = "{dep_ver}")')

    if modified:
        module_bazel_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        logger.info("Updated MODULE.bazel at %s", module_bazel_path)

    return modified


class CPANIndexer:
    """Orchestrates dependency index resolution, port refactoring, and workspace sync."""

    def __init__(
        self,
        index_dir: Path,
        workspace_dir: Path,
        bump_build_id: bool = False,
        lockfile_path: Optional[Path] = None,
    ) -> None:
        self.workspace_dir = workspace_dir
        self.index_dir = index_dir
        self.index_mgr = IndexManager(index_dir)
        self.bump_build_id = bump_build_id

        if lockfile_path and lockfile_path.exists():
            self.index_mgr.load_lockfile(lockfile_path)

        for candidate in [
            workspace_dir / "e2e" / "deps_txt" / "cpan.lock.json",
            workspace_dir / "e2e" / "pakket" / "cpan.lock.json",
            workspace_dir / "tests" / "cpan.lock.json",
            workspace_dir / "cpan.lock.json",
        ]:
            if candidate.exists() and candidate != lockfile_path:
                self.index_mgr.load_lockfile(candidate)

    def index_distribution(
        self,
        dist_name: str,
        version: str,
        url: str,
        sha256: str,
        is_xs: bool = False,
        provides: Optional[List[str]] = None,
        dependencies: Optional[Dict[str, List[str]]] = None,
        archive_path: Optional[Path] = None,
    ) -> str:
        """Indexes a single distribution and returns the resolved BCR version."""
        res = self.index_mgr.resolve(dist_name, version)
        runtime_cpan_deps = dependencies.get("runtime", []) if dependencies else []
        test_cpan_deps = dependencies.get("test", []) if dependencies else []

        if res.status == "EXACT_MATCH":
            if self.bump_build_id:
                new_ver = self.index_mgr.bump_build_id(res.module_name, res.requested_version)
                return new_ver
            return res.matched_version  # type: ignore

        if res.status == "OLDER_VERSION_EXISTS":
            self.index_mgr.refactor_older_version(
                module_name=res.module_name,
                dist_name=dist_name,
                source_version=res.source_template_version,  # type: ignore
                target_version=res.target_version,  # type: ignore
                upstream_version=res.requested_version,
                archive_url=url,
                archive_sha256=sha256,
            )
            return res.target_version  # type: ignore

        # NEW_DISTRIBUTION
        self.index_mgr.create_new_port(
            dist_name=dist_name,
            upstream_version=version,
            archive_url=url,
            archive_sha256=sha256,
            archive_path=archive_path,
            is_xs_hint=is_xs,
            provides=provides,
            runtime_deps=runtime_cpan_deps,
            test_deps=test_cpan_deps,
        )
        return res.target_version  # type: ignore

    def index_lockfile(
        self,
        lockfile_path: Path,
        sync_module_bazel: bool = True,
        module_bazel_path: Optional[Path] = None,
    ) -> Dict[str, str]:
        """Indexes all distributions in a cpan.lock.json lockfile."""
        if not lockfile_path.exists():
            raise FileNotFoundError(f"Lockfile {lockfile_path} does not exist")

        self.index_mgr.load_lockfile(lockfile_path)
        data = json.loads(lockfile_path.read_text(encoding="utf-8"))
        dists = data.get("distributions", {})
        root_deps = data.get("root_dependencies", [])

        resolved_versions: Dict[str, str] = {}
        logger.info("Indexing %d distributions from lockfile %s ...", len(dists), lockfile_path)

        for dist_name, d_info in dists.items():
            version = str(d_info.get("version", ""))
            url = d_info.get("url", "")
            sha256 = d_info.get("sha256", "")
            is_xs = bool(d_info.get("is_xs", False))
            provides = list(d_info.get("provides", []))
            dependencies = d_info.get("dependencies", {})

            bcr_version = self.index_distribution(
                dist_name=dist_name,
                version=version,
                url=url,
                sha256=sha256,
                is_xs=is_xs,
                provides=provides,
                dependencies=dependencies,
            )
            module_name = sanitize_module_name(dist_name)
            resolved_versions[module_name] = bcr_version

        # Synchronize direct root dependencies to workspace MODULE.bazel
        if sync_module_bazel:
            target_mb = module_bazel_path or (self.workspace_dir / "MODULE.bazel")
            direct_deps_to_sync: Dict[str, str] = {}
            for root_req in root_deps:
                root_name = root_req.split()[0]
                mod_name = sanitize_module_name(root_name)
                if mod_name in resolved_versions:
                    direct_deps_to_sync[mod_name] = resolved_versions[mod_name]

            if direct_deps_to_sync:
                sync_workspace_module_bazel(target_mb, direct_deps_to_sync)

        return resolved_versions


def parse_args(args: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="rules_cpan Gazelle-style out-of-build indexer tool."
    )
    parser.add_argument(
        "--index-dir",
        help="Path to cpan-index registry directory (default: cpan-index in workspace root).",
    )
    parser.add_argument(
        "--lock",
        "--lockfile",
        dest="lockfile",
        help="Path to cpan.lock.json lockfile to index.",
    )
    parser.add_argument(
        "--module-bazel",
        help="Path to workspace MODULE.bazel file to synchronize.",
    )
    parser.add_argument(
        "--sync-module-bazel",
        action="store_true",
        default=True,
        help="Synchronize direct dependencies into workspace MODULE.bazel (default: True).",
    )
    parser.add_argument(
        "--no-sync-module-bazel",
        dest="sync_module_bazel",
        action="store_false",
        help="Do not synchronize workspace MODULE.bazel.",
    )
    parser.add_argument(
        "--distribution",
        "-d",
        help="Single CPAN distribution name to index (e.g. Algorithm-Diff).",
    )
    parser.add_argument(
        "--version",
        "-v",
        help="Distribution upstream release version (e.g. 1.201).",
    )
    parser.add_argument(
        "--archive",
        help="Path to local distribution tarball.",
    )
    parser.add_argument(
        "--bump-build-id",
        action="store_true",
        help="Force increment build-id if matching version is already in index.",
    )
    parser.add_argument(
        "--regenerate",
        action="store_true",
        help="Regenerate BCR port from generator-metadata.yaml.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Apply regeneration across all modules in cpan-index, not just those with generator-metadata.yaml.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging output.",
    )
    return parser.parse_args(args)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format="%(levelname)s: %(message)s")

    workspace_dir = Path(
        os.environ.get("BUILD_WORKSPACE_DIRECTORY", os.getcwd())
    ).resolve()
    index_dir = (
        Path(args.index_dir).resolve()
        if args.index_dir
        else workspace_dir / "cpan-index"
    )

    if not index_dir.exists():
        logger.error("cpan-index directory not found at %s", index_dir)
        return 1

    lock_path = Path(args.lockfile) if args.lockfile else None
    if lock_path and not lock_path.is_absolute():
        lock_path = workspace_dir / lock_path

    indexer = CPANIndexer(
        index_dir=index_dir,
        workspace_dir=workspace_dir,
        bump_build_id=args.bump_build_id,
        lockfile_path=lock_path,
    )

    if args.regenerate:
        if args.distribution:
            mod_name = sanitize_module_name(args.distribution)
            new_ver = indexer.index_mgr.regenerate_port(
                module_name=mod_name,
                upstream_version=args.version,
                bump_build_id=args.bump_build_id,
            )
            print(f"[cpan_indexer] Successfully regenerated {mod_name} -> {new_ver}")
            return 0
        else:
            # Regenerate modules
            count = 0
            for mod_entry in sorted((index_dir / "modules").iterdir()):
                if not mod_entry.is_dir():
                    continue
                has_metadata = (mod_entry / "generator-metadata.yaml").exists()
                if args.all or has_metadata:
                    try:
                        new_ver = indexer.index_mgr.regenerate_port(
                            module_name=mod_entry.name,
                            bump_build_id=args.bump_build_id,
                        )
                        print(f"[cpan_indexer] Regenerated {mod_entry.name} -> {new_ver}")
                        count += 1
                    except Exception as e:
                        logger.warning("Failed regenerating %s: %s", mod_entry.name, e)
            print(f"[cpan_indexer] Successfully regenerated {count} modules")
            return 0

    if args.lockfile:
        lock_path = Path(args.lockfile)
        if not lock_path.is_absolute():
            lock_path = workspace_dir / lock_path
        mb_path = Path(args.module_bazel) if args.module_bazel else None
        if mb_path and not mb_path.is_absolute():
            mb_path = workspace_dir / mb_path

        resolved = indexer.index_lockfile(
            lockfile_path=lock_path,
            sync_module_bazel=args.sync_module_bazel,
            module_bazel_path=mb_path,
        )
        print(f"[cpan_indexer] Successfully indexed {len(resolved)} distributions from {lock_path}")
        return 0

    if args.distribution:
        dist_name = args.distribution
        version = args.version or "1.0.0"
        archive_path = Path(args.archive) if args.archive else None
        archive_sha256 = ""
        url = ""

        if archive_path and archive_path.exists():
            archive_sha256 = hashlib.sha256(archive_path.read_bytes()).hexdigest()
            url = f"file://{archive_path.name}"
        else:
            # Query MetaCPAN for archive URL and sha256
            api_url = f"https://fastapi.metacpan.org/v1/release/{dist_name}"
            req = urllib.request.Request(api_url, headers={"User-Agent": "rules_cpan/indexer"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                meta = json.loads(resp.read().decode("utf-8"))
            url = meta.get("download_url", "")
            version = str(meta.get("version", version)).lstrip("v")
            archive_sha256 = meta.get("checksum_sha256", "")

        resolved_ver = indexer.index_distribution(
            dist_name=dist_name,
            version=version,
            url=url,
            sha256=archive_sha256,
            archive_path=archive_path,
        )
        module_name = sanitize_module_name(dist_name)
        if args.sync_module_bazel:
            mb_path = Path(args.module_bazel) if args.module_bazel else workspace_dir / "MODULE.bazel"
            sync_workspace_module_bazel(mb_path, {module_name: resolved_ver})

        print(f"[cpan_indexer] Successfully indexed {dist_name} -> {module_name} {resolved_ver}")
        return 0

    # Default fallback: check if cpan.lock.json or tests/cpan.lock.json exists in workspace
    default_lock = workspace_dir / "cpan.lock.json"
    if not default_lock.exists():
        default_lock = workspace_dir / "tests" / "cpan.lock.json"

    if default_lock.exists():
        indexer.index_lockfile(
            lockfile_path=default_lock,
            sync_module_bazel=args.sync_module_bazel,
        )
        print(f"[cpan_indexer] Successfully indexed default lockfile: {default_lock}")
        return 0

    logger.error("No --lock or --distribution provided and no default lockfile found.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
