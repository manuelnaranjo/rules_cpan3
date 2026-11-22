---
name: cpan2bazel
description: Port Perl CPAN distributions to Bazel and the local BCR registry. Generates hermetic BUILD.bazel and BCR module definitions for pure Perl, XS modules, and generated Perl code, supporting Linux and macOS on x86_64 and arm64.
user-invocable: true
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
---

# /cpan2bazel — Port CPAN Distributions to Bazel BCR Modules

`cpan2bazel` ports Perl CPAN distributions into hermetic Bazel modules registered under the local Bazel Central Registry (BCR) index as `perl-<cpan-name>`. Inspired by `any2bazel`, it models and analyzes Perl build systems (`Makefile.PL` / ExtUtils::MakeMaker, `Build.PL` / Module::Build, and `dist.ini` / Dist::Zilla) to produce deterministic `BUILD.bazel` files, handles generated Perl/C code and XS extensions, and ensures cross-platform compilation for Linux and macOS across x86_64 and arm64.

---

## Prerequisites

- `python3` (>= 3.9)
- `bazel` or `bazelisk`
- `curl` or `wget`
- `tar`, `gzip`

---

## Architecture & Integration

### BCR Registry Layout (`bazel/3rdparty`)

Ported Perl distributions are placed under `bazel/3rdparty/modules/perl-<cpan-name>/`:

```
bazel/3rdparty/modules/perl-<cpan-name>/
├── metadata.json
└── <version>/
    ├── MODULE.bazel
    ├── source.json
    └── patches/
        └── add_build_file.patch
```

Module names in Bzlmod are strictly lowercase alphanumeric with hyphens (e.g. `Compress-Raw-Zlib` becomes `perl-compress-raw-zlib`).

### Bzlmod Injection (`cpan.inject`)

Once a distribution is ported into the registry, workspaces using `rules_cpan` can consume it via `bazel_dep` and inject it into the `cpan` module extension:

```python
# In MODULE.bazel
bazel_dep(name = "perl-compress-raw-zlib", version = "2.226")

cpan = use_extension("@rules_cpan//cpan:extensions.bzl", "cpan")
cpan.install(
    name = "cpan",
    lock = "//:cpan.lock.json",
)

# Inject the ported module to replace cpan_dist_repo
cpan.inject(
    distribution = "Compress-Raw-Zlib",
    hub = "cpan",
    target = "@perl-compress-raw-zlib//:Compress-Raw-Zlib",
)
```

When injected:
1. `cpan` module extension suppresses generation of internal `cpan_dist_repo` for this distribution.
2. Downstream distributions in the CPAN closure depending on `Compress-Raw-Zlib` have their runtime dependencies routed to `@perl-compress-raw-zlib//:Compress-Raw-Zlib`.
3. Hub aliases `@cpan//:Compress-Raw-Zlib` and `@cpan//Compress-Raw-Zlib` route to the injected target.

---

## Migration Workflow

### 1. Analyze Upstream Distribution

`cpan2bazel` inspects the CPAN distribution archive or working directory:
- **Pure Perl**: Classifies `.pm` and `.pod` sources under `lib/` or `.`, and runfiles under `lib/` or `share/`.
- **XS C Extensions**: Identifies `*.xs`, auxiliary `*.c` and `*.h` files, `typemap`, and DynaLoader output path (`auto/...`).
- **Generated Code & Fallbacks**: Detects generated constants (e.g. `fallback/constants.h`, `fallback/constants.xs` from `constants.pl`), typemaps, and preprocessor definitions.
- **Native Prerequisites**: Detects external native library dependencies (e.g. `zlib` via `-lz`, `libyaml` via `-lyaml`) and maps them to BCR modules (`@zlib`, `@libyaml`).

### 2. Multi-Platform Support (Linux & macOS across x86_64 & arm64)

The generated `BUILD.bazel` uses standard platform selects and compatibility constraints:
- `@platforms//os:linux`
- `@platforms//os:osx`
- `@platforms//cpu:x86_64`
- `@platforms//cpu:arm64`

Example for XS module:
```python
load("@rules_cpan//cpan:defs.bzl", "cpan_xs")
load("@rules_perl//perl:defs.bzl", "perl_library")

package(default_visibility = ["//visibility:public"])

cpan_xs(
    name = "foo_xs",
    srcs = ["Foo.xs"],
    cc_srcs = glob(["*.c"], exclude = ["t/**"]),
    defines = select({
        "@platforms//os:osx": ["OSX_COMPAT", "GZIP_OS_CODE=19"],
        "//conditions:default": ["GZIP_OS_CODE=3"],
    }),
    output_loc = "auto/Foo/Foo",
    textual_hdrs = glob(["*.h", "*.xs"]),
    typemaps = ["typemap"],
    deps = ["@zlib"],
)

perl_library(
    name = "Foo",
    srcs = glob(["lib/**/*.pm"]),
    data = [":foo_xs"],
    includes = [".", "lib"],
)
```

### 3. Running `cpan2bazel` CLI

The CLI tool automates tarball fetching, SRI hash calculation, patch generation, and registry updates:

```bash
# Port a distribution from MetaCPAN
python3 .agents/skills/cpan2bazel/scripts/cpan2bazel.py \
    --distribution Compress-Raw-Zlib \
    --version 2.226 \
    --registry bazel/3rdparty

# Port a local tarball
python3 .agents/skills/cpan2bazel/scripts/cpan2bazel.py \
    --archive /path/to/Foo-1.0.tar.gz \
    --registry bazel/3rdparty
```

---

## Verifying Ported Modules

Verify cross-platform compilation of ported modules:

```bash
INVOCATION_ID=$(uuidgen)
echo "Invocation ID: ${INVOCATION_ID}"
bazel build --invocation_id=${INVOCATION_ID} \
    --platforms=@rules_cpan//platforms:linux_x86_64 \
    --platforms=@rules_cpan//platforms:linux_arm64 \
    --platforms=@rules_cpan//platforms:darwin_x86_64 \
    --platforms=@rules_cpan//platforms:darwin_arm64 \
    @perl-<cpan-name>//:<dist_name>
```
