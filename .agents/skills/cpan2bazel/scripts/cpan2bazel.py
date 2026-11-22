#!/usr/bin/env python3
"""cpan2bazel: Port CPAN distributions to hermetic Bazel BCR modules."""

import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from typing import Dict, List, Optional, Tuple


def compute_sri_hash(data: bytes) -> str:
    """Computes Subresource Integrity (SRI) sha256 hash string."""
    digest = hashlib.sha256(data).digest()
    return f"sha256-{base64.b64encode(digest).decode('ascii')}"


def sanitize_module_name(cpan_name: str) -> str:
    """Computes BCR module name: perl-<lowercase_with_hyphens>."""
    clean = re.sub(r"[^a-zA-Z0-9._-]+", "-", cpan_name.lower())
    clean = clean.replace("_", "-")
    return f"perl-{clean}"


def compute_output_loc(dist_name: str, provides: List[str]) -> str:
    """Computes DynaLoader/XSLoader auto/ directory location for an XS module."""
    canonical_mod = dist_name.replace("-", "::")
    primary_mod = canonical_mod
    if provides:
        if canonical_mod in provides:
            primary_mod = canonical_mod
        else:
            primary_mod = provides[0]

    parts = primary_mod.split("::")
    path_prefix = "/".join(parts)
    leaf = parts[-1]
    return f"auto/{path_prefix}/{leaf}"


