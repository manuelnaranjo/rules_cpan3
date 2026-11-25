"""Public platforms API for rules_cpan"""

PLATFORMS = {
    "darwin_arm64": "//platforms:darwin_arm64",
    "darwin_x86_64": "//platforms:darwin_x86_64",
    "linux_arm64": "//platforms:linux_arm64",
    "linux_x86_64": "//platforms:linux_x86_64",
}

SUPPORTED_PLATFORMS = [
    "//platforms:linux_x86_64",
    "//platforms:linux_arm64",
    "//platforms:darwin_x86_64",
    "//platforms:darwin_arm64",
]

RBE_PLATFORMS = {
    "linux_arm64": "//platforms:rbe_linux_arm64",
    "linux_x86_64": "//platforms:rbe_linux_x86_64",
}

RBE_DOCKERD_PLATFORMS = {
    "linux_arm64": "//platforms:rbe_linux_arm64_dockerd",
    "linux_x86_64": "//platforms:rbe_linux_x86_64_dockerd",
}
