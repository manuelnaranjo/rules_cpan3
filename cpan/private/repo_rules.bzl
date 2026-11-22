"""Repository rules for rules_cpan distributions and hub repository."""

def sanitize_repo_name(name):
    """Sanitize distribution names for Bazel repository names.

    Args:
        name: CPAN distribution name.

    Returns:
        Sanitized repository name string.
    """
    res = ""
    for i in range(len(name)):
        c = name[i]
        if (c >= "a" and c <= "z") or (c >= "A" and c <= "Z") or (c >= "0" and c <= "9") or c in ["-", "_", "."]:
            res += c
        else:
            res += "_"
    return res

def get_strip_prefix(url):
    """Compute archive strip prefix from tarball URL.

    Args:
        url: Upstream tarball URL.

    Returns:
        Archive directory prefix to strip.
    """
    filename = url.split("/")[-1]
    for ext in [".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tar.xz", ".txz", ".zip"]:
        if filename.endswith(ext):
            return filename[:-len(ext)]
    return ""

def prune_runtime_cycles(dists, root_dependencies):
    """Prunes back-edges from runtime dependency graph to ensure a DAG in Bazel.

    Args:
        dists: Dictionary of distributions from lockfile.
        root_dependencies: List of root dependencies from lockfile.

    Returns:
        Dictionary mapping distribution name to a cycle-free list of runtime dependencies.
    """
    raw_graph = {k: list(dists[k].get("dependencies", {}).get("runtime", [])) for k in dists}
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
                    # Back-edge forming a cycle; prune it
                    continue
                pruned_graph[node].append(v)
                if state[v] == 0:
                    state[v] = 1
                    stack.append((v, 0))
            else:
                state[node] = 2
                stack.pop()

    return pruned_graph

def get_primary_module(dist_name, provides):
    """Determine the primary Perl module name for a distribution.

    Args:
        dist_name: CPAN distribution name (e.g. 'Algorithm-Diff').
        provides: List of packages provided by the distribution.

    Returns:
        Primary Perl package name (e.g. 'Algorithm::Diff').
    """
    canonical_mod = dist_name.replace("-", "::")
    if provides:
        if canonical_mod in provides:
            return canonical_mod
        return provides[0]
    return canonical_mod

def _compute_output_loc(dist_name, provides):
    """Compute the DynaLoader/XSLoader auto/ directory location for an XS module."""
    primary_mod = get_primary_module(dist_name, provides)
    parts = primary_mod.split("::")
    path_prefix = "/".join(parts)
    leaf = parts[-1]
    return "auto/" + path_prefix + "/" + leaf

def _apply_patches(ctx):
    for patch in ctx.attr.patches:
        ctx.patch(patch)

    patch_cmds = ctx.attr.patch_cmds
    if ctx.os.name.startswith("windows"):
        if ctx.attr.patch_cmds_win:
            patch_cmds = ctx.attr.patch_cmds_win

    for cmd in patch_cmds:
        if ctx.os.name.startswith("windows"):
            res = ctx.execute(["cmd.exe", "/c", cmd])
        else:
            res = ctx.execute(["sh", "-c", cmd])
        if res.return_code != 0:
            fail("Failed to execute patch_cmd '%s':\n%s\n%s" % (cmd, res.stdout, res.stderr))

