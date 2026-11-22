# rules_cpan

Bazel rules for consuming Perl CPAN dependencies hermetically.

## Requirements

- Bazel 9+ (with strict Bzlmod enabled)

## Overview

`rules_cpan` provides hermetic resolution, building, and linking of CPAN distributions in Bazel, supporting:
- Pure Perl and XS (C/C++) extensions
- Hermetic toolchains via `rules_perl` and LLVM
- Multi-arch cross-compilation (Linux and macOS on `x86_64` and `arm64`)
- Remote Build Execution (RBE) readiness
- Fast bulk CPAN dependency resolution and lockfile generation

## Usage

In your `MODULE.bazel`:

```starlark
bazel_dep(name = "rules_cpan", version = "...")
```

## Dependency Resolution & Lockfile Generation

`rules_cpan` provides a fast bulk dependency resolver that parses user dependency specifications (`deps.txt`), queries CPAN mirror indices (`02packages.details.txt.gz`) and MetaCPAN bulk APIs, resolves the complete transitive dependency closure, verifies SHA256 checksums, detects XS/C extensions, and produces a deterministic `cpan.lock.json`:

```bash
INVOCATION_ID=$(uuidgen)
echo "Invocation ID: ${INVOCATION_ID}"
bazel run --invocation_id=${INVOCATION_ID} //tools:resolver -- --input deps.txt --output cpan.lock.json
```

See [docs/resolver.md](docs/resolver.md) for full details, lockfile format specifications, and CLI options.

