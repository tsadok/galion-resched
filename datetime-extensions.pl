#!/usr/bin/perl
# -*- cperl -*-

use DateTime;
use DateTime::Format::MySQL;
use Carp;

use strict;
require "./db.pl";

# The following can be overridden:
our $firsthour = 8;
our $lasthour = 20;

sub DateTime::Format::Cookie {
  my ($dt) = @_;
  $dt->set_time_zone('UTC');
  # Example of the correct format:  Wed, 01 Jan 3000 00:00:00 GMT
  return ((ucfirst $dt->day_abbr())   . ", " .
          sprintf("%02d",$dt->mday()) . " "  .
          $dt->month_abbr()           . " "  .
          sprintf("%04d", $dt->year)  . " "  .
          $dt->hms()                  . " GMT");
}

sub DateTime::Format::ForDB {
  my ($dt) = @_;
  return DateTime::Format::MySQL->format_datetime($dt) if $dt;
  carp "Pestilence and Discomfort: $dt";
}

sub DateTime::Format::ForURL {
  my ($dt) = @_;
  ref $dt or confess "DateTime::Format::ForURL called without a DateTime object.";
  my $string = DateTime::Format::ForDB($dt);
  $string =~ s/\s/_/g;
  return $string;
}

sub DateTime::Format::ts {
  my ($dt) = @_;
  ref $dt or confess "DateTime::Format::ts called without a DateTime object.";
  return sprintf "%04d%02d%02d%02d%02d%02d", $dt->year, $dt->month, $dt->mday, $dt->hour, $dt->minute, $dt->second; 
}

sub DateTime::From::MySQL {
  my ($dtstring, $tzone, $dbgmsg) = @_;
  $tzone ||= $include::localtimezone || 'America/New_York';
  if ($dtstring =~ /(\d{4})-(\d{2})-(\d{2})(?:[_]+|\s+|T)(\d{2})[:](\d{2})[:](\d{2})/) {
    return DateTime->new(
                         year   => $1,
                         month  => $2,
                         day    => $3,
                         hour   => $4,
                         minute => $5,
                         second => $6,
                         time_zone => $tzone,
                        );
  } else {
    carp "from_mysql $dbgmsg:  Cannot parse datetime string: '$dtstring'";
    return undef;
  }
}

sub DateTime::NormaliseInput {
  # Basically, this lets you get datetimes out of years, months, and
  # stuff.  For the reverse operation, see DateTime::Form::Fields

  # Takes a hashref, which is presumed to contain CGI input.  Picks
  # out keys of the form foo_datetime_bar (where bar is 'year',
  # 'month', and so on and so forth) and synthesizes them into
  # foo_datetime (the value of which will be a DateTime object) for
  # all foo.  Returns a hashref containing the normalised data.  The
  # year is mandatory for synthesis to occur; all other portions of
  # the date if missing will default to DateTime's defaults; if that's
  # a problem, ||= your own defaults into the hash beforehand.  Input
  # fields that do not match the magic pattern are unchanged.
  my %input = %{shift@_};
  for (grep { $_ =~ m/_datetime_year$/ } keys %input) {
    /^(.*)[_]datetime_year/;
    my $prefix = $1;
    my %dt = map {
      /${prefix}_datetime_(.*)/;
      my $k = $1;
      my $v = $input{"${prefix}_datetime_$k"};
      delete $input{$_};
      # push @DateTime::NormaliseInput::Debug, "<!-- $k => $v -->";
      $k => $v;
    } grep {
      /${prefix}_datetime_/;
    } keys %input;
    push @DateTime::NormaliseInput::Debug, "<!-- " . Dumper(\%dt) . " -->";
    $input{"${prefix}_datetime"} = DateTime->new(%dt);
  }
  push @DateTime::NormaliseInput::Debug, "<!-- " . Dumper(\%input) . " -->";
  return \%input;
}

our %monthname =
  (
   1 => "January",
   2 => "February",
   3 => "March",
   4 => "April",
   5 => "May",
   6 => "June",
   7 => "July",
   8 => "August",
   9 => "September",
   10 => "October",
   11 => "November",
   12 => "December",
  );