def _cpan_dist_repo_impl(ctx):
    strip_prefix = ctx.attr.strip_prefix
    if not strip_prefix:
        strip_prefix = get_strip_prefix(ctx.attr.url)

    ctx.download_and_extract(
        url = ctx.attr.url,
        sha256 = ctx.attr.sha256,
        stripPrefix = strip_prefix,
    )
    _apply_patches(ctx)

    if ctx.attr.build_file:
        ctx.file("BUILD.bazel", ctx.read(ctx.attr.build_file))
        return

    # Check fallback directory for constants if present
    if not ctx.attr.patch_cmds:
        if ctx.path("fallback/constants.h").exists and not ctx.path("constants.h").exists:
            ctx.file("constants.h", ctx.read(ctx.path("fallback/constants.h")))
        if ctx.path("fallback/constants.xs").exists and not ctx.path("constants.xs").exists:
            ctx.file("constants.xs", ctx.read(ctx.path("fallback/constants.xs")))

    deps_items = ['"%s"' % d for d in ctx.attr.runtime_deps]
    if deps_items:
        deps_str = "\n        " + ",\n        ".join(deps_items) + ",\n    "
    else:
        deps_str = ""

    target_compat_items = ['"%s"' % d for d in ctx.attr.target_compatible_with]
    if target_compat_items:
        target_compat_str = "\n    target_compatible_with = [\n        " + ",\n        ".join(target_compat_items) + ",\n    ],"
    else:
        target_compat_str = ""

    exec_compat_items = ['"%s"' % d for d in ctx.attr.exec_compatible_with]
    if exec_compat_items:
        exec_compat_str = "\n    exec_compatible_with = [\n        " + ",\n        ".join(exec_compat_items) + ",\n    ],"
    else:
        exec_compat_str = ""

    tags_items = ['"%s"' % d for d in ctx.attr.extra_tags]
    if tags_items:
        tags_str = "\n    tags = [\n        " + ",\n        ".join(tags_items) + ",\n    ],"
    else:
        tags_str = ""

    if ctx.attr.execution_requirements:
        reqs_items = ['"%s": "%s"' % (k, v) for k, v in ctx.attr.execution_requirements.items()]
        exec_reqs_str = "\n    execution_requirements = {\n        " + ",\n        ".join(reqs_items) + ",\n    },"
    else:
        exec_reqs_str = ""

    includes_list = ['"."', '"lib"']
    for inc in ctx.attr.includes:
        quoted = '"%s"' % inc
        if quoted not in includes_list:
            includes_list.append(quoted)
    includes_str = "\n        " + ",\n        ".join(includes_list) + ",\n    "

    src_patterns = ['"lib/**/*.pm"', '"lib/**/*.pod"', '"*.pm"']
    data_patterns = ['"lib/**/*"']
    exclude_patterns = ['"lib/**/*.pm"', '"lib/**/*.pod"']

    for inc in ctx.attr.includes:
        src_patterns.append('"%s/**/*.pm"' % inc)
        src_patterns.append('"%s/**/*.pod"' % inc)
        data_patterns.append('"%s/**/*"' % inc)
        exclude_patterns.append('"%s/**/*.pm"' % inc)
        exclude_patterns.append('"%s/**/*.pod"' % inc)

    srcs_str = "\n        " + ",\n        ".join(src_patterns) + ",\n    "
    data_str = "\n        " + ",\n        ".join(data_patterns) + ",\n    "
    exclude_str = "\n        " + ",\n        ".join(exclude_patterns) + ",\n    "

    if not ctx.attr.is_xs:
        # Pure Perl distribution
        build_content = """# Auto-generated by rules_cpan for {dist_name}
load("@rules_perl//perl:defs.bzl", "perl_library")

package(default_visibility = ["//visibility:public"])

perl_library(
    name = "{dist_name}",
    srcs = glob([{srcs_str}], allow_empty = True),
    data = glob([{data_str}], exclude = [{exclude_str}], allow_empty = True),
    includes = [{includes_str}],{exec_compat_str}{tags_str}{target_compat_str}
    deps = [{deps_str}],
)
""".format(
            dist_name = ctx.attr.dist_name,
            srcs_str = srcs_str,
            data_str = data_str,
            exclude_str = exclude_str,
            deps_str = deps_str,
            exec_compat_str = exec_compat_str,
            includes_str = includes_str,
            tags_str = tags_str,
            target_compat_str = target_compat_str,
        )
    else:
        # XS (C extension) module
        output_loc = ctx.attr.output_loc
        if not output_loc:
            output_loc = _compute_output_loc(ctx.attr.dist_name, ctx.attr.provides)

        defines_items = ['"%s"' % d for d in ctx.attr.defines]
        if defines_items:
            defines_str = "\n        " + ",\n        ".join(defines_items) + ",\n    "
        else:
            defines_str = ""

        native_deps_items = ['"%s"' % d for d in ctx.attr.native_deps]
        if native_deps_items:
            native_deps_str = "\n        " + ",\n        ".join(native_deps_items) + ",\n    "
        else:
            native_deps_str = ""

        build_content = """# Auto-generated by rules_cpan for {dist_name} (XS extension)
load("@rules_cpan//cpan:defs.bzl", "cpan_xs")
load("@rules_perl//perl:defs.bzl", "perl_library")

package(default_visibility = ["//visibility:public"])

cpan_xs(
    name = "{dist_name}_xs",
    srcs = glob([
        "*.xs",
        "**/*.xs",
    ], allow_empty = True),
    cc_srcs = glob([
        "*.c",
        "**/*.c",
    ], exclude = [
        "_xs/**",
        "t/**",
        "fallback/**",
    ], allow_empty = True),
    defines = [{defines_str}],{exec_compat_str}{exec_reqs_str}
    output_loc = "{output_loc}",{tags_str}{target_compat_str}
    textual_hdrs = glob([
        "*.h",
        "**/*.h",
        "*.xs",
        "**/*.xs",
    ], allow_empty = True),
    typemaps = glob([
        "typemap",
        "**/typemap",
    ], allow_empty = True),
    deps = [{native_deps_str}],
)

perl_library(
    name = "{dist_name}",
    srcs = glob([{srcs_str}], allow_empty = True),
    data = [
        ":{dist_name}_xs",
    ] + glob([{data_str}], exclude = [{exclude_str}], allow_empty = True),
    includes = [{includes_str}],{exec_compat_str}{tags_str}{target_compat_str}
    deps = [{deps_str}],
)
""".format(
            dist_name = ctx.attr.dist_name,
            output_loc = output_loc,
            srcs_str = srcs_str,
            data_str = data_str,
            exclude_str = exclude_str,
            defines_str = defines_str,
            native_deps_str = native_deps_str,
            deps_str = deps_str,
            exec_compat_str = exec_compat_str,
            exec_reqs_str = exec_reqs_str,
            includes_str = includes_str,
            tags_str = tags_str,
            target_compat_str = target_compat_str,
        )

    ctx.file("BUILD.bazel", build_content)

