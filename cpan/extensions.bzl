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

    for mod in module_ctx.modules:
        for install in mod.tags.install:
            hub_name = install.name
            if hub_name in seen_hubs:
                continue
            seen_hubs[hub_name] = True

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
                repo_name = dist_repo_names[dist_name]
                url = dist_info.get("url", "")
                sha256 = dist_info.get("sha256", "")
                is_xs = dist_info.get("is_xs", False)
                provides = dist_info.get("provides", [])
                version = dist_info.get("version", "")

                runtime_deps = []
                for dep in pruned_runtime.get(dist_name, []):
                    if dep in dist_repo_names:
                        runtime_deps.append("@" + dist_repo_names[dep] + "//:" + dep)

                build_file = install.build_file_overlays.get(dist_name, None)
                defines = install.defines.get(dist_name, [])
                native_deps = install.native_deps.get(dist_name, [])
                patch_cmds = install.patch_cmds.get(dist_name, [])
                patch_cmds_win = install.patch_cmds_win.get(dist_name, [])

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
                    native_deps = native_deps,
                    patch_cmds = patch_cmds,
                    patch_cmds_win = patch_cmds_win,
                )

            # Third pass: instantiate hub repository rule
            cpan_hub_repo(
                name = hub_name,
                hub_name = hub_name,
                direct_deps = direct_deps.keys(),
                all_dists = all_dists,
                dist_provides = {d: info.get("provides", []) for d, info in distributions.items()},
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
        "lock": attr.label(
            doc = "Label to cpan.lock.json lockfile.",
            mandatory = True,
        ),
        "name": attr.string(
            doc = "Name of the hub repository.",
            default = "cpan",
        ),
        "native_deps": attr.string_list_dict(
            doc = "Optional native C/C++ library dependencies per distribution.",
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
    },
)

cpan = module_extension(
    doc = "Module extension for hermetic CPAN dependency installation.",
    implementation = _cpan_impl,
    tag_classes = {
        "install": install_tag,
    },
)
