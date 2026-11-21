"""Module extensions for rules_cpan"""

def _cpan_impl(_module_ctx):
    pass

cpan = module_extension(
    implementation = _cpan_impl,
)
