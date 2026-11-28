"""Custom foreign_cc build rule for CPAN distributions using hermetic perl and ape tools."""

load("@bazel_skylib//lib:paths.bzl", "paths")
load("@rules_foreign_cc//foreign_cc:providers.bzl", "ForeignCcArtifactInfo", "ForeignCcDepsInfo")
load("@rules_perl//perl:perl_info.bzl", "PerlInfo")

_DEFAULT_APE_TOOLS = [
    "@ape//ape:make",
    "@ape//ape:sed",
    "@ape//ape:grep",
    "@ape//ape:awk",
    "@ape//ape:tar",
    "@ape//ape:patch",
    "@ape//ape:cat",
    "@ape//ape:cp",
    "@ape//ape:mv",
    "@ape//ape:rm",
    "@ape//ape:mkdir",
    "@ape//ape:diff",
    "@ape//ape:find",
    "@ape//ape:uname",
    "@ape//ape:echo",
]

def _cpan_dist_impl(ctx):
    out_dir = ctx.actions.declare_directory(ctx.label.name)

    perl_toolchain = ctx.toolchains["@rules_perl//perl:toolchain_type"].perl_runtime
    perl_interpreter = perl_toolchain.interpreter
    perl_runtime = perl_toolchain.runtime

    # Gather inputs
    transitive_inputs = [
        perl_runtime,
        depset([perl_interpreter]),
        depset(ctx.files._tools),
        depset(ctx.files.srcs),
    ]

    dep_artifacts = []
    dep_include_paths = []
    for dep in ctx.attr.deps:
        transitive_inputs.append(dep[DefaultInfo].files)
        transitive_inputs.append(dep[DefaultInfo].default_runfiles.files)
        if ForeignCcDepsInfo in dep:
            dep_artifacts.append(dep[ForeignCcDepsInfo].artifacts)
        if PerlInfo in dep:
            for inc in dep[PerlInfo].includes.to_list():
                dep_include_paths.append(inc)

        # Also collect directories from DefaultInfo files and runfiles
        for f in dep[DefaultInfo].files.to_list() + dep[DefaultInfo].default_runfiles.files.to_list():
            if f.is_directory or f.basename == "build":
                dep_include_paths.append(f.path + "/lib/perl5")
                transitive_inputs.append(depset([f]))

    all_artifacts = depset(transitive = dep_artifacts)
    for art in all_artifacts.to_list():
        dep_include_paths.append(art.gen_dir.path + "/lib/perl5")
        transitive_inputs.append(depset([art.gen_dir]))

    seen_paths = {}
    unique_include_paths = []
    for inc in dep_include_paths:
        if inc not in seen_paths:
            seen_paths[inc] = True
            unique_include_paths.append(inc)

    # Locate source directory containing top-level Makefile.PL or Build.PL
    src_root = ""
    min_depth = 999999
    for f in ctx.files.srcs:
        if f.basename in ["Makefile.PL", "Build.PL"]:
            depth = len(f.dirname.split("/")) if f.dirname else 0
            if depth < min_depth:
                min_depth = depth
                src_root = f.dirname

    if not src_root and ctx.files.srcs:
        min_depth = 999999
        for f in ctx.files.srcs:
            depth = len(f.dirname.split("/")) if f.dirname else 0
            if depth < min_depth:
                min_depth = depth
                src_root = f.dirname

    tool_links = []
    for tool in ctx.files._tools:
        tool_links.append('ln -sf "$(pwd)/{path}" "$TOOLS_DIR/{basename}"'.format(
            path = tool.path,
            basename = tool.basename,
        ))

    script_lines = [
        "#!/usr/bin/env bash",
        "set -euo pipefail",
        "",
        "# Set up hermetic tools from @ape and rules_perl",
        'TOOLS_DIR="$(mktemp -d -t cpan_tools_XXXXXX)"',
        'BUILD_DIR="$(mktemp -d -t cpan_build_XXXXXX)"',
        'cleanup() { rm -rf "$TOOLS_DIR" "$BUILD_DIR"; }',
        "trap cleanup EXIT",
        "",
    ]
    script_lines.extend(tool_links)
    script_lines.extend([
        'if [ -f "$TOOLS_DIR/make" ] && [ ! -f "$TOOLS_DIR/gmake" ]; then',
        '    ln -sf "$TOOLS_DIR/make" "$TOOLS_DIR/gmake"',
        "fi",
        'ln -sf "$(pwd)/{perl}" "$TOOLS_DIR/perl"'.format(perl = perl_interpreter.path),
        'ln -sf "$(pwd)/{perl}" "$TOOLS_DIR/perl5"'.format(perl = perl_interpreter.path),
        'export PATH="$TOOLS_DIR:$PATH"',
        "",
        "# Setup PERL5LIB for dependent CPAN modules",
        "PERL5LIB_DIRS=()",
    ])

    for inc in unique_include_paths:
        script_lines.append("""if [ -d "{inc}" ]; then
    PERL5LIB_DIRS+=("$(pwd)/{inc}")
elif [ -d "external/{inc}" ]; then
    PERL5LIB_DIRS+=("$(pwd)/external/{inc}")
fi""".format(inc = inc))

    script_lines.extend([
        "if [ ${#PERL5LIB_DIRS[@]} -gt 0 ]; then",
        '    export PERL5LIB="$(IFS=:; echo "${PERL5LIB_DIRS[*]}"):${PERL5LIB:-}"',
        "fi",
        "",
        "# Non-interactive automated build flags",
        "export PERL_MM_USE_DEFAULT=1",
        "export AUTOMATED_TESTING=1",
        "export NONINTERACTIVE_TESTING=1",
        "export NO_NETWORK_TESTING=1",
        "export PERL_USE_UNSAFE_INC=1",
        "",
        "# Prepare build tree",
        'OUT_ABS="$(readlink -f "{out_dir}")"'.format(out_dir = out_dir.path),
        'mkdir -p "$OUT_ABS/lib/perl5"',
        "",
        'SRC_ROOT="$(pwd)/{src_root}"'.format(src_root = src_root),
        'cp -RL "$SRC_ROOT/." "$BUILD_DIR/"',
        'cd "$BUILD_DIR"',
        "chmod -R u+w .",
        'export PERL5LIB=".:${PERL5LIB:-}"',
        "",
        "# Run configure and build without running tests",
        "if [ -f Makefile.PL ]; then",
        '    perl Makefile.PL INSTALL_BASE="$OUT_ABS" INSTALLMAN1DIR=none INSTALLMAN3DIR=none < /dev/null',
        "    make < /dev/null",
        "    make install < /dev/null",
        "elif [ -f Build.PL ]; then",
        '    perl Build.PL --install_base="$OUT_ABS" --install_path bindoc=none --install_path libdoc=none < /dev/null',
        "    perl ./Build < /dev/null",
        "    perl ./Build install < /dev/null",
        "elif [ -d lib ]; then",
        '    cp -RL lib/. "$OUT_ABS/lib/perl5/"',
        "else",
        '    echo "Error: Neither Makefile.PL nor Build.PL found in $(pwd)" >&2',
        "    exit 1",
        "fi",
    ])

    ctx.actions.run_shell(
        outputs = [out_dir],
        inputs = depset(transitive = transitive_inputs),
        command = "\n".join(script_lines),
        mnemonic = "CpanDistBuild",
        progress_message = "Building CPAN distribution %{label}",
        execution_requirements = {
            "block-network": "",
        },
    )

    workspace_name = ctx.label.workspace_name
    if not workspace_name:
        workspace_name = ctx.workspace_name

    include_path = paths.normalize("{}/{}/lib/perl5".format(workspace_name, out_dir.basename))
    transitive_includes = [dep[PerlInfo].includes for dep in ctx.attr.deps if PerlInfo in dep]

    this_art = ForeignCcArtifactInfo(
        gen_dir = out_dir,
        bin_dir_name = "bin",
        lib_dir_name = "lib/perl5",
        include_dir_name = "include",
        dll_dir_name = "",
    )

    return [
        DefaultInfo(
            files = depset([out_dir]),
            runfiles = ctx.runfiles(files = [out_dir]),
        ),
        PerlInfo(
            transitive_perl_sources = depset(),
            includes = depset([include_path], transitive = transitive_includes),
        ),
        this_art,
        ForeignCcDepsInfo(
            artifacts = depset([this_art], transitive = dep_artifacts),
        ),
    ]

cpan_dist = rule(
    implementation = _cpan_dist_impl,
    attrs = {
        "dist_name": attr.string(
            doc = "Distribution name (e.g. Algorithm-Diff)",
        ),
        "srcs": attr.label_list(
            doc = "Source files of the CPAN distribution",
            allow_files = True,
        ),
        "deps": attr.label_list(
            doc = "Dependent CPAN distribution libraries",
            providers = [],
        ),
        "_tools": attr.label_list(
            default = _DEFAULT_APE_TOOLS,
            cfg = "exec",
        ),
    },
    toolchains = ["@rules_perl//perl:toolchain_type"],
)
