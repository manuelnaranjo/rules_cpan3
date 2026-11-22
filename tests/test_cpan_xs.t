use strict;
use warnings;
use Test::More tests => 6;

use Compress::Raw::Zlib qw(:DEFAULT Z_OK Z_BEST_COMPRESSION);

my ($deflater, $status) = new Compress::Raw::Zlib::Deflate(
    -Level => Z_BEST_COMPRESSION,
    -AppendOutput => 1,
);
cmp_ok($status, '==', Z_OK, "Deflate init status is Z_OK");
ok(defined $deflater, "Deflate object defined");

my $input = "Hello CPAN from hermetic rules_cpan module extension!";
my $compressed = "";
$status = $deflater->deflate($input, $compressed);
cmp_ok($status, '==', Z_OK, "Deflate string status is Z_OK");

$status = $deflater->flush($compressed);
cmp_ok($status, '==', Z_OK, "Flush status is Z_OK");

my ($inflater, $inf_status) = new Compress::Raw::Zlib::Inflate(
    -AppendOutput => 1,
    -ConsumeInput => 1,
);
cmp_ok($inf_status, '==', Z_OK, "Inflate init status is Z_OK");

my $decompressed = "";
$inf_status = $inflater->inflate($compressed, $decompressed);
is($decompressed, $input, "Roundtrip compression and decompression verified");
