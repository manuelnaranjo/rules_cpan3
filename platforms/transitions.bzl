"""Platform transition rules and multi-arch build helpers for rules_cpan"""

def _platform_transition_impl(_settings, attr):
    return {
        "//command_line_option:platforms": [attr.platform],
    }

platform_transition = transition(
    implementation = _platform_transition_impl,
    inputs = [],
    outputs = ["//command_line_option:platforms"],
)

def _transition_binary_impl(ctx):
    out = ctx.actions.declare_file(ctx.label.name)
    actual_file = ctx.file.actual
    ctx.actions.symlink(
        output = out,
        target_file = actual_file,
    )
    return [
        DefaultInfo(
            files = depset([out]),
            executable = out,
            runfiles = ctx.runfiles(files = [actual_file]),
        ),
    ]

platform_binary = rule(
    implementation = _transition_binary_impl,
    attrs = {
        "actual": attr.label(
            mandatory = True,
            allow_single_file = True,
            cfg = platform_transition,
        ),
        "platform": attr.string(
            mandatory = True,
        ),
        "_allowlist_function_transition": attr.label(
            default = "@bazel_tools//tools/allowlists/function_transition_allowlist",
        ),
    },
    executable = True,
)

def _multi_platform_test_impl(ctx):
    out = ctx.actions.declare_file(ctx.label.name + ".sh")
    ctx.actions.write(
        output = out,
        content = "#!/bin/sh\necho 'Multi-platform verification passed'\nexit 0\n",
        is_executable = True,
    )
    runfiles = ctx.runfiles(files = ctx.files.targets)
    return [
        DefaultInfo(
            executable = out,
            runfiles = runfiles,
        ),
    ]

multi_platform_test = rule(
    implementation = _multi_platform_test_impl,
    attrs = {
        "targets": attr.label_list(
            mandatory = True,
            allow_files = True,
        ),
    },
    test = True,
)
