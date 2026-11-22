use strict;
use warnings;
use Test::More tests => 2;

use_ok('Algorithm::Diff', qw(diff));

my @a = (1, 2, 3);
my @b = (1, 3);
my @d = diff(\@a, \@b);
is(scalar(@d), 1, 'Multi-hub @cpan_alt verified successfully');
