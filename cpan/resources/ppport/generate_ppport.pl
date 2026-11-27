#!/usr/bin/env perl
use strict;
use warnings;
use Devel::PPPort;

my $output = shift @ARGV or die "Usage: $0 <output_file>\n";
Devel::PPPort::WriteFile($output);
