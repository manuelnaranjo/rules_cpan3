"""Module extensions for rules_cpan"""

load(
    "//cpan/private:repo_rules.bzl",
    "cpan_dist_repo",
    "cpan_hub_repo",
    "prune_runtime_cycles",
    "sanitize_repo_name",
)

def _cpan_impl(module_ctx):
    seen_hubs = {}

    # Collect distribution annotations across modules
    annotations = {}
    for mod in module_ctx.modules:
        for annot in mod.tags.annotation:
            key = (annot.hub, annot.distribution)
            annotations[key] = annot

    # Collect injected distribution targets across modules
    injected_by_hub = {}
    for mod in module_ctx.modules:
        for inj in getattr(mod.tags, "inject", []):
            hub = inj.hub
            if hub not in injected_by_hub:
                injected_by_hub[hub] = {}
            if inj.target:
                injected_by_hub[hub][inj.distribution] = str(inj.target)

    for mod in module_ctx.modules:
        for install in mod.tags.install:
            hub_name = install.name
            if hub_name in seen_hubs:
                continue
            seen_hubs[hub_name] = True

            hub_injected = dict(injected_by_hub.get(hub_name, {}))
            for dist_name, target in install.injected.items():
                if target:
                    hub_injected[dist_name] = str(target)

            lock_content = module_ctx.read(install.lock)
            lock_data = json.decode(lock_content)

            distributions = lock_data.get("distributions", {})
            root_dependencies = lock_data.get("root_dependencies", [])

            # Prune circular runtime dependencies into a strict DAG
            pruned_runtime = prune_runtime_cycles(distributions, root_dependencies)

            # Determine direct dependencies (distributions from root_dependencies)
            direct_deps = {}
            for item in root_dependencies:
                dist = item.split(" ")[0]
                if dist in distributions:
                    direct_deps[dist] = True
                else:
                    for d in distributions.keys():
                        if item.startswith(d):
                            direct_deps[d] = True

            all_dists = {}
            dist_repo_names = {}

            # First pass: compute unique repo names for each distribution
            for dist_name in distributions.keys():
                repo_name = hub_name + "__" + sanitize_repo_name(dist_name)
                all_dists[dist_name] = repo_name
                dist_repo_names[dist_name] = repo_name

            # Second pass: instantiate distribution repository rules
            for dist_name, dist_info in distributions.items():
                if dist_name in hub_injected:
                    # Injected ported distribution managed externally
                    continue

                repo_name = dist_repo_names[dist_name]
                url = dist_info.get("url", "")
                sha256 = dist_info.get("sha256", "")
                is_xs = dist_info.get("is_xs", False)
                provides = dist_info.get("provides", [])
                version = dist_info.get("version", "")

                runtime_deps = []
                for dep in pruned_runtime.get(dist_name, []):
                    if dep in hub_injected:
                        runtime_deps.append(hub_injected[dep])
                    elif dep in dist_repo_names:
                        runtime_deps.append("@" + dist_repo_names[dep] + "//:" + dep)

                test_deps = []
                for dep in dist_info.get("dependencies", {}).get("test", []):
                    if dep in hub_injected:
                        test_deps.append(hub_injected[dep])
                    elif dep in dist_repo_names:
                        test_deps.append("@" + dist_repo_names[dep] + "//:" + dep)

                annot = annotations.get((hub_name, dist_name))

                build_file = install.build_file_overlays.get(dist_name, None)
                defines = list(install.defines.get(dist_name, []))
                includes = list(install.includes.get(dist_name, []))
                native_deps = list(install.native_deps.get(dist_name, []))
                output_loc = install.output_locs.get(dist_name, "")
                patch_cmds = list(install.patch_cmds.get(dist_name, []))
                patch_cmds_win = list(install.patch_cmds_win.get(dist_name, []))

                target_compatible_with = list(install.target_compatible_with.get(dist_name, []))
                exec_compatible_with = list(install.exec_compatible_with.get(dist_name, []))
                execution_requirements = {}
                tags = list(install.tags.get(dist_name, []))

                if annot:
                    if annot.build_file:
                        build_file = annot.build_file
                    if annot.defines:
                        defines.extend(annot.defines)
                    if annot.includes:
                        includes.extend(annot.includes)
                    if annot.native_deps:
                        native_deps.extend(annot.native_deps)
                    if annot.output_loc:
                        output_loc = annot.output_loc
                    if annot.patch_cmds:
                        patch_cmds.extend(annot.patch_cmds)
                    if annot.patch_cmds_win:
                        patch_cmds_win.extend(annot.patch_cmds_win)
                    if annot.target_compatible_with:
                        target_compatible_with = annot.target_compatible_with
                    if annot.exec_compatible_with:
                        exec_compatible_with = annot.exec_compatible_with
                    if annot.execution_requirements:
                        execution_requirements.update(annot.execution_requirements)
                    if annot.tags:
                        tags.extend(annot.tags)

                dist_test_tags = list(install.test_tags.get(dist_name, []))
                if dist_name in install.manual_tests:
                    if "manual" not in dist_test_tags:
                        dist_test_tags.append("manual")
                if "manual" in tags and "manual" not in dist_test_tags:
                    dist_test_tags.append("manual")
                if annot:
                    if hasattr(annot, "test_tags") and annot.test_tags:
                        for t in annot.test_tags:
                            if t not in dist_test_tags:
                                dist_test_tags.append(t)
                    if "manual" in annot.tags and "manual" not in dist_test_tags:
                        dist_test_tags.append("manual")

                cpan_dist_repo(
                    name = repo_name,
                    dist_name = dist_name,
                    version = version,
                    url = url,
                    sha256 = sha256,
                    is_xs = is_xs,
                    provides = provides,
                    runtime_deps = runtime_deps,
                    build_file = build_file,
                    defines = defines,
                    includes = includes,
                    native_deps = native_deps,
                    output_loc = output_loc,
                    patch_cmds = patch_cmds,
                    patch_cmds_win = patch_cmds_win,
                    target_compatible_with = target_compatible_with,
                    exec_compatible_with = exec_compatible_with,
                    execution_requirements = execution_requirements,
                    extra_tags = tags,
                    test_deps = test_deps,
                    test_tags = dist_test_tags,
                )

            hub_test_tags = {}
            hub_test_modules = {}
            hub_manual_tests = list(install.manual_tests)
            for dist_name in distributions.keys():
                dtags = list(install.test_tags.get(dist_name, []))
                if "manual" in install.tags.get(dist_name, []):
                    if "manual" not in dtags:
                        dtags.append("manual")
                annot = annotations.get((hub_name, dist_name))
                if annot:
                    if hasattr(annot, "test_tags") and annot.test_tags:
                        for t in annot.test_tags:
                            if t not in dtags:
                                dtags.append(t)
                    if hasattr(annot, "test_module") and annot.test_module:
                        hub_test_modules[dist_name] = annot.test_module
                    if "manual" in annot.tags:
                        if "manual" not in dtags:
                            dtags.append("manual")
                if "manual" in dtags and dist_name not in hub_manual_tests:
                    hub_manual_tests.append(dist_name)
                if dtags:
                    hub_test_tags[dist_name] = dtags

            # Third pass: instantiate hub repository rule
            cpan_hub_repo(
                name = hub_name,
                hub_name = hub_name,
                direct_deps = direct_deps.keys(),
                all_dists = all_dists,
                injected_targets = hub_injected,
                dist_provides = {d: info.get("provides", []) for d, info in distributions.items()},
                manual_tests = hub_manual_tests,
                test_modules = hub_test_modules,
                test_tags = hub_test_tags,
            )

