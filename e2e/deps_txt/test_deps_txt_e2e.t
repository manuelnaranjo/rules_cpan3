#!/usr/bin/env perl
use strict;
use warnings;

use Test::More tests => 38;

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
use Compress::Zstd qw(compress decompress compress_mt);
use XML::Parser;
use IO::Tty;
use YAML::XS;
use Clone qw(clone);
use Sub::Name qw(subname);

# BCR Native Integrations
use Compress::LZ4 ();
use Compress::Snappy ();
use Math::Prime::Util::GMP ();
use Crypt::NaCl::Sodium ();
use Crypt::Sodium::Nitrate ();
use Curses ();
use Authen::PAM ();
use Authen::Simple::PAM ();
use XML::LibXML ();
use XML::LibXML::Simple ();
use Crypt::OpenSSL::AES ();
use Crypt::OpenSSL::Bignum ();
use Crypt::OpenSSL::Random ();
use Crypt::OpenSSL::RSA ();
use Crypt::OpenSSL::X509 ();
use Crypt::SMIME ();
use Net::SSLeay ();
use CommonMark ();
use CSS::Sass ();
use Text::Iconv ();
use Text::Markdown::Discount ();

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

# Test 10: XML::Parser (XS - BCR libexpat integration)
my $xml_parser = XML::Parser->new(Style => 'Tree');
my $tree = $xml_parser->parse('<root id="123"><child attr="val">Hello XML Expat</child></root>');
is($tree->[0], 'root', "XML::Parser parsed root element accurately");
is($tree->[1]->[2]->[2], 'Hello XML Expat', "XML::Parser parsed child text accurately");

# Test 11: Compress::Zstd (XS - BCR zstd integration)
my $zstd_in = "Hermetic zstd compression via rules_cpan3!";
my $zstd_out = compress($zstd_in);
my $zstd_decomp = decompress($zstd_out);
is($zstd_decomp, $zstd_in, "Compress::Zstd roundtrip compression matches input");
my $zstd_mt_out = compress_mt($zstd_in, 2);
is(decompress($zstd_mt_out), $zstd_in, "Compress::Zstd multi-threaded compression matches input");

# Test 12: Compress::LZ4 (XS - BCR lz4 integration)
my $lz4_in = "Hermetic lz4 compression via rules_cpan3!";
my $lz4_out = Compress::LZ4::compress($lz4_in);
is(Compress::LZ4::decompress($lz4_out), $lz4_in, "Compress::LZ4 roundtrip compression matches input");

# Test 13: Compress::Snappy (XS - BCR snappy integration)
my $snappy_in = "Hermetic snappy compression via rules_cpan3!";
my $snappy_out = Compress::Snappy::compress($snappy_in);
is(Compress::Snappy::decompress($snappy_out), $snappy_in, "Compress::Snappy roundtrip compression matches input");

# Test 14: Math::Prime::Util::GMP (XS - BCR gmp integration)
ok(Math::Prime::Util::GMP::is_prime(104729), "Math::Prime::Util::GMP identifies prime correctly");

# Test 15 & 16: Crypt::NaCl::Sodium & Crypt::Sodium::Nitrate (XS - BCR libsodium integration)
my $crypto_box = Crypt::NaCl::Sodium->new();
ok($crypto_box, "Crypt::NaCl::Sodium instance initialized");
ok(Crypt::Sodium::Nitrate::MACBYTES(), "Crypt::Sodium::Nitrate MACBYTES constant works");

# Test 17: Curses (XS - BCR ncurses integration)
ok(defined(&Curses::initscr), "Curses function initscr is defined");

# Test 18 & 19: Authen::PAM & Authen::Simple::PAM (XS - BCR linux-pam integration)
ok(defined(&Authen::PAM::pam_start), "Authen::PAM function pam_start is defined");
my $pam_simple = Authen::Simple::PAM->new(service => "login");
ok($pam_simple, "Authen::Simple::PAM instance created");

# Test 20 & 21: XML::LibXML & XML::LibXML::Simple (XS - BCR libxml2 integration)
my $doc = XML::LibXML->load_xml(string => "<root><elem id='1'>test</elem></root>");
is($doc->findvalue('/root/elem/@id'), "1", "XML::LibXML parses and queries DOM accurately");
my $xml_simple = XML::LibXML::Simple->new();
my $xml_hash = $xml_simple->XMLin("<root><val>42</val></root>");
is($xml_hash->{val}, "42", "XML::LibXML::Simple parsed XML to hash");

# Test 22: Crypt::OpenSSL::AES (XS - BCR openssl integration)
my $aes = Crypt::OpenSSL::AES->new("0123456789abcdef");
my $aes_enc = $aes->encrypt("abcdefghijklmnop");
is($aes->decrypt($aes_enc), "abcdefghijklmnop", "Crypt::OpenSSL::AES encrypt/decrypt roundtrip");

# Test 23: Crypt::OpenSSL::Bignum (XS - BCR openssl integration)
my $bn = Crypt::OpenSSL::Bignum->new_from_word(42);
is($bn->to_decimal(), "42", "Crypt::OpenSSL::Bignum word to decimal");

# Test 24: Crypt::OpenSSL::Random (XS - BCR openssl integration)
my $rand_bytes = Crypt::OpenSSL::Random::random_bytes(16);
is(length($rand_bytes), 16, "Crypt::OpenSSL::Random generated 16 bytes");

# Test 25: Crypt::OpenSSL::RSA (XS - BCR openssl integration)
my $rsa = Crypt::OpenSSL::RSA->generate_key(1024);
ok($rsa->is_private(), "Crypt::OpenSSL::RSA generated private key");

# Test 26: Crypt::OpenSSL::X509 (XS - BCR openssl integration)
ok(defined(&Crypt::OpenSSL::X509::new_from_string), "Crypt::OpenSSL::X509 function is defined");

# Test 27: Crypt::SMIME (XS - BCR openssl integration)
my $smime = Crypt::SMIME->new();
ok($smime, "Crypt::SMIME instance initialized");

# Test 28: Net::SSLeay (XS - BCR openssl integration)
Net::SSLeay::randomize();
ok(1, "Net::SSLeay randomize executed successfully");

# Test 29: CommonMark (XS - BCR cmark integration)
my $cmark_html = CommonMark->markdown_to_html("# CommonMark Test");
ok(index($cmark_html, "<h1>CommonMark Test</h1>") != -1, "CommonMark markdown_to_html works");

# Test 30: CSS::Sass (XS - BCR libsass integration)
my ($sass_css, $sass_err) = CSS::Sass::sass_compile("foo { color: red; }");
ok(index($sass_css, "color: red") != -1, "CSS::Sass compiled SCSS successfully");

# Test 31: Text::Iconv (XS - BCR libiconv integration)
my $iconv_conv = Text::Iconv->new("UTF-8", "UTF-8");
my $iconv_res = $iconv_conv->convert("hello world");
is($iconv_res, "hello world", "Text::Iconv converted text accurately");

# Test 32: Text::Markdown::Discount (XS - BCR discount integration)
my $discount_html = Text::Markdown::Discount::markdown("# Discount Test");
ok(index($discount_html, "<h1>Discount Test</h1>") != -1, "Text::Markdown::Discount works");
