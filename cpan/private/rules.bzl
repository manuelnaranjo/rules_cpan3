"""Internal implementation rules for rules_cpan"""

load("@bazel_skylib//lib:new_sets.bzl", "sets")
load("@bazel_skylib//lib:paths.bzl", "paths")
load("@rules_cc//cc:defs.bzl", "CcInfo", "cc_common")
load("@rules_cc//cc:find_cc_toolchain.bzl", "find_cc_toolchain")

# buildifier: disable=bzl-visibility
load("@rules_perl//perl/private:perl_tool.bzl", "PerlToolInfo")

_MACOS_LINKOPTS = [
    "-undefined",
    "dynamic_lookup",
]

_MSVC_COMPILERS = ["msvc-cl", "clang-cl", "cl"]

def _has_constraint(ctx, constraint):
    return ctx.target_platform_has_constraint(constraint[platform_common.ConstraintValueInfo])

def _is_msvc(compiler):
    return compiler in _MSVC_COMPILERS

def _compile_flags(toolchain, cc_toolchain, is_windows):
    ccflags = toolchain.ccflags
    if is_windows and toolchain.cc and _is_msvc(toolchain.cc) != _is_msvc(cc_toolchain.compiler):
        ccflags = [flag for flag in ccflags if flag.startswith("-D")]
        if _is_msvc(cc_toolchain.compiler):
            ccflags.append("-D__inline__=__inline")
    raw_flags = ccflags + toolchain.cccdlflags
    clean_flags = []
    for flag in raw_flags:
        if flag.startswith("-I/usr") or flag.startswith("-I/opt"):
            continue
        clean_flags.append(flag)
    return clean_flags

def _dlext(toolchain, is_windows, is_macos):
    if toolchain.dlext:
        return "." + toolchain.dlext
    if is_windows:
        return ".dll"
    if is_macos:
        return ".bundle"
    return ".so"

def _libperl(ctx, toolchain):
    if toolchain.libperl == None:
        fail((
            "{}: the resolved perl toolchain has no import library for perl's shared " +
            "library (perl_toolchain.libperl), which an XS object on Windows must link against"
        ).format(ctx.label))
    return toolchain.libperl

def _compute_output_loc_rpaths(output_loc, deps, is_macos):
    """Computes runtime search paths (rpaths) for XS libraries in subdirectories.

    On Linux/macOS, if the XS shared library is placed in a subfolder
    (e.g. output_loc = auto/Foo/Bar/Bar.so), Bazel's default RUNPATH relative
    to the package root does not match the actual location of the .so at runtime.
    This helper computes and returns extra rpaths from output_loc to all dependent
    solib directories.
    """
    if not output_loc:
        return []

    dirname = paths.dirname(output_loc)
    depth = len([p for p in dirname.split("/") if p and p != "."])
    if depth == 0:
        return []

    solib_dirs = []
    for dep in deps:
        if CcInfo in dep:
            for li in dep[CcInfo].linking_context.linker_inputs.to_list():
                for lib_item in li.libraries:
                    dyn = lib_item.dynamic_library
                    if dyn:
                        sdir = paths.dirname(dyn.short_path)
                        if sdir not in solib_dirs:
                            solib_dirs.append(sdir)

    if not solib_dirs:
        return []

    origin_var = "@loader_path" if is_macos else "$ORIGIN"
    rf_dots = "/".join([".." for _ in range(depth + 1)])
    bin_dots = "/".join([".." for _ in range(depth + 2)])
    rpaths = []
    for sdir in solib_dirs:
        rpaths.append("-Wl,-rpath,%s/%s/_main/%s" % (origin_var, rf_dots, sdir))
        rpaths.append("-Wl,-rpath,%s/%s/%s" % (origin_var, bin_dots, sdir))
        rpaths.append("-Wl,-rpath,%s/%s/%s" % (origin_var, rf_dots, sdir))
    return rpaths