annotation_tag = tag_class(
    doc = "Defines extra annotations (platform constraints, execution requirements, etc.) for a generated distribution.",
    attrs = {
        "build_file": attr.label(
            doc = "Custom BUILD file overlay.",
            default = None,
        ),
        "defines": attr.string_list(
            doc = "Extra preprocessor defines.",
            default = [],
        ),
        "distribution": attr.string(
            doc = "CPAN distribution name (e.g. 'Compress-Raw-Zlib').",
            mandatory = True,
        ),
        "exec_compatible_with": attr.string_list(
            doc = "Execution platform constraints.",
            default = [],
        ),
        "execution_requirements": attr.string_dict(
            doc = "Execution requirements for actions (e.g. {'no-remote': '1'}).",
            default = {},
        ),
        "hub": attr.string(
            doc = "Name of the hub repository this annotation applies to.",
            default = "cpan",
        ),
        "includes": attr.string_list(
            doc = "Extra library include paths to search for Perl modules and add to @INC (e.g. ['LibYAML/lib']).",
            default = [],
        ),
        "native_deps": attr.string_list(
            doc = "Extra native C/C++ dependencies.",
            default = [],
        ),
        "output_loc": attr.string(
            doc = "Optional DynaLoader/XSLoader auto/ directory location for an XS module.",
            default = "",
        ),
        "patch_cmds": attr.string_list(
            doc = "Patch bash commands.",
            default = [],
        ),
        "patch_cmds_win": attr.string_list(
            doc = "Patch windows commands.",
            default = [],
        ),
        "tags": attr.string_list(
            doc = "Bazel tags to add to the generated targets.",
            default = [],
        ),
        "target_compatible_with": attr.string_list(
            doc = "Target platform constraints (e.g. ['@platforms//os:linux']).",
            default = [],
        ),
        "test_module": attr.string(
            doc = "Perl package to load in generated module test (defaults to primary module).",
            default = "",
        ),
        "test_tags": attr.string_list(
            doc = "Bazel tags to add to generated test targets.",
            default = [],
        ),
    },
)

