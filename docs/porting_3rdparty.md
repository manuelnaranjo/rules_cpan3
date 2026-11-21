# Porting 3rdparty Native C/C++ Dependencies for CPAN with `any2bazel`

This document outlines how to port external non-BCR C/C++ libraries needed by Perl CPAN distributions into the local Bazel Central Registry (BCR) index at `bazel/3rdparty` using the `any2bazel` workflow.

---

## 1. Registry Architecture & Precedence

`rules_cpan` consumes dependencies through Bzlmod and Bazel Central Registry (BCR).

### When to Port to `bazel/3rdparty`
- **BCR-available libraries**: Do **not** port libraries that already exist in the public BCR (such as `zlib`, `curl`, `libxml2`, `boringssl`, `mimalloc`). Always consume these directly via `bazel_dep` from the public BCR (`https://bcr.bazel.build`).
- **Non-BCR native libraries**: Only port native C/C++ libraries that are required by CPAN XS modules and are **not** present in BCR (e.g. `gdbm`, `libdb`, `libtidy`).

### Registry Configuration

The registry precedence is defined in `.bazelrc`:

```ini
# Local BCR registry first, followed by public BCR
common --registry=file://%workspace%/bazel/3rdparty
common --registry=https://bcr.bazel.build
```

In `MODULE.bazel`:
```python
# Registries configured in .bazelrc:
# 1. file://%workspace%/bazel/3rdparty (Local BCR registry for 3rdparty native C/C++ dependencies)
# 2. https://bcr.bazel.build (Public Bazel Central Registry)
# registry = ["file://%workspace%/bazel/3rdparty", "https://bcr.bazel.build"]
```

When resolving dependencies:
1. Bazel inspects `file://%workspace%/bazel/3rdparty` first.
2. If the module is not found locally, Bazel falls back to the public BCR index at `https://bcr.bazel.build`.

---

## 2. Installing `any2bazel`

`any2bazel` is an automated tool and agent skill developed by EngFlow for migrating projects (CMake, Make, Maven) to Bazel via deterministic parity comparison between action graphs.

### Prerequisites
- `python3` (>= 3.9)
- `bazel` or `bazelisk`
- `curl` or `wget`
- `jq`

### Installation
Clone `any2bazel` into your local skills or tools directory:

```bash
# Clone any2bazel repository
git clone https://github.com/engflow/any2bazel ~/.gemini/skills/any2bazel

# Set environment variable for convenience
export ANY2BAZEL_DIR="$HOME/.gemini/skills/any2bazel"
```

---

## 3. The `any2bazel` Parity Porting Workflow

The core idea of `any2bazel` is to extract a canonical action model from the upstream build system (CMake, Make, Autotools) and compare it against the Bazel action graph produced by `bazel aquery`.

```
Reference build           ──extract_<frontend>.py──┐
                                                   ├─► reconstruct.py ─► diff.py ─► triage.py
Bazel aquery jsonproto    ──extract_bazel.py───────┘        ▲
                                                            │
                                                     any2bazel.json
```

### Step 1: Extract the Reference Build Model

Unpack the upstream release archive of the native C library:

#### For CMake Projects:
```bash
mkdir -p <build>/.cmake/api/v1/query
touch <build>/.cmake/api/v1/query/codemodel-v2
cmake -S <src> -B <build> -DCMAKE_EXPORT_COMPILE_COMMANDS=ON \
    --trace-expand --trace-format=json-v1 2> <build>/trace.jsonl

python3 "$ANY2BAZEL_DIR/scripts/extract_cmake.py" \
    <build> <src> model.cmake.json <build>/trace.jsonl
```

#### For Autotools / Make Projects:
```bash
cd <src>
./configure
make --dry-run > make_actions.txt
```
Extract actions and compilation parameters into `model.<frontend>.json`.

### Step 2: Author Initial `BUILD.bazel` and `MODULE.bazel`

Draft a `BUILD.bazel` covering the library translation units and headers:

```python
load("@rules_cc//cc:defs.bzl", "cc_library")

cc_library(
    name = "foo",
    srcs = glob(["*.c"]),
    hdrs = glob(["*.h"]),
    includes = ["."],
    visibility = ["//visibility:public"],
)
```

### Step 3: Extract the Bazel Action Graph

Extract the action graph via `bazel aquery` with param-file expansion disabled:

```bash
bazel aquery 'mnemonic("CppCompile|ObjcCompile|CppLink|CppArchive", //...)' \
    --features=-compiler_param_file --features=-linker_param_file \
    --output=jsonproto > aquery.json

python3 "$ANY2BAZEL_DIR/scripts/extract_bazel.py" \
    aquery.json <src> model.bazel.json
```

### Step 4: Diff and Triage

Run the differ and triage discrepancies:

```bash
python3 "$ANY2BAZEL_DIR/scripts/diff.py" \
    model.<frontend>.json model.bazel.json any2bazel.json > diff.json

python3 "$ANY2BAZEL_DIR/scripts/triage.py" diff.json
```

Iterate on `BUILD.bazel` (copts, defines, includes, deps) and `any2bazel.json` until:
`converged: true`.

---

## 4. Packaging into `bazel/3rdparty`

Once the Bazel build reaches parity with upstream, package the library into the local BCR registry:

1. **Directory Structure**:
   ```
   bazel/3rdparty/modules/<name>/
   ├── metadata.json
   └── <version>/
       ├── MODULE.bazel
       ├── source.json
       └── patches/
           └── add_build_file.patch
   ```

2. **Compute SRI Hashes**:
   Compute Subresource Integrity (SRI) sha256 hashes for the upstream archive and patch file:
   ```bash
   # Upstream tarball integrity
   sha256sum <archive.tar.gz> | awk '{print $1}' | xxd -r -p | base64
   # Patch integrity
   sha256sum add_build_file.patch | awk '{print $1}' | xxd -r -p | base64
   ```

3. **Format `source.json`**:
   ```json
   {
     "url": "https://example.org/download/libfoo-1.0.0.tar.gz",
     "integrity": "sha256-...",
     "strip_prefix": "libfoo-1.0.0",
     "patch_strip": 0,
     "patches": {
       "add_build_file.patch": "sha256-..."
     }
   }
   ```

4. **Format `metadata.json`**:
   Keep version history clean by specifying only active versions:
   ```json
   {
     "homepage": "https://example.org/libfoo",
     "maintainers": [
       {
         "name": "rules_cpan maintainers",
         "github": "manuelnaranjo"
       }
     ],
     "versions": [
       "1.0.0"
     ],
     "yanked_versions": {}
   }
   ```

---

## 5. Consuming Native C Dependencies in CPAN XS Modules

`rules_cpan` provides the `cpan_xs` rule in `//cpan:defs.bzl`. Unlike standard `perl_xs`, `cpan_xs` properly propagates `CcInfo` compilation contexts (headers, includes, defines) from dependencies to the C compilation step, and provides `textual_hdrs` as inputs to `xsubpp`.

### Example: Building CPAN `Compress::Raw::Zlib` with `@zlib`

In [tests/Compress-Raw-Zlib/BUILD.bazel](file:///home/manuel/workspace/rules_cpan3/.worktrees/main/tests/Compress-Raw-Zlib/BUILD.bazel):

```python
load("@rules_perl//perl:defs.bzl", "perl_library", "perl_test")
load("//cpan:defs.bzl", "cpan_xs")

# 1. Build the XS shared library linking against BCR zlib
cpan_xs(
    name = "zlib_xs",
    srcs = ["Zlib.xs"],
    defines = [
        "NO_VIZ",
        "USE_PPPORT_H",
        "GZIP_OS_CODE=3",
        "Perl_crz_BUILD_ZLIB=0",
    ],
    output_loc = "auto/Compress/Raw/Zlib/Zlib",
    textual_hdrs = [
        "constants.h",
        "constants.xs",
        "ppport.h",
    ],
    typemaps = ["typemap"],
    deps = [
        "@zlib",
    ],
)

# 2. Package into perl_library
perl_library(
    name = "Compress-Raw-Zlib",
    srcs = ["lib/Compress/Raw/Zlib.pm"],
    data = [":zlib_xs"],
    includes = [".", "lib"],
)

# 3. Run CPAN test suites with perl_test
perl_test(
    name = "version_test",
    size = "small",
    srcs = ["t/01version.t"],
    deps = [
        ":Compress-Raw-Zlib",
        ":test_utils",
    ],
)

perl_test(
    name = "zlib_test",
    size = "small",
    srcs = ["t/02zlib.t"],
    deps = [
        ":Compress-Raw-Zlib",
        ":test_utils",
    ],
)
```

Running `bazel test //tests/Compress-Raw-Zlib:...` executes all 362 CPAN tests hermetically using the LLVM C toolchain, BCR `zlib`, and `rules_perl`.
