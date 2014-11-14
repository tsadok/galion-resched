#!/usr/bin/perl -T
# -*- cperl -*-

our $debug = 0;
$maxrows = 150; # safety precaution
our $didyoumean_enabled = 1;

$ENV{PATH}='';
$ENV{ENV}='';

use DateTime;
use DateTime::Span;
use HTML::Entities qw(); sub encode_entities{ my $x = HTML::Entities::encode_entities(shift@_);
                                              $x =~ s/[-][-]/&mdash;/g;
                                              return $x; }
use Data::Dumper;

require "./forminput.pl";
require "./include.pl";
require "./auth.pl";
require "./db.pl";
require "./datetime-extensions.pl";

our %input = %{getforminput()};
#$input{useajax} = 'off'; # Hardcoding this would turn the AJAX stuff off for everybody (e.g. for testing)

our $persistentvars = persist();
our $hiddenpersist  = persist('hidden');
my $datevars = join "&amp;", grep { $_ } map { $input{$_} ? "$_=$input{$_}" : '' } qw (year month mday magicdate startyear startmonth startmday endyear endmonth endmday);

sub usersidebar; # Defined below.
sub uniq;        # Also defined below.
sub uniqnonzero; # below.

my $ab = authbox(sub { my $x = getrecord('users', shift); "<!-- Hello, $$x{nickname} -->"; });
my @warn; # scoped this way because sub nextrecur pushes warnings onto it in certain cases.
my $uniqueid = 101;
my $didyoumean_invoked;
my ($messagetouser, $redirectheader) = ('', '');

