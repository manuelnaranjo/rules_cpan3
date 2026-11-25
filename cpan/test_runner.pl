#!/usr/bin/env perl
use strict;
use warnings;
use File::Basename qw(basename dirname);
use File::Spec;
use Cwd qw(abs_path);

my $test_file = shift @ARGV;
die "No test file specified to test_runner.pl\n" unless defined $test_file;

my $target_test;
if (File::Spec->file_name_is_absolute($test_file) && -f $test_file) {
    $target_test = $test_file;
} elsif (-f $test_file) {
    $target_test = abs_path($test_file);
} elsif ($ENV{TEST_SRCDIR}) {
    my $candidate = File::Spec->catfile($ENV{TEST_SRCDIR}, $test_file);
    if (-f $candidate) {
        $target_test = abs_path($candidate);
    } else {
        require File::Find;
        my $target_leaf = (File::Spec->splitpath($test_file))[2];
        File::Find::find({
            wanted => sub {
                if ($_ eq $target_leaf && -f $_) {
                    my $rel = File::Spec->abs2rel($File::Find::name, $ENV{TEST_SRCDIR});
                    if ($rel =~ m{\Q$test_file\E$}) {
                        $target_test = abs_path($File::Find::name);
                    }
                }
            },
            no_chdir => 1,
        }, $ENV{TEST_SRCDIR});
    }
}

die "Test file '$test_file' could not be found\n" unless defined $target_test && -f $target_test;

my $test_dir = dirname($target_test);
my $dist_dir = $test_dir;
if (basename($dist_dir) eq "t") {
    $dist_dir = dirname($dist_dir);
}
chdir($dist_dir) or die "Failed to chdir to $dist_dir: $!\n";

$ENV{PERL5LIB} = join(':', @INC);
$ENV{PERL_USE_UNSAFE_INC} = 1;

my @extra_flags;
if (open my $fh, '<', $target_test) {
    my $first_line = <$fh>;
    close $fh;
    if (defined $first_line && $first_line =~ m{^#!\s*\S*perl\S*(?:\s+(.*?))?\s*$}) {
        my $opts = $1 // '';
        $opts =~ s/#.*//;
        for my $flag (split ' ', $opts) {
            if ($flag =~ /^-[a-zA-Z0-9]+$/) {
                push @extra_flags, $flag;
            }
        }
    }
}

my @inc_flags = map { "-I$_" } @INC;
exec $^X, @extra_flags, @inc_flags, $target_test, @ARGV
    or die "Failed to exec $^X: $!\n";
