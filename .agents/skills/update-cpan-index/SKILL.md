---
name: update-cpan-index
description: Regenerate and verify the rules_cpan cpan-index BCR registry ports using the hermetic out-of-build indexer tool.
user-invocable: true
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
---

# /update-cpan-index — Regenerate and Verify CPAN Index BCR Modules

The `update-cpan-index` skill guides developers and AI agents in regenerating, indexing, and validating ported CPAN distributions in the `cpan-index` local Bazel Central Registry (BCR) registry.

The indexer tool runs out-of-build via `bazel run //:cpan_indexer -- <args>` to inspect upstream CPAN tarballs, synthesize `BUILD.bazel`, format them with `buildifier`, manage `overlay/` assets, and verify integrity hashes in `source.json`.

---

## Bazel Invocation Protocol

Whenever invoking `bazel` commands, adhere to the mandatory Invocation ID protocol:

```bash
INVOCATION_ID=$(uuidgen)
echo "Invocation ID: ${INVOCATION_ID}"
bazel run --invocation_id=${INVOCATION_ID} //:cpan_indexer -- <args>
```

---

## Indexer Operations

### 1. Check Idempotency (CI & Verification)

To verify that `cpan-index` is completely up to date and that regeneration produces zero unexpected diffs, run with `--check`:

```bash
INVOCATION_ID=$(uuidgen)
echo "Invocation ID: ${INVOCATION_ID}"
bazel run --invocation_id=${INVOCATION_ID} //:cpan_indexer -- \
    --check \
    --all \
    --lockfile e2e/deps_txt/cpan.lock.json \
    --lockfile e2e/pakket/cpan.lock.json \
    --lockfile tests/cpan.lock.json
```

Alternatively, use the Makefile target:

```bash
make check-cpan-index
```

If any file in `cpan-index` would be modified, added, or deleted, unified diffs are printed to standard output and the command exits with code `1`.

---

### 2. Full Regeneration Across All Modules

To regenerate all ported modules in `cpan-index`:

```bash
INVOCATION_ID=$(uuidgen)
echo "Invocation ID: ${INVOCATION_ID}"
bazel run --invocation_id=${INVOCATION_ID} //:cpan_indexer -- \
    --regenerate \
    --all \
    --lockfile e2e/deps_txt/cpan.lock.json \
    --lockfile e2e/pakket/cpan.lock.json \
    --lockfile tests/cpan.lock.json
```

> [!NOTE]
> Lockfiles must be explicitly passed via `--lockfile <path>`. The indexer does not guess or hardcode lockfile paths.

---

### 3. Regenerate a Single Module

To regenerate a single distribution or module (e.g. `Crypt-OpenSSL-RSA`):

```bash
INVOCATION_ID=$(uuidgen)
echo "Invocation ID: ${INVOCATION_ID}"
bazel run --invocation_id=${INVOCATION_ID} //:cpan_indexer -- \
    --regenerate \
    -d Crypt-OpenSSL-RSA \
    --lockfile tests/cpan.lock.json
```

---

### 4. Index a New Lockfile

When updating or adding a lockfile:

```bash
INVOCATION_ID=$(uuidgen)
echo "Invocation ID: ${INVOCATION_ID}"
bazel run --invocation_id=${INVOCATION_ID} //:cpan_indexer -- \
    --lockfile e2e/deps_txt/cpan.lock.json
```

---

## Generator Metadata Schema (`generator-metadata.yaml`)

Per-module generator hints are placed in `cpan-index/modules/perl-<module-name>/generator-metadata.yaml`. The schema is strictly validated:

| Key | Type | Description |
|---|---|---|
| `is_xs` | `bool` | Explicitly declares whether module is XS/C or pure Perl |
| `native_deps` | `List[str]` | Native C/C++ Bazel dependencies (e.g. `["@openssl", "@zlib"]`) |
| `extra_deps` | `List[str]` | Extra runtime CPAN dependencies (e.g. `["@perl-encode"]`) |
| `extra_test_deps` | `List[str]` | Extra test CPAN dependencies (e.g. `["@perl-test-nowarn"]`) |
| `exported_headers` | `List[str]` | Headers to export publicly |
| `include_dirs` | `List[str]` | Additional C include paths |
| `copts` | `List[str]` | Additional compiler flags |
| `linkopts` | `List[str]` | Additional linker flags |
| `patch_cmds` | `List[str]` | Shell commands executed in extracted source before generation |
| `strip_prefix` | `str` | Explicit archive strip prefix |
| `skip_tests` | `List[str]` | Tests to omit from `test_suite` |
| `timeout_tests` | `Dict[str, str]` | Custom timeouts for specific tests |
| `replace_symbols` | `Dict[str, str]` | Header macro symbol replacements |

Any unknown keys or incorrect types cause regeneration to fail loudly.

---

## Commit Hygiene

When working on indexer or generator updates:
1. **Commit 1**: Generator code changes (`cpan/tools/indexer/...`, `tests/...`, `MODULE.bazel`, etc.).
2. **Commit 2**: Dedicated commit for regenerated `cpan-index` files.
