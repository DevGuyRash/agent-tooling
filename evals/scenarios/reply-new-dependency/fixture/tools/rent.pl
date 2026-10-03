#!/usr/bin/perl
# rent.pl -- what each plot owes for a season, for the treasurer's bank sheet.
#
#   perl tools/rent.pl --season 2026 data/plots.csv
#
# Prints a header line, then one tab-separated line per charged plot in plot order
# (plot, holder, rent in pence, water in pence), then a total line. The rules are written
# down in docs/rent.md; this script is what the treasurer banks against.
#
# Dev Okonjo, 2019. Second-plot surcharge added 2023, trough water 2024.
use strict;
use warnings;

my $HEADER = 'plot,size_m2,kind,holder,start,concession,water';
my %KINDS = map { $_ => 1 } qw(full half bed community);

my ($season, @files);
while (@ARGV) {
    my $arg = shift @ARGV;
    if ($arg eq '--season') {
        $season = shift @ARGV;
    } elsif ($arg =~ /^--season=(.*)$/) {
        $season = $1;
    } else {
        push @files, $arg;
    }
}
if (!defined $season || @files != 1) {
    print STDERR "usage: rent.pl --season YEAR PLOTS.csv\n";
    exit 2;
}
if ($season !~ /^[0-9]{4}$/) {
    print STDERR "rent.pl: bad season \"$season\"\n";
    exit 2;
}
my $file = $files[0];

sub fail {
    my ($msg) = @_;
    print STDERR "rent.pl: $msg\n";
    exit 1;
}

sub days_in_month {
    my ($y, $m) = @_;
    return 29 if $m == 2 && (($y % 4 == 0 && $y % 100 != 0) || $y % 400 == 0);
    return (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)[$m - 1];
}

sub parse_date {
    my ($text) = @_;
    return undef unless $text =~ /^([0-9]{4})-([0-9]{2})-([0-9]{2})$/;
    my ($y, $m, $d) = ($1 + 0, $2 + 0, $3 + 0);
    return undef if $y < 1 || $m < 1 || $m > 12 || $d < 1 || $d > days_in_month($y, $m);
    return [$y, $m, $d];
}

sub date_key { my ($d) = @_; return sprintf('%04d%02d%02d', @$d); }

open(my $fh, '<', $file) or fail("cannot read $file");
my (@plots, %seen);
my $n = 0;
my $header_seen = 0;
while (my $line = <$fh>) {
    $n++;
    chomp $line;
    $line =~ s/\r$//;
    if ($n == 1) {
        fail("$file line 1: expected header $HEADER") unless $line eq $HEADER;
        $header_seen = 1;
        next;
    }
    next if $line =~ /^[ \t]*$/;
    my @f = split /,/, $line, -1;
    fail("$file line $n: expected 7 fields, found " . scalar(@f)) unless @f == 7;
    s/^[ \t]+|[ \t]+$//g for @f;
    my ($plot, $size, $kind, $holder, $start, $concession, $water) = @f;
    fail("$file line $n: bad plot id \"$plot\"") unless $plot =~ /^[A-Z][0-9]{1,3}$/;
    fail("$file line $n: plot $plot listed twice") if $seen{$plot}++;
    fail("$file line $n: bad size \"$size\"") unless $size =~ /^[1-9][0-9]*$/;
    fail("$file line $n: unknown kind \"$kind\"") unless $KINDS{$kind};
    my $date;
    if ($holder ne '' || $start ne '') {
        $date = parse_date($start);
        fail("$file line $n: bad start date \"$start\"") unless defined $date;
    }
    fail("$file line $n: bad concession flag \"$concession\"") unless $concession eq '' || $concession eq 'Y';
    fail("$file line $n: bad water flag \"$water\"") unless $water eq '' || $water eq 'Y' || $water eq 'T';
    push @plots, {
        plot => $plot, site => substr($plot, 0, 1), number => substr($plot, 1) + 0,
        size => $size + 0, kind => $kind, holder => $holder, start => $date,
        concession => $concession eq 'Y', water => $water,
    };
}
close $fh;
fail("$file line 1: expected header $HEADER") unless $header_seen;

my $season_start = sprintf('%04d1001', $season);
my $season_end = sprintf('%04d0930', $season + 1);

# Whole months from the month the holder joined to September, counting the month they joined.
sub months_due {
    my ($start) = @_;
    return 12 if date_key($start) le $season_start;
    my ($y, $m) = @$start;
    return ($season + 1) * 12 + 9 - ($y * 12 + $m) + 1;
}

my @charged = sort { $a->{site} cmp $b->{site} || $a->{number} <=> $b->{number} }
              grep { $_->{holder} ne '' && date_key($_->{start}) le $season_end } @plots;

my %full_plots;
my ($total_rent, $total_water) = (0, 0);
print "plot\tholder\trent\twater\n";
for my $p (@charged) {
    my $rent;
    if ($p->{kind} eq 'full' || $p->{kind} eq 'half') {
        my $first = $p->{size} < 125 ? $p->{size} : 125;
        $rent = $first * 40 + ($p->{size} - $first) * 28;
    } elsif ($p->{kind} eq 'bed') {
        $rent = 1800;
    } else {
        $rent = 0;
    }
    # The lower field (site C) floods every winter: 20% off, to the nearest penny.
    $rent = int(($rent * 8 + 5) / 10) if $p->{site} eq 'C';
    # A holder's second and later full plots pay 25% more, rounded up.
    if ($p->{kind} eq 'full' && ++$full_plots{$p->{holder}} > 1) {
        $rent = int(($rent * 5 + 3) / 4);
    }
    $rent = int(($rent + 1) / 2) if $p->{concession} && $rent > 0;
    my $months = months_due($p->{start});
    $rent = int(($rent * $months + 11) / 12) if $months < 12;
    $rent = 1200 if $p->{kind} ne 'community' && $rent < 1200;
    my $water = $p->{water} eq 'Y' ? 1400 : $p->{water} eq 'T' ? 600 : 0;
    $total_rent += $rent;
    $total_water += $water;
    print join("\t", $p->{plot}, $p->{holder}, $rent, $water), "\n";
}
print join("\t", 'total', '', $total_rent, $total_water), "\n";
