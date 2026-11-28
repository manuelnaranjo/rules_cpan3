"""Repository rules for rules_cpan distributions and hub repository."""

def sanitize_repo_name(name):
    """Sanitize distribution names for Bazel repository names.

    Args:
        name: Distribution name to sanitize.

    Returns:
        Sanitized repository name.
    """
    res = ""
    for i in range(len(name)):
        c = name[i]
        if (c >= "a" and c <= "z") or (c >= "A" and c <= "Z") or (c >= "0" and c <= "9") or c in ["-", "_", "."]:
            res += c
        else:
            res += "_"
    return res

def sanitize_target_name(name):
    """Sanitize names for Bazel target names.

    Args:
        name: Name to sanitize.

    Returns:
        Sanitized target name.
    """
    res = ""
    for i in range(len(name)):
        c = name[i]
        if (c >= "a" and c <= "z") or (c >= "A" and c <= "Z") or (c >= "0" and c <= "9") or c in ["-", "_"]:
            res += c
        else:
            res += "_"
    return res

def get_strip_prefix(url):
    """Computes strip prefix from archive url.

    Args:
        url: Archive URL.

    Returns:
        Computed strip prefix string.
    """
    filename = url.split("/")[-1]
    for ext in [".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tar.xz", ".txz", ".zip"]:
        if filename.endswith(ext):
            return filename[:-len(ext)]
    return ""

def _find_test_files(ctx):
    t_path = ctx.path("t")
    if not t_path.exists:
        return []
    test_files = []
    dirs_to_visit = [t_path]
    for _ in range(100):
        if not dirs_to_visit:
            break
        current_dir = dirs_to_visit.pop(0)
        for child in current_dir.readdir():
            if child.is_dir:
                dirs_to_visit.append(child)
            elif child.basename.endswith(".t"):
                rel = str(child)[len(str(ctx.path(""))) + 1:]
                test_files.append(rel)
    return test_files

def _find_test_includes(ctx):
    t_path = ctx.path("t")
    if not t_path.exists:
        return []
    include_dirs = ["t"]
    dirs_to_visit = [t_path]
    for _ in range(100):
        if not dirs_to_visit:
            break
        curr = dirs_to_visit.pop(0)
        has_pm = False
        for child in curr.readdir():
            if child.is_dir:
                dirs_to_visit.append(child)
            elif child.basename.endswith(".pm"):
                has_pm = True
        if has_pm:
            rel = str(curr)[len(str(ctx.path(""))) + 1:]
            if rel not in include_dirs:
                include_dirs.append(rel)
    return include_dirs

def _cpan_dist_repo_impl(ctx):
    url = ctx.attr.url
    sha256 = ctx.attr.sha256
    strip_prefix = ctx.attr.strip_prefix

    ctx.download_and_extract(
        url = url,
        sha256 = sha256,
        stripPrefix = strip_prefix if strip_prefix else "",
    )

    if not strip_prefix:
        entries = ctx.path(".").readdir()
        subdirs = [e for e in entries if e.is_dir and e.basename not in [".git", "external"]]
        files = [e for e in entries if not e.is_dir]
        if len(subdirs) == 1 and len(files) == 0:
            single_dir = subdirs[0]
            res = ctx.execute(["bash", "-c", 'shopt -s dotglob && mv "{dir}"/* . && rmdir "{dir}"'.format(dir = str(single_dir))])
            if res.return_code != 0:
                fail("Failed to flatten archive directory {}: {}".format(single_dir, res.stderr))

    test_files = _find_test_files(ctx)
    test_includes = _find_test_includes(ctx)

    dependencies = json.decode(ctx.attr.dependencies)
    all_dists_map = json.decode(ctx.attr.all_dists)

    configure_deps = dependencies.get("configure", [])
    build_deps = dependencies.get("build", [])
    runtime_deps = dependencies.get("runtime", [])
    test_deps_names = dependencies.get("test", [])

    resolved_build_deps = []
    for d in configure_deps + build_deps + runtime_deps:
        if d in all_dists_map:
            target_label = "@" + all_dists_map[d] + "//:build"
            if target_label not in resolved_build_deps:
                resolved_build_deps.append(target_label)

    resolved_runtime_deps = []
    for d in runtime_deps:
        if d in all_dists_map:
            target_label = "@" + all_dists_map[d] + "//:" + d
            if target_label not in resolved_runtime_deps:
                resolved_runtime_deps.append(target_label)

    resolved_test_deps = [":test_lib"]
    for d in test_deps_names:
        if d in all_dists_map:
            target_label = "@" + all_dists_map[d] + "//:" + d
            if target_label not in resolved_test_deps:
                resolved_test_deps.append(target_label)

    test_target_names = []
    test_blocks = []

    for t_file in test_files:
        clean_name = t_file
        if clean_name.endswith(".t"):
            clean_name = clean_name[:-2]
        t_name = "test_" + sanitize_target_name(clean_name)
        test_target_names.append('":%s"' % t_name)
        test_blocks.append("""perl_test(
    name = "{name}",
    size = "small",
    srcs = ["{src}"],
    deps = {deps},
)""".format(
            name = t_name,
            src = t_file,
            deps = json.encode(resolved_test_deps),
        ))

    build_content = """# Auto-generated BUILD.bazel for {dist_name}
load("@rules_cpan//cpan:defs.bzl", "cpan_dist")
load("@rules_perl//perl:perl.bzl", "perl_library", "perl_test")

package(default_visibility = ["//visibility:public"])

# 1. Custom foreign_cc build rule
cpan_dist(
    name = "build",
    dist_name = "{dist_name}",
    srcs = glob(["**"], exclude = [
        "BUILD.bazel",
        "BUILD",
        "WORKSPACE.bazel",
        "WORKSPACE",
        "MODULE.bazel",
    ], allow_empty = True),
    deps = {build_deps},
)

# 2. Wrapped install directory into perl_library
perl_library(
    name = "{dist_name}",
    data = [":build"],
    includes = ["build/lib/perl5", "build/lib/perl5/x86_64-linux-thread-multi"],
    deps = {runtime_deps},
)

alias(
    name = "dist",
    actual = ":{dist_name}",
)

# Helper library providing distribution runtime and test helper sources
perl_library(
    name = "test_lib",
    srcs = glob(["t/**/*.pm", "t/*.pm"], allow_empty = True),
    data = glob(["**"], exclude = [
        "BUILD.bazel",
        "BUILD",
        "WORKSPACE.bazel",
        "WORKSPACE",
        "MODULE.bazel",
        "t/**/*.t",
        "t/*.t",
    ], allow_empty = True),
    includes = {test_includes},
    deps = [":{dist_name}"],
)

# 3. Unit test targets for .t files in t/
{test_blocks}

test_suite(
    name = "test",
    tests = [{tests_joined}],
)
""".format(
        dist_name = ctx.attr.dist_name,
        build_deps = json.encode(resolved_build_deps),
        runtime_deps = json.encode(resolved_runtime_deps),
        test_includes = json.encode(test_includes),
        test_blocks = "\n\n".join(test_blocks),
        tests_joined = ", ".join(test_target_names),
    )

    ctx.file("BUILD.bazel", build_content)

