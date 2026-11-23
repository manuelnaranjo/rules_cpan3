# Native C/C++ System Libraries & Dependencies

Tracking document for Issue [#19](https://github.com/manuelnaranjo/rules_cpan3/issues/19): *[E2E Failures] Missing Native C/C++ System Libraries & Headers*.

## Overview

During the end-to-end evaluation of bulk CPAN packages (`e2e/deps_txt`), several XS distributions failed to build or run hermetically due to missing external native C/C++ system libraries and headers.

This document classifies all required native libraries, their availability in the public Bazel Central Registry (BCR) versus local registry (`bazel/3rdparty`), known version discrepancies, and required compatibility patches.

---

## Library Classification & Sub-Issues

### 1. Libraries Available in BCR (11 Libraries)

| Sub-Issue | Library | BCR Module | Available BCR Versions | Affected CPAN Distributions | Discrepancies & Patching Notes |
|---|---|---|---|---|---|
| [#31](https://github.com/manuelnaranjo/rules_cpan3/issues/31) | **OpenSSL** | `openssl` | 3.3.1.bcr.0–13, 3.5.x, 4.0.x | `Crypt-OpenSSL-AES`, `Crypt-OpenSSL-Bignum`, `Crypt-OpenSSL-RSA`, `Crypt-OpenSSL-Random`, `Crypt-OpenSSL-X509`, `Crypt-SMIME`, `Net-SSLeay` | Net-SSLeay 1.88 targets OpenSSL 1.0/1.1; building against OpenSSL 3.3+ fails with API deprecations and struct access errors (resolved in Net-SSLeay 1.92+). Requires backported patches or version bump. `Crypt-OpenSSL-*` requires `-DOPENSSL_SUPPRESS_DEPRECATED` or compatibility patches. |
| [#32](https://github.com/manuelnaranjo/rules_cpan3/issues/32) | **libxml2** | `libxml2` | 2.13.5, 2.14.4, 2.15.1–4 | `XML-LibXML` | XML-LibXML 2.0207 was written for libxml2 2.9/2.10. Libxml2 2.12+ in BCR changed `xmlError` and structured callback const-correctness. Needs compatibility patch or version bump. |
| [#33](https://github.com/manuelnaranjo/rules_cpan3/issues/33) | **expat** | `libexpat` | 2.7.1, 2.8.3, 2.9.0 | `XML-Parser` | Expat C API is backward-compatible. Requires build overlay or `cpan.annotation(native_deps = ["@libexpat//:expat"])`. |
| [#34](https://github.com/manuelnaranjo/rules_cpan3/issues/34) | **bzip2** | `bzip2` | 1.0.8 | `Compress-Bzip2`, `Compress-Raw-Bzip2` | BCR bzip2 1.0.8 is ABI-compatible. `Compress-Raw-Bzip2` also requires pre-copying fallback constants (`constants.h`/`constants.xs`), similar to `Compress-Raw-Zlib`. |
| [#35](https://github.com/manuelnaranjo/rules_cpan3/issues/35) | **lz4** | `lz4` | 1.9.4, 1.10.0 | `Compress-LZ4` | Compress-LZ4 0.25 bundles an obsolete internal snapshot (r119) and tries to compile `src/lz4.c` directly. Needs build overlay linking `@lz4//:lz4` and bypassing internal compilation. |
| [#36](https://github.com/manuelnaranjo/rules_cpan3/issues/36) | **snappy** | `snappy` | 1.1.8–1.2.2 | `Compress-Snappy` | BCR provides Google's C++ Snappy, whereas Compress-Snappy wraps `csnappy` (C port). Can link BCR snappy via C wrapper or provide build overlay compiling bundled csnappy cleanly. |
| [#37](https://github.com/manuelnaranjo/rules_cpan3/issues/37) | **zstd** | `zstd` | 1.5.5–1.5.7 | `Compress-Zstd` | Compress-Zstd 0.20 bundles zstd 1.4.x sources and fails because `cpan_xs` globs Linux kernel contrib headers. Linking `@zstd//:zstd` (1.5.7) via build overlay cleanly replaces bundled sources. |
| [#38](https://github.com/manuelnaranjo/rules_cpan3/issues/38) | **ncurses** | `ncurses` | 6.4.20221231, 6.6.20261024 | `Curses` | Curses 1.36 expects `c-config.h` generated at configure time. Requires build overlay with hermetic pre-generated `c-config.h` targeting `@ncurses//:ncurses`. |
| [#39](https://github.com/manuelnaranjo/rules_cpan3/issues/39) | **linux-pam** | `linux-pam` | 1.7.3 | `Authen-PAM`, `Authen-Simple-PAM` | Authen-PAM 0.16 requires configure-generated `PAM_config.h`. Needs build overlay linking `@linux-pam//:pam` and providing `PAM_config.h`. |
| [#40](https://github.com/manuelnaranjo/rules_cpan3/issues/40) | **libsodium** | `libsodium` | 1.0.19 | `Crypt-NaCl-Sodium`, `Crypt-Sodium-Nitrate` | BCR libsodium 1.0.19 is fully compatible. Packages use `Alien::Sodium`; provide `cpan.annotation(native_deps = ["@libsodium//:libsodium"])` or build overlays. |
| [#41](https://github.com/manuelnaranjo/rules_cpan3/issues/41) | **gmp** | `gmp` | 6.2.0, 6.3.0 | `Math-Prime-Util-GMP` | BCR gmp 6.3.0 is compatible. Requires `cpan.annotation(native_deps = ["@gmp//:gmp"])` and header search path mapping. |

---

### 2. Libraries Missing from BCR (5 Libraries)

These libraries are not currently present in the upstream Bazel Central Registry and need to be ported to `bazel/3rdparty/modules/`:

| Sub-Issue | Library | Target Local Module | Target Version | Affected CPAN Distributions | Porting & Patching Notes |
|---|---|---|---|---|---|
| [#42](https://github.com/manuelnaranjo/rules_cpan3/issues/42) | **CommonMark** | `cmark` | 0.29.x / 0.31.x | `CommonMark` | CommonMark 0.290000 links `-lcmark` and `#include <cmark.h>`. Port upstream GitHub `commonmark/cmark` with hermetic `cc_library`. |
| [#43](https://github.com/manuelnaranjo/rules_cpan3/issues/43) | **LibSass** | `libsass` | 3.6.5 / 3.6.6 | `CSS-Sass` | CSS-Sass 3.6.4 requires libsass C/C++ library (`sass.h`, `-lsass`). Port libsass to `bazel/3rdparty` or write build overlay for bundled sources. |
| [#44](https://github.com/manuelnaranjo/rules_cpan3/issues/44) | **Kerberos 5** | `krb5` | 1.21.x | `Authen-Krb5-Admin`, `Authen-Krb5` | Authen-Krb5-Admin 0.17 requires `krb5`, `kadm5clnt`, `k5crypto`, and `com_err` headers/libraries. Port MIT Kerberos or provide hermetic sysroot shim. |
| [#45](https://github.com/manuelnaranjo/rules_cpan3/issues/45) | **libiconv** | `libiconv` | 1.17 / 1.18 | `Text-Iconv` | On Linux host, iconv is in glibc, but on macOS and hermetic toolchains, GNU `libiconv` is required in `bazel/3rdparty`. |
| [#46](https://github.com/manuelnaranjo/rules_cpan3/issues/46) | **Discount** | `discount` | 2.2.7 | `Text-Markdown-Discount` | Text-Markdown-Discount 0.12 bundles Discount in `discount-2.X`. Port Discount to `bazel/3rdparty` or provide build overlay compiling bundled `mkdio.h` and C sources. |

---

## Packages Reclassified as Pure XS (10 Packages)

Detailed build testing revealed that 10 packages originally grouped in Issue #19 do not depend on external C/C++ system libraries:

1. **`Algorithm-Diff-XS`**: Pure XS. All unit tests build and pass hermetically out of the box.
2. **`Algorithm-Heapify-XS`**: Pure XS. Fails on modern Perl C API macro `Perl_do_ncmp` (XS Perl macro change, tracked in [#22](https://github.com/manuelnaranjo/rules_cpan3/issues/22)).
3. **`BSD-Resource`**: Pure POSIX `<sys/resource.h>`. Compiles cleanly; failure is sandbox `rlimit` environment assertions (tracked in [#23](https://github.com/manuelnaranjo/rules_cpan3/issues/23)).
4. **`CSS-Minifier-XS`**: Pure XS. Compiles and passes cleanly.
5. **`Crypt-ScryptKDF`**: Bundles scrypt source in `src/`. Fails on internal `#include "sha256.c.inc"` (textual inclusion, tracked in [#22](https://github.com/manuelnaranjo/rules_cpan3/issues/22)).
6. **`CryptX`**: Bundles LibTomCrypt/LibTomMath in `src/ltc/`. Fails on textual inclusion `#include "aes_tab.c"` (tracked in [#22](https://github.com/manuelnaranjo/rules_cpan3/issues/22)).
7. **`Text-CSV_XS`**: Pure XS. Compiles cleanly.
8. **`Text-Levenshtein-Damerau-XS`**: Pure XS. Fails on modern Clang `-Wimplicit-function-declaration` for `abs()` (tracked in [#22](https://github.com/manuelnaranjo/rules_cpan3/issues/22)).
9. **`Text-LevenshteinXS`**: Pure XS. Compiles cleanly.
10. **`Unix-Sysexits`**: Pure XS. Fails on MakeMaker dynamic constants generation (`const-c.inc`/`const-xs.inc`) (tracked in [#22](https://github.com/manuelnaranjo/rules_cpan3/issues/22)).
