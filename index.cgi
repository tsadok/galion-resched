#!/usr/bin/perl -T
# -*- cperl -*-

our $debug = 0;
$maxrows = 150; # safety precaution
our $didyoumean_enabled = 1;

$ENV{PATH}='';
$ENV{ENV}='';

use strict;
use Carp;
use DateTime;
use DateTime::Span;
use HTML::Entities qw(); sub encode_entities{ my $x = HTML::Entities::encode_entities(shift @_);
                                              $x =~ s/[-][-]/&mdash;/g;
                                              return $x; }
use Math::SigFigs;
use Data::Dumper;
use File::Spec::Functions;

require "./forminput.pl";
require "./include.pl";
require "./auth.pl";
require "./db.pl";
require "./datetime-extensions.pl";
require "./prefs.pl";

our %input = %{getforminput() || +{}};

our @dt; # I suspect some bugs may be lurking here.
our $debugtext;
our $persistentvars = persist();
our $hiddenpersist  = persist('hidden');
my $datevars = join "&amp;", grep { $_ } map { $input{$_} ? "$_=$input{$_}" : '' } qw (year month mday magicdate startyear startmonth startmday endyear endmonth endmday);

sub usersidebar; # Defined below.

my $ab = authbox(sub { my $x = getrecord('users', shift); "<!-- Hello, $$x{nickname} -->"; });
my @warn; # scoped this way because sub nextrecur pushes warnings onto it in certain cases.
my $uniqueid = 101;
my $didyoumean_invoked;
my ($messagetouser, $redirectheader) = ('', '');
my %user;

if ($auth::user) {
  # ****************************************************************************************************************
  # User is authorized as staff.
  %user = %{getrecord('users',$auth::user)}; # Some things below want to know which staff.
  $input{usestyle} ||= getpref("usestyle", $auth::user);
  $input{useajax}  ||= getpref("useajax", $auth::user);
  #warn "usestyle=$input{usestyle}; useajax=$input{useajax}";
  if ($input{extend}) {
    ($messagetouser, $redirectheader) = extendbooking();
    # Note: extendbooking() kludges %input:
    #  * It fills in $input{view} based on the resource's showwith field.
    #  * As of version 0.6.1 it also fills in date info based on the booking's date.
  }
  if ($input{search}) {
    print include::standardoutput("Search Results:  " . encode_entities($input{search}),
                                  searchresults(), $ab, $input{usestyle});
  } elsif ($input{action} eq 'newaliasfrm') {
    print include::standardoutput("Alias Management", newaliasform(), $ab, $input{usestyle});
  } elsif ($input{action} eq 'createalias') {
    my $arec = +{
                 alias => include::normalisebookedfor($input{alias}),
                 canon => include::normalisebookedfor($input{canon}),
                };
    if (not sanitycheckalias($arec)) {
      die "CAN'T HAPPEN:  The subroutine sanitycheckalias cannot return false, but it did.";
    } else {
      my $result = addrecord('resched_alias', $arec);
      print include::standardoutput("Alias Added:  " . encode_entities($input{alias}),
                                    qq[<div class="info"><p>The alias has been added.</p>
                                                         <p>If you need to add another, you can use the form below.</p></div>]
                                    . newaliasform(),
                                    $ab, $input{usestyle});
    }
  } elsif ($input{action} eq 'updatealias') {
    my ($content, $title) = updatealias();
    $title ||= 'Alias Update';
    print include::standardoutput($title, $content, $ab, $input{usestyle});
  } elsif ($input{alias}) {
    # This is actually the alias search.
    my ($content, $title) = aliassearch();
    print include::standardoutput($title, $content, $ab, $input{usestyle});
  } elsif ($input{action} eq "markcleaned") {
    my ($content, $title) = markcleaned();
    print include::standardoutput($title, $content, $ab, $input{usestyle});
    exit 0;
  } elsif ($input{overview}) {
    # User wants to just see a broad overview for certain resource(s).
    my ($content, $title) = overview();
    print include::standardoutput($title, $content, $ab, $input{usestyle});
    exit 0;
  } elsif ($input{view}) {
    # User wants to see the hour-by-hour schedule for certain resource(s).
    doview();
  } elsif ($input{action} eq 'didyoumean') { # This is short enough to leave inline...
    my %booking = %{getrecord('resched_bookings', $input{booking})};
    $booking{id} or warn 'Taxes and Hot Fish Juice';
    my $bookedforastyped = $booking{bookedfor};
    $booking{bookedfor} = include::capitalise(include::dealias(include::normalisebookedfor($bookedforastyped)));
    my @changes = @{updaterecord('resched_bookings', \%booking)};
    my %res = %{getrecord('resched_resources', $booking{resource})};
    my $when = DateTime::From::MySQL($booking{fromtime});
    print include::standardoutput('Booking Updated: ' . $booking{bookedfor},
                                  qq[<div class="info">The booking has been updated.</div>],
                                  $ab, $input{usestyle}, redirect_header(\%res, $when), );
  } elsif ($input{action} eq 'newbooking') { # User wants to book a resource for a particular time.
    my ($content, $title) = newbooking();
    print include::standardoutput($title, $content, $ab, $input{usestyle});
  } elsif ($input{action} eq 'makebooking') {
    my ($content, $title, $redirect) = makebooking();
    print include::standardoutput($title, $content, $ab, $input{usestyle}, $redirect);
  } elsif ($input{action} eq 'daysclosed') {
    if ($input{year1} and $input{month1} and $input{mday1}) {
      my ($content, $title) = markdaysclosed();
      print include::standardoutput($title, $content, $ab, $input{usestyle});
    } else {
      print include::standardoutput('Mark Resources Unavailable for Closed Dates:',
                                    daysclosedform(), $ab, $input{usestyle}, );
    }
  } elsif ($input{action} eq "showgraph") {
    showgraph();
  } elsif ($input{booking}) {
    # User wants to view details of a specific booking.
    my ($content, $title) = viewbooking();
    print include::standardoutput($title, $content, $ab, $input{usestyle});
  } elsif ($input{doneearly}) {
    # We're marking a booking as finished early.  We may also be creating a new followup booking.
    my %ob = %{getrecord('resched_bookings', $input{doneearly})}; # Original Booking
    my $when = DateTime::From::MySQL($ob{fromtime});
    my $resource = getrecord('resched_resources', $ob{resource});
    if ($input{action} eq 'change') {
      # We have the user input.  Effect the change:
      my @result;
      push @result, "<!-- Input: ".Dumper(\%input)." -->" if $debug;
      my %input = %{DateTime::NormaliseInput(\%input)};
      $ob{doneearly} = DateTime::Format::ForDB($input{donetime_datetime});
      if ($input{followupname}) {
        # Auto-extend if applicable:
        my %res = %{getrecord('resched_resources', $ob{resource})};
        my %sch = %{getrecord('resched_schedules', $res{schedule})};
        if ($res{autoex}) {
          my $mindt  = DateTime::From::MySQL($ob{doneearly})->add( minutes => $sch{durationmins} );
          my $untildt = DateTime::From::MySQL($ob{until});
          my $autodt = $untildt->clone();
          while ($autodt < $mindt) { $autodt = $autodt->add( minutes => $sch{intervalmins}); }
          # But, back it off if there are conflicts...
          my @collision = include::check_for_collision_using_datetimes($res{id}, $when, $autodt);
          if (grep { not $$_{id} eq $ob{id} } @collision) {
            my %fupchain; my %fb = %ob;
            while ($fb{isfollowup}) {
              $fupchain{$fb{id}} = 1;
              $fupchain{$fb{isfollowup}} = 1;
              %fb = %{getrecord('resched_bookings', $fb{isfollowup})};
            }
            while (($autodt > $untildt)
                   and
                   (grep { (not $fupchain{$$_{id}}) and (not $$_{id} eq $ob{id})
                             and (
                                  # and it overlaps:
                                  DateTime::From::MySQL($$_{fromtime}) < $autodt
                                 )
                         } @collision)
                  ) {
              $autodt = $autodt->subtract( minutes => $sch{intervalmins} );
            }}
          # $autodt now has the datetime we want to auto-extend until.
          $ob{until} = DateTime::Format::ForDB($autodt);
          my @autochanges = @{updaterecord('resched_bookings', \%ob)};
          if (@autochanges) {
            push @result, qq[<div class="info">The following changes were made<!-- to record $ob{id} -->:\n<ul>\n]
              . (join "\n", map { qq[<li>Changed $$_[0] to $$_[1] (was $$_[2])<!-- $$_[3] --></li>] } @autochanges)
              . '</ul></div>';
          } else {
            push @result, qq[<p class="info">The timeslot could not be auto-extended.</p>]
          }
        }
        # Add the followup booking (so we can record its id number) if necessary:
        if (not $ob{followedby}) {
          my $bookedfor = include::dealias(include::normalisebookedfor($input{followupname}));
          my $result = addrecord('resched_bookings',
                                 {
                                  bookedby   => $user{id},
                                  resource   => $ob{resource},
                                  bookedfor  => $bookedfor,
                                  fromtime   => $ob{doneearly}, # Followup booking starts when the parent booking finished,
                                  until      => $ob{until},     # and is scheduled until the end of the original timeslot.
                                  isfollowup => $ob{id},        # This keeps it from getting its own table cell.
                                                                # (It will be listed in the same cell with the parent.)
                                  (($input{staffinitials} || $user{initials}) ? (staffinitials => $input{staffinitials} || $user{initials}) : ()),
                                  (((lc $bookedfor) ne (lc $input{followupname}))
                                   ? ( notes => "($input{followupname})")
                                   : ()),
                                 });
          push @result, "<!-- Add Result:  $result -->\n";
          $ob{followedby} = $db::added_record_id;
          push @result, qq[<p class="info"><a href="./?booking=$ob{followedby}&amp;$persistentvars">View Followup Booking</a></p>];
        }
      } # Now, actually change the main booking:
      my @changes = @{updaterecord('resched_bookings', \%ob)};
      if (@changes) {
        unshift @result, qq[<p class="info">The following changes were made:<ul>].
          (join $/, map{"       <li>Changed $$_[0] to $$_[1] (was $$_[2])<!-- result: $$_[3] --></li>"}@changes)
          .qq[</ul></p><p class="info"><a href="./?booking=$ob{id}&amp;$persistentvars">View the updated main booking.</a></p>];
      } else {
        unshift @result, include::errordiv('Error - No Changes', qq[No changes were made!]);
      }
      print include::standardoutput('Resource Scheduling: early finish recorded',
                                    "@result", $ab, $input{usestyle},
                                    redirect_header($resource, $when)
                                   );
    } else {
      # We haven't got the user input yet.  Get it.
      # We start by taking a default value from either the existing
      # doneearly value (if it is extant, which is unlikely) or the
      # until value (more likely).  We let the user change this and
      # optionally create a new booking for the remainder of the slot.
      my $defaultdone = ($ob{donearly}?$ob{doneearly}:$ob{until});
      my %res = %{getrecord('resched_resources', $ob{resource})};
      my $now = DateTime->now(time_zone => $include::localtimezone);
      my $donedt = DateTime::From::MySQL($ob{until});
      print include::standardoutput('Resource Scheduling:  early finish',
                                    (qq[<form action="./" method="POST" name="doneearlyform">
        <input type="hidden" name="doneearly" value="$ob{id}"></input>
        <input type="hidden" name="action"    value="change"></input>
        ].persist('hidden', ['magicdate']).qq[
        <table><tr>
           <td>
             <p>$ob{bookedfor} booked the $res{name}
                <div>from $ob{fromtime} until $ob{until}</div>
                but actually finished at:</p>
             <table><col width="50%"></col><col></col><tr>
                <td>]#.(DateTime::Form::Fields(DateTime::From::MySQL($ob{until}),'donetime',undef,undef,'FieldsP'))
                   .qq[<input type="hidden" name="donetime_datetime_year"  value="].$donedt->year.qq[" />
                       <input type="hidden" name="donetime_datetime_month" value="].$donedt->month.qq[" />
                       <input type="hidden" name="donetime_datetime_day"   value="].$donedt->mday.qq[" />
                     ].(DateTime::Form::Fields($donedt, 'donetime','skipdate',undef,'FieldsQ',
                                               time_list_quarter_hours_first => getvariable('resched', 'time_list_quarter_hours_first'))).qq[
                </td>
                <td><input type="button" value="Right Now" onclick="
                       var f=document.doneearlyform;
                       var d = new Date()
                       var m = d.getMinutes();
                       if (m < 10)
                       {
                            m = '0'.concat(m);
                       }
                       // f.donetime_datetime_year.value   = ].$now->year.";
                       // f.donetime_datetime_month.value  = ".$now->month.";
                       // f.donetime_datetime_day.value    = ".$now->mday.qq[;
                       f.donetime_datetime_hour.value   = d.getHours();
                       f.donetime_datetime_minute.value = m;
                     "></input>
                </td></tr></table><!-- /table gimmel -->
             <div><input type="submit" value="Save Change"></input></div>
             <p><div>Optional:</div>
                <input type="text" name="followupname"></input>
                then booked the remainder of the timeslot.
                <div>staff initials:&nbsp;<input name="staffinitials" type="text" size="3" value="$user{initials}" /></div>
                </p>
           </td></tr></table><!-- /table daleth -->
      </form>]),
                                    $ab, $input{usestyle});
    }
    # ****************************************************************************************************************
  } elsif ($input{action} eq 'switch') {
    my %mainbook   = %{getrecord('resched_bookings',  $input{id})};
    my %mainres    = %{getrecord('resched_resources', $mainbook{resource})};
    my %targetres  = %{getrecord('resched_resources', $input{with})};
    if ($targetres{id}) {
      my @listing;
      my @targetbook = grep {
        $$_{fromtime} eq $mainbook{fromtime}
      } findrecord('resched_bookings', 'resource', $targetres{id});
      # First off, whether we've found any target bookings or not, we
      # definitely want to change the main booking to the target resource.
      $mainbook{resource} = $targetres{id};
      my @changes = @{updaterecord('resched_bookings', \%mainbook)};
      if (@changes) {
        push @listing, qq[<p class="info">The following changes were made<!-- to record $mainbook{id} -->:\n<ul>\n]
          .(join$/,map{"             <li>Changed $$_[0] to $$_[1] (was $$_[2])<!-- $$_[3] --></li>"}@changes)
          ."</ul></p>";
      } else {
        push @listing, include::errordiv('Error - No Changes', qq[No changes were made!]);
      }
      # The main booking has been switched to the target resource.
      if (@targetbook) {
        push @listing, "<!-- target bookings:  " . encode_entities(Dumper(\@targetbook)) . " -->" if $debug;
        for my $tb (@targetbook) {
          $$tb{resource} = $mainres{id};
          my @changes = @{updaterecord('resched_bookings', $tb)};
          if (@changes) {
            push @listing, qq[<p class="info">The following changes were made<!-- to record $$tb{id} -->:\n<ul>\n]
              .(join$/,map{"             <li>Changed $$_[0] to $$_[1] (was $$_[2])<!-- $$_[3] --></li>"}@changes)
              ."</ul></p>";
          } else {
            push @listing, include::errordiv('Error - No Changes', qq[No changes were made!]);
          }
        }
      } else {
        push @listing, qq[<p class="info">The $mainres{name} is now unbooked (available) at $mainbook{fromtime}.</p>];
      }
      print include::standardoutput("Resource Switched",
                                    (join $/, @listing),
                                    $ab, $input{usestyle});
    } else {
      my $sysadmin = getvariable('resched', 'sysadmin_name');
      print include::standardoutput('Error:  Cannot Switch To Resource $input{with}',
                                    include::errordiv('Weird Error',
                                           qq{Blue Tomatoes: This looks like a job for $sysadmin.
                                     <div class="fineprint">You said you wanted to switch Booking
                                     number $input{id} ($mainbook{bookedfor}) from resource
                                     $mainbook{resource} ($mainres{name}) to resource $input{with},
                                     but there is no resource with id number $input{with}.</div>}),
                                    $ab, $input{usestyle});
    }
    # ****************************************************************************************************************
  } elsif ($input{cancel}) {
    # ****************************************************************************************************************
    if ($input{action} eq 'confirm') {
      my @cancellation;
      my $q = (dbconn()->prepare("DELETE FROM resched_bookings WHERE id=?"));
      for my $booking (split /,\s*/, $input{cancel}) {
        my $fb = getrecord('resched_bookings', $booking);
        if ($$fb{followedby}) {
          push @cancellation, "<p>I'm sorry, but I can't delete a booking after the patron has already finished early and been followed by someone else.  It would leave the poor followup booking orphaned.</p>";
        } else {
          my $parent = $$fb{isfollowup};
          my $result = $q->execute($booking);
          push @cancellation, "<p>Deleted: booking #$booking<!-- result: $result --></p>";
          my $pb = getrecord('resched_bookings', $parent);
          if ($$pb{followedby} == $booking) {
            $$pb{followedby} = undef;
            my $changes = updaterecord('resched_bookings', $pb);
            push @cancellation, "<p>Changed booking #$parent to not have a followup.</p><!-- changes: @$changes -->";
          }
        }
      }
      print include::standardoutput('Cancellation Complete',
                                    (join $/, @cancellation),
                                    $ab, $input{usestyle},
                                    #redirect_header(\%res, $when) # Yeah, but we have to get $when from someplace.
                                   );
    } else {
      my @cancellation;
      for my $booking (split /,\s*/, $input{cancel}) {
        my %b = %{getrecord('resched_bookings', $booking)};
        my %r = %{getrecord('resched_resources', $b{resource})};
        my $ftime = include::datewithtwelvehourtime(DateTime::From::MySQL($b{fromtime}));
        my $udt = DateTime::From::MySQL($b{until});
        my $utime = include::twelvehourtime($udt->hour() . ':' . $udt->minute());
        push @cancellation, "<p>$r{name} is booked for $b{bookedfor} from $ftime until $utime.</p>";
      }
      print include::standardoutput('Confirm Cancellation',
                                    ("<p>You are about to <strong>cancel</strong> the following:</p>" .
                                     (join $/, @cancellation) .
                                     qq[<form action="./" method="post">
                                    <input type="hidden" name="action" value="confirm"></input>
                                    <input type="hidden" name="cancel" value="$input{cancel}"></input>
                                    $hiddenpersist
                                    <input type="submit" value="Confirm"></input>
                                    </form>]),
                                    $ab, $input{usestyle});
    }
  } elsif ($input{availstats}) {
    # How many were _available_ (i.e., not booked) at any given time?
    availstats();
  } elsif ($input{stats}) {
    gatherstats();
  } elsif ($input{frequserform}) {
    my $formhtml = frequserform();
    print include::standardoutput('Frequent User Lookup:',
                                  qq[$formhtml],
                                  $ab, $input{usestyle}
                                 );
  } elsif ($input{frequser}) {
    frequsersearch();
  } elsif ($input{test} eq 'n11n') {
    my $raw = $input{rawname};
    my $nrm = include::normalisebookedfor($raw);
    my $isa = include::isalias($nrm) ? "yes" : "no";
    my $dea = include::dealias($nrm);
    my $cap = include::capitalise($dea);
    print include::standardoutput('Testing N11N',
                                  qq[
          <table><tbody>
             <tr><td>Raw Input:</td>  <td>$raw</td></tr>
             <tr><td>Normalised:</td> <td>$nrm</td></tr>
             <tr><td>Isalias:</td>    <td>$isa</td></tr>
             <tr><td>Dealiased:</td>  <td>$dea</td></tr>
             <tr><td>Capitalised:</td><td>$cap</td></tr>
          </tbody></table>
    ], $ab, $input{usestyle});
  } elsif ($input{test}) {
    # User wants to test some stuff...
    print include::standardoutput('Test Page',
                                 qq[<div><strong>Test Facility:</strong></div>
    <table><tbody>
        <tr><td><input type="button" value="Test AJAX Alert Capability" onclick="onemoment('testalerthere'); sendajaxrequest('ajax=testalert');" /></td><td id="testalerthere"><span></span></td></tr>
        <tr><td><input type="button" value="Test AJAX Replace Capability" onclick="onemoment('testreplacehere'); sendajaxrequest('ajax=testreplace&amp;containerid=testreplacehere');" /></td>
            <td id="testreplacehere"><span>This is the original content of this cell.</span>
                <span>It is permitted to contain multiple elements.</span></td></tr>
        <tr><td><a href="./?csstest=1">Stylesheet Test 1</a></td><td>See what admin, error, and info divs look like.</td></tr>
        <tr><td>Normalise &c: <form action="index.cgi" method="post">
               <input type="hidden" name="test" value="n11n" />
               <input type="text" name="rawname" />
               <input type="submit" value="Test" />
               </form></td>
            <td>Test n11n, c12n, isalias, dealias</td>
            </tr>
    </tbody></table>
    ],
                                 $ab, $input{usestyle});
  } elsif ($input{csstest}) {
    print include::standardoutput('Resource Scheduling:  CSS Test',
                                  qq[
    <div class="admin">
       <div><strong>Admin</strong></div>
       This is an admin div.
       <a href="index.cgi?csstest=yes">This is a link.</a>
    </div>
    <div class="error">
       <div><strong>Error</strong></div>
       This is an error div.
       <a href="index.cgi?csstest=yes">This is a link.</a>
    </div>
    <div class="info">
       <div><strong>Info</strong></div>
       This is an info div.
       <a href="index.cgi?csstest=yes">This is a link.</a>
    </div>
   ],
                                  $ab, $input{usestyle});
  } elsif ($input{someoption}) {
    print include::standardoutput('Resource Scheduling:  someoption',
                                  "<p>If this had been an actual option, content would have appeared here.</p>",
                                  $ab, $input{usestyle});
    # ****************************************************************************************************************
  } else {
    # User has not specified any particular thing to do, so we'll show
    # the form that lets them pick.  We'll offer them a list of
    # possible resources and a way to choose a date (or list of dates
    # and ranges of dates).
    my @res = getrecord('resched_resources');
    my @category = include::categories();
    my %rescat =
      map {
        my $cat = $_;
        my ($catname, @catitem) = @$cat;
        map { $_ => $catname } @catitem; # categoryitems($catname, \@catitem); # @$cat;
      } @category;           ;
    my @rescb = map {[$rescat{$$_{id}}, qq[<div><span class="nobr"><input type="checkbox" value="$$_{id}" name="view" />&nbsp;$$_{name}</span></div>]]} sort { $$a{id} <=> $$b{id} } @res;
    %rescat = ();
    for (@rescb) {
      push @{$rescat{$$_[0]}}, $$_[1];
    }
    my $reslist = (join "\n", map {
      qq[<div class="category"><div><strong>$_:</strong></div>]
         . (join "\n", @{$rescat{$_}})
         . "</div>"
       } sort keys %rescat);
    my $now = DateTime->now(time_zone => $include::localtimezone);
    my $resexplan = ($input{mday}) ? '<strong><em>Check one or more resource(s):</em></strong>' : "";
    $input{month} ||= $now->month(); $input{year} ||= $now->year(); $input{mday} ||= $now->mday();
    my $closeddays = join ',', map { $_ . 's' } daysclosed(2);

    print include::standardoutput('Resource Scheduling',
                                  qq[<h2>Welcome to the Resource Scheduling facility.</h2>
<form action="./" method="POST">
] . persist('hidden', ['category']) . qq[
<table style="border-style: ridge; padding: 0.5em;">
  <colgroup span="2"><col width="40%"></col><col width="60%"></col></colgroup>
<thead><tr><th>Resource(s):</th><th>Date(s):</th></tr></thead>
   <tr><td>$resexplan $reslist</td>
       <td><p>Year:  <input type="text" name="year" value="$input{year}"></input></p>
           <p>Month: <select name="month">].(join $/, map {
             # DateTime cannot choke here, because all values are hardcoded (month goes from 1 .. 12)
             my $dt = DateTime->new( year => 1974, month => $_ , day => 15);
             my $selected = (($input{month} == $dt->month())?' selected="selected"':"");
             (qq[<option value="$_"$selected>].($dt->month_name)."</option>")
           } 1 .. 12).qq[</select></p>
           <p>Day(s): <input type="text" name="mday" value="$input{mday}"></input></p>
           <p>(For days, you can give a comma-separated list of
               dates and date ranges.  Dates are taken in order, so
               <q><code>30-31,1-3</code></q> will show the 30<sup>th</sup> and 31<sup>st</sup> of
               the month you specify plus the first three days of the
               next month.  <q><code>1,1,1,1</code></q> will show the first of the month
               for four months.  $closeddays are not shown.)</p>
           </td></tr>
</table>
<p><input type="submit" value="View Schedule"></input></p>
</form>
],
                                  $ab, $input{usestyle});
  }
} else {
  print include::standardoutput('Authentication Needed',
                                "<p>In order to access Resource Scheduling you need to log in.</p>",
                                $ab, $input{usestyle});
}


exit 0; # Subroutines follow.

