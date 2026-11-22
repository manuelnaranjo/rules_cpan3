#!/usr/bin/env python3
"""Unit tests for cpan2bazel porting workflow."""

import json
import os
import tempfile
import unittest

from cpan2bazel import CPANPorter, compute_output_loc, compute_sri_hash, sanitize_module_name


class TestCPAN2Bazel(unittest.TestCase):

    def test_sanitize_module_name(self):
        self.assertEqual(sanitize_module_name("Compress-Raw-Zlib"), "perl-compress-raw-zlib")
        self.assertEqual(sanitize_module_name("Algorithm::Diff"), "perl-algorithm-diff")
        self.assertEqual(sanitize_module_name("YAML_LibYAML"), "perl-yaml-libyaml")

    def test_compute_output_loc(self):
        self.assertEqual(
            compute_output_loc("Compress-Raw-Zlib", ["Compress::Raw::Zlib"]),
            "auto/Compress/Raw/Zlib/Zlib",
        )
        self.assertEqual(
            compute_output_loc("Socket", ["Socket"]),
            "auto/Socket/Socket",
        )

    def test_compute_sri_hash(self):
        data = b"Hello, world!"
        sri = compute_sri_hash(data)
        self.assertTrue(sri.startswith("sha256-"))

    def test_pure_perl_build_generation(self):
        porter = CPANPorter(
            distribution="Algorithm-Diff",
            version="1.201",
        )
        porter.is_xs = False
        content = porter.generate_build_content()
        self.assertIn('load("@rules_perl//perl:defs.bzl", "perl_library")', content)
        self.assertIn('name = "Algorithm-Diff"', content)
        self.assertNotIn("cpan_xs", content)

    def test_xs_build_generation(self):
        porter = CPANPorter(
            distribution="Compress-Raw-Zlib",
            version="2.226",
            native_deps=["@zlib"],
        )
        porter.is_xs = True
        porter.provides = ["Compress::Raw::Zlib"]
        content = porter.generate_build_content()
        self.assertIn('load("@rules_cpan//cpan:defs.bzl", "cpan_xs")', content)
        self.assertIn('name = "Compress-Raw-Zlib_xs"', content)
        self.assertIn('output_loc = "auto/Compress/Raw/Zlib/Zlib"', content)
        self.assertIn('"@zlib"', content)
        self.assertIn("@platforms//os:osx", content)


if __name__ == "__main__":
    unittest.main()
