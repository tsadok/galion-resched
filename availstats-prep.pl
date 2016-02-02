#!/usr/bin/perl
# -*- cperl -*-

# The purpose of this script is to populate the resched_availstats table.
# This is necessary because the process is too time-consuming to do on the
# fly, particularly when we might want to look at an entire year's stats.

# create table resched_availstats (
#     id integer NOT NULL AUTO_INCREMENT PRIMARY KEY,
#     category tinytext,
#     timeframestart datetime,
#     timeframeend datetime,
#     numavailable integer,
#     numused integer,
#     numtotal integer,
#     flags tinytext );

# The default is to gather stats for yesterday.  Going forward, this
# will work nicely with having the thing run on a cron job every
# morning.  However, to bootstrap, it is also possible to specify
# start and stop dates on the command line.

use DateTime;
use Term::ANSIColor;
require "./include.pl";
require "./db.pl";
require "./datetime-extensions.pl";

my %arg = @ARGV;

my ($startdate, $stopdate);
if ($arg{startdate} =~ m!(\d{4})[-/](\d+)[-/](\d+)!) {
    my ($y, $m, $d) = ($1, $2, $3);
    $startdate = DateTime->new( time_zone => $include::localtimezone,
				year      => $y,
				month     => $m,
				day       => $d);
} else  {
    die "Failed to parse startdate: $arg{startdate}" if $arg{startdate};
    my $yesterday = DateTime->now(time_zone => $include::localtimezone)->clone()->subtract( days => 1 );
    $startdate = DateTime->new( time_zone => $include::localtimezone,
				year      => $yesterday->year(),
				month     => $yesterday->month(),
				day       => $yesterday->day());
}
if ($arg{stopdate} =~ m!(\d{4})[-/](\d+)[-/](\d+)!) {
    my ($y, $m, $d) = ($1, $2, $3);
    $stopdate = DateTime->new( time_zone => $include::localtimezone,
			       year      => $y,
			       month     => $m,
			       day       => $d);
} else  {
    die "Failed to parse startdate: $arg{startdate}" if $arg{stopdate};
    my $today = DateTime->now(time_zone => $include::localtimezone);
    $stopdate = DateTime->new( time_zone => $include::localtimezone,
			       year      => $today->year(),
			       month     => $today->month(),
			       day       => $today->day());
}

my %excluderesource = ();
if ($arg{excluderesources}) { # Mainly useful when retroactively filling in historical availability
                              # stats, if new resources have since been added that, not yet having
                              # been present, should not count as having been "available" then.
  for my $rid (split /,\s*/, $arg{excluderesources}) {
    $excluderesource{$rid}++;
  }
}
my %addresource = ();
if ($arg{addresources}) { # Mainly useful when retroactively filling in historical availability
                          # stats, if old resources have since been retired but should be counted
                          # during the timeframe in question.
  for my $catinfo (split /;\s*/, $arg{addresources}) {
    my ($catname, @res) = split /[,:]\s*/, $arg{addresources};
    for (@res) {
      if (/(\d+)/) {
	my $rid = $1;
	push @{$addresource{$catname}}, $rid;
      } else {
	errorline("Invalid resource ID: $_");
      }
    }
  }
}

print "Gathering availability information starting on " . $startdate->ymd() . ", stopping at " . $stopdate->ymd() . ".\n";
my %closedwday = map { $_ => 1 } split /,\s*/, getvariable('resched', 'daysclosed');

