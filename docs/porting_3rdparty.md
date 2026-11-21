# Porting 3rdparty Native C/C++ Dependencies for CPAN with `any2bazel`

This document describes how to port native C/C++ libraries required by Perl CPAN distributions (e.g. `zlib`, `openssl`, `libcurl`, `libyaml`) into the local Bazel Central Registry (BCR) index at `bazel/3rdparty`, using the `any2bazel` parity workflow.

---

## 1. Overview & Architecture

Many Perl CPAN distributions use XS (Perl's C extension mechanism) or FFI to interface with system C libraries:
- `Compress::Raw::Zlib` & `IO::Compress::Zlib` require `zlib`
- `Net::SSLeay` & `IO::Socket::SSL` require `openssl`
- `Net::Curl` requires `libcurl`
- `YAML::XS` requires `libyaml`

To ensure hermetic, reproducible builds across Linux and macOS (x86_64 and arm64), `rules_cpan` manages native dependencies via a local BCR registry at `bazel/3rdparty`.

### Registry Precedence

Registry configuration is established in `.bazelrc`:

```ini
# Local BCR registry first, followed by public BCR
common --registry=file://%workspace%/bazel/3rdparty
common --registry=https://bcr.bazel.build
```

In `MODULE.bazel`:
```python
# Declare 3rdparty native C/C++ libraries ported to bazel/3rdparty
bazel_dep(name = "zlib", version = "1.3.1.bcr.5")
```

When Bazel resolves dependencies, it checks `file://%workspace%/bazel/3rdparty` first. If the module and version are defined locally, Bazel uses the local port; otherwise, it falls back to the public BCR.

---

## 2. Porting Workflow using `any2bazel`

The `any2bazel` workflow ensures parity between upstream build systems (CMake, Autotools, Make) and the generated Bazel rules by comparing action graphs.

### Step 1: Upstream Model Extraction

Unpack the upstream release archive into a workspace or scratch directory:

#### For CMake projects:
1. Enable File API query and trace execution:
   ```bash
   mkdir -p <build>/.cmake/api/v1/query
   touch <build>/.cmake/api/v1/query/codemodel-v2
   cmake -S <src> -B <build> -DCMAKE_EXPORT_COMPILE_COMMANDS=ON \
       --trace-expand --trace-format=json-v1 2> <build>/trace.jsonl
   ```
2. Extract the canonical action model:
   ```bash
   python3 ~/.gemini/skills/any2bazel/scripts/extract_cmake.py \
       <build> <src> model.cmake.json <build>/trace.jsonl
   ```

#### For Autotools / Make projects:
1. Configure and run compilation actions under Bear or make dry-run:
   ```bash
   cd <src>
   ./configure
   make --dry-run > make_actions.txt
   ```
2. Parse the compilation actions into translation units, compiler flags, and include paths using `//tools:port_3rdparty -- model <name> --source-dir <src>`.

---

### Step 2: Bazel Scaffolding & Action Extraction

1. Draft the `BUILD.bazel` target:
   ```python
   load("@rules_cc//cc:defs.bzl", "cc_library")

   cc_library(
       name = "zlib",
       srcs = glob(["*.c"]),
       hdrs = glob(["*.h"]),
       includes = ["."],
       visibility = ["//visibility:public"],
   )
   ```

2. Extract Bazel action graph:
   ```bash
   bazel aquery 'mnemonic("CppCompile|ObjcCompile|CppLink|CppArchive", //...)' \
       --features=-compiler_param_file --features=-linker_param_file \
       --output=jsonproto > aquery.json
   python3 ~/.gemini/skills/any2bazel/scripts/extract_bazel.py \
       aquery.json <src> model.bazel.json
   ```

---

### Step 3: Action Graph Diffing & Parity Convergence

Run the `any2bazel` differ to identify missing translation units, compile flags, defines, or include paths:

```bash
python3 ~/.gemini/skills/any2bazel/scripts/diff.py \
    model.cmake.json model.bazel.json any2bazel.json > diff.json
python3 ~/.gemini/skills/any2bazel/scripts/triage.py diff.json
```

Iterate on `BUILD.bazel` and `any2bazel.json` until:
`converged: true` (zero errors).

---

### Step 4: Packaging into `bazel/3rdparty`

Use the automated `//tools:port_3rdparty` utility:

1. Initialize module directory:
   ```bash
   bazel run //tools:port_3rdparty -- init zlib 1.3.1 \
       --url "https://github.com/madler/zlib/releases/download/v1.3.1/zlib-1.3.1.tar.gz" \
       --strip-prefix "zlib-1.3.1"
   ```

2. Generate patch from the converged `BUILD.bazel`:
   ```bash
   bazel run //tools:port_3rdparty -- patch zlib 1.3.1 \
       --build-file path/to/BUILD.bazel
   ```

3. Verify hermetic build:
   ```bash
   bazel run //tools:port_3rdparty -- verify zlib 1.3.1 --target zlib
   ```

---

## 3. Consuming Ported Modules in CPAN Distributions

When authoring or generating Bazel rules for CPAN modules that require native libraries:

1. In `cpan/defs.bzl` or target BUILD files, reference the native module:
   ```python
   perl_xs(
       name = "Zlib_xs",
       srcs = ["Zlib.xs"],
       deps = ["@zlib//:zlib"],
   )
   ```

2. Both C tests and Perl test harnesses can hermetically link against and verify the native dependency:
   ```python
   cc_test(
       name = "zlib_consumption_test",
       srcs = ["test_zlib.c"],
       deps = ["@zlib//:zlib"],
   )
   ```

All artifacts build hermetically using the registered LLVM toolchain across all supported target platforms.
