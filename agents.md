# Agent Guidelines for rules_cpan3

Welcome to the `rules_cpan3` repository. This file defines repository conventions, coding standards, build and test procedures, and AI agent workflows.

## Gitignored Local Configuration
Local configurations, developer overrides, or machine-specific notes should be placed in `agents.local.md`, which is ignored by git.
If `agents.local.md` is present, agents MUST read and follow its contents as part of their instructions.

<!-- include: agents.local.md -->

## Bazel Invocation Protocol
Whenever invoking Bazel commands (`build`, `test`, `run`, `cquery`, `query`, etc.):
1. Generate an invocation ID:
   ```bash
   INVOCATION_ID=$(uuidgen)
   ```
2. Print it out:
   ```bash
   echo "Invocation ID: ${INVOCATION_ID}"
   ```
3. Pass `--invocation_id=${INVOCATION_ID}` immediately after the command:
   ```bash
   bazel <command> --invocation_id=${INVOCATION_ID} <args>
   ```

## Path Handling
- Always use relative paths relative to the repository workspace root.
- For tools executed via `bazel run`, reference files relative to `BUILD_WORKSPACE_DIRECTORY`.

## Bzlmod & Dependencies
- Strictly use Bzlmod (`MODULE.bazel`). No legacy `WORKSPACE` files.
- Native C/C++ third-party dependencies are ported into the local BCR registry at `bazel/3rdparty` if not present in the upstream BCR.

## Pre-commit Verification
- Always run `pre-commit run --all-files` before each commit to verify and enforce formatting (Buildifier), script executable permissions, trailing whitespace, and file endings.
