"""Unit tests for rules_cpan Bzlmod module extension and repository rule logic."""

import json
import os
import unittest


def sanitize_repo_name(name: str) -> str:
    res = ""
    for c in name:
        if (
            ("a" <= c <= "z")
            or ("A" <= c <= "Z")
            or ("0" <= c <= "9")
            or c in ["-", "_", "."]
        ):
            res += c
        else:
            res += "_"
    return res


def dist_to_bcr_module(dist_name: str) -> str:
    res = ""
    for c in dist_name.lower():
        if ("a" <= c <= "z") or ("0" <= c <= "9") or c in [".", "-"]:
            res += c
        else:
            res += "-"
    res = res.strip("-")
    return f"perl-{res}"


def get_strip_prefix(url: str) -> str:
    filename = url.split("/")[-1]
    for ext in [
        ".tar.gz",
        ".tgz",
        ".tar.bz2",
        ".tbz2",
        ".tar.xz",
        ".txz",
        ".zip",
    ]:
        if filename.endswith(ext):
            return filename[: -len(ext)]
    return ""


def get_primary_module(dist_name: str, provides: list[str]) -> str:
    canonical_mod = dist_name.replace("-", "::")
    if provides:
        if canonical_mod in provides:
            return canonical_mod
        return provides[0]
    return canonical_mod


def compute_output_loc(dist_name: str, provides: list[str]) -> str:
    primary_mod = get_primary_module(dist_name, provides)
    parts = primary_mod.split("::")
    path_prefix = "/".join(parts)
    leaf = parts[-1]
    return f"auto/{path_prefix}/{leaf}"


def prune_runtime_cycles(
    dists: dict, root_dependencies: list[str]
) -> dict[str, list[str]]:
    raw_graph = {
        k: list(dists[k].get("dependencies", {}).get("runtime", []))
        for k in dists
    }
    state = {k: 0 for k in dists}
    pruned_graph = {k: [] for k in dists}

    start_nodes = []
    for root in root_dependencies:
        dist = root.split(" ")[0]
        if dist in dists and dist not in start_nodes:
            start_nodes.append(dist)
    for dist in sorted(dists.keys()):
        if dist not in start_nodes:
            start_nodes.append(dist)

    max_steps = (len(dists) + 1) * 20

    for start in start_nodes:
        if state[start] != 0:
            continue
        stack = [(start, 0)]
        state[start] = 1
        for _ in range(max_steps):
            if not stack:
                break
            node, idx = stack[-1]
            neighbors = raw_graph.get(node, [])
            if idx < len(neighbors):
                stack[-1] = (node, idx + 1)
                v = neighbors[idx]
                if v not in dists:
                    continue
                if state[v] == 1:
                    continue
                pruned_graph[node].append(v)
                if state[v] == 0:
                    state[v] = 1
                    stack.append((v, 0))
            else:
                state[node] = 2
                stack.pop()

    return pruned_graph


def is_dag(graph: dict[str, list[str]]) -> bool:
    vis = {}
    has_cycle = False

    def dfs(u):
        nonlocal has_cycle
        vis[u] = 1
        for v in graph.get(u, []):
            if vis.get(v, 0) == 1:
                has_cycle = True
            elif vis.get(v, 0) == 0:
                dfs(v)
        vis[u] = 2

    for node in graph:
        if vis.get(node, 0) == 0:
            dfs(node)

    return not has_cycle


