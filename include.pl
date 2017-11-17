#!/usr/bin/perl
# -*- cperl -*-

use strict;
require "./db.pl";
package include;
require "./sitecode.pl"; # Site-specific code should be moved into there.
use Carp;

my $ajaxscript = qq[<script language="javascript" src="ajax.js" type="text/javascript">\n</script>\n];

our %userflag = (
                 A => [A => 'Admin'      => 'User is a ReSched Administrator and can edit user records, site-wide configuration, etc.'],
                 M => [M => 'Multiuser'  => 'Account is used by multiple persons, e.g., a team working a circulation desk together.'],
                );

our %sidebarpos = ( right => 1 ) unless exists $sidebarpos{right}; # Used by contentwithsidebar
# any of 'left', 'right', 'top', and 'bottom' that are set to true
# cause sidebar to appear there.  'right' only is the default.

sub datewithtwelvehourtime {
  my ($dt) = @_;
  confess "datewithtwelvehourtime() needs a DateTime object" if not ref $dt;
  return $dt->year() . '-' . $dt->month_abbr() . '-' . $dt->mday()
    . " at " . twelvehourtime($dt->hour() . ":" . (sprintf "%02d", $dt->minute()));
}

sub twelvehourtimefromdt {
  my ($dt) = @_;
  confess "twelvehourtimefromdt() needs a DateTime object" if not ref $dt;
  my $h = $dt->hour;
  my $m = sprintf "%02d", $dt->minute;
  $m = '' if ($m == 0 and $h ne 12);
  if ($h > 12) {
    $m .= "pm";
    $h -= 12;
  } elsif ($h < 12) {
    $m .= "am";
  }
  return $h . $m if $m =~ /^[ap]m$/;
  return $h . ":" . $m;
}

sub twelvehourtime {
  my ($time, %option) = @_;
  my ($h, $m, $rest) = $time =~ /(\d+)[:](\d+)(.*)/;
  #$rest = '0' . $rest if $rest =~ /^\d$/;
  $m = sprintf "%02d", $m;
  $m = ($m eq '00') ? '' : ":$m";
  if ($h > 12) {
    $h -= 12; $rest .= " pm";
  } else {
    $rest .= " am" unless (($h == 12) or $option{suppressam});
  }
  return $h . $m . $rest;
}

sub htmlordinal {
  my ($number) = @_;
  my $suffix = ordinalsuffix($number);
  return qq[$number<sup>$suffix</sup>];
}

sub ordinalsuffix {
  my ($n) = @_;
  return "th" if ($n > 10 and $n < 14);
  my %th = ( 1 => 'st', 2 => 'nd', 3 => 'rd', map { ($_ => 'th') } (0, 4..9));
  return $th{($n =~ /.*(\d)/)[0]};
}

sub hasaliases {
  my ($name) = @_;
  my @result = main::findrecord('resched_alias', 'canon', $name);
  return @result;
}

sub isalias {
  my ($name) = @_;
  my @result = main::findrecord('resched_alias', 'alias', $name);
  if (@result) {
    return ${$result[-1]}{canon};
  } else {
    return; # false
  }
}

sub dealias {
  my ($name) = @_;
  my @result = main::findrecord('resched_alias', 'alias', $name);
  if (@result) {
    return ${$result[-1]}{canon};
  } else {
    return $name;
  }
}

