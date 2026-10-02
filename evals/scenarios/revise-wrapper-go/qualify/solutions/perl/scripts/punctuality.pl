#!/usr/bin/env perl
# Punctuality figures per route, for `ferry punctuality`: scripts/punctuality.py in Perl, for hosts without
# Python. Reads {"sailings": [{"route", "delay"}, ...]} as JSON on standard input and writes {"routes": [...]}.
use strict;
use warnings;
use sort 'stable';
use JSON::PP;
use POSIX qw(floor);

my $json = JSON::PP->new->utf8;
my $input = do { local $/; <STDIN> };
my $request = $json->decode($input);

my (@order, %delays);
for my $s (@{ $request->{sailings} }) {
    my $route = $s->{route};
    push @order, $route unless exists $delays{$route};
    push @{ $delays{$route} }, $s->{delay};
}

my @routes;
for my $route (@order) {
    my @ds = @{ $delays{$route} };
    my @ran = grep { defined } @ds;
    my %bands;
    $bands{ floor($_ / 5) * 5 }++ for @ran;
    my @sorted = sort { $a <=> $b } @ran;
    my $n = @sorted;
    my $median = !$n ? undef : $n % 2 ? $sorted[($n - 1) / 2] : ($sorted[$n / 2 - 1] + $sorted[$n / 2]) / 2;
    push @routes, {
        route     => $route,
        sailings  => scalar(@ds),
        cancelled => @ds - @ran,
        on_time   => scalar(grep { $_ <= 5 } @ran),
        median    => $median,
        worst     => $n ? $sorted[-1] : undef,
        bands     => [ map { [ $_ + 0, $bands{$_} ] } sort { $a <=> $b } keys %bands ],
    };
}

sub share {
    my ($r) = @_;
    my $ran = $r->{sailings} - $r->{cancelled};
    return $ran ? $r->{on_time} / $ran : -1;
}

@routes = sort { share($a) <=> share($b) } @routes;
print $json->encode({ routes => \@routes }), "\n";
