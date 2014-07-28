#!/usr/bin/perl -T
# -*- cperl -*-

#$debug = 1;
$maxrows = 150; # safety precaution

$ENV{PATH}='';
$ENV{ENV}='';

use DateTime;
use DateTime::Span;
use HTML::Entities qw(); sub encode_entities{$_=HTML::Entities::encode_entities(shift@_);s/[-][-]/&mdash;/g;return$_;}

require "./forminput.pl";
require "./include.pl";
require "./auth.pl";
require "./db.pl";
require "./ajax.pl";
require "./datetime-extensions.pl";

our %input = %{getforminput()};

#use Data::Dumper; warn Dumper(+{ input => \%input });

my $ab = authbox(sub { my $x = getrecord('users', shift); "<!-- Hello, $$x{nickname} -->"; });

if ($auth::user) {
  if ($input{ajax} eq 'updateme') {
    my $since = DateTime::From::MySQL($input{since});
    my @r = getsince('resched_bookings', 'tsmod', $since);
    # TODO:  allow updates to be retrieved and inserted into the table automatically.
#  } elsif ($input{ajax} eq 'gettimeslot') {
#    my $when = DateTime::From::MySQL($input{when});
  } elsif ($input{ajax} eq 'updates-p') {
    # Check to see if there _are_ updates, and if so signal a page reload.
    # This is not ideal.  updateme would be ideal.  This is easier to code.
    die "No since argument" if not $input{since};
    #warn "Checking for updates since $input{since}\n";
    my $since = DateTime::From::MySQL($input{since});
    my %res = map { $_ => 1 } split /,\s*/, $input{resource};
    my @nb = grep { $res{$$_{resource}}
                  } getsince('resched_bookings', 'tsmod', $since);
    if (scalar @nb) {
      #warn "Found " . @nb . "\n";
      sendresponse(qq[<updatecount>] . @nb . '</updatecount>');
    } else {
      #warn "Did not find any.\n";
      sendresponse(qq[<success>There are no new bookings since ] . $since->hms() . qq[.</success>])
    }
  } elsif ($input{ajax} eq 'testalert') {
    sendalert("Testing 1, 2, 3, ...");
  } elsif ($input{ajax} eq 'testreplace') {
    my $rnum = sprintf "%0.4d", rand(1000);
    sendreplace($input{containerid}, qq[<span class="test"><div><strong>Testing...</strong></div><div>$rnum</div></span>]);
  } elsif ($input{ajax} eq 'newbookingform') {
    sendnewbookingform($input{containerid}, $input{resource}, $input{when});
  } elsif ($input{ajax} eq 'doneearlyform') {
    senddoneearlyform($input{containerid}, $input{bookingid});
  } elsif ($input{ajax} eq 'somerequest') {
    # Process additional types of requests here.
  } else {
    my $sysadmin = getvariable('resched', 'sysadmin_name');
    sendfailure(
                error       => "Unknown Request Type: $input{ajax}",
                likelycause => 'There may be a bug in the software.',
                suggestion  => "Contact $sysadmin.",
               );
  }
} else {
  sendfailure(
              error       => 'Authorization Failure',
              likelycause => 'The user may not have logged in before the request was made.',
              suggestion  => 'First log in, then try again.',
             );
}

exit 0; # subroutines follow.

