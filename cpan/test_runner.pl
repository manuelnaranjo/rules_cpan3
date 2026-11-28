#!/usr/bin/env perl
use strict;
use warnings;
use File::Basename qw(basename dirname);
use File::Spec;
use Cwd qw(abs_path);

my @services;
while (@ARGV && $ARGV[0] =~ /^--service=(.+)$/) {
    push @services, $1;
    shift @ARGV;
}

my $test_file = shift @ARGV;
die "No test file specified to test_runner.pl\n" unless defined $test_file;

my $target_test;
if (File::Spec->file_name_is_absolute($test_file) && -f $test_file) {
    $target_test = $test_file;
} elsif (-f $test_file) {
    $target_test = abs_path($test_file);
}

if (!$target_test && $ENV{TEST_WORKSPACE} && $ENV{TEST_SRCDIR}) {
    my $candidate = File::Spec->catfile($ENV{TEST_SRCDIR}, $ENV{TEST_WORKSPACE}, $test_file);
    if (-f $candidate) {
        $target_test = abs_path($candidate);
    }
}

# Determine manifest or runfiles directory
my @manifest_candidates = (
    $ENV{RUNFILES_MANIFEST_FILE},
    ($ENV{RUNFILES_DIR} ? "$ENV{RUNFILES_DIR}_manifest" : undef),
    ($ENV{TEST_SRCDIR} ? "$ENV{TEST_SRCDIR}_manifest" : undef),
    "$0.runfiles_manifest",
);

for my $mf (@manifest_candidates) {
    next unless defined $mf && -f $mf;
    if (open my $mfh, '<', $mf) {
        while (my $mline = <$mfh>) {
            chomp $mline;
            my ($rpath, $fpath) = split ' ', $mline, 2;
            if ($rpath && $fpath && -f $fpath) {
                if (defined $ENV{TEST_WORKSPACE} && $rpath eq "$ENV{TEST_WORKSPACE}/$test_file") {
                    $target_test = abs_path($fpath);
                    last;
                } elsif ($rpath =~ m{\Q$test_file\E$}) {
                    $target_test //= abs_path($fpath);
                }
            }
        }
        close $mfh;
        last if $target_test;
    }
}

if (!$target_test && $ENV{TEST_SRCDIR} && -d $ENV{TEST_SRCDIR}) {
    require File::Find;
    my $target_leaf = (File::Spec->splitpath($test_file))[2];
    File::Find::find({
        wanted => sub {
            if (File::Basename::basename($_) eq $target_leaf && -f $_) {
                my $rel = File::Spec->abs2rel($_, $ENV{TEST_SRCDIR});
                if ($rel =~ m{\Q$test_file\E$}) {
                    $target_test = abs_path($_);
                }
            }
        },
        no_chdir => 1,
    }, $ENV{TEST_SRCDIR});
}

die "Test file '$test_file' could not be found\n" unless defined $target_test && -f $target_test;

my $test_dir = dirname($target_test);
my $dist_dir = $test_dir;
while ($dist_dir ne "/" && $dist_dir ne "." && basename($dist_dir) ne "t") {
    my $parent = dirname($dist_dir);
    last if $parent eq $dist_dir;
    $dist_dir = $parent;
}
if (basename($dist_dir) eq "t") {
    $dist_dir = dirname($dist_dir);
}

my @abs_inc = map { -d $_ ? abs_path($_) : $_ } @INC;

chdir($dist_dir) or die "Failed to chdir to $dist_dir: $!\n";

if (! -d "blib") {
    eval {
        require File::Path;
        File::Path::make_path("blib");
        my $target_lib = -d "build/lib/perl5" ? abs_path("build/lib/perl5") : (-d "lib" ? abs_path("lib") : undef);
        if ($target_lib && ! -e "blib/lib") {
            eval { symlink($target_lib, "blib/lib"); } or File::Path::make_path("blib/lib");
        } elsif (! -d "blib/lib") {
            File::Path::make_path("blib/lib");
        }
        my $target_arch;
        if (-d "build/lib/perl5") {
            for my $sub (glob("build/lib/perl5/*-linux* build/lib/perl5/*-thread*")) {
                if (-d $sub) {
                    $target_arch = abs_path($sub);
                    last;
                }
            }
        }
        $target_arch //= $target_lib;
        if ($target_arch && ! -e "blib/arch") {
            eval { symlink($target_arch, "blib/arch"); } or File::Path::make_path("blib/arch");
        } elsif (! -d "blib/arch") {
            File::Path::make_path("blib/arch");
        }
    };
}

