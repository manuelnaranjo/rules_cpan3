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

def _compute_output_loc(dist_name, provides):
    """Compute the DynaLoader/XSLoader auto/ directory location for an XS module."""
    canonical_mod = dist_name.replace("-", "::")
    primary_mod = canonical_mod
    if provides:
        if canonical_mod in provides:
            primary_mod = canonical_mod
        else:
            primary_mod = provides[0]

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

    if not ctx.attr.is_xs:
        # Pure Perl distribution
        build_content = """# Auto-generated by rules_cpan for {dist_name}
load("@rules_perl//perl:defs.bzl", "perl_library")

package(default_visibility = ["//visibility:public"])

perl_library(
    name = "{dist_name}",
    srcs = glob([
        "lib/**/*.pm",
        "lib/**/*.pod",
        "*.pm",
    ], allow_empty = True),
    data = glob([
        "lib/**/*",
    ], exclude = [
        "lib/**/*.pm",
        "lib/**/*.pod",
    ], allow_empty = True),
    includes = [
        ".",
        "lib",
    ],{exec_compat_str}{tags_str}{target_compat_str}
    deps = [{deps_str}],
)
""".format(
            dist_name = ctx.attr.dist_name,
            deps_str = deps_str,
            exec_compat_str = exec_compat_str,
            tags_str = tags_str,
            target_compat_str = target_compat_str,
        )
    else:
        # XS (C extension) module
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
    srcs = glob([
        "lib/**/*.pm",
        "lib/**/*.pod",
        "*.pm",
    ], allow_empty = True),
    data = [
        ":{dist_name}_xs",
    ] + glob([
        "lib/**/*",
    ], exclude = [
        "lib/**/*.pm",
        "lib/**/*.pod",
    ], allow_empty = True),
    includes = [
        ".",
        "lib",
    ],{exec_compat_str}{tags_str}{target_compat_str}
    deps = [{deps_str}],
)
""".format(
            dist_name = ctx.attr.dist_name,
            output_loc = output_loc,
            defines_str = defines_str,
            native_deps_str = native_deps_str,
            deps_str = deps_str,
            exec_compat_str = exec_compat_str,
            exec_reqs_str = exec_reqs_str,
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
        "is_xs": attr.bool(
            doc = "Whether this distribution is an XS C extension.",
            default = False,
        ),
        "native_deps": attr.string_list(
            doc = "Optional native C/C++ library dependencies (e.g. @zlib).",
            default = [],
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

    root_lines = [
        "# Auto-generated hub repository for rules_cpan (%s)" % ctx.attr.hub_name,
        "package(default_visibility = [\"//visibility:public\"])",
        "",
    ]

    for dist_name, repo_name in ctx.attr.all_dists.items():
        is_direct = dist_name in direct_set
        vis = "[\"//visibility:public\"]" if is_direct else "[\"//visibility:private\"]"

        # Root alias: @cpan//:Algorithm-Diff
        root_lines.append("""alias(
    name = "{dist_name}",
    actual = "@{repo_name}//:{dist_name}",
    visibility = {vis},
)
""".format(
            dist_name = dist_name,
            repo_name = repo_name,
            vis = vis,
        ))

        # Subpackage alias: @cpan//Algorithm-Diff (resolves to @cpan//Algorithm-Diff:Algorithm-Diff)
        sub_content = """# Auto-generated package alias for {dist_name}
package(default_visibility = ["//visibility:public"])

alias(
    name = "{dist_name}",
    actual = "@{repo_name}//:{dist_name}",
    visibility = {vis},
)
""".format(
            dist_name = dist_name,
            repo_name = repo_name,
            vis = vis,
        )
        ctx.file(dist_name + "/BUILD.bazel", sub_content)

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
    },
)