if ($auth::user) {
  # ****************************************************************************************************************
  # User is authorized as staff.
  my %user = %{getrecord('users',$auth::user)}; # Some things below want to know which staff.
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
              . (join "\n", map { qq[<li>Changed $$_[0] to $$_[1] (was $$_[2])<!-- $$_[3] --></li>] } @changes)
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
                                  (($input{staffinitials}) ? (staffinitials => $input{staffinitials}) : ()),
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
                <div>staff initials:&nbsp;<input name="staffinitials" type="text" size="3" /></div>
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
        for $tb (@targetbook) {
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
      for $booking (split /,\s*/, $input{cancel}) {
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
      for $booking (split /,\s*/, $input{cancel}) {
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
  } elsif ($input{stats}) {
    gatherstats();
  } elsif ($input{frequserform}) {
    my $formhtml = frequserform();
    print include::standardoutput('Frequent User Lookup:',
                                  qq[$formhtml],
                                  $ab, $input{usestyle}
                                 );
  } elsif ($input{frequser}) {
    my $formhtml = frequserform();
    my $start = DateTime->new(
                              year  => parsenum($input{startyear}),
                              month => parsenum($input{startmonth}),
                              day  => parsenum($input{startmday}),
                             );
    my $end = DateTime->new(
                            year  => parsenum($input{endyear}),
                            month => parsenum($input{endmonth}),
                            day   => parsenum($input{endmday}),
                            hour  => 23,
                           );
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
    for my $ck (uniq @ck) {
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
    my %rescat =
      map {
        my $cat = $_;
        my $catname = shift @$cat;
        map { $_ => $catname } @$cat;
      } include::categories();
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

sub viewbooking {
  # User wants to view details of a specific booking.
  my @bookinglisting;
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
        if (($origuntil->mday ne $newuntil->mday)
            and not getvariable('resched', 'allow_extend_past_midnight')) {
          warn "Tried to extend past midnight, not allowed.";
          push @bookinglisting, "" . include::errordiv('Cannot Extend Past Midnight', qq[Extending a booking past midnight into a new day is not supported.  Please see the recurring booking options if what you really want is to book the same resource at the same time on multiple days.]);
        } else {
          if ($input{latestart}) {
            warn "latestart has a value: $input{latestart}" if $debug;
            $newb{latestart} = DateTime::Format::ForDB(DateTime->new(
                                                                     year   => $newb{fromtime_datetime}->year,
                                                                     month  => $newb{fromtime_datetime}->month,
                                                                     day    => $newb{fromtime_datetime}->mday,
                                                                     hour   => $input{booking_late_datetime_hour},
                                                                     minute => $input{booking_late_datetime_minute},
                                                                    ));
          }
          if ($input{doneearlycheckbox}) {
            warn "doneearlycheckbox has a value: $input{doneearlycheckbox}" if $debug;
            $newb{doneearly} = DateTime::Format::ForDB(DateTime->new(
                                                                     year   => $newb{until_datetime}->year,
                                                                     month  => $newb{until_datetime}->month,
                                                                     day    => $newb{until_datetime}->mday,
                                                                     hour   => $input{booking_doneearly_datetime_hour},
                                                                     minute => $input{booking_doneearly_datetime_minute},
                                                                    ));
            if ($input{followupname}) {
              my %fb;
              if ($b{followedby}) {
                %fb = %{getrecord('resched_bookings', $b{followedby})};
              } else {
                $fb{resource} = $b{resource};
                $fb{isfollowup} = $b{id};
              }
              $fb{staffinitials} = $input{followupstaffinitials} || $fb{staffinitials} || $input{staffinitials} || $newb{staffinitials};
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
      my $fromdt = DateTime::From::MySQL( $b{fromtime}, undef, 'B');
      my $untidt = DateTime::From::MySQL( $b{until}, undef, 'C');
      my $earldt = DateTime::From::MySQL(($b{doneearly} ? $b{doneearly} : $b{until}),undef,'D');
      my %fbyrec; %fbyrec = %{getrecord('resched_bookings', $b{followedby})} if $b{followedby};
      my $ts = ((getvariable('resched', 'show_booking_timestamp')
                 ? qq[ <span class="tsmod">last modified $b{tsmod}</span>]
                 : ''));
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
                  <td><input type="checkbox" name="latestart" ]
                    .($b{latestart} ? ' checked="checked" ' : '').qq[ />&nbsp;Started late at
                      ].(DateTime::Form::Fields($latedt, 'booking_late', 'skipdate',undef,'FieldsL',
                                                time_list_quarter_hours_first => getvariable('resched', 'time_list_quarter_hours_first'))).qq[</td></tr>
              <tr><td>Until<sup><a href="#footnote2">2</a></sup>:</td>
                  <td>].(DateTime::Form::Fields($untidt, 'booking_until',undef,undef,'FieldsM',
                                                time_list_quarter_hours_first => getvariable('resched', 'time_list_quarter_hours_first'))).qq[</td>
                  <td><input type="checkbox" name="doneearlycheckbox" ].($b{doneearly}?' checked="checked" ' : '').qq[ />&nbsp;Done early at
                      ].(DateTime::Form::Fields($earldt,'booking_doneearly', 'skipdate',undef,'FieldsN',
                                                time_list_quarter_hours_first => getvariable('resched', 'time_list_quarter_hours_first'))).qq[
                      Followed by: <input name="followupname" value="$fbyrec{bookedfor}" />
                      <span class="nobr">Initials:<input name="followupstaffinitials" size="4" type="text" value="$fbyrec{staffinitials}" /></span>
                      </td></tr>
              <tr><td><input type="submit" value="Save Changes" /></td>
                  <td></td>
                  <td><a class="button" href="./?cancel=$b{id}&amp;$persistentvars">Cancel Booking</a></td></tr>
              <tr><td>Notes:</td><td colspan="2"><textarea cols="50" rows="$noteslines" name="booking_notes">$ben{notes}</textarea></td></tr>
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
  for my $n (1..10) {
    if ($input{'year'.$n} and $input{'month'.$n} and $input{'mday'.$n}) {
      my $dt = DateTime->new(
                             year    => $input{'year'.$n},
                             month   => $input{'month'.$n},
                             day     => $input{'mday'.$n},
                            );
      my %ot = include::openingtimes();
      my ($hour, $minute) = @{$ot{$dt->dow()} || [ 8, 0]};
      my $wc = DateTime->new(
                             year    => $dt->year(),
                             month   => $dt->month(),
                             day     => $dt->day(),
                             hour    => $hour,   # This gets overridden below, based on schedule.
                             minute  => $minute, # ditto.
                            );
      my %ct = include::closingtimes();
      my ($hour, $minute) = @{$ct{$dt->dow()} || [ 18, 0]};
      my $cu = DateTime->new(
                             year    => $dt->year(),
                             month   => $dt->month(),
                             day     => $dt->day(),
                             hour    => $hour,   # This gets overridden below, based on schedule.
                             minute  => $minute, # ditto.
                             );
      addrecord('resched_days_closed', +{ whenclosed  => DateTime::Format::ForDB($wc),
                                          closeduntil => DateTime::Format::ForDB($cu),
                                          reason      => encode_entities($input{notes}),
                                          user        => $user{id},
                                        });
      push @dc, $wc;
    }}
  $input{untilhour} = 20; $input{untilmin}  = 30; # TODO: closing times should NOT be hardcoded.
  my @resource = getrecord('resched_resources');
  my @result = map { my $dt = $_;
                     map {
                       my %s = %{getrecord('resched_schedules', $$_{schedule})};
                       my $when = DateTime::From::MySQL($s{firsttime});
                       attemptbooking($_, $$_{schedule}, $dt->clone()->set( hour => $when->hour, minute=> $when->minute ) );
                     } @resource;
                   } @dc;
  my $content = join "\n", @result;
  return ($content, 'Marking Closed Dates');
}

sub makebooking {
  my %res = %{getrecord('resched_resources', $input{resource})};
  my %sch = %{getrecord('resched_schedules', $res{schedule})};
  my @restobook = (\%res);
  if ($res{combine}) {
    for my $r (map { getrecord('resched_resources', $_) } split /,\s*/, $res{combine}) {
      push @restobook, $r if $input{"combiner$$r{id}"};
    }}
  my $when = DateTime::From::MySQL($input{when});
  my @when = ($when);
  if ($input{recur} eq 'listed') {
    for my $n (grep { $input{'recurlistmday'.$_} and $input{'recurlistyear'.$_} and $input{'recurlistmonth'.$_}
                    } map { /recurlistmday(\d+)/; $1 } grep { /^recurlistmday/ } keys %input) {
      push @when, DateTime->new(
                                year   => $input{'recurlistyear'.$n},
                                month  => $input{'recurlistmonth'.$n},
                                day    => $input{'recurlistmday'.$n},
                                hour   => $when->hour,
                                minute => $when->minute,
                               );
    }
  } elsif ($input{recur}) {
    my $udt;
    if ($input{recurstyle} eq 'until') {
      $udt = DateTime->new(year  => $input{recuruntilyear},  month  => $input{recuruntilmonth},
                           day   => $input{recuruntilmday},
                           hour  => $when->hour,             minute => $when->minute);
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
    $input{notes} .= "\n==============================\n" . assemble_extranotes($res);
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
  return ($content, 'Booking Resource: ' . $res{name}, $redirect_header);
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

  if ('yes' eq lc $input{policyhave}) {
    $extranotes .= "Already have a copy of our meeting room policy on file.\n";
  } else {
    if ($input{policysendemail}) {
      my $eddress = encode_entities($input{policysendemailaddress});
      $extranotes .= qq[Send meeting room policy by email to $eddress\n];
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
                            month => $_,
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
          initials:&nbsp;<input type="text" name="staffinitials" value="$input{staffinitials}" size="3" maxsize="20" />
          </p>
       $roombookingfields
       $submitbeforenotes
       <p><input type="checkbox" name="latestart" /> Started late at
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
                        my $dt = DateTime->new( year => 1974, month => $_ , day => 7);
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
  my %alwaysclosed = map { $_ => 1 } daysclosed(0);
  for my $id (@res) { $res{$id} = +{ %{getrecord('resched_resources', $id)} }; }
  my %sch = map { $_ => scalar getrecord('resched_schedules', $_) } uniq map { $res{$_}{schedule} } @res;
  my @calendar;
  for (qw(startyear startmonth startmday endyear endmonth endmday)) {
    ($input{$_}) = $input{$_} =~ /(\d+)/;
  }
  $input{endyear} ||= $input{startyear};
  $input{endmonth} ||= $input{startmonth};
  my $begdt = DateTime->new(
                            year  => $input{startyear},
                            month => $input{startmonth},
                            day   => ($input{startmday} || 1),
                           );
  my $enddt = DateTime->new(
                            year   => $input{endyear},
                            month  => $input{endmonth},
                            day    => ($input{endmday} ||
                                       last_mday_of_month(year   => $input{endyear},
                                                          month  => $input{endmonth})),
                            #hour   => 23, # i.e., _after_ the dt that starts this day, but before the next day.
                           );
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
  push @calendar, qq[
    <form class="nav" action="index.cgi" method="get">Get overview
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
  return (qq[<div class="overviewheader">Overview: $labeltext</div>] . (join "\n", @calendar), "Overview");
}

sub daysclosed {
  my ($form) = @_; # $form should be 0 for number, 1 for abbreviation, 2 for full day name.
  my @num = map { $_ % 7 } split /,\s*/, (getvariable('resched', 'daysclosed') || '0');
  return @num if not $form;
  my @answer;
  for my $num (@num) {
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
  my $dt = DateTime->new( year => 1978, month => 1, day => 1 ); # This date corresponds to a Sunday.
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
  # This was originally inlined above, but it was long, so I factored
  # it out to a subroutine for maintainability.
    my $now = DateTime->now(time_zone => $include::localtimezone);
    my %alwaysclosed = map { $_ => 1 } daysclosed(0);
    my @category = include::categories();
    my %category = map { my @x = @$_; my $name = shift @x; ($name, \@x) } @category;
    my @res;
    if ($input{category} and $category{$input{category}}) {
      @res = @{$category{$input{category}}};
    } else {
      @res = split /,\s*/, $input{view};
    }

    my %res;
    for my $id (@res) {
      $res{$id} =
        {
         %{getrecord('resched_resources', $id)},
         # Bookings are filled in below, after we know what dates we want.
        };
    }
    my @s = map {       scalar getrecord('resched_schedules', $_) } uniq map { $res{$_}{schedule} } @res;
    my %s = map { $_ => scalar getrecord('resched_schedules', $_) } uniq map { $res{$_}{schedule} } @res;

    # We want the starttimes as numbers of minutes since midnight.
    my @starttime = uniq map { $$_{firsttime} =~ m/(\d{2})[:](\d{2})[:]\d{2}/; (60*$1)+$2; } @s;
    # (These are used to calculate the gcf and also for the table's start time for the first row.)

    my $gcf;
    { # Now, we need the gcf interval.  Start based on schedules...

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
    }
    # $gcf now is the number of minutes per table row.  We can get the
    # rowspan figure for each cell by dividing the duration it
    # represents by this $gcf figure.  We can also calculate the times
    # to label each row with using this figure and the time from the
    # row above.

    # For the table's start time, we just want the earliest of the
    # starttimes:
    my $t = $starttime[0]; for (@starttime) { $t = $_ if $_ < $t }
    $tablestarttime=$t;

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
      my $dt = DateTime->new(year   => $year,
                             month  => $month,
                             day    => $mday,
                             hour   => int($t / 60),
                             minute => $t % 60,
                            );
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

    # Now we can fill in the bookings:
    {
      my $mindt = $dt[0];
      my $maxdt = $dt[-1]->clone()->add(days => 1);
      for my $id (@res) {
        $res{$id}{bookings} = [ get_timerange_bookings($id, $mindt, $maxdt) ];
      }
    }

    $debugtext .= "<p><div><strong>Viewing Schedules for @res:</strong></div>$/<pre>".encode_entities(Dumper(\%res))."</pre></p>
<p><div><strong>Schedules:</strong></div>$/<pre>".encode_entities(Dumper(\@s))."</pre></p>
<p>$gcf</p>
<p>Starting Times:<pre>".encode_entities(Dumper(@dt))."</pre></p>\n" if $debug;

#    my %endingtime =
#      (
#       #(map { $_ => [20, 30] } (1..4)), # 8:30pm Monday - Thursday,
#       #5 => [18, 0], # 6pm on Friday,
#       #6 => [17, 0], # 5pm on Saturday,
#       #7 => [8, 0],  # 8am on Sunday (i.e., we're not open at all).  This should never get used, though, because we filter out Sundays entirely.
#       (map { $_ => [20, 20] } (1..4)), # 8:20pm Monday - Thursday,
#       5 => [17, 50], # 5:50pm on Friday,
#       6 => [16, 50], # 4:50pm on Saturday,
#       7 => [8, 0],  # 8am on Sunday (i.e., we're not open at all).  This should never get used, though, because we filter out Sundays entirely.
#      );
    my %endingtime = include::closingtimes();
    #warn Dumper(\%endingtime);

    @col;
    # For each day we're showing, we want columns for each resource.
    for $dt (@dt) {
      for $r (@res) {
        my $end = $endingtime{$dt->wday()};
        my $schedule = $s{$res{$r}->{schedule}};
        $$schedule{firsttime} =~ /(\d{2})[:](\d{2})[:]\d+/;
        my ($beghour, $begmin) = ($1, $2);
        push @col,
          +{
            res => $res{$r},
            # cdt => DateTime->new( # DateTime for current row.
            #                      year   => $dt->year(),
            #                      month  => $dt->month(),
            #                      day    => $dt->day(),
            #                      hour   => $dt->hour(),
            #                      minute => $dt->minute(),
            #                     ),
            cdt => $dt->clone(),
            sdt => DateTime->new( # DateTime for first timeslot at beginning of day.
                                 year   => $dt->year(),
                                 month  => $dt->month(),
                                 day    => $dt->day(),
                                 hour   => $beghour,
                                 minute => $begmin,
                                ),
            end => DateTime->new( # DateTime for end of day
                                 year   => $dt->year(),
                                 month  => $dt->month(),
                                 day    => $dt->day(),
                                 hour   => $$end[0],
                                 minute => $$end[1],
                                ),
            # rsp => (($$schedule{intervalmins}) / $gcf),
          };
      }
    }

    $debugtext .= "<p>\%endingtime: ".(encode_entities(Dumper(\%endingtime)))."</p>
<p><div><strong>Columns:</strong></div><div><pre>".encode_entities(Dumper(\@col))."</pre></div></p>";

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
                               qq[<th class="res$res{$r}{id}"$s><a href="./?view=$res{$r}{id}&amp;year=$input{year}&amp;month=$input{month}&amp;mday=$input{mday}&amp;]. persist(undef, ['magicdate']) .qq[">$res{$r}{name}</a></th>]} @res
                           } @dt
                         )."<!-- dt: @dt --></tr>\n");
    my $maxnts; # Each iteration of the loop below calculates an $nts
                # value (number of timeslots); we want the largest one
                # for the next loop.
    for $c (@col) {
      # We must construct the column.  First we place appointments
      # already booked, then we place the empty timeslots at the
      # correct intervals, then we calculate how many rows each one
      # takes up.
      #use Data::Dumper; warn Dumper(+{ col => $c });
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
        my $cdt = $$c{cdt};
        (    ($bdt->year()  == $cdt->year())
         and ($bdt->month() == $cdt->month())
         and ($bdt->mday()  == $cdt->mday()))
      } @{$$c{res}{bookings}};

      for $b (@b) {
        my $fromtime = DateTime::From::MySQL($$b{fromtime});
        # But, what timeslots are we taking up, then?
        my $msm = ((60*$fromtime->hour())+$fromtime->min()); # minutes since midnight.
        my $msb = $msm - $tablestarttime; # minutes since beginning time of table.
        my $ts = $msb / $gcf;
        $ts = 0 if $ts < 0;
        #use Data::Dumper; warn Dumper(+{ fromtime => $fromtime->hms(), msm => $msm, msb => $msb, ts => $ts });

        # So, how many timeslots long is this booking?
        my $until    = DateTime::From::MySQL($$b{until});
        #my $duration = DateTime->new(
        #                             year   => $until->year(),
        #                             month  => $until->month(),
        #                             day    => $until->day(),
        #                             hour   => $until->hour(),
        #                             minute => $until->minute(),
        #                            )->subtract_datetime($fromtime);
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
              <!-- Booked by $$x{bookedby} for timeslot from $$x{fromtime} to $$x{until} (done: $$x{doneearly}, followed by $$x{followedby}) -->";
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
            $$c{tdcontent}[$ts] .= qq[<hr class="doneearly"></hr>\n<!-- Followup Booking: ########################################################
           fromtime => $$x{fromtime},    until => $$x{until},
           --><a href="./?booking=$$x{id}&amp;$persistentvars">].
              (
               include::capitalise(include::dealias(include::normalisebookedfor($$x{bookedfor})))
              ) ." ($fbytimeth)$notes</a>
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
        my $when = DateTime->new(# This is WRONG for columns that start their first timeslot
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
    for $c (@col) {
      # Calculate the rowspan values:
      my $rsp = 0;
      for $tsn (reverse 0 .. $maxnts) {
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
    for $row (0 .. $numofrows) {
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
        $min  = sprintf "%02d", ($rowtime % 60);
        $label = "<!-- $rowtime -->$hour:$min$ampm";
        if ($beforeopen) { $label = '<!-- before open -->'; $labelclass = 'beforeopen' }
      }
      $labelclass ||= 'label';
      push @tbody, qq[<tr><!-- $row --><td class="$labelclass">$label</td>] .
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
        . "</tr>";
    }
    my $pagetitle = 'View Schedule'; # Sane default.
    if ($input{view} =~ /^(\d+)$/) {
      my %r = %{getrecord('resched_resources', $1)};
      $pagetitle = $r{name};
      # This is a slightly better title, but maybe we can do better.
    }
    my %specialview = map {
      my ($name, @res) = @$_;
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
       $messagetouser
       $nownote
       <table border="1" class="scheduletable">
       <thead>].(join"\n",@thead).qq[</thead>
       <tbody>].(join"\n",@tbody).qq[</tbody>
       </table><!-- /table aleph -->],
                                  $ab, $input{usestyle},
                                  (($input{extend} ? $redirectheader : '')
                                   . $updatescript),
                                 );
    # ****************************************************************************************************************
}# end of doview()

sub gatherstats {
  my (@category);
  if ($input{resource}) {
    @category = (['Selected Resource(s)' => split /,\s*/, $input{resource}]);
  } else {
    @category = include::categories();
     # (['Internet' => 15, 16, 17, 3],
     #  ['Word Processing' => 4, 5, 6],
     #  ['Typewriter' => 7],
     #  ['Rooms' => 8, 9, 10],
     #  ['Practice Zone' => 11,12,13,14]);
  }
  my ($startstats, $endstats);
  if ($input{stats} eq 'yesterday') {
    $endstats = DateTime->now(time_zone => $include::localtimezone);
    $endstats->set_hour(0); $endstats->set_minute(1);
    $startstats = $endstats->clone()->subtract( days => 1 );
  } elsif ($input{stats} eq 'lastweek') {
    $endstats = DateTime->now(time_zone => $include::localtimezone);
    $endstats->set_hour(0); $endstats->set_minute(1);
    while ($endstats->wday > 1) { $endstats = $endstats->subtract( days => 1 ); }
    $startstats = $endstats->clone()->subtract( days => 7 );
  } elsif ($input{stats} eq 'lastmonth') {
    $endstats = DateTime->now(time_zone => $include::localtimezone);
    $endstats->set_hour(0); $endstats->set_minute(1);
    $endstats->set_day(1); # First of the month.
    $startstats = $endstats->clone()->subtract( months => 1 );
  } elsif ($input{stats} eq 'lastyear') {
    $endstats = DateTime->new(
                              year => DateTime->now->year(),
                              month => 1,
                              day   => 1,
                             );
    $startstats = $endstats->clone()->subtract( years => 1 );
  } elsif ($input{stats} eq 'custom') {
    $startstats = DateTime->new(
                                year  => parsenum($input{startyear}),
                                month => parsenum($input{startmonth}),
                                day  => parsenum($input{startmday}),
                               );
    $endstats = DateTime->new(
                              year  => parsenum($input{endyear}),
                              month => parsenum($input{endmonth}),
                              day  => parsenum($input{endmday}),
                             );
  } elsif ($input{stats} eq 'overtime') {
    # This is where we start doing multiple date ranges.
    # TODO:  implement this.
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
  print include::standardoutput('Usage Statistics',
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
  # TODO:  Make this return something that specifies the date range,
  #        so that if we gather for multiple ranges the results make sense.
  my @category = @$categories;
  my (@gatheredstat);
  my %exclude = map { (lc $_) => 1 } split /,\s*/, (getvariable('resched', 'nonusers') || 'closed,maintenance,out of order');
  for (@category) {
    ($category, @resid) = @$_;
    my ($totaltotalbookings, $totaltotalduration);
    push @gatheredstat, '<div>&nbsp;</div><table><thead><tr><th colspan="4"><strong>' . "$category</strong></th></tr>\n\n";
    # <div><strong>' . ucfirst $category . '</strong></div>' . "\n<table>\n";
    for $rid (@resid) {
      my %r = %{getrecord('resched_resources', $rid)};
      my $db = dbconn();
      my $q = $db->prepare('SELECT * FROM resched_bookings '
                           . 'WHERE resource=? AND fromtime>=? AND fromtime<?'
                           . 'AND bookedfor NOT IN (' . (join ',', map { '?' } keys %exclude) . ')');
      $q->execute(
                  $rid,
                  DateTime::Format::MySQL->format_datetime($startstats),
                  DateTime::Format::MySQL->format_datetime($endstats),
                  (keys %exclude),
                 );
      my ($totalbookings, $totalduration);
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
      my $durinhours = (ref $totalduration ? $totalduration->in_units('hours') : '0');
      $totalbookings ||= 0;
      push @gatheredstat, qq[<tr><td>$r{name}:</td>
              <td class="numeric">$totalbookings bookings</td>
              <td> totalling</td><td class="numeric">$durinhours hours.</td></tr>\n];
      $totaltotalbookings += $totalbookings;
      $totaltotalduration = (ref $totaltotalduration ? $totaltotalduration + $totalduration : $totalduration);
    }
    my $durinhours = (ref $totaltotalduration ? $totaltotalduration->in_units('hours') : '0');
    push @gatheredstat, qq[<tr><td><strong>Subtotal:</strong></td>
              <td class="numeric">$totaltotalbookings bookings</td>
              <td> totalling</td><td class="numeric">$durinhours hours.</td></tr></table>\n];
  }
  return @gatheredstat;
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
  }
  # So if we get here, we have results in @result:
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
      @changes = @{updaterecord('resched_bookings', \%booking)};
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
  <span class="nobr">Staff Initials: <input type="text" name="staffinitials" size="5" /></span>
  <div>Reason for Closing: <input type="text" name="notes" /></div>
  <br />
  <input type="submit" value="Book Us Closed" />
</form>
DAYSCLOSEDFORM
}

sub frequserform {
  my ($now, $soy);
  if ($input{endyear} and $input{endmonth} and $input{endmday}) {
    $now = DateTime->new(
                         year  => $input{endyear},
                         month => $input{endmonth},
                         day   => $input{endmday},
                        );
  } else {
    $now = DateTime->now(time_zone => $include::localtimezone);
  }
  if ($input{startyear} and $input{startmonth} and $input{startmday}) {
    $soy = DateTime->new(
                         year  => $input{startyear},
                         month => $input{startmonth},
                         day   => $input{startmday},
                        );
  } else {
    $soy = DateTime->new(  year  => DateTime->now(time_zone => $include::localtimezone)->year(),
                           month => 1,
                           day   => 1,  );
  }
  my $monthoptionsoy = join "\n", map {
    my $dt = DateTime->new( year  => 1970,
                            month => $_,
                            day   => 1);
    my $abbr = $dt->month_abbr;
    my $selected = ($_ == $soy->month) ? ' selected="selected"' : '';
    qq[<option value="$_"$selected>$abbr</option>];
  } 1..12;
  my $monthoptionnow = join "\n", map {
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
  return qq[<form action="index.cgi" method="post">
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
  my %sch = %$schedule; my %res = %$resource;
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
        $until = DateTime->new(
                               time_zone => $include::localtimezone,
                               year      => $when->year,
                               month     => $when->month,
                               day       => $when->mday,
                               hour      => $hour,
                               minute    => $min,
                              );
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
  } elsif ($res{requireinitials} and not $input{staffinitials}) {
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
                   (($input{staffinitials}) ? (staffinitials => $input{staffinitials}) : ()),
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
      my $late = DateTime->new(
                               time_zone => $include::localtimezone,
                               year      => $when->year,
                               month     => $when->month,
                               day       => $when->day,
                               hour      => $input{latehour},
                               minute    => $input{lateminute},
                              );
      if (($when->hour >= 12)
          and ($late->hour < 12)) {
        $late = $late->add( hours => 12 );
      }
      $booking{latestart} = DateTime::Format::ForDB($late);
    } elsif ($input{dynamicform} and getvariable('resched', 'automatic_late_start_time')) {
      # Do implicit late start if AND ONLY IF we are making the booking during the timeslot.
      my $now = DateTime->now(time_zone => $include::localtimezone);
      if (($now >= $when) and ($now <= $until)) {
        my $late = DateTime->new(
                                 time_zone => $include::localtimezone,
                                 year      => $when->year,
                                 month     => $when->month,
                                 day       => $when->day,
                                 hour      => $now->hour,
                                 minute    => $now->minute,
                              );
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
                    } uniq(map {
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
            "Alias Not Found: $alias");
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
  my %category = map { my @x = @$_; my $name = shift @x; ($name, \@x) } include::categories();
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
  my %category = map { my @x = @$_; my $name = shift @x; ($name, \@x) } include::categories();
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
    my $numofdays = @dt;
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
        <li><a href="./?stats=yesterday&amp;].persist(undef,['magicdate']).qq[">yesterday</a></li>
        <li><a href="./?stats=lastweek&amp;].persist(undef,['magicdate']).qq[">last week</a></li>
        <li><a href="./?stats=lastmonth&amp;].persist(undef,['magicdate']).qq[">last month</a></li>
        <li><a href="./?stats=lastyear&amp;].persist(undef,['magicdate']).qq[">last year</a></li>
        </ul></div></div>];
  my $stylesection = include::sidebarstylesection($currentview);
  my $otherfeatures = 0;
  my $staffschfeature = ''; if (getvariable('resched', 'staff_schedule_show_in_sidebar')) {
    $staffschfeature = qq[<div><strong><a href="staffsch.cgi?usestyle=$input{usestyle}">Staff Schedules</a></strong></div>];
    $otherfeatures++;
  }
  my $programsignup = ''; if (getvariable('resched', 'program_signup_show_in_sidebar')) {
    $programsignup  = qq[<div><strong><a href="program-signup.cgi?usestyle=$input{usestyle}">Program Signup</a></strong></div>];
    $otherfeature++;
  }
  my $otherfeaturessec = $otherfeatures ? qq[<!-- div id="otherfeaturessection" -->
        $programsignup
        $staffschfeature<!-- /div -->] : '';
  return qq[<div class="sidebar">
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

sub uniq {
  my %seen;
  return grep { not $seen{$_}++ } @_;
}
sub uniqnonzero {
  my %seen = ( 0 => 1 );
  return grep { not $seen{$_}++ } @_;
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
  my $dt = DateTime->new(
                         hour   => $1,
                         minute => $2,
                         second => $3,
                         year   => 1970, month => 1, day => 1,
                        )->subtract(minutes => $gcf*$x);
  return $dt->hms();
}

sub parsenum {
  my ($string) = @_;
  my ($num) = $string =~ /(\d+)/;
  return $num;
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
  my @pf = map {
    my @f = primefactor abs $_;
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

sub sanitycheckalias {
  my ($arec) = @_;
  # If the alias record passes the sanity checks, return it.
  # Otherwise, print an error message and exit.
  if (include::isalias($$arec{canon})) {
    print include::standardoutput("Error: Canonical Name Cannot Also Be An Alias",
                                  errordiv('Invalid Alias',
                                           qq[Thou shalt not use as a canonical name any sequence
                                          of letters that is also an alias.]),
                                  $ab, $input{usestyle}); exit 0;
  } elsif (findrecord('resched_alias', 'canon', $$arec{alias})) {
    print include::standardoutput("Error: Canonical Name Cannot Also Be An Alias",
                                  errordiv('Invalid Alias',
                                           qq[Thou shalt not use as an alias any sequence
                                              of letters that is also a canonical name.]),
                                  $ab, $input{usestyle}); exit 0;
  } elsif (not $$arec{alias}) {
    print include::standardoutput("Error: Alias Field Blank",
                                  errordiv('Invalid Alias',
                                           qq[Obviously you didn't really mean for the alias field to be blank.]),
                                  $ab, $input{usestyle}); exit 0;
  } elsif (not $$arec{canon}) {
    print include::standardoutput("Error: Canonical Name Blank",
                                  errordiv('Invalid Alias', "The canonical name is not allowed to be blank."),
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
