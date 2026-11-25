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
    native_deps: List[str] = field(default_factory=list)
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
                elif f == "typemap" or f.endswith(".typemap"):
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

        # 4. Discover test files in t/
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

        # 5. Inspect Makefile.PL and Build.PL for native libs, defines, and run build simulation
        self._inspect_build_scripts(extract_dir, inspection)

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
        define_matches = re.findall(r"-D([A-Za-z0-9_]+(?:=[^\s\'\"]+)?)", script_text)
        for define in define_matches:
            if define not in inspection.defines:
                inspection.defines.append(define)

        # Attempt build system dry-run if Makefile.PL exists
        if not makefile_pl.exists():
            return

        existing_files = {p for p in extract_dir.rglob("*") if p.is_file()}
        try:
            subprocess.run(
                ["perl", "Makefile.PL"],
                cwd=str(extract_dir),
                capture_output=True,
                timeout=10,
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
    ) -> str:
        """Generates BUILD.bazel content for overlay/BUILD.bazel."""
        dist = inspection.dist_name
        runtime_deps = runtime_deps or []
        test_deps = test_deps or []

        cpan_deps_str = ""
        if runtime_deps:
            items = [f'"{d}"' for d in runtime_deps]
            cpan_deps_str = "\n        " + ",\n        ".join(items) + ",\n    "

        # Build test rules if t/ directory has test files
        test_content = ""
        load_perl_test = ', "perl_test"' if inspection.t_files else ""
        if inspection.t_files:
            test_target_names: List[str] = []
            test_target_blocks: List[str] = []

            for rel_path in inspection.t_files:
                clean_name = rel_path.replace("/", "_")
                if clean_name.endswith(".t"):
                    clean_name = clean_name[:-2]
                sanitized = re.sub(r"[^a-zA-Z0-9_.-]+", "_", clean_name)
                target_name = f"test_{sanitized}"
                test_target_names.append(f'":{target_name}"')

                test_target_blocks.append(f"""perl_test(
    name = "{target_name}",
    size = "small",
    srcs = ["{test_runner_label}"],
    args = ["{rel_path}"],
    deps = [":{dist}_test_lib"],
)""")

            tests_str = ",\n        ".join(test_target_names)
            test_deps_items = [f'"{d}"' for d in test_deps]
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
    name = "test",
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
    includes = [
        "lib",
    ],
    deps = [{cpan_deps_str}],
)

alias(
    name = "{module_name}",
    actual = ":{dist}",
)
{test_content}"""

        # XS extension BUILD.bazel
        output_loc = inspection.output_loc
        native_deps_items = [f'"{d}"' for d in inspection.native_deps]
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
        for inc_c in inspection.included_c_files:
            quoted = f'"{inc_c}"'
            if quoted not in cc_excludes:
                cc_excludes.append(quoted)
        cc_excludes_str = "\n        " + ",\n        ".join(cc_excludes) + ",\n    "

        defines_items = [f'"{d}"' for d in inspection.defines]
        defines_str = ""
        if defines_items:
            defines_str = "\n        " + ",\n        ".join(defines_items) + ",\n    "

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
    defines = [{defines_str}],
    output_loc = "{output_loc}",
    textual_hdrs = glob([
        "*.h",
        "**/*.h",
        "*.xs",
        "**/*.xs",
        "*.inc",
        "**/*.inc",
    ], allow_empty = True),
    typemaps = glob([
        "typemap",
        "**/typemap",
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
    includes = [
        "lib",
    ],
    deps = [{cpan_deps_str}],
)

alias(
    name = "{module_name}",
    actual = ":{dist}",
)
{test_content}"""

    def generate_module_bazel(
        self,
        module_name: str,
        version: str,
        native_deps: Optional[List[str]] = None,
        cpan_deps: Optional[List[Tuple[str, str]]] = None,
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

        if native_deps:
            for nat_target in native_deps:
                dep_name = nat_target.lstrip("@").split("//")[0]
                dep_info = NATIVE_DEP_MAP.get(dep_name)
                if dep_info:
                    lines.append(f'bazel_dep(name = "{dep_info["bazel_dep"]}", version = "{dep_info["version"]}")')

        if cpan_deps:
            for cpan_mod, cpan_ver in cpan_deps:
                lines.append(f'bazel_dep(name = "{cpan_mod}", version = "{cpan_ver}")')

        return "\n".join(lines) + "\n"
