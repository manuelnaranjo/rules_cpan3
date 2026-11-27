#!/usr/bin/env python3
"""Comprehensive unit and integration test suite for rules_cpan out-of-build indexer."""

import base64
import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from cpan.tools.indexer.heuristics import (
    DistributionInspection,
    GeneratorMetadata,
    HeuristicsEngine,
    compute_output_loc,
    compute_sri_hash,
    hex_to_sri,
    is_manual_test,
    sanitize_module_name,
)
from cpan.tools.indexer.indexer import (
    CPANIndexer,
    IndexManager,
    IndexResolution,
    parse_args,
    regenerate_modules,
    sync_workspace_module_bazel,
)


class HeuristicsEngineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.heuristics = HeuristicsEngine()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.work_dir = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_sri_and_module_naming(self) -> None:
        data = b"Hello world for SRI test"
        expected_digest = hashlib.sha256(data).digest()
        expected_sri = f"sha256-{base64.b64encode(expected_digest).decode('ascii')}"

        self.assertEqual(compute_sri_hash(data), expected_sri)

        hex_sha = hashlib.sha256(data).hexdigest()
        self.assertEqual(hex_to_sri(hex_sha), expected_sri)

        self.assertEqual(sanitize_module_name("Algorithm-Diff"), "perl-algorithm-diff")
        self.assertEqual(sanitize_module_name("Compress-Raw-Zlib"), "perl-compress-raw-zlib")
        self.assertEqual(sanitize_module_name("IO_Tty"), "perl-io-tty")
        self.assertEqual(sanitize_module_name("Text::CSV_XS"), "perl-text-csv-xs")

    def test_compute_output_loc(self) -> None:
        self.assertEqual(
            compute_output_loc("Algorithm-Diff", ["Algorithm::Diff"]),
            "auto/Algorithm/Diff/Diff",
        )
        self.assertEqual(
            compute_output_loc("Compress-Raw-Zlib", ["Compress::Raw::Zlib"]),
            "auto/Compress/Raw/Zlib/Zlib",
        )
        self.assertEqual(
            compute_output_loc("IO-Tty", ["IO::Tty", "IO::Pty"]),
            "auto/IO/Tty/Tty",
        )

    def test_pure_perl_inspection(self) -> None:
        dist_dir = self.work_dir / "Algorithm-Diff-1.201"
        dist_dir.mkdir(parents=True)
        lib_dir = dist_dir / "lib" / "Algorithm"
        lib_dir.mkdir(parents=True)
        (lib_dir / "Diff.pm").write_text("package Algorithm::Diff;\nour $VERSION = '1.201';\n1;\n")
        (dist_dir / "Makefile.PL").write_text("use ExtUtils::MakeMaker;\nWriteMakefile(NAME => 'Algorithm::Diff');\n")

        # Test files in t/
        t_dir = dist_dir / "t"
        t_dir.mkdir(parents=True)
        (t_dir / "01_basic.t").write_text("use Test::More; pass('ok'); done_testing();\n")
        (t_dir / "diff.t").write_text("use Test::More; pass('ok'); done_testing();\n")

        inspection = self.heuristics.inspect_directory(
            extract_dir=dist_dir,
            dist_name="Algorithm-Diff",
            provides=["Algorithm::Diff"],
        )

        self.assertFalse(inspection.is_xs)
        self.assertEqual(inspection.output_loc, "auto/Algorithm/Diff/Diff")
        self.assertEqual(inspection.t_files, ["t/01_basic.t", "t/diff.t"])
        self.assertNotIn("_test_runner.pl", inspection.overlay_files)

        build_bazel = self.heuristics.generate_build_bazel(
            inspection=inspection,
            module_name="perl-algorithm-diff",
            runtime_deps=[],
        )
        self.assertIn('name = "Algorithm-Diff"', build_bazel)
        self.assertIn('alias(\n    name = "perl-algorithm-diff",\n    actual = ":Algorithm-Diff",\n)', build_bazel)
        self.assertNotIn("cpan_xs", build_bazel)

        # Test targets generation
        self.assertIn('load("@rules_perl//perl:defs.bzl", "perl_library", "perl_test")', build_bazel)
        self.assertIn('name = "Algorithm-Diff_test_lib"', build_bazel)
        self.assertIn('name = "test_t_01_basic"', build_bazel)
        self.assertIn('name = "test_t_diff"', build_bazel)
        self.assertIn('srcs = ["@rules_cpan//cpan:test_runner.pl"]', build_bazel)
        self.assertIn('includes = ["t", "t/lib"]', build_bazel)
        self.assertIn('includes = [\n        "lib",\n    ]', build_bazel)
        self.assertIn('test_suite(\n    name = "test",\n    tests = [\n        ":test_t_01_basic",\n        ":test_t_diff",\n    ],', build_bazel)

    def test_xs_inspection_and_dynamic_constants(self) -> None:
        dist_dir = self.work_dir / "Sample-XS-0.01"
        dist_dir.mkdir(parents=True)

        # Top-level XS file
        (dist_dir / "Sample.xs").write_text("""
#include "EXTERN.h"
#include "perl.h"
#include "XSUB.h"
#include "ppport.h"
#include "helper.c"

INCLUDE: constants.xs

MODULE = Sample::XS PACKAGE = Sample::XS
PROTOTYPES: ENABLE
int sample_func()
    CODE:
        RETVAL = 42;
    OUTPUT:
        RETVAL
""")
        # Included fragment XS and C files
        (dist_dir / "constants.xs").write_text("/* fragment xs without MODULE */\n")
        (dist_dir / "helper.c").write_text("int helper_val = 1;\n")
        (dist_dir / "ppport.h").write_text("/* ppport */\n")
        (dist_dir / "typemap").write_text("TYPEMAP\n")

        # Fallback constants
        fallback_dir = dist_dir / "fallback"
        fallback_dir.mkdir(parents=True)
        (fallback_dir / "constants.h").write_text("#define SAMPLE_CONST 100\n")
        (fallback_dir / "constants.xs").write_text("/* fallback xs */\n")

        # Makefile.PL with native lib flag
        (dist_dir / "Makefile.PL").write_text("""
use ExtUtils::MakeMaker;
WriteMakefile(
    NAME => 'Sample::XS',
    LIBS => ['-lz -lyaml'],
    DEFINE => '-DSAMPLE_OPT',
);
""")

        inspection = self.heuristics.inspect_directory(
            extract_dir=dist_dir,
            dist_name="Sample-XS",
            provides=["Sample::XS"],
        )

        self.assertTrue(inspection.is_xs)
        self.assertIn("Sample.xs", inspection.top_level_xs)
        self.assertIn("helper.c", inspection.included_c_files)
        self.assertIn("typemap", inspection.typemaps)
        self.assertIn("@zlib", inspection.native_deps)
        self.assertIn("@libyaml", inspection.native_deps)
        self.assertIn("SAMPLE_OPT", inspection.defines)

        # Dynamic fallback constants should be tracked as file copies
        self.assertIn(("fallback/constants.h", "constants.h"), inspection.file_copies)
        self.assertIn(("fallback/constants.xs", "constants.xs"), inspection.file_copies)
        self.assertNotIn("constants.h", inspection.overlay_files)
        self.assertNotIn("constants.xs", inspection.overlay_files)

        build_bazel = self.heuristics.generate_build_bazel(
            inspection=inspection,
            module_name="perl-sample-xs",
            runtime_deps=[],
        )
        self.assertIn("cpan_xs(", build_bazel)
        self.assertIn('name = "Sample-XS_xs"', build_bazel)
        self.assertIn('"Sample.xs"', build_bazel)
        self.assertIn('"helper.c"', build_bazel)  # Excluded from cc_srcs because it's included
        self.assertIn('"@zlib"', build_bazel)
        self.assertIn('"@libyaml"', build_bazel)
        self.assertIn('name = "perl-sample-xs"', build_bazel)

    def test_wrap_constants_in_ifdef(self) -> None:
        raw_c = """
newCONSTSUB(stash, "TIOCGWINSZ", newSViv(TIOCGWINSZ));
newCONSTSUB(stash, "TIOCNOTTY", newSViv(TIOCNOTTY));
"""
        wrapped = self.heuristics.wrap_constants_in_ifdef(raw_c)
        self.assertIn("#ifdef TIOCGWINSZ\nnewCONSTSUB(stash, \"TIOCGWINSZ\", newSViv(TIOCGWINSZ));\n#else\nnewCONSTSUB(stash, \"TIOCGWINSZ\", newSV(0));\n#endif", wrapped)
        self.assertIn("#ifdef TIOCNOTTY\nnewCONSTSUB(stash, \"TIOCNOTTY\", newSViv(TIOCNOTTY));\n#else\nnewCONSTSUB(stash, \"TIOCNOTTY\", newSV(0));\n#endif", wrapped)

    def test_is_manual_test(self) -> None:
        patterns = ["t/85gofer.t", "t/20-modules/*", "foo.t"]
        self.assertTrue(is_manual_test("t/85gofer.t", patterns))
        self.assertTrue(is_manual_test("t/20-modules/sub.t", patterns))
        self.assertTrue(is_manual_test("t/foo.t", patterns))
        self.assertFalse(is_manual_test("t/01basic.t", patterns))
        self.assertTrue(is_manual_test("t/anything.t", ["*"]))

    def test_generator_metadata_build_bazel(self) -> None:
        meta = GeneratorMetadata(
            manual_tests=["t/broken.t"],
            test_services=["redis"],
            test_exec_properties={"workload-isolation-type": "firecracker"},
            defines=["CUSTOM_FLAG"],
            includes=["custom/include"],
            output_loc="auto/My/Mod/Mod",
            target_compatible_with=["@platforms//os:linux"],
            exec_compatible_with=["@platforms//os:linux"],
            execution_requirements={"no-remote": "1"},
        )
        inspection = DistributionInspection(
            dist_name="My-Mod",
            is_xs=True,
            top_level_xs=["Mod.xs"],
            t_files=["t/ok.t", "t/broken.t"],
        )
        content = self.heuristics.generate_build_bazel(
            inspection=inspection,
            module_name="perl-my-mod",
            generator_metadata=meta,
        )
        self.assertIn('CUSTOM_FLAG', content)
        self.assertIn('"custom/include"', content)
        self.assertIn('output_loc = "auto/My/Mod/Mod"', content)
        self.assertIn('target_compatible_with = ["@platforms//os:linux"]', content)
        self.assertIn('--service=redis', content)
        self.assertIn('"init-dockerd": "true"', content)
        self.assertIn('name = "test_t_broken"', content)
        self.assertIn('tags = ["manual", "no-remote"]', content)
        # Verify test_suite only has non-manual tests
        self.assertIn('":test_t_ok"', content)
        self.assertNotIn('":test_t_broken"', content.split('name = "test"')[1])


class IndexManagerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.index_dir = Path(self.temp_dir.name) / "cpan-index"
        self.index_dir.mkdir(parents=True)
        (self.index_dir / "bazel_registry.json").write_text("{}", encoding="utf-8")
        self.manager = IndexManager(self.index_dir)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_resolve_new_distribution(self) -> None:
        res = self.manager.resolve("Algorithm-Diff", "1.201")
        self.assertEqual(res.status, "NEW_DISTRIBUTION")
        self.assertEqual(res.module_name, "perl-algorithm-diff")
        self.assertEqual(res.target_version, "1.201.cpan1")

    def test_resolve_exact_match(self) -> None:
        mod_dir = self.index_dir / "modules" / "perl-compress-raw-zlib"
        v_dir = mod_dir / "2.226.cpan1"
        v_dir.mkdir(parents=True)
        (mod_dir / "metadata.json").write_text(json.dumps({
            "homepage": "https://metacpan.org/dist/Compress-Raw-Zlib",
            "versions": ["2.226.cpan1"],
        }), encoding="utf-8")

        res = self.manager.resolve("Compress-Raw-Zlib", "2.226")
        self.assertEqual(res.status, "EXACT_MATCH")
        self.assertEqual(res.matched_version, "2.226.cpan1")

    def test_resolve_older_version_exists(self) -> None:
        mod_dir = self.index_dir / "modules" / "perl-compress-raw-zlib"
        v_dir = mod_dir / "2.226.cpan1"
        v_dir.mkdir(parents=True)
        (mod_dir / "metadata.json").write_text(json.dumps({
            "homepage": "https://metacpan.org/dist/Compress-Raw-Zlib",
            "versions": ["2.226.cpan1"],
        }), encoding="utf-8")

        res = self.manager.resolve("Compress-Raw-Zlib", "2.227")
        self.assertEqual(res.status, "OLDER_VERSION_EXISTS")
        self.assertEqual(res.source_template_version, "2.226.cpan1")
        self.assertEqual(res.target_version, "2.227.cpan1")

    def test_refactor_older_version(self) -> None:
        mod_dir = self.index_dir / "modules" / "perl-algorithm-diff"
        src_v_dir = mod_dir / "1.19.cpan1"
        src_overlay = src_v_dir / "overlay"
        src_overlay.mkdir(parents=True)

        (src_v_dir / "MODULE.bazel").write_text("""module(
    name = "perl-algorithm-diff",
    version = "1.19.cpan1",
)
bazel_dep(name = "rules_perl", version = "2.1.0")
""", encoding="utf-8")

        (src_overlay / "BUILD.bazel").write_text("""# Build file for Algorithm-Diff
perl_library(name = "Algorithm-Diff")
""", encoding="utf-8")

        (mod_dir / "metadata.json").write_text(json.dumps({
            "homepage": "https://metacpan.org/dist/Algorithm-Diff",
            "versions": ["1.19.cpan1"],
        }), encoding="utf-8")

        dummy_sha256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        dest_dir = self.manager.refactor_older_version(
            module_name="perl-algorithm-diff",
            dist_name="Algorithm-Diff",
            source_version="1.19.cpan1",
            target_version="1.201.cpan1",
            upstream_version="1.201",
            archive_url="https://cpan.metacpan.org/authors/id/R/RJ/RJBS/Algorithm-Diff-1.201.tar.gz",
            archive_sha256=dummy_sha256,
        )

        self.assertTrue(dest_dir.exists())
        self.assertTrue((dest_dir / "overlay" / "BUILD.bazel").exists())

        # Check updated MODULE.bazel
        dest_mod = (dest_dir / "MODULE.bazel").read_text(encoding="utf-8")
        self.assertIn('version = "1.201.cpan1"', dest_mod)

        # Check updated source.json
        source_json = json.loads((dest_dir / "source.json").read_text(encoding="utf-8"))
        self.assertEqual(source_json["strip_prefix"], "Algorithm-Diff-1.201")
        self.assertEqual(source_json["integrity"], hex_to_sri(dummy_sha256))
        self.assertIn("BUILD.bazel", source_json["overlay"])

        # Check metadata.json
        meta = json.loads((mod_dir / "metadata.json").read_text(encoding="utf-8"))
        self.assertIn("1.201.cpan1", meta["versions"])

    def test_bump_build_id(self) -> None:
        mod_dir = self.index_dir / "modules" / "perl-compress-raw-zlib"
        v_dir = mod_dir / "2.226.cpan1"
        (v_dir / "overlay").mkdir(parents=True)
        (v_dir / "MODULE.bazel").write_text('module(name = "perl-compress-raw-zlib", version = "2.226.cpan1")\n', encoding="utf-8")
        (mod_dir / "metadata.json").write_text(json.dumps({
            "homepage": "https://metacpan.org/dist/Compress-Raw-Zlib",
            "versions": ["2.226.cpan1"],
        }), encoding="utf-8")

        new_ver = self.manager.bump_build_id("perl-compress-raw-zlib", "2.226")
        self.assertEqual(new_ver, "2.226.cpan2")
        self.assertTrue((mod_dir / "2.226.cpan2" / "MODULE.bazel").exists())
        self.assertFalse((mod_dir / "2.226.cpan1").exists())

        meta = json.loads((mod_dir / "metadata.json").read_text(encoding="utf-8"))
        self.assertEqual(meta["versions"], ["2.226.cpan2"])


class WorkspaceSyncTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.mb_path = Path(self.temp_dir.name) / "MODULE.bazel"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_sync_workspace_module_bazel(self) -> None:
        initial_content = """module(name = "my_workspace")

bazel_dep(name = "rules_cpan", version = "0.0.0")
bazel_dep(name = "perl-compress-raw-zlib", version = "2.226.cpan1")
bazel_dep(name = "rules_perl", version = "2.1.0")
"""
        self.mb_path.write_text(initial_content, encoding="utf-8")

        deps_to_sync = {
            "perl-compress-raw-zlib": "2.226.cpan2",  # Updated existing
            "perl-algorithm-diff": "1.201.cpan1",     # Brand new
        }

        modified = sync_workspace_module_bazel(self.mb_path, deps_to_sync)
        self.assertTrue(modified)

        updated_text = self.mb_path.read_text(encoding="utf-8")
        self.assertIn('bazel_dep(name = "perl-compress-raw-zlib", version = "2.226.cpan2")', updated_text)
        self.assertIn('bazel_dep(name = "perl-algorithm-diff", version = "1.201.cpan1")', updated_text)
        self.assertIn('bazel_dep(name = "rules_perl", version = "2.1.0")', updated_text)


class CPANIndexerIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root_path = Path(self.temp_dir.name)
        self.index_dir = self.root_path / "cpan-index"
        self.index_dir.mkdir(parents=True)
        (self.index_dir / "bazel_registry.json").write_text("{}", encoding="utf-8")

        self.mb_path = self.root_path / "MODULE.bazel"
        self.mb_path.write_text('module(name = "test_workspace")\n', encoding="utf-8")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_index_lockfile_with_mocked_ports(self) -> None:
        lock_file = self.root_path / "cpan.lock.json"
        lock_content = {
            "lock_version": "1.0.0",
            "root_dependencies": [
                "Algorithm-Diff 1.201",
            ],
            "distributions": {
                "Algorithm-Diff": {
                    "version": "1.201",
                    "url": "https://cpan.metacpan.org/authors/id/R/RJ/RJBS/Algorithm-Diff-1.201.tar.gz",
                    "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                    "is_xs": False,
                    "provides": ["Algorithm::Diff"],
                    "dependencies": {"runtime": []},
                }
            },
        }
        lock_file.write_text(json.dumps(lock_content), encoding="utf-8")

        indexer = CPANIndexer(
            index_dir=self.index_dir,
            workspace_dir=self.root_path,
        )

        # Mock download/extraction in create_new_port to avoid network call in unit test
        with patch.object(IndexManager, "create_new_port") as mock_create:
            mock_create.return_value = self.index_dir / "modules" / "perl-algorithm-diff" / "1.201.cpan1"
            resolved = indexer.index_lockfile(
                lockfile_path=lock_file,
                sync_module_bazel=True,
                module_bazel_path=self.mb_path,
            )

            mock_create.assert_called_once()
            self.assertEqual(resolved.get("perl-algorithm-diff"), "1.201.cpan1")

            # Verify MODULE.bazel was updated with root dependency
            mb_text = self.mb_path.read_text(encoding="utf-8")
            self.assertIn('bazel_dep(name = "perl-algorithm-diff", version = "1.201.cpan1")', mb_text)

    def test_create_new_port_preserves_archive_prefix_case(self) -> None:
        """Verifies that create_new_port preserves directory casing from the actual archive."""
        import io
        import tarfile

        # Create a synthetic tarball with uppercase prefix
        tar_buf = io.BytesIO()
        with tarfile.open(fileobj=tar_buf, mode="w:gz") as tar:
            ti = tarfile.TarInfo("Grpc-XS-0.38/lib/Grpc/XS.pm")
            content = b"package Grpc::XS;\nour $VERSION = '0.38';\n1;\n"
            ti.size = len(content)
            tar.addfile(ti, io.BytesIO(content))

        tar_bytes = tar_buf.getvalue()
        tar_path = self.root_path / "grpc-xs-0.38.tar.gz"
        tar_path.write_bytes(tar_bytes)

        manager = IndexManager(index_dir=self.index_dir)
        dest_dir = manager.create_new_port(
            dist_name="grpc-xs",
            upstream_version="0.38",
            archive_url="https://cpan.metacpan.org/authors/id/J/JO/JOYREX/grpc-xs-0.38.tar.gz",
            archive_sha256="",
            archive_path=tar_path,
            target_version="0.38.cpan1",
        )

        source_json = json.loads((dest_dir / "source.json").read_text(encoding="utf-8"))
        self.assertEqual(source_json["strip_prefix"], "Grpc-XS-0.38")

    def test_generate_build_bazel_includes_cpan_runtime_deps(self) -> None:
        """Verifies that generate_build_bazel adds CPAN lockfile runtime dependencies to perl_library."""
        inspection = DistributionInspection(
            dist_name="My-Module",
            is_xs=False,
            output_loc="auto/My/Module/Module",
            t_files=[],
        )
        engine = HeuristicsEngine()
        build_bazel = engine.generate_build_bazel(
            inspection=inspection,
            module_name="perl-my-module",
            runtime_deps=["Class-Load", "File-ShareDir", ":local_lib", "@custom//:dep"],
        )
        self.assertIn('name = "My-Module"', build_bazel)
        self.assertIn('":local_lib"', build_bazel)
        self.assertIn('"@custom//:dep"', build_bazel)
        self.assertIn('"@perl-class-load"', build_bazel)
        self.assertIn('"@perl-file-sharedir"', build_bazel)
        self.assertNotIn('"@perl-my-module"', build_bazel)

    def test_generate_build_bazel_includes_cpan_test_deps(self) -> None:
        """Verifies that generate_build_bazel adds CPAN lockfile test dependencies to test_lib."""
        inspection = DistributionInspection(
            dist_name="My-Module",
            is_xs=False,
            output_loc="auto/My/Module/Module",
            t_files=["t/01_test.t"],
        )
        engine = HeuristicsEngine()
        build_bazel = engine.generate_build_bazel(
            inspection=inspection,
            module_name="perl-my-module",
            test_deps=["Test-Exception", "Test-Deep", "My-Module", ":extra_lib", "@custom//:dep"],
        )
        self.assertIn('name = "My-Module_test_lib"', build_bazel)
        self.assertIn('":extra_lib"', build_bazel)
        self.assertIn('"@custom//:dep"', build_bazel)
        self.assertIn('"@perl-test-deep"', build_bazel)
        self.assertIn('"@perl-test-exception"', build_bazel)
        self.assertNotIn('"@perl-my-module"', build_bazel)

    def test_create_and_regenerate_port_with_lockfile_test_deps(self) -> None:
        """Verifies that create_new_port and regenerate_port wire test dependencies from lockfile."""
        import io
        import tarfile

        tar_buf = io.BytesIO()
        with tarfile.open(fileobj=tar_buf, mode="w:gz") as tar:
            ti = tarfile.TarInfo("Sample-Dist-1.00/lib/Sample/Dist.pm")
            content = b"package Sample::Dist;\nour $VERSION = '1.00';\n1;\n"
            ti.size = len(content)
            tar.addfile(ti, io.BytesIO(content))

            ti_t = tarfile.TarInfo("Sample-Dist-1.00/t/test.t")
            content_t = b"use Test::More;\nplan tests => 1;\nok(1);\n"
            ti_t.size = len(content_t)
            tar.addfile(ti_t, io.BytesIO(content_t))

        tar_bytes = tar_buf.getvalue()
        tar_path = self.root_path / "sample-dist-1.00.tar.gz"
        tar_path.write_bytes(tar_bytes)

        # Create metadata for dependency
        dep_dir = self.index_dir / "modules" / "perl-test-exception"
        dep_dir.mkdir(parents=True, exist_ok=True)
        (dep_dir / "metadata.json").write_text(json.dumps({"versions": ["0.43.cpan1"]}), encoding="utf-8")

        lockfile = self.root_path / "cpan.lock.json"
        lockfile.write_text(
            json.dumps({
                "distributions": {
                    "Sample-Dist": {
                        "dependencies": {
                            "runtime": [],
                            "test": ["Test-Exception"],
                        },
                        "version": "1.00",
                        "url": tar_path.as_uri(),
                    }
                }
            }),
            encoding="utf-8",
        )

        manager = IndexManager(index_dir=self.index_dir)
        manager.load_lockfile(lockfile)
        dest_dir = manager.create_new_port(
            dist_name="Sample-Dist",
            upstream_version="1.00",
            archive_url=tar_path.as_uri(),
            archive_sha256="",
            archive_path=tar_path,
            target_version="1.00.cpan1",
        )

        build_text = (dest_dir / "overlay" / "BUILD.bazel").read_text(encoding="utf-8")
        self.assertIn('"@perl-test-exception"', build_text)
        mb_text = (dest_dir / "MODULE.bazel").read_text(encoding="utf-8")
        self.assertIn('bazel_dep(name = "perl-test-exception", version = "0.43.cpan1")', mb_text)

        # Now test regenerate_port in place
        (dest_dir.parent / "metadata.json").write_text(json.dumps({"versions": ["1.00.cpan1"]}), encoding="utf-8")
        regen_ver = manager.regenerate_port("perl-sample-dist", bump_build_id=False)
        self.assertEqual(regen_ver, "1.00.cpan1")
        build_text_regen = (dest_dir / "overlay" / "BUILD.bazel").read_text(encoding="utf-8")
        self.assertIn('"@perl-test-exception"', build_text_regen)
        mb_text_regen = (dest_dir / "MODULE.bazel").read_text(encoding="utf-8")
        self.assertIn('bazel_dep(name = "perl-test-exception", version = "0.43.cpan1")', mb_text_regen)

    def test_create_and_regenerate_port_with_lockfile_runtime_deps(self) -> None:
        """Verifies that create_new_port and regenerate_port wire runtime dependencies from lockfile."""
        import io
        import tarfile

        tar_buf = io.BytesIO()
        with tarfile.open(fileobj=tar_buf, mode="w:gz") as tar:
            ti = tarfile.TarInfo("Sample-Runtime-1.00/lib/Sample/Runtime.pm")
            content = b"package Sample::Runtime;\nour $VERSION = '1.00';\n1;\n"
            ti.size = len(content)
            tar.addfile(ti, io.BytesIO(content))

        tar_bytes = tar_buf.getvalue()
        tar_path = self.root_path / "sample-runtime-1.00.tar.gz"
        tar_path.write_bytes(tar_bytes)

        # Create metadata for dependencies
        dep_dir1 = self.index_dir / "modules" / "perl-class-load"
        dep_dir1.mkdir(parents=True, exist_ok=True)
        (dep_dir1 / "metadata.json").write_text(json.dumps({"versions": ["0.25.cpan1"]}), encoding="utf-8")

        lockfile = self.root_path / "cpan.lock.json"
        lockfile.write_text(
            json.dumps({
                "distributions": {
                    "Sample-Runtime": {
                        "dependencies": {
                            "runtime": ["Class-Load"],
                            "test": [],
                        },
                        "version": "1.00",
                        "url": tar_path.as_uri(),
                    }
                }
            }),
            encoding="utf-8",
        )

        manager = IndexManager(index_dir=self.index_dir)
        manager.load_lockfile(lockfile)
        dest_dir = manager.create_new_port(
            dist_name="Sample-Runtime",
            upstream_version="1.00",
            archive_url=tar_path.as_uri(),
            archive_sha256="",
            archive_path=tar_path,
            target_version="1.00.cpan1",
        )

        build_text = (dest_dir / "overlay" / "BUILD.bazel").read_text(encoding="utf-8")
        self.assertIn('"@perl-class-load"', build_text)
        mb_text = (dest_dir / "MODULE.bazel").read_text(encoding="utf-8")
        self.assertIn('bazel_dep(name = "perl-class-load", version = "0.25.cpan1")', mb_text)

        # Test regenerate_port in place
        (dest_dir.parent / "metadata.json").write_text(json.dumps({"versions": ["1.00.cpan1"]}), encoding="utf-8")
        regen_ver = manager.regenerate_port("perl-sample-runtime", bump_build_id=False)
        self.assertEqual(regen_ver, "1.00.cpan1")
        build_text_regen = (dest_dir / "overlay" / "BUILD.bazel").read_text(encoding="utf-8")
        self.assertIn('"@perl-class-load"', build_text_regen)
        mb_text_regen = (dest_dir / "MODULE.bazel").read_text(encoding="utf-8")
        self.assertIn('bazel_dep(name = "perl-class-load", version = "0.25.cpan1")', mb_text_regen)


    def test_generate_build_bazel_includes_custom_directories(self) -> None:
        """Verifies that generate_build_bazel globs custom includes in srcs and data."""
        inspection = DistributionInspection(
            dist_name="YAML-LibYAML",
            is_xs=True,
            output_loc="auto/YAML/XS/LibYAML/LibYAML",
            t_files=[],
        )
        metadata = GeneratorMetadata(
            includes=["LibYAML/lib"],
        )
        engine = HeuristicsEngine()
        build_bazel = engine.generate_build_bazel(
            inspection=inspection,
            module_name="perl-yaml-libyaml",
            generator_metadata=metadata,
        )
        self.assertIn('"LibYAML/lib/**/*.pm"', build_bazel)
        self.assertIn('"LibYAML/lib/**/*.pod"', build_bazel)
        self.assertIn('"LibYAML/lib/**/*"', build_bazel)
        self.assertIn('"LibYAML/lib"', build_bazel)

    def test_parse_args_jobs_and_all(self) -> None:
        """Verifies that parse_args defaults --jobs to all CPU cores and accepts custom values."""
        import os
        args_default = parse_args([])
        self.assertEqual(args_default.jobs, os.cpu_count() or 1)
        self.assertFalse(args_default.all)

        args_custom = parse_args(["-j", "4", "--all"])
        self.assertEqual(args_custom.jobs, 4)
        self.assertTrue(args_custom.all)

        args_long = parse_args(["--jobs", "8"])
        self.assertEqual(args_long.jobs, 8)

    def test_regenerate_modules_parallel_and_resilience(self) -> None:
        """Verifies parallel regeneration of modules across worker threads."""
        import io
        import tarfile

        # Create two sample tarballs
        tar1_buf = io.BytesIO()
        with tarfile.open(fileobj=tar1_buf, mode="w:gz") as tar:
            ti = tarfile.TarInfo("Sample-One-1.00/lib/Sample/One.pm")
            content = b"package Sample::One;\nour $VERSION = '1.00';\n1;\n"
            ti.size = len(content)
            tar.addfile(ti, io.BytesIO(content))
        tar1_path = self.root_path / "sample-one-1.00.tar.gz"
        tar1_path.write_bytes(tar1_buf.getvalue())

        tar2_buf = io.BytesIO()
        with tarfile.open(fileobj=tar2_buf, mode="w:gz") as tar:
            ti = tarfile.TarInfo("Sample-Two-2.00/lib/Sample/Two.pm")
            content = b"package Sample::Two;\nour $VERSION = '2.00';\n1;\n"
            ti.size = len(content)
            tar.addfile(ti, io.BytesIO(content))
        tar2_path = self.root_path / "sample-two-2.00.tar.gz"
        tar2_path.write_bytes(tar2_buf.getvalue())

        manager = IndexManager(index_dir=self.index_dir)
        d1 = manager.create_new_port(
            dist_name="Sample-One",
            upstream_version="1.00",
            archive_url=tar1_path.as_uri(),
            archive_sha256="",
            archive_path=tar1_path,
            target_version="1.00.cpan1",
        )
        (d1.parent / "metadata.json").write_text(json.dumps({"versions": ["1.00.cpan1"]}), encoding="utf-8")

        d2 = manager.create_new_port(
            dist_name="Sample-Two",
            upstream_version="2.00",
            archive_url=tar2_path.as_uri(),
            archive_sha256="",
            archive_path=tar2_path,
            target_version="2.00.cpan1",
        )
        (d2.parent / "metadata.json").write_text(json.dumps({"versions": ["2.00.cpan1"]}), encoding="utf-8")

        indexer = CPANIndexer(
            index_dir=self.index_dir,
            workspace_dir=self.root_path,
        )

        # Regenerate in parallel with jobs=2 including an invalid module to verify resilience
        count = indexer.regenerate_modules(
            modules=["perl-sample-one", "non-existent-module", "perl-sample-two"],
            bump_build_id=False,
            jobs=2,
        )
        self.assertEqual(count, 2)
        self.assertTrue((d1 / "overlay" / "BUILD.bazel").exists())
        self.assertTrue((d2 / "overlay" / "BUILD.bazel").exists())

    def _create_sample_tar(self, prefix: str, files: dict[str, str]) -> Path:
        import io
        import tarfile
        tar_buf = io.BytesIO()
        with tarfile.open(fileobj=tar_buf, mode="w:gz") as tar:
            for rel_path, content in files.items():
                encoded = content.encode("utf-8")
                ti = tarfile.TarInfo(f"{prefix}/{rel_path}")
                ti.size = len(encoded)
                tar.addfile(ti, io.BytesIO(encoded))
        tar_path = self.root_path / f"{prefix.lower()}.tar.gz"
        tar_path.write_bytes(tar_buf.getvalue())
        return tar_path

    def test_xs_included_c_files_relative_resolution(self) -> None:
        """Verifies that #include of C files in subdirectory XS files are resolved to their relative path."""
        tar_path = self._create_sample_tar(
            "Authen-Sample-1.00",
            {
                "lib/Authen/Sample.xs": 'MODULE = Authen::Sample\n#include "sample_constants.c"\n',
                "lib/Authen/sample_constants.c": '/* constants */\n',
                "lib/Authen/Sample.pm": 'package Authen::Sample;\n1;\n',
            },
        )
        manager = IndexManager(index_dir=self.index_dir)
        d = manager.create_new_port(
            dist_name="Authen-Sample",
            upstream_version="1.00",
            archive_url=tar_path.as_uri(),
            archive_sha256="",
            archive_path=tar_path,
            target_version="1.00.cpan1",
        )
        build_bazel = (d / "overlay" / "BUILD.bazel").read_text(encoding="utf-8")
        self.assertIn('"lib/Authen/sample_constants.c"', build_bazel)
        self.assertNotIn('"sample_constants.c"', build_bazel)

    def test_root_pm_mapping_to_overlay(self) -> None:
        """Verifies that root .pm files are mapped into lib/ via copy_file without checking in file."""
        tar_path = self._create_sample_tar(
            "Text-SampleDisplay-1.00",
            {
                "SampleDisplay.pm": 'package Text::SampleDisplay;\n1;\n',
                "Makefile.PL": (
                    'use ExtUtils::MakeMaker;\n'
                    'WriteMakefile(NAME => "Text::SampleDisplay", VERSION_FROM => "SampleDisplay.pm");\n'
                ),
            },
        )
        manager = IndexManager(index_dir=self.index_dir)
        d = manager.create_new_port(
            dist_name="Text-SampleDisplay",
            upstream_version="1.00",
            archive_url=tar_path.as_uri(),
            archive_sha256="",
            archive_path=tar_path,
            target_version="1.00.cpan1",
        )
        build_bazel = (d / "overlay" / "BUILD.bazel").read_text(encoding="utf-8")
        self.assertIn("copy_file(", build_bazel)
        self.assertIn("SampleDisplay.pm", build_bazel)
        self.assertIn("lib/Text/SampleDisplay.pm", build_bazel)
        source_json = json.loads((d / "source.json").read_text(encoding="utf-8"))
        self.assertNotIn("lib/Text/SampleDisplay.pm", source_json.get("overlay", {}))
        self.assertFalse((d / "overlay" / "lib" / "Text" / "SampleDisplay.pm").exists())
        module_bazel = (d / "MODULE.bazel").read_text(encoding="utf-8")
        self.assertIn('bazel_dep(name = "bazel_lib"', module_bazel)

    def test_build_requires_included_in_test_deps(self) -> None:
        """Verifies that build dependencies from lockfile are included in test_deps."""
        tar_path = self._create_sample_tar(
            "Sample-BuildReq-1.00",
            {
                "lib/Sample/BuildReq.pm": 'package Sample::BuildReq;\n1;\n',
                "t/01-test.t": 'print "1..1\\nok 1\\n";\n',
            },
        )
        lockfile = self.root_path / "cpan.lock.json"
        lock_data = {
            "version": "1.0",
            "distributions": {
                "Sample-BuildReq": {
                    "version": "1.00",
                    "dependencies": {
                        "runtime": [],
                        "build": ["Test-Helper"],
                        "test": [],
                    },
                    "provides": ["Sample::BuildReq"],
                }
            },
        }
        lockfile.write_text(json.dumps(lock_data), encoding="utf-8")

        manager = IndexManager(index_dir=self.index_dir)
        manager.load_lockfile(lockfile)
        d = manager.create_new_port(
            dist_name="Sample-BuildReq",
            upstream_version="1.00",
            archive_url=tar_path.as_uri(),
            archive_sha256="",
            archive_path=tar_path,
            target_version="1.00.cpan1",
        )
        build_bazel = (d / "overlay" / "BUILD.bazel").read_text(encoding="utf-8")
        self.assertIn("@perl-test-helper", build_bazel)

    def test_ppport_h_synthesis_when_missing(self) -> None:
        """Verifies that ppport.h is emitted via copy_file from rules_cpan without checking in file."""
        tar_path = self._create_sample_tar(
            "Sample-Ppport-1.00",
            {
                "Sample.xs": '#include "EXTERN.h"\n#include "perl.h"\n#include "XSUB.h"\n#include "ppport.h"\nMODULE = Sample::Ppport\n',
                "lib/Sample/Ppport.pm": 'package Sample::Ppport;\n1;\n',
            },
        )
        manager = IndexManager(index_dir=self.index_dir)
        d = manager.create_new_port(
            dist_name="Sample-Ppport",
            upstream_version="1.00",
            archive_url=tar_path.as_uri(),
            archive_sha256="",
            archive_path=tar_path,
            target_version="1.00.cpan1",
        )
        build_bazel = (d / "overlay" / "BUILD.bazel").read_text(encoding="utf-8")
        self.assertIn("copy_file(", build_bazel)
        self.assertIn("@rules_cpan//cpan/resources/ppport:ppport.h", build_bazel)
        source_json = json.loads((d / "source.json").read_text(encoding="utf-8"))
        self.assertNotIn("ppport.h", source_json.get("overlay", {}))
        self.assertFalse((d / "overlay" / "ppport.h").exists())


if __name__ == "__main__":
    unittest.main()
