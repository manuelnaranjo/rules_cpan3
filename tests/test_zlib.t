use strict;
use warnings;
use Test::More tests => 3;

ok(1, 'Perl test harness initialized');

# Verify that the native zlib consumer binary works and reports ok
my $bin = './tests/zlib_consumption_test';
if (! -x $bin) {
    my $test_srcdir = $ENV{TEST_SRCDIR} || '';
    my $test_ws = $ENV{TEST_WORKSPACE} || 'rules_cpan';
    my $candidate = "$test_srcdir/$test_ws/tests/zlib_consumption_test";
    if (-x $candidate) {
        $bin = $candidate;
    }
}

ok(1, "Testing native zlib integration from CPAN harness");
my $output = `$bin 2>&1`;
my $exit_code = $? >> 8;
is($exit_code, 0, "zlib consumption binary executed successfully: $output");

done_testing();
