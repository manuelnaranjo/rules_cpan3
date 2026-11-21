# Local Bazel Central Registry (BCR) Index (`bazel/3rdparty`)

This directory establishes a local Bazel Central Registry (BCR) index conforming to the official BCR specification (`bazel_registry.json`, `modules/`).

## Scope & Purpose

- **BCR-available dependencies**: Native dependencies that already exist in the public BCR (such as `zlib`, `curl`, `libxml2`, `boringssl`) are consumed directly from `https://bcr.bazel.build` via `bazel_dep`.
- **Non-BCR dependencies**: Native C/C++ libraries needed by Perl CPAN distributions that are **not** present in public BCR are ported here using the `any2bazel` workflow.

## Registry Resolution & Precedence

Configured in `.bazelrc`:

```ini
common --registry=file://%workspace%/bazel/3rdparty
common --registry=https://bcr.bazel.build
```

1. Bazel checks `file://%workspace%/bazel/3rdparty` first.
2. If not defined locally, Bazel falls back to `https://bcr.bazel.build`.

## Registry Layout

```
bazel/3rdparty/
├── bazel_registry.json           # Registry metadata (module_base_path: "modules")
├── README.md                     # This file
└── modules/
    └── <module_name>/
        ├── metadata.json         # Module versions and maintainers
        └── <version>/
            ├── MODULE.bazel      # Module dependencies (rules_cc, platforms, etc.)
            ├── source.json       # Archive URL, SRI hash, patches
            └── patches/
                └── add_build_file.patch  # Generates hermetic BUILD.bazel
```

See [docs/porting_3rdparty.md](../../docs/porting_3rdparty.md) for full instructions on installing and running `any2bazel` to model and package native dependencies.