def _boot_def_file(ctx, srcs):
    xs_def = ctx.attr._xs_def[PerlToolInfo]
    out = ctx.actions.declare_file(ctx.label.name + ".def")

    args = ctx.actions.args()
    args.add(xs_def.main)
    args.add("--output", out)
    args.add_all(srcs)

    exec_reqs = {"supports-path-mapping": "1"}
    exec_reqs.update(ctx.attr.execution_requirements)

    ctx.actions.run(
        mnemonic = "PerlXsDef",
        outputs = [out],
        inputs = srcs,
        arguments = [args],
        progress_message = "Listing XS exports for %s" % out.short_path,
        executable = xs_def.interpreter,
        tools = xs_def.tools,
        execution_requirements = exec_reqs,
        toolchain = None,
    )

    return out

def _cpan_xs_cc_lib(ctx, toolchain, srcs, is_windows, is_macos):
    cc_toolchain = find_cc_toolchain(ctx)
    xs_headers = toolchain.xs_headers

    includes = [f.dirname for f in xs_headers.to_list()]

    textual_hdrs = []
    for hdrs in ctx.attr.textual_hdrs:
        for hdr in hdrs.files.to_list():
            textual_hdrs.append(hdr)
            includes.append(hdr.dirname)

    includes = sets.make(includes)
    includes = sets.to_list(includes)

    feature_configuration = cc_common.configure_features(
        ctx = ctx,
        cc_toolchain = cc_toolchain,
        requested_features = ctx.features,
        unsupported_features = ctx.disabled_features,
    )

    hdrs = [h for h in textual_hdrs if not h.basename.endswith(".xs")]

    # Pass compilation_contexts from deps so headers like zlib.h are available!
    (compilation_context, compilation_outputs) = cc_common.compile(
        actions = ctx.actions,
        name = ctx.label.name,
        feature_configuration = feature_configuration,
        cc_toolchain = cc_toolchain,
        srcs = srcs + ctx.files.cc_srcs,
        defines = ctx.attr.defines,
        public_hdrs = hdrs,
        additional_inputs = textual_hdrs,
        private_hdrs = xs_headers.to_list(),
        includes = includes,
        user_compile_flags = _compile_flags(toolchain, cc_toolchain, is_windows) + ctx.attr.copts,
        compilation_contexts = [dep[CcInfo].compilation_context for dep in ctx.attr.deps],
    )

    linkopts = list(ctx.attr.linkopts)
    additional_inputs = []
    variables_extension = {}
    if is_macos:
        linkopts.extend(_MACOS_LINKOPTS)
    if is_windows:
        libperl = _libperl(ctx, toolchain)
        additional_inputs.append(libperl)
        linkopts.append(libperl.path)

        def_file = _boot_def_file(ctx, srcs)
        additional_inputs.append(def_file)
        variables_extension["def_file_path"] = def_file.path
    else:
        linkopts.extend(_compute_output_loc_rpaths(ctx.attr.output_loc, ctx.attr.deps, is_macos))

    linking_outputs = cc_common.link(
        actions = ctx.actions,
        name = ctx.label.name,
        feature_configuration = feature_configuration,
        cc_toolchain = cc_toolchain,
        compilation_outputs = compilation_outputs,
        user_link_flags = linkopts,
        linking_contexts = [dep[CcInfo].linking_context for dep in ctx.attr.deps],
        additional_inputs = additional_inputs,
        variables_extension = variables_extension,
        output_type = "dynamic_library",
    )

    return CcInfo(
        compilation_context = compilation_context,
        linking_context = cc_common.create_linking_context(
            linker_inputs = depset([cc_common.create_linker_input(
                owner = ctx.label,
                libraries = depset([linking_outputs.library_to_link]),
            )]),
        ),
    )

