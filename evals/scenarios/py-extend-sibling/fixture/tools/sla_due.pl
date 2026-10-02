#!/usr/bin/perl
# sla_due.pl: when a ticket's first response is due, by support's business calendar.
#
#   tools/sla_due.pl [--config DIR] OPENED PRIORITY     one ticket
#   tools/sla_due.pl [--config DIR] < tickets.txt       "OPENED PRIORITY" per line, one due time per line
#
# OPENED is the office's local time, YYYY-MM-DDTHH:MM with optional :SS (seconds are dropped). The due time is
# printed as YYYY-MM-DDTHH:MM. DIR (default: config) holds business-hours.conf, holidays.txt, and
# sla-targets.conf; docs/sla.md describes them and the rules. An unknown priority is an error (in the batch form
# the line prints "-" and the exit status is 1 at the end).
use strict;
use warnings;
use Time::Local qw(timegm);

my @DAYS = qw(sun mon tue wed thu fri sat);
my $config = 'config';
if (@ARGV >= 2 && $ARGV[0] eq '--config') {
    $config = $ARGV[1];
    splice @ARGV, 0, 2;
}
die "usage: sla_due.pl [--config DIR] [OPENED PRIORITY]\n" unless @ARGV == 0 || @ARGV == 2;

my (%weekly, %holiday, %target);

sub fail { my ($file, $n, $msg) = @_; die "sla_due: $file line $n: $msg\n" }

sub minutes {    # "HH:MM" -> minutes since midnight; 24:00 is allowed as an end
    my ($hhmm) = @_;
    my ($h, $m) = $hhmm =~ /^([01][0-9]|2[0-4]):([0-5][0-9])$/ or return undef;
    my $t = $h * 60 + $m;
    return $t <= 1440 ? $t : undef;
}

sub interval {    # "HH:MM-HH:MM" -> [start, end] or undef
    my ($text) = @_;
    my ($a, $b) = $text =~ /^(\d\d:\d\d)-(\d\d:\d\d)$/ or return undef;
    my ($s, $e) = (minutes($a), minutes($b));
    return undef unless defined $s && defined $e && $s < $e && $s < 1440;
    return [$s, $e];
}

sub lines {    # the meaningful lines of a config file: [number, text]
    my ($name) = @_;
    my $path = "$config/$name";
    open my $fh, '<', $path or die "sla_due: cannot read $path: $!\n";
    my @out;
    while (my $line = <$fh>) {
        $line =~ s/#.*//;
        $line =~ s/^\s+|\s+$//g;
        push @out, [$., $line] if length $line;
    }
    close $fh;
    return @out;
}

sub add_interval {    # keep a day's intervals sorted; overlapping or touching ones are an error
    my ($list, $iv, $file, $n) = @_;
    for my $o (@$list) {
        fail($file, $n, 'overlapping hours') if $iv->[0] <= $o->[1] && $o->[0] <= $iv->[1];
    }
    @$list = sort { $a->[0] <=> $b->[0] } @$list, $iv;
}

for (lines('business-hours.conf')) {
    my ($n, $text) = @$_;
    my ($day, $span) = $text =~ /^(\w+)\s+(\S+)$/ or fail('business-hours.conf', $n, 'expected "DAY HH:MM-HH:MM"');
    my ($i) = grep { $DAYS[$_] eq lc $day } 0 .. 6;
    fail('business-hours.conf', $n, "unknown day '$day'") unless defined $i;
    my $iv = interval($span) or fail('business-hours.conf', $n, "bad hours '$span'");
    add_interval($weekly{$i} ||= [], $iv, 'business-hours.conf', $n);
}

for (lines('holidays.txt')) {
    my ($n, $text) = @$_;
    my ($date, $span) = $text =~ /^(\d{4}-\d\d-\d\d)(?:\s+(\S+))?$/ or fail('holidays.txt', $n, 'expected "YYYY-MM-DD [HH:MM-HH:MM]"');
    defined day_number($date) or fail('holidays.txt', $n, "no such date '$date'");
    $holiday{$date} ||= [];
    next unless defined $span;
    my $iv = interval($span) or fail('holidays.txt', $n, "bad hours '$span'");
    add_interval($holiday{$date}, $iv, 'holidays.txt', $n);
}

for (lines('sla-targets.conf')) {
    my ($n, $text) = @$_;
    my ($prio, $amount, $unit) = $text =~ /^(\S+)\s+(\d+)([mh])$/ or fail('sla-targets.conf', $n, 'expected "PRIORITY Nm" or "PRIORITY Nh"');
    my $m = $unit eq 'h' ? $amount * 60 : $amount;
    fail('sla-targets.conf', $n, 'a target must be more than nothing') unless $m > 0;
    $target{$prio} = $m;
}

sub day_number {    # "YYYY-MM-DD" -> days since 1970-01-01, or undef when there is no such date
    my ($date) = @_;
    my ($y, $mo, $d) = $date =~ /^(\d{4})-(\d\d)-(\d\d)$/ or return undef;
    my $t = eval { timegm(0, 0, 0, $d, $mo - 1, $y) };
    return undef unless defined $t;
    my @g = gmtime $t;
    return undef unless $g[3] == $d && $g[4] == $mo - 1 && $g[5] + 1900 == $y;
    return int($t / 86400);
}

sub date_of {    # days since 1970-01-01 -> ("YYYY-MM-DD", weekday 0=sun)
    my ($day) = @_;
    my @g = gmtime($day * 86400);
    return (sprintf('%04d-%02d-%02d', $g[5] + 1900, $g[4] + 1, $g[3]), $g[6]);
}

sub hours_on {    # the open intervals of a day: its holiday line(s) if it has any, else its weekday's
    my ($day) = @_;
    my ($date, $wday) = date_of($day);
    return @{ $holiday{$date} } if exists $holiday{$date};
    return @{ $weekly{$wday} || [] };
}

sub due {
    my ($opened, $prio) = @_;
    my ($date, $hh, $mm) = $opened =~ /^(\d{4}-\d\d-\d\d)T(\d\d):(\d\d)(?::\d\d)?$/
        or return (undef, "bad time '$opened'");
    my $day = day_number($date);
    return (undef, "bad time '$opened'") unless defined $day && $hh < 24 && $mm < 60;
    return (undef, "unknown priority '$prio'") unless exists $target{$prio};
    my ($now, $left) = ($hh * 60 + $mm, $target{$prio});
    for my $step (0 .. 3660) {
        for my $iv (hours_on($day)) {
            my ($s, $e) = @$iv;
            next if $e <= $now;
            my $from = $s > $now ? $s : $now;
            if ($left <= $e - $from) {
                my $at = $from + $left;
                my ($d) = date_of($day);
                return (sprintf('%sT%02d:%02d', $d, int($at / 60), $at % 60)) if $at < 1440;
                ($d) = date_of($day + 1);    # due at 24:00: midnight, the start of the next day
                return ("${d}T00:00");
            }
            $left -= $e - $from;
        }
        $day++;
        $now = 0;
    }
    return (undef, 'no business hours within ten years');
}

if (@ARGV == 2) {
    my ($at, $err) = due(@ARGV);
    die "sla_due: $err\n" unless defined $at;
    print "$at\n";
    exit 0;
}
my $status = 0;
while (my $line = <STDIN>) {
    chomp $line;
    next unless $line =~ /\S/;
    my ($opened, $prio) = split ' ', $line;
    my ($at, $err) = due($opened, defined $prio ? $prio : '');
    if (defined $at) {
        print "$at\n";
    } else {
        print "-\n";
        warn "sla_due: line $.: $err\n";
        $status = 1;
    }
}
exit $status;
