#!/usr/bin/env perl
use strict;
use warnings;

use Test2::V0;
use Test2::Tools::Basic;

# Verify Pakket core modules load cleanly
use Pakket;
use Pakket::Utils qw(encode_json_pretty normalize_version clean_hash);
use Pakket::Utils::Package qw(canonical_name);
use Pakket::Helper::Versioner;
use Pakket::Type::Meta;
use Pakket::Type::Package;

# Verify injected BCR CPAN XS dependency
use Compress::Raw::Zlib;

# Test 1: Pakket::Utils::Package canonical_name
my $name = canonical_name("perl", "Foo-Bar", "1.2.3", 1);
is($name, "perl/Foo-Bar=1.2.3:1", "Pakket::Utils::Package generates canonical package string");

# Test 2: Pakket::Helper::Versioner requirement parsing
my $ver = Pakket::Helper::Versioner->new(type => "Perl");
isa_ok($ver, "Pakket::Helper::Versioner");
my $reqs = $ver->parse_req_string(">= 1.2.0, < 2.0.0");
is($reqs, [[">=", "1.2.0"], ["<", "2.0.0"]], "Pakket::Helper::Versioner parses requirement intervals");

# Test 3: Pakket::Type::Meta & Package construction
my $meta = Pakket::Type::Meta->new(
    prereqs => { runtime => { requires => { "Foo::Bar" => 0 } } },
);
isa_ok($meta, "Pakket::Type::Meta");

my $pkg = Pakket::Type::Package->new(
    category => "perl",
    name => "Pakket",
    version => "3.417",
    release => 1,
);
isa_ok($pkg, "Pakket::Type::Package");
is($pkg->name, "Pakket", "Pakket::Type::Package stores distribution name");

# Test 4: Injected Compress::Raw::Zlib compression roundtrip
my ($def, $status) = new Compress::Raw::Zlib::Deflate();
ok($status == Z_OK, "Compress::Raw::Zlib deflate initialization succeeded");
my $in = "Pakket hermetic packaging test with rules_cpan3!";
my $out = "";
$status = $def->deflate($in, $out);
ok($status == Z_OK, "Compress::Raw::Zlib deflated data");
my $flushed = "";
$status = $def->flush($flushed);
ok($status == Z_OK, "Compress::Raw::Zlib flushed stream");
$out .= $flushed;

my ($inf, $inf_status) = new Compress::Raw::Zlib::Inflate();
ok($inf_status == Z_OK, "Compress::Raw::Zlib inflate initialization succeeded");
my $decomp = "";
$inf_status = $inf->inflate($out, $decomp);
is($decomp, $in, "Compress::Raw::Zlib roundtrip decompression matches input");

done_testing();