def _cpan_xs_implementation(ctx):
    toolchain = ctx.toolchains["@rules_perl//perl:toolchain_type"].perl_runtime

    if not toolchain.supports_xs:
        fail((
            "{}: the resolved perl toolchain cannot load XS. " +
            "On Linux set --@rules_perl//perl/settings:xs=true"
        ).format(ctx.label))

    is_windows = _has_constraint(ctx, ctx.attr._windows_constraint)
    is_macos = _has_constraint(ctx, ctx.attr._macos_constraint)

    xsubpp = ctx.attr._xsubpp[PerlToolInfo]

    gen = []

    exec_reqs = {"supports-path-mapping": "1"}
    exec_reqs.update(ctx.attr.execution_requirements)

    for src in ctx.files.srcs:
        c_execpath = paths.replace_extension(src.path, ".c")
        out = ctx.actions.declare_file(paths.join("_xs", c_execpath))

        args = ctx.actions.args()
        args.add(xsubpp.main)
        args.add_all(ctx.files.typemaps, before_each = "--typemap")
        args.add("--output", out)
        args.add(src)

        # Include textual_hdrs as inputs so xsubpp's INCLUDE directive can find included .xs files
        ctx.actions.run(
            mnemonic = "PerlTranslitterate",
            outputs = [out],
            inputs = [src] + ctx.files.typemaps + ctx.files.textual_hdrs,
            arguments = [args],
            progress_message = "Translitterating %s to %s" % (src.short_path, out.short_path),
            executable = xsubpp.interpreter,
            tools = xsubpp.tools,
            execution_requirements = exec_reqs,
            toolchain = None,
        )

        gen.append(out)

    cc_info = _cpan_xs_cc_lib(ctx, toolchain, gen, is_windows, is_macos)
    lib = cc_info.linking_context.linker_inputs.to_list()[0].libraries[0]
    dyn_lib = lib.dynamic_library

    ext = _dlext(toolchain, is_windows, is_macos)
    if ctx.attr.output_loc:
        output_loc = ctx.attr.output_loc
        if "." not in paths.basename(output_loc):
            output_loc = output_loc + ext
    else:
        output_loc = ctx.label.name + ext

    if dyn_lib.path == paths.join(ctx.bin_dir.path, ctx.label.workspace_root, ctx.label.package, output_loc):
        output = dyn_lib
    else:
        output = ctx.actions.declare_file(output_loc)
        ctx.actions.symlink(output = output, target_file = dyn_lib)

    runfiles = ctx.runfiles(files = [output])
    for dep in ctx.attr.deps:
        runfiles = runfiles.merge(dep[DefaultInfo].default_runfiles)

    return [
        cc_info,
        DefaultInfo(
            files = depset([output]),
            runfiles = runfiles,
        ),
    ]

cpan_xs = rule(
    doc = """Builds a Perl XS extension for CPAN distributions with full CcInfo compilation context propagation.""",
    attrs = {
        "cc_srcs": attr.label_list(
            doc = "Additional C or C++ source files compiled and linked into the extension.",
            allow_files = [".c", ".cc"],
        ),
        "copts": attr.string_list(
            doc = "Extra compiler flags passed to the C/C++ compilation.",
        ),
        "defines": attr.string_list(
            doc = "Preprocessor defines (e.g. -DNAME or -DNAME=value) for compilation.",
        ),
        "deps": attr.label_list(
            doc = "Targets providing CcInfo (e.g. cc_library) to link with the extension.",
            providers = [CcInfo],
        ),
        "execution_requirements": attr.string_dict(
            doc = "Execution requirements for Perl actions spawned by this rule (e.g. {'no-remote': '1'}).",
            default = {},
        ),
        "linkopts": attr.string_list(
            doc = "Extra linker flags passed when linking the shared library.",
        ),
        "output_loc": attr.string(
            doc = "Optional output path for the shared library.",
        ),
        "srcs": attr.label_list(
            doc = "Perl XS (.xs) source files.",
            allow_files = [".xs"],
        ),
        "textual_hdrs": attr.label_list(
            doc = "Header files included in the build.",
            allow_files = True,
        ),
        "typemaps": attr.label_list(
            doc = "Typemap files used by xsubpp when translating XS.",
            allow_files = True,
        ),
        "_macos_constraint": attr.label(
            default = Label("@platforms//os:macos"),
        ),
        "_windows_constraint": attr.label(
            default = Label("@platforms//os:windows"),
        ),
        "_xs_def": attr.label(
            cfg = "exec",
            providers = [PerlToolInfo],
            default = Label("@rules_perl//perl/private:xs_def"),
        ),
        "_xsubpp": attr.label(
            cfg = "exec",
            providers = [PerlToolInfo],
            default = Label("@rules_perl//perl/private:xsubpp"),
        ),
    },
    implementation = _cpan_xs_implementation,
    fragments = ["cpp"],
    toolchains = [
        "@rules_perl//perl:toolchain_type",
        "@bazel_tools//tools/cpp:toolchain_type",
    ],
)
