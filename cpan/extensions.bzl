"""Module extensions for rules_cpan"""

load(
    "//cpan/private:repo_rules.bzl",
    "cpan_dist_repo",
    "cpan_hub_repo",
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
                all_dists[dist_name] = hub_name + "__" + sanitize_repo_name(dist_name)

            # Declare repository for each distribution in lockfile
            for dist_name, dist_info in distributions.items():
                repo_name = all_dists[dist_name]
                cpan_dist_repo(
                    name = repo_name,
                    dist_name = dist_name,
                    version = dist_info.get("version", ""),
                    url = dist_info.get("url", ""),
                    sha256 = dist_info.get("sha256", ""),
                    strip_prefix = dist_info.get("strip_prefix", ""),
                    is_xs = dist_info.get("is_xs", False),
                    provides = dist_info.get("provides", []),
                    dependencies = json.encode(dist_info.get("dependencies", {})),
                    all_dists = json.encode(all_dists),
                    hub_name = hub_name,
                )

            # Instantiate hub repository rule
            cpan_hub_repo(
                name = hub_name,
                hub_name = hub_name,
                direct_deps = direct_deps.keys(),
                all_dists = all_dists,
            )

inject_tag = tag_class(
    doc = "Legacy tag for backwards compatibility (no-op).",
    attrs = {
        "distribution": attr.string(
            doc = "CPAN distribution name.",
            mandatory = False,
        ),
        "hub": attr.string(
            doc = "Name of the hub repository.",
            default = "cpan",
        ),
        "target": attr.label(
            doc = "Bazel target label.",
            mandatory = False,
        ),
    },
)

install_tag = tag_class(
    doc = "Defines a CPAN hub repository and installs dependencies from a lockfile.",
    attrs = {
        "injected": attr.string_keyed_label_dict(
            doc = "Optional mapping for backwards compatibility.",
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