sub normalisebookedfor {
  my ($rawname, $order) = @_;
  #warn "Normalizing with order $order";
  my $normalname = lc $rawname;
  my ($given, $surname, $suffix, $oldorder);
  if ($normalname =~ /(.+)[,]\s*(.+)\s*\b(ii|iii|iv|vi|vii|viii|jr|esq)?$/) {
    ($surname, $given, $suffix, $oldorder) = ($1, $2, $3, 1);
  } elsif ($normalname =~ /(.*?)\s+(\w+)\s*\b(ii|iii|iv|vi|vii|viii|jr|esq)?$/) {
    ($given, $surname, $suffix, $oldorder) = ($1, $2, $3, 0);
  } else {
    # If all else fails, just treat the whole thing as a surname:
    ($surname, $given, $suffix) = ($normalname, '', '')
  }
  $order = (main::getvariable('resched', 'normal_name_order') || 0) if not defined $order;
  if ($order == 1) { # Smith, James W Jr
    my $rest = join " ", $given, $suffix;
    $normalname = join ", ", $surname, $rest;
  } elsif ($order == 2) { # Eastern order, no comma
    $normalname = join " ", $surname, $given, $suffix;
  } else { # Default to normal Western order.
    $normalname = join " ", $given, $surname, $suffix;
  }
  #use Data::Dumper; warn Dumper(+{ surname => $surname, given => $given, suffix => $suffix, oldorder => $oldorder, order => $order, partially_normalised => $normalname });
  $normalname = sitecode::normalisebookedfor($normalname);
  $normalname =~ s/\s+/ /g;
  $normalname =~ s/[.]//g;
  return $normalname;
}

