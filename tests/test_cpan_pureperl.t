use strict;
use warnings;
use Test::More tests => 3;

use_ok('Algorithm::Diff', qw(diff));

my @seq1 = qw(apple orange banana cherry);
my @seq2 = qw(apple banana grape cherry);

my @diffs = diff(\@seq1, \@seq2);
ok(@diffs > 0, "diff returned non-empty hunk list");
is(scalar(@diffs), 2, "found expected 2 difference hunks");