sub senddoneearlyform {
  my ($containerid, $bookingid) = @_;
  my $booking = getrecord('resched_bookings', $bookingid);
  if (ref $booking) {
    my $for = include::capitalise(include::dealias(include::normalisebookedfor($$booking{bookedfor})));
    my $donedt = DateTime::From::MySQL($$booking{until});
    my $now = DateTime->now(time_zone => $include::localtimezone);
    my $focid = 'foc' . join '', map { (qw(a b c d e f g h i j k l m n o p q r s t u v w x y z))[1 + rand 25] } 1..13;
    ref $donedt or warn "No DateTime object";
    sendreplace($containerid,
                qq[<form action="./" method="GET" name="doneearlyform" class="doneearly">
        <input type="hidden" name="action"    value="change" />
        <input type="hidden" name="doneearly" value="$$booking{id}" />
        ] . persist('hidden', ['magicdate']) . qq[
                   $for finished at
                   <input type="hidden" name="donetime_datetime_year"  value="].$donedt->year.qq[" />
                   <input type="hidden" name="donetime_datetime_month" value="].$donedt->month.qq[" />
                   <input type="hidden" name="donetime_datetime_day"   value="].$donedt->mday.qq[" />
                   ].(DateTime::Form::Fields($now, 'donetime','skipdate',undef,'FieldsQ')).qq[
                       and was followed by
                       <input type="text" name="followupname" id="$focid" />
                       initial:<input type="text" name="staffinitials" size="3" />
                     <input type="submit" value="Save Change" />
    </form>], $focid);
  } else {
    my $sysadmin = getvariable('resched', 'sysadmin_name');
    sendfailure(
                error       => 'No Such Booking',
                likelycause => 'Someone may have deleted the booking, or there may be a bug in the software.',
                suggestion  => "Contact the $sysadmin",
               );
  }
}

sub sendnewbookingform {
  my ($containerid, $resid, $when) = @_;
  #warn "containerid: $containerid; resid: $resid; when: $when";
  my %res = %{getrecord('resched_resources', $resid)};
  $res{id} or warn "sendnewbookingform has a problem with resource $resid";
  my %sch = %{getrecord('resched_schedules', $res{schedule})};
  $sch{id} or warn "sendnewbookingform has a problem with schedule $res{schedule}";
  #warn "Ready to construct when dt";
  my $whendt = DateTime::From::MySQL($when);
  ref $whendt or warn "sendnewbookingform has a problem when $when";
  #warn "Ready to construct untildt";
  my $untildt = $whendt->clone()->add( minutes => $sch{durationmins} );
  ref $untildt or warn "sendnewbookingform has a problem with untildt $untildt";
  # We can schedule for less, down to intervalmins, if there's a
  # problem, but this initial $untildt is what we really want.
  # Note that we ASSUME durationmins is a multiple of intervalmins.
  my ($collision, @collision, $retries);
  while (($whendt < $untildt)
         and (dt_difference_in_minutes($untildt, $whendt) >= $sch{intervalmins})
         and (@collision = include::check_for_collision_using_datetimes($res{id}, $whendt, $untildt))) {
    #use Data::Dumper; warn "Collision(s) found: " . Dumper(@collision);
    #warn "Trying for a smaller timeslot: slot was from $whendt until $untildt; subtracting $sch{intervalmins} minutes.";
    $untildt = $untildt->subtract( minutes => $sch{intervalmins});
    ++$retries;
    #warn "New timeslot is from $whendt until $untildt.";
    $collision = $collision[0]; # Save the first collision in case we need it to construct an error message.
  }
  if (@collision) {
    #use Data::Dumper; warn "Collision: " . Dumper($collision);
    sendalertandreplace($input{containerid},
                        "Sorry, but the $res{name} is already booked at that time.",
                        qq[<span class="dynamic_content">Already Booked:]
                        . showbooking($collision, \%res, quick => 'quick')
                        . "</span>"
                       );
  } else {
    my $untilinput;
    if (not $sch{durationlock}) {
      my $n = $sch{durationmins} / $sch{intervalmins};
      $untilinput = qq[<span class="nobr">until: <select name="untiltime">] . (join "\n       ",
                                                map {
                                                  my $dt = $whendt->clone()->add(minutes => $sch{intervalmins}*$$_[0]);
                                                  '<option value="'.$dt->hour.':'.$dt->minute.'"'.$$_[1].'>'.include::twelvehourtimefromdt($dt).'</option>'
                                                } map {
                                                  [$_, (($_ eq $n and not $retries)
                                                        ? ' selected="selected"' : '')],
                                                } 1 .. 6) . qq[</select></span>];
    }
    my $focid = 'foc' . join '', map { (qw(a b c d e f g h i j k l m n o p q r s t u v w x y z))[1 + rand 25] } 1..13;
    sendreplace($input{containerid},
                qq[<span class="dynamic_content"><form action="index.cgi" method="post">
                     <input type="hidden" name="action"       value="makebooking" />
                     <input type="hidden" name="when"         value="$when" />
                     <input type="hidden" name="resource"     value="$res{id}" />
                     <input type="hidden" name="usestyle"     value="$input{usestyle}" />
                     <input type="hidden" name="dynamicform"  value="yes" />
                     <input type="text" name="bookedfor" size="20" id="$focid" />
                     $untilinput
                     <span class="nobr">initial:<input type="text" size="3" name="staffinitials" maxsize="20" /></span>
                     <input type="submit" value="Do it" />
                   </form></span>],
                $focid
               );
  }
  die "Fallthrough!";
}

