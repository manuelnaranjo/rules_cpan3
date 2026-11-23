#!/usr/bin/env perl
use strict;
use warnings;

use Test::More tests => 13;

# Pure Perl distributions
use Moo;
use Try::Tiny;
use Path::Tiny;
use URI;
use Capture::Tiny qw(capture_stdout);

# XS extensions
use Compress::Raw::Zlib;
use Compress::Raw::Bzip2 qw(BZ_OK);
use Compress::Bzip2 qw(bzip2 bunzip2);
use IO::Tty;
use YAML::XS;
use Clone qw(clone);
use Sub::Name qw(subname);

# Test 1: Try::Tiny
my $caught = 0;
try {
    die "intentional error";
} catch {
    $caught = 1;
};
ok($caught, "Try::Tiny caught exception successfully");

# Test 2: Path::Tiny
my $temp = Path::Tiny->tempfile;
$temp->spew("hello rules_cpan3 deps_txt e2e");
is($temp->slurp, "hello rules_cpan3 deps_txt e2e", "Path::Tiny roundtrip read/write");

# Test 3: URI
my $uri = URI->new("https://cpan.metacpan.org/authors/id/P/PM/PMQS/Compress-Raw-Zlib-2.226.tar.gz");
is($uri->scheme, "https", "URI scheme parsed correctly");
is($uri->host, "cpan.metacpan.org", "URI host parsed correctly");

# Test 4: Capture::Tiny
my $stdout = capture_stdout {
    print "captured string\n";
};
is($stdout, "captured string\n", "Capture::Tiny captured stdout");

# Test 5: Compress::Raw::Zlib (XS - Injected BCR module)
my ($def, $status) = new Compress::Raw::Zlib::Deflate();
ok($status == Z_OK, "Compress::Raw::Zlib deflate initialized");
my $in = "Rules CPAN3 bulk deps.txt integration test!";
my $out = "";
$status = $def->deflate($in, $out);
my $flushed = "";
$def->flush($flushed);
$out .= $flushed;

my ($inf, $inf_status) = new Compress::Raw::Zlib::Inflate();
my $decomp = "";
$inf->inflate($out, $decomp);
is($decomp, $in, "Compress::Raw::Zlib roundtrip decompression matches input");

# Test 6: Clone (XS)
my $orig = { a => 1, b => [2, 3], c => { d => 4 } };
my $cloned = clone($orig);
is_deeply($cloned, $orig, "Clone duplicated structure accurately");
$cloned->{b}[0] = 99;
isnt($orig->{b}[0], 99, "Clone performed deep copy");

# Test 7: YAML::XS (XS)
my $yaml_str = YAML::XS::Dump({ greeting => "hello", language => "perl" });
my $yaml_data = YAML::XS::Load($yaml_str);
is($yaml_data->{greeting}, "hello", "YAML::XS serialized and deserialized correctly");

# Test 8: Compress::Raw::Bzip2 (XS - BCR bzip2 integration)
my ($bz_def, $bz_status) = new Compress::Raw::Bzip2(0);
ok($bz_status == BZ_OK, "Compress::Raw::Bzip2 deflate initialized");
my $bz_in = "Hermetic bzip2 compression via rules_cpan3!";
my $bz_out = "";
$bz_def->bzdeflate($bz_in, $bz_out);
my $bz_flushed = "";
$bz_def->bzclose($bz_flushed);
$bz_out .= $bz_flushed;

my ($bz_inf, $bz_inf_status) = new Compress::Raw::Bunzip2(0);
my $bz_decomp = "";
$bz_inf->bzinflate($bz_out, $bz_decomp);
is($bz_decomp, $bz_in, "Compress::Raw::Bzip2 roundtrip compression matches input");

# Test 9: Compress::Bzip2 (XS - BCR bzip2 integration)
my $compressed_bz2 = Compress::Bzip2::memBzip("High-level bzip2 test string");
my $decompressed_bz2 = Compress::Bzip2::memBunzip($compressed_bz2);
is($decompressed_bz2, "High-level bzip2 test string", "Compress::Bzip2 roundtrip matches");
