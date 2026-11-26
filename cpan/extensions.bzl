"""Module extensions for rules_cpan"""

load(
    "//cpan/private:repo_rules.bzl",
    "cpan_hub_repo",
    "dist_to_bcr_module",
)

def _cpan_impl(module_ctx):
    seen_hubs = {}

    # Collect injected distribution targets across modules
    injected_by_hub = {}
    for mod in module_ctx.modules:
        for inj in getattr(mod.tags, "inject", []):
            hub = inj.hub
            if hub not in injected_by_hub:
                injected_by_hub[hub] = {}
            if inj.target:
                injected_by_hub[hub][inj.distribution] = str(inj.target)
            else:
                bcr_mod = dist_to_bcr_module(inj.distribution)
                injected_by_hub[hub][inj.distribution] = "@" + bcr_mod + "//:" + inj.distribution

    for mod in module_ctx.modules:
        for install in mod.tags.install:
            hub_name = install.name
            if hub_name in seen_hubs:
                continue
            seen_hubs[hub_name] = True

            hub_injected = dict(injected_by_hub.get(hub_name, {}))
            for dist_name, target in getattr(install, "injected", {}).items():
                if target:
                    hub_injected[dist_name] = str(target)

            distributions = {}
            root_dependencies = []
            if install.lock:
                lock_content = module_ctx.read(install.lock)
                lock_data = json.decode(lock_content)
                distributions = lock_data.get("distributions", {})
                root_dependencies = lock_data.get("root_dependencies", [])

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
            for dist_name in distributions.keys():
                all_dists[dist_name] = dist_to_bcr_module(dist_name)

            # Instantiate hub repository rule pointing directly to BCR modules
            cpan_hub_repo(
                name = hub_name,
                hub_name = hub_name,
                direct_deps = direct_deps.keys(),
                all_dists = all_dists,
                injected_targets = hub_injected,
            )

inject_tag = tag_class(
    doc = "Injects an externally-managed or ported Bazel target for a CPAN distribution into the hub.",
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
            mandatory = False,
        ),
    },
)

install_tag = tag_class(
    doc = "Defines a CPAN hub repository and installs dependencies from a lockfile.",
    attrs = {
        "injected": attr.string_keyed_label_dict(
            doc = "Optional mapping from distribution name to injected Bazel target label.",
            default = {},
        ),
        "lock": attr.label(
            doc = "Label to cpan.lock.json lockfile.",
            mandatory = False,
        ),
        "name": attr.string(
            doc = "Name of the hub repository.",
            default = "cpan",
        ),
    },
)

cpan = module_extension(
    doc = "Module extension for hermetic CPAN dependency installation.",
    implementation = _cpan_impl,
    tag_classes = {
        "inject": inject_tag,
        "install": install_tag,
    },
)
