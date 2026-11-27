# Makefile for rules_cpan3
# Reproduces repository CI workflows: pre-commit checks, full builds, and tests across all workspaces.

SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c

BAZEL ?= bazel
PRE_COMMIT ?= pre-commit
BAZEL_FLAGS ?=

# BuildBuddy RBE configuration: automatically activate --config=rbe if BB_TOKEN is present in env
ifneq ($(strip $(BB_TOKEN)),)
  BAZEL_CONFIG ?= --config=rbe
else
  BAZEL_CONFIG ?=
endif

# Root workspace flags: apply --config=ci if running in CI environment
ROOT_FLAGS ?=
ifneq ($(strip $(CI)),)
  ROOT_FLAGS := --config=ci
endif

# Macro to invoke Bazel adhering to repository Invocation ID Protocol
define run_bazel
	@set -e; \
	INV_ID=$$($(BAZEL_UUID_GEN)); \
	echo "Invocation ID: $$INV_ID"; \
	echo "Running: $(BAZEL) $(2) in $(1)"; \
	(cd $(1) && $(BAZEL) $(2) --invocation_id="$$INV_ID" $(BAZEL_CONFIG) $(3) $(BAZEL_FLAGS) $(4))
endef

BAZEL_UUID_GEN := uuidgen 2>/dev/null || cat /proc/sys/kernel/random/uuid 2>/dev/null || python3 -c 'import uuid; print(uuid.uuid4())'

.DEFAULT_GOAL := all

.PHONY: all ci build test pre-commit lint format clean help \
	build-root build-smoke build-pakket build-deps-txt \
	test-root test-smoke test-pakket test-deps-txt \
	clean-root clean-smoke clean-pakket clean-deps-txt \
	check-cpan-index update-cpan-index

## ----------------------------------------------------------------------
## Top-Level Targets
## ----------------------------------------------------------------------

# The default target runs full pre-commit verification, full build, and tests
all: pre-commit build test

# Alias for CI workflow reproduction
ci: pre-commit build test

# Build all workspaces: root and end-to-end suites
build: build-root build-smoke build-pakket build-deps-txt

# Test all workspaces: root and end-to-end suites
test: test-root test-smoke test-pakket test-deps-txt

# Pre-commit checks (formatting, buildifier, linting, git hygiene)
pre-commit:
	@echo "Running pre-commit checks..."
	$(PRE_COMMIT) run --all-files

lint: pre-commit
format: pre-commit

## ----------------------------------------------------------------------
## Root Workspace Targets (.)
## ----------------------------------------------------------------------

build-root:
	$(call run_bazel,.,build,$(ROOT_FLAGS),//...)

test-root:
	$(call run_bazel,.,test,$(ROOT_FLAGS),//...)

clean-root:
	$(call run_bazel,.,clean,,)

check-cpan-index:
	$(call run_bazel,.,run,$(ROOT_FLAGS),//:cpan_indexer -- --check --all --lockfile e2e/deps_txt/cpan.lock.json --lockfile e2e/pakket/cpan.lock.json --lockfile tests/cpan.lock.json)

update-cpan-index:
	$(call run_bazel,.,run,$(ROOT_FLAGS),//:cpan_indexer -- --regenerate --all --lockfile e2e/deps_txt/cpan.lock.json --lockfile e2e/pakket/cpan.lock.json --lockfile tests/cpan.lock.json)

## ----------------------------------------------------------------------
## End-to-End: Smoke Test Workspace (e2e/smoke)
## ----------------------------------------------------------------------

build-smoke:
	$(call run_bazel,e2e/smoke,build,,//...)

test-smoke:
	$(call run_bazel,e2e/smoke,test,,//...)

clean-smoke:
	$(call run_bazel,e2e/smoke,clean,,)

## ----------------------------------------------------------------------
## End-to-End: Pakket Test Workspace (e2e/pakket)
## ----------------------------------------------------------------------

build-pakket:
	$(call run_bazel,e2e/pakket,build,,//...)

test-pakket:
	$(call run_bazel,e2e/pakket,test,,//...)

clean-pakket:
	$(call run_bazel,e2e/pakket,clean,,)

## ----------------------------------------------------------------------
## End-to-End: Deps Txt Test Workspace (e2e/deps_txt)
## ----------------------------------------------------------------------

build-deps-txt:
	$(call run_bazel,e2e/deps_txt,build,,//...)

test-deps-txt:
	$(call run_bazel,e2e/deps_txt,test,,//...)

clean-deps-txt:
	$(call run_bazel,e2e/deps_txt,clean,,)

## ----------------------------------------------------------------------
## Cleanup
## ----------------------------------------------------------------------

clean: clean-root clean-smoke clean-pakket clean-deps-txt

## ----------------------------------------------------------------------
## Help
## ----------------------------------------------------------------------

help:
	@echo "Available targets in rules_cpan3 Makefile:"
	@echo "  all              Run pre-commit checks, full build, and test across all workspaces"
	@echo "  ci               Reproduce CI pipeline (pre-commit, build, test)"
	@echo "  build            Build all workspaces (root, smoke, pakket, deps_txt)"
	@echo "  test             Run all tests across all workspaces"
	@echo "  pre-commit       Run pre-commit hooks (buildifier, lint, formatting)"
	@echo "  clean            Clean build outputs across all workspaces"
	@echo "  check-cpan-index Verify that cpan-index is up to date and idempotent"
	@echo "  update-cpan-index Regenerate all cpan-index ports with explicit lockfiles"
	@echo ""
	@echo "Workspace-specific build targets:"
	@echo "  build-root       Build root workspace (//...)"
	@echo "  build-smoke      Build e2e/smoke workspace (//...)"
	@echo "  build-pakket     Build e2e/pakket workspace (//...)"
	@echo "  build-deps-txt   Build e2e/deps_txt workspace (//...)"
	@echo ""
	@echo "Workspace-specific test targets:"
	@echo "  test-root        Test root workspace (//...)"
	@echo "  test-smoke       Test e2e/smoke workspace (//...)"
	@echo "  test-pakket      Test e2e/pakket workspace (//...)"
	@echo "  test-deps-txt    Test e2e/deps_txt workspace (//...)"
	@echo ""
	@echo "Variables:"
	@echo "  BAZEL            Bazel executable (default: bazel)"
	@echo "  BAZEL_FLAGS      Additional flags passed to bazel commands"
	@echo "  BAZEL_CONFIG     Bazel config to use (default: --config=rbe if BB_TOKEN set)"
	@echo "  PRE_COMMIT       Pre-commit executable (default: pre-commit)"