sub showfollowup {
  my ($id) = @_;
  my $booking = getrecord('resched_bookings', $id);
  my $resource = getrecord('resched_resources', $booking{resource});
  return showbooking($booking, $resource);
}
sub showbooking {
  my ($b, $r, %optn) = @_;
  my %booking = %$b;
  my %resource = %$r;
  my $donelink eq '';
  if ($optn{quick}) {
    # In the "Quick button" scenario, we only want to show the
    # "done early" link if the booking is for exactly intervalmins:
    my $s = getrecord('resched_schedules', $resource{schedule});
    my $untildt = DateTime::From::MySQL($booking{until});
    my $whendt  = DateTime::From::MySQL($booking{fromtime});
    if (dt_difference_in_minutes($untildt, $whendt) == $$s{intervalmins}) {
      $donelink = qq[<div style="text-align: right;" class="doneearly"><a href="./?doneearly=$booking{id}&amp;usestyle=$input{usestyle}&amp;stylepics=$input{stylepics}" class="avail">done early?</a></div>];
    } else {
      #warn "Difference is " . dt_difference_in_minutes($untildt, $whendt) . " versus intervalmins at $s{intervalmins}.";
      $donelink = qq[<div style="font-size: smaller;"><em>(New)</em></div>]
    }
  } else {
    $donelink = qq[<div style="text-align: right;" class="doneearly"><a href="./?doneearly=$booking{id}&amp;usestyle=$input{usestyle}&amp;stylepics=$input{stylepics}" class="avail">done early?</a></div>];
  }
  return
    qq[<a href="./?booking=$booking{id}&amp;usestyle=$input{usestyle}&amp;stylepics=$input{stylepics}">]
      . (include::capitalise(include::dealias(include::normalisebookedfor($booking{bookedfor}))))
      . ($booking{latestart} ? (' ('. twelvehourtimefromdt(DateTime::From::MySQL($booking{latestart})).')') : '')
      . ($booking{notes} ? qq[ <abbr title="].encode_entities($booking{notes}).qq["><img width="24" height="24" alt="[Notes]" src="notes.png" /></abbr>] : '')
      . qq[</a> <hr class="doneearly" />]
      . ($booking{doneearly}
         ? (
            $booking{followedby} ? showfollowup($booking{followedby}) :
            qq[<div style="text-align: right;" class="doneearly"><a href="./?doneearly=$booking{id}&amp;usestyle=$input{usestyle}&amp;stylepics=$input{stylepics} class="avail">]
            . ($booking{followedby} ? qq[] : "")
            . qq[</a></div>]
           )
         : (
            extendlink($b) . $donelink
           ));
}

sub extendlink {
  my ($b) = @_;
  my %booking = %$b;
  return qq[<a href="./?extend=$booking{id}&amp;usestyle=$input{usestyle}&amp;stylepics=$input{stylepics}"><img src="/img/arrow-down-blue.png" class="extendarrow" width="27" height="15" /></a>];
}

sub dt_difference_in_minutes {
  use Carp;
  my ($laterdt, $earlierdt) = @_;
  carp('laterdt:' . $laterdt) if $debug;
  carp('earlierdt:' . $earlierdt) if $debug;
  my $duration = $laterdt - $earlierdt;
  ref $duration or warn "no duration";
  my $minutes = $duration->delta_minutes;
  return $minutes;
}

