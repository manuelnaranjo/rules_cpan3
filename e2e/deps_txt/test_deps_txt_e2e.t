#!/usr/bin/env perl
use strict;
use warnings;

use Test::More tests => 10;

# Pure Perl distributions
use Moo;
use Try::Tiny;
use Path::Tiny;
use URI;
use Capture::Tiny qw(capture_stdout);

# XS extensions
use Compress::Raw::Zlib;
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
