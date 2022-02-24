#!/usr/bin/perl -wT
# -*- cperl -*-

use strict;
use Carp;
use DateTime;
use DateTime::Span;
use Data::Dumper;
use File::Spec::Functions;
#use Math::SigFigs;

require "./include.pl";
require "./db.pl";
require "./datetime-extensions.pl";
require "./prefs.pl";
our %eracolor;
require "./hours-historical.pl";

our $defaultlibdir = "/usr/local/svg_graph";
my ($libdir) = getvariable('resched', 'svg_graphs_install_dir') || $defaultlibdir;
if ($libdir and -e $libdir) {
  eval {
    do "" . catfile($libdir, "svg_graph.pl");
  };
} else {
  die "Cannot proceed without svg_graph dependency.";
}

our %input = @ARGV;
our $now = DateTime->now(time_zone => $include::localtimezone);

die "Must specify category." if not $input{category};
my @allcategory = include::categories("statgraphcategories");
my ($cat) = grep { $$_[0] eq $input{category} } @allcategory;
die "No such category known: '$input{category}' (known categories: " . (join ", ", map { $$_[0] } @allcategory) . ")" if not $cat;

my ($catname, @res) = @$cat;
@res = map {
  my $r = $_;
  my @x;
  if ($r =~ /^\d+\s*$/) {
    push @x, $r;
  } else {
    my ($subcat) = grep { $$_[0] eq $r } @allcategory;
    if (ref $subcat) {
      my $dummy;
      ($dummy, @x) = @$subcat;
      warn "Throwing away subcategory name: $dummy\n";
    }
  }
  @x;
} @res;
print "Category $catname\nResources @res\n";
my $colorfield = ((($input{rescolors} || "") =~ /dark/)  ? "darkbg" :
                  (($input{rescolors} || "") =~ /light/) ? "lightbg" :
                  "lowcontrastbg");
my %color = map { $$_{id} => $$_{$colorfield} } getrecord("resched_booking_color");
my %res   = map { $$_{id} => $_ } getrecord("resched_resources");
my %rescolor = map { $_ => $color{$res{$_}{bgcolor}} } keys %res;

my (@ts, @peakts, %stat, %mstat, %mcnt);
my $startday = DateTime->new( time_zone => $include::localtimezone,
                              year      => $input{startyear}  || ($now->year() - 2),
                              month     => $input{startmonth} || 1,
                              day       => $input{startmday}  || $input{startday} || 1,
                            );
my $tsmins = $input{timeslotminutes} || 30;
my $day = $startday->clone();
my ($starthour, $startmin, $stophour, $stopmin, $era);

print "Starting from " . $day->ymd() . "\n";
print "Processing ...\n"; $|=1;
my $lastera = "Start";
while ($day->ymd() lt $now->ymd()) {
  ($starthour, $startmin, $stophour, $stopmin, $era) = historical_hours_of_operation($day);
  if ($era ne $lastera) {
    print "\n$era...\n";
    $lastera = $era;
  }
  if ($day->mday() == 1) {
    print "\n" . $day->year() . "-" . sprintf("%02d", $day->month()) . " ";
  }
  print ".";
  my $dt = DateTime->new( time_zone => $include::localtimezone,
                          year      => $day->year(),
                          month     => $day->month(),
                          day       => $day->mday(),
                          hour      => $starthour,
                          minute    => $startmin,
                        );
  my $enddt = $dt->clone()->add( minutes => $tsmins );
  my @dayts;
  my $daymax = 0;
  while (($enddt->hour < $stophour) or (($enddt->hour == $stophour) and ($enddt->minute <= $stopmin))) {
    my @booked;
    for my $r (@res) {
      my @booking = include::check_for_collision_using_datetimes($r, $dt, $enddt);
      push @booked, $r if @booking;
    }
    #print scalar @booked;
    my $x = +{ era        => $era,
               dow        => $day->dow(),
               day        => $day,
               start_time => $dt,
               stop_time  => $enddt,
               resources  => [@booked]
             };
    push @dayts, $x;
    push @ts, $x;
    $daymax = scalar @booked if $daymax < scalar @booked;
    $dt = $enddt;
    $enddt = $dt->clone()->add( minutes => $tsmins );
  }
  my ($pts) = grep { $daymax == scalar @{$$_{resources}} } @dayts;
  push @peakts, $pts if $pts;
  $day = $day->add( days => 1 );
}

