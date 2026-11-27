"""Heuristics engine for CPAN distributions in rules_cpan indexer.

Provides detection and modeling of pure Perl vs XS extensions, typemaps,
Makefile.PL / Build.PL inspection, dynamic constants wrapping, and native C/C++
dependency mapping.
"""

from __future__ import annotations

import base64
import fnmatch
import hashlib
import json
import logging
import os
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
from typing import Any, Dict, List, Optional, Set, Tuple, Union

import yaml
from runfiles import Runfiles


def find_runfiles_binary(
    candidates: List[str],
    keyword: str,
    suffix: Union[str, Tuple[str, ...]],
) -> Optional[Path]:
    """Finds a hermetic binary in Bazel runfiles across candidate paths or the runfiles manifest/tree."""
    try:
        r = Runfiles.Create()
    except Exception:
        r = None
    if not r:
        return None

    for cand in candidates:
        try:
            resolved = r.Rlocation(cand)
            if resolved and Path(resolved).is_file() and os.access(resolved, os.X_OK):
                return Path(resolved)
        except Exception:
            pass

    strategy = getattr(r, "_strategy", None)
    if strategy:
        runfiles_dict = getattr(strategy, "_runfiles", None)
        if isinstance(runfiles_dict, dict):
            for rpath, fpath in runfiles_dict.items():
                if keyword in rpath and rpath.endswith(suffix):
                    if Path(fpath).is_file() and os.access(fpath, os.X_OK):
                        return Path(fpath)

        get_dir = getattr(strategy, "_GetRunfilesDir", None)
        if callable(get_dir):
            rf_dir = Path(get_dir())
            if rf_dir.exists():
                binary_name = candidates[0].split("/")[-1]
                for p in rf_dir.rglob(binary_name):
                    if p.is_file() and os.access(p, os.X_OK):
                        return Path(fpath if (fpath := p).is_file() else p)

    return None


def find_perl_binary() -> Optional[Path]:
    """Finds hermetic perl binary from rules_perl toolchain runfiles using bazel-runfiles."""
    return find_runfiles_binary(
        candidates=[
            "rules_perl/perl/bin/perl",
            "rules_perl/bin/perl",
        ],
        keyword="rules_perl",
        suffix="/bin/perl",
    )


def find_buildifier_binary() -> Optional[Path]:
    """Finds hermetic buildifier binary from buildifier_prebuilt runfiles using bazel-runfiles."""
    return find_runfiles_binary(
        candidates=[
            "buildifier_prebuilt/buildifier/buildifier.bash",
            "buildifier_prebuilt/buildifier",
            "buildifier_prebuilt/file/buildifier",
        ],
        keyword="buildifier",
        suffix=("/buildifier", "/buildifier.bash"),
    )


def parse_yaml_subset(text: str) -> Dict[str, Any]:
    """Parses a YAML document with PyYAML (no fallback)."""
    parsed = yaml.safe_load(text)
    return parsed if isinstance(parsed, dict) else {}


def dump_yaml_subset(data: Dict[str, Any]) -> str:
    """Serializes a dictionary to YAML format using PyYAML."""
    return yaml.dump(data, sort_keys=True, default_flow_style=False)

logger = logging.getLogger("cpan_indexer.heuristics")