sub DateTime::Form::Fields {
  my ($dt, $prefix, $skipdate, $skiptime, $dbgmsg, %optn) = @_;
  croak "DateTime::Form::Fields requires a datetime object as the first argument" if not ref $dt;
  # skipdate and skiptime, if set to the magic value of 'disable',
  # don't skip, but "disable" editing.  (This is a UI feature only; it
  # is not secure.)
  #confess " DateTime::Form::Fields $dbgmsg [@_]" if $dbgmsg;
  my $result = qq[];
  my ($disabledate, $disabletime);
  if ($skiptime eq 'disable') { $disabletime = ' disabled="disabled"'; undef $skiptime; }
  if ($skipdate eq 'disable') { $disabledate = ' disabled="disabled"'; undef $skipdate; }
  my ($dtyear, $yearinput, $monthinput, $mdayinput, $hourinput, $mininput) = (('') x 6);
  if (not $skipdate) {
    $dtyear = $dt->year;
    my $copyyear = $optn{copydate} ? (qq[ onchange="copyfieldvalue('${prefix}_datetime_year', '$optn{copydate}_datetime_year');"]) : '';
    my $copymon  = $optn{copydate} ? (qq[ onchange="copyfieldvalue('${prefix}_datetime_month', '$optn{copydate}_datetime_month');"]) : '';
    my $copymday = $optn{copydate} ? (qq[ onchange="copyfieldvalue('${prefix}_datetime_day', '$optn{copydate}_datetime_day');"]) : '';
    $yearinput   = qq[<input type="text" size="6" id="${prefix}_datetime_year" name="${prefix}_datetime_year" value="$dtyear"$disabledate$copyyear></input>];
    $monthinput  = qq[<select id="${prefix}_datetime_month" name="${prefix}_datetime_month"$disabledate$copymon>\n                ]
      .(join "\n                ", map {
        my $monnum = $_;
        my $selected = ($monnum == $dt->month) ? ' selected="selected"' : "";
        qq[                <option value="$monnum" $selected>$monthname{$monnum}</option>]
      } 1..12) . qq[</select>];
    $mdayinput = qq[<input type="text" size="3" name="${prefix}_datetime_day" id="${prefix}_datetime_day" value="].
           ($dt->mday) . qq["$disabledate$copymday></input>];
  }
  if (not $skiptime) {
    my $copyhour = $optn{copytime} ? (qq[ onchange="copyfieldvalue('${prefix}_datetime_hour', '$optn{copytime}_datetime_hour');"]) : '';
    my $copymin  = $optn{copytime} ? (qq[ onchange="copyfieldvalue('${prefix}_datetime_minute', '$optn{copytime}_datetime_minute');"]) : '';
    $hourinput = qq[<select name="${prefix}_datetime_hour" id="${prefix}_datetime_hour"$disabletime$copyhour>]
      .(join $/, map {
           my $selected = ($_ == $dt->hour) ? qq[ selected="selected"] : "";
           qq[<option value="$_" $selected>].(($_>12)?(($_-12) . " pm"):(($_<12)?"$_ am":$_))."</option>"
         } $firsthour .. $lasthour).qq[</select>];
    $mininput = qq[<select name="${prefix}_datetime_minute" id="${prefix}_datetime_minute"$disabletime$copymin>\n           ]
      .( join "\n", map {
        my $selected = ($_ == $dt->minute) ? ' selected="selected"' : "";
        qq[<option value="$_" $selected>$_</option>]
      } map { sprintf "%02d", $_ } 0 .. 59)."</select>";
  }
  if ($optn{layout} eq 'ilb') {
    my $ymd = $skipdate ? ''
      : qq[<div class="ilb">Year: $yearinput</div>
           <div class="ilb">Month: $monthinput</div>
           <div class="ilb">Day: $mdayinput</div>];
    my $tim = $skiptime ? ''
      : qq[<div class="ilb">Time: <span class="nobr">$hourinput : $mininput</span></div>];
    return qq[<div class="ilb">$ymd
                 $tim</div>];
  } elsif ($optn{layout} eq 'compactilb') {
    my $ymd = $skipdate ? ''
      : qq[<div class="ilb">$yearinput</div>
           <div class="ilb">$monthinput</div>
           <div class="ilb">$mdayinput</div>];
    my $tim = $skiptime ? ''
      : qq[<div class="ilb"><span class="nobr">${hourinput}:$mininput</span></div>];
    return qq[<div class="ilb">$ymd
                 $tim</div>];
  } else {
    # Default to table-based layout, for backward compatibility with
    # older versions.  (Some code that calls us assumes that's what
    # it's gonna get.)
    my $ymd = $skipdate ? ''
      : qq[<tr><td>Year:</td><td>$yearinput</td></tr>
         <tr><td>Month:</td><td>$monthinput</td></tr>
         <tr><td>Day:</td><td>$mdayinput</td></tr>];
    my $tim = $skiptime ? ''
      : qq[<tr><td>Time:</td><td><span class="nobr">$hourinput : $mininput</span></td></tr>];
    return qq[<div class="datetimeformfields">
     <table><tbody><!-- DateTime::Form::Fields $dbgmsg -->
         $ymd
         $tim
     </tbody></table></div>];
  }

}


42;