my $hcnt     = scalar @ts;
my $daycount = scalar @peakts;
my $max = 0;
my (%eracnt);
for my $r (@ts) {
  my $count = scalar @{$$r{resources}};
  $max = $count if $max < $count;
  $stat{$$r{era}}{$count}++;
  $stat{overview}{$count}++;
  $eracnt{$$r{era}}++;
  $eracnt{overview}++;
}
for my $r (@peakts) {
  my $count = scalar @{$$r{resources}};
  $mstat{$$r{era}}{$count}++;
  $mstat{overview}{$count}++;
  $mcnt{$$r{era}}++;
  $mcnt{overview}++;
}

for my $era (keys %stat) {
  print "$era:\n";
  for my $c (sort { $b <=> $a } keys %{$stat{$era}}) {
    my $hours = $stat{$era}{$c} / 2;
    my $pct   = roundpct(100 * $stat{$era}{$c} / ($eracnt{$era} || 1));
    my $ppct  = roundpct(100 * $mstat{$era}{$c} / ($mcnt{$era} || 1));
    print "  $c booked, $hours hours (" . $pct . "%); peak usage on $mstat{$era}{$c} days (" . $ppct . ")\n";
  }
  print "\n";
}
#exit 0;

my @elt;
my @peak;
my $bd = backdrop(%input);
push @elt, $bd;
push @peak, $bd;
push @elt, $_ for legend('rect',
                         legendwidth => ($input{legendwidth} || 100),
                         data => [map { my $k = $_;
                                        +{ name   => encode_entities($res{$k}{name} || $k),
                                           color  => $rescolor{$k},
                                         },
                                       } @res #keys %rescolor
                                 ],
                        );
push @elt, $_ for grid($max, $hcnt, undef, xlabels => [map { my $dt = $ts[$_]{start_time};
                                                             my ($yr) = $dt->year() =~ /(\d{2})$/;
                                                             $yr . "-" . $dt->month_abbr()
                                                           } 1 .. $hcnt], %input);
push @peak, $_ for grid($max, $daycount, undef, %input);

my $barwidth  = (825 - ($input{legendwidth} || 100)) / $hcnt;
my $barheight = 600 / $max;

my $n = 0;
for my $t (@ts) {
  my $xpos = 100 + ($barwidth * $n);
  # TODO: era indicator
  my $m = 0;
  for my $r (@{$$t{resources}}) {
    $m++;
    push @elt, rect( fillcolor   => $rescolor{$r},
                     x           => $xpos,
                     y           => 700 - ($m * $barheight),
                     width       => $barwidth,
                     height      => $barheight,
                     borderwidth => 0,
                     bordercolor => $rescolor{$r},
                   );
  }
  $n++;
}
my $fn = "usage-stack-graph.svg";
open SVG, ">", $fn;
print SVG svg(@elt);
close SVG;
print "\nWrote $fn\n";


$barwidth = 825 / $daycount;
$n = 0;
for my $t (@peakts) {
  my $xpos = 100 + ($barwidth * $n);
  my $m = scalar @{$$t{resources}};
  push @peak, rect( fillcolor   => $eracolor{$$t{era}},
                    x           => $xpos,
                    y           => 700 - ($m * $barheight),
                    width       => $barwidth,
                    height      => $m * $barheight,
                    borderwidth => 0,
                    bordercolor => $eracolor{$$t{era}},
                  );
  $n++;
}
$fn = "peak-usage-stack-graph.svg";
open SVG, ">", $fn;
print SVG svg(@peak);
close SVG;
print "\nWrote $fn\n";


sub roundpct {
  my ($pct) = @_;
  if ($pct > 10) {
      $pct = int $pct;
    } elsif ($pct > 1) {
      $pct = sprintf("%0.0f", $pct);
    } elsif ($pct > 0.1) {
      $pct = sprintf("%0.00f", $pct);
    } elsif ($pct > 0.01) {
      $pct = sprintf("%0.000f", $pct);
    }
  return $pct;
}
