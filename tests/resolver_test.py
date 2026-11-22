#!/usr/bin/env python3
"""Comprehensive test suite for rules_cpan CPAN resolver and lockfile generator."""

import gzip
import io
import json
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from cpan.tools.resolver.resolver import (
    ArchiveInspector,
    CPANIndex,
    CPANResolver,
    MetaCPANClient,
    Requirement,
    ResolvedDistribution,
)

SAMPLE_02PACKAGES = b"""File:         02packages.details.txt
URL:          http://www.cpan.org/modules/02packages.details.txt
Description:  Package names found in directory $CPAN/authors/id/
Columns:      package name, version, path
Line-Count:   6
Last-Updated: Sat, 21 Nov 2026 00:00:00 GMT

Algorithm::Diff                    1.201  R/RJ/RJBS/Algorithm-Diff-1.201.tar.gz
Algorithm::Diff::_impl             1.201  R/RJ/RJBS/Algorithm-Diff-1.201.tar.gz
Compress::Raw::Zlib                2.226  P/PM/PMQS/Compress-Raw-Zlib-2.226.tar.gz
strict                             1.14   S/SH/SHAY/perl-5.42.3.tar.gz
warnings                           1.78   L/LE/LEONT/perl-5.44.0.tar.gz
Test::More                         1.302  E/EX/EXODIST/Test-Simple-1.302.tar.gz
"""


class ResolverUnitTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cache_dir = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_parse_deps_file(self) -> None:
        deps_content = """
        # Sample dependencies specification
        ack v3.4.0
        Action-Retry 0.24 # With comment
        Algorithm-C3 0.10
        Compress-Raw-Zlib 2.226
        Algorithm::Diff >= 1.1903

        # Bare distribution without version
        Capture::Tiny
        """
        inspector = ArchiveInspector()
        index = CPANIndex()
        metacpan = MetaCPANClient()
        resolver = CPANResolver(index, metacpan, inspector)

        reqs = resolver.parse_deps_file(deps_content)
        self.assertEqual(len(reqs), 6)

        req_map = {r.name: r for r in reqs}
        self.assertEqual(req_map["ack"].version, "3.4.0")
        self.assertFalse(req_map["ack"].is_module)

        self.assertEqual(req_map["Action-Retry"].version, "0.24")
        self.assertEqual(req_map["Compress-Raw-Zlib"].version, "2.226")

        self.assertEqual(req_map["Algorithm::Diff"].version, "1.1903")
        self.assertTrue(req_map["Algorithm::Diff"].is_module)

        self.assertIsNone(req_map["Capture::Tiny"].version)
        self.assertTrue(req_map["Capture::Tiny"].is_module)

    def test_cpan_index_parsing(self) -> None:
        gz_data = gzip.compress(SAMPLE_02PACKAGES)
        index = CPANIndex(use_cache=False)
        index.load(gz_data)

        # Module to distribution mapping
        self.assertEqual(index.find_dist_for_module("Algorithm::Diff"), "Algorithm-Diff")
        self.assertEqual(index.find_dist_for_module("Test::More"), "Test-Simple")
        self.assertEqual(
            index.find_dist_for_module("Compress::Raw::Zlib"), "Compress-Raw-Zlib"
        )

        # Core detection
        self.assertTrue(index.is_core_module("strict"))
        self.assertTrue(index.is_core_module("warnings"))
        self.assertTrue(index.is_core_module("perl"))
        self.assertTrue(index.is_core_module("utf8"))
        self.assertFalse(index.is_core_module("Algorithm::Diff"))

        # Version extraction
        self.assertEqual(index.dist_to_version.get("Algorithm-Diff"), "1.201")
        self.assertEqual(index.dist_to_version.get("Compress-Raw-Zlib"), "2.226")

    def test_archive_inspector_xs_detection(self) -> None:
        inspector = ArchiveInspector(cache_dir=self.cache_dir, use_cache=True)

        # 1. Pure Perl tarball
        pp_bio = io.BytesIO()
        with tarfile.open(fileobj=pp_bio, mode="w:gz") as tar:
            f1 = tarfile.TarInfo("Foo-Bar-1.0/lib/Foo/Bar.pm")
            f1.size = 14
            tar.addfile(f1, io.BytesIO(b"package Foo::Bar; 1;"))
        pp_bytes = pp_bio.getvalue()

        # Mock download URL handling by saving to cache file
        pp_cache = self.cache_dir / "dist" / "Foo-Bar-1.0.tar.gz"
        pp_cache.parent.mkdir(parents=True, exist_ok=True)
        pp_cache.write_bytes(pp_bytes)

        sha256, is_xs, members = inspector.inspect_archive(
            "https://cpan.org/authors/id/F/FO/FOO/Foo-Bar-1.0.tar.gz"
        )
        self.assertFalse(is_xs)
        self.assertIn("Foo-Bar-1.0/lib/Foo/Bar.pm", members)

        # 2. XS tarball
        xs_bio = io.BytesIO()
        with tarfile.open(fileobj=xs_bio, mode="w:gz") as tar:
            f1 = tarfile.TarInfo("Zlib-1.0/Zlib.xs")
            f1.size = 20
            tar.addfile(f1, io.BytesIO(b"#include <EXTERN.h>\n"))
            f2 = tarfile.TarInfo("Zlib-1.0/lib/Zlib.pm")
            f2.size = 14
            tar.addfile(f2, io.BytesIO(b"package Zlib; 1;"))
        xs_bytes = xs_bio.getvalue()

        xs_cache = self.cache_dir / "dist" / "Zlib-1.0.tar.gz"
        xs_cache.write_bytes(xs_bytes)

        sha256, is_xs, members = inspector.inspect_archive(
            "https://cpan.org/authors/id/Z/ZL/ZLIB/Zlib-1.0.tar.gz"
        )
        self.assertTrue(is_xs)
        self.assertIn("Zlib-1.0/Zlib.xs", members)

    def test_deterministic_lockfile_generation(self) -> None:
        index = CPANIndex()
        metacpan = MetaCPANClient()
        inspector = ArchiveInspector()
        resolver = CPANResolver(index, metacpan, inspector)

        reqs = [
            Requirement(name="Compress-Raw-Zlib", version="2.226"),
            Requirement(name="Algorithm-Diff", version="1.201"),
        ]

        resolved = {
            "Compress-Raw-Zlib": ResolvedDistribution(
                name="Compress-Raw-Zlib",
                version="2.226",
                download_url="https://cpan.metacpan.org/authors/id/P/PM/PMQS/Compress-Raw-Zlib-2.226.tar.gz",
                sha256="80dc104a733976eba40dbe9272cd32ebf183195204e0bdd30e214a37d2ac42cb",
                is_xs=True,
                provides=["Compress::Raw::Zlib"],
                dependencies={
                    "build": ["ExtUtils::MakeMaker"],
                    "configure": ["ExtUtils::MakeMaker"],
                    "runtime": [],
                    "test": [],
                },
            ),
            "Algorithm-Diff": ResolvedDistribution(
                name="Algorithm-Diff",
                version="1.201",
                download_url="https://cpan.metacpan.org/authors/id/R/RJ/RJBS/Algorithm-Diff-1.201.tar.gz",
                sha256="0022da5982645d9ef0207f3eb9ef63e70e9713ed2340ed7b3850779b0d842a7d",
                is_xs=False,
                provides=["Algorithm::Diff", "Algorithm::Diff::_impl"],
                dependencies={
                    "build": ["ExtUtils::MakeMaker"],
                    "configure": ["ExtUtils::MakeMaker"],
                    "runtime": [],
                    "test": [],
                },
            ),
        }

        lockfile_path = self.cache_dir / "cpan.lock.json"
        content = resolver.generate_lockfile(reqs, resolved, output_path=lockfile_path)

        # Check file exists and is valid JSON
        self.assertTrue(lockfile_path.exists())
        data = json.loads(content)

        self.assertEqual(data["lock_version"], "1.0.0")
        self.assertIn("Algorithm-Diff", data["distributions"])
        self.assertIn("Compress-Raw-Zlib", data["distributions"])

        # Check determinism: distributions are sorted alphabetically
        keys = list(data["distributions"].keys())
        self.assertEqual(keys, ["Algorithm-Diff", "Compress-Raw-Zlib"])

        # Check properties
        zlib = data["distributions"]["Compress-Raw-Zlib"]
        self.assertTrue(zlib["is_xs"])
        self.assertEqual(zlib["version"], "2.226")
        self.assertEqual(
            zlib["sha256"],
            "80dc104a733976eba40dbe9272cd32ebf183195204e0bdd30e214a37d2ac42cb",
        )

        diff = data["distributions"]["Algorithm-Diff"]
        self.assertFalse(diff["is_xs"])
        self.assertEqual(diff["provides"], ["Algorithm::Diff", "Algorithm::Diff::_impl"])

    def test_transitive_closure_resolution(self) -> None:
        index = CPANIndex(use_cache=False)
        index.load(gzip.compress(SAMPLE_02PACKAGES))

        metacpan = MetaCPANClient()
        # Mock MetaCPAN bulk query
        metacpan.fetch_releases_bulk = MagicMock(
            return_value={
                "Algorithm-Diff": {
                    "distribution": "Algorithm-Diff",
                    "version": "1.201",
                    "download_url": "https://cpan.org/Algorithm-Diff-1.201.tar.gz",
                    "checksum_sha256": "0022da5982645d9ef0207f3eb9ef63e70e9713ed2340ed7b3850779b0d842a7d",
                    "provides": ["Algorithm::Diff"],
                    "dependency": [
                        {
                            "module": "strict",
                            "phase": "runtime",
                            "relationship": "requires",
                        },
                        {
                            "module": "Test::More",
                            "phase": "test",
                            "relationship": "requires",
                        },
                    ],
                },
                "Test-Simple": {
                    "distribution": "Test-Simple",
                    "version": "1.302",
                    "download_url": "https://cpan.org/Test-Simple-1.302.tar.gz",
                    "checksum_sha256": "abcdef123456",
                    "provides": ["Test::More", "Test::Simple"],
                    "dependency": [
                        {
                            "module": "warnings",
                            "phase": "runtime",
                            "relationship": "requires",
                        }
                    ],
                },
            }
        )

        inspector = ArchiveInspector()
        inspector.inspect_archive = MagicMock(return_value=("fake_sha", False, []))

        resolver = CPANResolver(
            index, metacpan, inspector, verify_checksums=False
        )
        reqs = [Requirement(name="Algorithm-Diff", version="1.201")]

        resolved = resolver.resolve(reqs)

        # Transitive closure should contain both Algorithm-Diff and Test-Simple (from Test::More)
        self.assertIn("Algorithm-Diff", resolved)
        self.assertIn("Test-Simple", resolved)
        # strict and warnings are core modules, should not be resolved as CPAN distributions
        self.assertNotIn("strict", resolved)
        self.assertNotIn("warnings", resolved)

    def test_lockfile_schema_and_contents(self) -> None:
        # Locate files in runfiles or repository root
        candidates = [
            Path("tests/cpan.lock.json"),
            Path(__file__).parent / "cpan.lock.json",
        ]
        test_srcdir = Path.cwd()
        lock_path = None
        for cand in candidates:
            if cand.exists():
                lock_path = cand
                break
        if not lock_path:
            return  # skip if runfile not available in test environment

        data = json.loads(lock_path.read_text(encoding="utf-8"))
        self.assertEqual(data["lock_version"], "1.0.0")
        self.assertIsInstance(data["root_dependencies"], list)
        self.assertIsInstance(data["distributions"], dict)

        for dist_name, dist_info in data["distributions"].items():
            self.assertIsInstance(dist_name, str)
            self.assertIn("version", dist_info)
            self.assertIn("url", dist_info)
            self.assertIn("sha256", dist_info)
            self.assertIn("is_xs", dist_info)
            self.assertIsInstance(dist_info["is_xs"], bool)
            self.assertIn("provides", dist_info)
            self.assertIsInstance(dist_info["provides"], list)
            self.assertIn("dependencies", dist_info)
            deps = dist_info["dependencies"]
            for phase in ("build", "configure", "runtime", "test"):
                self.assertIn(phase, deps)
                self.assertIsInstance(deps[phase], list)


if __name__ == "__main__":
    unittest.main()