for my $category (include::categories()) {
  my ($catname, @resource) = @$category;
  majorheading($catname);
  @resource = include::uniq(@{$addresource{$catname}},
			    grep { not $excluderesource{$_} } @resource);
  my %res = map { my $rid = $_;
		  my @rec = getrecord('resched_resources', $rid);
		  $rid => $rec[0] } @resource;
  print "Resources: " . (join ", ", map { qq<$_ [$res{$_}{name}]> } @resource) . "\n";
  my @schedule  = include::uniq(map { $$_{schedule} } values %res);
  my %sch = map { my $sid = $_;
		  my @rec = getrecord('resched_schedules', $sid);
		  $sid => $rec[0] } @schedule;

  print "Schedules: " . (join ", ", map { qq<$_ [$sch{$_}{name}]> } @schedule) . "\n";
  my $gcf = include::schedule_start_offset_gcf(map { $sch{$_} } @schedule);
  print "GCF: $gcf\n";

  my %ot = include::openingtimes();
  my %ct = include::closingtimes();

  my $day = $startdate->clone();
  while ($day < $stopdate) {
    my $nextday = $day->clone()->add( days => 1 );
    my $when = $day->clone();
    my $dow = $day->dow() % 7;
    minorheading("day: $day (dow: $dow)");
    if ($closedwday{$dow}) {
      print "  Closed this day of the week.  Skipping.\n";
    } else {
      my ($ohour, $omin) = @{$ot{$dow} || [8,  0] };
      my ($chour, $cmin) = @{$ct{$dow} || [18, 0] };
      print "  open/close times: o = $ohour:$omin; c = $chour:$cmin\n";
      while (($when lt $nextday) and ($when->hour < $ohour))  { $when = $when->add( minutes => $gcf ); }
      print "  advanced to opening hour: $when\n";
      while (($when lt $nextday) and ($when->minute < $omin)) { $when = $when->add( minutes => $gcf ); }
      print "  advanced to opening minute: $when\n";
      print "  next day at $nextday\n";
      # TODO: specially mark days when everything is booked closed.
      while (($when lt $nextday) and (($when->hour < $chour) or ($when->hour == $chour and $when->minute <= $cmin))) {
	my $nextwhen = $when->clone()->add( minutes => $gcf );
	my $time     = sprintf "%1d:%02d", $when->hour, $when->minute;
	print "    time $time:";
	select undef, undef, undef, 0.2; # Be sure to give other processes a chance at the DB.
	my $month = $day->month();
	my ($avail, $used) = (0,0);
	for my $rid (@resource) {
	  if (include::check_for_collision_using_datetimes($rid, $when, $nextwhen->clone()->subtract ( seconds => 1))) {
	    print "u";
	    $used++;
	  } else {
	    print "a";
	    $avail++;
	  }
	}
	print " [$used/$avail]\n";
	markavail($catname, $when, $nextwhen, $avail, $used, $avail + $used, "");
	$when = $nextwhen;
      }
    }
    $day = $nextday;
    print "\n";
  }
}

sub markavail {
  my ($cat, $start, $end, $avail, $used, $total, $flags) = @_;
  $flags ||= '';
  $total ||= $avail + $used;
  my ($r) = findrecord('resched_availstats',
		       category       => $cat,
		       timeframestart => DateTime::Format::ForDB($start),
		       timeframeend   => DateTime::Format::ForDB($end),
		      );
  if (ref $r) {
    $$r{numavailable} = $avail;
    $$r{numused}      = $used;
    $$r{numtotal}     = $total;
    $$r{flags}        = ($$r{flags} =~ /U/) ? $$r{flags} : ($$r{flags} . "U"); # Updated
    updaterecord('resched_availstats', $r);
  } else {
    addrecord('resched_availstats',
	      +{ category       => $cat,
		 timeframestart => DateTime::Format::ForDB($start),
		 timeframeend   => DateTime::Format::ForDB($end),
		 numavailable   => $avail,
		 numused        => $used,
		 numtotal       => $total,
	       });
  }
}

sub errorline {
  my ($title, $color) = @_;
  $color ||= 'bold yellow on_red';
  print color($color);
  print $title;
  print color('reset');
  print "\n";
  return;
}

sub minorheading {
  my ($title, $color) = @_;
  $color ||= 'bold white';
  print "\n";
  print color($color);
  print $title;
  print color('reset');
  print "\n";
  return;
}

sub majorheading {
  my ($title, $color) = @_;
  $color ||= 'bold white on_blue';
  my $paddingneeded = (60 - length($title));
  my $leftpadding   = int($paddingneeded / 2);
  my $rightpadding  = $paddingneeded - $leftpadding;
  print "\n";
  print color($color);
  print " " x 60;
  print color('reset');
  print "\n";
  print color($color);
  print " " x $leftpadding;
  print $title;
  print " " x $rightpadding;
  print color('reset');
  print "\n";
  print color($color);
  print " " x 60;
  print color('reset');
  print "\n";
  return;
}