cpan_dist_repo = repository_rule(
    doc = "Downloads and builds a CPAN distribution in an isolated repository using custom rules_foreign_cc.",
    implementation = _cpan_dist_repo_impl,
    attrs = {
        "all_dists": attr.string(
            doc = "JSON-encoded mapping of all distribution names to repo names in this hub.",
            default = "{}",
        ),
        "dependencies": attr.string(
            doc = "JSON-encoded dependencies dictionary from lockfile.",
            default = "{}",
        ),
        "dist_name": attr.string(
            doc = "CPAN distribution name.",
            mandatory = True,
        ),
        "hub_name": attr.string(
            doc = "CPAN hub name.",
            default = "cpan",
        ),
        "is_xs": attr.bool(
            doc = "Whether distribution contains XS code.",
            default = False,
        ),
        "provides": attr.string_list(
            doc = "Packages provided by this distribution.",
            default = [],
        ),
        "sha256": attr.string(
            doc = "SHA256 checksum of upstream archive.",
            mandatory = True,
        ),
        "strip_prefix": attr.string(
            doc = "Strip prefix for extracting the archive.",
            default = "",
        ),
        "url": attr.string(
            doc = "Upstream archive URL.",
            mandatory = True,
        ),
        "version": attr.string(
            doc = "Distribution version.",
            default = "",
        ),
    },
)

def _cpan_hub_repo_impl(ctx):
    direct_set = {d: True for d in ctx.attr.direct_deps}
    has_direct = len(direct_set) > 0

    root_lines = [
        "# Auto-generated hub repository for rules_cpan (%s)" % ctx.attr.hub_name,
        "",
        "package(default_visibility = [\"//visibility:public\"])",
        "",
    ]

    all_dists_keys = dict(ctx.attr.all_dists)
    declared_tests = []

    for dist_name, repo_name in all_dists_keys.items():
        is_direct = dist_name in direct_set or not has_direct
        vis = '["//visibility:public"]' if is_direct else '["//visibility:private"]'

        actual = "@{repo_name}//:{dist_name}".format(repo_name = repo_name, dist_name = dist_name)
        actual_test = "@{repo_name}//:test".format(repo_name = repo_name)

        root_lines.append("""alias(
    name = "{dist_name}",
    actual = "{actual}",
    visibility = {vis},
)

test_suite(
    name = "test_{dist_name}",
    tests = ["{actual_test}"],
    visibility = {vis},
)

test_suite(
    name = "{dist_name}_test",
    tests = ["{actual_test}"],
    visibility = {vis},
)
""".format(
            dist_name = dist_name,
            actual = actual,
            actual_test = actual_test,
            vis = vis,
        ))

        declared_tests.append(":{dist_name}_test".format(dist_name = dist_name))

        sub_content = """# Auto-generated package alias for {dist_name}
package(default_visibility = ["//visibility:public"])

alias(
    name = "{dist_name}",
    actual = "{actual}",
    visibility = {vis},
)

test_suite(
    name = "test",
    tests = ["{actual_test}"],
    visibility = {vis},
)
""".format(
            dist_name = dist_name,
            actual = actual,
            actual_test = actual_test,
            vis = vis,
        )
        ctx.file(dist_name + "/BUILD.bazel", sub_content)

    tests_items = ['"%s"' % t for t in sorted(declared_tests)]
    if tests_items:
        tests_str = "\n        " + ",\n        ".join(tests_items) + ",\n    "
    else:
        tests_str = ""

    root_lines.append("""test_suite(
    name = "all_tests",
    tags = ["-manual"],
    tests = [{tests_str}],
)

test_suite(
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
            doc = "Mapping from distribution name to repo name.",
            default = {},
        ),
        "direct_deps": attr.string_list(
            doc = "Direct top-level dependencies exposed with public visibility.",
            default = [],
        ),
        "hub_name": attr.string(
            doc = "Configured name of this hub repository.",
            mandatory = True,
        ),
    },
)