# Mapping of native library names to BCR modules and versions
NATIVE_DEP_MAP: Dict[str, Dict[str, str]] = {
    "zlib": {"bazel_dep": "zlib", "version": "1.3.1.bcr.5", "target": "@zlib"},
    "bzip2": {"bazel_dep": "bzip2", "version": "1.0.8.bcr.4", "target": "@bzip2//:bz2"},
    "libexpat": {"bazel_dep": "libexpat", "version": "2.7.1.bcr.1", "target": "@libexpat"},
    "zstd": {"bazel_dep": "zstd", "version": "1.5.7.bcr.1", "target": "@zstd"},
    "openssl": {"bazel_dep": "openssl", "version": "3.3.1.bcr.13", "target": "@openssl//:ssl"},
    "libxml2": {"bazel_dep": "libxml2", "version": "2.15.4", "target": "@libxml2"},
    "lz4": {"bazel_dep": "lz4", "version": "1.10.0.bcr.2", "target": "@lz4"},
    "snappy": {"bazel_dep": "snappy", "version": "1.2.2.bcr.3", "target": "@snappy"},
    "ncurses": {"bazel_dep": "ncurses", "version": "6.4.20221231.bcr.15", "target": "@ncurses//:ncurses"},
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
        "target": "@bzip2//:bz2",
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
        "patterns": [
            r"-lssl\b",
            r"-lcrypto\b",
            r"['\"]ssl['\"]",
            r"['\"]crypto['\"]",
            r"['\"]openssl['\"]",
            r"\blibcrypto\b",
            r"\blibssl\b",
        ],
        "target": "@openssl//:ssl",
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
        "target": "@ncurses//:ncurses",
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

    is_xs: Optional[bool] = None
    manual_tests: List[str] = field(default_factory=list)
    test_services: List[str] = field(default_factory=list)
    test_exec_properties: Dict[str, str] = field(default_factory=dict)
    execution_requirements: Dict[str, str] = field(default_factory=dict)
    defines: List[str] = field(default_factory=list)
    defines_select: Dict[str, List[str]] = field(default_factory=dict)
    linkopts: List[str] = field(default_factory=list)
    linkopts_select: Dict[str, List[str]] = field(default_factory=dict)
    includes: List[str] = field(default_factory=list)
    output_loc: Optional[str] = None
    native_deps: List[str] = field(default_factory=list)
    strip_prefix: Optional[str] = None
    target_compatible_with: List[str] = field(default_factory=list)
    exec_compatible_with: List[str] = field(default_factory=list)
    cc_srcs_exclude: List[str] = field(default_factory=list)
    test_data_exclude: List[str] = field(default_factory=list)
    extra_deps: List[str] = field(default_factory=list)
    extra_test_deps: List[str] = field(default_factory=list)
    patch_cmds: List[str] = field(default_factory=list)
    patch_cmds_win: List[str] = field(default_factory=list)
    file_copies: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_yaml_file(cls, path: Path) -> GeneratorMetadata:
        if not path.exists():
            return cls()
        data = parse_yaml_subset(path.read_text(encoding="utf-8"))
        return cls.from_dict(data, source_path=path)

    @classmethod
    def from_dict(cls, data: Dict[str, Any], source_path: Optional[Path] = None) -> GeneratorMetadata:
        if not isinstance(data, dict):
            path_str = f" in {source_path}" if source_path else ""
            raise TypeError(f"Generator metadata{path_str} must be a mapping/dict, got {type(data).__name__}")

        valid_keys = {
            "is_xs",
            "manual_tests",
            "test_services",
            "test_exec_properties",
            "execution_requirements",
            "defines",
            "defines_select",
            "linkopts",
            "linkopts_select",
            "includes",
            "output_loc",
            "native_deps",
            "strip_prefix",
            "target_compatible_with",
            "exec_compatible_with",
            "cc_srcs_exclude",
            "test_data_exclude",
            "extra_deps",
            "extra_test_deps",
            "patch_cmds",
            "patch_cmds_win",
            "file_copies",
        }
        unknown_keys = sorted(set(data.keys()) - valid_keys)
        if unknown_keys:
            path_str = f" in {source_path}" if source_path else ""
            raise ValueError(
                f"Unknown key(s) in generator metadata{path_str}: {', '.join(unknown_keys)}. "
                f"Allowed keys are: {', '.join(sorted(valid_keys))}"
            )

        is_xs = data.get("is_xs")
        if is_xs is not None and not isinstance(is_xs, bool):
            path_str = f" in {source_path}" if source_path else ""
            raise TypeError(
                f"'is_xs'{path_str} must be a boolean (True or False), got {type(is_xs).__name__}: {is_xs!r}"
            )

        def _check_list_str(key: str) -> List[str]:
            val = data.get(key)
            if val is None:
                return []
            if not isinstance(val, list) or not all(isinstance(x, str) for x in val):
                path_str = f" in {source_path}" if source_path else ""
                raise TypeError(f"'{key}'{path_str} must be a list of strings, got {val!r}")
            return list(val)

        def _check_dict_str(key: str) -> Dict[str, str]:
            val = data.get(key)
            if val is None:
                return {}
            if not isinstance(val, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in val.items()):
                path_str = f" in {source_path}" if source_path else ""
                raise TypeError(f"'{key}'{path_str} must be a dict of string -> string, got {val!r}")
            return dict(val)

        def _check_dict_list_str(key: str) -> Dict[str, List[str]]:
            val = data.get(key)
            if val is None:
                return {}
            if not isinstance(val, dict):
                path_str = f" in {source_path}" if source_path else ""
                raise TypeError(f"'{key}'{path_str} must be a dict of string -> list[str], got {val!r}")
            for k, v in val.items():
                if not isinstance(k, str) or not isinstance(v, list) or not all(isinstance(x, str) for x in v):
                    path_str = f" in {source_path}" if source_path else ""
                    raise TypeError(f"'{key}'{path_str} entries must be string -> list of strings, got {k!r}: {v!r}")
            return dict(val)

        def _check_opt_str(key: str) -> Optional[str]:
            val = data.get(key)
            if val is not None and not isinstance(val, str):
                path_str = f" in {source_path}" if source_path else ""
                raise TypeError(f"'{key}'{path_str} must be a string or null, got {val!r}")
            return val

        return cls(
            is_xs=is_xs,
            manual_tests=_check_list_str("manual_tests"),
            test_services=_check_list_str("test_services"),
            test_exec_properties=_check_dict_str("test_exec_properties"),
            execution_requirements=_check_dict_str("execution_requirements"),
            defines=_check_list_str("defines"),
            defines_select=_check_dict_list_str("defines_select"),
            linkopts=_check_list_str("linkopts"),
            linkopts_select=_check_dict_list_str("linkopts_select"),
            includes=_check_list_str("includes"),
            output_loc=_check_opt_str("output_loc"),
            native_deps=_check_list_str("native_deps"),
            strip_prefix=_check_opt_str("strip_prefix"),
            target_compatible_with=_check_list_str("target_compatible_with"),
            exec_compatible_with=_check_list_str("exec_compatible_with"),
            cc_srcs_exclude=_check_list_str("cc_srcs_exclude"),
            test_data_exclude=_check_list_str("test_data_exclude"),
            extra_deps=_check_list_str("extra_deps"),
            extra_test_deps=_check_list_str("extra_test_deps"),
            patch_cmds=_check_list_str("patch_cmds"),
            patch_cmds_win=_check_list_str("patch_cmds_win"),
            file_copies=_check_dict_str("file_copies"),
        )

    def to_dict(self) -> Dict[str, Any]:
        res: Dict[str, Any] = {}
        if self.is_xs is not None:
            res["is_xs"] = self.is_xs
        if self.file_copies:
            res["file_copies"] = self.file_copies
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
        if self.defines_select:
            res["defines_select"] = self.defines_select
        if self.linkopts:
            res["linkopts"] = self.linkopts
        if self.linkopts_select:
            res["linkopts_select"] = self.linkopts_select
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
        if self.test_data_exclude:
            res["test_data_exclude"] = self.test_data_exclude
        if self.extra_deps:
            res["extra_deps"] = self.extra_deps
        if self.extra_test_deps:
            res["extra_test_deps"] = self.extra_test_deps
        if self.patch_cmds:
            res["patch_cmds"] = self.patch_cmds
        if self.patch_cmds_win:
            res["patch_cmds_win"] = self.patch_cmds_win
        return res
        if self.is_xs is not None:
            res["is_xs"] = self.is_xs
        if self.file_copies:
            res["file_copies"] = self.file_copies
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
        if self.defines_select:
            res["defines_select"] = self.defines_select
        if self.linkopts:
            res["linkopts"] = self.linkopts
        if self.linkopts_select:
            res["linkopts_select"] = self.linkopts_select
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
        if self.test_data_exclude:
            res["test_data_exclude"] = self.test_data_exclude
        if self.extra_deps:
            res["extra_deps"] = self.extra_deps
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
    deleted_files: List[str] = field(default_factory=list)
    defines: List[str] = field(default_factory=list)
    includes: List[str] = field(default_factory=list)
    native_deps: List[str] = field(default_factory=list)
    execution_requirements: Dict[str, str] = field(default_factory=dict)
    target_compatible_with: List[str] = field(default_factory=list)
    exec_compatible_with: List[str] = field(default_factory=list)
    overlay_files: Dict[str, bytes] = field(default_factory=dict)
    file_copies: List[Tuple[str, str]] = field(default_factory=list)
    output_loc: str = ""
    t_files: List[str] = field(default_factory=list)
    unreadable_files: List[str] = field(default_factory=list)

    def add_file_copy(self, src: str, dest: str) -> None:
        if src == dest:
            return
        for s, d in self.file_copies:
            if d == dest:
                return
        self.file_copies.append((src, dest))


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
            if any(p in ["t", "xt", "_xs", "blib", ".git", "examples", "example", "eg", "demo", "samples"] for p in parts):
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
        if generator_metadata and generator_metadata.is_xs is not None:
            inspection.is_xs = generator_metadata.is_xs
        elif is_xs_hint is not None:
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

            # Look for INCLUDE: <file>
            for line in content.splitlines():
                sline = line.strip()
                if sline.startswith("INCLUDE:"):
                    inc_target = sline.removeprefix("INCLUDE:").strip()
                    if inc_target.endswith(".xs"):
                        rel_dir = Path(xs).parent
                        resolved = (rel_dir / inc_target).as_posix() if rel_dir != Path(".") else inc_target
                        for candidate in (inc_target, resolved):
                            if candidate not in fragment_xs:
                                fragment_xs.append(candidate)

        # Inspect XS and C files for included .c files
        for src in xs_files + c_files:
            src_path = extract_dir / src
            content = self._safe_read_text(src_path)
            for line in content.splitlines():
                sline = line.strip()
                if sline.startswith("#") and "include" in sline:
                    c_includes = self._extract_c_includes(sline)
                    rel_dir = Path(src).parent
                    for c_inc in c_includes:
                        resolved = (rel_dir / c_inc).as_posix() if rel_dir != Path(".") else c_inc
                        chosen = None
                        if (extract_dir / resolved).exists():
                            chosen = resolved
                        elif (extract_dir / c_inc).exists():
                            chosen = c_inc
                        elif resolved in inspection.overlay_files:
                            chosen = resolved
                        elif c_inc in inspection.overlay_files:
                            chosen = c_inc

                        if chosen and chosen not in included_c_files:
                            included_c_files.append(chosen)

        # Included XS fragments must not be compiled as top-level XS units
        top_level_xs = [x for x in top_level_xs if x not in fragment_xs]
        inspection.top_level_xs = top_level_xs
        inspection.fragment_xs = fragment_xs
        inspection.included_c_files = included_c_files

        # 3. Dynamic constants: check fallback/ directory for headers/xs/inc/c files
        fallback_dir = extract_dir / "fallback"
        if fallback_dir.is_dir():
            for f in sorted(fallback_dir.glob("*")):
                if f.is_file() and f.suffix in (".h", ".xs", ".inc", ".c", ".xsi"):
                    inspection.add_file_copy(f"fallback/{f.name}", f.name)

        # 4. Synthesize Driver.xsi and DBI headers for DBD drivers
        if dist_name.startswith("DBD-") and dist_name != "DBD-Mock":
            driver_name = dist_name.removeprefix("DBD-")
            driver_xst = Path(__file__).resolve().parent.parent.parent / "resources" / "dbi" / "Driver.xst"
            if driver_xst.exists():
                xsi_content = driver_xst.read_text(encoding="utf-8").replace("~DRIVER~", driver_name)
                inspection.overlay_files[f"{driver_name}.xsi"] = xsi_content.encode("utf-8")
                for h_f in driver_xst.parent.glob("*.h"):
                    inspection.overlay_files[h_f.name] = h_f.read_bytes()

        # 5. Synthesize ppport.h if referenced and missing
        if not (extract_dir / "ppport.h").exists():
            needs_ppport = False
            for f in xs_files + c_files:
                p = extract_dir / f
                if p.is_file():
                    content = p.read_text(encoding="utf-8", errors="ignore")
                    if 'include "ppport.h"' in content or "include <ppport.h>" in content:
                        needs_ppport = True
                        break
            if not needs_ppport:
                for script in ["Makefile.PL", "Build.PL"]:
                    sp = extract_dir / script
                    if sp.is_file():
                        sc = sp.read_text(encoding="utf-8", errors="ignore")
                        if "use_ppport" in sc or "Devel::PPPort" in sc:
                            needs_ppport = True
                            break
            if needs_ppport:
                inspection.add_file_copy("@rules_cpan//cpan/resources/ppport:ppport.h", "ppport.h")

        # 6. Discover test files in t/
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
        self._inspect_build_scripts(extract_dir, inspection, generator_metadata=generator_metadata)

        # 7. Incorporate GeneratorMetadata customizations
        if generator_metadata:
            if generator_metadata.output_loc:
                inspection.output_loc = generator_metadata.output_loc
            if generator_metadata.defines:
                for d in generator_metadata.defines:
                    if d not in inspection.defines:
                        inspection.defines.append(d)
            if generator_metadata.native_deps:
                inspection.native_deps = list(generator_metadata.native_deps)
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
            if generator_metadata.file_copies:
                for src_c, dest_c in generator_metadata.file_copies.items():
                    inspection.add_file_copy(src_c, dest_c)
            if generator_metadata.defines or generator_metadata.output_loc or generator_metadata.includes:
                if len(xs_files) > 0 or len(c_files) > 0 or generator_metadata.output_loc:
                    inspection.is_xs = True

        unreadable_files: List[str] = []
        for p in extract_dir.rglob("*"):
            if p.is_file():
                try:
                    if (p.stat().st_mode & 0o444) == 0:
                        unreadable_files.append(p.relative_to(extract_dir).as_posix())
                except Exception:
                    pass
        inspection.unreadable_files = unreadable_files

        return inspection

    def _find_ppport_resource(self) -> Optional[Path]:
        """Locates generated or runfile ppport.h header."""
        # 1. Check relative to this source file
        p = Path(__file__).resolve().parent.parent.parent / "resources" / "ppport" / "ppport.h"
        if p.exists():
            return p
        # 2. Check Bazel runfiles environment variables
        for env_var in ("RUNFILES_DIR", "TEST_SRCDIR"):
            rf = os.environ.get(env_var)
            if rf:
                for cand in (
                    Path(rf) / "rules_cpan" / "cpan" / "resources" / "ppport" / "ppport.h",
                    Path(rf) / "_main" / "cpan" / "resources" / "ppport" / "ppport.h",
                    Path(rf) / "cpan" / "resources" / "ppport" / "ppport.h",
                ):
                    if cand.exists():
                        return cand
        # 3. Check bazel-bin in workspace directory
        workspace_dir = os.environ.get("BUILD_WORKSPACE_DIRECTORY")
        if workspace_dir:
            cand = Path(workspace_dir) / "bazel-bin" / "cpan" / "resources" / "ppport" / "ppport.h"
            if cand.exists():
                return cand
        for root in (Path.cwd(), Path(__file__).resolve().parents[3]):
            cand = root / "bazel-bin" / "cpan" / "resources" / "ppport" / "ppport.h"
            if cand.exists():
                return cand
        return None

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
        generator_metadata: Optional[GeneratorMetadata] = None,
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

        # Attempt build system dry-run if Makefile.PL exists using a scratch copy
        if makefile_pl.exists():
            with tempfile.TemporaryDirectory() as scratch_tmp:
                scratch_dir = Path(scratch_tmp) / "scratch"
                shutil.copytree(extract_dir, scratch_dir, symlinks=True)
                scratch_existing = {p.relative_to(scratch_dir).as_posix() for p in scratch_dir.rglob("*") if p.is_file()}

                existing_file_content_to_rel: Dict[bytes, str] = {}
                for p in scratch_dir.rglob("*"):
                    if p.is_file():
                        try:
                            c = p.read_bytes()
                            if c not in existing_file_content_to_rel:
                                existing_file_content_to_rel[c] = p.relative_to(scratch_dir).as_posix()
                        except Exception:
                            pass

                perl_bin = find_perl_binary()
                if not perl_bin:
                    raise RuntimeError("Hermetic perl binary not found in runfiles; host fallback is prohibited")
                env = dict(os.environ)
                env["PERL_MM_USE_DEFAULT"] = "1"
                env["AUTOMATED_TESTING"] = "1"
                env["NONINTERACTIVE_TESTING"] = "1"
                env["PATH"] = f"{perl_bin.parent}:{env.get('PATH', '')}"

                try:
                    subprocess.run(
                        [str(perl_bin), "Makefile.PL"],
                        cwd=str(scratch_dir),
                        capture_output=True,
                        stdin=subprocess.DEVNULL,
                        timeout=10,
                        env=env,
                    )
                except Exception:
                    pass

                new_files = {p for p in scratch_dir.rglob("*") if p.is_file() and p.relative_to(scratch_dir).as_posix() not in scratch_existing}
                all_cc_excludes = list(generator_metadata.cc_srcs_exclude) if generator_metadata and generator_metadata.cc_srcs_exclude else []
                all_cc_excludes.extend(["bzip2-src/**", "bzlib-src/**", "zlib-src/**"])

                for new_file in new_files:
                    rel = new_file.relative_to(scratch_dir).as_posix()
                    if rel.startswith(("blib", ".", "conf", "Makefile")):
                        continue

                    file_bytes = new_file.read_bytes()
                    if file_bytes in existing_file_content_to_rel:
                        orig_rel = existing_file_content_to_rel[file_bytes]
                        if any(fnmatch.fnmatch(orig_rel, pat) or fnmatch.fnmatch(rel, pat) for pat in all_cc_excludes):
                            continue
                        inspection.add_file_copy(orig_rel, rel)
                        if rel.endswith(".c") and rel not in inspection.included_c_files:
                            inspection.included_c_files.append(rel)
                        continue

                    # Check for generated xssubs.c or constants
                    if rel.endswith((".c", ".h", ".xs", ".inc")):
                        if any(fnmatch.fnmatch(rel, pat) for pat in all_cc_excludes):
                            continue
                        file_content = self._safe_read_text(new_file)
                        if "xssubs.c" in rel:
                            file_content = self.wrap_constants_in_ifdef(file_content)
                        if rel.endswith(".c"):
                            if rel not in inspection.included_c_files:
                                inspection.included_c_files.append(rel)
                        inspection.overlay_files[rel] = file_content.encode("utf-8")

                # Extract preprocessor defines and PM mappings from scratch Makefile
                makefile_file = scratch_dir / "Makefile"
                if makefile_file.exists():
                    mf_text = self._safe_read_text(makefile_file)
                    # 1. Parse defines from Makefile DEFINE line
                    define_match = re.search(r"^DEFINE\s*=\s*(.*)$", mf_text, re.MULTILINE)
                    if define_match:
                        for m in re.finditer(r"-D([A-Za-z0-9_]+)(?:=([^\s\'\"]+))?", define_match.group(1)):
                            name = m.group(1)
                            val = m.group(2)
                            if val is not None:
                                clean_val = re.sub(r'[\'\"\\/]+$', '', val).strip()
                                clean_def = f"{name}={clean_val}"
                            else:
                                clean_def = name
                            if clean_def and clean_def not in inspection.defines:
                                inspection.defines.append(clean_def)

                    # 2. Parse pm_to_blib mappings for root or non-standard .pm files
                    inst_libdir_match = re.search(r"^INST_LIBDIR\s*=\s*(.*)$", mf_text, re.MULTILINE)
                    inst_libdir_prefix = ""
                    if inst_libdir_match:
                        raw_libdir = inst_libdir_match.group(1).strip()
                        raw_libdir = raw_libdir.replace("$(INST_LIB)", "").strip("/\\ ")
                        inst_libdir_prefix = raw_libdir

                    pm_mappings = re.findall(
                        r"'([^'\s]+)'\s+'\$\((INST_LIB|INST_LIBDIR|INST_ARCHLIB)\)/([^'\s]+)'",
                        mf_text,
                    )
                    for src_rel, var_type, dest_sub in pm_mappings:
                        if var_type == "INST_LIBDIR" and inst_libdir_prefix:
                            dest_rel = f"{inst_libdir_prefix}/{dest_sub}".strip("/")
                        else:
                            dest_rel = dest_sub
                        if src_rel.endswith(".pm") and dest_rel.endswith(".pm"):
                            src_path = extract_dir / src_rel
                            dest_path = extract_dir / "lib" / dest_rel
                            if src_path.exists() and not dest_path.exists():
                                target_overlay_rel = f"lib/{dest_rel}"
                                inspection.add_file_copy(src_rel, target_overlay_rel)
                else:
                    # Fallback search for preprocessor defines from script_text when Makefile wasn't generated
                    for m in re.finditer(r"-D([A-Za-z0-9_]+)(?:=([^\s\'\"]+))?", script_text):
                        name = m.group(1)
                        val = m.group(2)
                        if val is not None:
                            if "$" in val or not re.match(r'^[A-Za-z0-9_."\'-]+$', val):
                                continue
                            clean_val = re.sub(r'[\'\"\\/]+$', '', val).strip()
                            clean_def = f"{name}={clean_val}"
                        else:
                            clean_def = name
                        if clean_def in ("XSH_MULTIPLICITY=0", "XSH_FORKSAFE=0", "SQLITE_MAX_LENGTH"):
                            continue
                        if clean_def and len(clean_def) > 1 and clean_def not in inspection.defines:
                            inspection.defines.append(clean_def)

        # Fallback check for root .pm matching Foo-Bar -> lib/Foo/Bar.pm
        dist_name = inspection.dist_name
        parts = dist_name.split("-")
        leaf_pm = f"{parts[-1]}.pm"
        leaf_path = extract_dir / leaf_pm
        dest_rel = "/".join(parts) + ".pm"
        dest_path = extract_dir / "lib" / dest_rel
        if leaf_path.exists() and not dest_path.exists():
            target_overlay_rel = f"lib/{dest_rel}"
            inspection.add_file_copy(leaf_pm, target_overlay_rel)

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
        valid_runtime_deps: List[str] = []
        raw_runtime = list(runtime_deps or [])
        if generator_metadata and generator_metadata.extra_deps:
            raw_runtime.extend(generator_metadata.extra_deps)

        for d in raw_runtime:
            if not d:
                continue
            if d.startswith(("@", ":")):
                label = d
                if label in (f":{dist}", f":{module_name}", f"@{module_name}"):
                    continue
            else:
                s_name = sanitize_module_name(d)
                if s_name == module_name:
                    continue
                label = f"@{s_name}"
            if label not in valid_runtime_deps:
                valid_runtime_deps.append(label)
        valid_runtime_deps.sort()

        all_test_deps = list(test_deps or [])
        if generator_metadata and generator_metadata.extra_test_deps:
            all_test_deps.extend(generator_metadata.extra_test_deps)

        valid_test_deps: List[str] = []
        for d in all_test_deps:
            if not d:
                continue
            if d.startswith(("@", ":")):
                label = d
                if label in (f":{dist}", f":{module_name}", f"@{module_name}"):
                    continue
            else:
                s_name = sanitize_module_name(d)
                if s_name == module_name:
                    continue
                label = f"@{s_name}"
            if label not in valid_test_deps:
                valid_test_deps.append(label)
        valid_test_deps.sort()

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

        srcs_patterns: List[str] = []
        data_patterns: List[str] = []
        data_excludes: List[str] = []
        for inc in perl_lib_includes:
            if inc in (".", ""):
                srcs_patterns.extend(['"*.pm"', '"*.pod"'])
                data_excludes.extend(['"*.pm"', '"*.pod"'])
            else:
                srcs_patterns.extend([f'"{inc}/**/*.pm"', f'"{inc}/**/*.pod"'])
                data_patterns.append(f'"{inc}/**/*"')
                data_excludes.extend([f'"{inc}/**/*.pm"', f'"{inc}/**/*.pod"'])
        if '"*.pm"' not in srcs_patterns:
            srcs_patterns.append('"*.pm"')

        srcs_patterns_str = "\n        " + ",\n        ".join(srcs_patterns) + ",\n    "
        data_patterns_str = "\n        " + ",\n        ".join(data_patterns) + ",\n    "
        data_excludes_str = "\n        " + ",\n        ".join(data_excludes) + ",\n    "

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
                tests_str = "\n        " + ",\n        ".join(non_manual_tests) + ",\n    "
                suite_tags = ""
            else:
                tests_str = ""
                suite_tags = '\n    tags = ["manual"],'

            test_deps_items = [f'"{d}"' for d in valid_test_deps]
            test_deps_str = (",\n        " + ",\n        ".join(test_deps_items)) if test_deps_items else ""

            test_data_excludes = [
                '"t/**/*.pm"',
                '"t/*.pm"',
            ]
            for uf in sorted(inspection.unreadable_files):
                if uf.startswith("t/"):
                    test_data_excludes.append(f'"{uf}"')
            if generator_metadata and generator_metadata.test_data_exclude:
                for exc in generator_metadata.test_data_exclude:
                    q = f'"{exc}"'
                    if q not in test_data_excludes:
                        test_data_excludes.append(q)
            test_data_excludes_str = ",\n            ".join(test_data_excludes)

            test_content = f"""
perl_library(
    name = "{dist}_test_lib",
    srcs = glob(["t/**/*.pm", "t/*.pm"], allow_empty = True),
    data = glob(
        ["t/**/*"],
        exclude = [
            {test_data_excludes_str},
        ],
        allow_empty = True,
    ),
    includes = ["t", "t/lib"],
    deps = [":{dist}"{test_deps_str}],
)

""" + "\n\n".join(test_target_blocks) + f"""

test_suite(
    name = "test",{suite_tags}
    tests = [{tests_str}],
)
"""
        else:
            test_content = f"""
test_suite(
    name = "test",
    tags = ["manual"],
    tests = [],
)
"""

        copy_file_rules: List[str] = []
        extra_perl_srcs: List[str] = []
        extra_cc_srcs: List[str] = []
        extra_textual_copies: List[str] = []

        if inspection.file_copies:
            for src_path, dest_path in sorted(inspection.file_copies, key=lambda x: (x[1], x[0])):
                rule_name = "copy_" + re.sub(r'[^a-zA-Z0-9_]', '_', dest_path)
                src_val = f'"{src_path}"'
                copy_file_rules.append(f"""copy_file(
    name = "{rule_name}",
    src = {src_val},
    out = "{dest_path}",
)""")
                if dest_path.endswith((".pm", ".pod")):
                    extra_perl_srcs.append(f'":{rule_name}"')
                elif dest_path.endswith(".c"):
                    if dest_path in inspection.included_c_files:
                        extra_textual_copies.append(f'":{rule_name}"')
                    else:
                        extra_cc_srcs.append(f'":{rule_name}"')
                elif dest_path.endswith((".h", ".inc", ".xsi", ".xs")):
                    extra_textual_copies.append(f'":{rule_name}"')

        load_copy_file = 'load("@bazel_lib//lib:copy_file.bzl", "copy_file")\n' if copy_file_rules else ""
        copy_file_block = "\n".join(copy_file_rules) + "\n\n" if copy_file_rules else ""

        srcs_pattern_parts = [f'glob([{srcs_patterns_str}], allow_empty = True)']
        if extra_perl_srcs:
            srcs_expr = "[\n        " + ",\n        ".join(extra_perl_srcs) + ",\n    ] + " + srcs_pattern_parts[0]
        else:
            srcs_expr = srcs_pattern_parts[0]

        if not inspection.is_xs:
            return f"""# Auto-generated by rules_cpan for {dist}
{load_copy_file}load("@rules_perl//perl:defs.bzl", "perl_library"{load_perl_test})

package(default_visibility = ["//visibility:public"])

{copy_file_block}perl_library(
    name = "{dist}",
    srcs = {srcs_expr},
    data = glob([{data_patterns_str}], exclude = [{data_excludes_str}], allow_empty = True),
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
        seen_native_deps: Set[str] = set()
        all_native_deps: List[str] = []
        raw_native_deps = (
            list(generator_metadata.native_deps)
            if generator_metadata and generator_metadata.native_deps
            else list(inspection.native_deps)
        )
        for d in raw_native_deps:
            d = d.strip()
            canon = f"{d}//:{d.lstrip('@')}" if d.startswith("@") and "//" not in d and ":" not in d else d
            if canon not in seen_native_deps and d not in seen_native_deps:
                seen_native_deps.add(canon)
                seen_native_deps.add(d)
                all_native_deps.append(d)
        native_deps_items = [f'"{d}"' for d in all_native_deps]
        native_deps_str = ""
        if native_deps_items:
            native_deps_str = "\n        " + ",\n        ".join(native_deps_items) + ",\n    "

        if inspection.top_level_xs:
            xs_srcs = [f'"{x}"' for x in inspection.top_level_xs]
            xs_srcs_str = f"[{', '.join(xs_srcs)}]"
        else:
            xs_srcs_str = 'glob(["*.xs"], allow_empty = True)'

        cc_excludes = [
            '"_xs/**"',
            '"t/**"',
            '"xt/**"',
            '"fallback/**"',
            '"conf/**"',
            '"examples/**"',
            '"example/**"',
            '"eg/**"',
            '"samples/**"',
            '"demo/**"',
            '"**/examples/**"',
            '"**/example/**"',
            '"**/eg/**"',
            '"**/samples/**"',
            '"**/demo/**"',
            '"**/contrib/**"',
            '"**/programs/**"',
            '"**/tests/**"',
        ]
        if generator_metadata and generator_metadata.cc_srcs_exclude:
            for exc in generator_metadata.cc_srcs_exclude:
                quoted = f'"{exc}"'
                if quoted not in cc_excludes:
                    cc_excludes.append(quoted)
        for inc_c in sorted(inspection.included_c_files):
            quoted = f'"{inc_c}"'
            if quoted not in cc_excludes:
                cc_excludes.append(quoted)
        for d_f in sorted(inspection.deleted_files):
            quoted = f'"{d_f}"'
            if quoted not in cc_excludes:
                cc_excludes.append(quoted)
        cc_excludes_str = "\n        " + ",\n        ".join(cc_excludes) + ",\n    "

        if generator_metadata and generator_metadata.defines_select:
            defines_lines = ["\n    defines = select({"]
            for cond, defs in sorted(generator_metadata.defines_select.items()):
                defs_items = [f'"{d}"' for d in defs]
                inner = ", ".join(defs_items)
                defines_lines.append(f'        "{cond}": [{inner}],')
            defines_lines.append("    }),")
            defines_block = "\n".join(defines_lines)
        else:
            if generator_metadata and generator_metadata.defines:
                all_defines = list(generator_metadata.defines)
            else:
                all_defines = [
                    d for d in inspection.defines
                    if "$" not in d and " " not in d and not d.endswith("=") and not d.startswith("/") and len(d) > 1
                ]
            defines_items = [f'"{d}"' for d in all_defines]
            defines_block = ""
            if defines_items:
                defines_block = "\n    defines = [\n        " + ",\n        ".join(defines_items) + ",\n    ],"

        linkopts_block = ""
        if generator_metadata and generator_metadata.linkopts_select:
            l_lines = ["\n    linkopts = select({"]
            for cond, lopts in sorted(generator_metadata.linkopts_select.items()):
                l_items = [f'"{o}"' for o in lopts]
                inner = ", ".join(l_items)
                l_lines.append(f'        "{cond}": [{inner}],')
            l_lines.append("    }),")
            linkopts_block = "\n".join(l_lines)
        elif generator_metadata and generator_metadata.linkopts:
            l_items = [f'"{o}"' for o in generator_metadata.linkopts]
            linkopts_block = "\n    linkopts = [" + ", ".join(l_items) + "],"

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

        extra_textual = [
            f'"{inc_c}"'
            for inc_c in sorted(inspection.included_c_files)
            if inc_c.endswith(".c")
        ]
        extra_textual.extend(sorted(extra_textual_copies))
        # Deduplicate
        seen_extra: set[str] = set()
        dedup_extra: List[str] = []
        for x in extra_textual:
            if x not in seen_extra:
                seen_extra.add(x)
                dedup_extra.append(x)
        if dedup_extra:
            prefix = "[\n        " + ",\n        ".join(dedup_extra) + ",\n    ] + "
        else:
            prefix = ""
        textual_hdrs_str = prefix + f"""glob([
        "*.h",
        "**/*.h",
        "*.xs",
        "**/*.xs",
        "*.xsi",
        "**/*.xsi",
        "*.inc",
        "**/*.inc",
    ], exclude = [{cc_excludes_str}], allow_empty = True)"""

        cc_srcs_pattern = f"""glob([
        "*.c",
        "**/*.c",
    ], exclude = [{cc_excludes_str}], allow_empty = True)"""
        if extra_cc_srcs:
            cc_srcs_expr = "[\n        " + ",\n        ".join(extra_cc_srcs) + ",\n    ] + " + cc_srcs_pattern
        else:
            cc_srcs_expr = cc_srcs_pattern

        return f"""# Auto-generated by rules_cpan for {dist} (XS extension)
load("@rules_cpan//cpan:defs.bzl", "cpan_xs")
{load_copy_file}load("@rules_perl//perl:defs.bzl", "perl_library"{load_perl_test})

package(default_visibility = ["//visibility:public"])

{copy_file_block}cpan_xs(
    name = "{dist}_xs",
    srcs = {xs_srcs_str},
    cc_srcs = {cc_srcs_expr},{defines_block}{linkopts_block}{xs_includes_str}{xs_exec_reqs_str}{target_compat_str}{exec_compat_str}
    output_loc = "{output_loc}",
    textual_hdrs = {textual_hdrs_str},
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
    srcs = {srcs_expr},
    data = [
        ":{dist}_xs",
    ] + glob([{data_patterns_str}], exclude = [{data_excludes_str}], allow_empty = True),
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
            dep_dir = m_dir / dep_name
            meta_path = dep_dir / "metadata.json"
            if meta_path.exists():
                try:
                    data = json.loads(meta_path.read_text(encoding="utf-8"))
                    versions = data.get("versions", [])
                    if versions:
                        return versions[-1]
                except Exception:
                    pass
            if dep_dir.exists():
                cpan_vers = sorted(
                    [p.name for p in dep_dir.iterdir() if p.is_dir() and ".cpan" in p.name],
                    key=lambda v: [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", v)],
                )
                if cpan_vers:
                    return cpan_vers[-1]

        return "0.0.0"

    def generate_module_bazel(
        self,
        module_name: str,
        version: str,
        native_deps: Optional[List[str]] = None,
        cpan_deps: Optional[List[Tuple[str, str]]] = None,
        test_deps: Optional[List[str]] = None,
        modules_dir: Optional[Path] = None,
        needs_bazel_lib: bool = False,
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
        if needs_bazel_lib and "bazel_lib" not in seen_deps:
            seen_deps.add("bazel_lib")
            lines.append('bazel_dep(name = "bazel_lib", version = "3.8.0")')

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

        if test_deps:
            for td in sorted(test_deps):
                if not td:
                    continue
                dep_raw = td.lstrip("@").split("//")[0].split(":")[0]
                dep_mod = sanitize_module_name(dep_raw)
                if dep_mod != module_name and dep_mod not in seen_deps:
                    seen_deps.add(dep_mod)
                    dep_ver = self._resolve_dep_version(dep_mod, cpan_deps, modules_dir)
                    lines.append(f'bazel_dep(name = "{dep_mod}", version = "{dep_ver}")')

        return "\n".join(lines) + "\n"