inject_tag = tag_class(
    doc = "Injects an externally-managed or ported Bazel target for a CPAN distribution.",
    attrs = {
        "distribution": attr.string(
            doc = "CPAN distribution name (e.g. 'Compress-Raw-Zlib').",
            mandatory = True,
        ),
        "hub": attr.string(
            doc = "Name of the hub repository this injection applies to.",
            default = "cpan",
        ),
        "target": attr.label(
            doc = "Bazel target label managing this distribution (e.g. '@perl-compress-raw-zlib//:Compress-Raw-Zlib').",
            mandatory = True,
        ),
    },
)

install_tag = tag_class(
    doc = "Defines a CPAN hub repository and installs dependencies from a lockfile.",
    attrs = {
        "build_file_overlays": attr.string_keyed_label_dict(
            doc = "Optional overlay BUILD files per distribution.",
            default = {},
        ),
        "defines": attr.string_list_dict(
            doc = "Optional preprocessor defines per distribution.",
            default = {},
        ),
        "exec_compatible_with": attr.string_list_dict(
            doc = "Optional execution platform constraints per distribution.",
            default = {},
        ),
        "includes": attr.string_list_dict(
            doc = "Optional extra include paths per distribution.",
            default = {},
        ),
        "injected": attr.string_keyed_label_dict(
            doc = "Optional mapping from distribution name to injected Bazel target label.",
            default = {},
        ),
        "lock": attr.label(
            doc = "Label to cpan.lock.json lockfile.",
            mandatory = True,
        ),
        "manual_tests": attr.string_list(
            doc = "Optional list of distribution names whose tests should be marked as manual.",
            default = [],
        ),
        "name": attr.string(
            doc = "Name of the hub repository.",
            default = "cpan",
        ),
        "native_deps": attr.string_list_dict(
            doc = "Optional native C/C++ library dependencies per distribution.",
            default = {},
        ),
        "output_locs": attr.string_dict(
            doc = "Optional DynaLoader/XSLoader auto/ location per distribution.",
            default = {},
        ),
        "patch_cmds": attr.string_list_dict(
            doc = "Optional bash patch commands per distribution.",
            default = {},
        ),
        "patch_cmds_win": attr.string_list_dict(
            doc = "Optional Windows batch commands per distribution.",
            default = {},
        ),
        "tags": attr.string_list_dict(
            doc = "Optional tags per distribution.",
            default = {},
        ),
        "target_compatible_with": attr.string_list_dict(
            doc = "Optional target platform constraints per distribution.",
            default = {},
        ),
        "test_tags": attr.string_list_dict(
            doc = "Optional test tags per distribution.",
            default = {},
        ),
    },
)

cpan = module_extension(
    doc = "Module extension for hermetic CPAN dependency installation.",
    implementation = _cpan_impl,
    tag_classes = {
        "annotation": annotation_tag,
        "inject": inject_tag,
        "install": install_tag,
    },
)