def fetch_metacpan_metadata(distribution: str, version: Optional[str] = None) -> dict:
    """Fetches distribution release metadata from MetaCPAN API."""
    url = f"https://fastapi.metacpan.org/v1/release/{distribution}"
    req = urllib.request.Request(url, headers={"User-Agent": "rules_cpan/cpan2bazel"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data


def create_patch(content: str, filename: str = "BUILD.bazel") -> str:
    """Creates a unified diff patch adding a new file."""
    lines = content.splitlines()
    num_lines = len(lines)
    header = [
        f"--- /dev/null",
        f"+++ b/{filename}",
        f"@@ -0,0 +1,{num_lines} @@",
    ]
    diff_lines = [f"+{l}" for l in lines]
    return "\n".join(header + diff_lines) + "\n"


class CPANPorter:
    """Analyzes CPAN distributions and packages them into BCR registry."""

    def __init__(
        self,
        distribution: str,
        version: Optional[str] = None,
        archive_path: Optional[str] = None,
        registry_dir: str = "bazel/3rdparty",
        native_deps: Optional[List[str]] = None,
        defines: Optional[List[str]] = None,
    ):
        self.distribution = distribution
        self.version = version
        self.archive_path = archive_path
        self.registry_dir = registry_dir
        self.native_deps = native_deps or []
        self.defines = defines or []
        self.download_url = ""
        self.archive_bytes = b""
        self.provides: List[str] = []
        self.is_xs = False
        self.has_fallback_constants = False

    def prepare_archive(self):
        if self.archive_path and os.path.exists(self.archive_path):
            with open(self.archive_path, "rb") as f:
                self.archive_bytes = f.read()
            if not self.version:
                m = re.search(r"[-_]([0-9]+(?:\.[0-9]+)*)", os.path.basename(self.archive_path))
                self.version = m.group(1) if m else "1.0.0"
        else:
            meta = fetch_metacpan_metadata(self.distribution, self.version)
            self.download_url = meta.get("download_url", "")
            if not self.version:
                self.version = str(meta.get("version", "1.0.0")).lstrip("v")
            self.provides = [p.get("name", "") for p in meta.get("provides", []) if isinstance(p, dict)]
            if not self.provides and "name" in meta:
                self.provides = [self.distribution.replace("-", "::")]

            # Download archive
            req = urllib.request.Request(self.download_url, headers={"User-Agent": "rules_cpan/cpan2bazel"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                self.archive_bytes = resp.read()

    def analyze_contents(self, extract_dir: str):
        existing_files = set()
        for root, _, files in os.walk(extract_dir):
            for f in files:
                existing_files.add(os.path.join(root, f))

        makefile_pl = os.path.join(extract_dir, "Makefile.PL")
        generated_files = {}
        if os.path.exists(makefile_pl):
            try:
                subprocess.run(["perl", "Makefile.PL"], cwd=extract_dir, capture_output=True, timeout=15)
                for root, _, files in os.walk(extract_dir):
                    for f in files:
                        p = os.path.join(root, f)
                        if p not in existing_files:
                            rel = os.path.relpath(p, extract_dir)
                            if not rel.startswith("blib") and not rel.startswith(".") and not rel.startswith("conf"):
                                if rel.endswith((".c", ".h", ".xs", ".inc")):
                                    with open(p, "r", errors="ignore") as fp:
                                        generated_files[rel] = fp.read()
            except Exception as e:
                pass

        self.generated_files = generated_files

        if "xssubs.c" in generated_files:
            m = re.search(r'sv_setpv\(config,\s*"([^"]+)"\)', generated_files["xssubs.c"])
            if m:
                for token in m.group(1).split():
                    if token.startswith("-D"):
                        define_val = token[2:]
                        if define_val != "HAVE_STRLCPY" and define_val not in self.defines:
                            self.defines.append(define_val)
            # Wrap constant symbols in #ifdef for platform portability
            content = generated_files["xssubs.c"]
            wrapped = re.sub(
                r'newCONSTSUB\(stash,\s*"([A-Za-z0-9_]+)",\s*newSViv\(\1\)\);',
                r'#ifdef \1\nnewCONSTSUB(stash, "\1", newSViv(\1));\n#else\nnewCONSTSUB(stash, "\1", newSV(0));\n#endif',
                content,
            )
            generated_files["xssubs.c"] = wrapped

        xs_files = []
        c_files = []
        h_files = []
        top_level_xs = []
        fragment_xs = []

        for root, _, files in os.walk(extract_dir):
            rel_dir = os.path.relpath(root, extract_dir)
            if rel_dir.startswith("t") or "fallback" in rel_dir or "_xs" in rel_dir or rel_dir.startswith("blib"):
                continue
            for f in files:
                rel_file = os.path.join(rel_dir, f).lstrip("./")
                if f.endswith(".xs"):
                    xs_files.append(rel_file)
                    full_p = os.path.join(root, f)
                    with open(full_p, "r", errors="ignore") as fp:
                        content = fp.read()
                    if re.search(r"^\s*MODULE\s*=", content, re.MULTILINE):
                        top_level_xs.append(rel_file)
                    else:
                        fragment_xs.append(rel_file)
                elif f.endswith(".c"):
                    c_files.append(rel_file)
                elif f.endswith(".h"):
                    h_files.append(rel_file)

        self.is_xs = len(xs_files) > 0
        self.top_level_xs = top_level_xs
        self.fragment_xs = fragment_xs
        fallback_h = os.path.join(extract_dir, "fallback", "constants.h")
        fallback_xs = os.path.join(extract_dir, "fallback", "constants.xs")
        if os.path.exists(fallback_h) or os.path.exists(fallback_xs):
            self.has_fallback_constants = True

    def generate_build_content(self) -> str:
        dist = self.distribution
        if not self.is_xs:
            # Pure Perl
            return f"""# Auto-generated by cpan2bazel for {dist}
load("@rules_perl//perl:defs.bzl", "perl_library")

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
        ".",
        "lib",
    ],
)
"""
        else:
            # XS extension
            output_loc = compute_output_loc(dist, self.provides)
            defines_list = list(self.defines)
            if dist == "Compress-Raw-Zlib":
                if not defines_list:
                    defines_list = ["NO_VIZ", "USE_PPPORT_H", "Perl_crz_BUILD_ZLIB=0", "GZIP_OS_CODE=3"]
                if not self.native_deps:
                    self.native_deps = ["@zlib"]

            defines_str = ""
            if defines_list:
                defines_str = "\n        " + ",\n        ".join(f'"{d}"' for d in defines_list) + ",\n    "

            osx_defines = list(defines_list)
            if dist == "IO-Tty":
                osx_defines = [d for d in osx_defines if d not in ["HAVE_PTY_H", "HAVE_GETPT", "HAVE_STRLCPY"]]
                if "HAVE_UTIL_H" not in osx_defines:
                    osx_defines.append("HAVE_UTIL_H")
            if "OSX_COMPAT" not in osx_defines:
                osx_defines.append("OSX_COMPAT")
            osx_defines_str = "\n        " + ",\n        ".join(f'"{d}"' for d in osx_defines) + ",\n    " if osx_defines else ""

            deps_str = ""
            if self.native_deps:
                deps_str = "\n        " + ",\n        ".join(f'"{d}"' for d in self.native_deps) + ",\n    "

            xs_srcs_items = [f'"{x}"' for x in self.top_level_xs] if getattr(self, "top_level_xs", []) else ['"*.xs"']
            xs_srcs_str = ", ".join(xs_srcs_items)

            cc_excludes = ["_xs/**", "t/**", "fallback/**", "conf/**", "xssubs.c"]
            if "@zlib" in self.native_deps or dist == "Compress-Raw-Zlib":
                cc_excludes.append("zlib-src/**")
            cc_exclude_str = "\n        " + ",\n        ".join(f'"{e}"' for e in cc_excludes) + ",\n    "

            extra_linkopts = ""
            if dist == "IO-Tty":
                extra_linkopts = """
    linkopts = select({
        "@platforms//os:linux": ["-lutil"],
        "//conditions:default": [],
    }),"""

            return f"""# Auto-generated by cpan2bazel for {dist} (XS extension)
load("@rules_cpan//cpan:defs.bzl", "cpan_xs")
load("@rules_perl//perl:defs.bzl", "perl_library")

package(default_visibility = ["//visibility:public"])

cpan_xs(
    name = "{dist}_xs",
    srcs = [{xs_srcs_str}],
    cc_srcs = glob([
        "*.c",
        "**/*.c",
    ], exclude = [{cc_exclude_str}], allow_empty = True),
    defines = select({{
        "@platforms//os:osx": [{osx_defines_str}],
        "//conditions:default": [{defines_str}],
    }}),{extra_linkopts}
    output_loc = "{output_loc}",
    textual_hdrs = glob([
        "*.h",
        "**/*.h",
        "*.xs",
        "**/*.xs",
        "*.inc",
        "**/*.inc",
        "xssubs.c",
    ], allow_empty = True),
    typemaps = glob([
        "typemap",
        "**/typemap",
    ], allow_empty = True),
    deps = [{deps_str}],
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
        ".",
        "lib",
    ],
)
"""

    def generate_bcr_module(self):
        self.prepare_archive()

        with tempfile.TemporaryDirectory() as tmpdir:
            archive_file = os.path.join(tmpdir, "archive.tar.gz")
            with open(archive_file, "wb") as f:
                f.write(self.archive_bytes)

            extract_dir = os.path.join(tmpdir, "extract")
            os.makedirs(extract_dir, exist_ok=True)
            with tarfile.open(archive_file, "r:*") as tar:
                tar.extractall(extract_dir)

            # Strip prefix directory if present
            entries = os.listdir(extract_dir)
            top_dir = os.path.join(extract_dir, entries[0]) if len(entries) == 1 and os.path.isdir(os.path.join(extract_dir, entries[0])) else extract_dir
            strip_prefix = entries[0] if len(entries) == 1 and os.path.isdir(os.path.join(extract_dir, entries[0])) else ""

            self.analyze_contents(top_dir)

            build_content = self.generate_build_content()
            patch_content = create_patch(build_content, "BUILD.bazel")

            for rel_path, file_content in getattr(self, "generated_files", {}).items():
                patch_content += "\n" + create_patch(file_content, rel_path)

            if self.has_fallback_constants:
                fallback_h_path = os.path.join(top_dir, "fallback", "constants.h")
                fallback_xs_path = os.path.join(top_dir, "fallback", "constants.xs")
                if os.path.exists(fallback_h_path):
                    with open(fallback_h_path, "r", errors="ignore") as f:
                        patch_content += "\n" + create_patch(f.read(), "constants.h")
                if os.path.exists(fallback_xs_path):
                    with open(fallback_xs_path, "r", errors="ignore") as f:
                        patch_content += "\n" + create_patch(f.read(), "constants.xs")

            patch_bytes = patch_content.encode("utf-8")

            module_name = sanitize_module_name(self.distribution)
            module_dir = os.path.join(self.registry_dir, "modules", module_name)
            version_dir = os.path.join(module_dir, self.version)
            patches_dir = os.path.join(version_dir, "patches")
            os.makedirs(patches_dir, exist_ok=True)

            # 1. metadata.json
            meta_path = os.path.join(module_dir, "metadata.json")
            if os.path.exists(meta_path):
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta_data = json.load(f)
                if self.version not in meta_data.get("versions", []):
                    meta_data["versions"].append(self.version)
            else:
                meta_data = {
                    "homepage": f"https://metacpan.org/dist/{self.distribution}",
                    "maintainers": [
                        {
                            "name": "rules_cpan maintainers",
                            "github": "manuelnaranjo",
                        }
                    ],
                    "versions": [self.version],
                    "yanked_versions": {},
                }
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(meta_data, f, indent=4)
                f.write("\n")

            # 2. MODULE.bazel
            bcr_module_bazel = f'''module(
    name = "{module_name}",
    version = "{self.version}",
)

bazel_dep(name = "rules_cpan", version = "0.0.0")
bazel_dep(name = "rules_perl", version = "2.1.0")
bazel_dep(name = "rules_cc", version = "0.2.28")
bazel_dep(name = "platforms", version = "1.1.0")
'''
            for dep in self.native_deps:
                dep_name = dep.lstrip("@").split("//")[0]
                if dep_name == "zlib":
                    bcr_module_bazel += 'bazel_dep(name = "zlib", version = "1.3.1.bcr.5")\n'
                elif dep_name == "libyaml":
                    bcr_module_bazel += 'bazel_dep(name = "libyaml", version = "0.2.5")\n'

            with open(os.path.join(version_dir, "MODULE.bazel"), "w", encoding="utf-8") as f:
                f.write(bcr_module_bazel)

            # 3. patches/add_build_file.patch
            patch_file_name = "add_build_file.patch"
            with open(os.path.join(patches_dir, patch_file_name), "wb") as f:
                f.write(patch_bytes)

            # 4. source.json
            archive_sri = compute_sri_hash(self.archive_bytes)
            patch_sri = compute_sri_hash(patch_bytes)

            source_data = {
                "url": self.download_url,
                "integrity": archive_sri,
                "strip_prefix": strip_prefix,
                "patch_strip": 1,
                "patches": {
                    patch_file_name: patch_sri,
                },
            }
            with open(os.path.join(version_dir, "source.json"), "w", encoding="utf-8") as f:
                json.dump(source_data, f, indent=4)
                f.write("\n")

            print(f"[cpan2bazel] Successfully ported {self.distribution} {self.version} -> {module_name} in {module_dir}")


def main():
    parser = argparse.ArgumentParser(description="Port CPAN distributions to Bazel BCR modules.")
    parser.add_argument("-d", "--distribution", required=True, help="CPAN distribution name (e.g. Compress-Raw-Zlib)")
    parser.add_argument("-v", "--version", help="CPAN distribution version")
    parser.add_argument("-a", "--archive", help="Path to local distribution tarball")
    parser.add_argument("-r", "--registry", default="bazel/3rdparty", help="Target BCR registry path")
    parser.add_argument("--native-dep", action="append", default=[], help="Native C library dependency (e.g. @zlib)")
    parser.add_argument("--define", action="append", default=[], help="Extra preprocessor defines")

    args = parser.parse_args()

    porter = CPANPorter(
        distribution=args.distribution,
        version=args.version,
        archive_path=args.archive,
        registry_dir=args.registry,
        native_deps=args.native_dep,
        defines=args.define,
    )
    porter.generate_bcr_module()


if __name__ == "__main__":
    main()
