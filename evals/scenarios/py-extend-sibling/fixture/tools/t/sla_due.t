#!/usr/bin/perl
# prove tools/t   (from the repository root; uses the calendar in config/)
use strict;
use warnings;
use Test::More;

sub due { my $out = `$^X tools/sla_due.pl @_ 2>&1`; chomp $out; return $out }

is(due('2026-10-01T09:00', 'P1'), '2026-10-01T10:00', 'inside opening hours');
is(due('2026-10-01T12:00', 'P1'), '2026-10-01T14:00', 'lunch is not business time');
is(due('2026-10-01T12:45', 'P1'), '2026-10-01T14:30', 'opened over lunch starts at 13:30');
is(due('2026-10-01T07:10', 'P2'), '2026-10-01T12:30', 'before opening starts at opening; four hours end as the morning closes');
is(due('2026-10-02T15:00', 'P1'), '2026-10-02T16:00', 'due exactly at closing is due at closing');
is(due('2026-10-02T16:45', 'P2'), '2026-10-06T09:30', 'Friday evening: Saturday morning, the Monday holiday, Tuesday');
is(due('2026-10-02T15:59:59', 'P1'), '2026-10-03T10:59', 'seconds are dropped');
is(due('2026-12-23T17:00', 'P2'), '2026-12-24T12:00', 'a holiday with hours is open for those hours');
is(due('2026-12-31T11:00', 'P2'), '2027-01-02T13:00', 'over the new year');
is(due('2026-10-09T10:00', 'P3'), '2026-10-12T17:30', 'sixteen hours over a weekend');
like(due('2026-10-01T09:00', 'P7'), qr/unknown priority 'P7'/, 'unknown priority');
like(due('2026-02-29T09:00', 'P1'), qr/bad time/, 'no such date');
is(`printf '2026-10-01T09:00 P1\n\n2026-10-01T09:00 P4\n' | $^X tools/sla_due.pl`, "2026-10-01T10:00\n2026-10-08T16:30\n",
   'batch form');
done_testing();
