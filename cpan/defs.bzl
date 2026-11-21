"""Public API re-exports for rules_cpan"""

load("//cpan/private:rules.bzl", _cpan_dummy = "cpan_dummy")
load(
    "//platforms:platforms.bzl",
    _PLATFORMS = "PLATFORMS",
    _RBE_PLATFORMS = "RBE_PLATFORMS",
    _SUPPORTED_PLATFORMS = "SUPPORTED_PLATFORMS",
)
load(
    "//platforms:transitions.bzl",
    _platform_binary = "platform_binary",
    _platform_transition = "platform_transition",
)

cpan_dummy = _cpan_dummy
PLATFORMS = _PLATFORMS
RBE_PLATFORMS = _RBE_PLATFORMS
SUPPORTED_PLATFORMS = _SUPPORTED_PLATFORMS
platform_transition = _platform_transition
platform_binary = _platform_binary