sub frequsersearch {
  my $formhtml = frequserform();
  my ($start, $end);
  eval {
    $start = DateTime->new(
                           year  => parsenum($input{startyear}),
                           month => parsenum($input{startmonth}),
                           day  => parsenum($input{startmday}),
                          );
    $end = DateTime->new(
                         year  => parsenum($input{endyear}),
                         month => parsenum($input{endmonth}),
                         day   => parsenum($input{endmday}),
                         hour  => 23,
                        );
  };
  if (not ref $start) {
    print include::standardoutput("Date/Time Error",
                                  dterrormsag($input{startyear}, $input{startmonth}, $input{startmday}, undef, undef,
                                              qq[ (for the start date)]));
    exit 0;
  }
  if (not ref $end) {
    print include::standardoutput("Date/Time Error",
                                  dterrormsag($input{endyear}, $input{endmonth}, $input{endmday}, undef, undef,
                                              qq[ (for the end date)]));
    exit 0;
  }
  my @res = split /,/, $input{resource};
  my %rawcount = %{countfield('resched_bookings', 'bookedfor', $start, $end,
                              (@res ? ('resource' => \@res) : ())
                             )};
  my $rawn = scalar (keys %rawcount);
  my (%count, %realkey, @ck); for my $rawkey (keys %rawcount) {
    my $consolikey = include::dealias(include::normalisebookedfor($rawkey));
    push @ck, $consolikey;
    $realkey{$consolikey} = $realkey{$consolikey} ? $realkey{$consolikey} . " / $rawkey" : $rawkey;
    $count{$consolikey} = defined $count{$consolikey}
      ? $count{$consolikey} + $rawcount{$rawkey}
      : $rawcount{$rawkey};
  }
  for my $ck (include::uniq(@ck)) {
    my $CK =
      #join ' ', map { ucfirst lc $_ } split /\s+/, $ck;
      include::capitalise($ck);
    $realkey{$ck} = qq[$CK</td><td> <cite style="font-size: 70%">($realkey{$ck})</cite>]
      unless lc $realkey{$ck} eq lc $CK;
  }
  my (@metacount, $fullcount);
  my $list = join "\n", map {
    $metacount[$count{$_}]++; $fullcount++;
    qq[<tr><td class="numeric">$count{$_}:</td>
             <td><a href="./?search=].uriencode($_).qq[&amp;$persistentvars">$realkey{$_}</a></td></tr>]
           } sort {
             $count{$b} <=> $count{$a}
           } grep {
             $count{$_} >= $input{frequser}
           } keys %count;
  $list ||= qq[<tr><td>none found with frequency >= $input{frequser}</td></tr>];
  my $n = scalar (keys %count);
  print include::standardoutput('Frequent Users',
                                qq[
      <div>Found $n distinct users (under $rawn names)<!-- res: @res -->.  Listing the top $fullcount.</div>
      <table><tbody>$list</tbody></table>
      <div>&nbsp;</div>
      <div>Meta Count: <ul>] . (join "\n", (map {
        qq[<li>$metacount[$_] users booked $_ time(s).</li>]
      } grep {
        $metacount[$_] } 1 .. $#metacount)) . qq[</ul></div>
      <div>&nbsp;</div>
      $formhtml]# . '<pre>Metacount: ' . Dumper(\@metacount) . '</pre>'
                                , $ab, $input{usestyle});
}

sub viewbooking {
  # User wants to view details of a specific booking.
  my @bookinglisting;
  my ($lateerror, $earlyerror) = ("", "");
  push @bookinglisting, "<!-- Global Input Hash:  " . Dumper(\%input) . " -->\n" if $debug;
  for (split /,\s*/, $input{booking}) {
    if (/(\d+)/) {
      my %b = %{getrecord('resched_bookings', $1)};
      $b{id} or warn 'Tribbles and Warm Milk (booking record has no id in viewbooking())';
      #use Data::Dumper; warn Dumper(\%b);
      if ($input{action} eq 'changebooking') {
        # First change the booking and push the change results onto @bookinglisting.
        # The view/change stuff will follow below, being pushed on afterward.
        my %newb = %{DateTime::NormaliseInput( +{ map { s/^booking_//; $_ => $input{"booking_$_"}
                                                      } grep { /^booking_/ and not /late/ and not /doneearly/ } keys %input })};
        $newb{bookedby}=$user{id}; $newb{id} = $b{id};
        $newb{fromtime} = DateTime::Format::ForDB($newb{fromtime_datetime});
        $newb{until}    = DateTime::Format::ForDB($newb{until_datetime});
        my $origuntil = DateTime::From::MySQL($b{until});
        my $newuntil  = $newb{until_datetime};
        $newb{flags}  = join "", map { my $flet = $_;
                                       $input{"flag" . $flet} ? $flet : ""
                                     } qw(C);
        if (($origuntil->mday ne $newuntil->mday)
            and not getvariable('resched', 'allow_extend_past_midnight')) {
          warn "Tried to extend past midnight, not allowed.";
          push @bookinglisting, "" . include::errordiv('Cannot Extend Past Midnight', qq[Extending a booking past midnight into a new day is not supported.  Please see the recurring booking options if what you really want is to book the same resource at the same time on multiple days.]);
        } else {
          if ($input{latestart}) {
            warn "latestart has a value: $input{latestart}" if $debug;
            eval {
              $newb{latestart} = DateTime::Format::ForDB(DateTime->new(
                                                                       year   => $newb{fromtime_datetime}->year,
                                                                       month  => $newb{fromtime_datetime}->month,
                                                                       day    => $newb{fromtime_datetime}->mday,
                                                                       hour   => $input{booking_late_datetime_hour},
                                                                       minute => $input{booking_late_datetime_minute},
                                                                      ));
            };
            $lateerror .= dterrormsg($newb{fromtime_datetime}->year(),
                                     $newb{fromtime_datetime}->month(),
                                     $newb{fromtime_datetime}->mday(),
                                     $input{booking_late_datetime_hour},
                                     $input{booking_late_datetime_minute},
                                     qq[ (for the late start time)]) if $@;
          } elsif ($input{waslatestart}) {
            $newb{latestart} = undef;
          }
          if ($input{doneearlycheckbox}) {
            warn "doneearlycheckbox has a value: $input{doneearlycheckbox}" if $debug;
            eval {
              $newb{doneearly} = DateTime::Format::ForDB(DateTime->new(
                                                                       year   => $newb{until_datetime}->year,
                                                                       month  => $newb{until_datetime}->month,
                                                                       day    => $newb{until_datetime}->mday,
                                                                       hour   => $input{booking_doneearly_datetime_hour},
                                                                       minute => $input{booking_doneearly_datetime_minute},
                                                                      ));
            };
            $earlyerror .= dterrormsg($newb{until_datetime}->year,
                                      $newb{until_datetime}->month,
                                      $newb{until_datetime}->mday,
                                      $input{booking_doneearly_datetime_hour},
                                      $input{booking_doneearly_datetime_minute},
                                      qq[ (for the done early time)]) if $@;
            if ($input{followupname}) {
              my %fb;
              if ($b{followedby}) {
                %fb = %{getrecord('resched_bookings', $b{followedby})};
              } else {
                $fb{resource} = $b{resource};
                $fb{isfollowup} = $b{id};
              }
              $fb{staffinitials} = $input{followupstaffinitials} || $fb{staffinitials} || $input{staffinitials} || $newb{staffinitials} || $user{initials};
              $fb{bookedfor} = include::dealias(include::normalisebookedfor($input{followupname}));
              if ((lc $fb{bookedfor}) ne (lc $input{followupname})) {
                $fb{notes} = ($fb{notes} ? ($fb{notes} . "\n") : '')
                  . encode_entities("($input{followupname})");
              }
              $fb{bookedby} = $user{id};
              $fb{until} = $newb{until}; $fb{fromtime} = $newb{doneearly};
              if ($fb{id}) {
                # Update extant followup:
                my @changes = @{updaterecord('resched_bookings', \%fb)};
                if (@changes) {
                  push @bookinglisting, qq[<div class="info">The following changes were made to the
                       <a href="./?booking=$fb{id}&amp;$persistentvars">followup booking</a>:<ul>
                       ].(join "\n", map {
                         qq[           <li>Changed $$_[0] to $$_[1] (was $$_[2])<!-- result: $$_[3] --></li>]
                       } @changes).qq[</ul></div>];
                } else {
                  # No changes were made to the followup.
                  push @bookinglisting, qq[<p class="info">No changes were made to the
                        <a href="./?booking=$fb{id}&amp;$persistentvars">followup booking</a>.
                        </p>];
                }
              } else {
                # Add it new:
                my $result = addrecord('resched_bookings', \%fb);
                $newb{followedby} = $db::added_record_id;
                push @bookinglisting, qq[<p class="info">Added <a href="./?booking=$newb{followedby}&amp;$persistentvars">followup booking</a><!-- Result: $result -->.</p>];
              }}
            # The changes to the main record will be made below,
            # outside the if clause, because even if doneearly doesn't
            # change, the other changes still must be made.
          }

          for my $k (grep { /_datetime$/ } keys %newb) { delete $newb{$k} if ref $newb{$k}; } # Don't need error messages in log to tell us we can't save these computed fields because there's no such column in the DB.
          my @changes = @{updaterecord('resched_bookings', \%newb)};
          if (@changes) {
            push @bookinglisting, qq[<div class="info">The following changes were made: <ul>] . (join $/, map {"<li>Changed $$_[0]
              to ".encode_entities($$_[1])." (was ".encode_entities($$_[2]).")<!-- ".encode_entities($$_[3])." --></li>"} @changes) . "</ul></div>";
          } elsif ($input{followupname}) {
            push @bookinglisting, qq[<div class="info">No changes were made to the main booking.</div>];
          } else {
            push @bookinglisting, include::errordiv('No Changes', qq[No changes were made!]);#@DateTime::NormaliseInput::Debug";
            push @bookinglisting, "<!-- newb: $/".(join$/,map{"\t$_\t => $b{$_}"} keys %b)." -->" if $debug;
          }
          %b = %{getrecord('resched_bookings', $b{id})}; # Refresh the record, so we have it with the changes made.
        }
      }
      my %r = %{getrecord('resched_resources', $b{resource})};
      my %res = map { $_ => encode_entities($r{$_}) } keys %r;
      # After the change (if there even was a change) we want to
      # show the user a view/edit form:
      my %ben = map { $_ => encode_entities($b{$_}) } keys %b;
      my @alias = include::hasaliases($b{bookedfor});
      my $aliasnote = (include::isalias(include::normalisebookedfor($b{bookedfor})))
        ? qq[ <cite><a href="./?alias=$b{bookedfor}">This name is an alias</a> for <u>] . (include::capitalise(include::dealias(include::normalisebookedfor($b{bookedfor})))) . qq[</u>.</cite>]
        : ((scalar @alias)
           ? qq[ <cite><a href="./?alias=$b{bookedfor}">This name has ] . (scalar @alias) . qq[ aliases.</a></cite>]
           : qq[ <cite><a href="./?action=newaliasfrm&amp;newalias=$b{bookedfor}">Make this name an alias.</a></cite>]
          );
      my ($switchwith, @switchwith) = ('',);
      if (not $b{isfollowup}) {
        @switchwith = map {
          my %sw = %{getrecord('resched_resources',$_)};
          qq[<!-- $_ --><span class="nobr"><a href="./?action=switch&amp;id=$b{id}&amp;with=$sw{id}&amp;$persistentvars">$sw{name}</a></span>]
        } parseswitchwith($res{switchwith}, $res{id});
        if (@switchwith) {
          $switchwith = qq[<div class="switchwith">Switch With:  ] . (join "\n              ", @switchwith) . "</div>";
        }
      }
      my $noteslines = 2 + split /\n/, $ben{notes};  $noteslines = 3 if $noteslines < 3; $noteslines = 10 if $noteslines > 10;
      #warn " latestart: '$b{latestart}'; fromtime: '$b{fromtime}'; ";
      my $latedt = DateTime::From::MySQL( ($b{latestart} ? $b{latestart} : $b{fromtime}), undef, 'A');
      my $waslat = $b{latestart} ? qq[<input type="hidden" name="waslatestart" value="1" >] : "";
      my $fromdt = DateTime::From::MySQL( $b{fromtime}, undef, 'B');
      my $untidt = DateTime::From::MySQL( $b{until}, undef, 'C');
      my $earldt = DateTime::From::MySQL(($b{doneearly} ? $b{doneearly} : $b{until}),undef,'D');
      my %fbyrec; %fbyrec = %{getrecord('resched_bookings', $b{followedby})} if $b{followedby};
      my $ts = ((getvariable('resched', 'show_booking_timestamp')
                 ? qq[ <span class="tsmod">last modified $b{tsmod}</span>]
                 : ''));
      my $startword = ($res{flags} =~ /R/) ? qq[Meeting starts] : qq[Started late];
      my $showstart = $b{latestart} ? "" : qq[ style="visibility: hidden"];
      my $showdone  = $b{doneearly} ? "" : qq[ style="visibility: hidden"];
      my $cleaned = ($res{flags} =~ /C/)
        ? (qq[<div class="bookingflag"><input type="checkbox" id="flagC" name="flagC" ] . (($b{flags} =~ /C/) ? ' checked="checked"' : '') . qq[ />
              <label for="flagC">Cleaned after use</label></div>])
        : "";
      #use Data::Dumper; warn Dumper(\%b);
      push @bookinglisting, qq[<form action="./" method="post">
           <input type="hidden" name="booking" value="$b{id}" />
           <input type="hidden" name="action" value="changebooking" />
           $hiddenpersist
           <table>
              <col></col><col width="190px"></col><col></col>
           <tbody>
              <tr><td>Resource</td>
                  <td colspan="2">$res{name}<input type="hidden" name="booking_resource" value="$b{resource}"></input>
                      $switchwith
                      </td></tr>
              <tr><td>Booked For:</td><td colspan="2"><input type="text" name="booking_bookedfor" value="$ben{bookedfor}" size="30"></input>$aliasnote</td></tr>
              <tr><td>Booked By:</td><td colspan="2">].(($user{id}==$b{bookedby})
                                            ?"$user{nickname}<!-- $user{id} -->"
                                            :"<del>$b{bookedby}</del> <ins>$user{id} ($user{nickname})</ins>"
                                           ).qq[<input type="hidden" name="booking_bookedby" value="$user{id}"></input>
                                          (initials:&nbsp;<input type="text" size="3" name="staffinitials" value="$b{staffinitials}" />) $ts
                                     </td></tr>
              <tr><td>From<sup><a href="#footnote1">1</a></sup>:</td>
                  <td>].(DateTime::Form::Fields($fromdt, 'booking_fromtime',undef,undef,'FieldsK',
                                                time_list_quarter_hours_first => getvariable('resched', 'time_list_quarter_hours_first'))).qq[</td>
                  <td>$lateerror$waslat<input type="checkbox" name="latestart" id="cblatestart" onchange="cbvistoggle('cblatestart', 'showstart');" ]
                    .($b{latestart} ? ' checked="checked" ' : '').qq[ />&nbsp;<label for="cblatestart">$startword</label> <span$showstart id="showstart">at
                      ].(DateTime::Form::Fields($latedt, 'booking_late', 'skipdate',undef,'FieldsL',
                                                time_list_quarter_hours_first => getvariable('resched', 'time_list_quarter_hours_first'))).qq[</span></td></tr>
              <tr><td>Until<sup><a href="#footnote2">2</a></sup>:</td>
                  <td>].(DateTime::Form::Fields($untidt, 'booking_until',undef,undef,'FieldsM',
                                                time_list_quarter_hours_first => getvariable('resched', 'time_list_quarter_hours_first'))).qq[</td>
                  <td>$earlyerror<input type="checkbox" id="cbdoneearly" name="doneearlycheckbox" onchange="cbvistoggle('cbdoneearly', 'showdone');" ]
                                                  .($b{doneearly}?' checked="checked" ' : '').qq[ />&nbsp;<label for="cbdoneearly">Done early</label>
                      <span$showdone id="showdone">at
                      ].(DateTime::Form::Fields($earldt,'booking_doneearly', 'skipdate',undef,'FieldsN',
                                                time_list_quarter_hours_first => getvariable('resched', 'time_list_quarter_hours_first'))).qq[
                      Followed by: <input name="followupname" value="$fbyrec{bookedfor}" />
                      <span class="nobr">Initials:<input name="followupstaffinitials" size="4" type="text" value="$fbyrec{staffinitials}" /></span></span>
                      </td></tr>
              <tr><td><input type="submit" value="Save Changes" /></td>
                  <td></td>
                  <td><a class="button" href="./?cancel=$b{id}&amp;$persistentvars">Cancel Booking</a></td></tr>
              <tr><td>Notes:</td><td colspan="2"><textarea cols="50" rows="$noteslines" name="booking_notes">$ben{notes}</textarea></td></tr>
              <tr><td>Flags:</td><td colspan="2">$cleaned</td></tr>
           </tbody></table><!-- /table beth -->
        </form>];
    }
  }
  my $content = ((join "\n", @bookinglisting)
                 .qq[<p class="info"><a name="footnote1"><strong>1</strong>:</a>
                       The <q>From</q> time is the beginning of the timeslot.  If they start partway through the timeslot, use the <q>Started late</q> setting.</p>
                       <p class="info"><a name="footnote2"><strong>2</strong>:</a>
                       The <q>Until</q> time is the time the resource is booked until.  If they finish early, use the <q>Done early</q> setting.</p>]);
  return ($content, "Resource Scheduling:  Booking #$input{booking}");
}

sub markdaysclosed {
  my @dc;
  my $dterrors = "";
  my %ctime = include::closingtimes();
  for my $n (1..10) {
    if ($input{'year'.$n} and $input{'month'.$n} and $input{'mday'.$n}) {
      my ($dt, $wc, $cu);
      eval {
        $dt = DateTime->new(
                            year    => $input{'year'.$n},
                            month   => $input{'month'.$n},
                            day     => $input{'mday'.$n},
                           );
      }; $dterrors .= dterrormsg($input{'year'.$n}, $input{'month'.$n}, $input{'mday'.$n}, undef, undef,
                                 qq[ (for the date)]) if $@;
      my %ot = include::openingtimes();
      my ($hour, $minute) = @{$ot{$dt->dow()} || [ 8, 0]};
      eval {
        $wc = DateTime->new(
                            year    => $dt->year(),
                            month   => $dt->month(),
                            day     => $dt->day(),
                            hour    => $hour,   # This gets overridden below, based on schedule.
                            minute  => $minute, # ditto.
                           );
      }; $dterrors .= dterrormsg($dt->year(), $dt->month(), $dt->day(), $hour, $minute,
                                 qq[ (for the opening time)]) if $@;
      ($hour, $minute) = @{$ctime{$dt->dow()} || [ 18, 0]};
      eval {
        $cu = DateTime->new(
                            year    => $dt->year(),
                            month   => $dt->month(),
                            day     => $dt->day(),
                            hour    => $hour,   # This gets overridden below, based on schedule.
                            minute  => $minute, # ditto.
                           );
      }; $dterrors .= dterrormsg($dt->year(), $dt->month(), $dt->day(), $hour, $minute,
                                 qq[ (for the closing time)]) if $@;
      addrecord('resched_days_closed', +{ whenclosed  => DateTime::Format::ForDB($wc),
                                          closeduntil => DateTime::Format::ForDB($cu),
                                          reason      => encode_entities($input{notes}),
                                          user        => $user{id},
                                        });
      push @dc, $wc;
    }}
  my @resource = getrecord('resched_resources');
  my @result = map { my $dt = $_;
                     map {
                       my %s = %{getrecord('resched_schedules', $$_{schedule})};
                       my $when = DateTime::From::MySQL($s{firsttime});
                       my $dow = $dt->dow();
                       $input{untilhour} = $ctime{$dt->dow()}[0] || 20;
                       $input{untilmin}  = (defined $ctime{$dow}[1] ? $ctime{$dow}[1] : 30);
                       attemptbooking($_, \%s, $dt->clone()->set( hour => $when->hour, minute=> $when->minute ) );
                     } @resource;
                   } @dc;
  my $content = join "\n", @result;
  return ($dterrors . $content, 'Marking Closed Dates');
}

sub makebooking {
  my %res = %{getrecord('resched_resources', $input{resource})};
  my %sch = %{getrecord('resched_schedules', $res{schedule})};
  my @restobook = (\%res);
  my ($errors) = "";
  if ($res{combine}) {
    for my $r (map { getrecord('resched_resources', $_) } split /,\s*/, $res{combine}) {
      push @restobook, $r if $input{"combiner$$r{id}"};
    }}
  my $when = DateTime::From::MySQL($input{when});
  my @when = ($when);
  if ($input{recur} eq 'listed') {
    for my $n (grep { $input{'recurlistmday'.$_} and $input{'recurlistyear'.$_} and $input{'recurlistmonth'.$_}
                    } map { /recurlistmday(\d+)/; $1 } grep { /^recurlistmday/ } keys %input) {
      eval {
        push @when, DateTime->new(
                                  year   => $input{'recurlistyear'.$n},
                                  month  => $input{'recurlistmonth'.$n},
                                  day    => $input{'recurlistmday'.$n},
                                  hour   => $when->hour,
                                  minute => $when->minute,
                                 );
      }; $errors .= dterrormsg($input{'recurlistyear'.$n}, $input{'recurlistmonth'.$n}, $input{'recurlistmday'.$n},
                               $when->hour, $when->minute, qq[ (for the booking time)]) if $@;
    }
  } elsif ($input{recur}) {
    my $udt;
    if ($input{recurstyle} eq 'until') {
      eval {
        $udt = DateTime->new(year  => $input{recuruntilyear},  month  => $input{recuruntilmonth},
                             day   => $input{recuruntilmday},
                             hour  => $when->hour,             minute => $when->minute);
      }; $errors .= dterrormsg($input{recuruntilyear}, $input{recuruntilmonth}, $input{recuruntilmday},
                               $when->hour, $when->minute, qq[ (for the <q>until</q> time)]) if $@;
    }
    my $next = nextrecur($when)->clone();
    # TODO:  Study the logic of this while loop:
    while (($input{recurstyle} eq 'ntimes') and (@when < $input{recurtimes})
           or
           (($input{recurstyle} eq 'until')  and (DateTime->compare($next, $udt) <= 0))) {
      push @when, $next->clone();
      $next = nextrecur($next)->clone();
    }
  }
  if (isroom($res{id})) {
    # It's a room we're booking.  First, make sure there are notes if required...
    if ($res{requirenotes} and not $input{notes}) {
      return ('Please go back and fill in contact information for the group contact person in the notes field.  Thanks.',
              'Contact Information Missing', undef);
    }
    # Plus there'll be all those extra form fields, which have to be added to the notes:
    $input{notes} .= "\n==============================\n" . assemble_extranotes(\%res);
  }
  my $redirect_header = redirect_header(\%res, $when); # tentatively
  my @booking_result = map {
    my $w = $_;
    map {
      attemptbooking($_, \%sch, $w)
    } @restobook;
  } @when;
  undef $redirect_header if $didyoumean_invoked;
  if (@booking_result == 1 and $booking_result[0] =~ /class=.error./) {
    undef $redirect_header;
    my $uri = select_redirect(\%res, $when);
    push @booking_result, qq[<div class="info">You may <a href="$uri">go back to the schedule</a> if you like.</div>];
  }
  my $content = ('<div class="results"><strong>Booking Results:</strong><ul>'
                 . (join "\n", map { "<li>" . $_ . "</li>" } @booking_result)
                 . '</ul></div>'
                );
  return ($errors . $content, 'Booking Resource: ' . $res{name}, $redirect_header);
}

sub assemble_extranotes {
  my ($resource) = @_;
  $resource ||= getrecord('resched_resources', $input{resource});
  ref $resource or die "assemble_extranotes(): no resource, no valid resource id.  " . Dumper(\%input);
  my $extranotes = "";
  my ($participants) = $input{participants} =~ /(\d+)/;

  my (@cat, %cat, %catyn);
  for my $e (sort { $$a{sortnum} <=> $$b{sortnum}
                  } map { getrecord('resched_equipment', $$_{equipment})
                        } grep { not $$_{flags} =~ /X/
                               } findrecord('resched_resource_equipment', 'resource', $$resource{id})) {
    my $cat = $$e{category};
    if (not ref($cat{$cat})) {
      push @cat, $cat;
      $cat{$cat} = [];
    }
    if ($$e{flags} =~ /H/) {
      $catyn{$cat} = $e;
    } else {
      push @{$cat{$cat}}, $e;
    }
  }
  my $eqval = sub {
    my ($e) = @_;
    my $label = ($$e{flags} =~ /H/) ? $$e{category} : $$e{label};
    my $indent = ($$e{flags} =~ /H/) ? "" : "   ";
    if ($$e{fieldtype} eq 'radiobool') {
      if (0 + $input{qq[equip$$e{id}]}) {
        return qq[$indent${label}.\n];
      } else { return ''; }
    } elsif ($$e{fieldtype} eq 'checkbox') {
      if ($input{qq[equip$$e{id}]}) {
        return qq[$indent${label}.\n];
      } else { return ''; }
    } elsif ($$e{fieldtype} eq 'text') {
      if ($input{qq[equip$$e{id}]}) {
        if ($$e{flags} =~ /N/) {
          my ($num) = $input{qq[equip$$e{id}]} =~ /(\d+)/;
          $label =~ s/^\s*([#]|No[.]?|Number|Num[.]?)(\s*of)?\s*// if $num;
          return qq[$indent$num ${label}.\n];
        } else {
          return qq[$indent${label}: ] . $input{qq[equip$$e{id}]} . "\n";
        }
      } else { return ''; }
    } else {
      warn "assemble_extranotes(): Unhandled field type: '$$e{fieldtype}' (equip$$e{id})";
      return $indent . "[unhandled: label=" . $input{qq[equip$$e{id}]} . "]\n";
    }
  };
  for my $c (@cat) {
    my $olden = $extranotes;
    if ($catyn{$c}) {
      $extranotes .= $eqval->($catyn{$c});
    } else {
      $extranotes .= $c;
    }
    for my $e (@{$cat{$c}}) {
      $extranotes .= $eqval->($e);
    }
    $extranotes .= "\n" unless $extranotes eq $olden;
  }

  if ($input{participants}) {
    $extranotes .= "$input{participants} Participants.\n";
  }

  if ('yes' eq lc $input{policyhave}) {
    $extranotes .= "Already have a copy of our meeting room policy on file.\n";
  } else {
    if ($input{policysendemail}) {
      use Email::Valid;
      my $toaddress = Email::Valid->address( -address  => $input{policysendemailaddress},
                                             -mxcheck  => 1,
                                             -tldcheck => 1);
      if ($toaddress) {
        # NOTE:  All this actually does is put a record in the database
        #        saying it needs to be sent.  Actual sending is meant to
        #        happen separately on a cron job.  See process-mail-queue.pl
        #        for an example of how that might work.
        my $now = DateTime::Format::ForDB(DateTime->now(time_zone => $include::localtimezone));
        addrecord("resched_mailqueue", +{ mailtype  => 'meetingroompolicy',
                                          toaddress => $toaddress,
                                          enqueued  => $now,
                                          tryafter  => $now, });
        my $eddress = encode_entities($input{policysendemailaddress});
        $extranotes .= qq[Attempted to send meeting room policy by email to $toaddress.\n];
      } else {
        $extranotes .= qq[Unable to send meeting room policy: not a valid email address:  '$input{policysendemailaddress}'\n];
      }
    }
    if ($input{policysendfax}) {
      my $faxnum  = encode_entities($input{policysendfaxnumber});
      $extranotes .= qq[Send meeting room policy by fax to $faxnum.\n];
    }
    if ($input{policysendsnail}) {
      my $snail = encode_entities($input{policysendmailingaddress});
      $extranotes .= qq[Send meeting room policy by U.S. Mail to $snail\n]
    }}
  return $extranotes;
}

sub categorycolor {
  my ($category) = @_;
  my ($catcolors) = getvariable("resched", "statgraphcolors");
  my %cclr = map {
    chomp;
    (split /[:]/, $_);
  } grep {
    $_ and not /^#/
  } split /^/, ($catcolors || "");
  return $cclr{$category};
}

sub rescolor {
  my ($resource) = @_;
  if (not ref $resource) {
    ($resource) = getrecord("resched_resources", $resource);
  }
  my $bgc = (ref $resource) ? ($$resource{bgcolor} || undef) : undef;
  return if not defined $bgc;
  my %bgfn       = ( darkonlight => 'lightbg', lightondark => 'darkbg', 'lowcontrast' => 'lowcontrastbg');
  my $bgcolor    = getrecord("resched_booking_color", $bgc) || +{};
  my $stylesht   = $input{usestyle} || 'lowcontrast';
  return lc $$bgcolor{$bgfn{$stylesht} || 'lowcontrastbg'};
}

sub bookingstyle {
  my ($rescolor) = @_; # This should be the bgcolor from the resched_resources record.
  my %bgfn       = ( darkonlight => 'lightbg', lightondark => 'darkbg', 'lowcontrast' => 'lowcontrastbg');
  my $bgcolor    = $rescolor ? getrecord('resched_booking_color', $rescolor) : undef;
  my $stylesht   = $input{usestyle} || 'lowcontrast';
  return $bgcolor ? qq[ style="background-color: $$bgcolor{$bgfn{$stylesht}};"] : '';
}

sub newbooking {
  # User wants to book a resource for a particular time.
  my %res = %{getrecord('resched_resources', $input{resource})};
  my %sch = %{getrecord('resched_schedules', $res{schedule})};
  my $when = DateTime::From::MySQL($input{when});
  my @when = ($when);
  my $monthoptions = join "\n", map {
    my $dt = DateTime->new( year  => 1970,
                            month => $_, # DateTime will never choke here, because the values are all hardcoded ($_ goes from 1 to 12).
                            day   => 1);
    my $abbr = $dt->month_abbr;
    my $selected = ($_ == $when->month) ? ' selected="selected"' : '';
    qq[<option value="$_"$selected>$abbr</option>];
  } 1..12;

  my $until = $when->clone()->add( minutes => $sch{durationmins} );
  my $untilp;
  if ($sch{durationlock}) {
    $untilp = "Booking from ".(
                               include::twelvehourtime($when->hour() . ':' . sprintf "%02d", $when->minute())
                              )." to ".(include::twelvehourtime($until->hour() . ":" . (sprintf "%02d", $until->minute())))." on ".($when->date());
  } else {
    my $hourselect = '<select name="untilhour">'.(include::houroptions($until->hour(), $until->dow())).'</select>';
    $untilp = "Booking from ".(
                               include::twelvehourtime($when->hour() . ":" . sprintf "%02d", $when->minute())
                              ).qq[ to
          <span class="nobr">$hourselect<strong>:</strong><input type="text" name="untilmin" size="3" value="].($until->minute())
            .qq[" /></span>\n          on ] . $when->date() . ".";
  }

  # Collision Detection:  What if it's already been booked?
  my @collision = include::check_for_collision_using_datetimes($res{id}, $when, $when->clone()->add(minutes => $sch{intervalmins}));
  if (@collision) {
    my %extant = %{$collision[0]};
    my %bookedby = %{getrecord('users', $extant{bookedby})};
    return (include::errordiv('Booking Conflict', qq[$res{name} is already booked for
                                     $extant{bookedfor} (booked by $bookedby{nickname})
                                     from $extant{fromtime} until $extant{until}.
                                     <p><a href="./?booking=$extant{id}&amp;$persistentvars">View
                                        or edit the existing booking.</a></p>]),
            "Booking Conflict: $res{name} already booked for $input{when}");
  } else {
    my $when = DateTime::From::MySQL($input{when});
    # No collision; let the user schedule the resource:
    my $submit = '<div><input type="submit" value="Make it so." /></div>';
    my ($roombookingfields, $notesheading, $submitbeforenotes, $submitafternotes) =
      ( '',                 'Notes',       $submit,            '');
    if (isroom($res{id})) {
      # This is a room booking.
      $notesheading = 'Contact Information (name, address, phone number) for Group Contact Person, and any other Notes'; # TODO: make this configurable
      my (@equip) = sort { ($$a{sortnum}||0) <=> ($$b{sortnum}||0) } map {
        getrecord('resched_equipment', $$_{equipment});
      } grep { not $$_{flags} =~ /X/ } findrecord('resched_resource_equipment', 'resource', $res{id});
      ($submitbeforenotes, $submitafternotes) = ('', $submit);
      my (%value, %ischecked, %isno, @cat, %cat, %catyn);
      for my $e (@equip) {
        if ($$e{fieldtype} eq 'checkbox') {
          $ischecked{$$e{id}} = ($input{qq[equip$$e{id}]}) ? ' checked="checked"' : '';
        } elsif ($$e{fieldtype} eq 'radiobool') {
          $ischecked{$$e{id}} = ($input{qq[equip$$e{id}]}) ? ' checked="checked"' : '';
          $isno{$$e{id}}      = ($input{qq[equip$$e{id}]}) ? '' : ' checked="checked"';
        } elsif ($$e{fieldtype} eq 'text') {
          my $val = encode_entities($input{qq[equip$$e{id}]});
          $value{$$e{id}}     = $val ? qq[ value="$val"] : '';
        }
        my $cat = $$e{category};
        if (not ref $cat{$cat}) {
          push @cat, $cat;
          $cat{$cat} = [];
        }
        if ($$e{flags} =~ /H/) {
          $catyn{$cat} = $e;
        } else {
          push @{$cat{$cat}}, $e;
        }
      }
      my $eqform = sub { my ($e) = @_;
                         my $cat = $$e{category};
                         my $onclick = '';
                         my %clear = ( checkbox  => [qq[document.getElementById('equip], qq[').checked=false;]],
                                       radiobool => [qq[document.getElementById('equip], qq[no').checked=true;]],
                                       text      => [qq[document.getElementById('equip], qq[').value='';]],
                                     );
                         my %set   = ( checkbox  => [qq[document.getElementById('equip], qq[').checked=true;]],
                                       radiobool => [qq[document.getElementById('equip], qq[yes').checked=true;]],
                                       text      => ['',''], # Not Recommended: using text field for the catyn does not make sense; it cannot be autofilled.
                                     );
                         if ($$e{flags} =~ /H/) {
                           $onclick = qq[ onChange="] . (join ' ', map { my $e = $_;
                                                                       $clear{$$e{fieldtype}}[0] . $$e{id} . $clear{$$e{fieldtype}}[1]
                                                                     } @{$cat{$cat}}) . '"';
                         } elsif ($catyn{$cat}) {
                           $onclick = qq( onChange="$set{$catyn{$cat}{fieldtype}}[0]$catyn{$cat}{id}$set{$catyn{$cat}{fieldtype}}[1]");
                         }
                         my $ungroup = ($$e{flags} =~ /G/) ? '' : qq[</div><div>&nbsp;</div>\n<div>                  ];
                         my $comment = $$e{pubcomment} ? (qq[ <span class="equipbookingcomment">] . encode_entities($$e{pubcomment}) . qq[</span>]) : '';
                         if ($$e{fieldtype} eq 'radiobool') {
                           my $isyes = $$e{dfltval} ? ' checked="checked"' : '';
                           my $isno  = $$e{dfltval} ? '' : ' checked="checked"';
                           my $addtoyes = ''; #if ($$e{flags} =~ /H/) { $addtoyes = " (" . encode_entities($$e{label}) . ")" if $$e{label} }
                           my $yesclick = ($$e{flags} =~ /H/) ? '' : $onclick;
                           my $noclick  = ($$e{flags} =~ /H/) ? $onclick : '';
                           return qq[$ungroup<span class="radiobool"><!-- eid: $$e{id} -->\n               ]
                             . qq[<span class="nobr"><input type="radio" name="equip$$e{id}" value="1" id="equip$$e{id}yes"$isyes$yesclick /> <label for="equip$$e{id}yes">Yes$addtoyes</label></span>\n               ]
                             . qq[<span class="nobr"><input type="radio" name="equip$$e{id}" value="0" id="equip$$e{id}no"$isno$noclick />    <label for="equip$$e{id}no">No</label></span>$comment</span>\n];
                         } elsif ($$e{fieldtype} eq 'checkbox') {
                           my $checked = $$e{dfltval} ? ' checked="checked"' : '';
                           my $label   = encode_entities($$e{label});
                           return qq[$ungroup<span class="nobr rightpad"><input type="checkbox" name="equip$$e{id}" id="equip$$e{id}"$checked$onclick /> <label for="equip$$e{id}">$label</label>$comment</span>]
                         } elsif ($$e{fieldtype} eq 'text') {
                           my $label   = encode_entities($$e{label});
                           my $value   = encode_entities($$e{dfltval});
                           my $size    = ($$e{flags} =~ /N/) ? 4 : 20;
                           return qq[$ungroup<label for="equip$$e{id}">$label</label> <input type="text" size="$size" name="equip$$e{id}" id="equip$$e{id}" value="$value"$onclick />$comment]
                         } else {
                           warn "newbooking(): unhandled equipment field type: '$$e{fieldtype}' (equipment #$$e{id}).";
                           return qq[$ungroup<!-- unhandled equipment field type: '$$e{fieldtype}' -->$comment];
                         }
      };
      my $equipmentfields = join "\n", map {
        my $c = $_;
        my $catyn = '';
        if (ref $catyn{$c}) {
          $catyn = $eqform->($catyn{$c});
        }
        qq[<div class="category"><div><strong>$c:</strong> $catyn<div><!-- ] . @{$cat{$c}} . qq[ -->&nbsp;</div></div>
             <div>] . (join "\n             ", map { $eqform->($_); } @{$cat{$c}}) . qq[</div>
           </div>]
      } @cat;
      $roombookingfields = qq[
  <div class="roombooking">
      <p>Number of Participants:  <input name="participants" type="text" size="4" $value{participants} /></p>
      $equipmentfields]
          . qq[
      <div class="category"><div><strong>Meeting Room Policy:</strong></div>
           <div><input type="radio" name="policyhave" value="Yes" id="policyhaveyes" />
                      <label for="policyhaveyes">Already have our policy on file.</label></div>
           <div><input type="radio" name="policyhave" value="No" id="policyhavenot" checked="checked" />
                      <label for="policyhavenot">Please send a copy</label>:
                  <div style="margin-left: 2em;">
                      <div><input type="checkbox" name="policysendemail" id="policysendemail" onClick="document.bookingform.policysendeddress.focus();"  />
                           <label for="policysendemail">by email</label>
                           <label for="policysendeddress">to this address</label>
                           <input id="policysendeddress" type="text" name="policysendemailaddress" onFocus="document.bookingform.policyhave[1].checked=true; document.bookingform.policysend[0].checked=true;" /></div>
                      <div><input type="checkbox" name="policysendfax" id="policysendfax" onClick="document.bookingform.policysendfaxnum.focus();" />
                           <label for="policysendfax">by fax</label>
                           <label for="policysendfaxnum">to this number</label>
                           <input id="policysendfaxnum" type="text" name="policysendfaxnumber" onFocus="document.bookingform.policyhave[1].checked=true; document.bookingform.policysend[1].checked=true;" /></div>
                      <div><input type="checkbox" name="policysendsnail" id="policysendsnail" onClick="document.bookingform.policysendusmaddress.focus();" />
                           <label for="policysendsnail">by U.S. Mail</label>
                           <label for="policysendusmaddress">to this address</label>
                           <input id="policysendusmaddress" type="text" name="policysendmailingaddress" onFocus="document.bookingform.policyhave[1].checked=true; document.bookingform.policysend[2].checked=true;" /></div>
                  </div>
                </div>
      </div>
  </div>]
    }
    my $combinerooms = '';
    if ($res{combine}) {
      my @r = map { getrecord('resched_resources', $_) } split /,\s*/, $res{combine};
      my $cr = join "\n        ", map {
        my $r = $_;
        qq[<div class="combiner"><input type="checkbox" id="combiner$$r{id}" name="combiner$$r{id}" />
             <label for="combiner$$r{id}">$$r{name}</label></div>]
      } @r;
      $combinerooms = qq[<div class="p"><div><strong>Combine Rooms:</strong></div>
        $cr
       </div>];
    }
    my $styleatt = bookingstyle($res{bgcolor});
    my $inits = encode_entities($input{staffinitials} || $user{initials} || "");
    my $startword = ($res{flags} =~ /R/) ? qq[Meeting starts] : qq[Started late];
    return (qq[
       <form action="./" method="POST" name="bookingform" class="res$res{id}">
       <div class="res$res{id}"$styleatt>
       <!-- *** First, the stuff we already know: *** -->
       <input type="hidden" name="action"    value="makebooking" />
       <input type="hidden" name="when"      value="$input{when}" />
       <input type="hidden" name="resource"  value="$input{resource}" />
       $hiddenpersist
       <p>Enter the name of the person or group who will be using the $res{name}:
            <input type="text" name="bookedfor" size="50"></input></p>
       <p>$untilp
          <!-- We pick up bookedby from your login, which is $auth::user.  Log out and log in as a different user to change this. -->
          initials:&nbsp;<input type="text" name="staffinitials" value="$inits" size="3" maxsize="20" /><!-- user $user{id} -->
          </p>
       $roombookingfields
       $submitbeforenotes
       <p><input type="checkbox" name="latestart" /> $startword at
          <input type="text" size="3" name="latehour" />:<input type="text" size="3" name="lateminute"  />
          <input type="button" value="Starting Late Right Now" onclick="
              var f=document.bookingform;
              var d = new Date();
              var m = d.getMinutes();
              if (m < 10) {
                 m = '0'.concat(m);
              }
              f.latehour.value    = d.getHours();
              f.lateminute.value  = m;
              f.latestart.checked = 'checked';
              " />
          </p>
       <p><div>$notesheading:</div><textarea name="notes" cols="50" rows="5"></textarea></p>
       $submitafternotes
       <hr />
       <div class="p"><div><strong>Recurring Booking:</strong></div>
          <div>Book this resource <select name="recur" id="recurformselect" onchange="changerecurform();">
               <option value="">Just This Once</option>
               <option value="daily">Daily</option>
               <option value="weekly">Weekly (every ].$when->day_name.qq[)</option>
               <option value="monthly">Monthly (on the ].ordinalnumber($when->mday).qq[)</option>
               <option value="nthdow">Monthly (on the ].ordinalnumber(nonstandard_week_of_month($when))
                                    ." ".$when->day_name.qq[)</option>
               <option value="quarterly">Quarterly (on the ].ordinalnumber($when->mday)
                                    .qq[ of every third month)</option>
               <option value="quarterlynthdow">Quarterly (on the ].ordinalnumber(nonstandard_week_of_month($when))
                                    ." ".$when->day_name.qq[ of every third month)</option>
               <option value="listed">on the dates listed below</option>
               </select></div>
               <span id="recurstyles" style="display: none;">
                 <div><input type="radio" name="recurstyle" value="ntimes" checked="checked" id="BookTimesRadio" />Book
                      <input type="text"  name="recurtimes" size="4" value="1" onchange="document.getElementById('BookTimesRadio').checked = 'checked';" /> time(s).</div>
                 <div><input type="radio" name="recurstyle" value="until" id="BookThruRadio" />Book through
                      <input type="text" name="recuruntilyear" size="6" value="].$when->year.qq[" onchange="document.getElementById('BookThruRadio').checked = 'checked';" />
                      <select name="recuruntilmonth" onchange="document.getElementById('BookThruRadio').checked = 'checked';">].(join $/, map {
                        my $dt = DateTime->new( year => 1974, month => $_ , day => 7); # DateTime will never choke here because all values are hardcoded.
                        my $selected = (($dt->month() == $when->month())?qq[ selected="selected"]:"");
                        (qq[<option value="$_"$selected>].($dt->month_name)."</option>")
                      } 1 .. 12).qq[</select>
                      <input type="text" name="recuruntilmday" value="].$when->mday.qq[" size="4" onchange="document.getElementById('BookThruRadio').checked = 'checked';" />.</div>
               </span>
               <span id="recurlist" style="display: none;">
                   <table class="table"><thead>
                       <tr><th>year</th><th>month</th><th>day</th></tr>
                   </thead><tbody>
                       <tr><td>].$when->year."</td><td>".$when->month_abbr."</td><td>".$when->mday.qq[</td></tr>
                       <tr><td><input type="text" name="recurlistyear1" size="5" value="].$when->year.qq[" /></td>
                           <td><select id="recurlistmonth1" name="recurlistmonth1">$monthoptions</select></td>
                           <td><input type="text" name="recurlistmday1" size="3" /></td>
                       </tr>
                       <tr id="insertmorelisteddateshere" />
                   </tbody></table>
                   <input type="button" value="Add Another Date" onclick= "augmentdatelist('].($when->year).qq[');"/>
                   <p />
               </span>
       </div>
       $combinerooms
       $submit
    </div></form>\n],
  "Booking $res{name} for $input{when}");
  }}

sub aliassearch {
  my $alias = include::normalisebookedfor($input{alias});
  my @arec;
  {
    my %a = map { $$_{id} => $_
                } searchrecord('resched_alias', 'alias', $alias),
                searchrecord('resched_alias', 'canon', $alias);
    @arec = map { $a{$_} } sort { $$a <=> $$b } keys %a;
  }
  if (not scalar @arec) {
    return (include::errordiv('Error - Missing Alias', qq[Sorry, but I couldn't find an alias
                                         record for <q>$alias</q>.]),
            "Alias Not Found: $alias");
  } else {
    my $content = join "\n<hr />\n", qq[<div>Names should be entered here in <q>normalized form</q>:
                   <ul>
                       <li>lowercase</li>
                       <li>no punctuation</li>
                       <li>first name first</li>
                       <li>leave out any parenthesized marks (e.g., <q>(IN)</q> for internet policy)</li>
                   </ul>
              </div>], map {
                my $arec = $_;
                my $aliasenc = encode_entities($$arec{alias});
                my $canonenc = encode_entities($$arec{canon});
                my $anum = sprintf "%04d", $$arec{id};
                my $editcontrols = ($input{action} eq 'editalias')
                  ? qq[<input type="submit" value="Save Changes" />
                       <!-- TODO: a class="button">Delete Alias</a -->]
                  : qq[<br /><a class="button" href="./?action=editalias&amp;alias=$aliasenc">Edit</a>];
                my $aliascontent = ($input{action} eq 'editalias')
                  ? qq[<input type="text" size="30" name="alias" value="$aliasenc" />]
                  : $aliasenc;
                my $canoncontent = ($input{action} eq 'editalias')
                  ? qq[<input type="text" size="30" name="canon" value="$canonenc" />]
                  : $canonenc;
                my $ilsname = getvariable('resched', 'ils_name');
        qq[<form action="index.cgi" method="post">
              <input type="hidden" name="aliasid" value="$$arec{id}" />
              <input type="hidden" name="action" value="updatealias" />
              <div><strong>Alias #$anum:</strong></div>
              <table class="table alias"><tbody>
                  <tr><th>Alias:</th><td>$aliascontent</td></tr>
                  <tr><th><div>Canonical Name:</div>
                          (as spelled in $ilsname)</th>
                      <td>$canoncontent</td></tr>
              </tbody></table>
              $editcontrols
           </form>]
      } @arec;
    return ($content, "Alias: $alias");
  }}

sub overview {
  # User wants to just see a broad overview for certain resource(s).
  my @res = split /,\s*/, $input{overview};
  my %res;
  my $errors = "";
  my %alwaysclosed = map { $_ => 1 } daysclosed(0);
  for my $id (@res) { $res{$id} = +{ %{getrecord('resched_resources', $id)} }; }
  my %sch = map { $_ => scalar getrecord('resched_schedules', $_)
		} include::uniq(map { $res{$_}{schedule} } @res);
  my @calendar;
  for (qw(startyear startmonth startmday endyear endmonth endmday)) {
    ($input{$_}) = $input{$_} =~ /(\d+)/;
  }
  $input{endyear}   ||= $input{startyear};
  $input{endmonth}  ||= $input{startmonth};
  $input{startmday} ||= 1;

  my ($begdt, $enddt);
  eval {
    $begdt = DateTime->new(
                           year  => $input{startyear},
                           month => $input{startmonth},
                           day   => ($input{startmday} || 1),
                          );
  };
  $errors .= dterrormsg($input{startyear}, $input{startmonth}, ($input{startmday} || 1), undef, undef,
                        qq[ (for the start date)]) if $@;
  my $ldom;
  eval {
    $ldom = last_mday_of_month(year   => $input{endyear},
                               month  => $input{endmonth});
  }; $errors .= include::errordiv("Date / Time Error", qq[Failed to find the last day of the month (year: $input{endyear}; month: $input{endmonth})]) if $@;
  eval {
    $enddt = DateTime->new(
                           year   => $input{endyear},
                           month  => $input{endmonth},
                           day    => ($input{endmday} || $ldom),
                           #hour   => 23, # i.e., _after_ the dt that starts this day, but before the next day.
                          );
  };
  $errors .= dterrormsg($input{endyear}, $input{endmonth}, ($input{endmday} || $ldom),
                        undef, undef, qq[ (for the end date)]) if $@;
  my $cutoffwarn = "";
  my $cutoffmonths = getvariable('resched', 'privacy_cutoff_old_schedules');
  $cutoffmonths = 12 if not defined $cutoffmonths;
  if ($cutoffmonths > 0) {
    my $cutoff = DateTime->now(time_zone => $include::localtimezone)->clone()->subtract( months => $cutoffmonths );
    if ($begdt < $cutoff) {
      $begdt = $cutoff;
      while ($begdt->mday > 1) {
        $begdt = $begdt->add( days => 1 );
      }
      $cutoffwarn = include::errordiv("Old Schedules Unavailable", "Schedules more than $cutoffmonths months old are unavailable.
                                                                    If this is a problem, ask your ReSched site administrator
                                                                    about the privacy policy configuration.");
      if (($enddt < $cutoff) || ($enddt <= $begdt)) {
        my $ldom;
        eval {
          $ldom = last_mday_of_month(year   => $begdt->year,
                                     month  => $begdt->month);
        }; $errors .= include::errordiv("Date / Time Error", qq[Failed to get last day of month (year=] . $begdt->year() . qq[; month=] . $begdt->month() . qq[)]) if $@;
        eval { $enddt = DateTime->new(
                                      year   => $begdt->year,
                                      month  => $begdt->month,
                                      day    => $ldom,
                                      #hour   => 23, # i.e., _after_ the dt that starts this day, but before the next day.
                                     );
             };
        $errors .= dterrormsg($begdt->year, $begdt->month, $ldom, undef, undef,
                              qq[ (for the end date, which had to be pushed out)]
                             ) if $@;
      }
    }
  }


  my $monthdt = $begdt->clone();
  my $dt = $monthdt->clone();
  my @dowhead = map { qq[<th class="dow">$_</th>] } daysopen(1);

  push @calendar, qq[<!-- begdt: $begdt; enddt: $enddt -->
      <table class="monthcal"><caption>].$dt->month_name.qq[</caption>
        <thead><tr>@dowhead</tr></thead>
        <tbody><tr>];
  if ($dt->wday > 1) { push @calendar, (qq[<td></td>] x ($dt->wday - 1)); }
  while ($dt <= $enddt) {
    if (not $dt->wday % 7) {
      push @calendar, qq[</tr>\n<tr>];
    }
    if ($alwaysclosed{$dt->wday % 7}) {
      # do nothing further; we are closed
    } else {
      my @b = overview_get_day_bookings($dt, @res);
      my ($y, $mon, $mday) = ($dt->year, $dt->month, $dt->mday);
      push @calendar, qq[<td><div class="calmdaynum"><a href="./?view=].(join ",", @res).qq[&amp;mday=$mday&amp;year=$y&amp;month=$mon&amp;$persistentvars">$mday</a></div>].
        ((@b) ? (join "\n", map {
          my $booking = $_;
          my $ftime   = include::twelvehourtimefromdt(DateTime::From::MySQL($$booking{fromtime}));
          my $utime   = include::twelvehourtimefromdt(DateTime::From::MySQL($$booking{until}));
          my $style   = bookingstyle($res{$$booking{resource}}{bgcolor});
          "<div$style>".(@res>1 ? qq[<span class="calresname">$res{$$booking{resource}}{name}:</span>] : '')
            .qq[ <a href="./?booking=$$booking{id}&amp;$persistentvars">$$booking{bookedfor}</a> ($ftime - $utime)</div>]
          } @b) : '<p class="calemptyday">&nbsp;</p>' )
          .qq[</td>];
    }
    # Now, increment the dt and check for month changeover.
    $dt = $dt->add(days => 1);
    if (($dt->month ne $monthdt->month) or $dt > $enddt) {
      if ($dt < $enddt) {
        push @calendar, qq[</tr></tbody></table>
          <p class="calmonthtransition" />
          <table class="monthcal"><caption>].$dt->month_name.qq[</caption>
          <thead><tr>@dowhead</tr></thead>
          <tbody><tr>] . join "", map {'<td></td>'} 1..($dt->dow - 1);
        $monthdt = $dt->clone();
      } else {
        push @calendar, qq[</tr></tbody></table>\n    <p class="calmonthtransition" />];
      }
    }
  }
  my %monabbr = ( 1 => 'Jan', 2 => 'Feb', 3 => 'Mar', 4 => 'Apr', 5 => 'May', 6 => 'Jun', 7 => 'Jul', 8 => 'Aug', 9 => 'Sep', 10 => 'Oct', 11 => 'Nov', 12 => 'Dec');
  my $startmonthoptions = include::optionlist('startmonth', \%monabbr, $begdt->month);
  my $endmonthoptions   = include::optionlist('endmonth', \%monabbr, $enddt->month);
  my $prevdt = $begdt->clone()->subtract( months => 1 );
  my $nextdt = $begdt->clone()->add( months => 1 );
  my $prevwhen = "startyear=" . ($prevdt->year()) . "&amp;startmonth=" . ($prevdt->month());
  my $nextwhen = "startyear=" . ($nextdt->year()) . "&amp;startmonth=" . ($nextdt->month());
  my $pmtext   = getvariable('resched', 'wording_overview_verbose_prev_month_label') || "";
  my $nmtext   = getvariable('resched', 'wording_overview_verbose_next_month_label') || "";
  $pmtext = qq[<div class="prevnextlabel prevlabel">$pmtext</div>] if $pmtext;
  $nmtext = qq[<div class="prevnextlabel nextlabel">$nmtext</div>] if $nmtext;
  push @calendar, qq[
    <form class="nav" action="index.cgi" method="get">
         <div class="prevarrow"><a href="index.cgi?overview=$input{overview}&amp;$prevwhen&amp;$persistentvars">⬅$pmtext</a></div>
         <div class="nextarrow"><a href="index.cgi?overview=$input{overview}&amp;$nextwhen&amp;$persistentvars">➡$nmtext</a></div>
         Get overview
         <input type="hidden" name="overview" value="$input{overview}" />
         ] . persist('hidden') . qq[
         <span class="nobr">starting from $startmonthoptions
               of <input type="text" name="startyear" size="5" value="$input{startyear}" />
               </span>
           and
         <span class="nobr">ending with $endmonthoptions
               of <input type="text" name="endyear" size="5" value="$input{endyear}" />
               </span>
         <input type="submit" value="Go" />
      </form>
    ];
  my $labeltext = join ", ", map { qq[<span class="resourcename">${$res{$_}}{name}</span>] } @res;
  return ($errors . qq[<div class="overviewheader">Overview: $labeltext</div>$cutoffwarn] . (join "\n", @calendar), "Overview");
}

sub daysclosed {
  my ($form) = @_; # $form should be 0 for number, 1 for abbreviation, 2 for full day name.
  my @num = map { $_ % 7 } split /,\s*/, (getvariable('resched', 'daysclosed') || '0');
  return @num if not $form;
  my @answer;
  for my $num (@num) {
    # DateTime will never choke here, because all values are hardcoded.
    my $dt = DateTime->new( year => 1970, month => 1, day => 1 );
    while (($dt->dow() %7) ne ($num %7)) {
      $dt = $dt->add(days => 1);         }
    if ($form > 1) {
      push @answer, $dt->day_name();
    } else {
      push @answer, $dt->day_abbr();
    }}
  return @answer;
}

sub daysopen {
  my ($form) = @_;
  # $form should be 0 for number, 1 for abbreviation, 2 for full day name.
  my %alwaysclosed = map { $_ => 1 } daysclosed(0);
  my $dt = DateTime->new( year => 1978, month => 1, day => 1 ); # This date corresponds to a Sunday.  DateTime will not choke, because the numbers are hardcoded.
  my @dow;
  for (0 .. 6) {
    if (not $alwaysclosed{$dt->dow() % 7}) {
      if ($form > 1) {
        push @dow, $dt->day_name();
      } elsif ($form > 0) {
        push @dow, $dt->day_abbr();
      } else {
        push @dow, $dt->dow();
      }}
    $dt = $dt->add( days => 1 );
  }
  return @dow;
}

sub doview {
  # User wants to see the hour-by-hour schedule for certain resource(s).
  my $now = DateTime->now(time_zone => $include::localtimezone);
  my $errors = "<!-- Errors: -->  ";
  my %alwaysclosed = map { $_ => 1 } daysclosed(0);
  my @category = include::categories();
  my %category = map { my @x = @$_; my $name = shift @x;
                       @x = categoryitems($name, \@category);
                       ($name, \@x) } @category;
  my @res;
  if ($input{category} and $category{$input{category}}) {
    @res = categoryitems($input{category}, \@category);
  } else {
    @res = split /,\s*/, $input{view};
  }

  my (%res, @thead, @tbody);
  for my $id (@res) {
    $res{$id} =
      {
       %{getrecord('resched_resources', $id)},
       # Bookings are filled in below, after we know what dates we want.
      };
  }
  my @s = map {       scalar getrecord('resched_schedules', $_) } include::uniq(map { $res{$_}{schedule} } @res);
  my %s = map { $_ => scalar getrecord('resched_schedules', $_) } include::uniq(map { $res{$_}{schedule} } @res);

  # We want the starttimes as numbers of minutes since midnight.
  my @starttime = include::uniq(map { $$_{firsttime} =~ m/(\d{2})[:](\d{2})[:]\d{2}/; (60*$1)+$2; } @s);
  # (These are used to calculate the gcf and also for the table's start time for the first row.)

  my $gcf = include::schedule_start_offset_gcf(@s);
  # $gcf now is the number of minutes per table row.  We can get the
  # rowspan figure for each cell by dividing the duration it
  # represents by this $gcf figure.  We can also calculate the times
  # to label each row with using this figure and the time from the
  # row above.

  # For the table's start time, we just want the earliest of the
  # starttimes:
  my $t = $starttime[0]; for (@starttime) { $t = $_ if $_ < $t }
  my $tablestarttime=$t;


  # What day(s) are we showing?
  my $year  = ($input{year}  || ((localtime)[5] + 1900));
  my $month = ($input{month} || ((localtime)[4] + 1));
  my $prevday;
  @dt = map {
    my $mday = $_;
    if ($mday <= $prevday) {
      # $mday = 1;
      $month++;
      if ($month > 12) {
        $year++; $month=1;
      }
    } $prevday = $mday;
    my ($dt);
    eval {
      $dt = DateTime->new(year   => $year,
                          month  => $month,
                          day    => $mday,
                          hour   => int($t / 60),
                          minute => $t % 60,
                         );
    }; $errors .= dterrormsg($year, $month, $mday, int($t / 60), ($t % 60),
                             qq[ (for what day(s) we are showing)]) if $@;
    ($alwaysclosed{$dt->dow() % 7})
      ? () # We are always closed that day.
      : $dt;
  } map {
    if (/(\d+)-(\d+)/) {
      $1 .. $2
    } else {
      $_
    }
  } split /,/, ($input{mday}  ||  (localtime)[3]);
  # Each of these DateTime values is a starting time for the top row
  # in a set of columns (one column per resource).

  my $cutoffmonths = getvariable('resched', 'privacy_cutoff_old_schedules');
  $cutoffmonths = 12 if not defined $cutoffmonths;
  my $origdaycount = scalar @dt;
  if ($cutoffmonths > 0) {
    my $cutoff = $now->clone()->subtract( months => $cutoffmonths );
    @dt = grep { $_ gt $cutoff } @dt;
  }
  if (not @dt) {
    if ($origdaycount > 0) {
      print include::standardoutput("Error: Old Schedules Unvailable",
                                    include::errordiv("Old Schedules Unavailable",
                                                      qq[Sorry, but schedules more than $cutoffmonths months old are
                                                           unavailable.  If this is a problem, ask your ReSched site
                                                           administrator about the privacy policy configuration.]));
    } else {
      print include::standardoutput("Error: No Dates Specified",
                                    include::errordiv("No Dates", qq[Did you forget to specify which dates you wanted to see the schedule for?]));
    }
  }

  # Now we can fill in the bookings:
  {
    my $mindt = $dt[0];
    my $maxdt = $dt[-1]->clone()->add(days => 1);
    $debugtext .= "<div>mindt " . $mindt->ymd() . " " . $mindt->hms() . "; maxdt " . $maxdt->ymd() . " " . $maxdt->hms() . "</div>";
    for my $id (@res) {
      $res{$id}{bookings} = [ get_timerange_bookings($id, $mindt, $maxdt) ];
      $debugtext .= "<div>res $id has " . @{$res{$id}{bookings}} . " bookings:</div><table><tbody><tr><td>&nbsp;</td><td>
          " . (join "\n          ", map {
            my $b = $_;
            qq[<div>b$$b{id}</div>]
          } @{$res{$id}{bookings}}) . "
          </td></tr></tbody></table>\n";
    }
  }

  $debugtext .= "<p><div><strong>Viewing Schedules for @res:</strong></div>$/<pre>".encode_entities(Dumper(\%res))."</pre></p>
<p><div><strong>Schedules:</strong></div>$/<pre>".encode_entities(Dumper(\@s))."</pre></p>
<p>$gcf</p>
<p>Starting Times:<pre>".encode_entities(Dumper(@dt))."</pre></p>\n" if $debug;

  my %endingtime = include::closingtimes();

  my @col;
  # For each day we're showing, we want columns for each resource.
  for my $dt (@dt) {
    for my $r (@res) {
      my $end = $endingtime{$dt->wday()};
      my $schedule = $s{$res{$r}->{schedule}};
      $$schedule{firsttime} =~ /(\d{2})[:](\d{2})[:]\d+/;
      my ($beghour, $begmin) = ($1, $2);
      my ($sdt, $edt);
      eval {
        $sdt = DateTime->new( # DateTime for first timeslot at beginning of day.
                             year   => $dt->year(),
                             month  => $dt->month(),
                             day    => $dt->day(),
                             hour   => $beghour,
                             minute => $begmin,
                            );
        $debugtext .= "<div>r$r sdt " . $sdt->hms() . "</div>";
      }; $errors .= dterrormsg($dt->year, $dt->month(), $dt->day(), $beghour, $begmin,
                               qq[ (for the beginning of a timeslot)]) if $@;
      eval {
        $edt = DateTime->new( # DateTime for end of day
                               year   => $dt->year(),
                               month  => $dt->month(),
                               day    => $dt->day(),
                               hour   => $$end[0],
                               minute => $$end[1],
                            );
        $debugtext .= "<div>r$r edt " . $edt->hms() . "</div>";
      }; $errors .= dterrormsg($dt->year, $dt->month(), $dt->day(), $$end[0], $$end[1],
                               qq[ (for the end of a timeslot)]) if $@;
      push @col,
        +{
          res => $res{$r},
          sdt => $sdt,
          end => $edt,
          dbg => "",
          # rsp => (($$schedule{intervalmins}) / $gcf),
         };
    }
  }

  $debugtext .= "<p>\%endingtime: ".(encode_entities(Dumper(\%endingtime)))."</p>\n"
    #. "<p><div><strong>Columns:</strong></div>\n<div><pre>".encode_entities(Dumper(\@col))."</pre></div></p>"
    ;

  push @thead, (qq[<tr><th rowspan="2" class="label">Time Range</th>]
                .(join '',
                  map {
                    my $dt = $_;
                    my $thclass  = ($dt->ymd eq $now->ymd) ? 'todayth' : 'dateth';
                    qq[<th colspan="].(scalar @res). qq[" class="$thclass"><a href="./?view=$input{view}&amp;year=].
                      ($dt->year())."&amp;month=".($dt->month)."&amp;mday=".($dt->mday()).
                      '&amp;' . persist(undef, ['magicdate']) . '">'
                      .($dt->day_name()) . ", " .($dt->ymd())."</a></th>"
                    } @dt
                 )."<!-- dt: @dt --></tr>\n");
  push @thead, ("<tr>".( join '',
                         map {
                           "<!-- res: @res -->".join'', map {
                             my $r = $_;
                             my $s = bookingstyle($res{$r}{bgcolor});
                             qq[<th class="res$res{$r}{id}"$s><a href="./?view=$res{$r}{id}&amp;year=$input{year}&amp;month=$input{month}&amp;mday=$input{mday}&amp;]. persist(undef, ['category']) .qq[">$res{$r}{name}</a></th>]} @res
                           } @dt
                       )."<!-- dt: @dt --></tr>\n");
  my $maxnts; # Each iteration of the loop below calculates an $nts
              # value (number of timeslots); we want the largest one
              # for the next loop.
  for my $c (@col) {
    # We must construct the column.  First we place appointments
    # already booked, then we place the empty timeslots at the
    # correct intervals, then we calculate how many rows each one
    # takes up.
    my @b = grep {
      # We don't want followup bookings.  (Those get picked up later
      # under the booking they follow up.)
      not $$_{isfollowup}
    } grep {
      # Of the bookings (which are already the ones for the entire
      # timerange we're doing), we only want the bookings that are
      # for the correct specific date.  (This is relevant if more
      # than one date is being looked at side-by-side.)
      my $bdt = DateTime::From::MySQL($$_{fromtime});
      my $cdt = $$c{sdt};
      my $result = $bdt cmp $cdt;
      eval {
        $result = (    ($bdt->year()  == $cdt->year())
                       and ($bdt->month() == $cdt->month())
                       and ($bdt->mday()  == $cdt->mday()));
      };
      $result;
    } @{$$c{res}{bookings}};
    $debugtext .= "<div>res $$c{res}{id}, " . @{$$c{res}{bookings}} . " bookings to consider placing</div>";

    for $b (@b) {
      my $fromtime = DateTime::From::MySQL($$b{fromtime});
      # But, what timeslots are we taking up, then?
      my $msm = ((60*$fromtime->hour())+$fromtime->min()); # minutes since midnight.
      my $msb = $msm - $tablestarttime; # minutes since beginning time of table.
      my $ts = $msb / $gcf;
      $ts = 0 if $ts < 0;

      # So, how many timeslots long is this booking?
      my $until    = DateTime::From::MySQL($$b{until});
      my $duration = $until->clone()->subtract_datetime($fromtime);
      # We do not provide a mechanism for appointments spanning
      # days, so we can just take hours and minutes here.
      my $durmins = $duration->minutes + (60*$duration->hours) + (int ($duration->seconds / 60));
      my $durts = int (0.75 + ($durmins / $gcf)); # duration in number of timeslots.
      #use Data::Dumper(); warn Dumper(+{ durmins => $durmins, durts => $durts });
      for my $i (1 .. ($durts-1)) { # timeslot 0 is the one we already marked, for a total of $durts slots.
        #warn "ts $ts and i $i\n";
        if (($ts + $i) >= 0) {
          $$c{tscont}[$ts+$i] = 1;
        } else {
          warn "Mass Hysteria: ts $ts and i $i";
        }
      }

      # We can't make the td element yet, because we don't know the
      # rowspan value yet, but we *can* now calculate the *contents*
      # of the td element:
      my $x = $b; my $inits = ($$x{staffinitials} ? " --$$x{staffinitials}" : '');
      my ($qstringsansmarkcleaned) = ($ENV{QUERY_STRING} =~ /action=markcleaned&(?:amp;)?booking=\d*(.*)/);
      $qstringsansmarkcleaned ||= $ENV{QUERY_STRING};
      $$c{tdcontent}[$ts] = "\n<!-- Actual Booking:  *********************************************************
           fromtime => $$x{fromtime},    until => $$x{until},
           duration => ".encode_entities(Dumper(\$duration)).qq[
           durmins  => $durmins,         durts => $durts,
           --><a href="./?booking=$$x{id}&amp;$persistentvars">].
             (
              include::capitalise(include::dealias(include::normalisebookedfor($$x{bookedfor})))
             ).
             (($$x{latestart}) ? (' (' . include::twelvehourtimefromdt(DateTime::From::MySQL($$x{latestart})) . ')') : '') .
             (($$x{notes})
              ?' <abbr title="'.encode_entities($$x{notes}.$inits).qq["><img width="24" height="24" alt="[Notes]" src="notes.png"></img></abbr>]
              :"")
               ."</a>
              <!-- Booked by $$x{bookedby} for timeslot from $$x{fromtime} to $$x{until} (done: $$x{doneearly}, followed by $$x{followedby}) -->"
               . (($$c{res}{flags} =~ /C/)
                  ? (($$b{flags} =~ /C/)
                     ? qq(<div><abbr title="Cleaned After Use"><img src="clean.png" width="32" height="32" alt="[Clean]" /></abbr></div>)
                     : qq[<div><a href="index.cgi?action=markcleaned&amp;booking=$$b{id}&amp;$qstringsansmarkcleaned"><abbr title="Still Needs Cleaned!"><img src="needs-cleaned.png" width="32" height="32" alt="[Needs Cleaned]" /></abbr></a></div>])
                  : "<!-- Cleanliness not tracked for this resource. -->");
      my $bookingcount = 1;
      my $foundfollowedbyempty;
      while ($$x{followedby} and not $foundfollowedbyempty) {
        my $p = $x;
        $x = getrecord('resched_bookings', $$x{followedby});
        if ($$x{id}) {
          my $notes = ''; if ($$x{notes}) {
            $notes = ' <abbr title="'.encode_entities($$x{notes}).qq["><img width="24" height="24" alt="[Notes]" src="notes.png" /></abbr>];
          }
          my ($fbytime) = ($$x{fromtime} =~ /(\d+[:]\d+)/);
          my $fbytimeth = include::twelvehourtime($fbytime);
          my $isclean   = (($$c{res}{flags} =~ /C/)
                           ? (($$x{flags} =~ /C/)
                              ? qq(<div><abbr title="Cleaned After Use"><img src="clean.png" width="32" height="32" alt="[Clean]" /></abbr></div>)
                              : qq[<div><a href="index.cgi?action=markcleaned&amp;booking=$$x{id}&amp;$qstringsansmarkcleaned"><abbr title="Still Needs Cleaned!"><img src="needs-cleaned.png" width="32" height="32" alt="[Needs Cleaned]" /></abbr></a></div>])
                           : "<!-- Cleanliness not tracked for this resource. -->");
          $$c{tdcontent}[$ts] .= qq[<hr class="doneearly"></hr>\n<!-- Followup Booking: ########################################################
           fromtime => $$x{fromtime},    until => $$x{until},
           --><a href="./?booking=$$x{id}&amp;$persistentvars">].
             (
              include::capitalise(include::dealias(include::normalisebookedfor($$x{bookedfor})))
             ) ." ($fbytimeth)$isclean$notes</a>
              <!-- Booked by $$x{bookedby} for timeslot from $$x{fromtime} to $$x{until} (done: $$x{doneearly}, followed by $$x{followedby}) -->";
          $bookingcount += 1; # I have the hr element styled so that this is enough.
        } else {
          $x = $p; $foundfollowedbyempty = 1;
        }
      }
      # Question: is there room to insert some blank lines before
      # the done early link?  That question gets addressed below,
      # when calculating the rowspan values, but we'll need the
      # bookingcount:
      $$c{bookingcount}[$ts] = $bookingcount;
      $$c{tdcontent}[$ts] .= "<!-- and now the done early link: -->"; my $donetext = "done early?";
      my $extendlink = '';
      my $currend = $until->hms();
      $extendlink = qq[<a href="./?extend=$$x{id}&amp;$persistentvars&amp;currentend=$currend"><img src="/img/arrow-down-blue-v2.png" class="extendarrow" width="36" height="21" /></a>];
      if ($$x{doneearly}) {
        my $doneat = include::twelvehourtimefromdt(DateTime::From::MySQL($$x{doneearly}));
        $donetext = "(available at $doneat)";
        $extendlink = '';
        $$c{tdcontent}[$ts] .= '<hr class="doneearly" />';
      }
      ++$uniqueid;
      my $delink = ($input{useajax} eq 'off')
        ? qq[<a href="./?doneearly=$$x{id}&amp;$persistentvars" class="avail">$donetext</a>]
        : qq[<a class="avail" onclick="onemoment('dnid$uniqueid'); sendajaxrequest('ajax=doneearlyform&amp;containerid=dnid$uniqueid&amp;bookingid=$$x{id}&amp;$persistentvars')">$donetext</a>];
      $$c{tdcontent}[$ts] .= qq[
          <div id="dnid$uniqueid">
             $extendlink
             <div style="text-align: right;" class="doneearly">$delink</div>
          </div>];
      # Since these are actual bookings, not mere scheduled
      # timeslots, we want to extend them downward for their
      # duration, so that regularly scheduled timeslots cannot break
      # in in the middle of them.  However, that's done below, after
      # we place the regularly scheduled thingies, when we calculate
      # the rowspan values.
    }
    # Now, the regularly scheduled empty timeslots (if they're not taken):
    # How many timeslots are there total (on the table, counting between ones)?
    my $esm = (60*$$c{end}->hour() + $$c{end}->min()); # Minutes since midnight at close (end of day).

    my $ssm = (60*$$c{sdt}->hour() + $$c{sdt}->min()); # Minutes since midnight for first timeslot.

    my $nts = int ((($esm - $tablestarttime) / $gcf) + 0.5); # If a timeslot is at least half there, show it.
    $maxnts = $nts if $maxnts < $nts;
    my $sts = int ((($ssm - $tablestarttime) / $gcf));
    # $nts is number of (raw) timeslots.
    # $sts is the first one to match the interval.
    $$c{sch} = $s{$$c{res}{schedule}};
    { # Calculate number of regularly scheduled appointment timeslots (tsl) for the column:
      $$c{tsl} = int ((($esm - $ssm) / $$c{sch}{intervalmins}) + 0.5); # If a timeslot is at least half there, go ahead and prepare rows for it.
    }
    my $tsc; for $tsc (0..($$c{tsl}-1)) {
      my $tsn = $sts + ($tsc * (int ($$c{sch}{intervalmins} / $gcf))); # Timeslot Number
      my $msm = $ssm + ($tsn * $gcf);
      my $when;
      eval {
        $when = DateTime->new(# This is WRONG for columns that start their first timeslot
                              # later than another displayed column, because $ssm is larger
                              # for some columns than for others (as it should be), and we
                              # don't know at this time the correct amount to subtract; this
                              # is FIXED later (where dectime() is called) once we have done
                              # some other calculations (so that we do know what to subtract)
                              # before the results are output to the user.
                              year   => $$c{sdt}->year(),
                              month  => $$c{sdt}->month(),
                              day    => $$c{sdt}->day(),
                              hour   => (int ($msm / 60) % 24),
                              minute => $msm % 60,
                             );
      }; $errors .= include::errordiv($$c{sdt}->year(), $$c{sdt}->month(), $$c{sdt}->day(),
                             (int ($msm / 60) % 24), ($msm % 60),
                             qq[ (for preliminary column start time)]) if $@;
      my $whentext = $when->date() . " " . $when->time();# . "&amp;tsn=$tsn&amp;gcf=$gcf&amp;ssm=$ssm";
      my $resid = $$c{res}{id};
      if (not $$c{tscont}[$tsn]) {
        my ($availstuff);
        if (isroom($resid)
            # or ($$c{sch}{intervalmins} ne $$c{sch}{durationmins}) # This MAY not matter, provided the page will reload anyway when the resource is booked.
            # or (not $$c{sch}{durationlock}) # This MAY not matter too, provided the user can always do things the old way if a different duration is wanted.
            or ($input{useajax} eq 'off')) {
          $availstuff = qq[<!-- *** Regularly Scheduled Interval ***
             --><a href="./?action=newbooking&amp;resource=$resid&amp;when=$whentext&amp;]. persist() . qq[" class="avail">(available)</a>];
        } else {
          ++$uniqueid;
          $availstuff = qq[<span id="unid$uniqueid"><!-- *** Regularly Scheduled Interval ***
             --><a href="./?action=newbooking&amp;resource=$resid&amp;when=$whentext&amp;]. persist() . qq[" class="avail">(available)</a>
                <input type="button" value="Quick!" onclick="onemoment('unid$uniqueid'); sendajaxrequest('ajax=newbookingform&amp;containerid=unid$uniqueid&amp;resource=$resid&amp;when=$whentext&amp;] . persist(undef, ['magicdate']) . qq[');" />
             </span>];
        }
        $$c{tdcontent}[$tsn] ||= $availstuff;
        push @{$$c{contentnote}}, +{
                                    tsc => $tsc,
                                    tsn => $tsn,
                                    con => $$c{tdcontent}[$tsn],
                                    msm => $msm,
                                    whe => $whentext,
                                   };
      }
    }
    # If the very first timeslot at the top of the day isn't taken, put a blank td in it:
    #$$c{tdcontent}[0] ||= "<!-- This Space Intentionally Left Blank -->";
    if (not $$c{tdcontent}[0]) {
      $$c{ssmoffset} += $gcf; # This still needs to be multiplied by
      # the rowspan value, which hasn't been
      # calculated yet.
      $$c{tdcontent}[0] = "<!-- This Space Intentionally Left Blank ($$c{ssmoffset}) -->";
    }
    # Also, mark off the final closing time at the end of the day:
    $$c{tdcontent}[$nts] = "(closing)<!-- nts: $nts -->";
  }
  for my $c (@col) {
    # Calculate the rowspan values:
    my $rsp = 0;
    for my $tsn (reverse 0 .. $maxnts) {
      if ($$c{tdcontent}[$tsn]) {
        $$c{tdrowspan}[$tsn] = ++$rsp;
        # Now, what about inserting some blank lines (if there's room) before the doneearly link?
        my $bl = $rsp - $$c{bookingcount}[$tsn] - 1;
        # Subtracting 1 accounts for the line the done early link takes for itself.
        for (1..$bl) {
          $$c{tdcontent}[$tsn] =~ s(<!-- and now the done early link: -->)(<div class="doneearlyspacer">&nbsp;</div><!-- and now the done early link: -->);
        }
        $rsp = 0;
      } else {
        $rsp++;
      }
    }
  }
  # Great, now create the actual rows...  but how many of them?
  my $lastendtime = (sort { $a <=> $b } map { $$_{end}->min() + (60*$$_{end}->hour()) } @col)[-1];
  my $numofrows = ($lastendtime - $tablestarttime) / $gcf;
  for my $row (0 .. $numofrows) {
    my $rowtime = $tablestarttime + ($gcf * $row);
    my ($label, $beforeopen, $labelclass); {
      my $ampm = "<!-- am -->";
      my $hour = int ($rowtime / 60);
      if ($hour < 9) {
        $beforeopen = 1;
      }
      if ($hour > 12) {
        $ampm = "<!-- pm -->"; $hour -= 12;
      }
      my $min  = sprintf "%02d", ($rowtime % 60);
      $label = "<!-- $rowtime -->$hour:$min$ampm";
      if ($beforeopen) { $label = '<!-- before open -->'; $labelclass = 'beforeopen' }
    }
    $labelclass ||= 'label';
    push @tbody, qq[<tr><!-- row $row --><td class="$labelclass">$label</td>] .
      (join $/, map {
        $$_{tdcontent}[$row]
          ? sub {
            my ($c, $r) = @_;
            my $class = ($$c{tdcontent}[$r] =~ /\(closed\)/) ? qq[ class="closed"] : qq[ class="res$$c{res}{id}"];
            if ($$c{ssmoffset}) {
              $$c{tdcontent}[$r] =~ s!(\d+[:]\d+[:]\d+)!dectime($1,$gcf,$$c{tdrowspan}[0])!eg; }
            my $style = bookingstyle($$c{res}{bgcolor});
            return qq[<td rowspan="$$_{tdrowspan}[$row]"$class$style>$$_{tdcontent}[$row]</td>\n              ];
          }->($_, $row)
            : "<!-- no tdcontent -->"
          } @col)
      . "</tr>\n";
  }
  my $pagetitle = 'View Schedule'; # Sane default.
  if ($input{view} =~ /^(\d+)$/) {
    my %r = %{getrecord('resched_resources', $1)};
    $pagetitle = $r{name};
    # This is a slightly better title, but maybe we can do better.
  }
  my %specialview = map {
    my ($name, @res) = @$_;
    @res = categoryitems($name, \@category);
    my $view = join ',', sort { $a <=> $b } @res;
    ($view => $name)
  } @category;
  my $thisview = join ",", sort { $a <=> $b } split /,\s*/, $input{view};
  if ($input{magicdate} eq 'today') {
    $pagetitle = "Today's ";
    if ($specialview{$thisview}) {
      $pagetitle .= $specialview{$thisview};
    } else {
      $pagetitle .= "Schedule";
    }
  } elsif ($specialview{$thisview}) {
    $pagetitle = $specialview{$thisview} . ' Schedule';
  }
  if ($input{magicdate} eq 'monthataglance') {
    $pagetitle .= ': Month at a Glance';
  }
  my $updateargs   = qq[ajax=updates-p&since=] .
    (DateTime::Format::ForDB($now)) . qq[&resource=$input{view}];
  #warn "Update args: $updateargs\n";
  my $updatesuri = updates_uri([split /,\s*/, $input{view}], $now);
  my $updatescript = qq[<script language="javascript">
       /* Issue a check for updates request periodically. */
       function checkforupdates() {
         sendajaxrequest('$updateargs');
       }
       function retrieveupdates() {
         window.location.href = '$updatesuri';
         window.location.reload();
       }
       window.setInterval(checkforupdates,  120000 );
    </script>];
  my $nownote = qq[<div class="currenttime">The following is current as of ] . (include::datewithtwelvehourtime(DateTime->now( time_zone => $include::localtimezone ))) . qq[</div>];
  print include::standardoutput($pagetitle,
       qq[
       <!-- table start time: $tablestarttime -->
       <!-- table end time:   $lastendtime -->
       <!-- number of rows:   $numofrows -->
       @DateTime::NormaliseInput::Debug
       $errors
       $messagetouser
       $nownote
       <!-- always closed: ] . (join ", ", keys %alwaysclosed) . qq[  -->
       <!-- categories: ] . (join "; ", map { my $cn = $_; "$cn: " . join(",", @{$category{$cn}}) } keys %category) . qq[  -->
       <!-- res:  @res -->
       ] . (join "\n       ", map {
         my $c = $_;
         qq[<!-- col r $$c{res}{id}, sdt $$c{sdt}, ] . (scalar @{$$c{res}{bookings}}) . qq[ bookings: ]
           . (join " | ", map {
             my $b = $_;
             qq[b$$b{id} r$$b{resource} ]
           } @{$$c{res}{bookings}}) . qq[ -->]
       } @col) . qq[
       <table border="1" class="scheduletable">
       <thead>].(join"\n",@thead).qq[</thead>
       <tbody>].(join"\n",@tbody).qq[</tbody>
       </table><!-- /table aleph -->]# . $debugtext
                                , $ab, $input{usestyle},
                                  (($input{extend} ? $redirectheader : '')
                                   . $updatescript),
                                 );
  # ****************************************************************************************************************
  exit 0;
}# end of doview()

sub markcleaned {
  my ($b) = getrecord('resched_bookings', $input{booking});
  if ($$b{id} eq $input{booking}) {
    $$b{flags} =~ s/C//; # Don't duplicate it.
    $$b{flags} .= "C";
    updaterecord("resched_bookings", $b);
    doview();
    exit 0;
  } else {
    return errordiv("Error: Booking Not Found", qq[I was going to mark a booking (number $input{booking}) as cleaned, but I could not find it in the database.]);
  }
}

sub availstats_for_category {
  my ($category, $startstats, $endstats, $categories) = @_;
  my @debugline;
  push @debugline, "category: $category";
  push @debugline, "startstats: $startstats";
  push @debugline, "endstats: $endstats";
  my (@resource, @month, @dow, @time, %monct, %dowct, %timect, %availstat);
  my ($catname, @resid) = @$category;
  my $errors = "";
  @resid = categoryitems($catname, $categories);
  push @resource, $_ for @resid;

  @resource = include::uniq(@resource);
  push @debugline, "resources: @resource";

  my $when;
  eval {
    # I don't _think_ DateTime can choke here, because the date
    # numbers all come from an existing DateTime object (and hour and
    # minute are optional anyhow); but I am being thorough today.
    $when = DateTime->new(
                          year    => $startstats->year(),
                          month   => $startstats->month(),
                          day     => $startstats->day(),
                          hour    => 0,
                          minute  => 0,
                            );
  }; $errors .= dterrormsg($startstats->year(), $startstats->month(), $startstats->day()) if $@;

  while ($when < $endstats) {
    push @month, $when->year . "_" . $when->month_abbr();
    $when = $when->add(months => 1);
  }
  push @debugline, "months: @month";

  my %closedwday = map { $_ => 1 } split /,\s*/, getvariable('resched', 'daysclosed');
  @dow = grep { not $closedwday{$_} } 0 .. 6;
  push @debugline, "dows: @dow";

  my %res = map { my $rid = $_;
		  my @rec = getrecord('resched_resources', $rid);
		  $rid => $rec[0] } @resource;
  use Data::Dumper; push @debugline, "res: " . Dumper(\%res);
  my @schedule  = include::uniq(map { $$_{schedule} } values %res);
  push @debugline, "schedules: @schedule";
  my %sch = map { my $sid = $_;
		  my @rec = getrecord('resched_schedules', $sid);
		  $sid => $rec[0] } @schedule;
  my @starttime = sort { $a <=> $b } include::uniq(map {
    $sch{$_}{firsttime} =~ m/(\d{2})[:](\d{2})[:]\d{2}/; (60*$1)+$2;
  } @schedule);
  push @debugline, "calculated start times: " . join ", ", @starttime;
  my $gcf = include::schedule_start_offset_gcf(map { $sch{$_} } @schedule);
  push @debugline, "gcf: $gcf";
  my %ot = include::openingtimes();
  my %ct = include::closingtimes();

  my $day;
  eval {
    # I don't _think_ DateTime can choke here, because the date
    # numbers all come from an existing DateTime object (and hour and
    # minute are optional anyhow); but I am being thorough today.
    $day = DateTime->new(
                         year    => $startstats->year(),
                         month   => $startstats->month(),
                         day     => $startstats->day(),
                         hour    => 0,
                         minute  => 0,
                        );
  }; $errors .= dterrormsg($startstats->year(), $startstats->month(), $startstats->day()) if $@;
  my ($firstday, $lastday);
  while ($day->ymd() lt $endstats->ymd()) {
    my $nextday = $day->clone()->add( days => 1 );
    $when = $day->clone();
    my $dow = $day->dow() % 7;
    push @debugline, "day: $day (dow: $dow)";
    if (not $closedwday{$dow}) {
      my ($ohour, $omin) = @{$ot{$dow} || [8,  0] };
      my ($chour, $cmin) = @{$ct{$dow} || [18, 0] };
      push @debugline, "  open/close times: o = $ohour:$omin; c = $chour:$cmin";
      while (($when lt $nextday) and ($when->hour < $ohour))  { $when = $when->add( minutes => $gcf ); }
      push @debugline, "  advanced to opening hour: $when";
      while (($when lt $nextday) and ($when->minute < $omin)) { $when = $when->add( minutes => $gcf ); }
      push @debugline, "  advanced to opening minute: $when";
      push @debugline, "  next day at $nextday";
      # TODO: skip days when everything is booked closed.
      while (($when lt $nextday) and (($when->hour < $chour) or ($when->hour == $chour and $when->minute <= $cmin))) {
        my $nextwhen = $when->clone()->add( minutes => $gcf );
        my $time = sprintf "%1d:%02d", $when->hour, $when->minute;
        push @debugline, "    time $time";
        my $month = $day->month();
        $timect{$time}++;
        $dowct{$dow}++;
        $monct{$month}++;
        $firstday ||= $day;
        $lastday    = $day;

        ### # The following produces the correct answer but performs very badly.
        ### my ($avail, $used) = (0,0);
        ### for my $rid (@resource) {
        ###   #my $r = $res{$rid};
        ###   if (include::check_for_collision_using_datetimes($rid, $when, $nextwhen->clone()->subtract ( seconds => 1))) {
        ###     push @debugline, "      res $rid $res{$rid}{name}: used";
        ###     $used++;
        ###   } else {
        ###     push @debugline, "      res $rid $res{$rid}{name}: avail";
        ###     $avail++;
        ###   }
        ### }

        # So for perf reasons, we have farmed out the stat collection to availstats-prep.pl
        my ($used, $avail);
        my ($availrec) = findrecord('resched_availstats',
                                    category       => $catname,
                                    timeframestart => DateTime::Format::ForDB($when),
                                    #timeframeend   => DateTime::Format::ForDB($nextwhen),
                                   );
        if (ref $availrec) {
          $used  = $$availrec{numused};
          $avail = $$availrec{numavailable};
        } else {
          push @debugline, "    Unknown (catname: $catname; start $when)";
          $used = $avail = '[Unknown]';
        }
        push @debugline, "    avail: $avail; used: $used";
        $availstat{overall}{avail}         += $avail;
        $availstat{overall}{used}          += $used;
        $availstat{overall}{cnt}{$avail}++;
        $availstat{overall}{cnt}{total}++;

        $availstat{bytime}{$time}{avail}   += $avail;
        $availstat{bytime}{$time}{used}    += $used;
        $availstat{bytime}{$time}{cnt}{$avail}++;
        $availstat{bytime}{$time}{cnt}{total}++;

        $availstat{bydow}{$dow}{avail}     += $avail;
        $availstat{bydow}{$dow}{used}      += $used;
        $availstat{bydow}{$dow}{cnt}{$avail}++;
        $availstat{bydow}{$dow}{cnt}{total}++;

        my $mon = $day->year . "_" . $day->month_abbr();
        $availstat{bymonth}{$mon}{avail} += $avail;
        $availstat{bymonth}{$mon}{used}  += $used;
        $availstat{bymonth}{$mon}{cnt}{$avail}++;
        $availstat{bymonth}{$mon}{cnt}{total}++;

        $when = $nextwhen;
      }
    }
    $day = $nextday;
  }
  @time = sort { $a cmp $b } keys %timect;
  push @debugline, "----------------------------------------------------------------------------------------------";

  return qq[
  <table class="availstatcriteria"><tbody>
     <tr><th>Category:</th> <td>$catname</td></tr>
     <tr><th>Resources:</th>  <td>]  . (join ", ", map { $res{$_}{name} } @resource) . qq[</td></tr>
     <tr><th>Date Range:</th> <td>] . $firstday->ymd() . " through " . $lastday->ymd() . qq[</td></tr>
     <!-- tr><th>Date Range:</th> <td>] . $startstats->ymd() . " through " . $endstats->ymd() . qq[</td></tr -->
     <tr><th>Statistical Interval:</th> <td>$gcf minutes</td></tr>
  </tbody></table>

  <h2>Overall $catname Availability</h2>
  <table class="availstats"><thead>
      <tr><th>&nbsp;</th><th class="numeric">Average</th>]
				. (join "", map { qq[<th class="numeric">$_ avail.</th>]
						} sort { $a <=> $b } grep { not /total/ } keys %{$availstat{overall}{cnt}}) . qq[</tr>
  </thead><tbody>
      <tr><th>Overall</th><th class="numeric">] .
				($availstat{overall}{cnt}{total}
				 ? (threeplaces($availstat{overall}{avail} / $availstat{overall}{cnt}{total})) : "N/A") . qq [</th>
              ] . (join "", map { my $n = $_;
			      $availstat{overall}{cnt}{total}
				? (sprintf(qq[<td class="numeric"><div>%1d times</div> <div>], $availstat{overall}{cnt}{$n}) .
				   threeplaces($availstat{overall}{cnt}{$n} * 100 / $availstat{overall}{cnt}{total}) .
				   qq[</div></td>])
				: qq[<td class="numeric">[none]</td>] # This datum notwithstanding, the column is numeric.
			    } sort { $a <=> $b } grep { not /total/ } keys %{$availstat{overall}{cnt}}) . qq[</tr>
  </tbody></table>

  <h2>Overall $catname Usage</h2>
  <table class="availstats"><thead>
      <tr><th>&nbsp;</th><th class="numeric">Average</th>]
				. (join "", map { qq[<th class="numeric">$_ avail.</th>]
						} sort { $a <=> $b } grep { not /total/ } keys %{$availstat{overall}{cnt}}) . qq[</tr>
  </thead><tbody>
      <tr><th>Overall</th><td class="numeric">] .
				($availstat{overall}{cnt}{total}
				 ? (threeplaces($availstat{overall}{used} / $availstat{overall}{cnt}{total})) : "N/A") . qq [</td></tr>
  </tbody></table>

  <h2>$catname Availability By Time of Day</h2>
  <table class="availstats"><thead>
      <tr><th>&nbsp;</th><th class="numeric">Average</th>]
				. (join "", map { qq[<th class="numeric">$_ avail.</th>]
						} sort { $a <=> $b } grep { not /total/ } keys %{$availstat{overall}{cnt}}) . qq[</tr>
      ] . (join "\n      ",
	   map { my $t = $_;
		 my $avg = $availstat{bytime}{$t}{cnt}{total}
		   ? threeplaces($availstat{bytime}{$t}{avail} / $availstat{bytime}{$t}{cnt}{total}) : qq[N/A];
		 qq[<tr><th>$t</th><td class="numeric">$avg</td>]
		   . (join "", map { my $n = $_;
				     $availstat{bytime}{$t}{cnt}{total}
				       ? (sprintf(qq[<td class="numeric"><div>%1d times</div>], $availstat{bytime}{$t}{cnt}{$n},)
					  . qq[<div>] . threeplaces($availstat{bytime}{$t}{cnt}{$n} * 100 / $availstat{bytime}{$t}{cnt}{total}) . qq[%</div></td>])
				       : qq[<td class="numeric">[none]</td>] # This datum notwithstanding, the column is numeric.
				     } sort { $a <=> $b } grep { not /total/ } keys %{$availstat{overall}{cnt}}) . qq[</tr>] } @time) . qq[
  </thead><tbody>
  </tbody></table>

  ] . (($startstats->clone->add(days => 1) < $endstats) ? (qq[
  <h2>$catname Availability By Day of Week</h2>
  <table class="availstats"><thead>
      <tr><th>&nbsp;</th><th class="numeric">Average</th>]
				. (join "", map { qq[<th class="numeric">$_ avail.</th>]
						} sort { $a <=> $b } grep { not /total/ } keys %{$availstat{overall}{cnt}}) . qq[</tr>
      ] . (join "\n      ",
	   map { my $dow = $_;
		 my $avg = $availstat{bydow}{$dow}{cnt}{total}
		   ? threeplaces($availstat{bydow}{$dow}{avail} / $availstat{bydow}{$dow}{cnt}{total}) : qq[N/A];
		 qq[<tr><th>$dow</th><td class="numeric">$avg</td>]
		   . (join "", map { my $n = $_;
				     $availstat{bydow}{$dow}{cnt}{total}
				       ? (sprintf(qq[<td class="numeric"><div>%1d times</div>], $availstat{bytime}{$dow}{cnt}{$n},)
					  . qq[<div>] . threeplaces($availstat{bydow}{$dow}{cnt}{$n} * 100 / $availstat{bydow}{$dow}{cnt}{total}) . qq[%</div></td>])
				       : qq[<td class="numeric">[none]</td>] # This datum notwithstanding, the column is numeric.
				     } sort { $a <=> $b } grep { not /total/ } keys %{$availstat{overall}{cnt}}) . qq[</tr>] } @dow) . qq[
  </thead><tbody>
  </tbody></table>]) : '') . qq[

  ] . ((1 < scalar @month) ? (qq[
  <h2>$catname Availability By Month</h2>
  <table class="availstats"><thead>
      <tr><th>&nbsp;</th><th class="numeric">Average</th>]
				. (join "", map { qq[<th class="numeric">$_ avail.</th>]
                                } sort { $a <=> $b } grep { not /total/ } keys %{$availstat{overall}{cnt}}) . qq[</tr>
      ] . (join "\n      ",
           map { my $mon = $_;
                 my $avg = $availstat{bymonth}{$mon}{cnt}{total}
                   ? threeplaces($availstat{bymonth}{$mon}{avail} / $availstat{bymonth}{$mon}{cnt}{total}) : qq[N/A];
                 qq[<tr><th>$mon</th><td class="numeric">$avg</td>]
                   . (join "", map { my $n = $_;
                                     $availstat{bymonth}{$mon}{cnt}{total}
                                       ? (sprintf(qq[<td class="numeric"><div>%1d times</div>], $availstat{bymonth}{$mon}{cnt}{$n},)
                                          . qq[<div>] . threeplaces($availstat{bymonth}{$mon}{cnt}{$n} * 100 / $availstat{bymonth}{$mon}{cnt}{total}) . qq[%</div></td>])
                                       : qq[<td class="numeric">[none]</td>] # This datum notwithstanding, the column is numeric.
                                     } sort { $a <=> $b } grep { not /total/ } keys %{$availstat{overall}{cnt}}) . qq[</tr>] } @month) . qq[
  </thead><tbody>
  </tbody></table>]) : '') . qq[

  <!-- \n] . (join "\n", @debugline) . qq[ -->\n];
}

sub availstats {
  my (@category);
  my $errors = "";
  if (grep { $input{$_} } grep { /^categorycb\w+/ } keys %input) {
    $input{category} = ($input{category} ? qq[$input{category},] : '')
      . join(",", map { /categorycb(.*)/; $1 } grep { $input{$_} } grep { /^categorycb\w+/ } keys %input);
  }
  if ($input{category}) {
    my @allcat = include::categories();
    for my $c (split /,\s*/, $input{category}) {
      push @category, $_ foreach (grep { $$_[0] eq $c } @allcat);
    }
  } else {
    @category = include::categories();
  }

  my ($startstats, $endstats);
  my $now = DateTime->now(time_zone => $include::localtimezone);
  if ($input{availstats} eq 'yesterday') {
    eval {
      $endstats = DateTime->new(#time_zone => $include::localtimezone,
                                year      => $now->year(),
                                month     => $now->month(),
                                day       => $now->mday(),
                               );
      $startstats = $endstats->clone()->subtract( days => 1 );
    }; $errors .= dterrormsg($now->year(), $now->month(), $now->day(), undef, undef,
                             qq[ (for the end of the stats period (yesterday))]) if $@;
  } elsif ($input{availstats} eq 'lastweek') {
    eval {
      $endstats = DateTime->new(#time_zone => $include::localtimezone,
                                year      => $now->year(),
                                month     => $now->month(),
                                day       => $now->mday(),
                               );
      while ($endstats->wday > 1) { $endstats = $endstats->subtract( days => 1 ); }
      $startstats = $endstats->clone()->subtract( days => 7 );
    }; $errors .= dterrormsg($now->year(), $now->month(), $now->day(), undef, undef,
                             qq[ (for the end of the stats period (lastweek))]) if $@;
  } elsif ($input{availstats} eq 'lastmonth') {
    eval {
      $endstats = DateTime->new(#time_zone => $include::localtimezone,
                                year      => $now->year(),
                                month     => $now->month(),
                                day       => 1,
                               );
      $startstats = $endstats->clone()->subtract( months => 1 );
    }; $errors .= dterrormsg($now->year(), $now->month(), 1, undef, undef,
                             qq[ (for the end of the stats period (lastmonth))]) if $@;
  } elsif ($input{availstats} eq 'lastyear') {
    eval {
      $endstats = DateTime->new(
                                year   => $now->year(),
                                month  => 1,
                                day    => 1,
                               );
      $startstats = $endstats->clone()->subtract( years => 1 );
    }; $errors .= dterrormsg($now->year(), 1, 1, undef, undef,
                             qq[ (for the end of the stats period (lastyear))]) if $@;
  } elsif ($input{availstats} eq 'custom') {
    eval {
      $startstats = DateTime->new(
                                  year  => parsenum($input{startyear}),
                                  month => parsenum($input{startmonth}),
                                  day  => parsenum($input{startmday}),
                                 );
    }; $errors .= dterrormsg(parsenum($input{startyear}), parsenum($input{startmonth}), parsenum($input{startmday}), undef, undef,
                             qq[ (for the start of the stats period (custom))]) if $@;
    eval {
      $endstats = DateTime->new(
                                year  => parsenum($input{endyear}),
                                month => parsenum($input{endmonth}),
                                day  => parsenum($input{endmday}),
                               );
    }; $errors .= dterrormsg(parsenum($input{endyear}), parsenum($input{endmonth}), parsenum($input{endmday}), undef, undef,
                             qq[ (for the end of the stats period (custom))]) if $@;
  } elsif ($input{availstats} eq 'overtime') {
    # This is where we start doing multiple date ranges.
    # TODO:  implement this.
  }
  warn "endstats: $endstats\n";

  my $dur = $endstats - $startstats;
  my $hrd = human_readable_duration($dur);
  my $prevstart = $startstats - $dur;
  my $nextend = $endstats + $dur;
  my $prevlink = qq[<a href="./?availstats=custom]
    . "&amp;startyear="  . $prevstart->year()  . "&amp;endyear="  . $startstats->year()
    . "&amp;startmonth=" . $prevstart->month() . "&amp;endmonth=" . $startstats->month()
    . "&amp;startmday="  . $prevstart->mday()  . "&amp;endmday="  . $startstats->mday()
    . '&amp;' . persist(undef, ['magicdate', 'availstats']) . qq[">&lt;= previous $hrd</a>];
  my $nextlink = '<a href="./?availstats=custom'
    . "&amp;startyear="  . $endstats->year()  . "&amp;endyear="  . $nextend->year()
    . "&amp;startmonth=" . $endstats->month() . "&amp;endmonth=" . $nextend->month()
    . "&amp;startmday="  . $endstats->mday()  . "&amp;endmday="  . $nextend->mday()
    . '&amp;' . persist(undef, ['magicdate', 'availstats']) . qq[">next $hrd =&gt;</a>];
  my $persisthidden = persist('hidden', ['magicdate', 'availstats', 'category']);
  my @monthopt = ( [ 1 => 'January'],   [  2 => 'February'], [  3 => 'March'],    [  4 => 'April'],
                   [ 5 => 'May'],       [  6 => 'June'],     [  7 => 'July'],     [  8 => 'August'],
                   [ 9 => 'September'], [ 10 => 'October'],  [ 11 => 'November'], [ 12 => 'December']);

  print include::standardoutput('Availability Statistics', $errors
                                . qq[<h1>Availability Statistics</h1>]
                                . qq[<p>$prevlink | $nextlink</p>]
                                . (join "\n\n", map { availstats_for_category($_, $startstats, $endstats, \@category) } @category)
                                . qq[<div>&nbsp;</div><hr /><div>&nbsp;</div>

  <form class="availstatsform" action"index.cgi" method="get">
      <input type="hidden" name="availstats" value="custom" />
      <table class="formtable"><tbody>
          <tr><th>Categories:</th>
              <td>] . (join "\n                  ", map {
                my ($catname, @res) = @$_;
                @res = categoryitems($catname, \@category);
                my $checked = (grep { $$_[0] eq $catname } @category) ? qq[checked="checked"] : '';
                qq[<input type="checkbox" id="cbcat$catname" name="categorycb$catname" $checked />&nbsp;<label for="cbcat$catname">$catname</label>];
              } include::categories()) . qq[</td></tr>
          <tr><th>Timeframe:</th>
              <td><table class="formtable subtable"><thead>
                      <tr><th></th><th>Year</th><th>Month</th><th>Day</th><td>Time</td></tr>
                  </thead><tbody>
                      <tr><th>Start:</th>
                          <td><input type="text" size="5" name="startyear" value="] . ($startstats->year()) . qq[" /></td>
                          <td>] . include::orderedoptionlist('startmonth', [@monthopt], $startstats->month()) . qq[</td>
                          <td><input type="text" size="5" name="startmday" value="] . ($startstats->mday()) . qq[" /></td>
                          <td> (all day)</td></tr>
                      <tr><th>Stop:</th>
                          <td><input type="text" size="5" name="endyear" value="] . ($endstats->year()) . qq[" /></td>
                          <td>] . include::orderedoptionlist('endmonth', [@monthopt], $endstats->month()) . qq[</td>
                          <td><input type="text" size="5" name="endmday" value="] . ($endstats->mday()) . qq[" /></td>
                          <td> (stop before opening&nbsp;&mdash; exclude this day)</td></tr>
                  </tbody></table></td></tr>
          <tr><th>Use These Settings:</th><td><input type="submit" value="Get Availability Stats" /></td></tr>
      </tbody></table>
  </form>\n],
				$ab, $input{usestyle});
  exit 0;
}

sub threeplaces {
  # Round to three significant digits and sprintf-pad to n.nn
  my ($number) = @_;
  use Math::SigFigs;
  my $result = FormatSigFigs($number,3);
  $result =~ s/[.]$//;
  return $result;
}

sub gatherstats {
  my (@category);
  my $errors = "";
  if ($input{resource}) {
    @category = (['Selected Resource(s)' => split /,\s*/, $input{resource}]);
  } else {
    @category = include::categories((($input{stats} eq "monthbymonth") or ($input{stats} eq "yearbyyear"))
                                    ? 'statgraphcategories' : 'categories');
  }
  if ($input{stats} eq 'monthbymonth') {
    return month_by_month_stats("months", \@category);
  } elsif ($input{stats} eq 'yearbyyear') {
    return month_by_month_stats("years", \@category);
  }
  my ($startstats, $endstats);
  my $now = DateTime->now(time_zone => $include::localtimezone);
  if ($input{stats} eq 'yesterday') {
    $endstats = DateTime->now(time_zone => $include::localtimezone);
    $endstats->set_hour(0); $endstats->set_minute(0); $endstats->set_second(0);
    $startstats = $endstats->clone()->subtract( days => 1 );
  } elsif ($input{stats} eq 'lastweek') {
    $endstats = DateTime->now(time_zone => $include::localtimezone);
    $endstats->set_hour(0); $endstats->set_minute(0);  $endstats->set_second(0);
    while ($endstats->wday > 1) { $endstats = $endstats->subtract( days => 1 ); }
    $startstats = $endstats->clone()->subtract( days => 7 );
  } elsif ($input{stats} eq 'lastmonth') {
    $endstats = DateTime->now(time_zone => $include::localtimezone);
    $endstats->set_hour(0); $endstats->set_minute(0);  $endstats->set_second(0);
    $endstats->set_day(1); # First of the month.
    $startstats = $endstats->clone()->subtract( months => 1 );
  } elsif ($input{stats} eq 'lastyear') {
    eval {
      $endstats = DateTime->new(
                                year => DateTime->now->year(),
                                month => 1,
                                day   => 1,
                               );
      $startstats = $endstats->clone()->subtract( years => 1 );
    }; $errors .= dterrormsg(DateTime->now->year(), 1, 1, undef, undef,
                             qq[ (for the end of the stats period (lastyear))]) if $@;
  } elsif ($input{stats} eq 'custom') {
    eval {
      $startstats = DateTime->new(
                                  year  => parsenum($input{startyear}),
                                  month => parsenum($input{startmonth}),
                                  day  => parsenum($input{startmday}),
                                 );
    }; $errors .= dterrormsg(parsenum($input{startyear}), parsenum($input{startmonth}), parsenum($input{startmday}), undef, undef,
                             qq[ (for the start of the stats period (custom))]) if $@;
    eval {
      $endstats = DateTime->new(
                                year  => parsenum($input{endyear}),
                                month => parsenum($input{endmonth}),
                                day  => parsenum($input{endmday}),
                               );
    }; $errors .= dterrormsg(parsenum($input{endyear}), parsenum($input{endmonth}), parsenum($input{endmday}), undef, undef,
                             qq[ (for the end of the stats period (custom))]) if $@;
  } elsif ($input{stats} eq 'overtime') {
    # This is where we start doing multiple date ranges.
    # TODO:  implement this.
    $errors .= include::errordiv("Not Implemented", qq[I haven't coded up the over-time stats yet, sorry.]);
  }
  my @gatheredstat = getstatsforadaterange(\@category, $startstats, $endstats);
  # Figure the previous/next links and send it all to the user:
  my $dur = $endstats - $startstats;
  my $hrd = human_readable_duration($dur);
  my $prevstart = $startstats - $dur;
  my $nextend = $endstats + $dur;
  my $prevlink = '<a href="./?stats=custom'
    . "&amp;startyear="  . $prevstart->year()  . "&amp;endyear="  . $startstats->year()
    . "&amp;startmonth=" . $prevstart->month() . "&amp;endmonth=" . $startstats->month()
    . "&amp;startmday="  . $prevstart->mday()  . "&amp;endmday="  . $startstats->mday()
    . '&amp;' . persist(undef, ['magicdate']) . qq[">&lt;= previous $hrd</a>];
  my $nextlink = '<a href="./?stats=custom'
    . "&amp;startyear="  . $endstats->year()  . "&amp;endyear="  . $nextend->year()
    . "&amp;startmonth=" . $endstats->month() . "&amp;endmonth=" . $nextend->month()
    . "&amp;startmday="  . $endstats->mday()  . "&amp;endmday="  . $nextend->mday()
    . '&amp;' . persist(undef, ['magicdate']) . qq[">next $hrd =&gt;</a>];
  print include::standardoutput('Usage Statistics', $errors .
                                qq[<div><strong>Gathering Usage Statistics</strong></div>
       <div><strong>Starting at 12:01 am on ] . $startstats->ymd() . qq[</strong></div>
       <div><strong>Ending at 12:01 am on ] . $endstats->ymd() . qq[</strong></div>
       <div>(excluding bookings for ] . (getvariable('resched', 'nonusers')) . qq[)</div>
       @gatheredstat
       <div>&nbsp;</div>
       <div class="nav">
          <div><strong>More Statistics:</strong></div>
          <div>$prevlink | $nextlink</div>
          <hr />
          <form action="index.cgi" method="post">
             Custom Timeframe:
             <input type="hidden" name="stats" value="custom" />
             ] . persist('hidden', ['magicdate']) . qq[
             <table><thead>
                <tr><th></th><th>Year</th><th>Month</th><th>Day</th><th>Time</th></tr>
             </thead><tbody>
                <tr><td>Start:</td>
                    <td><input type="text" size="5" name="startyear" value="$input{startyear}" /></td>
                    <td><input type="text" size="3" name="startmonth" value="$input{startmonth}" /></td>
                    <td><input type="text" size="3" name="startmday" value="$input{startmday}" /></td>
                    <td>12:01 am.</td>
                </tr>
                <tr><td>Stop:</td>
                    <td><input type="text" size="5" name="endyear" value="$input{endyear}" /></td>
                    <td><input type="text" size="3" name="endmonth" value="$input{endmonth}" /></td>
                    <td><input type="text" size="3" name="endmday" value="$input{endmday}" /></td>
                    <td>12:01 am.</td>
                </tr>
             </tbody></table>
             <input type="submit" value="Get Statistics for These Dates" />
          </form>
       </div>],
                                $ab, $input{usestyle});
}

sub getstatsforadaterange {
  my ($categories, $startstats, $endstats) = @_;
  my @category = @$categories;
  my @allcategory = include::categories();
  my (@gatheredstat);
  my %exclude = map { (lc $_) => 1 } map { $_, qq[ $_ ] }
    split /,\s*/, (getvariable('resched', 'nonusers') || 'closed,maintenance,out of order');
  for (@category) {
    my ($category, @resid) = @$_;
    @resid = categoryitems($category, \@allcategory)
      if not scalar @resid;
    my ($totaltotalbookings, $totaldurinhours);
    push @gatheredstat, '<div>&nbsp;</div><table><thead><tr><th colspan="4"><strong>' . "$category</strong></th></tr>\n\n";
    for my $rid (@resid) {
      if ($rid =~ /(\d+)/) {
        my %r = %{getrecord('resched_resources', $rid) || +{}};
        my ($totalbookings, $durinhours) = get_resource_usage_for_a_date_range(\%r, $startstats, $endstats, \%exclude);
        push @gatheredstat, qq[<tr><td>$r{name}:</td>
              <td class="numeric">$totalbookings bookings</td>
              <td> totalling</td><td class="numeric">$durinhours hours.</td></tr>\n];
        $totaltotalbookings += $totalbookings;
        $totaldurinhours    += $durinhours;
      } else {
        warn "getstatsforadaterange: failed to get stats for subcategory, '$rid'";
      }
    }
    push @gatheredstat, qq[<tr><td><strong>Subtotal:</strong></td>
              <td class="numeric">$totaltotalbookings bookings</td>
              <td> totalling</td><td class="numeric">$totaldurinhours hours.</td></tr></table>\n];
  }
  return @gatheredstat;
}

sub get_resource_usage_for_a_date_range {
  my ($r, $dtstart, $dtend, $exclude) = @_;

  my (@gatheredstat);

  croak "get_resource_usage_for_a_date_range(): resource is undef" if not ref $r;
  croak "resource has no id: " . Dumper($r) if not $$r{id};

  my ($stat) = findrecord("resched_usage",
                          resource  => $$r{id},
                          startdate => DateTime::Format::MySQL->format_datetime($dtstart),
                          enddate   => DateTime::Format::MySQL->format_datetime($dtend),
                          exclude   => join(";", sort { $a cmp $b } keys %$exclude),
                         );
  my ($totalbookings, $durinhours);
  if (ref $stat) {
    $totalbookings = $$stat{bookings};
    $durinhours    = $$stat{hours};
  } elsif ($dtstart->clone()->add( months => 1 ) lt $dtend) {
    # Try adding together subranges.
    my @subrange;
    my $prev = $dtstart;
    my $dt = $dtstart->clone()->add( months => 1 );
    while ($dt lt $dtend) {
      push @subrange, [$prev, $dt];
      $prev = $dt;
      $dt = $dt->clone()->add( months => 1);
    }
    push @subrange, [$prev, $dtend];
    ($totalbookings, $durinhours) = (0,0);
    #use Data::Dumper; die Dumper([ map { my ($s, $e) = @$_; $s->ymd() . " to " . $e->ymd() } @subrange ]);
    for my $sr (@subrange) {
      my ($s, $e) = @$sr;
      my ($b, $h) = get_resource_usage_for_a_date_range($r, $s, $e, $exclude);
      $totalbookings += $b;
      $durinhours    += $h;
    }
    addrecord("resched_usage", +{ resource  => $$r{id},
                                  startdate => DateTime::Format::ForDB($dtstart),
                                  enddate   => DateTime::Format::ForDB($dtend),
                                  bookings  => $totalbookings,
                                  hours     => $durinhours,
                                  exclude   => join(";", sort { $a cmp $b } keys %$exclude),
                                });
    # No need to test that the add was successful, as this is a cache we're populating.
    # Worst case scenario is the data have to be gathered/calculated again next time.
  } else {
    my $db = dbconn();
    my $q = $db->prepare('SELECT * FROM resched_bookings '
                         . 'WHERE resource=? AND fromtime>=? AND fromtime<?'
                         . 'AND bookedfor NOT IN (' . (join ',', map { '?' } keys %$exclude) . ')');
    $q->execute($$r{id}, $dtstart, $dtend, (keys %$exclude));
    my $totalduration;
    while (my $b = $q->fetchrow_hashref()) {
      ++$totalbookings;
      use Data::Dumper; push @gatheredstat, '<!-- ' . Dumper($b) . ' -->' if $debug > 1;
      if (not $$b{isfollowup}) {
        my $begin = DateTime::From::MySQL($$b{fromtime});
        #my $end = DateTime::From::MySQL(  ($$b{doneearly}) ? $$b{doneearly} : $$b{until}  );
        my $end = DateTime::From::MySQL(  $$b{until}  );
        my $dur = $end - $begin; # Should yield a DateTime::Duration object.
        $totalduration = (ref $totalduration ? $totalduration + $dur : $dur);
      }
    }
    $durinhours = (ref $totalduration ? $totalduration->in_units('hours') : '0');
    $totalbookings ||= 0;
    if ($dtend->clone()->add(days => 1) lt DateTime->now(time_zone => $include::localtimezone)) {
      addrecord("resched_usage", +{ resource  => $$r{id},
                                    startdate => DateTime::Format::ForDB($dtstart),
                                    enddate   => DateTime::Format::ForDB($dtend),
                                    bookings  => $totalbookings,
                                    hours     => $durinhours,
                                    exclude   => join(";", sort { $a cmp $b } keys %$exclude),
                                  });
      # No need to test that the add was successful, as this is a cache we're populating.
      # Worst case scenario is the data have to be gathered/calculated again next time.
    }
  }
  return ($totalbookings, $durinhours);
}

sub stat_graph_category_helper {
  my ($category, $resources, $interval, $stathash, $resnames, $monthsort, $subcats) = @_;
  $resources = +[ categoryitems($category, include::categories()) ]
    if not scalar @$resources;
  my %exclude = map { (lc $_) => 1 } map { $_, qq[ $_ ] }
    split /,\s*/, (getvariable('resched', 'nonusers') || 'closed,maintenance,out of order');
  for my $rid (@$resources) {
    if ($rid =~ /^\d+$/) {
      my ($res) = getrecord("resched_resources", $rid);
      $$resnames{$rid} = $$res{name};
      my @ru = findrecord("resched_usage", resource => $rid);
      # We only want the ones that represent months.
      my @monthru;
      eval {
        @monthru = grep {
          my $u = $_;
          my $s = DateTime::From::MySQL($$u{startdate});
          my $e = DateTime::From::MySQL($$u{enddate});
          my $month = $s->clone()->add( $interval => 1 );
          (($s->mday == 1) and ($month->ymd() eq $e->ymd()));
        } @ru;
      }; croak qq[DateTime error in stat_graph_category_helper.  Verify whether '$interval' is a valid DateTime component.] if $@;
      for my $usage (@monthru) {
        my $s = DateTime::From::MySQL($$usage{startdate});
        $$monthsort{$s->year() . " " . $s->month_abbr()} = (12 * $s->year()) + $s->month();
        my $monthlabel = $s->year() . " " . $s->month_abbr;
        if ($$usage{exclude} eq join(";", sort { $a cmp $b } keys %exclude)) {
          # If there's more than one, we prefer the one that uses the current exclude list.
          $$stathash{$category}{$rid}{$monthlabel} = $usage;
        } else {
          $$stathash{$category}{$rid}{$monthlabel} ||= $usage;
        }
      }
    } else {
      #warn "       - subcat: $rid\n";
      $$subcats{$rid}{$category}++;
    }}
  # Add up the totals:
  for my $rid (@$resources) {
    for my $month (keys %{$$stathash{$category}{$rid}}) {
      for my $field (qw(bookings hours)) {
        $$stathash{$category}{total}{$month}{$field} += $$stathash{$category}{$rid}{$month}{$field};
        $$stathash{TOTAL}{$month}{$field}            += $$stathash{$category}{$rid}{$month}{$field};
      }}}
}

sub stat_graph_subcategory_helper {
  my ($subcats, $stathash) = @_;
  for my $sc (keys %$subcats) {
    for my $parent (keys %{$$subcats{$sc}}) {
      for my $ml (keys %{$$stathash{$sc}{total}}) {
        for my $field (qw(bookings hours)) {
          $$stathash{$parent}{$sc}{$ml}{$field}    = $$stathash{$sc}{total}{$ml}{$field};
          $$stathash{$parent}{total}{$ml}{$field} += $$stathash{$sc}{total}{$ml}{$field};
        }}}}
}

sub month_by_month_stats {
  my ($interval, $categories) = @_;
  $interval ||= "months";
  my $title = ($interval eq "years") ? 'Year-By-Year Usage Statistics (Scheduled Resources)' : 'Month-By-Month Usage Statistics (Scheduled Resources)';
  my @allcategory = include::categories();
  my ($category, @resid, %stat, %monthsort, %resname, %subcat, @catinfo);
  for (@$categories) {
    ($category, @resid) = @$_;
    stat_graph_category_helper($category, \@resid, $interval, \%stat, \%resname, \%monthsort, \%subcat);
  }
  stat_graph_subcategory_helper(\%subcat, \%stat);
  # Now put together the info into nice tables and graphs for the user:
  for (@$categories) {
    ($category, @resid) = @$_;
    @resid = categoryitems($category, \@allcategory)
      if not scalar @resid;
    push @catinfo, qq[<div class="statcategory">
     <div class="h">$category</div>
     <div class="p">
       <table class="usagestats monthbymonthbookings table"><thead>
         <tr><th><span class="booking">$category Bookings</span></th>
             ] . (join "", map {
           qq[<th>$_</th>]
         } sort {
           $monthsort{$a} <=> $monthsort{$b}
         } keys %{$stat{$category}{total}}) . qq[</tr>
       </thead><tbody>
          ] . join("\n          ", map {
            my $rid = $_;
            my $name = (($rid eq "total") ? qq[$category (total)] : $resname{$rid}) || $rid;
            qq[<tr><th>$name</th>] . (join "", map {
              my $mon = $_;
              qq[<td><span class="booking">$stat{$category}{$rid}{$mon}{bookings}</span></td>]
            } sort {
              $monthsort{$a} <=> $monthsort{$b}
            } keys %{$stat{$category}{total}}) . qq[</tr>]
          } (@resid, "total")) . qq[
       </tbody></table>
       <img alt="[graph: $category Bookings over time]" src="index.cgi?action=showgraph&amp;graph=$input{stats}&amp;field=bookings&amp;category=$category] .
         (($input{resource}) ? qq[&amp;resource=$input{resource}] : ""). qq[" />
     </div>
     <div class="p">
       <table class="usagestats monthbymonthhours table"><thead>
         <tr><th><span class="booking">$category Hours</span></th>
             ] . (join "", map {
           qq[<th>$_</th>]
         } sort {
           $monthsort{$a} <=> $monthsort{$b}
         } keys %{$stat{$category}{total}}) . qq[</tr>
       </thead><tbody>
          ] . join("\n          ", map {
            my $rid = $_;
            my $name = (($rid eq "total") ? qq[$category (total)] : $resname{$rid}) || $rid;
            qq[<tr><th>$name</th>] . (join "", map {
              my $mon = $_;
              qq[<td><span class="hours">$stat{$category}{$rid}{$mon}{hours}</span></td>]
            } sort {
              $monthsort{$a} <=> $monthsort{$b}
            } keys %{$stat{$category}{total}}) . qq[</tr>]
          } (@resid, "total")) . qq[
       </tbody></table>
       <img alt="[graph: $category Hours Booked over time]" src="index.cgi?action=showgraph&amp;graph=$input{stats}&amp;field=hours&amp;category=$category] .
         (($input{resource}) ? qq[&amp;resource=$input{resource}] : ""). qq[" />
     </div>
    </div>];
  }
  # TODO: TOTALS
  my ($ivalsing) = $interval =~ /(.*)s$/;
  print include::standardoutput($title,
                                (include::infobox("Based on Cached Previously-Viewed Statistics",
      qq[In order to show these statistics over a long period of time, it is necessary for
         performance reasons to rely on cached statistics for each $ivalsing.  Only $interval whose data have been
         previously gathered, will be shown here.  If some $interval are missing, try visiting their per-$ivalsing
         pages (choose <q>last $ivalsing</q>, then <q>previous $ivalsing</q> at the bottom of that page, etc.) first,
         then come back to the ${ivalsing}-by-$ivalsing statistics.]) . join qq[\n\n<hr />\n\n], @catinfo),
                                undef, undef,
                                qq[]
                               );
}

sub svggraphs_not_enabled {
  return qq[<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<!-- Created with Inkscape (http://www.inkscape.org/) -->

<svg
   xmlns:dc="http://purl.org/dc/elements/1.1/"
   xmlns:cc="http://creativecommons.org/ns#"
   xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
   xmlns:svg="http://www.w3.org/2000/svg"
   xmlns="http://www.w3.org/2000/svg"
   version="1.1"
   width="300"
   height="200"
   id="svg2">
  <defs
     id="defs4" />
  <metadata
     id="metadata7">
    <rdf:RDF>
      <cc:Work
         rdf:about="">
        <dc:format>image/svg+xml</dc:format>
        <dc:type
           rdf:resource="http://purl.org/dc/dcmitype/StillImage" />
        <dc:title></dc:title>
      </cc:Work>
    </rdf:RDF>
  </metadata>
  <g
     transform="translate(0,-852.36218)"
     id="layer1">
    <rect
       width="280"
       height="180"
       x="10"
       y="862.36218"
       id="rect3753"
       style="fill:#331f00;fill-opacity:1;stroke:none" />
    <path
       d="m 233.78125,26.8125 c -0.86059,0.02736 -1.63344,0.26407 -2.34375,0.6875 -0.71032,0.40983 -1.29529,0.94596 -1.71875,1.65625 -0.4098,0.71035 -0.59375,1.49293 -0.59375,2.3125 l 0,24.34375 c 0,1.31137 0.44219,2.42854 1.34375,3.34375 0.91521,0.90156 2.01086,1.34375 3.28125,1.34375 0.84691,0 1.61976,-0.19761 2.34375,-0.59375 0.72397,-0.4098 1.29528,-0.96352 1.71875,-1.6875 0.43711,-0.72397 0.65624,-1.52807 0.65625,-2.375 l 0,-8.875 c -1e-5,-0.66933 0.24064,-1.23671 0.71875,-1.6875 0.47808,-0.45077 1.04546,-0.68749 1.6875,-0.6875 0.62834,0.01367 1.15661,0.25825 1.59375,0.75 0.4371,0.47811 0.65623,1.04156 0.65625,1.65625 l 0,8.84375 c -2e-5,1.29771 0.45584,2.39729 1.34375,3.3125 0.90155,0.91522 1.98354,1.4317 3.28125,1.5 1.33866,0 2.49101,-0.45978 3.40625,-1.375 0.92886,-0.92888 1.37498,-2.08122 1.375,-3.40625 l 0,-11 c -2e-5,-1.13377 -0.21522,-2.22156 -0.625,-3.21875 -0.39616,-0.99716 -0.94595,-1.81698 -1.65625,-2.5 -0.71034,-0.69664 -1.58686,-1.26009 -2.625,-1.65625 -1.02451,-0.39612 -2.13195,-0.59373 -3.375,-0.59375 -1.27039,2e-5 -2.64974,0.23674 -4.125,0.6875 -0.60106,0.21858 -1.1645,0.45923 -1.65625,0.71875 l 0,-6.8125 c -1e-5,-0.84689 -0.20155,-1.6334 -0.625,-2.34375 -0.40981,-0.72395 -0.97719,-1.29526 -1.6875,-1.71875 -0.71033,-0.42343 -1.50077,-0.62496 -2.375,-0.625 z M 75.0625,29.28125 c -0.983542,3e-5 -1.867922,0.30131 -2.6875,0.875 -0.80596,0.56009 -1.412449,1.32508 -1.78125,2.28125 l -4.9375,13.75 L 60.75,32.4375 C 60.381172,31.46767 59.805932,30.70268 59,30.15625 c -0.805946,-0.54637 -1.739165,-0.81247 -2.75,-0.8125 -0.805943,3e-5 -1.514233,0.13701 -2.15625,0.4375 -0.860581,0.42349 -1.55708,1.02025 -2.0625,1.8125 -0.491759,0.79231 -0.71875,1.62579 -0.71875,2.5 0,0.60106 0.115461,1.21148 0.375,1.8125 L 61.09375,57.25 c 0.969849,2.24024 2.443129,3.34375 4.4375,3.34375 0.505405,0 1.076716,-0.07242 1.71875,-0.25 1.243043,-0.36882 2.262343,-1.39991 3,-3.09375 l 9.40625,-21.34375 c 0.245852,-0.5737 0.343722,-1.18412 0.34375,-1.8125 -2.8e-5,-0.90153 -0.227018,-1.72135 -0.71875,-2.5 -0.491787,-0.77859 -1.170697,-1.38901 -2.03125,-1.8125 -0.724005,-0.32781 -1.463544,-0.49997 -2.1875,-0.5 z m 20,0 c -3.387693,3e-5 -6.412472,0.84717 -9.0625,2.5 -2.431485,1.52995 -4.317574,3.463 -5.65625,5.8125 -1.325021,2.33588 -2.000001,4.8148 -2,7.4375 -10e-7,1.99437 0.412809,3.96654 1.21875,5.90625 0.696657,1.6392 1.620147,3.09097 2.78125,4.375 1.161094,1.28405 2.518913,2.33666 4.0625,3.15625 1.557229,0.80594 3.275089,1.35966 5.1875,1.6875 1.393305,0.21856 2.665044,0.34375 3.8125,0.34375 2.008,0 3.864709,-0.28369 5.53125,-0.84375 1.68015,-0.56006 3.15343,-1.37201 4.4375,-2.4375 1.29767,-1.07913 2.35421,-2.3548 3.1875,-3.84375 0.75127,-1.35233 1.24623,-2.66712 1.4375,-3.9375 0.19116,-1.01083 0.28121,-2.01254 0.28125,-2.96875 -4e-5,-3.29205 -1.50849,-4.93748 -4.5,-4.9375 l -8.125,0 c -0.764979,2e-5 -1.469339,0.21129 -2.125,0.59375 -0.642037,0.3825 -1.162447,0.88924 -1.53125,1.53125 -0.368836,0.62837 -0.56645,1.33273 -0.59375,2.125 -1.6e-5,1.18843 0.399133,2.21559 1.21875,3.0625 0.833241,0.84693 1.860401,1.28126 3.0625,1.28125 l 2.53125,0 c -0.601062,0.83326 -1.645812,1.38306 -3.09375,1.65625 -0.710339,0.17757 -1.418628,0.25001 -2.15625,0.25 -1.215755,1e-5 -2.311405,-0.22306 -3.28125,-0.6875 -0.956213,-0.4781 -1.746653,-1.13941 -2.375,-2 C 88.684129,48.46952 88.24587,47.40325 88,46.1875 c -0.08197,-0.45077 -0.12501,-0.89689 -0.125,-1.375 -1e-5,-0.36881 0.04303,-0.74251 0.125,-1.125 0.20489,-1.20206 0.621629,-2.27226 1.25,-3.1875 0.628347,-0.9152 1.401197,-1.59804 2.34375,-2.0625 0.942525,-0.47808 2.030314,-0.71873 3.21875,-0.71875 1.47526,2e-5 3.04248,0.39524 4.75,1.1875 0.204878,0.08198 0.52375,0.21896 0.90625,0.4375 l 1.75,0.9375 0.0312,0 c 0.81957,0.34152 1.58849,0.50002 2.3125,0.5 0.98349,2e-5 1.83456,-0.29153 2.53125,-0.90625 0.98349,-0.86056 1.46872,-1.84075 1.46875,-2.90625 -3e-5,-1.78944 -1.17203,-3.46032 -3.5625,-5.03125 -1.17479,-0.71029 -2.4426,-1.2816 -3.78125,-1.71875 -1.393342,-0.43709 -2.819651,-0.72078 -4.28125,-0.84375 -0.819618,-0.0546 -1.437898,-0.09372 -1.875,-0.09375 z m 45.8125,0 c -3.38769,3e-5 -6.41247,0.84717 -9.0625,2.5 -2.43148,1.52995 -4.31757,3.463 -5.65625,5.8125 -1.32502,2.33588 -2,4.8148 -2,7.4375 0,1.99437 0.41281,3.96654 1.21875,5.90625 0.69666,1.6392 1.62015,3.09097 2.78125,4.375 1.1611,1.28405 2.51891,2.33666 4.0625,3.15625 1.55723,0.80594 3.30634,1.35966 5.21875,1.6875 1.3933,0.21856 2.63379,0.34375 3.78125,0.34375 2.008,0 3.86471,-0.28369 5.53125,-0.84375 1.68015,-0.56006 3.15343,-1.37201 4.4375,-2.4375 1.29767,-1.07913 2.35421,-2.3548 3.1875,-3.84375 0.75126,-1.35233 1.24622,-2.66712 1.4375,-3.9375 0.19116,-1.01083 0.28121,-2.01254 0.28125,-2.96875 -4e-5,-3.29205 -1.5085,-4.93748 -4.5,-4.9375 l -8.125,0 c -0.76498,2e-5 -1.46934,0.21129 -2.125,0.59375 -0.64204,0.3825 -1.16245,0.88924 -1.53125,1.53125 -0.36884,0.62837 -0.56645,1.33273 -0.59375,2.125 -2e-5,1.18843 0.43038,2.21559 1.25,3.0625 0.83324,0.84693 1.82915,1.28126 3.03125,1.28125 l 2.53125,0 c -0.60106,0.83326 -1.61456,1.38306 -3.0625,1.65625 -0.71034,0.17757 -1.44988,0.25001 -2.1875,0.25 -1.21576,1e-5 -2.31141,-0.22306 -3.28125,-0.6875 -0.95621,-0.4781 -1.74665,-1.13941 -2.375,-2 -0.62837,-0.87423 -1.06663,-1.9405 -1.3125,-3.15625 -0.0819,-0.45077 -0.12501,-0.89689 -0.125,-1.375 -1e-5,-0.36881 0.043,-0.74251 0.125,-1.125 0.20489,-1.20206 0.62163,-2.27226 1.25,-3.1875 0.62835,-0.9152 1.43245,-1.59804 2.375,-2.0625 0.94253,-0.47808 1.99906,-0.71873 3.1875,-0.71875 1.47526,2e-5 3.07373,0.39524 4.78125,1.1875 0.20488,0.08198 0.4925,0.21896 0.875,0.4375 l 1.75,0.9375 0.0312,0 c 0.81957,0.34152 1.61974,0.50002 2.34375,0.5 0.98349,2e-5 1.80331,-0.29153 2.5,-0.90625 0.98349,-0.86056 1.46871,-1.84075 1.46875,-2.90625 -4e-5,-1.78944 -1.17203,-3.46032 -3.5625,-5.03125 -1.17479,-0.71029 -2.4426,-1.2816 -3.78125,-1.71875 -1.39334,-0.43709 -2.81965,-0.72078 -4.28125,-0.84375 -0.81962,-0.0546 -1.4379,-0.09372 -1.875,-0.09375 z m -101.28125,0.0625 c -0.751313,3e-5 -1.477193,0.0431 -2.1875,0.125 -1.80313,0.21859 -3.423119,0.66078 -4.84375,1.34375 -1.420645,0.68303 -2.584785,1.52044 -3.5,2.53125 -0.819602,0.88793 -1.420292,1.87597 -1.84375,2.96875 -0.4098,1.09282 -0.625001,2.20606 -0.625,3.3125 -1e-6,1.37968 0.291549,2.65142 0.90625,3.8125 0.628358,1.16111 1.522467,2.10612 2.65625,2.84375 1.051814,0.65569 2.327484,1.18396 3.84375,1.59375 l 2.78125,0.8125 0.4375,0.0625 2.21875,0.5625 0.53125,0.15625 0.8125,0.28125 c 0.163905,0.05464 0.25784,0.0977 0.3125,0.125 0.286844,0.17759 0.437485,0.41824 0.4375,0.71875 -1.5e-5,0.2732 -0.146726,0.51385 -0.40625,0.71875 -0.177595,0.15026 -0.508255,0.3185 -1,0.46875 -0.341514,0.12291 -0.719144,0.18751 -1.15625,0.1875 -0.423472,1e-5 -0.908703,-0.06065 -1.46875,-0.15625 -0.177592,-0.04094 -0.418242,-0.084 -0.71875,-0.125 l -0.46875,-0.125 -1.1875,-0.28125 -1.6875,-0.4375 -1.84375,-0.5 C 31.101985,50.23453 30.616755,50.18751 30.125,50.1875 c -1.202083,1e-5 -2.207722,0.6065 -3,1.78125 -0.42346,0.64203 -0.64652,1.39729 -0.6875,2.3125 -1e-6,0.99719 0.18002,1.82674 0.5625,2.46875 0.396139,0.64203 1.122018,1.28183 2.1875,1.9375 1.598214,0.9562 4.055613,1.52751 7.375,1.71875 0.846908,0.0547 1.457328,0.09375 1.8125,0.09375 4.699022,0 8.25207,-1.46542 10.65625,-4.375 1.570875,-1.85775 2.343724,-3.89842 2.34375,-6.125 -2.6e-5,-0.77861 -0.09004,-1.50842 -0.28125,-2.21875 -0.191265,-0.71031 -0.496475,-1.39315 -0.90625,-2.0625 -0.396164,-0.66933 -0.881393,-1.27975 -1.46875,-1.8125 -0.573742,-0.54639 -1.248722,-1.02376 -2,-1.40625 -0.98354,-0.5054 -2.177059,-0.95152 -3.625,-1.375 L 40.3125,40.3125 38.9375,40 38.09375,39.78125 37.8125,39.6875 37,39.46875 C 36.699469,39.38681 36.462749,39.2968 36.3125,39.1875 36.14857,39.06458 36.09374,38.9276 36.09375,38.75 c -1e-5,-0.27318 0.09786,-0.51383 0.34375,-0.71875 0.286849,-0.2322 0.815119,-0.34373 1.59375,-0.34375 0.136588,0 0.24419,-0.0136 0.3125,0 0.08195,0 0.16803,0.01765 0.25,0.03125 L 39,37.78125 l 0.59375,0.15625 1.1875,0.28125 0.5,0.125 L 42.5,38.75 l 0.3125,0.125 c 0.969842,0.27322 1.860022,0.40627 2.625,0.40625 0.72396,2e-5 1.324649,-0.15062 1.84375,-0.4375 0.532718,-0.28684 0.996428,-0.74269 1.40625,-1.34375 0.450757,-0.62834 0.687477,-1.37574 0.6875,-2.25 -2.3e-5,-0.4371 -0.05092,-0.92232 -0.1875,-1.46875 -0.259563,-0.88787 -0.783903,-1.63134 -1.5625,-2.21875 -0.764981,-0.60101 -1.94671,-1.14687 -3.53125,-1.625 -1.434317,-0.40977 -2.942776,-0.59372 -4.5,-0.59375 z m 157.03125,7.1875 c -0.4508,2e-5 -0.85968,0.12521 -1.1875,0.34375 l -3.875,2.0625 0,-0.125 c -1.37967,-1.35232 -3.07994,-2.03123 -5.15625,-2.03125 -0.49177,2e-5 -1.20586,0.10369 -2.09375,0.28125 -1.58456,0.3142 -3.01874,0.97945 -4.34375,2.03125 -1.32503,1.03818 -2.39916,2.37055 -3.21875,3.96875 -0.80594,1.59823 -1.2794,3.33368 -1.375,5.21875 0,1.46163 0.16823,2.77248 0.46875,3.90625 0.30052,1.13379 0.7427,2.20792 1.34375,3.21875 0.88789,1.33869 1.95416,2.41675 3.15625,3.25 1.20207,0.8196 2.41712,1.34787 3.6875,1.59375 0.88789,0.16388 1.69592,0.25 2.40625,0.25 2.15827,0 3.85461,-0.66132 5.125,-2 l 0,-0.21875 3.84375,2.1875 c 1.325,0 2.43824,-0.43826 3.3125,-1.3125 0.87422,-0.87423 1.31248,-1.99533 1.3125,-3.375 l 0,-14.25 c -2e-5,-1.68016 -0.57133,-3.07129 -1.71875,-4.21875 -0.4508,-0.5054 -1.01818,-0.78123 -1.6875,-0.78125 z m 68.5625,0.34375 c -2.06267,2e-5 -3.88027,0.34827 -5.4375,1.03125 -1.54358,0.68302 -2.72924,1.58892 -3.5625,2.75 -0.83326,1.14746 -1.25,2.37615 -1.25,3.6875 0,0.79229 0.15457,1.59639 0.46875,2.375 0.31418,0.72399 0.69181,1.33834 1.15625,1.84375 0.4781,0.50543 1.14915,0.96521 1.96875,1.375 0.83326,0.39615 1.86827,0.75225 3.125,1.09375 l 0.78125,0.21875 1.09375,0.3125 0.84375,0.21875 0.40625,0.125 c 0.0273,0.0137 0.0352,0.0352 0.0625,0.0625 0.0409,0.0137 0.084,0.0352 0.125,0.0625 0.041,0.0137 0.0801,0.01765 0.0937,0.03125 0.30051,0.19125 0.43749,0.51405 0.4375,0.9375 -0.12295,0.24589 -0.34994,0.37501 -0.71875,0.375 l -0.53125,0 -0.25,0 c -0.75131,-0.09561 -1.57113,-0.33626 -2.5,-0.71875 l -0.59375,-0.21875 -0.84375,-0.25 c -0.80594,-0.25953 -1.50244,-0.37499 -2.0625,-0.375 -0.91522,1e-5 -1.70173,0.21914 -2.34375,0.65625 -0.64202,0.42347 -1.08028,1.01237 -1.3125,1.75 -0.12291,0.30053 -0.15625,0.63512 -0.15625,1.03125 0,1.29771 0.88438,2.50489 2.6875,3.625 1.46162,0.86058 3.47289,1.40251 6,1.59375 0.84691,0.0547 1.46126,0.0625 1.84375,0.0625 2.95054,0 5.30034,-0.70436 7.0625,-2.125 1.89872,-1.52991 2.84373,-3.36903 2.84375,-5.5 -2e-5,-1.01083 -0.25826,-1.96371 -0.75,-2.90625 -0.47812,-0.95619 -1.16489,-1.76422 -2.09375,-2.40625 C 270.79771,46.93808 269.87422,46.46071 269,46.1875 l -0.9375,-0.3125 -1.03125,-0.3125 -1.5,-0.5 -0.59375,-0.1875 -0.40625,-0.15625 c -0.0546,-0.0274 -0.084,-0.06645 -0.125,-0.09375 -0.041,-0.0274 -0.10165,-0.0352 -0.15625,-0.0625 -0.28687,-0.20489 -0.43751,-0.41616 -0.4375,-0.59375 -10e-6,-0.08195 0.0607,-0.1544 0.15625,-0.25 l 0.125,-0.125 0.0937,-0.09375 c 0.10927,-0.0273 0.5378,-0.03124 1.34375,-0.03125 0.0956,0 0.28143,0.03915 0.5,0.09375 l 0.65625,0.125 0.625,0.15625 1.28125,0.3125 c 0.86056,0.21857 1.52974,0.31251 2.0625,0.3125 0.34148,1e-5 0.70339,-0.043 1.03125,-0.125 0.72396,-0.17757 1.29527,-0.53368 1.71875,-1.09375 0.42344,-0.57371 0.62498,-1.20564 0.625,-1.875 -2e-5,-0.69664 -0.17611,-1.27188 -0.53125,-1.75 -0.71034,-0.94252 -2.05057,-1.70358 -4.03125,-2.25 -1.25674,-0.34148 -2.68304,-0.49998 -4.28125,-0.5 z m -102.375,0.09375 c -1.28405,2e-5 -2.39729,0.4598 -3.3125,1.375 -0.91522,0.91524 -1.375,2.01482 -1.375,3.3125 l 0,14.1875 c 0,1.28405 0.45978,2.36211 1.375,3.25 0.91521,0.87424 2.02845,1.3125 3.3125,1.3125 0.83325,-0.01366 1.60217,-0.21913 2.3125,-0.65625 0.71031,-0.43712 1.27769,-1.04361 1.6875,-1.78125 0.40979,-0.75129 0.59374,-1.54959 0.59375,-2.4375 l 0,-4.125 c -1e-5,-0.8879 0.043,-1.58832 0.125,-2.09375 0.0956,-0.51907 0.25017,-0.95733 0.46875,-1.3125 0.2322,-0.35515 0.59411,-0.68188 1.03125,-0.96875 0.45076,-0.28685 1.02208,-0.57054 1.71875,-0.84375 0.19123,-0.08195 0.32821,-0.1465 0.4375,-0.1875 0.10927,-0.04097 0.25598,-0.0703 0.40625,-0.125 1.48893,-0.50541 2.56699,-1.13342 3.25,-1.84375 0.68298,-0.72397 1.03123,-1.5653 1.03125,-2.5625 -1e-4,-0.21854 -0.0392,-0.56679 -0.0937,-1.03125 -0.15028,-0.76494 -0.52004,-1.44385 -1.09375,-2.03125 -0.56007,-0.58736 -1.24291,-0.98258 -2.0625,-1.1875 -0.32785,-0.10922 -0.70548,-0.15623 -1.15625,-0.15625 -1.27039,0.041 -2.45606,0.65142 -3.5625,1.8125 l -0.53125,0.53125 -0.25,0.28125 0,0.21875 -4.3125,-2.9375 z m 44.40625,0 c -1.32502,2e-5 -2.44613,0.47346 -3.375,1.375 -0.91523,0.88792 -1.37501,1.96991 -1.375,3.28125 l 0,24.46875 c -1e-5,1.29769 0.47343,2.43245 1.375,3.375 0.90155,0.94253 1.96596,1.40624 3.25,1.40625 1.2294,-1e-5 2.30353,-0.45979 3.21875,-1.375 0.92887,-0.92889 1.40624,-2.06365 1.40625,-3.375 l 0,-6.59375 0.40625,0.1875 0.46875,0.15625 c 1.13377,0.43712 2.35461,0.65625 3.625,0.65625 1.20207,0 2.39165,-0.18395 3.59375,-0.59375 1.81676,-0.65568 3.34674,-1.72587 4.5625,-3.1875 1.21571,-1.46161 2.01401,-3.23618 2.4375,-5.3125 0.20487,-0.84692 0.31247,-1.70584 0.3125,-2.59375 -3e-5,-0.61469 -0.0685,-1.38361 -0.21875,-2.3125 -0.28689,-1.65285 -0.81516,-3.13979 -1.59375,-4.4375 C 224.54752,40.79607 223.60644,39.77864 222.5,39 c -0.9289,-0.68298 -1.91302,-1.20339 -2.9375,-1.53125 -1.01086,-0.32782 -2.06346,-0.49998 -3.15625,-0.5 -2.14463,2e-5 -3.98768,0.64955 -5.53125,1.90625 l 0,0.1875 -3.65625,-2.09375 z m -19.4375,8.15625 c 0.40979,1e-5 0.8168,0.09395 1.28125,0.3125 1.07913,0.49177 1.73259,1.43678 1.9375,2.84375 0,0.56007 -0.004,0.99833 -0.0312,1.3125 -0.041,0.39615 -0.19163,0.80896 -0.4375,1.21875 -0.28687,0.56006 -0.6645,0.98074 -1.15625,1.28125 -0.49177,0.28687 -1.01611,0.43751 -1.5625,0.4375 -0.91523,1e-5 -1.69781,-0.3737 -2.3125,-1.125 -0.56007,-0.72398 -0.81251,-1.57504 -0.8125,-2.53125 0.0273,-0.16391 0.0312,-0.2794 0.0312,-0.375 0.0137,-0.10927 0.0175,-0.23839 0.0312,-0.375 0.16391,-0.91521 0.51609,-1.64109 1.0625,-2.1875 0.54639,-0.54639 1.21744,-0.81249 1.96875,-0.8125 z m 27.5,0.21875 c 0.66933,0.10929 1.23671,0.43209 1.6875,0.9375 0.46443,0.49177 0.75204,1.14523 0.875,1.9375 -2e-5,1.43431 -0.28763,2.51629 -0.875,3.28125 -0.58739,0.76496 -1.35238,1.15626 -2.28125,1.15625 -0.88791,1e-5 -1.61772,-0.34431 -2.21875,-1 C 211.88136,50.98692 211.5762,50.10647 211.5625,49 c -1e-5,-1.13377 0.33065,-2.01422 1,-2.65625 0.68299,-0.65567 1.58496,-0.99999 2.71875,-1 z"
       transform="translate(0,852.36218)"
       id="path3840"
       style="font-size:41.96350861px;font-style:normal;font-variant:normal;font-weight:normal;font-stretch:normal;text-align:center;line-height:125%;letter-spacing:0px;word-spacing:0px;writing-mode:lr-tb;text-anchor:middle;fill:#c4ffc5;fill-opacity:1;stroke:none;font-family:Anja Eliane accent;-inkscape-font-specification:Anja Eliane accent" />
    <path
       d="m 217.84375,83.6875 c -1.27038,2e-5 -2.34845,0.44222 -3.25,1.34375 -0.92889,0.96989 -1.40626,2.09099 -1.40625,3.375 l 0,2.03125 -0.40625,0 c -1.10647,3e-5 -2.06906,0.3698 -2.875,1.09375 -0.80594,0.76498 -1.1875,1.70606 -1.1875,2.8125 0,1.01086 0.33852,1.86979 1.0625,2.59375 0.84692,0.84694 1.85648,1.25002 3.03125,1.25 l 0.34375,0 0,10.71875 c -1e-5,1.32502 0.47736,2.46764 1.40625,3.4375 0.91521,0.91522 1.99721,1.375 3.28125,1.375 1.31135,0 2.407,-0.45978 3.28125,-1.375 0.92887,-0.92888 1.40624,-2.06757 1.40625,-3.40625 l 0,-10.65625 0.5625,0 c 1.10645,-0.04096 2.06905,-0.47529 2.875,-1.28125 0.21855,-0.24586 0.39857,-0.49437 0.5625,-0.78125 0.17757,-0.3005 0.32425,-0.6233 0.40625,-0.9375 0.0819,-0.31416 0.0937,-0.60571 0.0937,-0.90625 -2e-5,-1.07912 -0.39523,-2.0202 -1.1875,-2.8125 -0.77863,-0.75127 -1.68453,-1.12497 -2.75,-1.125 l -0.53125,0 0,-1.9375 c -1e-5,-1.28401 -0.47738,-2.42663 -1.40625,-3.4375 -0.92889,-0.92885 -2.02847,-1.37498 -3.3125,-1.375 z M 97.28125,89.75 c -0.450801,3e-5 -0.828432,0.12522 -1.15625,0.34375 l -3.875,2.0625 0,-0.125 C 90.870324,90.67894 89.138806,90.00003 87.0625,90 c -0.491771,3e-5 -1.174611,0.1037 -2.0625,0.28125 -1.584568,0.31421 -3.049987,0.97946 -4.375,2.03125 -1.325024,1.03818 -2.399154,2.37055 -3.21875,3.96875 -0.805941,1.59824 -1.24813,3.33368 -1.34375,5.21875 -10e-7,1.46163 0.136979,2.77248 0.4375,3.90625 0.300518,1.13379 0.742708,2.20791 1.34375,3.21875 0.887896,1.33868 1.954165,2.41674 3.15625,3.25 1.202072,0.8196 2.417112,1.34787 3.6875,1.59375 0.887889,0.16388 1.695919,0.25 2.40625,0.25 2.158265,0 3.885854,-0.66132 5.15625,-2 l 0,-0.21875 3.8125,2.1875 c 1.324997,0 2.438237,-0.43826 3.3125,-1.3125 0.87421,-0.87424 1.31247,-2.02659 1.3125,-3.40625 l 0,-14.21875 c -3e-5,-1.68016 -0.57134,-3.07129 -1.71875,-4.21875 -0.450803,-0.50539 -1.018183,-0.78122 -1.6875,-0.78125 z m 99.125,0.25 c -2.30855,3e-5 -4.41377,0.54589 -6.3125,1.625 -1.89874,1.07916 -3.37596,2.54851 -4.46875,4.40625 C 184.54585,97.87537 184,99.85539 184,102 c 0.0137,2.14463 0.56344,4.15198 1.65625,5.96875 1.09279,1.80312 2.58367,3.22943 4.46875,4.28125 1.89873,1.05182 3.98636,1.5625 6.28125,1.5625 2.32219,0 4.44892,-0.5322 6.375,-1.625 1.28402,-0.73764 2.39726,-1.67086 3.3125,-2.75 0.9152,-1.0928 1.58044,-2.2648 2.03125,-3.5625 0.46441,-1.29769 0.71872,-2.6164 0.71875,-3.96875 -3e-5,-0.80593 -0.0861,-1.63155 -0.25,-2.4375 -0.16395,-0.80592 -0.43978,-1.59243 -0.78125,-2.34375 -0.32786,-0.75128 -0.73094,-1.45957 -1.25,-2.15625 -0.50544,-0.69664 -1.09827,-1.3501 -1.78125,-1.9375 -1.12014,-0.96984 -2.40554,-1.69964 -3.8125,-2.21875 -1.40699,-0.53271 -2.92331,-0.81247 -4.5625,-0.8125 z m -23.34375,0.125 c -1.87143,3e-5 -3.76145,0.60652 -5.6875,1.78125 -0.30053,0.19126 -0.49815,0.31065 -0.59375,0.40625 l 0,0.1875 -3.6875,-2.3125 c -1.2977,3e-5 -2.37969,0.45588 -3.28125,1.34375 -0.8879,0.87426 -1.34375,1.97777 -1.34375,3.34375 l 0,14.09375 c 0,1.2977 0.44219,2.43246 1.34375,3.375 0.92888,0.8879 2.02846,1.34375 3.3125,1.34375 1.28403,0 2.39334,-0.45585 3.28125,-1.34375 0.92887,-0.92888 1.37499,-2.06364 1.375,-3.375 l 0,-8.75 c -1e-5,-0.62835 0.24064,-1.19965 0.71875,-1.71875 0.43711,-0.45076 1.00056,-0.68748 1.65625,-0.6875 0.65567,2e-5 1.18787,0.2446 1.625,0.75 0.46442,0.43714 0.68748,1.00058 0.6875,1.65625 l 0,8.8125 c -2e-5,1.32502 0.47735,2.44219 1.40625,3.34375 0.92886,0.90156 2.06362,1.34375 3.375,1.34375 0.8469,-0.0137 1.60216,-0.23279 2.3125,-0.65625 0.71029,-0.42346 1.27767,-1.00843 1.6875,-1.71875 0.42343,-0.71032 0.62497,-1.50076 0.625,-2.375 l 0,-10.84375 c -3e-5,-1.20206 -0.26613,-2.35834 -0.8125,-3.4375 -0.54643,-1.07912 -1.33687,-1.98502 -2.375,-2.75 -1.03818,-0.76493 -2.22777,-1.30686 -3.59375,-1.59375 -0.80596,-0.15019 -1.49853,-0.21872 -2.03125,-0.21875 z m -65.25,0.0625 c -1.28404,3e-5 -2.36604,0.45981 -3.28125,1.375 -0.91523,0.91524 -1.37501,2.01482 -1.375,3.3125 l 0,14.1875 c -1e-5,1.28404 0.45977,2.3621 1.375,3.25 0.91521,0.87424 1.99721,1.3125 3.28125,1.3125 0.83326,-0.0137 1.60218,-0.21913 2.3125,-0.65625 0.71032,-0.43712 1.27769,-1.04361 1.6875,-1.78125 0.40979,-0.7513 0.62499,-1.58085 0.625,-2.46875 l 0,-4.09375 c -1e-5,-0.88789 0.043,-1.58832 0.125,-2.09375 0.0956,-0.51907 0.25018,-0.95733 0.46875,-1.3125 0.23221,-0.35515 0.56287,-0.68188 1,-0.96875 0.45077,-0.28685 1.02208,-0.57054 1.71875,-0.84375 0.19123,-0.08195 0.32821,-0.1465 0.4375,-0.1875 0.10927,-0.04096 0.25598,-0.0703 0.40625,-0.125 1.48893,-0.5054 2.56698,-1.13341 3.25,-1.84375 0.68298,-0.72396 1.03123,-1.5653 1.03125,-2.5625 -1e-4,-0.21854 -0.0392,-0.56679 -0.0937,-1.03125 -0.15028,-0.76494 -0.52005,-1.44385 -1.09375,-2.03125 -0.56008,-0.58735 -1.24291,-0.98257 -2.0625,-1.1875 -0.32785,-0.10922 -0.70548,-0.15622 -1.15625,-0.15625 -1.27039,0.04101 -2.45605,0.62018 -3.5625,1.78125 l -0.53125,0.53125 -0.25,0.3125 0,0.21875 -4.3125,-2.9375 z m 24.5,0 c -1.76215,3e-5 -3.39,0.28765 -4.90625,0.875 -1.51627,0.5874 -2.83104,1.41302 -3.9375,2.4375 -1.0928,1.01086 -1.96932,2.20438 -2.625,3.625 -0.64202,1.407 -0.99025,2.89393 -1.03125,4.4375 0,1.74849 0.30914,3.36848 0.9375,4.84375 0.62836,1.47528 1.56551,2.75095 2.78125,3.84375 1.21574,1.0928 2.68115,1.93021 4.375,2.53125 1.70749,0.58738 3.5584,0.90625 5.59375,0.90625 0.9835,0 1.92065,-0.0782 2.78125,-0.1875 1.22938,-0.15026 2.41897,-0.39484 3.59375,-0.75 0.95617,-0.3415 1.69964,-0.65457 2.21875,-0.96875 0.53271,-0.32784 0.96704,-0.7152 1.28125,-1.125 0.32781,-0.4098 0.56846,-0.85592 0.71875,-1.375 0.0546,-0.19124 0.0625,-0.471 0.0625,-0.8125 -3e-5,-0.94254 -0.33069,-1.73297 -1,-2.375 -0.65571,-0.64201 -1.51857,-0.96874 -2.625,-0.96875 -0.40982,1e-5 -1.12784,0.12913 -2.125,0.375 -1.29772,0.35517 -2.37185,0.55275 -3.21875,0.59375 -0.87426,1e-5 -1.60407,-0.043 -2.21875,-0.125 -0.61471,-0.0956 -1.13119,-0.20714 -1.5,-0.34375 -0.35517,-0.15025 -0.72887,-0.38697 -1.125,-0.6875 -0.45079,-0.45077 -0.6954,-0.69925 -0.75,-0.78125 l 10.9375,0 c 1.36597,1e-5 2.31884,-0.28368 2.90625,-0.84375 0.58735,-0.56005 0.87497,-1.54024 0.875,-2.90625 -0.041,-1.01083 -0.28952,-2.02825 -0.78125,-3.09375 -0.47813,-1.07912 -1.13945,-2.10628 -2,-3.0625 -0.84695,-0.96984 -1.84865,-1.7818 -2.96875,-2.4375 -1.83046,-1.03813 -3.91416,-1.584 -6.25,-1.625 z m -0.53125,6.9375 c 1.69382,2e-5 2.63883,0.67893 2.84375,2.03125 0.0273,0.10929 0.0625,0.24234 0.0625,0.40625 l -5,0 c 0,-0.08195 0.008,-0.17982 0.0625,-0.34375 0.35515,-1.13376 1.03406,-1.84785 2.03125,-2.09375 z m 64.625,1.0625 c 1.14743,2e-5 2.0494,0.5674 2.71875,1.6875 0.36881,0.56007 0.56249,1.25657 0.5625,2.0625 -1e-4,0.17759 -0.008,0.46914 -0.0625,0.90625 -0.23223,1.68019 -1.08723,2.66824 -2.5625,2.96875 -0.34151,0.0683 -0.57425,0.12501 -0.65625,0.125 -0.91523,1e-5 -1.70174,-0.38735 -2.34375,-1.125 -0.62837,-0.73763 -0.93751,-1.68264 -0.9375,-2.84375 -1e-5,-0.79227 0.19367,-1.4927 0.5625,-2.09375 0.68299,-1.1201 1.58496,-1.68748 2.71875,-1.6875 z M 88.4375,98.3125 c 0.409786,2e-5 0.848046,0.12521 1.3125,0.34375 1.079124,0.49178 1.701334,1.43678 1.90625,2.84375 -2e-5,0.56007 -0.004,0.99833 -0.03125,1.3125 -0.041,0.39615 -0.191636,0.80896 -0.4375,1.21875 -0.286876,0.56007 -0.664505,0.98074 -1.15625,1.28125 -0.491774,0.28687 -1.016114,0.43751 -1.5625,0.4375 -0.915232,1e-5 -1.666561,-0.37369 -2.28125,-1.125 -0.56007,-0.72397 -0.843761,-1.57504 -0.84375,-2.53125 0.02731,-0.16391 0.03124,-0.2794 0.03125,-0.375 0.01365,-0.10927 0.01758,-0.23839 0.03125,-0.375 0.163909,-0.91521 0.54734,-1.64109 1.09375,-2.1875 0.546388,-0.54638 1.186187,-0.84373 1.9375,-0.84375 z"
       transform="translate(0,852.36218)"
       id="path3869"
       style="font-size:41.96350861px;font-style:normal;font-variant:normal;font-weight:normal;font-stretch:normal;text-align:center;line-height:125%;letter-spacing:0px;word-spacing:0px;writing-mode:lr-tb;text-anchor:middle;fill:#fffec4;fill-opacity:1;stroke:none;font-family:Anja Eliane accent;-inkscape-font-specification:Anja Eliane accent" />
    <path
       d="m 148.34375,133.625 c -1.28405,0.0274 -2.3797,0.52231 -3.28125,1.4375 -0.90156,0.91525 -1.34375,2.0109 -1.34375,3.28125 l 0,24.09375 c 0,1.3797 0.4246,2.51835 1.3125,3.40625 0.88789,0.8879 1.9972,1.3125 3.28125,1.3125 l 3.6875,-2.25 0,0.15625 c 1.32501,1.448 3.0859,2.1875 5.3125,2.1875 0.5737,0 1.27021,-0.0822 2.0625,-0.21875 1.61187,-0.2868 3.08907,-0.98735 4.46875,-2.09375 1.37964,-1.1202 2.47529,-2.51125 3.28125,-4.21875 0.81958,-1.7075 1.24998,-3.5466 1.25,-5.5 -2e-5,-0.7923 -0.10369,-1.60815 -0.28125,-2.46875 -0.32786,-1.5845 -0.88158,-3.0069 -1.6875,-4.25 -0.80596,-1.24305 -1.82919,-2.2702 -3.03125,-3.0625 -1.2021,-0.80591 -2.56384,-1.33811 -4.09375,-1.625 -0.66935,-0.15019 -1.32282,-0.24997 -1.9375,-0.25 -1.10648,3e-5 -2.29607,0.23282 -3.59375,0.65625 -0.40981,0.13663 -0.65045,0.2227 -0.71875,0.25 l 0,-6.09375 c -1e-5,-0.86055 -0.21521,-1.6334 -0.625,-2.34375 -0.40981,-0.72395 -0.96353,-1.32651 -1.6875,-1.75 -0.71033,-0.43709 -1.50077,-0.65622 -2.375,-0.65625 z m 79.28125,0 c -1.31138,3e-5 -2.41096,0.45981 -3.3125,1.375 -0.88792,0.90159 -1.34377,1.99724 -1.34375,3.28125 l 0,6.53125 c -0.21858,-0.10925 -0.45923,-0.2168 -0.71875,-0.3125 -1.39334,-0.49173 -2.73357,-0.74997 -4.03125,-0.75 -1.78947,3e-5 -3.49554,0.49499 -5.09375,1.4375 -1.32503,0.76498 -2.42853,1.77849 -3.34375,3.0625 -0.91522,1.2841 -1.57261,2.7574 -1.96875,4.4375 -0.19126,0.8197 -0.28125,1.71365 -0.28125,2.65625 0,0.7376 0.0509,1.52415 0.1875,2.34375 0.46444,2.4452 1.50919,4.4936 3.09375,6.1875 1.59821,1.6802 3.48823,2.73285 5.6875,3.15625 0.79227,0.1369 1.47118,0.21875 2.03125,0.21875 2.17192,0 3.92496,-0.74345 5.25,-2.21875 l 0,-0.15625 3.84375,2.28125 c 0.87421,0 1.64707,-0.19765 2.34375,-0.59375 0.69664,-0.3962 1.26009,-0.9284 1.65625,-1.625 0.40978,-0.7103 0.59373,-1.5359 0.59375,-2.4375 l 0,-24.125 c -2e-5,-0.83323 -0.18397,-1.61974 -0.59375,-2.34375 -0.40982,-0.72395 -0.9772,-1.29526 -1.6875,-1.71875 -0.71034,-0.43709 -1.47927,-0.6738 -2.3125,-0.6875 z m -52.84375,0.0625 c -0.87425,3e-5 -1.68228,0.20157 -2.40625,0.625 -0.72398,0.40983 -1.29529,0.97721 -1.71875,1.6875 -0.42346,0.71035 -0.625,1.46168 -0.625,2.28125 l 0,24.3125 c 0,1.3114 0.44612,2.41485 1.375,3.34375 0.92888,0.8879 2.02452,1.34375 3.28125,1.34375 1.25671,0 2.35629,-0.45585 3.3125,-1.34375 0.88789,-0.9289 1.34374,-2.0363 1.34375,-3.375 l 0,-24.1875 c -1e-5,-0.83323 -0.21521,-1.60215 -0.625,-2.3125 -0.39615,-0.71029 -0.94594,-1.29526 -1.65625,-1.71875 -0.69667,-0.43709 -1.448,-0.64255 -2.28125,-0.65625 z M 73.6875,136.40625 c -0.928885,3e-5 -1.762364,0.21916 -2.5,0.65625 -0.737642,0.42349 -1.326543,0.99872 -1.75,1.75 -0.423461,0.75132 -0.625001,1.5848 -0.625,2.5 l 0,20.59375 c -10e-7,0.6284 0.115459,1.24275 0.375,1.84375 0.437118,0.9699 1.069058,1.7388 1.875,2.3125 0.819596,0.5601 1.660935,0.84375 2.5625,0.84375 l 11.3125,0 c 1.174741,0 2.21369,-0.4167 3.15625,-1.25 0.846898,-0.8059 1.281229,-1.7763 1.28125,-2.9375 -2.1e-5,-0.56 -0.125212,-1.1059 -0.34375,-1.625 -0.218582,-0.5327 -0.531651,-0.97495 -0.96875,-1.34375 -0.915239,-0.8742 -1.993299,-1.3125 -3.25,-1.3125 l -6.3125,0 0,-2.65625 5.5,0 c 1.147422,0 2.182442,-0.3815 3.125,-1.1875 0.874219,-0.8332 1.312479,-1.8174 1.3125,-2.9375 -2.1e-5,-0.5328 -0.09396,-1.03945 -0.3125,-1.53125 -0.21858,-0.5054 -0.52772,-0.9573 -0.9375,-1.3125 -0.409819,-0.4097 -0.895048,-0.7053 -1.46875,-0.9375 -0.573737,-0.24586 -1.162637,-0.37498 -1.75,-0.375 l -5.46875,0 0,-2.5625 6.625,0 c 0.751281,3e-5 1.434121,-0.21124 2.0625,-0.59375 0.642,-0.38245 1.162409,-0.87554 1.53125,-1.53125 0.382458,-0.65565 0.562479,-1.37761 0.5625,-2.15625 -2.1e-5,-0.79226 -0.180042,-1.51421 -0.5625,-2.15625 -0.368841,-0.64199 -0.88925,-1.1624 -1.53125,-1.53125 -0.628379,-0.38245 -1.272109,-0.56247 -1.96875,-0.5625 l -11.53125,0 z m 64.15625,6.9375 c -0.4508,3e-5 -0.82843,0.094 -1.15625,0.3125 l -3.875,2.0625 0,-0.125 c -1.37968,-1.35231 -3.11119,-2.03122 -5.1875,-2.03125 -0.49177,3e-5 -1.17461,0.1037 -2.0625,0.28125 -1.58457,0.31421 -3.04999,1.01071 -4.375,2.0625 -1.32502,1.03818 -2.39915,2.3393 -3.21875,3.9375 -0.80594,1.5983 -1.24815,3.33365 -1.34375,5.21875 0,1.4616 0.13698,2.77245 0.4375,3.90625 0.30052,1.1338 0.77396,2.20795 1.375,3.21875 0.8879,1.3387 1.92292,2.4168 3.125,3.25 1.20207,0.8196 2.44836,1.34795 3.71875,1.59375 0.88789,0.1639 1.66467,0.25 2.375,0.25 2.15827,0 3.88585,-0.6613 5.15625,-2 l 0,-0.21875 3.84375,2.1875 c 1.32499,0 2.40698,-0.4383 3.28125,-1.3125 0.87421,-0.8743 1.31247,-1.9953 1.3125,-3.375 l 0,-14.21875 c -3e-5,-1.68019 -0.57134,-3.10253 -1.71875,-4.25 -0.45081,-0.50539 -1.01819,-0.74997 -1.6875,-0.75 z m -32.125,0.34375 c -1.87144,3e-5 -3.79271,0.60652 -5.71875,1.78125 -0.300532,0.19127 -0.49814,0.3419 -0.59375,0.4375 l 0,0.15625 -3.6875,-2.3125 c -1.297704,3e-5 -2.379693,0.45588 -3.28125,1.34375 -0.887901,0.87426 -1.343751,2.00903 -1.34375,3.375 l 0,14.09375 c -10e-7,1.2977 0.442189,2.40125 1.34375,3.34375 0.928877,0.8879 2.059706,1.34375 3.34375,1.34375 1.284033,0 2.362092,-0.45585 3.25,-1.34375 0.928869,-0.9289 1.37499,-2.03235 1.375,-3.34375 l 0,-8.78125 c -1e-5,-0.6283 0.24064,-1.19975 0.71875,-1.71875 0.43711,-0.4508 1.00055,-0.6875 1.65625,-0.6875 0.65566,0 1.18786,0.27585 1.625,0.78125 0.46442,0.4371 0.71873,0.9693 0.71875,1.625 l 0,8.8125 c -2e-5,1.325 0.4461,2.44215 1.375,3.34375 0.92886,0.9015 2.06363,1.34375 3.375,1.34375 0.8469,-0.0136 1.60216,-0.23275 2.3125,-0.65625 0.7103,-0.4234 1.27768,-0.9772 1.6875,-1.6875 0.42344,-0.7103 0.62498,-1.5007 0.625,-2.375 l 0,-10.875 c -2e-5,-1.202 -0.26612,-2.32705 -0.8125,-3.40625 -0.54642,-1.07912 -1.33686,-2.01627 -2.375,-2.78125 -1.03818,-0.76493 -2.22777,-1.27561 -3.59375,-1.5625 -0.80596,-0.15019 -1.46728,-0.24997 -2,-0.25 z m 88.25,0.0625 c -1.76215,3e-5 -3.42125,0.3189 -4.9375,0.90625 -1.51627,0.58741 -2.83105,1.38177 -3.9375,2.40625 -1.09281,1.01091 -1.96932,2.23565 -2.625,3.65625 -0.64202,1.407 -0.959,2.86265 -1,4.40625 0,1.7484 0.30914,3.36845 0.9375,4.84375 0.62836,1.4753 1.53425,2.75095 2.75,3.84375 1.21573,1.0928 2.68115,1.9614 4.375,2.5625 1.70748,0.5873 3.58965,0.875 5.625,0.875 0.98351,0 1.88941,-0.047 2.75,-0.15625 1.22938,-0.1502 2.41897,-0.42615 3.59375,-0.78125 0.95618,-0.3415 1.69965,-0.65465 2.21875,-0.96875 0.53272,-0.3279 0.96705,-0.7152 1.28125,-1.125 0.32782,-0.4098 0.56847,-0.8559 0.71875,-1.375 0.0547,-0.1912 0.0937,-0.471 0.0937,-0.8125 -2e-5,-0.9426 -0.36193,-1.7329 -1.03125,-2.375 -0.6557,-0.642 -1.51856,-0.96875 -2.625,-0.96875 -0.40982,0 -1.12784,0.1292 -2.125,0.375 -1.29771,0.3552 -2.37184,0.55275 -3.21875,0.59375 -0.87425,0 -1.60406,-0.043 -2.21875,-0.125 -0.61471,-0.0956 -1.09994,-0.20715 -1.46875,-0.34375 -0.35517,-0.1503 -0.72888,-0.387 -1.125,-0.6875 -0.4508,-0.4508 -0.72665,-0.69925 -0.78125,-0.78125 l 10.9375,0 c 1.36598,0 2.3501,-0.28365 2.9375,-0.84375 0.58736,-0.56 0.87498,-1.509 0.875,-2.875 -0.041,-1.0108 -0.32076,-2.0595 -0.8125,-3.125 -0.47812,-1.0791 -1.13944,-2.1063 -2,-3.0625 -0.84694,-0.96982 -1.8174,-1.7818 -2.9375,-2.4375 -1.83045,-1.03813 -3.91415,-1.584 -6.25,-1.625 z m -0.5625,6.96875 c 1.69383,0 2.67009,0.67895 2.875,2.03125 0.0273,0.1093 0.0312,0.24235 0.0312,0.40625 l -5,0 c 0,-0.0819 0.0391,-0.2111 0.0937,-0.375 0.35514,-1.1338 1.00281,-1.8166 2,-2.0625 z m 26.53125,0.96875 c 0.15024,0 0.39089,0.0387 0.71875,0.0937 1.33866,0.3142 2.15455,1.2631 2.46875,2.875 l 0,1.40625 c -0.16394,0.9972 -0.51612,1.74845 -1.0625,2.28125 -0.53276,0.5327 -1.19408,0.81675 -2,0.84375 -0.91523,0 -1.68415,-0.33465 -2.3125,-1.03125 -0.62837,-0.6967 -0.93751,-1.6299 -0.9375,-2.75 0,-0.3142 0.004,-0.51955 0.0312,-0.65625 0.16391,-0.9425 0.53368,-1.7036 1.09375,-2.25 0.56005,-0.5464 1.22137,-0.8125 2,-0.8125 z M 129,151.90625 c 0.40979,0 0.84805,0.0939 1.3125,0.3125 1.07912,0.4917 1.73258,1.43675 1.9375,2.84375 0,0.5601 -0.0352,0.9984 -0.0625,1.3125 -0.041,0.3962 -0.16039,0.80895 -0.40625,1.21875 -0.28688,0.56 -0.69576,0.98075 -1.1875,1.28125 -0.49178,0.2869 -1.01611,0.4375 -1.5625,0.4375 -0.91523,0 -1.66656,-0.3737 -2.28125,-1.125 -0.56007,-0.724 -0.84376,-1.57505 -0.84375,-2.53125 0.0273,-0.1639 0.0312,-0.279 0.0312,-0.375 0.0137,-0.1093 0.0488,-0.2384 0.0625,-0.375 0.16391,-0.9152 0.51609,-1.6411 1.0625,-2.1875 0.54639,-0.5464 1.18619,-0.8125 1.9375,-0.8125 z m 26.40625,0 c 1.1201,0 2.00056,0.3307 2.65625,1 0.65567,0.6694 0.96874,1.6104 0.96875,2.8125 -0.0137,0.6147 -0.1252,1.16445 -0.34375,1.65625 -0.21857,0.4917 -0.52378,0.887 -0.90625,1.1875 -0.36883,0.3005 -0.76799,0.49775 -1.21875,0.59375 -0.27322,0.055 -0.50994,0.0625 -0.6875,0.0625 -0.87426,0 -1.60407,-0.31305 -2.21875,-0.96875 -0.61471,-0.6693 -0.9238,-1.5458 -0.9375,-2.625 0,-0.3278 0.004,-0.6076 0.0312,-0.8125 0.13659,-0.8059 0.4418,-1.4321 0.90625,-1.9375 0.47808,-0.5191 1.06698,-0.84575 1.75,-0.96875 z"
       transform="translate(0,852.36218)"
       id="path3889"
       style="font-size:41.96350861px;font-style:normal;font-variant:normal;font-weight:normal;font-stretch:normal;text-align:center;line-height:125%;letter-spacing:0px;word-spacing:0px;writing-mode:lr-tb;text-anchor:middle;fill:#ffbcb0;fill-opacity:1;stroke:none;font-family:Anja Eliane accent;-inkscape-font-specification:Anja Eliane accent" />
  </g>
</svg>
];
}

sub showgraph {
  my $interval = "month";
  if ($input{graph} eq "yearbyyear") {
    $interval = "year";
  }
  my ($libdir) = getvariable('resched', 'svg_graphs_install_dir');
  if ($libdir) {
    eval {
      do "" . catfile($libdir, "svg_graph.pl");
    };
    if ($@) {
      print include::standardoutput("Error: Code Library Problem",
                                    (include::errordiv("Error loading SVG Graphs library.")),
                                    "Failed to load svg_graphs.pl from $libdir: '$@'.  I cannot create a graph without loading this library, sorry.  Check that the svg_graphs_install_dir variable is correct, and that the example scripts that ship with that library can be run from there, and that the user that I am running as, has read access to there.");
      exit 0;
    } else {
      my ($category, @resid, %stat, %monthsort, %resname, %subcat, @catinfo, @res);
      my @allcategory = include::categories("statgraphcategories");
      my ($cat) = grep { $$_[0] eq $input{category} } @allcategory;
      if ($cat) {
        my $dummy;
        ($dummy, @res) = @$cat;
      } else {
        @res = categoryitems($input{category}, \@allcategory);
      }
      for (grep { my $c = $_;
                  $$c[0] eq $input{category} or
                    (grep { $$c[0] eq $_ } @res)} @allcategory) {
        ($category, @resid) = @$_;
        stat_graph_category_helper($category, \@resid, $interval . "s", \%stat, \%resname, \%monthsort, \%subcat);
      }
      stat_graph_subcategory_helper(\%subcat, \%stat);
      my $ucfield = ucfirst($input{field});
      my @label = sort { $monthsort{$a} <=> $monthsort{$b} } keys %{$stat{$input{category}}{total}};
      if ($input{graph} eq "yearbyyear") { @label = map { /(\d+)/; $1; } @label; }
      my $maxchars = 1;
      for my $l (map { $resname{$_} || $_ } @res) {
        my $chars = length($l);
        # This assumes all chars are roughly the same width, so it's not perfect.
        # If your longest resource name has a tone of Ws in it, or something,
        # it'll go past the edge of the legend box.
        $maxchars = $chars if $chars > $maxchars;
      }
      my $lwidth = 20 + (8 * $maxchars);
      my $imagecontent = svg(linegraph( title    => ucfirst($input{category}) . " " . $ucfield,
                                        xlabels  => [ @label ],
                                        data     => [ map {
                                          my $rid = $_;
                                          my $color = ($rid =~ /^\d+$/) ? rescolor($rid) : categorycolor($rid);
                                          +{ name      => $resname{$rid} || $rid,
                                             color     => $color,
                                             values    => [ map {
                                               my $mon = $_;
                                               $stat{$input{category}}{$rid}{$mon}{$input{field}}
                                             } sort { $monthsort{$a} <=> $monthsort{$b} } keys %{$stat{$input{category}}{total}} ],
                                           }, } @res ],
                                        legendwidth => $lwidth,
                                      ));
      print qq[Content-type: image/svg+xml\n\n] . $imagecontent;
      exit 0;
    }
  } else {
    print qq[Content-type: image/svg+xml\n\n] . svggraphs_not_enabled() . qq[\n<!-- libdir not set -->\n];
    exit 0;
  }
}

sub searchresults {
  my @searchstring;
  my $canon = include::dealias(include::normalisebookedfor($input{search}));
  push @searchstring, $canon;
  push @searchstring, map { $$_{alias} } findrecord('resched_alias', 'canon', $canon);
  my @result = map { searchrecord('resched_bookings', 'bookedfor', $_) } @searchstring;
  if (not @result) {
    push @result, map { searchrecord('resched_bookings', 'notes', $input{search}) } @searchstring;
  }
  if (not @result) {
    print include::standardoutput("Not Found:  " . encode_entities($input{search}),
                                  include::errordiv('No Bookings Found',
                                           qq[Sorry, but I couldn't find any
                                              bookings where the string <q>$input{search}</q> matched
                                              either in the party it was booked for or in the notes.]),
                                  $ab, $input{usestyle});
    return;
  }
  # So if we get here, we have results in @result:
  my $cutoffmonths = getvariable('resched', 'privacy_cutoff_old_searches');
  $cutoffmonths = 24 if not defined $cutoffmonths;
  if ($cutoffmonths > 0) {
    my $cutoff = DateTime->now(time_zone => $include::localtimezone)->clone()->subtract( months => $cutoffmonths );
    @result = grep { $$_{fromtime} ge $cutoff } @result;
  }
  if (not @result) {
    print include::standardoutput("Not Found:  " . encode_entities($input{search}),
                                  include::errordiv('No Recent Bookings Found',
                                           qq[Sorry, but I couldn't find any
                                              bookings during the last $cutoffmonths months
                                              where the string <q>$input{search}</q> matched.]),
                                  $ab, $input{usestyle});
    return;
  }
  # So if we get here, we have non-expiered results in @result:
  return qq[<table class="searchresults"><thead>
              <tr><th>Booking</th><th>Resource</th><th>Date &amp; Time</th><th>Notes</th><th>Booked By</th></tr>
          </thead><tbody>\n].(join "\n                ", map {
            my %r = %{getrecord('resched_resources', $$_{resource})};
            my $al = (include::isalias(include::normalisebookedfor($$_{bookedfor})))
              ? qq[<div><cite>(alias for <span class="nobr">] . (
                                                    #join ' ', map { ucfirst lc $_ } split /\s+/,
                                                    #include::dealias(include::normalisebookedfor($$_{bookedfor}))
                                                    include::capitalise(include::dealias(include::normalisebookedfor($$_{bookedfor})))
                                                   ). '</span>)</cite></div>'
                                                     : '';
            my $dt = DateTime::From::MySQL($$_{fromtime});
            qq[<tr><td class="res$$_{resource}"><a href="./?$persistentvars&amp;booking=$$_{id}">$$_{bookedfor}</a>$al</td>
                 <td class="res$$_{resource}">].(encode_entities($r{name})).qq[</td>
                 <td class="res$$_{resource}">].($dt->ymd . " " . $dt->hms).qq[</td>
                 <td class="res$$_{resource}">].(encode_entities($r{notes})).qq[</td>
                 <td class="res$$_{resource}">].(getrecord('users', $$_{bookedby})->{nickname})."</td>
             </tr>"
               } reverse @result)."\n</tbody></table>";
}

sub extendbooking {
  # User wants to extend a booking.
  my %booking = %{getrecord('resched_bookings', $input{extend})};
  my %fupchain;
  while ($booking{isfollowup}) {
    $fupchain{$booking{id}} = 1;
    $fupchain{$booking{isfollowup}} = 1;
    %booking = %{getrecord('resched_bookings', $booking{isfollowup})};
  }
  my %resource = %{getrecord('resched_resources', $booking{resource})};
  $resource{id} or warn "Improper resource: ($booking{resource}, from booking $booking{id}) " . Dumper(\%resource);
  my %schedule = %{getrecord('resched_schedules', $resource{schedule})};
  my $when = DateTime::From::MySQL($booking{fromtime});
  my $until = DateTime::From::MySQL($booking{until});
  my $newuntil = $until->clone()->add( minutes => $schedule{durationmins} );
  my @collision;
  while (($newuntil > $until) and
         (@collision = grep {
           (not $fupchain{$$_{id}} and not $$_{id} eq $booking{id})
         } include::check_for_collision_using_datetimes($resource{id}, $when, $newuntil))) {
    $newuntil = $newuntil->subtract(minutes => $schedule{intervalmins});
  }
  my $view = join ",", parseshowwith($resource{showwith}, $resource{id});
  # Kludge input so that the results actually get displayed:
  $input{view} ||= $view;
  $input{year} ||= $when->year(); $input{month} ||= $when->month(); $input{mday} ||= $when->mday();
  if (($newuntil->mday ne $until->mday)
      and (not getvariable('resched', 'allow_extend_past_midnight'))) {
    return include::errordiv('Cannot Extend Past Midnight',
                             qq[Extending the booking past midnight into a new day is not supported.  Please see the recurring booking options if what you really want is to book the same resource at the same time on multiple days.],
                            ),
                              undef; # No redirect in this case.
  }
  elsif (($newuntil->mday ne $until->mday)
      and (getvariable('resched', 'confirm_extend_past_midnight'))
      and not ($input{confirm} =~ /pastmidnight/)) {
    return include::confirmdiv('Extend Past Midnight?',
                               qq[<div class="p">Did you really intend to extend this booking past midnight into a new day?</div>
                                  <div class="p">
                                     <a class="button" href="./?confirm=pastmidnight&amp;$persistentvars&amp;extend=$input{extend}&amp;currentend=$input{currentend}">Confirm: Extend Past Midnight</a>
                                     <a class="button" href="./?$persistentvars&amp;view=$view&amp;year=].$when->year().qq[&amp;month=].$when->month().qq[&amp;mday=].$when->mday().qq[">Wait, what?</a>
                                  </div>]),
                                 undef; # No redirect in this case.
  } else {
    if ($newuntil > $until) {
      $booking{until} = DateTime::Format::MySQL->format_datetime($newuntil);
      updaterecord('resched_bookings', \%booking);
      return qq[<div class="info">The booking has been extended.</div>],
        redirect_header(\%resource, $when, 30);
    } else {
      # No Can Do.
      return include::errordiv('Booking Conflict', qq[Booking #$booking{id} cannot be extended, due to the following scheduling conflict(s) for the $resource{name}.<ul>
      ] .(join "\n", map { "<li>$$_{id} ($$_{bookedfor}) from $$_{fromtime} until $$_{until}</li>" } @collision). "</ul>  Sorry!"),
        undef; # No redirect in this instance
    }
}
}

sub daysclosedform {
  my $now = DateTime->now(time_zone => $include::localtimezone);
  #my @prefill;
  #if ($now->month < 3) {
  #  push @prefill, []
  #}
  my $nowyear = $now->year;
  ++$nowyear if $now->month > 10;
  my $dateinputs = join "\n  ", map {
    qq[<div><input type="text" name="year$_" size="5" value="$nowyear" />
       <select name="month$_">
           <option value="1">Jan</option> <option value="2">Feb</option> <option value="3">Mar</option> <option value="4">Apr</option>
           <option value="5">May</option> <option value="6">Jun</option> <option value="7">Jul</option> <option value="8">Aug</option>
           <option value="9">Sep</option><option value="10">Oct</option><option value="11">Nov</option><option value="12">Dec</option>
         </select>
       <input type="text" name="mday$_" size="3" value="] . ( ($_ == 1) ? '1' : '' ) . qq[" />
     </div>]
  } (1 .. ($input{batch} || 1));
  my $psvars = persist('hidden', ['magicdate']);
  return <<"DAYSCLOSEDFORM";
<form action="index.cgi" method="post">
  $psvars
  <input type="hidden" name="action" value="daysclosed" />
  <input type="hidden" name="bookedfor" value="CLOSED" />
  <div>Mark <em>all resources</em> unavailable
       <em>all day long</em> on the following date, since we will be closed:</div>
  $dateinputs
  <br />
  <span class="nobr">Staff Initials: <input type="text" name="staffinitials" size="5" value="$user{initials}" /></span>
  <div>Reason for Closing: <input type="text" name="notes" /></div>
  <br />
  <input type="submit" value="Book Us Closed" />
</form>
DAYSCLOSEDFORM
}

sub frequserform {
  my ($now, $soy);
  my $errors = "";
  if ($input{endyear} and $input{endmonth} and $input{endmday}) {
    eval {
      $now = DateTime->new(
                           year  => $input{endyear},
                           month => $input{endmonth},
                           day   => $input{endmday},
                          );
    }; $errors .= dterrormsg($input{endyear}, $input{endmonth}, $input{endmday}, undef, undef,
                             qq[ (for the <q>now</q> date)]) if $@;
  } else {
    eval {
      $now = DateTime->now(time_zone => $include::localtimezone);
    }; $errors .= errordiv("Date/Time Error", "DateTime choked trying to get the current date/time for the <q>$include::localtimezone</q> time zone.") if $@;
  }
  if ($input{startyear} and $input{startmonth} and $input{startmday}) {
    eval {
      $soy = DateTime->new(
                           year  => $input{startyear},
                           month => $input{startmonth},
                           day   => $input{startmday},
                          );
    }; $errors .= dterrormsg($input{startyear}, $input{startmonth}, $input{startmday}, undef, undef,
                             qq[ (for the start-of-year date)]) if $@;
  } else {
    my $year;
    eval {
      $year = DateTime->now(time_zone => $include::localtimezone)->year();
    }; $errors .= errordiv("Date/Time Error", qq[DateTime choked on the <q>$include::localtimezone</q> time zone, when trying to get the current year]) if $@;
    eval {
      $soy = DateTime->new(  year  => $year,
                             month => 1,
                             day   => 1,  );
    }; $errors .= dterrormsg($year, 1, 1, undef, undef,
                             qq[ (for the start-of-year date)]) if $@;
  }
  my $monthoptionsoy = join "\n", map {
    # DateTime cannot choke here because all values are hardcoded (months go from 1 .. 12).
    my $dt = DateTime->new( year  => 1970,
                            month => $_,
                            day   => 1);
    my $abbr = $dt->month_abbr;
    my $selected = ($_ == $soy->month) ? ' selected="selected"' : '';
    qq[<option value="$_"$selected>$abbr</option>];
  } 1..12;
  my $monthoptionnow = join "\n", map {
    # DateTime cannot choke here because all values are hardcoded (months go from 1 .. 12).
    my $dt = DateTime->new( year  => 1970,
                            month => $_,
                            day   => 1);
    my $abbr = $dt->month_abbr;
    my $selected = ($_ == $now->month) ? ' selected="selected"' : '';
    qq[<option value="$_"$selected>$abbr</option>];
  } 1..12;
  $input{frequser} ||= 10;
  my $resourceoptions = join "\n              ", map {
    my @r = @$_;
    my $catname = shift @r;
    my $reslist = join ',', @r;
    qq[<option value="$reslist">$catname</option>]
  } include::categories();
  return $errors . qq[<form action="index.cgi" method="post">
       <div><span class="nobr">Look up users who used</span>
            <select name="resource">
              <option value="" selected="selected">anything</option>
              $resourceoptions
           </select>
           <span class="nobr">at least <input type="text" size="5" name="frequser" value="$input{frequser}" /> times</span>
       </div>
       <div><span class="nobr">from <input type="text" size="5" name="startyear" value="] . $soy->year . qq[" />
                       <select name="startmonth">$monthoptionsoy</select>
                       <input type="text" name="startmday" size="3" value="1" />
            </span>
            <span class="nobr">through <input type="text" size="5" name="endyear" value="] . $now->year . qq[" />
                          <select name="endmonth">$monthoptionnow</select>
                          <input type="text" name="endmday" size="3" value="] . $now->mday . qq[" />
            </span>
       </div>
       ].persist('hidden', ['category', 'magicdate']).qq[
       <input type="submit" value="Look 'em up!" />
    </form>];
}

sub sgorpl {
  my ($qtty, $unit, $plunit) = @_;
  # Appends a singular or plural unit label, as appropriate, to a number.
  if ($qtty == 1) { return "$qtty $unit"; }
  $plunit ||= $unit . 's';
  return "$qtty $plunit";
}
sub human_readable_duration {
  my ($dur) = @_; # This is expected to be a DateTime::Duration object.
  if ($dur->in_units('years')) { return sgorpl($dur->in_units('years'), 'year') }
  if ($dur->in_units('months')) { return sgorpl($dur->in_units('months'), 'month') }
  if ($dur->in_units('weeks')) { return sgorpl($dur->in_units('weeks'), 'week') }
  return sgorpl($dur->in_units('days'), 'day');
}


sub last_mday_of_month {
  # This has no place to put an error message, so the caller must wrap
  # it in eval{} in case DateTime chokes on the inputs.
  my %arg = @_;
  my $dt;
  if ($arg{datetime}) {
    $dt = $arg{datetime};
  } elsif ($arg{year} and $arg{month}) {
    $dt = DateTime->new(
                        year  => $arg{year},
                        month => $arg{month},
                        day   => 1,
                       );
  } else {
    use Carp;
    confess "last_mday_of_month called without valid arguments";
  }
  my $ldom = $dt->clone()->set(day => 1)->add(months => 1)->subtract(days => 1);
  return $ldom->mday();
}

sub isroom {
  my ($resourceid) = @_;
  my $res = getrecord('resched_resources', $resourceid);
  return $resourceid if $$res{flags} =~ /R/;
}

sub redirect_header {
  my ($r, $when, $seconds) = @_;
  return unless ref $when;
  return if $input{recur};
  $seconds ||= getvariable('resched', 'redirect_seconds') || 15;
  my $uri = select_redirect($r, $when);
  return qq[<meta http-equiv="refresh" content="$seconds; URL=$uri" />];
}
sub select_redirect {
  my ($r, $when) = @_;
  return unless ref $when;
  confess "select_redirect called with invalid resource" unless ref $r;
  my @r = parseshowwith($$r{showwith}, $$r{id});
  my $now = DateTime->now(time_zone => $include::localtimezone);
  my $uri = getvariable('resched', 'url_base') . "?view="
    . (join ",", @r)
    . (($when->mday == $now->mday and $when->month == $now->month and $when->year == $now->year)
      ? "&amp;magicdate=today"
      : "&amp;year=" . $when->year . "&amp;month=" . $when->month  . "&amp;mday=" . $when->mday
      )
    . "&amp;" . persist(undef, ['magicdate']);
  $uri =~ s/resched/resched-dev/ if $0 =~ /resched-dev/;
   # Some sites (such as Galion) might have a test installation of a
   # development version, running on the same server, using the same
   # database as a production installation.  If the production release
   # is in a folder called resched, and the dev release is in a folder
   # called resched-dev within the same parent, this makes it work.
   # (Err, except for the baseurl in ajax.js, which for now must be
   # separately adjusted.)
  return $uri;
}
sub updates_uri {
  my ($res, $when) = @_;
  my @r = @$res;
  return unless ref $when;
  my $pv = persist(undef, ['category', 'magicdate']);
  $pv = s/&amp;/&/g;
  my $now = DateTime->now(time_zone => $include::localtimezone);
  my $uri = getvariable('resched', 'url_base') . "?view="
    . (join ",", @r)
    . (($when->mday == $now->mday and $when->month == $now->month and $when->year == $now->year)
      ? "&magicdate=today"
      : "&year=" . $when->year . "&month=" . $when->month  . "&mday=" . $when->mday
      )
    . "&" . $pv;
  $uri =~ s/resched/resched-dev/ if $0 =~ /resched-dev/; # See above comment on similar substitution.
  return $uri;
}


sub nextrecur {
  # Takes a DateTime object, and returns another DateTime object which
  # tells when the _next_ recurrance will be, based on $input{recur},
  # $input{recurstyle}, and so on and so forth.
  my ($prev) = @_;
  if ($input{recur} eq 'daily') {
    my $dt = $prev->clone()->add(days => 1);     return $dt;
  } elsif ($input{recur} eq 'weekly') {
    my $dt = $prev->clone()->add(weeks => 1);    return $dt;
  } elsif ($input{recur} eq 'monthly') {
    my $dt = $prev->clone()->add(months => 1);   return $dt;
  } elsif ($input{recur} eq 'quarterly') {
    my $dt = $prev->clone()->add(months => 3);   return $dt;
  } elsif ($input{recur} eq 'listed') {
    die "Can't Happen:  nextrecur is not supposed to be called for listed dates.";
  } elsif ($input{recur} eq 'nthdow' or $input{recur} eq 'quarterlynthdow') {
    my $ow = DateTime::From::MySQL($input{when});
    my $dt = $prev->clone();  $dt->set(day => 1);
    $dt->add(months => (($input{recur} eq 'quarterlynthdow') ? 3 : 1));
    my $stayinthismonth = $dt->month; # Sanity check for situations
                                      # where there _is_ no fifth
                                      # thursday, or whatever, to
                                      # prevent infinite loops.
    #$dt = DateTime->new(
    #                    year   => $dt->year,
    #                    month  => $dt->month,
    #                    day    => 1,
    #                    hour   => $dt->hour,
    #                    minute => $dt->minute,
    #                   );
    while (($dt->month == $stayinthismonth)
           and ((nonstandard_week_of_month($dt) != nonstandard_week_of_month($ow))
                or ($dt->dow != $ow->dow))) {
      if ($dt->dow == $ow->dow) {
        $dt->add(days => 7);
      } else {
        $dt->add(days => 1); # Not maximally efficient, but O(n) is limited.
      }
    }
    if ((nonstandard_week_of_month($dt) == nonstandard_week_of_month($ow)) and ($dt->dow == $ow->dow)) {
      return $dt;
    }
    # There's no correct answer, because the user has asked for
    # something that doesn't exist, such as the first Tuesday of a
    # month that starts on Wednesday, or the fifth Friday of a month
    # that starts on Monday.  So, what to return?  $dt is junk.  What
    # we'll do is temporarily modify %input to request a different
    # week of the month and recurse.  This will give us the right day
    # of the week in the right month, but a slightly wrong week of the
    # month this month.  We'll also push a warning onto @warn.
    { local %input = %input; my $oldwhen = $input{when}; $|++;
      warn "User asked for non-extant nthdow: " . ordinalnumber(nonstandard_week_of_month($ow)) . ' ' . $ow->day_name . ".  Attempting to compensate.";
      my $w = $ow->clone();
      if (nonstandard_week_of_month($w) < 2) {
        # Maybe we'll succeed in the _following_ week:
        $w = $w->add(weeks=>1);
      } elsif (nonstandard_week_of_month($w)>3) {
        # Maybe we'll succeed in the _previous_ week:
        $w = $w->subtract(weeks=>1);
      } else {
        # This can only happen under fantastically unusual
        # circumstances, e.g., if a change to the Earth/Sun motion
        # creates the need for a calendar correction.
        die "Wicked strange calendar condition: There is no ".(ordinalnumber(nonstandard_week_of_month($ow)))."
                       ".($prev->day_name)." in ".($prev->clone()->add(months=>1)->month_name)."
                       of ".($ow->year).".";
      }
      $input{when} = DateTime::Format::ForDB($w);
      push @warn, "<li>There is, according to our nonstandard definition,
                       no ".(ordinalnumber(nonstandard_week_of_month($ow)))."
                       ".($prev->day_name)." in ".($prev->clone()->add(months=>1)->month_name)."
                       of ".($ow->year).".  Trying for
                       the ".(ordinalnumber(nonstandard_week_of_month($w)))."
                       ".($prev->day_name).".</li>";
      #use Data::Dumper; warn "Returning: " . Dumper(+{answer => $answer});
      my $answer = nextrecur($prev); $input{when} = $oldwhen; return $answer;
    }
  }
}

sub nonstandard_week_of_month {
  # The week_of_month function provided by the DateTime module is
  # based on the ICU definition of 'week of month', wherein the first
  # week of the month is the first week that contains a Thursday in
  # that month, correlating with the ISO8601 definition of what
  # constitutes the first week of the year.  (If the first week of a
  # month were defined differently, then you could have a week that is
  # in year A but the month containing it might be in year A+1 or A-1,
  # which would be exceedingly bizarre.)

  # That however is all quite irrelevant to us: when we want to know
  # whether a day is the nth somethingday of the month, what we're
  # really asking is whether, of the days in the month that are
  # somethingdays, this day is chronologically the nth one.  For this
  # we define our own custom function, which will work by counting
  # somethingdays, going backwards seven days at a time, until it hits
  # one that's not in the right month anymore.
  my ($dt) = @_;
  $dt = $dt->clone();
  my $month = $dt->month;
  my $answer;
  while ($month == $dt->month) {
    ++$answer;
    $dt = $dt->subtract(days => 7);
  }
  return $answer;
}


sub attemptbooking {
  my ($resource, $schedule, $when) = @_; # Two hashrefs and a DateTime object, respectively.
  croak "attemptbooking(): schedule is not a reference: $schedule" if not ref $schedule;
  my %sch = %$schedule;
  croak "attemptbooking(): resource is not a reference: $resource" if not ref $resource;
  my %res = %$resource;
  my %closedwday = map { $_ => 1 } split /,\s*/, getvariable('resched', 'daysclosed');
  my $until; {
    if ($sch{durationlock}) {
      $until = $when->clone()->add( minutes => $sch{durationmins} );
    } else {
      my ($hour, $min);
      if ($input{untiltime}) {
        ($hour, $min) = ($input{untiltime} =~ /(\d+)[:](\d+)/);
        # This option is now used by the AJAX interface.
      } elsif ($input{untilhour}) {
        # This is the option used by the traditional CGI interface.
        ($hour, $min) = @input{qw(untilhour untilmin)}; # This is for the new, better UI form.
      }
      if ($hour) {
        eval {
          $until = DateTime->new(
                                 time_zone => $include::localtimezone,
                                 year      => $when->year,
                                 month     => $when->month,
                                 day       => $when->mday,
                                 hour      => $hour,
                                 minute    => ($min || 0),
                                );
        }; return dterrormsg($when->year, $when->month, $when->mday, $hour, ($min || 0),
                             qq[( for the <q>booked until</q> time)]) if $@;
      } else {
        # It wasn't specified, so default to a timeslot durationmins long:
        $until = $when->clone()->add( minutes => $sch{durationmins});
      }
    }}
  if ($until < $when) {
    return  include::errordiv('Unauthorized Time Travel Attempt',
                     qq[The Time Police have intercepted your attempt to travel
                        backward in time from $when to $until and aborted it, and
                        your identity has been recorded in the temporal logs.
                        If you have a valid time travel permit, please fill
                        out form 709284750, section T, subsection 17, part C,
                        have it notarized in triplicate, and submit it to your
                        local Temporal Affairs office in order to have your
                        operation reinstated.  Remember, only you can prevent
                        the entire space-time continuum from collapsing.]);
  }
  my $timewewant = DateTime::Span->from_datetimes(start => $when, before => $until);
  my @collision = include::check_for_collision_using_datetimes($res{id}, $when, $until);
  if (@collision) {
    return join "\n", map {
      #my %extant = %{$collision[0]};
      my %extant = %$_;
      my $inits = ($extant{staffinitials} ? " [$extant{staffinitials}]" : '');
      my %bookedby = %{getrecord('users', $extant{bookedby})};
      include::errordiv('Booking Conflict',
               qq[$res{name} is already booked for
                  $extant{bookedfor} (booked by $bookedby{nickname}$inits)
                  from $extant{fromtime} until $extant{until}.
                  (<a href="./?booking=$extant{id}&amp;$persistentvars">View
                  or edit the existing booking.</a>)]);
    } @collision;
  } elsif ($closedwday{$when->dow}) {
    return include::errordiv('Booking Conflict', 'The '.ordinalnumber($when->mday)." of ".$when->month_name."
            falls on a ".($when->day_name)." in ".$when->year.".  $res{name} not booked.");
  } elsif ($res{requireinitials} and not ($input{staffinitials} ||= $user{initials})) {
    return include::errordiv('Initials Required', qq[Staff initials are required to book this resource.
            Please go back and fill in your initials.  Thanks.]);
  } elsif ($res{requirenotes} and not $input{notes}) {
    return include::errordiv('Notes Required', qq[Notes are required to book this resource.  Please
             go back and fill in contact information and any other relevant notes.  Thanks.]);
  } elsif ($input{latestart} and (
                                  (not $input{latehour})
                                  or (not $input{lateminute})
                                 )) {
    return include::errordiv('Information Missing', qq[You said they started late, but you didn't say when.  Please fill out both the hour and minute fields.]);
  } else {
    my $fromtime = DateTime::Format::ForDB($when);
    my $bookedfor = encode_entities(include::dealias(include::normalisebookedfor($input{bookedfor})));
    my %booking = (
                   resource   => $res{id},
                   bookedfor  => $bookedfor,
                   bookedby   => $auth::user,
                   fromtime   => $fromtime,
                   until      => DateTime::Format::ForDB($until),
                   notes      => encode_entities($input{notes}),
                   (($input{staffinitials} || $user{initials}) ? (staffinitials => ($input{staffinitials} || $user{initials})) : ()),
#                   notes      => (((lc $bookedfor) ne (lc $input{bookedfor}))
#                                  ? ( $input{notes}
#                                      ? encode_entities($input{notes}) . "\n(" . encode_entities($input{bookedfor}) . ")"
#                                      : "($input{bookedfor})"
#                                    )
#                                  : (encode_entities($input{notes}))),
                  );
    if ($didyoumean_enabled) {
      my $name = include::normalisebookedfor($input{bookedfor});
      if (include::isalias($name) and not $name =~ /guest/i) {
        $name = include::capitalise(include::dealias($name));
        $booking{bookedfor} = encode_entities($name);
        if ((lc $booking{bookedfor}) ne (lc $input{bookedfor})) {
          $booking{notes} = ($booking{notes} ? ($booking{notes} . "\n") : '')
            . encode_entities("($input{bookedfor})");
        }
      }
    }
    if ($input{latestart}) {
      my $late;
      eval {
        $late = DateTime->new(
                              time_zone => $include::localtimezone,
                              year      => $when->year,
                              month     => $when->month,
                              day       => $when->day,
                              hour      => $input{latehour},
                              minute    => $input{lateminute},
                             );
      }; return dterrormsg($when->year, $when->month, $when->day, $input{latehour}, $input{lateminute},
                           qq[ (for the late start time)]) if $@;
      if (($when->hour >= 12)
          and ($late->hour < 12)) {
        $late = $late->add( hours => 12 );
      }
      $booking{latestart} = DateTime::Format::ForDB($late);
    } elsif ($input{waslatestart}) {
      $booking{latestart} = undef;
    } elsif ($input{dynamicform} and getvariable('resched', 'automatic_late_start_time')) {
      # Do implicit late start if AND ONLY IF we are making the booking during the timeslot.
      my $now = DateTime->now(time_zone => $include::localtimezone);
      if (($now >= $when) and ($now <= $until)) {
        my $late;
        eval {
          # This can choke e.g. if the booking is during a DST forward
          # clock change, and the current day has no such change.  It
          # would be kinda rare, for someone to be editing bookings
          # during the wee hours of the morning, for another date, but
          # it is possible in principle.
          $late = DateTime->new(
                                time_zone => $include::localtimezone,
                                year      => $when->year,
                                month     => $when->month,
                                day       => $when->day,
                                hour      => $now->hour,
                                minute    => $now->minute,
                               );
        }; return dterrormsg($when->year, $when->month, $when->day, $now->hour, $now->minute) if $@;
        $booking{latestart} = DateTime::Format::ForDB($late);
      }
    }
    my $result = addrecord('resched_bookings',\%booking);

    my $ftime = include::datewithtwelvehourtime(DateTime::From::MySQL($booking{fromtime}));
    my $answer = qq[<div class="info">The $res{name} has been booked for <q>$booking{bookedfor}</q> for the $ftime timeslot.
                 You may <a href="./?booking=$db::added_record_id&amp;$persistentvars">view the booking</a> if you like.
            </div>];
    if ($didyoumean_enabled) {
      my $name = include::normalisebookedfor($input{bookedfor});
      if ($name =~ /^\s*\w+\s*$/ and not ($name =~ /maintenance|visitor|guest|patron|staff|testing|CLOSED/i)) {
        # Extreme laziness: only a single word has been entered (e.g.,
        # only a first name, only a last name, or cetera). I am sorely
        # tempted to just reject these outright, but for the time
        # being we'll present multiple choice...
        #   As for the exceptions:
        #   * 'maintenance' is used when I need to keep the system free so I can do maintenance on it; there is nothing more to say.
        #   * 'testing', similarly, is not a real patron but is used for test bookings mainly in the practice zone.
        #   * 'patron', 'visitor', and 'guest' are either deliberately vague or represent a genuine lack of knowledge, not just being too lazy to type the rest of the name.
        #   * 'staff' implies it's being used for library purposes, so not available for patrons
        #   * 'CLOSED' has obvious special meaning.
        my %result;
        for my $res (map { $$_{bookedfor} } searchrecord('resched_bookings', 'bookedfor', $name)) {
          $result{$res}++;
        }
        if (keys %result) {
          $didyoumean_invoked++;
          $answer = include::errordiv('Did You Mean', qq[<ul>
               ] . (join "\n", (map {
                      qq[               <li><a href="index.cgi?persistentvars&amp;action=didyoumean&amp;booking=$db::added_record_id&amp;bookedfor=$_">$_</a></li>]
                    } sort {
                        $result{$b} <=> $result{$a}
                    } grep {
                      lc $_ ne lc $name
                    } include::uniq(map {
                      #join " ", map { ucfirst lc $_ } split /\W+/, include::dealias(include::normalisebookedfor($_))
                      include::capitalise(include::dealias(include::normalisebookedfor($_)))
                    } keys %result))) . qq[
               <li>Other:
                   <form action="index.cgi" method="post">
                      <input type="hidden" name="action" value="didyoumean" />
                      <input type="hidden" name="booking" value="$db::added_record_id" />
                      $hiddenpersist
                      <input type="hidden" name="freeform" value="yes" />
                      <input type="text" name="bookedfor" value="$name" />
                      <input type="submit" value="Change It" />
                   </form></li>
            </ul>]);
        } else {
          # TODO: There are no suggestions.  Should we just bug the
          # user for more info?  Maybe later.
        }
      }
    }

    return $answer;
    # ****************************************************************************************************************
  }
}

sub updatealias {
  my $id = $input{aliasid};
  my $arec = getrecord('resched_alias', $id);
  if (ref $arec) {
    $$arec{alias} = include::normalisebookedfor($input{alias});
    $$arec{canon} = include::normalisebookedfor($input{canon});
    if (not sanitycheckalias($arec)) {
      return (include::errordiv('Programming Error (Bug)',
                                qq[CAN'T HAPPEN: The subroutine sanitycheckalias cannot return false, but it did.
                     Find the programmer and give him what for.]), 'PROGRAMMING ERROR');
    } else {
      # Sanity checks passed: actually make the change.
      my (@changes) = @{updaterecord('resched_alias', $arec)};
      if (@changes) {
        return (qq[The alias has been updated.  Technical details: <pre>]
                . (Dumper(+{changes => \@changes})) . qq[</pre>], "Alias Updated");
      } else {
        return (qq[<div class="warning">Nothing was changed!</div>], "No Changes");
      }
    }
  } else {
    return (include::errordiv('Error - Missing Alias', qq[Sorry, but I couldn't find alias #$id.]),
            "Alias Not Found: $id");
  }
  return (include::errordiv('Programming Error (Bug)', qq[There is a fallthrough condition in the updatealias subroutine.]),
          'PROGRAMMING ERROR');
}

sub overview_get_day_bookings {
  my ($day, @r) = @_;
  my $end = $day->clone()->set( hour => 23 );
  my $db = dbconn();
  my $q = $db->prepare('SELECT * FROM resched_bookings WHERE resource IN ( ' . (join ",", @r) . ' ) AND fromtime > ? AND until < ? ');
  $q->execute( DateTime::Format::MySQL->format_datetime($day),
               DateTime::Format::MySQL->format_datetime($end)
             );
  my ($booking, @b);
  while ($booking = $q->fetchrow_hashref) {
    push @b, $booking;
  }
  return sort { $$a{fromtime} cmp $$b{fromtime} or $$a{until} cmp $$b{until} or $$a{resource} <=> $$b{resource} } @b;
}

sub get_timerange_bookings {
  my ($res, $mindt, $maxdt) = @_;
  my $db = dbconn();
  my $q = $db->prepare("SELECT * FROM resched_bookings WHERE resource=? AND until>=? and fromtime<=?");
  $q->execute($res, $mindt, $maxdt);
  my @r;
  while (my $r = $q->fetchrow_hashref) {
    push @r, $r;
  }
  return @r;
}

sub getcategoryfromitem {
  my ($r) = @_; # $r can be either a record (in hashref form) or just the number from the id field.
  # No attempt is made to return multiple categories.  You get the first match.
  my $resid;
  if (ref $r) {
    $resid = $$r{id};
  } elsif ($r =~ /^\d+$/) {
    $resid = $r;
  } else {
    confess "getcategoryfromitem called with invalid resource: $r";
  }
  for my $c (include::categories()) {
    my ($name, @id) = @$c;
    my @match = grep { $_ eq $resid } @id;
    if (scalar @match) {
      if (wantarray) {
        return ($name, @id);
      } else {
        return $name;
      }}}
}

sub parseshowwith {
  my ($sw, $r) = @_; # That's (showwith, id) for a resource we were just working with.
  my @category = include::categories();
  my %category = map { my @x = @$_; my $name = shift @x; ($name, [categoryitems($name, \@category)]) } @category;
  if ($category{$sw}) {
    my @r = @{$category{$sw}};
    my %included = map { $_ => 1 } @r;
    if ($included{$r}) {
      return @r;
    } else {
      push @r, $r if not $included{$r};
      return sort { $a <=> $b } @r;
    }
  } elsif ($sw =~ /\d/) {
    return sort { $a <=> $b } ($r, (split /,/, $sw));
  } else {
    my $c = getcategoryfromitem($r);
    return @{$category{$c}} if ref $category{$c};
    return ($r);
  }
}

sub parseswitchwith {
  my ($sw, $r) = @_; # That's (switchwith, id) for a resource we were just working with.
  #warn "parseswitchwith('$sw', $r)\n";
  my @category = include::categories();
  my %category = map { my @x = @$_; my $name = shift @x; ($name, [categoryitems($name, \@category)]) } @category;
  if ($category{$sw}) {
    #use Data::Dumper; warn Dumper($category{$sw});
    return grep { $_ ne $r } @{$category{$sw}};
  } elsif ($sw =~ /\d/) {
    #warn Dumper('split-on-comma');
    return split /,/, $sw;
  } else {
    warn "Failed to parse sw: '$sw'" if $sw; # Don't warn for the empty string.
    my $c = getcategoryfromitem($r);
    if (ref $category{$c}) {
      return grep { $_ ne $r } @{$category{$c}};
    }}
  return;
}

sub usersidebar {
  my $now = DateTime->now(time_zone => $include::localtimezone);
  my ($istoday) = 1; # Default to today.  This get changed if we look at any other day.
  my $oneweek  = join ",", map { DateTime->now(time_zone => $include::localtimezone)->add(days=>$_)->mday() } 0..6;
  my $twoweeks = join ",", map { DateTime->now(time_zone => $include::localtimezone)->add(days=>$_)->mday() } 0..13;
  #my $net = "15,16,17,3"; my $wp = "4,5,6";
  my $prevnext = '';
  my %alwaysclosed = map { $_ => 1 } daysclosed(0);
  if ($input{mday}) {
    # The "next day(s)" link is complicated by the fact that we may
    # currently be displaying multiple days.  What we want to do is
    # display the same number of days, starting with the first day
    # after the last one we are currently displaying.  This may mean
    # wrapping around a month boundary.

    # One thing we do NOT intend to handle is the situation where the
    # user has hand-crafted a list of non-contiguous days (e.g., every
    # Monday in January) and wants to go to the "next" set according
    # to the same pattern (e.g., every Monday in February).  Figuring
    # out the user's precise intention in such cases requires a kind
    # of AI that I don't know how to write.  Rather than spew errors,
    # though, we'll just naively give them the "next" n days starting
    # the day after the last day they were looking at.
    my $numofdays = scalar @dt;
    if ($numofdays == 1) {
      my $thisday = $dt[0];
      my $today = DateTime->now(time_zone => $include::localtimezone);
      $istoday = ($today->year == $thisday->year and $today->month == $thisday->month and $today->mday == $thisday->mday);
      my @daylink;
      for my $offset (-2 .. 3) {
        if ($offset == 0) {
          push @daylink, ($istoday ? 'Today' : 'This Day');
        } else {
          my $linkday = $thisday->clone()->add( days => $offset );
          my $ordnum = ordinalnumber($linkday->mday);
          $ordnum =~ s!(st|nd|rd|th)!<sup>$1</sup>!;
          my $linktext = $linkday->day_abbr . " " . $ordnum;
          $linktext = ($istoday ? 'Yesterday' : 'Previous') if $offset == -1;
          $linktext = ($istoday ? 'Tomorrow' : 'Next') if $offset == 1;
          my $year = $linkday->year; my $month = $linkday->month(); my $mday = $linkday->mday;
          push @daylink, qq[<a href="./?view=$input{view}&amp;year=$year&amp;month=$month&amp;mday=$mday&amp;] . persist(undef, ['magicdate']) . qq[">$linktext</a>]
            unless $linkday->wday == 7;
        }
      }
      $prevnext = join ", ", @daylink;
      $prevnext = qq[<div style="font-size: smaller;">Days:  $prevnext</div>];
    } elsif ($numofdays) {
      my $prevday = $dt[-1];
      my @day; for (1..$numofdays) {
        my $nextday = $prevday->clone()->add(days=>1);
        while ($alwaysclosed{$nextday->dow() % 7}) { $nextday = $nextday->clone()->add(days=>1) } # Skip Sundays.
        push @day, $nextday->clone(); $prevday = $nextday->clone();
      }
      my $year = $day[0]->year(); my $month = $day[0]->month();
      my $mday = join ",", map { $_->mday() } @day;
      my $next = qq[<span class="nobr"><a href="./?view=$input{view}&amp;year=$year&amp;month=$month&amp;mday=$mday&amp;].persist(undef, ['magicdate']).'">Next '.(($numofdays>1)?"$numofdays days":"day")."</a></span>";
      my $subday = $dt[0];
      @day = (); for (1..$numofdays) {
        my $prevday = $subday->clone()->subtract(days=>1);
        while ($alwaysclosed{$prevday->dow() % 7}) { $prevday = $prevday->clone()->subtract(days=>1) } # Skip Sundays.
        unshift @day, $prevday->clone(); $subday = $prevday->clone();
      }
      my $year = $day[0]->year(); my $month = $day[0]->month();
      my $mday = join ",", map { $_->mday() } @day;
      my $prev = qq[<span class="nobr"><a href="./?view=$input{view}&amp;year=$year&amp;month=$month&amp;mday=$mday&amp;].persist(undef, ['magicdate']).'">Previous '.(($numofdays>1)?"$numofdays days":"day")."</a></span>";
      $prevnext = "&lt;-- $prev --- $next --&gt;";
    }
  }
  my @category = include::categories();
  my $other = '';
  if (not $istoday) {
    # We also want to link to other related items maybe, depending on
    # what item we're looking at...
    my ($resnum, $booking);
    if ($input{booking}) {
      $booking = getrecord('resched_bookings', $input{booking});
      if (ref $booking) {
        $resnum = $$booking{resource}
      }
    }

    my $thisday = (($input{mday} =~ /,|-/)?'These Same Days':'This Same Day');
    $other = qq[<strong>$thisday:</strong><ul>\n     ]
      . (join "\n     ", map {
        my ($catname, @id) = @$_;
        qq[<li><a href="./?view=] . (join ",", @id)
        . qq[&amp;$datevars&amp;category=$catname&amp;] . persist(undef, ['category']). qq[">$catname</a></li>]
      } @category) . qq[</ul>]
  }
  $other = ($other) ? "<div>$other</div>" : '';
  my $currentview = join '&amp;', map {
    $input{$_} ? "$_=$input{$_}" : ()
  } qw(view overview year month mday startyear startmonth startmday endyear endmonth endmday magicdate);
  my $aftertoday = getvariable('resched', 'sidebar_post_today');
  my $today = qq[<div><strong>Today:</strong>\n   <ul>
      ] . (join "\n      ", map {
        my ($catname, @id) = @$_;
        @id = categoryitems($catname, \@category);
        qq[<li><a href="./?category=$catname&amp;view=] . (join ',', @id)
        . '&amp;magicdate=today&amp;' . persist(undef, ['magicdate', 'category']) . qq[">$catname</a></li>]
      } @category) . qq[   </ul>\n   </div>];
  my @room = grep { $$_{flags} =~ /R/ and not $$_{flags} =~ /X/ } getrecord('resched_resources');
  my $roomsoneweek = qq[<div><strong>Rooms (1 week):</strong><ul>
        ] . (join "\n       ", map {
              my $r = $_;
              qq[<li><a href="./?view=$$r{id}&amp;year=].$now->year()."&amp;month=".$now->month(). "&amp;mday=$oneweek&amp;" . persist(undef, ['category', 'magicdate']) . '"' . ">$$r{name}</a></li>"
             } @room)
          . qq[\n        </ul></div>];
  my $overview = qq[<div><strong>Overview (month):</strong><ul>
        ] . (join "\n        ", map {
              qq[<li><a href="./?overview=$$_{id}&amp;startyear=]    . $now->year()."&amp;startmonth=".$now->month(). '&amp;' . persist(undef, ['category', 'magicdate']) . '"' . ">$$_{name}</a></li>"
             } @room, +{
                        name => 'all meeting rooms',
                        id   => (join ',', map { $$_{id} } @room)
                       })
          . qq[\n        </ul></div>];
  my $searchsection = qq[<div><strong><span onclick="toggledisplay('searchlist','searchmark');" id="searchmark" class="expmark">+</span>
          <span onclick="toggledisplay('searchlist','searchmark','expand');">Search:</span></strong>
          <div id="searchlist" style="display: none;">
            <ul><li><form action="index.cgi" method="post">
                      $hiddenpersist
                      <span class="nobr"><input type="text" name="search" size="12" />&nbsp;<input type="submit" value="Search" /></span>
                    </form></li>
                <li><form action="index.cgi" method="post">
                      $hiddenpersist
                      <span class="nobr"><input type="text" name="alias" size="12" />&nbsp;<input type="submit" value="Alias Search" /></span>
                    </form></li>
                <li><a href="./?frequserform=1&amp;$persistentvars">frequent user lookup</a></li>
            </ul>
          </div>
        </div>];
  my $aliassection = qq[<div><strong><span onclick="toggledisplay('aliaslist','aliasmark');" id="aliasmark" class="expmark">+</span>
        <span onclick="toggledisplay('aliaslist','aliasmark','expand');">Aliases:</span></strong>
        <div id="aliaslist" style="display: none;"><ul>
            <li><a href="index.cgi?action=newaliasfrm">New Alias</a></li>
            <li><form action="index.cgi" method="post">
                  $hiddenpersist
                  <span class="nobr"><input type="text" name="alias" size="12" />&nbsp;<input type="submit" value="Alias Search" /></span>
                </form></li>
        </ul></div></div>];
  my $statsection = qq[<div><strong><span onclick="toggledisplay('statslist','statsmark');" id="statsmark" class="expmark">+</span>
        <span onclick="toggledisplay('statslist','statsmark','expand');">Statistics:</span></strong>
        <div id="statslist" style="display: none;"><ul>
        <li><strong>Usage</strong><ul>
            <li><a href="./?stats=yesterday&amp;].persist(undef,['magicdate']).qq[">yesterday</a></li>
            <li><a href="./?stats=lastweek&amp;].persist(undef,['magicdate']).qq[">last week</a></li>
            <li><a href="./?stats=lastmonth&amp;].persist(undef,['magicdate']).qq[">last month</a></li>
            <li><a href="./?stats=lastyear&amp;].persist(undef,['magicdate']).qq[">last year</a></li>
            <li><a href="./?stats=monthbymonth&amp;].persist(undef,['magicdate']).qq[">month-by-month</a></li>
            <li><a href="./?stats=yearbyyear&amp;].persist(undef,['magicdate']).qq[">year-by-year</a></li>
          </ul></li>
        <li><strong>Availability</strong><ul>
            <li><a href="./?availstats=yesterday&amp;].persist(undef,['magicdate']).qq[">yesterday</a></li>
            <li><a href="./?availstats=lastweek&amp;].persist(undef,['magicdate']).qq[">last week</a></li>
            <li><a href="./?availstats=lastmonth&amp;].persist(undef,['magicdate']).qq[">last month</a></li>
          </ul></li>
        </ul></div></div>];
  my $stylesection = include::sidebarstylesection($currentview);
  my $otherfeatures = 0;
  my $staffschfeature = ''; if (getvariable('resched', 'staff_schedule_show_in_sidebar')) {
    $staffschfeature = qq[<div><strong><a href="staffsch.cgi?usestyle=$input{usestyle}">Staff Schedules</a></strong></div>];
    $otherfeatures++;
  }
  my $programsignup = ''; if (getvariable('resched', 'program_signup_show_in_sidebar')) {
    $programsignup  = qq[<div><strong><a href="program-signup.cgi?usestyle=$input{usestyle}">Program Signup</a></strong></div>];
    $otherfeatures++;
  }
  my ($mailfeature, $inboxnote) = ("", "");
  if (getvariable('resched', 'mail_enable')) {
    my $mailfeaturename = getvariable('resched', 'mail_sidebar_link_text');
    if ($mailfeaturename) {
      $mailfeature = qq[<div><strong><a href="mail.cgi?usestyle=$input{usestyle}">$mailfeaturename</a></strong></div>];
      $otherfeatures++;
    }
    my %unread = %{countfield('circdeskmail_header', 'folder', undef, undef, 'status', [0])};
    if ($unread{inbox}) {
      $inboxnote = qq[<div class="mailfoldersidebar"><a href="mail.cgi">inbox: <span class="unreadcount">$unread{inbox}</span> Unread messages</a></div>];
    }
  }
  my $otherfeaturessec = $otherfeatures ? qq[<!-- div id="otherfeaturessection" -->
        $programsignup
        $staffschfeature
        $mailfeature<!-- /div -->] : '';
  return qq[<div class="sidebar">$inboxnote
   <div>$prevnext</div>
   <div><a href="./?usestyle=$input{usestyle}"><strong>Choose Resource(s) &amp; Date(s)</strong></a></div>
   $other
   $today
   $otherfeaturessec
   $aftertoday
   $roomsoneweek
   $overview
   <div><strong>Upcoming Events:</strong><ul>
           <li><a href="./?action=daysclosed&amp;].persist(undef,['magicdate', 'category']).qq[">mark closed date</a></li>
        </ul></div>
   $searchsection
   $aliassection
   $statsection
   $stylesection
   <div><strong><span onclick="toggledisplay('ajaxtechlist','ajaxtechmark');" id="ajaxtechmark" class="expmark">+</span>
        <span onclick="toggledisplay('ajaxtechlist','ajaxtechmark','expand');">AJAX technology:</span></strong>
        <div id="ajaxtechlist" style="display: none;"><ul>
           <li><a href="./?$currentview&amp;usestyle=$input{usestyle}&amp;useajax=on">turn AJAX on</a></li>
           <li><a href="./?$currentview&amp;usestyle=$input{usestyle}&amp;useajax=off">turn AJAX off</a></li>
           </ul></div>
   </div>
</div>];
}

sub categoryitems {
  my ($catname, $categories) = @_;
  $categories = [include::categories()] if not scalar @$categories;
  #use Data::Dumper; warn Dumper(+{ categoryitems_categories => $categories });
  my ($cat) = grep { $$_[0] eq $catname } @$categories;
  croak "categoryitems(): category not found: '$catname' (possible categories: " . (join ", ", map { $$_[0] } @$categories) . ")" if not $cat;
  my ($cn, @id) = @$cat;
  @id = map { my @r = ($_);
              if (not $r[0] =~ /^\d+$/) {
                my ($subcat) = grep { $$_[0] eq $r[0] } @$categories;
                if ($subcat) {
                  @r = @$subcat;
                  shift @r;
                }
              }
              @r;
            } @id;
  return @id;
}

sub dterrormsg {
  my ($year, $mon, $mday, $hour, $min, $purpose) = @_;
  $purpose ||= "";
  my $timerows = "";
  if ($hour or $min) {
    $timerows = qq[<tr><th>Hour</th>
                              <td>$hour</td></tr>
                          <tr><th>Minute</th>
                              <td>$min</td></tr>];
  }
  return include::errordiv("Date/Time Error",
                           qq[DateTime could not make sense of these inputs$purpose:
                      <table><tbody>
                          <tr><th>Year</th>
                              <td>$year</td></tr>
                          <tr><th>Month</th>
                              <td>$mon</td></tr>
                          <tr><th>Day</th>
                              <td>$mday</td></tr>
                          $timerows
                      </tbody></table>\n]);
}

sub ordinalnumber {
  my ($n) = @_;
  return $n . include::ordinalsuffix($n);
}

sub uriencode {
  my ($uri) = @_;
  $uri =~ s/([\W])/"%" . uc(sprintf("%2.2x",ord($1)))/eg;
  return $uri;
}

sub dectime {
  my ($t, $gcf, $x) = @_;
  $t =~ /(\d+)[:](\d+)[:](\d+)/;
  my ($h, $m, $s) = ($1, $2, $3);
  my $dt;
  eval {
    $dt = DateTime->new(
                        hour   => $h,
                        minute => $m,
                        second => $s,
                        year   => 1970, month => 1, day => 1,
                       )->subtract(minutes => $gcf*$x);
  }; return dterrormsg(1970, 1, 1, $h, $m,
                       qq[ (for dectime($t, $gcf, $x))]) if $@;
  return $dt->hms();
}

sub parsenum {
  my ($string) = @_;
  my ($num) = $string =~ /(\d+)/;
  return $num;
}

sub sanitycheckalias {
  my ($arec) = @_;
  # If the alias record passes the sanity checks, return it.
  # Otherwise, print an error message and exit.
  if (include::isalias($$arec{canon})) {
    print include::standardoutput("Error: Canonical Name Cannot Also Be An Alias",
                                  include::errordiv('Invalid Alias',
                                                    qq[Thou shalt not use as a canonical name any sequence
                                          of letters that is also an alias.]),
                                  $ab, $input{usestyle}); exit 0;
  } elsif (findrecord('resched_alias', 'canon', $$arec{alias})) {
    print include::standardoutput("Error: Canonical Name Cannot Also Be An Alias",
                                  include::errordiv('Invalid Alias',
                                                    qq[Thou shalt not use as an alias any sequence
                                              of letters that is also a canonical name.]),
                                  $ab, $input{usestyle}); exit 0;
  } elsif (not $$arec{alias}) {
    print include::standardoutput("Error: Alias Field Blank",
                                  include::errordiv('Invalid Alias',
                                                    qq[Obviously you didn't really mean for the alias field to be blank.]),
                                  $ab, $input{usestyle}); exit 0;
  } elsif (not $$arec{canon}) {
    print include::standardoutput("Error: Canonical Name Blank",
                                  include::errordiv('Invalid Alias', "The canonical name is not allowed to be blank."),
                                  $ab, $input{usestyle}); exit 0;
  } else {
    return $arec;
  }
}

sub newaliasform {
  my $newalias = include::normalisebookedfor($input{newalias});
  my $newcanon = include::normalisebookedfor($input{newcanon}); # Nothing uses this at the moment.
  my $ilsname = getvariable('resched', 'ils_name');
  return qq[
   <form action="index.cgi" method="post">
       <table><tr><td>
               <input type="hidden" name="action" value="createalias" />
                <table class="table alias"><tbody>
                    <tr><th>Alias:</th>
                        <td><input type="text" size="30" name="alias" value="$newalias" /></td></tr>
                    <tr><th><div>Canonical Name:</div>
                            (as spelled in $ilsname)</th>
                        <td><input type="text" size="30" name="canon" value="$newcanon" /></td></tr>
                </tbody></table>
               <input type="submit" value="Save" />
       </td><td style="vertical-align: top; padding-left: 1em;">
           Aliasing is a way to mark several spellings of a name as
           all belonging to the same person.  This can be used to
           <q>correct</q> common misspellings.  It can also be used to
           create abbreviations for incredibly long names.  For
           instance, the alias <q>wia</q> expands to <q>mid-ohio
           educational service center/wia youth program</q>.
       </td></tr></table>
             </form>]
}