$ENV{PERL5LIB} = join(':', @abs_inc);
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

my %KNOWN_SERVICES = (
    'redis' => {
        port => 6379,
        image => 'redis:alpine',
        cmd => 'docker run -d --rm --name %s -p 6379:6379 redis:alpine',
    },
    'memcached' => {
        port => 11211,
        image => 'memcached:alpine',
        cmd => 'docker run -d --rm --name %s -p 11211:11211 memcached:alpine',
    },
    'mysql' => {
        port => 3306,
        image => 'mysql:8.0',
        cmd => 'docker run -d --rm --name %s -p 3306:3306 -e MYSQL_ALLOW_EMPTY_PASSWORD=yes -e MYSQL_DATABASE=test mysql:8.0',
    },
    'postgres' => {
        port => 5432,
        image => 'postgres:alpine',
        cmd => 'docker run -d --rm --name %s -p 5432:5432 -e POSTGRES_HOST_AUTH_METHOD=trust -e POSTGRES_DB=test postgres:alpine',
    },
    'postgresql' => {
        port => 5432,
        image => 'postgres:alpine',
        cmd => 'docker run -d --rm --name %s -p 5432:5432 -e POSTGRES_HOST_AUTH_METHOD=trust -e POSTGRES_DB=test postgres:alpine',
    },
    'cassandra' => {
        port => 9042,
        image => 'cassandra:latest',
        cmd => 'docker run -d --rm --name %s -p 9042:9042 cassandra:latest',
    },
    'elasticsearch' => {
        port => 9200,
        image => 'elasticsearch:7.17.10',
        cmd => 'docker run -d --rm --name %s -p 9200:9200 -e discovery.type=single-node -e xpack.security.enabled=false elasticsearch:7.17.10',
    },
);

my @started_containers;
if (@services) {
    eval {
        require IO::Socket::INET;
        for my $svc (@services) {
            my $info = $KNOWN_SERVICES{$svc};
            next unless $info;
            my $port = $info->{port};
            my $is_open = sub {
                my $sock = IO::Socket::INET->new(
                    PeerAddr => '127.0.0.1',
                    PeerPort => $port,
                    Proto    => 'tcp',
                    Timeout  => 1,
                );
                if ($sock) {
                    close $sock;
                    return 1;
                }
                return 0;
            };

            if (!$is_open->()) {
                my $docker_ok = system("docker info >/dev/null 2>&1") == 0;
                if ($docker_ok) {
                    my $cname = "cpan_${svc}_" . $$ . "_" . int(rand(100000));
                    my $cmd = sprintf($info->{cmd}, $cname);
                    system("$cmd >/dev/null 2>&1");
                    push @started_containers, $cname;

                    for (1..30) {
                        last if $is_open->();
                        sleep 1;
                    }
                }
            }
        }
    };
}

my $cleanup = sub {
    for my $c (@started_containers) {
        system("docker stop $c >/dev/null 2>&1");
    }
};

$SIG{INT} = sub { $cleanup->(); exit 1; };
$SIG{TERM} = sub { $cleanup->(); exit 1; };

my @inc_flags = map { "-I$_" } @abs_inc;
my $rel_target_test = File::Spec->abs2rel($target_test, $dist_dir);
my $exec_test = (-f $rel_target_test) ? $rel_target_test : $target_test;
if (@started_containers) {
    system($^X, @extra_flags, @inc_flags, $exec_test, @ARGV);
    my $exit_code = $? >> 8;
    $cleanup->();
    exit $exit_code;
} else {
    exec $^X, @extra_flags, @inc_flags, $exec_test, @ARGV
        or die "Failed to exec $^X: $!\n";
}
