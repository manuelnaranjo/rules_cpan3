# Local Bazel Central Registry (BCR) Index (`bazel/3rdparty`)

This directory establishes a local Bazel Central Registry (BCR) index conforming to the official BCR specification (`bazel_registry.json`, `modules/`).

It allows `rules_cpan` to provide hermetic, reproducible ports of external non-BCR or customized C/C++ libraries needed by Perl CPAN distributions (such as `zlib`, `openssl`, `libcurl`, `libyaml`).

## Registry Layout

```
bazel/3rdparty/
├── bazel_registry.json           # Registry metadata (module_base_path: "modules")
├── README.md                     # This file
└── modules/
    └── <module_name>/            # e.g., zlib
        ├── metadata.json         # Module versions and maintainers
        └── <version>/            # e.g., 1.3.1
            ├── MODULE.bazel      # Module dependencies (rules_cc, platforms, etc.)
            ├── source.json       # Source archive URL, SRI hash, patches
            └── patches/
                └── add_build_file.patch  # Generates hermetic BUILD.bazel
```

## Registry Resolution & Precedence

Bazel searches registries in the exact order specified in `.bazelrc`:

```ini
common --registry=file://%workspace%/bazel/3rdparty
common --registry=https://bcr.bazel.build
```

- When resolving a dependency, Bazel checks the local `bazel/3rdparty` registry first.
- If a matching module and version exists locally, Bazel uses it.
- If not present locally, Bazel falls back to the public BCR index at `https://bcr.bazel.build`.

## Automated Porting Tool

Use `//tools:port_3rdparty` to automate adding and managing ported dependencies:

```bash
# Initialize a new module
bazel run //tools:port_3rdparty -- init <name> <version> --url <tarball_url>

# Turn a BUILD.bazel into a patch and register in source.json
bazel run //tools:port_3rdparty -- patch <name> <version> --build-file <path_to_BUILD.bazel>

# Model upstream source using any2bazel
bazel run //tools:port_3rdparty -- model <name> --source-dir <unpacked_source_dir>

# Verify hermetic build via local registry
bazel run //tools:port_3rdparty -- verify <name> <version>
```

For complete documentation on the `any2bazel` parity workflow, see [docs/porting_3rdparty.md](../../docs/porting_3rdparty.md).
