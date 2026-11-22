# Bzlmod Module Extension & Repository Rules

`rules_cpan` provides a Bzlmod module extension (`cpan`) and repository rules that turn a deterministic `cpan.lock.json` lockfile into Bazel targets using `rules_perl` and hermetic C/C++ toolchains.

## Quickstart

### 1. In `MODULE.bazel`

Declare dependency on `rules_cpan`, configure the module extension with your lockfile, and import the hub repository:

```starlark
bazel_dep(name = "rules_cpan", version = "0.0.0")

cpan = use_extension("@rules_cpan//cpan:extensions.bzl", "cpan")
cpan.install(
    name = "cpan",
    lock = "//:cpan.lock.json",
)
use_repo(cpan, "cpan")
```

### 2. In `BUILD.bazel`

Consume installed CPAN modules by distribution name:

```starlark
load("@rules_perl//perl:defs.bzl", "perl_binary", "perl_test")

perl_test(
    name = "my_test",
    srcs = ["my_test.t"],
    deps = [
        "@cpan//Algorithm-Diff",
        "@cpan//Compress-Raw-Zlib",
    ],
)
```

Both `@cpan//Algorithm-Diff` and `@cpan//:Algorithm-Diff` are valid label formats.

---

## Features

### Pure Perl Distributions
Pure Perl distributions are extracted hermetically and converted into `perl_library` targets:
- Automatically packages `lib/**/*.pm`, `lib/**/*.pod`, and root `*.pm` files.
- Packages non-code assets in `data`.
- Configures includes (`.`, `lib`) so modules are accessible to Perl's `@INC`.
- Connects runtime dependencies to other resolved CPAN distributions.

### XS (C Extension) Distributions
Distributions containing XS/C extensions use `cpan_xs`:
- Translates `.xs` files to C via `xsubpp`.
- Compiles using hermetic LLVM toolchain with `cc_common`.
- Links dynamic libraries under the standard Perl `auto/<Path>/<Module>.<ext>` location.
- Binds into a `perl_library` with dynamic library in `data` and include paths configured.

### Visibility Control
- **Direct Dependencies**: Top-level distributions specified in `root_dependencies` of `cpan.lock.json` are exposed with `visibility = ["//visibility:public"]`.
- **Transitive Dependencies**: Indirect distributions pulled in as transitive dependencies have `visibility = ["//visibility:private"]` in the hub repository, preventing unintentional direct usage without declaring them in `deps.txt`.

### Multiple Hub Repositories
A workspace can declare multiple independent hub repositories (e.g. for different Perl versions, platforms, or configurations):

```starlark
cpan.install(
    name = "cpan_linux",
    lock = "//platforms/linux:cpan.lock.json",
)
cpan.install(
    name = "cpan_macos",
    lock = "//platforms/macos:cpan.lock.json",
)
use_repo(cpan, "cpan_linux", "cpan_macos")
```

Distribution repositories are isolated by prefixing with the hub name (`<hub_name>__<dist_name>`), avoiding any target or repo collisions.

### Overlays and Customization
For distributions requiring custom build logic, patches, or native BCR dependencies (e.g. `@zlib`):

```starlark
cpan.install(
    name = "cpan",
    lock = "//:cpan.lock.json",
    build_file_overlays = {
        "Compress-Raw-Zlib": "//tests:BUILD.Compress-Raw-Zlib.bazel",
    },
    patch_cmds = {
        "Compress-Raw-Zlib": [
            "cp fallback/constants.h constants.h",
            "cp fallback/constants.xs constants.xs",
        ],
    },
    patch_cmds_win = {
        "Compress-Raw-Zlib": [
            "copy fallback\\constants.h constants.h",
            "copy fallback\\constants.xs constants.xs",
        ],
    },
)
```

### Cyclic Dependency Pruning
CPAN distributions frequently declare circular runtime requirements (e.g. `Test::Simple` <-> `Time::HiRes` <-> `XSLoader`). The `cpan` module extension runs bounded cycle detection to prune back-edges from runtime dependencies, ensuring that Bazel's build graph remains a strict Directed Acyclic Graph (DAG) while preserving full runtime module availability in runfiles.
