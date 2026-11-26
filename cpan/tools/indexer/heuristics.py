"""Heuristics engine for CPAN distributions in rules_cpan indexer.

Provides detection and modeling of pure Perl vs XS extensions, typemaps,
Makefile.PL / Build.PL inspection, dynamic constants wrapping, and native C/C++
dependency mapping.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import re
import subprocess
import tarfile
import tempfile
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


def parse_yaml_subset(text: str) -> Dict[str, Any]:
    """Parses a YAML document with support for mappings, lists, and scalars."""
    try:
        import yaml
        return yaml.safe_load(text) or {}
    except Exception:
        pass

    result: Dict[str, Any] = {}
    current_key: Optional[str] = None

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line or line.strip().startswith("#"):
            continue

        indent = len(line) - len(line.lstrip())
        stripped = line.strip()

        if indent == 0 and ":" in stripped:
            parts = stripped.split(":", 1)
            k = parts[0].strip()
            v = parts[1].strip()
            if not v:
                result[k] = []
                current_key = k
            else:
                if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
                    v = v[1:-1]
                result[k] = v
                current_key = None
            continue

        if current_key is not None:
            if stripped.startswith("- "):
                val = stripped[2:].strip()
                if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                    val = val[1:-1]
                if not isinstance(result[current_key], list):
                    result[current_key] = []
                result[current_key].append(val)
            elif ":" in stripped:
                parts = stripped.split(":", 1)
                sub_k = parts[0].strip()
                sub_v = parts[1].strip()
                if (sub_v.startswith('"') and sub_v.endswith('"')) or (sub_v.startswith("'") and sub_v.endswith("'")):
                    sub_v = sub_v[1:-1]
                if not isinstance(result[current_key], dict):
                    result[current_key] = {}
                result[current_key][sub_k] = sub_v

    return result


def dump_yaml_subset(data: Dict[str, Any]) -> str:
    """Serializes a dictionary to YAML format."""
    try:
        import yaml
        return yaml.dump(data, sort_keys=False, default_flow_style=False)
    except Exception:
        pass

    lines = []
    for k, v in data.items():
        if isinstance(v, list):
            lines.append(f"{k}:")
            for item in v:
                lines.append(f"  - {item}")
        elif isinstance(v, dict):
            lines.append(f"{k}:")
            for sub_k, sub_v in v.items():
                lines.append(f"  {sub_k}: \"{sub_v}\"")
        elif isinstance(v, str):
            lines.append(f"{k}: {v}")
    return "\n".join(lines) + "\n"

logger = logging.getLogger("cpan_indexer.heuristics")

# Mapping of native library names to BCR modules and versions
NATIVE_DEP_MAP: Dict[str, Dict[str, str]] = {
    "zlib": {"bazel_dep": "zlib", "version": "1.3.1.bcr.5", "target": "@zlib"},
    "bzip2": {"bazel_dep": "bzip2", "version": "1.0.8.bcr.4", "target": "@bzip2"},
    "libexpat": {"bazel_dep": "libexpat", "version": "2.7.1.bcr.1", "target": "@libexpat"},
    "zstd": {"bazel_dep": "zstd", "version": "1.5.7.bcr.1", "target": "@zstd"},
    "openssl": {"bazel_dep": "openssl", "version": "3.3.1.bcr.13", "target": "@openssl"},
    "libxml2": {"bazel_dep": "libxml2", "version": "2.15.4", "target": "@libxml2"},
    "lz4": {"bazel_dep": "lz4", "version": "1.10.0.bcr.2", "target": "@lz4"},
    "snappy": {"bazel_dep": "snappy", "version": "1.2.2.bcr.3", "target": "@snappy"},
    "ncurses": {"bazel_dep": "ncurses", "version": "6.4.20221231.bcr.15", "target": "@ncurses"},
    "linux-pam": {"bazel_dep": "linux-pam", "version": "1.7.3", "target": "@linux-pam"},
    "libsodium": {"bazel_dep": "libsodium", "version": "1.0.19", "target": "@libsodium"},
    "gmp": {"bazel_dep": "gmp", "version": "6.3.0.bcr.5", "target": "@gmp"},
    "cmark": {"bazel_dep": "cmark", "version": "0.31.1.cpan-external.1", "target": "@cmark"},
    "libsass": {"bazel_dep": "libsass", "version": "3.6.6.cpan-external.1", "target": "@libsass"},
    "discount": {"bazel_dep": "discount", "version": "3.0.2.0.cpan-external.1", "target": "@discount"},
    "libiconv": {"bazel_dep": "libiconv", "version": "1.18.cpan-external.1", "target": "@libiconv"},
    "krb5": {"bazel_dep": "krb5", "version": "1.22.3.cpan-external.1", "target": "@krb5"},
    "libyaml": {"bazel_dep": "libyaml", "version": "0.2.5", "target": "@libyaml"},
    "grpc": {"bazel_dep": "grpc", "version": "1.85.4", "target": "@grpc"},
}

NATIVE_DEP_CONFIGS: List[Dict[str, Any]] = [
    {
        "patterns": [r"-lz\b", r"-lzlib\b", r"['\"]zlib['\"]", r"['\"]z['\"]"],
        "target": "@zlib",
    },
    {
        "patterns": [r"-lbz2\b", r"-lbzip2\b", r"['\"]bzip2['\"]", r"['\"]bz2['\"]"],
        "target": "@bzip2",
    },
    {
        "patterns": [r"-lexpat\b", r"['\"]expat['\"]", r"['\"]libexpat['\"]"],
        "target": "@libexpat",
    },
    {
        "patterns": [r"-lzstd\b", r"['\"]zstd['\"]"],
        "target": "@zstd",
    },
    {
        "patterns": [r"-lssl\b", r"-lcrypto\b", r"['\"]ssl['\"]", r"['\"]crypto['\"]", r"['\"]openssl['\"]"],
        "target": "@openssl",
    },
    {
        "patterns": [r"-lxml2\b", r"['\"]xml2['\"]", r"['\"]libxml2['\"]"],
        "target": "@libxml2",
    },
    {
        "patterns": [r"-llz4\b", r"['\"]lz4['\"]"],
        "target": "@lz4",
    },
    {
        "patterns": [r"-lsnappy\b", r"['\"]snappy['\"]"],
        "target": "@snappy",
    },
    {
        "patterns": [r"-lncurses\b", r"['\"]ncurses['\"]"],
        "target": "@ncurses",
    },
    {
        "patterns": [r"-lpam\b", r"['\"]pam['\"]"],
        "target": "@linux-pam",
    },
    {
        "patterns": [r"-lsodium\b", r"['\"]sodium['\"]"],
        "target": "@libsodium",
    },
    {
        "patterns": [r"-lgmp\b", r"['\"]gmp['\"]"],
        "target": "@gmp",
    },
    {
        "patterns": [r"-lcmark\b", r"['\"]cmark['\"]"],
        "target": "@cmark",
    },
    {
        "patterns": [r"-lsass\b", r"['\"]sass['\"]", r"['\"]libsass['\"]"],
        "target": "@libsass",
    },
    {
        "patterns": [r"-ldiscount\b", r"['\"]discount['\"]"],
        "target": "@discount",
    },
    {
        "patterns": [r"-liconv\b", r"['\"]iconv['\"]"],
        "target": "@libiconv",
    },
    {
        "patterns": [r"-lkrb5\b", r"['\"]krb5['\"]"],
        "target": "@krb5",
    },
    {
        "patterns": [r"-lyaml\b", r"['\"]yaml['\"]", r"['\"]libyaml['\"]"],
        "target": "@libyaml",
    },
]


def compute_sri_hash(data: bytes) -> str:
    """Computes Subresource Integrity (SRI) sha256 hash string."""
    digest = hashlib.sha256(data).digest()
    return f"sha256-{base64.b64encode(digest).decode('ascii')}"


def hex_to_sri(hex_sha: str) -> str:
    """Converts a standard hexadecimal SHA256 string into an SRI sha256 hash."""
    clean_hex = hex_sha.strip().lower()
    raw_bytes = bytes.fromhex(clean_hex)
    return f"sha256-{base64.b64encode(raw_bytes).decode('ascii')}"


def sanitize_module_name(dist_name: str) -> str:
    """Computes BCR module name: perl-<lowercase_with_hyphens>."""
    clean = re.sub(r"[^a-zA-Z0-9._-]+", "-", dist_name.lower())
    clean = clean.replace("_", "-").strip("-")
    return f"perl-{clean}"


def get_primary_module(dist_name: str, provides: List[str]) -> str:
    """Determines primary Perl module name (e.g. Algorithm::Diff)."""
    canonical_mod = dist_name.replace("-", "::")
    if not provides:
        return canonical_mod
    if canonical_mod in provides:
        return canonical_mod
    return provides[0]


def compute_output_loc(dist_name: str, provides: List[str]) -> str:
    """Computes DynaLoader/XSLoader auto/ directory location for an XS module."""
    primary_mod = get_primary_module(dist_name, provides)
    parts = primary_mod.split("::")
    path_prefix = "/".join(parts)
    leaf = parts[-1]
    return f"auto/{path_prefix}/{leaf}"


@dataclass
class GeneratorMetadata:
    """Per-module generator metadata loaded from generator-metadata.yaml."""

    manual_tests: List[str] = field(default_factory=list)
    test_services: List[str] = field(default_factory=list)
    test_exec_properties: Dict[str, str] = field(default_factory=dict)
    execution_requirements: Dict[str, str] = field(default_factory=dict)
    defines: List[str] = field(default_factory=list)
    includes: List[str] = field(default_factory=list)
    output_loc: Optional[str] = None
    native_deps: List[str] = field(default_factory=list)
    strip_prefix: Optional[str] = None
    target_compatible_with: List[str] = field(default_factory=list)
    exec_compatible_with: List[str] = field(default_factory=list)
    cc_srcs_exclude: List[str] = field(default_factory=list)
    patch_cmds: List[str] = field(default_factory=list)
    patch_cmds_win: List[str] = field(default_factory=list)

    @classmethod
    def from_yaml_file(cls, path: Path) -> GeneratorMetadata:
        if not path.exists():
            return cls()
        try:
            data = parse_yaml_subset(path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("Failed to load %s: %s", path, e)
            return cls()
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> GeneratorMetadata:
        return cls(
            manual_tests=list(data.get("manual_tests") or []),
            test_services=list(data.get("test_services") or []),
            test_exec_properties=dict(data.get("test_exec_properties") or {}),
            execution_requirements=dict(data.get("execution_requirements") or {}),
            defines=list(data.get("defines") or []),
            includes=list(data.get("includes") or []),
            output_loc=data.get("output_loc"),
            native_deps=list(data.get("native_deps") or []),
            strip_prefix=data.get("strip_prefix"),
            target_compatible_with=list(data.get("target_compatible_with") or []),
            exec_compatible_with=list(data.get("exec_compatible_with") or []),
            cc_srcs_exclude=list(data.get("cc_srcs_exclude") or data.get("cc_excludes") or []),
            patch_cmds=list(data.get("patch_cmds") or []),
            patch_cmds_win=list(data.get("patch_cmds_win") or []),
        )

    def to_dict(self) -> Dict[str, Any]:
        res: Dict[str, Any] = {}
        if self.manual_tests:
            res["manual_tests"] = self.manual_tests
        if self.test_services:
            res["test_services"] = self.test_services
        if self.test_exec_properties:
            res["test_exec_properties"] = self.test_exec_properties
        if self.execution_requirements:
            res["execution_requirements"] = self.execution_requirements
        if self.defines:
            res["defines"] = self.defines
        if self.includes:
            res["includes"] = self.includes
        if self.output_loc:
            res["output_loc"] = self.output_loc
        if self.native_deps:
            res["native_deps"] = self.native_deps
        if self.strip_prefix:
            res["strip_prefix"] = self.strip_prefix
        if self.target_compatible_with:
            res["target_compatible_with"] = self.target_compatible_with
        if self.exec_compatible_with:
            res["exec_compatible_with"] = self.exec_compatible_with
        if self.cc_srcs_exclude:
            res["cc_srcs_exclude"] = self.cc_srcs_exclude
        if self.patch_cmds:
            res["patch_cmds"] = self.patch_cmds
        if self.patch_cmds_win:
            res["patch_cmds_win"] = self.patch_cmds_win
        return res


def is_manual_test(rel_path: str, manual_patterns: List[str]) -> bool:
    """Checks whether a test path matches any manual test pattern or glob."""
    if not manual_patterns:
        return False
    clean_rel = rel_path.lstrip("./")
    leaf = Path(clean_rel).name
    t_name = clean_rel.replace("/", "_")
    if t_name.endswith(".t"):
        t_name = t_name[:-2]
    target_name = f"test_{re.sub(r'[^a-zA-Z0-9_.-]+', '_', t_name)}"

    for pat in manual_patterns:
        p = pat.strip()
        if p.startswith(":"):
            p = p[1:]
        if p == "*" or p == clean_rel or p == leaf or p == target_name or p == t_name:
            return True
        import fnmatch
        if fnmatch.fnmatch(clean_rel, p) or fnmatch.fnmatch(leaf, p) or fnmatch.fnmatch(target_name, p):
            return True
        if p.endswith("*") and (clean_rel.startswith(p[:-1]) or target_name.startswith(p[:-1])):
            return True
    return False


@dataclass
class DistributionInspection:
    """Results of inspecting a CPAN distribution directory or archive."""

    dist_name: str
    is_xs: bool = False
    provides: List[str] = field(default_factory=list)
    top_level_xs: List[str] = field(default_factory=list)
    fragment_xs: List[str] = field(default_factory=list)
    c_files: List[str] = field(default_factory=list)
    h_files: List[str] = field(default_factory=list)
    typemaps: List[str] = field(default_factory=list)
    included_c_files: List[str] = field(default_factory=list)
    defines: List[str] = field(default_factory=list)
    includes: List[str] = field(default_factory=list)
    native_deps: List[str] = field(default_factory=list)
    execution_requirements: Dict[str, str] = field(default_factory=dict)
    target_compatible_with: List[str] = field(default_factory=list)
    exec_compatible_with: List[str] = field(default_factory=list)
    overlay_files: Dict[str, bytes] = field(default_factory=dict)
    output_loc: str = ""
    t_files: List[str] = field(default_factory=list)


class HeuristicsEngine:
    """Applies heuristics to inspect CPAN distributions and generate BCR files."""

    def __init__(self) -> None:
        pass

    def inspect_directory(
        self,
        extract_dir: Path,
        dist_name: str,
        provides: Optional[List[str]] = None,
        is_xs_hint: Optional[bool] = None,
        generator_metadata: Optional[GeneratorMetadata] = None,
    ) -> DistributionInspection:
        """Inspects an unpacked CPAN distribution directory."""
        all_provides = list(provides or [])
        if not all_provides:
            all_provides = [get_primary_module(dist_name, [])]

        inspection = DistributionInspection(
            dist_name=dist_name,
            provides=all_provides,
            output_loc=compute_output_loc(dist_name, all_provides),
        )

        # 1. Inspect existing files
        xs_files: List[str] = []
        c_files: List[str] = []
        h_files: List[str] = []
        typemaps: List[str] = []

        for root, dirs, files in os.walk(extract_dir):
            rel_dir = os.path.relpath(root, extract_dir)
            if rel_dir == ".":
                rel_dir = ""

            # Skip auxiliary test and scratch directories
            parts = Path(rel_dir).parts
            if any(p in ["t", "xt", "_xs", "blib", ".git"] for p in parts):
                continue

            for f in files:
                rel_file = os.path.join(rel_dir, f) if rel_dir else f
                if f.endswith(".xs"):
                    xs_files.append(rel_file)
                elif f.endswith(".c"):
                    c_files.append(rel_file)
                elif f.endswith((".h", ".inc")):
                    h_files.append(rel_file)
                elif f == "typemap" or f.endswith(".typemap") or f.upper() == "TYPEMAP":
                    typemaps.append(rel_file)

        # Determine whether this is an XS distribution
        if is_xs_hint is not None:
            inspection.is_xs = is_xs_hint
        else:
            inspection.is_xs = len(xs_files) > 0 or len(c_files) > 0

        inspection.c_files = c_files
        inspection.h_files = h_files
        inspection.typemaps = typemaps

        # 2. Inspect XS files for top-level vs fragment files and included .c files
        included_c_files: List[str] = []
        top_level_xs: List[str] = []
        fragment_xs: List[str] = []

        for xs in xs_files:
            xs_path = extract_dir / xs
            content = self._safe_read_text(xs_path)

            if re.search(r"^\s*MODULE\s*=", content, re.MULTILINE):
                top_level_xs.append(xs)
            else:
                fragment_xs.append(xs)

            # Look for INCLUDE: <file> and #include "<file>.c"
            for line in content.splitlines():
                sline = line.strip()
                if sline.startswith("INCLUDE:"):
                    inc_target = sline.removeprefix("INCLUDE:").strip()
                    if inc_target.endswith(".xs"):
                        if inc_target not in fragment_xs:
                            fragment_xs.append(inc_target)
                elif sline.startswith("#") and "include" in sline:
                    c_includes = self._extract_c_includes(sline)
                    for c_inc in c_includes:
                        if c_inc not in included_c_files:
                            included_c_files.append(c_inc)

        inspection.top_level_xs = top_level_xs
        inspection.fragment_xs = fragment_xs
        inspection.included_c_files = included_c_files

        # 3. Dynamic constants: check fallback/constants.h and fallback/constants.xs
        fallback_h = extract_dir / "fallback" / "constants.h"
        fallback_xs = extract_dir / "fallback" / "constants.xs"
        if fallback_h.exists():
            inspection.overlay_files["constants.h"] = fallback_h.read_bytes()
        if fallback_xs.exists():
            inspection.overlay_files["constants.xs"] = fallback_xs.read_bytes()

        # 4. Synthesize Driver.xsi and DBI headers for DBD drivers
        if dist_name.startswith("DBD-") and dist_name != "DBD-Mock":
            driver_name = dist_name.removeprefix("DBD-")
            driver_xst = Path(__file__).resolve().parent.parent.parent / "resources" / "dbi" / "Driver.xst"
            if driver_xst.exists():
                xsi_content = driver_xst.read_text(encoding="utf-8").replace("~DRIVER~", driver_name)
                inspection.overlay_files[f"{driver_name}.xsi"] = xsi_content.encode("utf-8")
                for h_f in driver_xst.parent.glob("*.h"):
                    inspection.overlay_files[h_f.name] = h_f.read_bytes()

        # 5. Discover test files in t/
        t_dir = extract_dir / "t"
        t_files: List[str] = []
        if t_dir.is_dir():
            for root, _, files in os.walk(t_dir):
                for f in files:
                    if f.endswith(".t"):
                        full_p = Path(root) / f
                        rel_p = full_p.relative_to(extract_dir).as_posix()
                        t_files.append(rel_p)
        t_files.sort()
        inspection.t_files = t_files

        # 6. Inspect Makefile.PL and Build.PL for native libs, defines, and run build simulation
        self._inspect_build_scripts(extract_dir, inspection)

        # 7. Incorporate GeneratorMetadata customizations
        if generator_metadata:
            if generator_metadata.output_loc:
                inspection.output_loc = generator_metadata.output_loc
            if generator_metadata.defines:
                for d in generator_metadata.defines:
                    if d not in inspection.defines:
                        inspection.defines.append(d)
            if generator_metadata.native_deps:
                for n in generator_metadata.native_deps:
                    if n not in inspection.native_deps:
                        inspection.native_deps.append(n)
            if generator_metadata.includes:
                for inc in generator_metadata.includes:
                    if inc not in inspection.includes:
                        inspection.includes.append(inc)
            if generator_metadata.execution_requirements:
                inspection.execution_requirements.update(generator_metadata.execution_requirements)
            if generator_metadata.target_compatible_with:
                inspection.target_compatible_with = list(generator_metadata.target_compatible_with)
            if generator_metadata.exec_compatible_with:
                inspection.exec_compatible_with = list(generator_metadata.exec_compatible_with)
            if generator_metadata.defines or generator_metadata.output_loc or generator_metadata.includes:
                if len(xs_files) > 0 or len(c_files) > 0 or generator_metadata.output_loc:
                    inspection.is_xs = True

        return inspection

    def _safe_read_text(self, file_path: Path) -> str:
        """Safely reads file as UTF-8 or latin1 text."""
        try:
            return file_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return ""

    def _extract_c_includes(self, line: str) -> List[str]:
        parts = line.split('"')
        if len(parts) < 2:
            return []
        found: List[str] = []
        for part in parts:
            if part.endswith(".c") and ".." not in part:
                found.append(part)
        return found

    def _inspect_build_scripts(
        self,
        extract_dir: Path,
        inspection: DistributionInspection,
    ) -> None:
        """Scans Makefile.PL / Build.PL and simulates execution to capture generated code."""
        makefile_pl = extract_dir / "Makefile.PL"
        build_pl = extract_dir / "Build.PL"

        script_text = ""
        if makefile_pl.exists():
            script_text += self._safe_read_text(makefile_pl) + "\n"
        if build_pl.exists():
            script_text += self._safe_read_text(build_pl) + "\n"

        # Search for library linking flags: -lz, -lyaml, LIBS => ..., etc.
        for config in NATIVE_DEP_CONFIGS:
            for pat in config["patterns"]:
                if re.search(pat, script_text, re.IGNORECASE):
                    target = config["target"]
                    if target not in inspection.native_deps:
                        inspection.native_deps.append(target)
                    break

        # Search for preprocessor defines: -D...
        define_matches = re.findall(r"-D([A-Za-z0-9_]+(?:=[^\s\'\"\$]+)?)", script_text)
        for define in define_matches:
            clean_def = re.sub(r'[\'\"\\/]+$', '', define).strip()
            if clean_def and "$" not in clean_def and len(clean_def) > 1 and clean_def not in inspection.defines:
                inspection.defines.append(clean_def)

        # Attempt build system dry-run if Makefile.PL exists
        if not makefile_pl.exists():
            return

        existing_files = {p for p in extract_dir.rglob("*") if p.is_file()}
        try:
            env = dict(os.environ)
            env["PERL_MM_USE_DEFAULT"] = "1"
            env["AUTOMATED_TESTING"] = "1"
            env["NONINTERACTIVE_TESTING"] = "1"
            subprocess.run(
                ["perl", "Makefile.PL"],
                cwd=str(extract_dir),
                capture_output=True,
                stdin=subprocess.DEVNULL,
                timeout=5,
                env=env,
            )
        except Exception:
            return

        new_files = {p for p in extract_dir.rglob("*") if p.is_file()} - existing_files
        for new_file in new_files:
            rel = new_file.relative_to(extract_dir).as_posix()
            if rel.startswith("blib") or rel.startswith("."):
                continue

            # Check for generated xssubs.c or constants
            if rel.endswith((".c", ".h", ".xs", ".inc")):
                file_content = self._safe_read_text(new_file)
                if "xssubs.c" in rel:
                    file_content = self.wrap_constants_in_ifdef(file_content)
                inspection.overlay_files[rel] = file_content.encode("utf-8")

    def wrap_constants_in_ifdef(self, content: str) -> str:
        """Wraps newCONSTSUB calls in #ifdef guards for platform portability."""
        wrapped = re.sub(
            r'newCONSTSUB\(stash,\s*"([A-Za-z0-9_]+)",\s*newSViv\(\1\)\);',
            r'#ifdef \1\nnewCONSTSUB(stash, "\1", newSViv(\1));\n#else\nnewCONSTSUB(stash, "\1", newSV(0));\n#endif',
            content,
        )
        return wrapped

    def generate_build_bazel(
        self,
        inspection: DistributionInspection,
        module_name: str,
        runtime_deps: Optional[List[str]] = None,
        test_deps: Optional[List[str]] = None,
        test_runner_label: str = "@rules_cpan//cpan:test_runner.pl",
        generator_metadata: Optional[GeneratorMetadata] = None,
    ) -> str:
        """Generates BUILD.bazel content for overlay/BUILD.bazel."""
        dist = inspection.dist_name
        valid_runtime_deps = [d for d in (runtime_deps or []) if d.startswith(("@", ":"))]
        valid_test_deps = [d for d in (test_deps or []) if d.startswith(("@", ":"))]

        cpan_deps_str = ""
        if valid_runtime_deps:
            items = [f'"{d}"' for d in valid_runtime_deps]
            cpan_deps_str = "\n        " + ",\n        ".join(items) + ",\n    "

        # Target and exec constraints
        target_compat_items = (
            generator_metadata.target_compatible_with if generator_metadata and generator_metadata.target_compatible_with
            else inspection.target_compatible_with
        )
        target_compat_str = ""
        if target_compat_items:
            target_compat_str = "\n    target_compatible_with = [" + ", ".join([f'"{c}"' for c in target_compat_items]) + "],"

        exec_compat_items = (
            generator_metadata.exec_compatible_with if generator_metadata and generator_metadata.exec_compatible_with
            else inspection.exec_compatible_with
        )
        exec_compat_str = ""
        if exec_compat_items:
            exec_compat_str = "\n    exec_compatible_with = [" + ", ".join([f'"{c}"' for c in exec_compat_items]) + "],"

        # Includes
        extra_includes = list(inspection.includes)
        if generator_metadata and generator_metadata.includes:
            for inc in generator_metadata.includes:
                if inc not in extra_includes:
                    extra_includes.append(inc)

        perl_lib_includes = ["lib"] + [inc for inc in extra_includes if inc != "lib"]
        perl_lib_includes_str = "\n        " + ",\n        ".join([f'"{inc}"' for inc in perl_lib_includes]) + ",\n    "

        # Build test rules if t/ directory has test files
        test_content = ""
        load_perl_test = ', "perl_test"' if inspection.t_files else ""
        if inspection.t_files:
            test_target_names: List[Tuple[str, bool]] = []
            test_target_blocks: List[str] = []
            manual_tests = generator_metadata.manual_tests if generator_metadata else []

            for rel_path in inspection.t_files:
                clean_name = rel_path.replace("/", "_")
                if clean_name.endswith(".t"):
                    clean_name = clean_name[:-2]
                sanitized = re.sub(r"[^a-zA-Z0-9_.-]+", "_", clean_name)
                target_name = f"test_{sanitized}"

                is_manual = is_manual_test(rel_path, manual_tests)
                tags: List[str] = []
                if is_manual:
                    tags.append("manual")
                if generator_metadata and generator_metadata.execution_requirements:
                    for req_k in generator_metadata.execution_requirements:
                        if req_k not in tags:
                            tags.append(req_k)
                tags_str = ""
                if tags:
                    tags_items = [f'"{t}"' for t in tags]
                    tags_str = "\n    tags = [" + ", ".join(tags_items) + "],"

                test_services = generator_metadata.test_services if generator_metadata else []
                test_args = []
                for svc in test_services:
                    test_args.append(f"--service={svc}")
                test_args.append(rel_path)
                args_items = [f'"{a}"' for a in test_args]
                args_str = "[" + ", ".join(args_items) + "]"

                test_size = "medium" if test_services else "small"

                exec_props: Dict[str, str] = {}
                if test_services:
                    exec_props["init-dockerd"] = "true"
                    exec_props["test.init-dockerd"] = "true"
                    exec_props["test.workload-isolation-type"] = "firecracker"
                    exec_props["workload-isolation-type"] = "firecracker"
                if generator_metadata and generator_metadata.test_exec_properties:
                    exec_props.update(generator_metadata.test_exec_properties)

                exec_props_str = ""
                if exec_props:
                    exec_props_str = "\n    exec_properties = {\n" + ",\n".join(
                        [f'        "{k}": "{v}"' for k, v in sorted(exec_props.items())]
                    ) + ",\n    },"

                test_target_names.append((f'":{target_name}"', is_manual))

                test_target_blocks.append(f"""perl_test(
    name = "{target_name}",
    size = "{test_size}",
    srcs = ["{test_runner_label}"],
    args = {args_str},{tags_str}{exec_props_str}{target_compat_str}{exec_compat_str}
    deps = [":{dist}_test_lib"],
)""")

            non_manual_tests = [t for t, is_man in test_target_names if not is_man]
            if non_manual_tests:
                tests_str = ",\n        ".join(non_manual_tests)
                suite_tags = ""
            else:
                tests_str = ",\n        ".join([t for t, _ in test_target_names])
                suite_tags = '\n    tags = ["manual"],'

            test_deps_items = [f'"{d}"' for d in valid_test_deps]
            test_deps_str = (",\n        " + ",\n        ".join(test_deps_items)) if test_deps_items else ""

            test_content = f"""
perl_library(
    name = "{dist}_test_lib",
    srcs = glob(["t/**/*.pm", "t/*.pm"], allow_empty = True),
    data = glob(
        ["t/**/*"],
        exclude = [
            "t/**/*.pm",
            "t/*.pm",
        ],
        allow_empty = True,
    ),
    includes = ["t", "t/lib"],
    deps = [":{dist}"{test_deps_str}],
)

""" + "\n\n".join(test_target_blocks) + f"""

test_suite(
    name = "test",{suite_tags}
    tests = [
        {tests_str},
    ],
)
"""

        if not inspection.is_xs:
            return f"""# Auto-generated by rules_cpan for {dist}
load("@rules_perl//perl:defs.bzl", "perl_library"{load_perl_test})

package(default_visibility = ["//visibility:public"])

perl_library(
    name = "{dist}",
    srcs = glob([
        "lib/**/*.pm",
        "lib/**/*.pod",
        "*.pm",
    ], allow_empty = True),
    data = glob([
        "lib/**/*",
    ], exclude = [
        "lib/**/*.pm",
        "lib/**/*.pod",
    ], allow_empty = True),
    includes = [{perl_lib_includes_str}],{target_compat_str}{exec_compat_str}
    deps = [{cpan_deps_str}],
)

alias(
    name = "{module_name}",
    actual = ":{dist}",
)
{test_content}"""

        # XS extension BUILD.bazel
        output_loc = (
            generator_metadata.output_loc
            if generator_metadata and generator_metadata.output_loc
            else inspection.output_loc
        )
        all_native_deps = list(inspection.native_deps)
        if generator_metadata and generator_metadata.native_deps:
            for n in generator_metadata.native_deps:
                if n not in all_native_deps:
                    all_native_deps.append(n)
        native_deps_items = [f'"{d}"' for d in all_native_deps]
        native_deps_str = ""
        if native_deps_items:
            native_deps_str = "\n        " + ",\n        ".join(native_deps_items) + ",\n    "

        xs_srcs = [f'"{x}"' for x in inspection.top_level_xs] if inspection.top_level_xs else ['"*.xs"']
        xs_srcs_str = ", ".join(xs_srcs)

        cc_excludes = [
            '"_xs/**"',
            '"t/**"',
            '"fallback/**"',
            '"conf/**"',
        ]
        if generator_metadata and generator_metadata.cc_srcs_exclude:
            for exc in generator_metadata.cc_srcs_exclude:
                quoted = f'"{exc}"'
                if quoted not in cc_excludes:
                    cc_excludes.append(quoted)
        for inc_c in inspection.included_c_files:
            quoted = f'"{inc_c}"'
            if quoted not in cc_excludes:
                cc_excludes.append(quoted)
        cc_excludes_str = "\n        " + ",\n        ".join(cc_excludes) + ",\n    "

        if generator_metadata and generator_metadata.defines:
            all_defines = list(generator_metadata.defines)
        else:
            all_defines = [
                d for d in inspection.defines
                if "$" not in d and " " not in d and not d.endswith("=") and not d.startswith("/") and len(d) > 1
            ]
        defines_items = [f'"{d}"' for d in all_defines]
        defines_str = ""
        if defines_items:
            defines_str = "\n        " + ",\n        ".join(defines_items) + ",\n    "

        xs_includes_str = ""
        if extra_includes:
            xs_includes_items = [f'"{inc}"' for inc in extra_includes]
            xs_includes_str = "\n    includes = [\n        " + ",\n        ".join(xs_includes_items) + ",\n    ],"

        xs_exec_reqs_str = ""
        xs_exec_reqs = dict(inspection.execution_requirements)
        if generator_metadata and generator_metadata.execution_requirements:
            xs_exec_reqs.update(generator_metadata.execution_requirements)
        if xs_exec_reqs:
            xs_exec_reqs_str = "\n    execution_requirements = {\n" + ",\n".join(
                [f'        "{k}": "{v}"' for k, v in sorted(xs_exec_reqs.items())]
            ) + ",\n    },"

        return f"""# Auto-generated by rules_cpan for {dist} (XS extension)
load("@rules_cpan//cpan:defs.bzl", "cpan_xs")
load("@rules_perl//perl:defs.bzl", "perl_library"{load_perl_test})

package(default_visibility = ["//visibility:public"])

cpan_xs(
    name = "{dist}_xs",
    srcs = [{xs_srcs_str}],
    cc_srcs = glob([
        "*.c",
        "**/*.c",
    ], exclude = [{cc_excludes_str}], allow_empty = True),
    defines = [{defines_str}],{xs_includes_str}{xs_exec_reqs_str}{target_compat_str}{exec_compat_str}
    output_loc = "{output_loc}",
    textual_hdrs = glob([
        "*.h",
        "**/*.h",
        "*.xs",
        "**/*.xs",
        "*.xsi",
        "**/*.xsi",
        "*.inc",
        "**/*.inc",
    ], allow_empty = True),
    typemaps = glob([
        "*typemap*",
        "**/*typemap*",
        "*TYPEMAP*",
        "**/*TYPEMAP*",
    ], allow_empty = True),
    deps = [{native_deps_str}],
)

perl_library(
    name = "{dist}",
    srcs = glob([
        "lib/**/*.pm",
        "lib/**/*.pod",
        "*.pm",
    ], allow_empty = True),
    data = [
        ":{dist}_xs",
    ] + glob([
        "lib/**/*",
    ], exclude = [
        "lib/**/*.pm",
        "lib/**/*.pod",
    ], allow_empty = True),
    includes = [{perl_lib_includes_str}],{target_compat_str}{exec_compat_str}
    deps = [{cpan_deps_str}],
)

alias(
    name = "{module_name}",
    actual = ":{dist}",
)
{test_content}"""

    def _resolve_dep_version(
        self,
        dep_name: str,
        cpan_deps: Optional[List[Tuple[str, str]]] = None,
        modules_dir: Optional[Path] = None,
    ) -> str:
        """Resolves the version for a dependency, checking cpan_deps, metadata.json, or fallback."""
        if cpan_deps:
            for mod, ver in cpan_deps:
                if mod == dep_name:
                    return ver

        search_dirs: List[Path] = []
        if modules_dir and modules_dir.exists():
            search_dirs.append(modules_dir)
        default_modules = Path("cpan-index/modules")
        if default_modules.exists() and default_modules not in search_dirs:
            search_dirs.append(default_modules)

        for m_dir in search_dirs:
            meta_path = m_dir / dep_name / "metadata.json"
            if meta_path.exists():
                try:
                    data = json.loads(meta_path.read_text(encoding="utf-8"))
                    versions = data.get("versions", [])
                    if versions:
                        return versions[-1]
                except Exception:
                    pass

        return "0.0.0"

    def generate_module_bazel(
        self,
        module_name: str,
        version: str,
        native_deps: Optional[List[str]] = None,
        cpan_deps: Optional[List[Tuple[str, str]]] = None,
        modules_dir: Optional[Path] = None,
    ) -> str:
        """Generates MODULE.bazel for the BCR module."""
        lines = [
            "module(",
            f'    name = "{module_name}",',
            f'    version = "{version}",',
            ")",
            "",
            'bazel_dep(name = "rules_cpan", version = "0.0.0")',
            'bazel_dep(name = "rules_perl", version = "2.1.0")',
            'bazel_dep(name = "rules_cc", version = "0.2.28")',
            'bazel_dep(name = "platforms", version = "1.1.0")',
        ]

        seen_deps = {"rules_cpan", "rules_perl", "rules_cc", "platforms", module_name}

        if native_deps:
            for nat_target in native_deps:
                dep_label = nat_target.lstrip("@").split("//")[0].split(":")[0]
                if dep_label.startswith("cpan__"):
                    dep_label = sanitize_module_name(dep_label.removeprefix("cpan__"))
                dep_info = NATIVE_DEP_MAP.get(dep_label)
                if dep_info:
                    dep_name = dep_info["bazel_dep"]
                    if dep_name not in seen_deps:
                        seen_deps.add(dep_name)
                        lines.append(f'bazel_dep(name = "{dep_name}", version = "{dep_info["version"]}")')
                elif dep_label.startswith("perl-"):
                    if dep_label not in seen_deps:
                        seen_deps.add(dep_label)
                        dep_ver = self._resolve_dep_version(dep_label, cpan_deps, modules_dir)
                        lines.append(f'bazel_dep(name = "{dep_label}", version = "{dep_ver}")')
                else:
                    if dep_label not in seen_deps:
                        seen_deps.add(dep_label)
                        lines.append(f'bazel_dep(name = "{dep_label}", version = "0.0.0")')

        if cpan_deps:
            for cpan_mod, cpan_ver in cpan_deps:
                if cpan_mod not in seen_deps:
                    seen_deps.add(cpan_mod)
                    lines.append(f'bazel_dep(name = "{cpan_mod}", version = "{cpan_ver}")')

        return "\n".join(lines) + "\n"