sub capitalise {
  my ($name) = @_; # This should already be dealiased, if that is desired, and normalised.
  my @p = split /\s+/, $name;
  my @part;
  while (@p) {
    my $n = shift @p;
    $n = ucfirst lc $n;
    if ((scalar @part) > (scalar @p)) {
      # Given names ordinarily don't follow these patterns, but
      # surnames and suffices do:
      $n =~ s/^(Ma?c|Van|(?:[A-Z])(?:[']|[&]#39;))(\w)/$1 . ucfirst $2/e;
      $n =~ s/\b(ii|iii|iv|vi|vii|viii)\b/uc $1/ei;
    }
    push @part, $n;
  }
  return join " ", @part;
}

sub main::persist {
  my ($hidden, $skip, $additional) = @_;
  my %skip = map { $_ => 1 } @{$skip} if ref $skip;
  my $vars = '';
  for my $v (grep { not $skip{$_} } (qw(usestyle useajax category magicdate), @$additional)) {
    if ($main::input{$v}) {
      if ($hidden) {
        $vars .= qq[\n         <input type="hidden" name="$v"   value="$main::input{$v}" />];
      } else {
        if ($vars) {
          $vars .= qq[&amp;$v=$main::input{$v}];
        } else {
          $vars = qq[$v=$main::input{$v}];
        }
      }}}
  return $vars;
}

sub confirmdiv {
  my ($title, $details) = @_;
  return qq[<div class="confirm"><div><strong>$title</strong></div>
     $details</div>];
}

sub errordiv {
  my ($title, $details) = @_;
  return qq[<div class="error"><div><strong>$title</strong></div>
     $details</div>];
}

sub standardoutput {
  # This returns the complete http headers and the html
  # calling code must define sub main::usersidebar that
  # returns an appropriate div.
  my ($title, $content, $ab, $style, $meta, $favicon) = @_;
  $style   ||= 'lowcontrast';
  my $cws = contentwithsidebar($content, "$ab\n".main::usersidebar());
  my $css = include::style($style);
  $favicon ||= main::getvariable('resched', 'bookmark_icon') || 'resched.ico';
  return qq[Content-type: $include::content_type\n$auth::cookie

$include::doctype
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en" lang="en">
<head>
   <!--  This page is served by Galion ReSched, a Resource Scheduling tool.  -->
   <!--  Created by Nathan Eady for Galion Public Library.                   -->
   <!--  Galion ReSched version 0.9.8 vintage 2016 August 12.                -->
   <!--  http://cgi.galion.lib.oh.us/staff/resched-public/                   -->
   <title>$title</title>
   <link rel="SHORTCUT ICON" href="$favicon" />
   $ajaxscript
   $meta
   $css
</head>
<body>
  $cws
$include::footer
</body>
</html>];
}

sub sidebarstylesection {
  my ($preserve, $program) = @_;
  if ($preserve and not $preserve =~ /&amp;$/) {
    $preserve .= '&amp;';
  }
  $program ||= './';
  my $keepajax = 'useajax=' . join ",", map { encode_entities($_) } grep { $_ } split /,\s*/, $main::input{useajax};
  return qq[<div><strong><span onclick="toggledisplay('visualstylelist','visualstylemark');" id="visualstylemark" class="expmark">+</span>
        <span onclick="toggledisplay('visualstylelist','visualstylemark','expand');">Visual Style:</span></strong>
        <div id="visualstylelist" style="display: none;"><ul>
        <!-- Schemes with general appeal: -->
           <li><a href="${program}?${preserve}usestyle=lightondark&amp;$keepajax">Light on Dark</a></li>
           <li><a href="${program}?${preserve}usestyle=darkonlight&amp;$keepajax">Dark on Light</a></li>
           <li><a href="${program}?${preserve}usestyle=lowcontrast&amp;$keepajax">Low Contrast</a></li>
           <!-- li><a href="${program}?${preserve}usestyle=browserdefs&amp;$keepajax">Browser Colors</a></li -->
           <!-- li><a href="${program}?${preserve}usestyle=funwithfont&amp;$keepajax">Fun with Fonts</a></li -->
           <!-- li><a href="${program}?${preserve}usestyle=blackonwite&amp;$keepajax">Black on White</a></li -->
        </ul></div></div>];
}

sub contentwithsidebar {
  # It is up to the calling code to ensure $sidebar will display
  # properly in the position in question.  (This is especially an
  # issue for top or bottom 'sidebars'.
  my ($content, $sidebar) = @_;
  my $colspan = 1 + ($sidebarpos{left}?1:0) + ($sidebarpos{right}?1:0);
  return qq[<table border="0" class="contentwithsidebar" width="100%">]
    . ($sidebarpos{top} ?  qq[<tr class="sidebar"><td class="sidebar" colspan="$colspan">$sidebar</td></tr>]:"")
    . "<tr>" . ($sidebarpos{left} ? qq[<td class="sidebar">$sidebar</td>]:"")
             . qq[<td class="content">\n<!-- **************************************************************************************** -->
\n$content\n
<!-- **************************************************************************************** -->\n</td>]
             . ($sidebarpos{right} ? qq[<td class="sidebar">$sidebar</td>]:"")
             ."</tr>"
    . ($sidebarpos{bottom} ? qq[<tr class="sidebar"><td class="sidebar" colspan="$colspan">$sidebar</td></tr>]:"")
    . "</table>";
}



sub orderedoptionlist {
  my ($listname, $aref, $default, $id) = @_;
  my @option = @{$aref};
  $id ||= $listname;
  my $list = qq[<select name="$listname" id="$id">];
  for my $opt (@option) {
    $list .= qq[<option value="$$opt[0]"].(($$opt[0] eq $default)?' selected="selected"':'').qq[>$$opt[1]</option>];
  }
  $list .= "</select>";
  return $list;
}

sub optionlist {
  my ($listname, $hashref, $default, $id) = @_;
  my %option = %{$hashref};
  $id ||= $listname;
  #use Data::Dumper; warn Dumper(@_);
  my $list = qq[<select name="$listname" id="$id">];
  for my $opt (sort { $a <=> $b } keys %option) {
    $list .= qq[<option value="$opt"].(($opt eq $default)?' selected="selected"':'').qq[>$option{$opt}</option>];
  }
  $list .= "</select>";
  #warn $list;
  return $list;
}

sub parseopenorclosetimes {
  my ($spec) = @_;
  my %t;
  for my $dayspec (split /,/, ($spec)) {
    my ($n, $hour, $min) = $dayspec =~ m/(\d+(?:-\d+)?)[:](\d+)[.:]?(\d*)/;
    #warn "for day $n, closing time is $hour:$min";
    if ($n =~ m/(\d+)\D+(\d+)/) {
      my ($from, $to) = ($1, $2);
      #warn "from $from to $to";
      for my $m ($from .. $to) {
        $t{$m} = [$hour, $min];
      }
    } else {
      $t{$n} = [$hour, $min];
    }}
  if (wantarray) {
    return %t;
  }
  return \%t;
}

sub openingtimes {
  return parseopenorclosetimes(main::getvariable('resched', 'openingtimes') || '0-7:9:0');
}

sub closingtimes {
  return parseopenorclosetimes(
                               main::getvariable('resched', 'closingtimes')
                               || '0:12.00,1-2:20:00,3:15:00,4-5:20:00,6:15:00');
}

sub houroptions {
  my ($selectedhour, $dow) = @_;
  carp "houroptions called without day of week" if not $dow;
  $dow ||= 1; # Default is to supply Monday's times.  Why?  Because.
  my %ot = openingtimes();
  my %ct = closingtimes();
  return join "\n            ",
    map {
      my $val = $_;
      my $hour = ($val <= 12) ? ("$val"."am") : (($val-12)."pm");
      my $selected = ($_ == $selectedhour) ? ' selected="selected"' : '';
      qq[<option value="$val"$selected>$hour</option>]
    } ($ot{$dow}[0] || 9) .. ($ct{$dow}[0] || 20);
}

our $doctype = qq[<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">];
our $content_type = "text/html";

sub include::check_for_collision_using_datetimes {
  my ($res, $begdt, $enddt) = @_;
  die "check_for_collision_using_datetimes takes datetime arguments for the timeslot beginning and end" unless (ref $begdt and ref $enddt);
  my $beg = DateTime::Format::ForDB($begdt);
  my $end = DateTime::Format::ForDB($enddt);
  return include::check_for_collision($res, $beg, $end);
}
sub include::check_for_collision {
  # This is an optimization.  Previously we fetched all results for
  # the resource in question, made DateTime objects for their start
  # and end, and checked for overlap using DateTime::Duration.  That
  # was reliable, but this way is a big performance improvement.
  my ($res, $beg, $end) = @_;
  die "check_for_collision does not take datetime arguments; use check_for_collision_using_datetimes if you need that" if (ref $beg or ref $end);
  my $db = main::dbconn();
  my ($resid) = $res =~ /(\d+)/;
  my $q = $db->prepare("SELECT * FROM resched_bookings WHERE resource=? AND until > ? AND fromtime < ?");
  $q->execute($resid, $beg, $end);
  my (@answer, $r);
  while ($r = $q->fetchrow_hashref()) { push @answer, $r; }
  #warn "Checked for collisions on resource $res from $beg until $end: found " . scalar @answer . " collision(s) on behalf of $ENV{REMOTE_ADDR}.\n"; # TODO:  Comment this out when we're sure all is well.
  return @answer;
}

sub include::style {
  my ($s) = @_;
  $s ||= 'lowcontrast';
  my %stylesub = ( # a holdover from the old style system, for backward compatibility only.
                  manilla     => 'darkonlight',
                  hicmanilla  => 'darkonlight',
                  lightpurple => 'darkonlight',
                  softpurple  => 'lightondark',
                  burgundy    => 'lightondark',
                  neonlites   => 'lightondark',
                  britewite   => 'blackonwite',
                  jonadabian  => 'lightondark',
                 );
  $s = $stylesub{$s} if $stylesub{$s};
  my %style = (
               lightondark => qq[<link rel="stylesheet" type="text/css" media="screen" href="lightondark.css" title="Light on Dark Colors" />],
               darkonlight => qq[<link rel="stylesheet" type="text/css" media="screen" href="darkonlight.css" title="Dark on Light Colors" />],
               lowcontrast => qq[<link rel="stylesheet" type="text/css" media="screen" href="lowcontrast.css" title="Low Contrast" />],
               #browserdefs => qq[<link rel="stylesheet" type="text/css" media="screen" href="browserdefs.css" title="Browser Colors" />],
               #funwithfont => qq[<link rel="stylesheet" type="text/css" media="screen" href="funwithfont.css" title="Fun with Fonts" />],
               #blackonwite => qq[<link rel="stylesheet" type="text/css" media="screen" href="blackonwite.css" title="Black on White" />],
              );
  my $style = join "\n", (map {
    $style{$_}
  } sort {
    ($a eq $s) ? -1 : (($b eq $s) ? 1 : ($b cmp $a))
  } keys %style), ($s ? $style{$s} : '');
  my $nonajaxstyle = qq[
<style type="text/css">

.nonajax {
  display: none;
}

.nobr {
  white-space: nowrap;
}

</style>] unless $main::input{ajax} eq 'off';
  return qq[
$style
<link rel="stylesheet" type="text/css" media="print"  href="print.css" />

$nonajaxstyle
];
}

our $footer = qq[<div class="footer">
<p class="noprint">Powered By <abbr title="Linux, Apache, MySQL, Perl"><a href="http://www.onlamp.com">LAMP</a></abbr>
   and <abbr title="Asynchronous Javascript And XML"><a href="http://en.wikipedia.org/wiki/AJAX">AJAX</a></abbr> Technologies:
<a href="http://www.linux.org"><img src="tux-small.png" alt="Linux, "></img></a>
<a href="http://www.apache.org"><img src="feather-small.png" alt="Apache, "></img></a>
<a href="http://www.mysql.com/"><img src="dolphin-blue-white-small.png" alt="MySQL, " width="36" height="32"></img></a>
<a href="http://www.perl.com/"><img src="camel-small.png" alt="Perl, " width="28" height="31"></img></a>
<a href="http://en.wikipedia.org/wiki/Javascript"><img src="rhino.png" alt="Javascript, " width="23" height="32" /></a>
<abbr title="Extensible Markup Language"><a href="http://www.w3.org/XML/"><code>&lt;xml/&gt;</code></a></abbr>
</p></div>\n];

our $localtimezone = main::getvariable('resched', 'time_zone') || "America/New_York";

sub categories {
  my $categories = main::getvariable('resched', 'categories');
  my @category;
  if ($categories) {
    @category = map {
      my ($catname, @id) = split /,\s*/, $_;
      [$catname, map { /(\w+)/; $1 } @id]
    } grep { $_ } split /\r?\n/, $categories;
  } else {
    @category = map {
      [$$_{name} => $$_{id}]
    } grep {
      not $$_{flags} =~ /X/
    } main::getrecord('resched_resources');
  }
  #use Data::Dumper; warn Dumper(+{ categories => \@category,
  #                                 variable   => $categories,
  #                               });
  return @category;
}

sub uniq {
  my %seen;
  return grep { not $seen{$_}++ } @_;
}

sub uniqnonzero {
  my %seen = ( 0 => 1 );
  return grep { not $seen{$_}++ } @_;
}

sub schedule_start_offset_gcf { # Returns GCF of the _offsets_ (not of the start times themselves).
  my (@s) = @_;
  # We want the starttimes as numbers of minutes since midnight.
  my @starttime = uniq(map { $$_{firsttime} =~ m/(\d{2})[:](\d{2})[:]\d{2}/; (60*$1)+$2; } @s);

  my $gcf;
  # Start based on schedules...

  # We need the gcf of the durations of the _offsets_ (not of the
  # start times themselves).  The algo below takes permutations,
  # which will run in O(n*n) time, so don't feed it large numbers
  # of distinct starttimes.
  my @offset = uniqnonzero map {
    my $st = $_;
    map { abs ($st - $_) } @starttime;
  } @starttime;

  # Now, we need the gcf of these offsets taken together with the
  # intervals from the actual schedules:
  $gcf = arithgcf(@offset, uniqnonzero map { $$_{intervalmins} } @s);
  return $gcf;
}

sub primefactor {
  # Don't try to do huge numbers (e.g., for cryptanalysis) with this, but it works for our purposes:
  my ($composite) = @_;
  die "Cannot prime-factor a non-integer value ($composite)" unless ($composite == int $composite);
  my $pf = 2;
  my @fact;
  while ($composite >= $pf) {
    while (not ($composite % $pf)) {
      $composite /= $pf;
      push @fact, $pf;
    }
    $pf++;
  }
  return @fact;
}

sub arithgcf {
  # return the greatest common factor of the integers in @_.
  # primefactor will die if any are non-integers.
  my ($f, $pf);
  my @pf = map {
    my @f = primefactor(abs $_);
    my %f;
    for (@f) { ++$f{$_} }
    \%f
  } @_;
  my %pf = %{ $pf[0] };
  my %opf = %pf;
  for $f (@pf) {
    my %f = %$f;
    for (keys %f) {
      if (exists $pf{$_}) {
        $pf{$_} = $f{$_} if $pf{$_} >= $f{$_};
      }
    }
    for (keys %pf) {
      delete $pf{$_} unless $f{$_};
    }
  }
  my $gcf = 1;
  for $pf (keys %pf) {
    for (1..$pf{$pf}) {
      $gcf *= $pf;
    }
  }
  return $gcf;
}

# The following works, but we ended up not needing it:
# sub arithlcd {
#   # return the lowest common denominator of the integers in @_.
#   # primefactor will die if any are non-integers.
#   my @pf = map {[primefactor abs $_]} @_;
#   my %pf;
#   for (@pf) {
#     my %f;
#     for (@$_) { ++$f{$_} }
#     for (keys %f) {
#       $pf{$_} = $f{$_} unless $pf{$_} >= $f{$_};
#     }
#   }
#   my $lcd = 1;
#   for $pf (keys %pf) {
#     for (1..$pf{$pf}) {
#       $lcd *= $pf;
#     }
#   }
#   return $lcd;
# }

sub getnum {
  my ($name) = @_;
  my ($num) = $main::input{$name} =~ /([0-9.]+)/;
  return $num;
}

sub possessive {
  my ($noun) = @_;
  if ($noun =~ /[']s$/i) {
    return $noun
  } elsif ($noun =~ /s[']/i) {
    return $noun;
  } elsif ($noun =~ /s$/i) {
    return $noun . "'";
  } else {
    return $noun . "'s";
  }
}

sub sgorpl {
  my ($num, $sg, $pl) = @_;
  if ($num == 1) {
    return(qq[$num $sg]);
  }
  return($num . ' ' . ($pl || ($sg . "s")));
}
sub isare {
  my ($num) = @_;
  return inflectverbfornumber($num, 'is', 'are');
}
sub inflectverbfornumber {
  my ($num, $sg, $pl) = @_;
  if (not defined $pl) {
    # Handles weak verbs only.
    if ($sg =~ /e$/) { $pl = $sg . 'd'; } else { $pl = $sg . 'ed'; }
  }
  return $sg if ($num == 1);
  return $pl;
}

sub parsemonth {
  local ($_)=@_;
  if    (/\d+/)   { return $1; }
  elsif (/^jan/i) { return  1; }
  elsif (/^feb/i) { return  2; }
  elsif (/^mar/i) { return  3; }
  elsif (/^apr/i) { return  4; }
  elsif (/^may/i) { return  5; }
  elsif (/^jun/i) { return  6; }
  elsif (/^jul/i) { return  7; }
  elsif (/^aug/i) { return  8; }
  elsif (/^sep/i) { return  9; }
  elsif (/^oct/i) { return 10; }
  elsif (/^nov/i) { return 11; }
  elsif (/^dec/i) { return 12; }
  else {
    return 0;
  }
}

1;
