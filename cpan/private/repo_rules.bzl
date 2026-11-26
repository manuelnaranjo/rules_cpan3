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

def dist_to_bcr_module(dist_name):
    """Computes BCR module name: perl-<lowercase_with_hyphens>.

    Args:
        dist_name: CPAN distribution name (e.g. 'Algorithm-Diff').

    Returns:
        BCR module name (e.g. 'perl-algorithm-diff').
    """
    res = ""
    for i in range(len(dist_name)):
        c = dist_name[i].lower()
        if (c >= "a" and c <= "z") or (c >= "0" and c <= "9") or c in [".", "-"]:
            res += c
        else:
            res += "-"

    # Strip leading and trailing hyphens
    for _ in range(len(res)):
        if res.startswith("-"):
            res = res[1:]
        elif res.endswith("-"):
            res = res[:-1]
        else:
            break
    return "perl-" + res

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

def _cpan_hub_repo_impl(ctx):
    direct_set = {d: True for d in ctx.attr.direct_deps}
    has_direct = len(direct_set) > 0 or len(ctx.attr.injected_targets) > 0

    root_lines = [
        "# Auto-generated hub repository for rules_cpan (%s)" % ctx.attr.hub_name,
        "",
        "package(default_visibility = [\"//visibility:public\"])",
        "",
    ]

    all_dists_keys = dict(ctx.attr.all_dists)
    for dist_name in ctx.attr.injected_targets:
        if dist_name not in all_dists_keys:
            all_dists_keys[dist_name] = dist_to_bcr_module(dist_name)

    declared_tests = []

    for dist_name, bcr_mod in all_dists_keys.items():
        if not bcr_mod:
            bcr_mod = dist_to_bcr_module(dist_name)

        is_direct = dist_name in direct_set or dist_name in ctx.attr.injected_targets
        vis = "[\"//visibility:public\"]" if (is_direct or not has_direct) else "[\"//visibility:private\"]"

        if dist_name in ctx.attr.injected_targets:
            actual = ctx.attr.injected_targets[dist_name]
        else:
            actual = "@@{bcr_mod}+//:{bcr_mod}".format(
                bcr_mod = bcr_mod,
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

        # Root alias for BCR module name if distinct: @cpan//:perl-algorithm-diff
        if bcr_mod != dist_name:
            root_lines.append("""alias(
    name = "{bcr_mod}",
    actual = "{actual}",
    visibility = {vis},
)
""".format(
                bcr_mod = bcr_mod,
                actual = actual,
                vis = vis,
            ))

        sub_test_alias = ""

        # Test targets for injected dependencies
        if dist_name in ctx.attr.injected_targets:
            test_target_name = "{dist_name}_test".format(dist_name = dist_name)
            if "//" in actual:
                inj_repo = actual.split("//")[0]
                upstream_test = "{inj_repo}//:test".format(inj_repo = inj_repo)
            else:
                upstream_test = "{actual}_test".format(actual = actual)

            root_lines.append("""test_suite(
    name = "{test_target_name}",
    tags = ["-manual"],
    tests = ["{upstream_test}"],
)

alias(
    name = "test_{dist_name}",
    actual = ":{test_target_name}",
)
""".format(
                test_target_name = test_target_name,
                upstream_test = upstream_test,
                dist_name = dist_name,
            ))
            declared_tests.append(":{test_target_name}".format(test_target_name = test_target_name))

            sub_test_alias = """
alias(
    name = "test",
    actual = "//:{test_target_name}",
)
""".format(test_target_name = test_target_name)

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

        if bcr_mod != dist_name:
            ctx.file(bcr_mod + "/BUILD.bazel", """# Auto-generated package alias for {bcr_mod}
package(default_visibility = ["//visibility:public"])

alias(
    name = "{bcr_mod}",
    actual = "{actual}",
    visibility = {vis},
){sub_test_alias}""".format(
                bcr_mod = bcr_mod,
                actual = actual,
                vis = vis,
                sub_test_alias = sub_test_alias,
            ))

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
            doc = "Mapping from distribution name to BCR module name.",
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
        "injected_targets": attr.string_dict(
            doc = "Mapping from distribution name to injected Bazel target label.",
            default = {},
        ),
    },
)
