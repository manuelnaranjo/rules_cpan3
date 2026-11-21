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