class BzlmodExtensionTests(unittest.TestCase):
    def test_sanitize_repo_name(self):
        self.assertEqual(sanitize_repo_name("Algorithm-Diff"), "Algorithm-Diff")
        self.assertEqual(
            sanitize_repo_name("Compress-Raw-Zlib"), "Compress-Raw-Zlib"
        )
        self.assertEqual(
            sanitize_repo_name("Text-Tabs+Wrap"), "Text-Tabs_Wrap"
        )
        self.assertEqual(sanitize_repo_name("Foo::Bar@1"), "Foo__Bar_1")

    def test_dist_to_bcr_module(self):
        self.assertEqual(dist_to_bcr_module("Algorithm-Diff"), "perl-algorithm-diff")
        self.assertEqual(
            dist_to_bcr_module("Compress-Raw-Zlib"), "perl-compress-raw-zlib"
        )
        self.assertEqual(dist_to_bcr_module("IO-Tty"), "perl-io-tty")
        self.assertEqual(dist_to_bcr_module("Text-Tabs+Wrap"), "perl-text-tabs-wrap")
        self.assertEqual(dist_to_bcr_module("YAML-LibYAML"), "perl-yaml-libyaml")
        self.assertEqual(dist_to_bcr_module("Cpanel-JSON-XS"), "perl-cpanel-json-xs")

    def test_get_strip_prefix(self):
        self.assertEqual(
            get_strip_prefix(
                "https://cpan.metacpan.org/authors/id/R/RJ/RJBS/Algorithm-Diff-1.201.tar.gz"
            ),
            "Algorithm-Diff-1.201",
        )
        self.assertEqual(
            get_strip_prefix("https://example.com/archive.tgz"), "archive"
        )
        self.assertEqual(
            get_strip_prefix("https://example.com/archive.zip"), "archive"
        )
        self.assertEqual(
            get_strip_prefix("https://example.com/archive.tar.bz2"), "archive"
        )

    def test_compute_output_loc(self):
        self.assertEqual(
            compute_output_loc("Compress-Raw-Zlib", ["Compress::Raw::Zlib"]),
            "auto/Compress/Raw/Zlib/Zlib",
        )
        self.assertEqual(compute_output_loc("Socket", ["Socket"]), "auto/Socket/Socket")
        self.assertEqual(
            compute_output_loc("Data-Dumper", ["Data::Dumper"]),
            "auto/Data/Dumper/Dumper",
        )

    def test_cycle_pruning_on_synthetic_cycle(self):
        # A -> B -> C -> A
        dists = {
            "A": {"dependencies": {"runtime": ["B"]}},
            "B": {"dependencies": {"runtime": ["C"]}},
            "C": {"dependencies": {"runtime": ["A"]}},
        }
        pruned = prune_runtime_cycles(dists, ["A"])
        self.assertTrue(is_dag(pruned))
        # Ensure reachability from A is maintained to B and C
        self.assertIn("B", pruned["A"])
        self.assertIn("C", pruned["B"])
        self.assertNotIn("A", pruned["C"])

    def test_cycle_pruning_on_cpan_lockfile(self):
        lock_path = os.environ.get(
            "TEST_LOCKFILE", "tests/cpan.lock.json"
        )
        if not os.path.exists(lock_path):
            # Try finding via runfiles
            lock_path = os.path.join(
                os.environ.get("TEST_SRCDIR", ""),
                os.environ.get("TEST_WORKSPACE", "_main"),
                "tests/cpan.lock.json",
            )
        self.assertTrue(os.path.exists(lock_path), f"Lockfile not found at {lock_path}")

        with open(lock_path) as f:
            data = json.load(f)

        dists = data["distributions"]
        root_deps = data["root_dependencies"]

        pruned = prune_runtime_cycles(dists, root_deps)
        self.assertTrue(
            is_dag(pruned), "Pruned CPAN runtime dependency graph must be a strict DAG"
        )

    def test_annotations_formatting(self):
        # Verify formatting helper logic for annotations
        target_compat = ["@platforms//os:linux", "@platforms//os:macos"]
        exec_reqs = {"no-remote": "1", "supports-path-mapping": "1"}
        extra_includes = ["LibYAML/lib", "custom/inc"]

        target_str = ", ".join(f'"{x}"' for x in target_compat)
        self.assertIn('"@platforms//os:linux"', target_str)
        self.assertIn('"@platforms//os:macos"', target_str)

        reqs_str = ", ".join(f'"{k}": "{v}"' for k, v in exec_reqs.items())
        self.assertIn('"no-remote": "1"', reqs_str)
        self.assertIn('"supports-path-mapping": "1"', reqs_str)

        includes_list = ['"."', '"lib"']
        for inc in extra_includes:
            quoted = f'"{inc}"'
            if quoted not in includes_list:
                includes_list.append(quoted)
        self.assertIn('"LibYAML/lib"', includes_list)
        self.assertIn('"custom/inc"', includes_list)

    def test_injected_targets_mapping(self):
        injected = {
            "Compress-Raw-Zlib": "@perl-compress-raw-zlib//:Compress-Raw-Zlib",
        }
        all_dists = {"Algorithm-Diff": dist_to_bcr_module("Algorithm-Diff")}
        # Combined keys
        combined = dict(all_dists)
        for dist in injected:
            if dist not in combined:
                combined[dist] = dist_to_bcr_module(dist)
        self.assertIn("Compress-Raw-Zlib", combined)
        self.assertIn("Algorithm-Diff", combined)

        # Resolution for alias directly pointing to BCR module target
        bcr_mod = all_dists["Algorithm-Diff"]
        actual_injected = injected.get(
            "Compress-Raw-Zlib",
            f"@{dist_to_bcr_module('Compress-Raw-Zlib')}//:{dist_to_bcr_module('Compress-Raw-Zlib')}",
        )
        actual_normal = injected.get("Algorithm-Diff", f"@{bcr_mod}//:{bcr_mod}")
        self.assertEqual(actual_injected, "@perl-compress-raw-zlib//:Compress-Raw-Zlib")
        self.assertEqual(actual_normal, "@perl-algorithm-diff//:perl-algorithm-diff")

    def test_get_primary_module(self):
        self.assertEqual(
            get_primary_module("Algorithm-Diff", ["Algorithm::Diff", "Algorithm::Diff::_impl"]),
            "Algorithm::Diff",
        )
        self.assertEqual(
            get_primary_module("PathTools", ["Cwd", "File::Spec"]),
            "Cwd",
        )
        self.assertEqual(
            get_primary_module("Text-Tabs+Wrap", ["Text::Tabs", "Text::Wrap"]),
            "Text::Tabs",
        )
        self.assertEqual(
            get_primary_module("Unknown-Module", []),
            "Unknown::Module",
        )

    def test_hub_repo_test_suite_generation(self):
        injected = {
            "Algorithm-Diff": "@perl-algorithm-diff//:Algorithm-Diff",
            "Compress-Raw-Zlib": "@perl-compress-raw-zlib//:Compress-Raw-Zlib",
        }

        declared_tests = []
        upstream_tests = {}
        for dist, actual in sorted(injected.items()):
            target_name = f":{dist}_test"
            if "//" in actual:
                repo = actual.split("//")[0]
                upstream = f"{repo}//:test"
            else:
                upstream = f"{actual}_test"
            declared_tests.append(target_name)
            upstream_tests[target_name] = upstream

        self.assertEqual(declared_tests, [":Algorithm-Diff_test", ":Compress-Raw-Zlib_test"])
        self.assertEqual(upstream_tests[":Algorithm-Diff_test"], "@perl-algorithm-diff//:test")
        self.assertEqual(upstream_tests[":Compress-Raw-Zlib_test"], "@perl-compress-raw-zlib//:test")


if __name__ == "__main__":
    unittest.main()
