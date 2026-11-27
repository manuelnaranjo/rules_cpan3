# Translates a Perl XS file to C with support for included generated files.
use strict;
use warnings;
use File::Basename qw(basename dirname);
use File::Spec;

BEGIN { @INC = map { ref($_) ? $_ : File::Spec->rel2abs($_) } @INC }

use ExtUtils::ParseXS;
use Getopt::Long;

sub main {
    my @typemaps;
    my @includes;
    my $output;
    GetOptions(
        "typemap=s" => \@typemaps,
        "include=s" => \@includes,
        "output=s"  => \$output,
    ) or die "Failed to parse arguments\n";
    die "Usage: $0 [--typemap <file>]... [--include <file>]... --output <file.c> <file.xs>\n"
        unless defined $output && @ARGV == 1;

    my $xs_file = $ARGV[0];
    my $xs_dir = dirname($xs_file);

    my @cleanup;
    for my $inc (@includes) {
        my $base = basename($inc);
        my $dest = File::Spec->catfile($xs_dir, $base);
        if (! -e $dest) {
            my $abs_src = File::Spec->rel2abs($inc);
            my $ok = eval { symlink($abs_src, $dest) };
            if (!$ok) {
                eval {
                    require File::Copy;
                    File::Copy::copy($abs_src, $dest);
                };
            }
            if (-e $dest) {
                push @cleanup, $dest;
            }
        }
    }

    my $pxs = ExtUtils::ParseXS->new;
    $pxs->process_file(
        filename => $xs_file,
        output   => $output,
        typemap  => [ map { File::Spec->rel2abs($_) } @typemaps ],
    );

    unlink $_ for @cleanup;

    return $pxs->report_error_count() ? 1 : 0;
}

exit(main());