cpan_dist_repo = repository_rule(
    doc = "Hermetically fetches and builds a single CPAN distribution.",
    implementation = _cpan_dist_repo_impl,
    attrs = {
        "build_file": attr.label(
            doc = "Optional overlay BUILD file replacing generated build rules.",
            default = None,
        ),
        "defines": attr.string_list(
            doc = "Optional preprocessor defines for XS compilation.",
            default = [],
        ),
        "dist_name": attr.string(
            doc = "Original CPAN distribution name.",
            mandatory = True,
        ),
        "exec_compatible_with": attr.string_list(
            doc = "Optional execution platform constraints.",
            default = [],
        ),
        "execution_requirements": attr.string_dict(
            doc = "Optional execution requirements for actions (e.g. {'no-remote': '1'}).",
            default = {},
        ),
        "includes": attr.string_list(
            doc = "Optional extra include paths for Perl modules.",
            default = [],
        ),
        "is_xs": attr.bool(
            doc = "Whether this distribution is an XS C extension.",
            default = False,
        ),
        "native_deps": attr.string_list(
            doc = "Optional native C/C++ library dependencies (e.g. @zlib).",
            default = [],
        ),
        "output_loc": attr.string(
            doc = "Optional DynaLoader/XSLoader auto/ directory location for an XS module.",
            default = "",
        ),
        "patch_args": attr.string_list(
            default = ["-p0"],
        ),
        "patch_cmds": attr.string_list(
            doc = "Optional bash patch commands to run after extraction.",
            default = [],
        ),
        "patch_cmds_win": attr.string_list(
            doc = "Optional Windows batch commands to run after extraction.",
            default = [],
        ),
        "patch_tool": attr.string(
            default = "",
        ),
        "patches": attr.label_list(
            doc = "Optional patch files to apply.",
            default = [],
        ),
        "provides": attr.string_list(
            doc = "Perl packages provided by this distribution.",
            default = [],
        ),
        "runtime_deps": attr.string_list(
            doc = "Labels of runtime CPAN distribution dependencies.",
            default = [],
        ),
        "sha256": attr.string(
            doc = "SHA256 checksum of the upstream tarball.",
            mandatory = True,
        ),
        "strip_prefix": attr.string(
            doc = "Directory prefix to strip from archive.",
            default = "",
        ),
        "extra_tags": attr.string_list(
            doc = "Optional target tags to add to generated BUILD targets.",
            default = [],
        ),
        "target_compatible_with": attr.string_list(
            doc = "Optional target platform constraints (e.g. ['@platforms//os:linux']).",
            default = [],
        ),
        "url": attr.string(
            doc = "Upstream archive download URL.",
            mandatory = True,
        ),
        "version": attr.string(
            doc = "Distribution release version.",
            default = "",
        ),
    },
)

