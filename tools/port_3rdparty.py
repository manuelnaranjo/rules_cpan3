#!/usr/bin/env python3
"""Automation tool for local BCR 3rdparty registry and any2bazel porting workflow.

This tool automates creating, modeling, patching, and verifying 3rdparty native
C/C++ dependencies in the local BCR registry at `bazel/3rdparty` for consumption
by Perl CPAN distributions.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional


def compute_sri_hash(data: bytes) -> str:
    """Compute Subresource Integrity (SRI) sha256 hash formatted as sha256-<base64>."""
    h = hashlib.sha256(data).digest()
    return f"sha256-{base64.b64encode(h).decode('utf-8')}"


def get_workspace_root() -> Path:
    """Find the root of the Bazel workspace."""
    # First check BUILD_WORKSPACE_DIRECTORY if run via 'bazel run'
    ws_env = os.environ.get("BUILD_WORKSPACE_DIRECTORY")
    if ws_env:
        return Path(ws_env)

    # Search upwards from current directory or script directory
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        if (parent / "MODULE.bazel").exists() or (parent / "WORKSPACE").exists():
            return parent
    return Path(__file__).resolve().parent.parent


def get_registry_root(workspace: Path) -> Path:
    return workspace / "bazel" / "3rdparty"


def ensure_registry_scaffolding(registry_root: Path) -> None:
    """Ensure bazel_registry.json and modules/ exist in local BCR registry."""
    registry_root.mkdir(parents=True, exist_ok=True)
    reg_json = registry_root / "bazel_registry.json"
    if not reg_json.exists():
        with open(reg_json, "w", encoding="utf-8") as f:
            json.dump({"module_base_path": "modules", "mirrors": []}, f, indent=2)
            f.write("\n")

    modules_dir = registry_root / "modules"
    modules_dir.mkdir(parents=True, exist_ok=True)


def cmd_init(args: argparse.Namespace) -> None:
    workspace = get_workspace_root()
    registry_root = get_registry_root(workspace)
    ensure_registry_scaffolding(registry_root)

    module_name = args.name
    version = args.version
    url = args.url
    strip_prefix = args.strip_prefix or f"{module_name}-{version}"

    module_dir = registry_root / "modules" / module_name
    version_dir = module_dir / version
    patches_dir = version_dir / "patches"
    patches_dir.mkdir(parents=True, exist_ok=True)

    # Download tarball to compute SRI hash
    print(f"Downloading source archive from {url}...")
    req = urllib.request.Request(url, headers={"User-Agent": "rules_cpan3-port-tool/1.0"})
    with urllib.request.urlopen(req) as resp:
        tarball_bytes = resp.read()
    archive_hash = compute_sri_hash(tarball_bytes)
    print(f"Calculated integrity: {archive_hash}")

    # 1. metadata.json
    metadata_file = module_dir / "metadata.json"
    if metadata_file.exists():
        with open(metadata_file, "r", encoding="utf-8") as f:
            meta = json.load(f)
        if version not in meta.get("versions", []):
            meta.setdefault("versions", []).append(version)
    else:
        meta = {
            "homepage": args.homepage or f"https://github.com/{module_name}",
            "maintainers": [
                {
                    "name": "rules_cpan maintainers",
                    "github": "manuelnaranjo",
                }
            ],
            "versions": [version],
            "yanked_versions": {},
        }
    with open(metadata_file, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
        f.write("\n")

    # 2. MODULE.bazel
    mod_bazel = version_dir / "MODULE.bazel"
    if not mod_bazel.exists():
        content = (
            f'module(\n'
            f'    name = "{module_name}",\n'
            f'    version = "{version}",\n'
            f'    compatibility_level = 1,\n'
            f')\n\n'
            f'bazel_dep(name = "platforms", version = "1.1.0")\n'
            f'bazel_dep(name = "rules_cc", version = "0.2.28")\n'
        )
        mod_bazel.write_text(content, encoding="utf-8")

    # 3. source.json
    source_json = version_dir / "source.json"
    source_data = {
        "integrity": archive_hash,
        "patch_strip": 0,
        "patches": {},
        "strip_prefix": strip_prefix,
        "url": url,
    }
    with open(source_json, "w", encoding="utf-8") as f:
        json.dump(source_data, f, indent=2)
        f.write("\n")

    print(f"Initialized BCR module at {version_dir.relative_to(workspace)}")


def cmd_patch(args: argparse.Namespace) -> None:
    workspace = get_workspace_root()
    registry_root = get_registry_root(workspace)
    version_dir = registry_root / "modules" / args.name / args.version
    source_json_file = version_dir / "source.json"

    if not source_json_file.exists():
        print(f"Error: {source_json_file} does not exist. Run init first.", file=sys.stderr)
        sys.exit(1)

    patches_dir = version_dir / "patches"
    patches_dir.mkdir(parents=True, exist_ok=True)

    with open(source_json_file, "r", encoding="utf-8") as f:
        source_data = json.load(f)

    if args.build_file:
        build_path = Path(args.build_file)
        if not build_path.exists():
            print(f"Error: BUILD file {build_path} does not exist", file=sys.stderr)
            sys.exit(1)

        build_content = build_path.read_text(encoding="utf-8")
        patch_file = patches_dir / "add_build_file.patch"

        lines = build_content.splitlines()
        patch_lines = [
            "--- /dev/null",
            "+++ BUILD.bazel",
            f"@@ -0,0 +1,{len(lines)} @@",
        ]
        for line in lines:
            patch_lines.append(f"+{line}")
        patch_content = "\n".join(patch_lines) + "\n"

        patch_file.write_text(patch_content, encoding="utf-8")
        patch_hash = compute_sri_hash(patch_file.read_bytes())
        source_data.setdefault("patches", {})["add_build_file.patch"] = patch_hash
        print(f"Generated patch {patch_file.name} with hash {patch_hash}")

    if args.patch_file:
        src_patch = Path(args.patch_file)
        dest_patch = patches_dir / src_patch.name
        shutil.copy2(src_patch, dest_patch)
        patch_hash = compute_sri_hash(dest_patch.read_bytes())
        source_data.setdefault("patches", {})[src_patch.name] = patch_hash
        print(f"Installed patch {src_patch.name} with hash {patch_hash}")

    with open(source_json_file, "w", encoding="utf-8") as f:
        json.dump(source_data, f, indent=2)
        f.write("\n")
    print(f"Updated {source_json_file.relative_to(workspace)}")


def find_any2bazel_scripts() -> Optional[Path]:
    """Locate any2bazel skill scripts in known search paths."""
    candidates = [
        Path.home() / ".gemini" / "skills" / "any2bazel" / "scripts",
        Path.home() / ".claude" / "skills" / "any2bazel" / "scripts",
    ]
    for c in candidates:
        if c.is_dir() and (c / "diff.py").exists():
            return c
    return None


def cmd_model(args: argparse.Namespace) -> None:
    source_dir = Path(args.source_dir).resolve()
    if not source_dir.exists():
        print(f"Error: Source directory {source_dir} does not exist", file=sys.stderr)
        sys.exit(1)

    skill_scripts = find_any2bazel_scripts()
    build_system = args.type
    if not build_system:
        if (source_dir / "CMakeLists.txt").exists():
            build_system = "cmake"
        elif (source_dir / "configure").exists() or (source_dir / "configure.ac").exists():
            build_system = "configure"
        elif (source_dir / "Makefile").exists():
            build_system = "make"
        else:
            build_system = "cmake"

    print(f"Modeling build system for {args.name} using '{build_system}'...")
    print(f"Source directory: {source_dir}")

    # Inspect C/C++ source and header files
    c_srcs = sorted(str(p.relative_to(source_dir)) for p in source_dir.glob("*.c"))
    h_hdrs = sorted(str(p.relative_to(source_dir)) for p in source_dir.glob("*.h"))

    print(f"Found {len(c_srcs)} C source files and {len(h_hdrs)} header files.")
    if skill_scripts:
        print(f"any2bazel skill scripts located at: {skill_scripts}")
    else:
        print("Note: any2bazel skill scripts not detected in default paths; using native modeling.")

    # Scaffold suggested BUILD.bazel
    target_name = args.name.removeprefix("lib")
    build_snippet = [
        'load("@rules_cc//cc:defs.bzl", "cc_library")',
        "",
        "cc_library(",
        f'    name = "{target_name}",',
        "    srcs = [",
    ]
    for s in c_srcs:
        build_snippet.append(f'        "{s}",')
    build_snippet.extend([
        "    ],",
        "    hdrs = [",
    ])
    for h in h_hdrs:
        build_snippet.append(f'        "{h}",')
    build_snippet.extend([
        "    ],",
        '    includes = ["."],',
        '    visibility = ["//visibility:public"],',
        ")",
    ])

    suggested_build = "\n".join(build_snippet) + "\n"
    output_path = Path(args.out) if args.out else Path.cwd() / f"BUILD.{args.name}.suggested"
    output_path.write_text(suggested_build, encoding="utf-8")
    print(f"Suggested BUILD file written to {output_path}")


def cmd_verify(args: argparse.Namespace) -> None:
    workspace = get_workspace_root()
    module_name = args.name
    target = args.target or module_name

    target_label = f"@{module_name}//:{target}"
    print(f"Verifying build of target: {target_label} ...")

    # Generate invocation ID per Bazel protocol
    import uuid
    invocation_id = str(uuid.uuid4())
    print(f"Invocation ID: {invocation_id}")

    cmd = [
        "bazel",
        "build",
        f"--invocation_id={invocation_id}",
        target_label,
    ]
    res = subprocess.run(cmd, cwd=workspace)
    if res.returncode == 0:
        print(f"SUCCESS: {target_label} built cleanly from local BCR registry!")
    else:
        print(f"FAILURE: Build failed with exit code {res.returncode}", file=sys.stderr)
        sys.exit(res.returncode)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Local BCR 3rdparty registry and any2bazel workflow automator",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # init
    p_init = subparsers.add_parser("init", help="Initialize a module in bazel/3rdparty")
    p_init.add_argument("name", help="BCR module name (e.g. zlib)")
    p_init.add_argument("version", help="Module version (e.g. 1.3.1)")
    p_init.add_argument("--url", required=True, help="Download URL of source archive")
    p_init.add_argument("--strip-prefix", help="Strip prefix in archive (defaults to <name>-<version>)")
    p_init.add_argument("--homepage", help="Homepage URL")
    p_init.set_defaults(func=cmd_init)

    # patch
    p_patch = subparsers.add_parser("patch", help="Add or update patch for a BCR module")
    p_patch.add_argument("name", help="BCR module name")
    p_patch.add_argument("version", help="Module version")
    p_patch.add_argument("--build-file", help="Path to BUILD.bazel to turn into add_build_file.patch")
    p_patch.add_argument("--patch-file", help="Path to existing patch file to install")
    p_patch.set_defaults(func=cmd_patch)

    # model
    p_model = subparsers.add_parser("model", help="Model build system with any2bazel")
    p_model.add_argument("name", help="Module name")
    p_model.add_argument("--source-dir", required=True, help="Directory containing unpacked sources")
    p_model.add_argument("--type", choices=["cmake", "configure", "make"], help="Build system type")
    p_model.add_argument("--out", help="Output path for suggested BUILD file")
    p_model.set_defaults(func=cmd_model)

    # verify
    p_verify = subparsers.add_parser("verify", help="Verify module builds via local BCR registry")
    p_verify.add_argument("name", help="Module name")
    p_verify.add_argument("version", help="Module version")
    p_verify.add_argument("--target", help="Target name to build within module (default: module name)")
    p_verify.set_defaults(func=cmd_verify)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