def _cpan_hub_repo_impl(ctx):
    direct_set = {d: True for d in ctx.attr.direct_deps}
    has_direct = len(direct_set) > 0 or len(ctx.attr.injected_targets) > 0

    root_lines = [
        "# Auto-generated hub repository for rules_cpan (%s)" % ctx.attr.hub_name,
        "load(\"@rules_perl//perl:defs.bzl\", \"perl_test\")",
        "",
        "package(default_visibility = [\"//visibility:public\"])",
        "",
    ]

    all_dists_keys = dict(ctx.attr.all_dists)
    for dist_name in ctx.attr.injected_targets:
        if dist_name not in all_dists_keys:
            all_dists_keys[dist_name] = ""

    declared_tests = []
    manual_tests_set = {d: True for d in ctx.attr.manual_tests}

    for dist_name, repo_name in all_dists_keys.items():
        is_direct = dist_name in direct_set or dist_name in ctx.attr.injected_targets
        vis = "[\"//visibility:public\"]" if (is_direct or not has_direct) else "[\"//visibility:private\"]"

        if dist_name in ctx.attr.injected_targets:
            actual = ctx.attr.injected_targets[dist_name]
        else:
            actual = "@{repo_name}//:{dist_name}".format(
                repo_name = repo_name,
                dist_name = dist_name,
            )

        # Root alias: @cpan//:Algorithm-Diff
        root_lines.append("""alias(
    name = "{dist_name}",
    actual = "{actual}",
    visibility = {vis},
)
""".format(
            dist_name = dist_name,
            actual = actual,
            vis = vis,
        ))

        # Test generation for requested modules
        should_test = is_direct if has_direct else True
        if should_test:
            primary_mod = ctx.attr.test_modules.get(dist_name, "")
            if not primary_mod:
                provides = ctx.attr.dist_provides.get(dist_name, [])
                primary_mod = get_primary_module(dist_name, provides)
            test_file_name = "test_%s.t" % sanitize_repo_name(dist_name)
            test_content = """#!/usr/bin/env perl
use strict;
use warnings;
use Test::More;

BEGIN {{
    Test::More::use_ok('{primary_mod}') or Test::More::BAIL_OUT("Failed to load {primary_mod}");
}}

Test::More::done_testing();
""".format(primary_mod = primary_mod)
            ctx.file(test_file_name, test_content)

            cur_tags = list(ctx.attr.test_tags.get(dist_name, []))
            if dist_name in manual_tests_set:
                if "manual" not in cur_tags:
                    cur_tags.append("manual")

            if cur_tags:
                tags_str = "\n    tags = [\n        " + ",\n        ".join(['"%s"' % t for t in cur_tags]) + ",\n    ],"
            else:
                tags_str = ""

            test_target_name = "{dist_name}_test".format(dist_name = dist_name)
            root_lines.append("""perl_test(
    name = "{test_target_name}",
    size = "small",
    srcs = ["{test_file_name}"],{tags_str}
    deps = [":{dist_name}"],
)

alias(
    name = "test_{dist_name}",
    actual = ":{test_target_name}",
)
""".format(
                test_target_name = test_target_name,
                dist_name = dist_name,
                test_file_name = test_file_name,
                tags_str = tags_str,
            ))
            declared_tests.append(":{test_target_name}".format(test_target_name = test_target_name))

            sub_test_alias = """
alias(
    name = "test",
    actual = "//:{test_target_name}",
)
""".format(test_target_name = test_target_name)
        else:
            sub_test_alias = ""

        # Subpackage alias: @cpan//Algorithm-Diff (resolves to @cpan//Algorithm-Diff:Algorithm-Diff)
        sub_content = """# Auto-generated package alias for {dist_name}
package(default_visibility = ["//visibility:public"])

alias(
    name = "{dist_name}",
    actual = "{actual}",
    visibility = {vis},
){sub_test_alias}""".format(
            dist_name = dist_name,
            actual = actual,
            vis = vis,
            sub_test_alias = sub_test_alias,
        )
        ctx.file(dist_name + "/BUILD.bazel", sub_content)

    tests_items = ['"%s"' % t for t in declared_tests]
    if tests_items:
        tests_str = "\n        " + ",\n        ".join(tests_items) + ",\n    "
    else:
        tests_str = ""

    root_lines.append("""test_suite(
    name = "test-rules-cpan-modules",
    tags = ["-manual"],
    tests = [{tests_str}],
)
""".format(tests_str = tests_str))

    ctx.file("BUILD.bazel", "\n".join(root_lines))

cpan_hub_repo = repository_rule(
    doc = "Generates a clean hub repository providing distribution aliases with visibility controls.",
    implementation = _cpan_hub_repo_impl,
    attrs = {
        "all_dists": attr.string_dict(
            doc = "Mapping from distribution name to internal repo name.",
            mandatory = True,
        ),
        "direct_deps": attr.string_list(
            doc = "Direct top-level dependencies exposed with public visibility.",
            default = [],
        ),
        "dist_provides": attr.string_list_dict(
            doc = "Provided packages per distribution.",
            default = {},
        ),
        "hub_name": attr.string(
            doc = "Configured name of this hub repository.",
            mandatory = True,
        ),
        "injected_targets": attr.string_dict(
            doc = "Mapping from distribution name to injected Bazel target label.",
            default = {},
        ),
        "manual_tests": attr.string_list(
            doc = "List of distribution names whose tests should be marked as manual.",
            default = [],
        ),
        "test_modules": attr.string_dict(
            doc = "Optional mapping from distribution name to custom Perl package to test.",
            default = {},
        ),
        "test_tags": attr.string_list_dict(
            doc = "Optional test tags per distribution.",
            default = {},
        ),
    },
)
