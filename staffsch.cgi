#!/usr/bin/perl -T
# -*- cperl -*-

our $debug = 0;

$ENV{PATH}='';
$ENV{ENV}='';

use DateTime;
use DateTime::Span;
use HTML::Entities qw(); sub encode_entities{ my $x = HTML::Entities::encode_entities(shift@_);
                                              $x =~ s/[-][-]/&mdash;/g;
                                              return $x; }
use Data::Dumper;

our %input;

require "./forminput.pl";
require "./include.pl";
require "./auth.pl";
require "./db.pl";
require "./ajax.pl";
require "./datetime-extensions.pl";
require "./colors.pl"; our (@color, %backgroundcolor, $defaultbackgroundcolor);
our $localtimezone ||= 'America/New_York';
our $now   = DateTime->now( time_zone => $localtimezone );
our $dbnow = DateTime::Format::ForDB($now);

our %input = %{getforminput()};

our $persistentvars = persist(undef,    [qw(category magicdate)]);#join '&amp', map { qq[$_=] . encode_entities($input{$_}) } grep { $input{$_} } qw(usestyle useajax);
our $hiddenpersist  = persist('hidden', [qw(category magicdate)]);
#warn "Persist: $persistentvars\n";

our $wherever = +{ id => 0, briefname => 'float', description => 'wherever needed' };

sub usersidebar; # Defined below.
sub uniq;        # Also defined below.
sub uniqnonzero; # below.

my $ab = authbox(sub { my $x = getrecord('users', shift); "<!-- Hello, $$x{nickname} -->"; });

my $content = '';
my $pagetitle = 'Staff Schedule';
my %user;
if ($auth::user) {
  # ****************************************************************************************************************
  # User is authorized as staff.
  %user = %{getrecord('users',$auth::user)}; # Some things below want to know which staff.
  my $adminprivs = (($user{flags} =~ /A/) or (getvariable('resched', 'staff_schedule_lax_security'))) ? 1 : 0;
  if ($input{action} eq 'showday') {
    ($content, $pagetitle)   = showday();
    $pagetitle             ||= join ' ', grep { $_ } ('Staff', encode_entities($input{requireflag}), 'Schedules Today');
  } elsif ($input{action} eq 'showweek') {
    ($content, $pagetitle)   = showweek();
    $pagetitle             ||= join ' ', grep { $_ } ('Staff', encode_entities($input{requireflag}), 'Schedules This Week');
  } elsif ($input{action} eq 'showmonth') {
    ($content, $pagetitle)   = showmonth();
    $pagetitle             ||= join ' ', grep { $_ } ('Staff', encode_entities($input{requireflag}), 'Schedules This Month');
  } elsif ($input{action} eq 'showinterval') {
    ($content, $pagetitle)   = custominterval();
    $pagetitle             ||= join ' ', grep { $_ } ('Staff', encode_entities($input{requireflag}), 'Schedules');
  } elsif ($input{action} eq 'liststaff') {
    $content = liststaff();
  } elsif (($input{action} eq 'newstaff') and $adminprivs) {
    $content = staffform();
  } elsif (($input{action} eq 'createstaff') and $adminprivs) {
    $content = createstaff();
  } elsif (($input{action} eq 'editstaff') and $adminprivs) {
    $content = staffform(getrecord('resched_staff', $input{staffid}));
  } elsif (($input{action} eq 'updatestaff') and $adminprivs) {
    $content = updatestaff();
  } elsif ($input{action} eq 'staffschedule') {
    $content = staffschedule();
  } elsif ($input{action} eq 'editstaffhours') {
    $content = maybeeditstaffhours();
  } elsif ($input{action} eq 'updatestaffhours') {
    $content = maybeupdatestaffhours();
  } elsif ($input{action} eq 'editregularhours') {
    $content = maybeeditregularhours();
  } elsif ($input{action} eq 'updateregularhours') {
    $content = maybeupdateregularhours();
  } elsif ($input{action} eq 'addregularhours') {
    $content = addregularhours();
  } elsif ($input{action} eq 'editoccasionhours') {
    $content = maybeeditoccasionhours();
  } elsif ($input{action} eq 'inputrecurocchours') {
    $content = inputrecurocchours();
  } elsif ($input{action} eq 'updateoccasionhours') {
    $content = maybeupdateoccasionhours();
  } elsif ($input{action} eq 'addoccasionhours') {
    $content = addoccasionhours();
  } elsif (($input{action} eq 'editcolors') and $adminprivs) {
    $content = editcolors();
  } elsif (($input{action} eq 'updatecolors') and $adminprivs) {
    $content = updatecolors();
  } else {
    $content = qq[<div class="h">Welcome to the Staff Schedule facility</div>] . showweek();
  }
} else {
  $content = 'Not Authorized';
}

if ($input{ajaxreplace}) {
  sendreplace($input{ajaxreplace}, $content);
} else {
  print include::standardoutput($pagetitle, $content, $ab, $input{usestyle},
                                #qq[<script language="javascript" src="ajax.js" type="text/javascript">\n</script>\n]
                               );
}


exit 0; # Subroutines follow.

sub showday {
  my $year  = include::getnum('startyear')  || $now->year();
  my $month = include::getnum('startmonth') || $now->month();
  my $day   = include::getnum('startmday')  || $now->mday();
  my $start = DateTime->new( time_zone => $localtimezone,
                             year      => $year,
                             month     => $month,
                             day       => $day, );
  my $end   = $start->clone()->add( days => ($input{numofdays} || 1) );
  return showinterval($start, $end);
}
sub showweek {
  my $year  = include::getnum('startyear')  || $now->year();
  my $month = include::getnum('startmonth') || $now->month();
  my $day   = include::getnum('startmday')  || $now->mday();
  my $start = DateTime->new( time_zone => $localtimezone,
                             year      => $year,
                             month     => $month,
                             day       => $day, );
  while (($start->dow() % 7) ne (getvariable('resched', 'staff_schedule_first_day_of_week') || 0)) {
    $start = $start->subtract( days => ($input{numofweeks} || 1) );
  }
  my $end   = $start->clone()->add( days => 7 );
  return showinterval($start, $end);
}
sub showmonth {
  my $year  = include::getnum('startyear')  || $now->year();
  my $month = include::getnum('startmonth') || $now->month();
  my $start = DateTime->new( time_zone => $localtimezone,
                             year      => $year,
                             month     => $month,
                             day       => 1 );
  my $end   = $start->clone()->add( months => ($input{numofmonths} || 1) );
  while (($start->dow() % 7) ne (getvariable('resched', 'staff_schedule_first_day_of_week') || 0)) {
    $start = $start->subtract( days => ($input{numofweeks} || 1) );
  }
  return showinterval($start, $end);
}

sub showinterval {
  my ($startdt, $enddt, %option) = @_;
  my @day;
  my $dt = $startdt->clone();
  my %closed = map { (($_ % 7) + 0) => 1 } split /,\s*/, (getvariable('resched', 'daysclosed') || '0');
  #use Data::Dumper; warn Dumper(+{ closed => \%closed });
  my @schedflag        = getrecord('resched_staffsch_flag');
  my @sepsch           = grep { $$_{flags} =~ /S/ } @schedflag;
  my $separateschedule = (join '|', map { $$_{flagchar} } @sepsch) || '__NOMATCH__';
  my $cancelflag       = (join '|', map { $$_{flagchar} } grep { $$_{flags} =~ /X/ } @schedflag) || '__NOMATCH__';
  my $partial          = (join '|', map { $$_{flagchar} } grep { $$_{flags} =~ /P/ } @schedflag) || '__NOMATCH__';
  my $aflag            = (join '|', map { $$_{flagchar} } grep { $$_{flags} =~ /A/ } @schedflag) || '__NOMATCH__';
  #use Data::Dumper(); warn Dumper( +{ separateschedule => $separateschedule, cancelflag => $cancelflag, partial => $partial, } );
  my $tfvars = persist(undef, [qw(category magicdate)], [qw(action startyear startmonth startmday)]);
  my $sepschnote = ((scalar @sepsch) and not $input{requireflag})
    ? (qq[<div class="p explan">Hours with any of the following flags are on separate schedules: ]
       . (join ", ", map { qq[<a class="altschedulelink button" href="staffsch.cgi?$tfvars&amp;requireflag=$$_{flagchar}">] . formatflag($_) . qq[</a>]
                         } @sepsch) . qq[</div>]) : '';
  my $issepsch = ($input{requireflag}) ? (qq[<div class="h">] . (join "", map {
    my $fc  = $_;
    my ($f) = grep { $$_{flagchar} eq $fc } findrecord('resched_staffsch_flag', 'flagchar', $fc);
    encode_entities($$f{shortdesc}) . ' ';
  } split //, $input{requireflag}) . qq[Schedule:</div>]) : '';
  my %reqflag = ();
  while ($dt->ymd() lt $enddt->ymd()) {
    if ($closed{$dt->dow() % 7}) {
      push @day, qq[<!-- always closed on ] . ($dt->day_abbr()) . qq[ -->];
    } else {
      my $cu = $dt->clone()->add( hours => 20 );
      my ($closedrec) = finddateoverlap('resched_days_closed', 'whenclosed', 'closeduntil', $dt, $cu);
      my $closed = (ref $closedrec) ? qq[<div class="dayclosed"><span class="dayclosedlabel">Closed:</span> <span class="dayclosedreason">$$closedrec{reason}</span></div>] : qq[<!-- not closed: [$wc] - [$cu] -->];
      my $dow  = $dt->day_abbr();
      my $mon  = $dt->month_abbr();
      my $mday = include::htmlordinal($dt->mday());
      my $tday = ($dt->ymd() eq $now->ymd()) ? ' staffscheduletoday' : '';
      my %aflagcount = ();
      my @special = finddateoverlap('resched_staffsch_occasion', 'starttime', 'endtime', $dt, $dt->clone()->add( days => 1 ));
      if (not $input{showcanceled}) {
        @special = grep { not $$_{flags} =~ /$cancelflag/ } @special;
      }
      if ($input{requireflag}) {
        for my $rflag (grep { $_ and /\w/ } split //, $input{requireflag}) {
          $reqflag{$rflag}++;
          @special = grep { $$_{flags} =~ /$rflag/ } @special;
        }
      } else {
        @special = grep { not $$_{flags} =~ /$separateschedule/ } @special;
      }
      if ($input{staffid}) {
        @special = grep { $$_{staffid} eq $input{staffid} } @special;
      }
      if (($input{location}) and ($input{strictlocation})) {
        @special = grep { $$_{location} eq $input{location} } @special;
      } elsif ($input{location}) {
        @special = grep { (not $$_{location}) or ($$_{location} eq $input{location}) } @special;
      }
      my %special;
      my @item;
      push @item, (map {
        my $spc = $_;
        $special{$$spc{staffid}}++ # So ignore regularly-scheduled hours for this person (below)
          unless $$spc{flags} =~ /$partial/;# Partial exception, does not entirely replace regular hours
        my $aflags = join '', grep { $_ =~ /$aflag/ } split //, $$spc{flags};
        $aflagcount{$aflags}++ if $aflags;
        my %suppressflag = %reqflag;
        if (not (getvariable('resched', 'staff_schedule_show_redundant_flags') || 0)) {
          $suppressflag{$_}++ for grep { $_ =~ /$aflag/ } split //, $$spc{flags};
        }
        my $o = formatoccasion($spc, suppressdate => 1, suppressflag => \%suppressflag );
        [qq[<div class="staffschedulehours specialhours">$o</div>], $$spc{starttime}, $$spc{endtime}, $aflags];
      } @special);
      my @regular = grep {
        ($$_{dow} eq $dt->dow())
          and
        (not $special{$$_{staffid}})
          and
        ((not $$_{obsolete}) or ($$_{obsolete} gt $dt->ymd()))
          and
        ($$_{effective} le $dt->ymd())
      } getrecord('resched_staffsch_regular');
      if ($input{requireflag}) {
        for my $rflag (grep { $_ and /\w/ } split //, $input{requireflag}) {
          @regular = grep { $$_{flags} =~ /$rflag/ } @regular;
        }
      } else {
        @regular = grep { not $$_{flags} =~ /$separateschedule/ } @regular;
      }

      push @item, map {
        my $rh = $_;
        my $aflags = join '', grep { $_ =~ /$aflag/ } split //, $$rh{flags};
        $aflagcount{$aflags}++ if $aflags;
        my $suppressflag = %reqflag;
        if (not (getvariable('resched', 'staff_schedule_show_redundant_flags') || 0)) {
          $suppressflag{$_}++ for grep { $_ =~ /$aflag/ } split //, $$rh{flags};
        }
        [qq[<div class="staffschedulehours regularhours">] . formatreghours($rh, suppressdow => 1,
                                                                                 suppressflag => \%suppressflag,
                                                                           ) . qq[</div>],
         DateTime::Format::ForDB(DateTime->new(year      => $dt->year,
                                               month     => $dt->month,
                                               day       => $dt->mday,
                                               hour      => ($$rh{starthour} || 0),
                                               minute    => ($$rh{startmin} || 0),
                                               time_zone => $localtimezone, )),
         DateTime::Format::ForDB(DateTime->new(year      => $dt->year,
                                               month     => $dt->month,
                                               day       => $dt->mday,
                                               hour      => ($$rh{endhour} || 0),
                                               minute    => ($$rh{endmin} || 0),
                                               time_zone => $localtimezone, )),
         $aflags,
        ];
      } @regular;
      if ($input{sortby} eq 'time') {
        @item = sort { ($$a[1] cmp $$b[1]) or ($$a[2] cmp $$b[2]) } @item;
      } else { # default: sort by "additional-schedule" flags:
        for my $fc (keys %aflagcount) {
          my ($fr) = grep { $$_{flagchar} eq $fc } findrecord('resched_staffsch_flag', 'flagchar', $fc);
          my $fn   = (ref $fr) ? (qq[<div class="altschedulename">] . encode_entities($$fr{shortdesc}) . qq[:</div>]) : '';
          push @item, [qq[$fn], '', '', $fc];
        }
        @item = sort { $$a[3] cmp $$b[3] or $$a[1] cmp $$b[1] or $$a[2] cmp $$b[2] } @item;
      }
      my $items = ((ref $closedrec) and getvariable('resched', 'staff_schedule_suppress_hours_when_closed')) ? '<!-- no staff hours because closed -->'
        : join "\n         ", map { $$_[0] } @item;
      my $resaux = '';
      for my $res (grep { $$_{flags} =~ /S/ } getrecord('resched_resources')) {
        my $resname = $$res{name}    || "Resource $$res{id}";
        my $bgrec   = $$res{bgcolor} ? (scalar getrecord('resched_booking_color', $$res{bgcolor})) : undef;
        my $css     = $input{usestyle} || 'lowcontrast';
        my %bgfn    = ( darkonlight => 'lightbg', lightondark => 'darkbg', 'lowcontrast' => 'lowcontrastbg');
        my $resbg   = (ref $bgrec) ? $$bgrec{$bgfn{$css}} : 'inherit';
        my @booking = finddateoverlap('resched_bookings', 'fromtime', 'until', $dt, $dt->clone()->add( days => 1 ), 'resource', $$res{id});
        if (scalar @booking) {
          $resaux .= qq[<div class="altschedule staffschedauxres" style="background-color: $resbg;">
             <div class="altschedulename">$resname</div>
          ] . (join "\n          ", map {
            my $booking   = $_;
            my $fromtime  = include::twelvehourtimefromdt(DateTime::From::MySQL($$booking{fromtime}));
            qq[<div class="resbooking"><span class="bookedfor">$$booking{bookedfor}</span> <span class="fromtime">$fromtime</span></div>];
          } @booking) . qq[</div>];
        }
      }
      push @day, qq[<div class="ilb staffscheduleday$tday">
                    <div class="h scheduledate"><span class="scheduledatedow">$dow</span><span class="punctuation">,</span>
                             <span class="scheduledatemonth">$mon</span>
                             <span class="scheduledatemday">$mday</span></div>
                    $closed
                    $items
                    $resaux
                    </div>];
    }
    $dt = $dt->add( days => 1 );
  }
  my @week;
  while (@day) {
    my @d = map { (scalar @day) ? (shift @day) : '' } 1 .. 7;
    push @week, qq[<div class="staffscheduleweek">] . (join "\n", @d) . qq[</div>]
  }
  return $issepsch . join "\n", @week, $sepschnote, intervalform($startdt, $enddt->clone()->subtract( days => 1 ));
}

sub custominterval {
  my %input = %{DateTime::NormaliseInput(\%input)};
  my ($st)  = $input{intervalstart_datetime} || $now->clone();
  my ($et)  = $input{intervalend_datetime}   || $now->clone();
  if ($et->ymd() gt $st->ymd()) {
    while ((($st->dow()) % 7) ne (getvariable('resched', 'staff_schedule_first_day_of_week') || 0)) {
      $st = $st->subtract( days => 1 );
    }
  }
  return showinterval($st, $et->add( days => 1 ));
}

sub intervalform {
  my ($startdt, $enddt, %option) = @_;
  my $start = DateTime::Form::Fields($startdt, 'intervalstart', undef, 'skiptime', undef, layout => 'compactilb',
                                     time_list_quarter_hours_first => getvariable('resched', 'time_list_quarter_hours_first'));
  my $end   = DateTime::Form::Fields($enddt,   'intervalend',   undef, 'skiptime', undef, layout => 'compactilb',
                                     time_list_quarter_hours_first => getvariable('resched', 'time_list_quarter_hours_first'));
  my $rflag = $input{requireflag} ? qq[<input type="hidden" name="requireflag" value="$input{requireflag}" />] : '';
  return qq[<form class="intervalform box" action="staffsch.cgi" method="post">
  <input type="hidden" name="action" value="showinterval" />\n  $rflag
  $hiddenpersist
  <div class="intervalstart ilb"><label for="intervalstart_datetime_day">Show schedule from</label> $start</div>
  <div class="intervalend ilb"><label for="intervalend_datetime_day">through</label> $end</div>
  <input type="submit" value="Use These Dates" />
</form>];
}

sub formatlocation {
  my ($lr) = @_;
  return '' if getvariable('resched', 'staff_schedule_suppress_locations');
  return qq[<abbr title="] . encode_entities($$lr{description})
       . qq[">] . encode_entities($$lr{briefname}) . qq[</abbr>];
}

sub maybeupdatestaffhours {
  my $sr = getrecord('resched_staff', include::getnum('staffid'));
  return qq[<div class="error"><div class="h">Error: Staff Record Not Found</div>
       I cannot seem to find staff record id <q>$input{staffid}</q> in the database.</div>] if not ref $sr;
  if (($user{flags} =~ /A/) or ($$sr{userid} eq $user{id}) or getvariable('resched', 'staff_schedule_lax_security')) {
    return updatestaffhours($sr);
  } else {
    my $detail = '';
    if ($$sr{userid}) {
      my $urec = getrecord('users', $$sr{userid});
      $detail = qq[ (in this case, $$urec{username}&nbsp;&mdash; you are currently logged in as $user{username})];
    }
    return qq[<div class="error"><div class="h">Error: Not Authorized</div>
    To edit a staff schedule, you must be logged in either as an
    administrator or as the same person whose schedule you are trying to edit$detail.</div>];
  }
}

sub maybeeditstaffhours {
  my $sr = getrecord('resched_staff', include::getnum('staffid'));
  return qq[<div class="error"><div class="h">Error: Staff Record Not Found</div>
       I cannot seem to find staff record id <q>$input{staffid}</q> in the database.</div>] if not ref $sr;
  if (($user{flags} =~ /A/) or ($$sr{userid} eq $user{id}) or getvariable('resched', 'staff_schedule_lax_security')) {
    return editstaffhours($sr);
  } else {
    my $detail = '';
    if ($$sr{userid}) {
      my $urec = getrecord('users', $$sr{userid});
      $detail = qq[ (in this case, $$urec{username}&nbsp;&mdash; you are currently logged in as $user{username})];
    }
    return qq[<div class="error"><div class="h">Error: Not Authorized</div>
    To edit a staff schedule, you must be logged in either as an
    administrator or as the same person whose schedule you are trying to edit$detail.</div>];
  }
}

sub maybeupdateoccasionhours {
  my $sr = getrecord('resched_staff', include::getnum('staffid'));
  return qq[<div class="error"><div class="h">Error: Staff Record Not Found</div>
       I cannot seem to find staff record id <q>$input{staffid}</q> in the database.</div>] if not ref $sr;
  if (($user{flags} =~ /A/) or ($$sr{userid} eq $user{id}) or getvariable('resched', 'staff_schedule_lax_security')) {
    return updateoccasionhours($sr);
  } else {
    my $detail = '';
    if ($$sr{userid}) {
      my $urec = getrecord('users', $$sr{userid});
      $detail = qq[ (in this case, $$urec{username}&nbsp;&mdash; you are currently logged in as $user{username})];
    }
    return qq[<div class="error"><div class="h">Error: Not Authorized</div>
    To edit a staff schedule, you must be logged in either as an
    administrator or as the same person whose schedule you are trying to edit$detail.</div>];
  }
}

sub maybeeditoccasionhours {
  my $sr = getrecord('resched_staff', include::getnum('staffid'));
  return qq[<div class="error"><div class="h">Error: Staff Record Not Found</div>
       I cannot seem to find staff record id <q>$input{staffid}</q> in the database.</div>] if not ref $sr;
  if (($user{flags} =~ /A/) or ($$sr{userid} eq $user{id}) or getvariable('resched', 'staff_schedule_lax_security')) {
    return editoccasionhours($sr);
  } else {
    my $detail = '';
    if ($$sr{userid}) {
      my $urec = getrecord('users', $$sr{userid});
      $detail = qq[ (in this case, $$urec{username}&nbsp;&mdash; you are currently logged in as $user{username})];
    }
    return qq[<div class="error"><div class="h">Error: Not Authorized</div>
    To edit a staff schedule, you must be logged in either as an
    administrator or as the same person whose schedule you are trying to edit$detail.</div>];
  }
}

sub maybeupdateregularhours {
  my $sr = getrecord('resched_staff', include::getnum('staffid'));
  return qq[<div class="error"><div class="h">Error: Staff Record Not Found</div>
       I cannot seem to find staff record id <q>$input{staffid}</q> in the database.</div>] if not ref $sr;
  if (($user{flags} =~ /A/) or ($$sr{userid} eq $user{id}) or getvariable('resched', 'staff_schedule_lax_security')) {
    return updateregularhours($sr);
  } else {
    my $detail = '';
    if ($$sr{userid}) {
      my $urec = getrecord('users', $$sr{userid});
      $detail = qq[ (in this case, $$urec{username}&nbsp;&mdash; you are currently logged in as $user{username})];
    }
    return qq[<div class="error"><div class="h">Error: Not Authorized</div>
    To edit a staff schedule, you must be logged in either as an
    administrator or as the same person whose schedule you are trying to edit$detail.</div>];
  }
}

sub maybeeditregularhours {
  my $sr = getrecord('resched_staff', include::getnum('staffid'));
  return qq[<div class="error"><div class="h">Error: Staff Record Not Found</div>
       I cannot seem to find staff record id <q>$input{staffid}</q> in the database.</div>] if not ref $sr;
  if (($user{flags} =~ /A/) or ($$sr{userid} eq $user{id}) or getvariable('resched', 'staff_schedule_lax_security')) {
    return editregularhours($sr);
  } else {
    my $detail = '';
    if ($$sr{userid}) {
      my $urec = getrecord('users', $$sr{userid});
      $detail = qq[ (in this case, $$urec{username}&nbsp;&mdash; you are currently logged in as $user{username})];
    }
    return qq[<div class="error"><div class="h">Error: Not Authorized</div>
    To edit a staff schedule, you must be logged in either as an
    administrator or as the same person whose schedule you are trying to edit$detail.</div>];
  }
}

sub updatestaffhours {
  # This is kind of cheating, but it's easy:
  updateoccasionhours();
  updateregularhours();
  return editstaffhours();
}



sub updateoccasionhours {
  my %input = %{DateTime::NormaliseInput(\%input)};
  #use Data::Dumper; warn Dumper(+{ input => { map { $_ => qq[$input{$_}] } keys %input}});
  my $debugrecur = '';
  my $sr = getrecord('resched_staff', include::getnum('staffid'));
  return qq[<div class="error"><div class="h">Staff Not Found</div> I cannot seem to find staff record ID <q>$input{staffid}</q> in the database</div>]
    if not ref $sr;
  for my $n (map { /^occasion(\d+)/; $1 } grep { /^occasion\d+$/ } keys %input) {
    $debugrecur .= "[uco: $n]";
    my $id = include::getnum(qq[ohid$n]);
    my $r  = +{ staffid => $$sr{id} };
    if ($id) {
      $r = getrecord('resched_staffsch_occasion', $id);
      return qq[<div class="error"><div class="h">Schedule Record Not Found</div> I cannot seem to find the staff schedule record id <q>$input{"ohid$n"}</q> in the database.</div>]
        if not ref $r;
    }
    $$r{starttime} = DateTime::Format::ForDB($input{qq[starttime${n}_datetime]}) if ref $input{qq[starttime${n}_datetime]};
    $$r{endtime}   = DateTime::Format::ForDB($input{qq[endtime${n}_datetime]})   if ref $input{qq[endtime${n}_datetime]};
    if (not getvariable('resched', 'staff_schedule_suppress_locations')) {
      my $locid      = include::getnum(qq[location$n]);
      my $lr         = $locid ? getrecord('resched_staffsch_location', $locid) : $wherever;
      $$r{location}  = $$lr{id} if ref $lr;
    }
    $$r{flags}     = join '', map { $$_{flagchar}
                                  } grep {
                                    $input{qq[flag$$_{flagchar}$n]}
                                  } grep {
                                    (not $$_{obsolete}) or ($dbnow lt $$_{obsolete})
                                  } getrecord('resched_staffsch_flag');
    $$r{comment} = $input{"occsncomment$n"};
    if ($id) {
      updaterecord('resched_staffsch_occasion', $r);
    } else {
      $debugrecur .= "[uco: new]";
      $$r{createdts} = $dbnow;
      addrecord('resched_staffsch_occasion', $r);
      my $firstoccasion = getrecord('resched_staffsch_occasion', $db::added_record_id);
      if ($input{recurtype}) {
        $debugrecur .= "[uco: recur]";
        my ($startdow, $enddow, $startcnt, $endcnt, @rdate);
        my $findnext   = sub{ die "Fallthrough: findnext->() not specified for events scheduled '$input{recurtype}'." };
        my $startdt    = $input{qq[starttime${n}_datetime]} || $now;
        my $enddt      = $input{qq[endtime${n}_datetime]}   || $startdt->add( hours => 1 );
        my $duration   = $enddt - $startdt;
        $debugrecur   .= "recur: [type: $input{recurtype}]";
        if ($input{recurtype} =~ /(daily|weekly|monthly|quarterly|annually)(?!nthdow)/) {
          my $freq = $1; $debugrecur .= "[freq: $freq]";
          my %add  = ( daily     => [ days   => 1],
                       weekly    => [ days   => 7],
                       monthly   => [ months => 1],
                       quarterly => [ months => 3],
                       annually  => [ years  => 1],
                     );
          my ($unit, $number) = @{$add{$freq}};
          $debugrecur .= "[unit '$unit', number $number]";
          $findnext = sub {
            my ($prevdt) = @_;
            $debugrecur .= "[findnext: incrementing $unit by $number]";
            my $nextdt = $prevdt->clone()->add( $unit => $number );
            return $nextdt;
          };
        } elsif ($input{recurtype} =~ /(nthdow|quarterlynthdow)/) {
          my $freq = $1; $debugrecur .= "[freq: $freq]";
          my %addmonths = ( nthdow => 1, quarterlynthdow => 3, );
          $startdow = $startdt->dow();
          $startcnt = 0;
          my $tempdt = $startdt->clone();
          while ($tempdt->month() eq $startdt->month()) {
            $startcnt++;
            $tempdt = $tempdt->subtract( days => 7 );
          }
          $debugrecur .= "[startdow: $startdow][startcnt: $startcnt]";
          $findnext = sub {
            my ($prevdt) = @_;
            my $nextdt = $prevdt->clone()->add( months => $addmonths{$input{recurtype}} )->set( day => 1 );
            $debugrecur .= "[findnext: looking for day $startdow of week $startcnt (sort of), after $addmonths{$input{recurtype}} month(s), going from " . $nextdt->ymd() . "]";
            while ($nextdt->dow() ne $startdow) {
              $nextdt = $nextdt->add( days => 1 );
              $debugrecur .= ".";
            }
            for (1 .. ($startcnt - 1)) {
              $nextdt = $nextdt->add( days => 7 );
              $debugrecur .= "w";
            }
            return $nextdt;
          };
        } elsif ($input{recurtype} eq 'listed') {
          $debugrecur .= '[listed]';
          for my $num (map { /recurlistmday(\d+)/; $1 } grep { /^recurlistmday/ } keys %input) {
            my $year  = $input{qq[recurlistyear$num]};
            my $month = $input{qq[recurlistmonth$num]};
            my $mday  = $input{qq[recurlistmday$num]};
            push @rdate, DateTime->new( year      => $year,
                                        month     => $month,
                                        day       => $mday,
                                        hour      => $startdt->hour(),
                                        minute    => $startdt->minute(),
                                        time_zone => $localtimezone,
                                      );
            $findnext = sub {
              my $nextdate = shift @rdate;
              $debugrecur .= '[findnext: shift]';
              if (ref $nextdate) { return $nextdate; }
              return qq[<div class="error">Oops, I seem to have run out of dates.</div>];
            };
          }
        } else {
          die "Unknown recurtype: '$input{recurtype}' ($debugrecur)";
        }
        # Now we just read off the startdates using findnext(), calcuate the enddates by adding the duration:
        my $dt = $startdt;
	my $addrecur = sub { my ($start, $end) = (@_);
			     addrecord('resched_staffsch_occasion',
				       +{ staffid   => $$sr{id},
					  starttime => $start,
					  endtime   => $end,
					  location  => $$firstoccasion{location},
					  flags     => ($$firstoccasion{flags} . 'C'),
					  comment   => $$firstoccasion{comment},
					  createdts => $dbnow,
					});
			   };
        if ($input{recurtype} eq 'listed') {
          $debugrecur .= '[listed]';
          while (scalar @rdate) {
            $debugrecur .= '[while: ' . (scalar @rdate) . ']';
            $dt = $findnext->($dt);
            $debugrecur .= '[' . (scalar @rdate) . ' left]';
            $addrecur->(DateTime::Format::ForDB($dt->clone()),
			DateTime::Format::ForDB($dt->clone()->add_duration($duration)));
            $debugrecur .= "[id: $db::added_record_id]";
          }
        } elsif ($input{recurstyle} eq 'ntimes') {
          $debugrecur .= '[ntimes]';
          for (1 .. $input{recurtimes}) {
            $debugrecur .= "[for: $_]";
            $dt = $findnext->($dt);
	    $addrecur->(DateTime::Format::ForDB($dt->clone()),
			DateTime::Format::ForDB($dt->clone()->add_duration($duration)));
            $debugrecur .= "[id: $db::added_record_id]";
          }
        } elsif ($input{recurstyle} eq 'until') {
          $debugrecur .= '[until]';
          my $until;
          eval {
            $debugrecur .= "[eval: start][year: $input{recuruntilyear}][month: $input{recuruntilmonth}][day: $input{recuruntilmday}]";
            $until = DateTime->new( year  => $input{recuruntilyear},
                                    month => $input{recuruntilmonth},
                                    day   => $input{recuruntilmday},
                                  )->ymd();
            $debugrecur .= '[dt.ok]';
          };$debugrecur   .= "[posteval: $until]";
          $until or return qq[<div class="error">Sorry, I'm not sure when to schedule that until.  My date parsing has failed.
                                    (You said: year '$input{recuruntilyear}', month '$input{recuruntilmonth}', day '$input{recuruntilday}'.)
                <!-- $debugrecur (] . (warn $debugrecur) . qq[) --></div>];
          $debugrecur .= "[until is true: $debugrecur]";
          $dt = $findnext->($dt);
          while ($dt->ymd() le $until) {
            $debugrecur .= '[while: ' . $dt->ymd() . ']';
	    $addrecur->(DateTime::Format::ForDB($dt->clone()),
			DateTime::Format::ForDB($dt->clone()->add_duration($duration)));
            $dt = $findnext->($dt);
            $debugrecur .= '[next: ' . $dt->ymd() . ']';
          }
        } else {
          return qq[<div class="error">Sorry, I'm not sure how many times to schedule that.<!-- recurstyle '$input{recurstyle}', recurtype '$input{recurtype}', debug '$debugrecur' --></div>];
        }
        warn "[done with recur: $debugrecur]" if $debug;
      }
    }
  }
  return editoccasionhours($sr);
}

sub occasionhoursform {
  my ($r, $n) = @_;
  my $startdt = $$r{starttime} ? DateTime::From::MySQL($$r{starttime})
    : DateTime->new( time_zone => $localtimezone,
                     year => $now->year(), month => $now->month(), day => $now->mday(),
                     hour => 9, minute => 0, );
  my $enddt = $$r{endtime} ? DateTime::From::MySQL($$r{endtime})
    : DateTime->new( time_zone => $localtimezone,
                     year => $now->year(), month => $now->month(), day => $now->mday(),
                     hour => 17, minute => 0, );
  my $start = DateTime::Form::Fields($startdt, "starttime$n", undef, undef, undef, layout => 'compactilb',
                                     time_list_quarter_hours_first => getvariable('resched', 'time_list_quarter_hours_first'),
                                     copydate => ($startdt->ymd() eq $enddt->ymd() ? "endtime$n" : undef) );
  my $end   = DateTime::Form::Fields($enddt,   "endtime$n",   undef, undef, undef, layout => 'compactilb',
                                     time_list_quarter_hours_first => getvariable('resched', 'time_list_quarter_hours_first') );
  my $idfield   = $$r{id} ? qq[<input type="hidden" name="ohid$n" value="$$r{id}" />] : '';
  my $locsel    = getvariable('resched', 'staff_schedule_suppress_locations')
    ? '' : include::orderedoptionlist("location$n", [
                                                     map { [$$_{id} => encode_entities($$_{briefname})]
                                                         } ($wherever,
                                                            grep { not /X/ } getrecord('resched_staffsch_location'))
                                                    ],
                                      ($$r{location} || 0));
  my $comment   = encode_entities($$r{comment});
  my $next      = $n + 1;
  my $flags     = occasionflagcheckboxes($n, ($$r{flags} || ''));
  my $multiday  = ($enddt->ymd() ne $startdt->ymd()) ? ' multiday' : '';
  # fields: id, staffid, starttime, endtime, location, flags
  return qq[<div class="occasionhoursinstance">
    <div class="ilb$multiday">$idfield
       <input type="hidden" name="occasion$n" value="occasion$n" />
       <div class="ilb"><label for="starttime${n}_datetime_day">From</label> $start</div>
       <div class="ilb"><label for="endtime${n}_datetime_day">To</label> $end</div>
       <div class="ilb">$locsel</div>
       <div class="ilb hoursinstanceflags">$flags</div>
       <div class="ilb hoursinstancecomment"><label for="occsncomment$n">Comment:</label> <input type="text" size="30" name="occsncomment$n" id="occsncomment$n" value="$comment" /></div>
    </div>
       </div>];
}

sub occasionflagcheckboxes {
  my ($n, $flags) = @_;
  $flags ||= '';
  return join "\n                  ", map {
    my $f = $_;
    my $long    = encode_entities($$f{longdesc});
    my $short   = encode_entities($$f{shortdesc});
    my $checked = ($flags =~ /$$f{flagchar}/) ? ' checked="checked"' : '';
    my $disable = ($$f{flags} =~ /D/) ? ' disabled="disabled"' : '';
    ($checked or not $disable)
      ? qq[<input type="checkbox" id="flag$$f{flagchar}$n" name="flag$$f{flagchar}$n"$checked$disable />
                  <label for="flag$$f{flagchar}${n}"><abbr title="$long">$short</abbr></label>] : '';
  } grep {
    ((not ($$_{flags} =~ /R/)) or ($$_{flags} =~ /O/))
  } grep {
    (not $$_{obsolete}) or ($dbnow lt $$_{obsolete})
  } getrecord('resched_staffsch_flag');
}

sub addoccasionhours {
  my $num   = include::getnum('number');
  my $next  = $num + 1;
  my $blank = occasionhoursform(+{ }, $num);
  return qq[<div>
     $blank
     <div id="eohadd$next" class="occasionhoursinstance addmore"><a href="javascript: sendajaxrequest('action=addoccasionhours&amp;number=$next&amp;ajaxreplace=eohadd$next', 'staffsch.cgi')">Add More</a></div>
  </div>];
}

sub editstaffhours {
  my ($sr) = @_;
  $sr ||= getrecord('resched_staff', include::getnum('staffid'));
  ref $sr or return qq[<div class="error"><div class="h">Error: No Staff Record Found</div>
      I cannot seem to find staff ID <q>$input{staffid}</q> in the database.</div>];
  my $sname   = formatshortname($sr);
  my $count = 0;

  my $cutoff  = (include::getnum('sstart_datetime_day'))
    ? DateTime->new( time_zone => $localtimezone,
                     year  => (include::getnum('sstart_datetime_year')  || $now->year()),
                     month => (include::getnum('sstart_datetime_month') || $now->month()),
                     day   => include::getnum('sstart_datetime_day'),   )
    : $now;

  my @regular = grep { (not defined $$_{obsolete}) or ($$_{obsolete} gt $cutoff->ymd())
                     } findrecord('resched_staffsch_regular', 'staffid', $$sr{id});
  my %aflagcount = ();
  if ($input{sortby} eq 'time') {
    @regular = sort { $$a{dow} <=> $$b{dow} } @regular;
  } elsif ($input{sortby} eq 'aflags') {
    my $aflagpattern = (join '|', map { $$_{flagchar}
                                      } grep { $$_{flags} =~ /A/
                                             } getrecord('resched_staffsch_flag')) || '__NOMATCH__';
    #warn " aflag pattern: $aflagpattern\n";
    @regular = map { $$_[0]
                   } sort {
                     $$a[1] cmp $$b[1] or $$a[0]{dow} <=> $$b[0]{dow}
                   } map {
                     my $r = $_;
                     my $aflags = join '', (sort { $a cmp $b
                                                 } grep {
                                                   $_ =~ /$aflagpattern/
                                                 } split //, $$r{flags});
                     $aflagcount{$aflags}++ if $aflags;
                     #warn "  aflags ($$r{flags}): $aflags\n";
                     [$r => $aflags]
                   } @regular;
  } else { # default sort on the unified regular/occasion form is by time (within each category):
    @regular = sort { $$a{dow} <=> $$b{dow} } @regular;
  }

  my $extantreg = join "\n        ", map {
    (ref $_) ? reghoursform($_, ++$count, 'erh') : qq[<hr class="altschedulesep" />];
  } @regular;
  my $next = $count + 1;
  $hiddenpersist = persist('hidden', [qw(category magicdate)], [qw(sstart_datetime_year sstart_datetime_month sstart_datetime_day)]);
  my $viewlink = $optn{justsaved} ? qq[<div class="p"><a class="button" href="staffsch.cgi?action=staffschedule&amp;staffid=$$sr{id}&amp;$persistentvars">View Schedule</a> for $sname</div>] : '';

  my @occasion = sort {
    $$a{starttime} cmp $$b{starttime} or $$a{endtime} cmp $$b{endtime}
  } grep {
    $$_{staffid} eq $$sr{id}
  } getsince('resched_staffsch_occasion', 'endtime', $cutoff);
  # fields: id, staffid, starttime, endtime, location, flags
  $count += 65535;
  my $extantocc = join "\n         ", map {
    occasionhoursform($_, ++$count);
  } @occasion;
  my $next = $count + 1;
  $hiddenpersist = persist('hidden', [qw(category magicdate)], [qw(sstart_datetime_year sstart_datetime_month sstart_datetime_day)]);
  return qq[<form class="staffscheduleform" action="staffsch.cgi" method="post"><!-- cutoff: ] . $cutoff->ymd() . qq[ -->
      <input type="hidden" name="action" value="updatestaffhours" />
      <input type="hidden" name="staffid" value="$$sr{id}" />
      $hiddenpersist

      <div class="h"><strong>Regular</strong> Schedule for $sname:</div><hr />
      <div>
        <div class="extant">
          $extantreg</div>
        <div id="erhadd$next" class="reghoursinstance addmore"><a href="javascript: sendajaxrequest('action=addregularhours&amp;number=$next&amp;ajaxreplace=erhadd$next', 'staffsch.cgi');">Add Regular Hours</a></div>
        <div><input type="submit" value="Save Changes" /></div>
      </div>
      <hr />
      <div class="h">Scheduled Hours for $sname on <strong>Specific Dates</strong>:</div><hr />
      <div>
        <div class="extant">
           $extantocc</div>
        <div id="eohadd$next" class="occasionhoursinstance addmore"><a href="javascript: sendajaxrequest('action=addoccasionhours&amp;number=$next&amp;ajaxreplace=eohadd$next', 'staffsch.cgi')">Add Hours on a Specific Date</a>
             <div><a href="staffsch.cgi?action=inputrecurocchours&amp;staffid=$$sr{id}&amp;$persist">Add Recurring Events</a></div>
             </div>
        <div><input type="submit" value="Save Changes" /></div>
      </div>
    </form>\n    $viewlink\n];
}

sub editoccasionhours {
  my ($sr) = @_;
  $sr ||= getrecord('resched_staff', include::getnum('staffid'));
  ref $sr or return qq[<div class="error"><div class="h">Error: No Staff Record Found</div>
      I cannot seem to find staff ID <q>$input{staffid}</q> in the database.<!-- editoccasionhours --></div>];
  my $sname   = formatshortname($sr);
  my $cutoff  = (include::getnum('sstart_datetime_day'))
    ? DateTime->new( time_zone => $localtimezone,
                     year  => (include::getnum('sstart_datetime_year')  || $now->year()),
                     month => (include::getnum('sstart_datetime_month') || $now->month()),
                     day   => include::getnum('sstart_datetime_day'),   )
    : $now;
  my @occasion = sort {
    $$a{starttime} cmp $$b{starttime} or $$a{endtime} cmp $$b{endtime}
  } grep {
    $$_{staffid} eq $$sr{id}
  } getsince('resched_staffsch_occasion', 'endtime', $cutoff);
  # fields: id, staffid, starttime, endtime, location, flags
  my $count = 0;
  my $extant = join "\n         ", map {
    occasionhoursform($_, ++$count);
  } @occasion;
  my $next = $count + 1;
  $hiddenpersist = persist('hidden', [qw(category magicdate)], [qw(sstart_datetime_year sstart_datetime_month sstart_datetime_day)]);
  return qq[<form class="staffscheduleform" action="staffsch.cgi" method="post">
    <input type="hidden" name="action"  value="updateoccasionhours" />
    <input type="hidden" name="staffid" value="$$sr{id}" />
    $hiddenpersist
    <div class="h">Schedule Exceptions for $sname:</div><hr />
    <div>
      <div class="extant">
         $extant</div>
      <div id="eohadd$next" class="occasionhoursinstance addmore"><a href="javascript: sendajaxrequest('action=addoccasionhours&amp;number=$next&amp;ajaxreplace=eohadd$next', 'staffsch.cgi')">Add More</a></div>
      <div><input type="submit" value="Save Changes" /></div>
    </div>
  </form>];
}

sub inputrecurocchours {
  my ($sr) = @_;
  $sr ||= getrecord('resched_staff', include::getnum('staffid'));
  ref $sr or return qq[<div class="error"><div class="h">Error: No Staff Record Found</div>
      I cannot seem to find staff ID <q>$input{staffid}</q> in the database.<!-- inputrecurocchours --></div>];
  my $sname   = formatshortname($sr);
  my $startdt = DateTime->new( time_zone => $localtimezone,
                               year => $now->year(), month => $now->month(), day => $now->mday(),
                               hour => 9, minute => 0, );
  my $enddt   = DateTime->new( time_zone => $localtimezone,
                               year => $now->year(), month => $now->month(), day => $now->mday(),
                               hour => 17, minute => 0, );
  my $start   = DateTime::Form::Fields($startdt, "starttime1", undef, undef, undef, layout => 'compactilb',
                                       copydate => ($startdt->ymd() eq $enddt->ymd() ? "endtime1" : undef),
                                       time_list_quarter_hours_first => getvariable('resched', 'time_list_quarter_hours_first'), );
  my $end     = DateTime::Form::Fields($enddt,   "endtime1",   undef, undef, undef, layout => 'compactilb',
                                       time_list_quarter_hours_first => getvariable('resched', 'time_list_quarter_hours_first') );
  my $locsel  = getvariable('resched', 'staff_schedule_suppress_locations')
    ? '' : include::orderedoptionlist("location1", [
                                                    map { [$$_{id} => encode_entities($$_{briefname})]
                                                        } ($wherever,
                                                           grep { not /X/ } getrecord('resched_staffsch_location'))
                                                   ],
                                      0);
  my $flags  = occasionflagcheckboxes(1);
  my $monthoptions = join "\n                        ", map {
    my $monthnum = $_;
    my $dt = DateTime->new( year => 1974, month => $monthnum , day => 7);
    warn "Blurgle-Argh-Aaarghh-Blargh-Blarghle-Fazoop" if not ref $dt;
    my $selected = (($dt->month() == $now->month())?qq[ selected="selected"]:"");
    (qq[<option value="$_"$selected>].($dt->month_abbr)."</option>")
  } (1 .. 12);
  return qq[<form class="staffscheduleform recuroccform" action="staffsch.cgi" method="post">
    <input type="hidden" name="action"  value="updatestaffhours" />
    <input type="hidden" name="staffid" value="$$sr{id}" />
    <div class="h">Schedule Recurring Event for $sname:</div><hr />
    <div class="occasionhoursinstance">
      <input type="hidden" name="occasion1" value="occasion1" />
      <div class="ilb">
        <div class="ilb"><label for="starttime1_datetime_day">From</label> $start</div>
        <div class="ilb"><label for="endtime1_datetime_day">To</label> $end</div>
        <div class="ilb">$locsel </div>
        <div class="ilb">$flags </div>
        <div class="ilb"><label for="occsncomment1">Comment:</label> <input type="text" size="30" name="occsncomment1" id="occsncomment1" /></div>
      </div>
      <hr />
      <div class="ilb recurfields">
        <div class="ilb"><label for="recurformselect">Also Schedule Identical Events:</label>
            <select name="recurtype" id="recurformselect" onchange="changerecurform();">
               <option value="">Just This Once</option>
               <option value="daily">Daily</option>
               <option value="weekly">Weekly</option>
               <option value="monthly">Monthly (nth day of the month)</option>
               <option value="nthdow">Monthly (same day of the week, nth week)</option>
               <option value="quarterly">Quarterly (nth day of the month)</option>
               <option value="quarterlynthdow">Quarterly (same day of the week, nth week of the month)</option>
               <option value="listed">on the dates listed below</option>
            </select>

            <span id="recurstyles" style="display: none;">
                 <div><input type="radio" name="recurstyle" value="ntimes" id="BookTimesRadio" />Book
                      <input type="text"  name="recurtimes" size="4" value="1" onchange="document.getElementById('BookTimesRadio').checked = 'checked';" /> additional time(s).</div>
                 <div><input type="radio" name="recurstyle" value="until" id="BookThruRadio" checked="checked" />Book through
                      <input type="text" name="recuruntilyear" size="6" value="].($now->year).qq[" onchange="document.getElementById('BookThruRadio').checked = 'checked';" />
                      <select name="recuruntilmonth" onchange="document.getElementById('BookThruRadio').checked = 'checked';">].($monthoptions).qq[</select>
                      <input type="text" name="recuruntilmday" value="].($now->mday).qq[" size="4" onchange="document.getElementById('BookThruRadio').checked = 'checked';" />.</div>
               </span>

               <span id="recurlist" style="display: none;">
                   <table class="table"><thead>
                       <tr><th>year</th><th>month</th><th>day</th></tr>
                   </thead><tbody>
                       <tr><td>].$now->year."</td><td>".$now->month_abbr."</td><td>".$now->mday.qq[</td></tr>
                       <tr><td><input type="text" name="recurlistyear1" size="5" value="].$now->year.qq[" /></td>
                           <td><select id="recurlistmonth1" name="recurlistmonth1">$monthoptions</select></td>
                           <td><input type="text" name="recurlistmday1" size="3" /></td>
                       </tr>
                       <tr id="insertmorelisteddateshere" />
                   </tbody></table>
                   <input type="button" value="Add Another Date" onclick= "augmentdatelist('].($now->year).qq[');"/>
                   <p />
            </span>

        </div>
      </div>
    </div>
    <input type="submit" value="Save To Staff Schedule" />
  </form>];
}


sub updateregularhours {
  my %input = %{DateTime::NormaliseInput(\%input)};
  my $sr = getrecord('resched_staff', include::getnum('staffid'));
  return qq[<div class="error"><div class="h">Staff Not Found</div> I cannot seem to find staff record ID <q>$input{staffid}</q> in the database</div>]
    if not ref $sr;
  for my $n (map { /^dow(\d+)*/; $1 } grep { /^dow\d+$/ } keys %input) {
    my $id = include::getnum(qq[rhid$n]);
    my $r  = +{ staffid => $$sr{id} };
    if ($id) {
      $r = getrecord('resched_staffsch_regular', $id);
      return qq[<div class="error"><div class="h">Hours Record Not Found</div> I cannot seem to find the regular-hours staff schedule record id <q>$input{"rhid$n"}</q> in the database.</div>]
        if not ref $r;
    }
    $$r{effective}  = $input{qq[effective${n}_datetime]}->ymd() if ref $input{qq[effective${n}_datetime]};
    if ($input{qq[isobsolete$n]}) {
      $$r{obsolete} = $input{qq[obsolete${n}_datetime]}->ymd() if ref $input{qq[effective${n}_datetime]};
    }
    $$r{dow}       = include::getnum(qq[dow$n]);
    $$r{starthour} = include::getnum(qq[starthour$n]) || $$r{starthour};
    $$r{startmin}  = include::getnum(qq[startmin$n])  || $$r{startmin};
    $$r{endhour}   = include::getnum(qq[endhour$n])   || $$r{endhour};
    $$r{endmin}    = include::getnum(qq[endmin$n])    || $$r{endmin};
    $$r{starthour} = 0 if $$r{starthour} == 12;
    $$r{endhour}   = 0 if $$r{endhour}   == 12;
    $$r{starthour}+= 12 if $input{"startpm$n"};
    $$r{endhour}  += 12 if $input{"endpm$n"};
    if (not getvariable('resched', 'staff_schedule_suppress_locations')) {
      my $locid    = include::getnum(qq[location$n]);
      my $lr       = $locid ? getrecord('resched_staffsch_location', $locid) : $wherever;
      $$r{location}= (ref $lr) ? $$lr{id} : 0;
    }
    $$r{flags}     = join '', map { $$_{flagchar}
                                  } grep {
                                    $input{qq[flag$$_{flagchar}$n]}
                                  } grep {
                                    (not $$_{obsolete}) or ($dbnow lt $$_{obsolete})
                                  } getrecord('resched_staffsch_flag');
    if ($id) {
      updaterecord('resched_staffsch_regular', $r);
    } else {
      addrecord('resched_staffsch_regular', $r);
    }
  }
  return editregularhours($sr, justsaved => 1);
}

sub reghoursform {
  my ($r, $n, $dbg) = @_;
  my $effdt = $$r{effective} ? DateTime::From::MySQL($$r{effective}) : $now;
  my $obsdt = $$r{obsolete}  ? DateTime::From::MySQL($$r{obsolete})  : $now->clone()->add(years => 30);
  my $obsch = $$r{obsolete}  ? qq[ checked="checked"] : '';
  my $effective = DateTime::Form::Fields($effdt, "effective$n", undef, 'skiptime', undef, layout => 'compactilb',
                                         time_list_quarter_hours_first => getvariable('resched', 'time_list_quarter_hours_first'));
  my $obsolete  = qq[<input type="checkbox" name="isobsolete$n" id="isobsolete$n" $obsch />
      <label for="isobsolete$n">obsolete as of</label>
      ] . DateTime::Form::Fields($obsdt, "obsolete$n", undef, 'skiptime', undef, layout => 'compactilb',
                                 time_list_quarter_hours_first => getvariable('resched', 'time_list_quarter_hours_first'));
  my $idfield   = $$r{id} ? qq[<input type="hidden" name="rhid$n" value="$$r{id}" />]
                          : '';
  my $defdow    = $$r{dow} || ($n % 7);
  my $dowsel    = include::optionlist("dow$n", +{ 0 => 'Sundays', 1 => 'Mondays', 2 => 'Tuesdays', 3 => 'Wednesdays',
                                                  4 => 'Thursdays', 5 => 'Fridays', 6 => 'Saturdays' }, $defdow );
  my $locsel    = getvariable('resched', 'staff_schedule_suppress_locations')
    ? '' : include::optionlist("location$n", +{# ( 0 => 'wherever' ),
                                               map { $$_{id} => encode_entities($$_{briefname})
                                                   } ($wherever,
                                                      grep { not /X/ } getrecord('resched_staffsch_location'))
                                              }, $$r{location});
  my $startpm   = ($$r{starthour} >= 12) ? ' selected="selected"' : '';
  my $endpm     = ($$r{endhour} >= 12)   ? ' selected="selected"' : '';
  my $starthour = ($$r{starthour} > 12) ? ($$r{starthour} % 12) : $$r{starthour};
  my $endhour   = ($$r{endhour} > 12) ? ($$r{endhour} % 12) : $$r{endhour};
  my $startmin  = sprintf "%02d", $$r{startmin};
  my $endmin    = sprintf "%02d", $$r{endmin};
  my $next      = $n + 1;
  my $flags    = join "\n", map {
    my $f = $_;
    my $long    = encode_entities($$f{longdesc});
    my $short   = encode_entities($$f{shortdesc});
    my $checked = ($$r{flags} =~ /$$f{flagchar}/) ? ' checked="checked"' : '';
    qq[<input type="checkbox" id="flag$$f{flagchar}$n" name="flag$$f{flagchar}$n" $checked />
                  <label for="flag$$f{flagchar}$n"><abbr title="$long">$short</abbr></label>];
  } grep {
    ((not ($$_{flags} =~ /O/)) or ($$_{flags} =~ /R/))
  } grep {
    (not $$_{obsolete}) or ($dbnow lt $$_{obsolete})
  } getrecord('resched_staffsch_flag');
  return qq[<div class="reghoursinstance"><!-- [rh$$r{id}/$n/$dbg] -->
       <div class="ilb hoursinstancedetails">$idfield
         <div class="ilb">
            <div class="dowsel ilb">$dowsel</div>
            <div class="locsel ilb">$locsel</div></div>
         <div class="ilb">
            <div class="ilb"><label for="starthour$n">from</label>
                 <nobr><input type="text" size="2" name="starthour$n" id="starthour$n" value="$starthour" /><label for="startmin$n">:</label><input type="text" size="2" name="startmin$n"  id="startmin$n"  value="$startmin" />
                       <select name="startpm$n"><option value="0">am</option><option value="1"$startpm>pm</option></select></nobr></div>
            <div class="ilb"><label for="endhour$n">to</label>
                 <nobr><input type="text" size="2" name="endhour$n"   id="endhour$n"   value="$endhour"   /><label for="endmin$n">:</label><input   type="text" size="2" name="endmin$n"    id="endmin$n"    value="$endmin" />
                       <select name="endpm$n"><option value="0">am</option><option value="1"$endpm>pm</option></select></nobr></div>
            </div>
         <div class="ilb hoursinstanceflags">$flags</div>
       </div>
       <div class="ilb hoursinstanceeffectiverange">
         <div class="ilb">effective $effective</div>
         <div class="ilb">$obsolete</div>
       </div><!-- {rh$$r{id}/$n/$dbg} -->
     </div>
     ];
}

sub addregularhours {
  my $num   = include::getnum('number');
  my $blank = reghoursform(+{
                             effective => $dbnow,
                             dow       => (($num + 2) % 7),
                             starthour => 9,
                             endhour   => 17,
                            }, $num, 'arh');
  my $next = $num + 1;
  return qq[<div>
     $blank
     <div id="erhadd$next" class="reghoursinstance addmore"><a href="javascript: sendajaxrequest('action=addregularhours&amp;number=$next&amp;ajaxreplace=erhadd$next', 'staffsch.cgi');">Add More</a></div>
  </div>\n]
}

sub editregularhours {
  my ($sr, %optn) = @_;
  $sr ||= getrecord('resched_staff', include::getnum('staffid'));
  ref $sr or return qq[<div class="error"><div class="h">Error: No Staff Record Found</div>
      I cannot seem to find staff ID <q>$input{staffid}</q> in the database.</div>];
  my $sname   = formatshortname($sr);
  my $cutoff  = (include::getnum('sstart_datetime_day'))
    ? DateTime->new( time_zone => $localtimezone,
                     year  => (include::getnum('sstart_datetime_year')  || $now->year()),
                     month => (include::getnum('sstart_datetime_month') || $now->month()),
                     day   => include::getnum('sstart_datetime_day'),   )
    : $now;
  my @regular = grep { (not defined $$_{obsolete}) or ($$_{obsolete} gt $cutoff->ymd())
                     } findrecord('resched_staffsch_regular', 'staffid', $$sr{id});
  my %aflagcount = ();
  if ($input{sortby} eq 'time') {
    @regular = sort { $$a{dow} <=> $$b{dow} } @regular;
  } else { # default sort is by aflags:
    my $aflagpattern = (join '|', map { $$_{flagchar}
                                      } grep { $$_{flags} =~ /A/
                                             } getrecord('resched_staffsch_flag')) || '__NOMATCH__';
    #warn " aflag pattern: $aflagpattern\n";
    @regular = map { $$_[0]
                   } sort {
                     $$a[1] cmp $$b[1] or $$a[0]{dow} <=> $$b[0]{dow}
                   } map {
                     my $r = $_;
                     my $aflags = join '', (sort { $a cmp $b
                                                 } grep {
                                                   $_ =~ /$aflagpattern/
                                                 } split //, $$r{flags});
                     $aflagcount{$aflags}++ if $aflags;
                     #warn "  aflags ($$r{flags}): $aflags\n";
                     [$r => $aflags]
                   } @regular;
  }
  my $count = 0;
  my $extant = join "\n        ", map {
    (ref $_) ? reghoursform($_, ++$count, 'erh') : qq[<hr class="altschedulesep" />];
  } @regular;
  my $next = $count + 1;
  $hiddenpersist = persist('hidden', [qw(category magicdate)], [qw(sstart_datetime_year sstart_datetime_month sstart_datetime_day)]);
  my $viewlink = $optn{justsaved} ? qq[<div class="p"><a class="button" href="staffsch.cgi?action=staffschedule&amp;staffid=$$sr{id}&amp;$persistentvars">View Schedule</a> for $sname</div>] : '';
  return qq[<form class="staffscheduleform" action="staffsch.cgi" method="post">
      <input type="hidden" name="action" value="updateregularhours" />
      <input type="hidden" name="staffid" value="$$sr{id}" />
      $hiddenpersist
      <div class="h">Regular Schedule for $sname:</div><hr />
      <div>
        <div class="extant">
          $extant</div>
        <div id="erhadd$next" class="reghoursinstance addmore"><a href="javascript: sendajaxrequest('action=addregularhours&amp;number=$next&amp;ajaxreplace=erhadd$next', 'staffsch.cgi');">Add More</a></div>
        <div><input type="submit" value="Save Changes" /></div>
      </div>
  </form>
  $viewlink]
}

sub staffschedule {
  my $sr = getrecord('resched_staff', include::getnum('staffid'));
  ref $sr or return qq[<div class="error"><div class="h">Error: Staff Record Not Found</div>
       I cannot seem to find staff ID <q>$input{staffid}</q> in the database.</div>];
  my ($startdt, $enddt);
  if (include::getnum('sstart_datetime_day')) {
    $startdt = DateTime->new( time_zone => $localtimezone,
                              year  => (include::getnum('sstart_datetime_year')  || $now->year()),
                              month => (include::getnum('sstart_datetime_month') || $now->month()),
                              day   => include::getnum('sstart_datetime_day'),   );
  } else {
    $startdt = $now;
  }
  if (include::getnum('send_datetime_day')) {
    $enddt = DateTime->new( time_zone => $localtimezone,
                            year   => (include::getnum('send_datetime_year')  || $now->year()),
                            month  => (include::getnum('send_datetime_month') || $now->month()),
                            day    => include::getnum('send_datetime_day'),
                            hour   => 23,
                            minute => 59 );
  } else {
    $enddt = $startdt->clone()->add( months => 3 );
  }
  while ($enddt->ymd() le $startdt->ymd()) {
    $enddt = $enddt->add( months => 1 );
  }
  my $startdate = DateTime::Format::ForDB($startdt);
  my $enddate   = DateTime::Format::ForDB($enddt);
  my @regular = sort { $$a{dow} <=> $$b{dow}
                     } grep { (not $$_{obsolete}) or ($$_{obsolete} gt $startdate)
                     } findrecord('resched_staffsch_regular', 'staffid', $$sr{id});
  my @downame = qw(Sundays Mondays Tuesdays Wednesdays Thursdays Fridays Saturdays Sundays);
  my $persist = persist(undef, [qw(category magicdate)], [qw(sstart_datetime_year sstart_datetime_month sstart_datetime_day
                                                             send_datetime_year   send_datetime_month   send_datetime_day)]);
  my $editreg = (($user{flags} =~ /A/) or ($user{id} eq $$sr{userid}) or getvariable('resched', 'staff_schedule_lax_security'))
    ? qq[ <a href="staffsch.cgi?action=editstaffhours&amp;staffid=$$sr{id}&amp;$persist">[Edit Schedule]</a>] : '';
  my $regular = (scalar @regular) ? (
                                     qq[<div class="p">Regular Hours${editreg}:</div><ul class="staffreghours">]
                                     . (join "\n             ", map {
                                       qq[<li>] . formatreghours($_, verbosedow => 1, suppressname => 1, ) . qq[</li>];
                                     } @regular) . qq[</ul>]
                                    ) : qq[<div>$editreg</div>];
  my @occasion = sort { ($$a{starttime} cmp $$b{starttime}) or ($$a{endtime} cmp $$b{endtime})
                      } grep {
                        $$_{endtime} ge $startdate and $$_{starttime} le $enddate
  } findrecord('resched_staffsch_occasion', 'staffid', $$sr{id});
  @occasion = grep { not $$_{flags} =~ /X/ } @occasion unless $input{showcanceled};
  my $editocc = (($user{flags} =~ /A/) or ($user{id} eq $$sr{userid}) or getvariable('resched', 'staff_schedule_lax_security'))
    ? qq[ <a href="staffsch.cgi?action=editstaffhours&amp;staffid=$$sr{id}&amp;$persist">[Edit Schedule]</a>] : '';
  my $occasions = qq[<div>$editocc</div>];
  my $dorecur = (($user{flags} =~ /A/) or ($user{id} eq $$sr{userid}) or getvariable('resched', 'staff_schedule_lax_security'))
    ? qq[<div><a href="staffsch.cgi?action=inputrecurocchours&amp;staffid=$$sr{id}&amp;$persist">[Add Recurring Events]</a></div>] : '';
  if (scalar @occasion) {
    $occasions = qq[<div class="p">Specific Dates$editocc:</div><ul class="staffoccasionhours">]
      . (join "\n            ", map {
        qq[<li>] . formatoccasion($_, suppressname => 1, datefirst => 1) . qq[</li>];
      } @occasion) . qq[</ul>];
  }

  my $forwhom = formatshortname($sr);
  # TODO:  Add edit links when appropriate.
  my $startdateform = DateTime::Form::Fields($startdt, 'sstart', undef, 'skiptime', 'staffschedule()', layout => 'compactilb',
                                             time_list_quarter_hours_first => getvariable('resched', 'time_list_quarter_hours_first'));
  my $enddateform   = DateTime::Form::Fields($enddt,   'send',   undef, 'skiptime', 'staffschedule()', layout => 'compactilb',
                                             time_list_quarter_hours_first => getvariable('resched', 'time_list_quarter_hours_first'));
  my $snamepos      = formatshortname($sr, possessive => 1);
  my $showcanceled  = $input{showcanceled} ? ' checked="checked"' : '';
  return qq[<div class="h">Schedule for $forwhom:</div>\n$regular\n$occasions\n$dorecur
  <div class="spacer">&nbsp;</div>
  <form action="staffsch.cgi" method="post">
    <input type="hidden" name="action" value="staffschedule" />
    <input type="hidden" name="staffid" value="$$sr{id}" />
    $hiddenpersist
    <div class="ilb">
       <div class="ilb"><label for="sstartmonth">Show $snamepos schedule from</label> $startdateform</div>
       <div class="ilb"><label for="sendmonth">through</label> $enddateform</div>
    </div>
    <div class="ilb">
       <input type="checkbox" name="showcanceled" id="showcanceled" $showcanceled />
       <label for="showcanceled">Show Canceled Dates</label>
    </div>
    <input type="submit" value="Go" />
  </form>\n];
}

sub formatflag {
  my ($fr) = @_;
  my $short = encode_entities($$fr{shortdesc});
  my $long  = encode_entities($$fr{longdesc});
  return qq[<span class="flag"><abbr title="$long">$short</abbr></span>];
}

sub formatreghours {
  my ($rr, %arg) = @_;
  $arg{suppressflag} ||= +{}; # No stupid warning
  my $flags = $arg{suppressflags} ? ''
    : (join ' ', map { my $fc = $_;
                       formatflag(grep { $$_{flagchar} eq $fc } findrecord('resched_staffsch_flag', 'flagchar', $fc))
                     } grep { (not /A/) and not ${$arg{suppressflag}}{$_} } split //, $$rr{flags});
  my $where = '';
  if (not $arg{suppresslocation} and not getvariable('resched', 'staff_schedule_suppress_locations')) {
    $where = formatlocation($$rr{location} ? getrecord('resched_staffsch_location', $$rr{location}) : $wherever);
  }
  my $name = '';
  if (not $arg{suppressname}) {
    $name  = formatshortname(getrecord('resched_staff', $$rr{staffid}));
  }
  my $dow = '';
  if (not $arg{suppressdow}) {
    my %dow = ( 0 => 'Sunday', 1 => 'Monday', 2 => 'Tuesday', 3 => 'Wednesday', 4 => 'Thursday', 5 => 'Friday', 6 => 'Saturday', 7 => 'Sunday');
    if ($arg{dowtla}) {
      %dow = ( 0 => 'Sun', 1 => 'Mon', 2 => 'Tue', 3 => 'Wed', 4 => 'Thu', 5 => 'Fri', 6 => 'Sat', 7 => 'Sun');
    } elsif ($arg{dowsla}) {
      %dow = ( 0 => 'S', 1 => 'M', 2 => 'T', 3 => 'W', 4 => 'R', 5 => 'F', 6 => 's', 7 => 'S');
    } elsif ($arg{verbosedow}) {
      %dow = ( 0 => 'Most Sundays', 1 => 'Most Mondays', 2 => 'Most Tuesdays', 3 => 'Most Wednesdays', 4 => 'Most Thursdays', 5 => 'Most Fridays', 6 => 'Most Saturdays', 7 => 'Most Sundays');
    }
    $dow  = $dow{$$rr{dow}};
  }
  my $time = '';
  if (not $arg{suppresstime}) {
    my $allday = join '|', map { $$_{flagchar} } searchrecord('resched_staffsch_flag', 'flags', 'L');
    if ($allday and ($$rr{flags} =~ /$allday/)) {
      $time = 'all&nbsp;day';
    } else {
      my $fromtime = qq[$$rr{starthour}:$$rr{startmin}];
      my $endtime  = qq[$$rr{endhour}:$$rr{endmin}];
      $time  = qq[<nobr>] . include::twelvehourtime($fromtime) . qq[<!-- $fromtime --></nobr>];
      $time .= '-' . qq[<nobr>] . include::twelvehourtime($endtime) . qq[<!-- $endtime --></nobr>]
        if not $arg{suppressendtime};
      if ($time =~ /am.*am|pm.*pm/) {
        $time =~ s/\s?[ap]m//;
      }
    }
  }
  return join ' ', grep { $_ } $dow, $name, $where, $date, $time, $flags;
}

sub formatoccasion {
  my ($or, %arg) = @_;
  $arg{suppressflag} ||= +{}; # No stupid warning
  my $flags = $arg{suppressflags} ? ''
    : join ' ', map { my $fc = $_;
                      "<!-- $_ -->" . formatflag(grep { ($$_{flagchar} eq $fc) and not ($$_{flags} =~ /H/)
                                                      } findrecord('resched_staffsch_flag', 'flagchar', $fc))
                    } grep { (not /A/) and not ${$arg{suppressflag}}{$_} } split //, $$or{flags};
  my $name = '';
  if (not $arg{suppressname}) {
    $name  = formatshortname(getrecord('resched_staff', $$or{staffid}));
  }
  my $sdt = DateTime::From::MySQL($$or{starttime});
  my $edt = DateTime::From::MySQL($$or{endtime});
  my $class = ($sdt->ymd() ne $edt->ymd()) ? qq[occasion multidayoccasion] : 'occasion';
  my $date = '';
  if (not $arg{suppressdate}) {
    $date = $sdt->month_abbr() . '&nbsp;' . include::htmlordinal($sdt->mday());
    if ($sdt->ymd() ne $edt->ymd()) {
      $date .= '-';
      if ($sdt->month() ne $edt->month()) {
        $date .= $edt->month_abbr() . '&nbsp;';
      }
      $date .= include::htmlordinal($edt->mday());
    }
    $date .= ' ';
  }
  my $time = include::twelvehourtimefromdt($sdt) . '<!-- ' . $sdt->hms() . ' -->';
  if (not $arg{suppressendtime}) {
    $time .= '&mdash;' . include::twelvehourtimefromdt($edt) . '<!-- ' . $edt->hms() . ' -->';
  }
  my $allday = join '|', map { $$_{flagchar} } searchrecord('resched_staffsch_flag', 'flags', 'L');
  if ($allday and ($$or{flags} =~ /$allday/)) {
    $time = 'all&nbsp;day';
  }
  my $location = '';
  if (not $arg{suppresslocation} and not getvariable('resched', 'staff_schedule_suppress_locations')) {
    $location = ' ' . formatlocation(getrecord('resched_staffsch_location', $$or{location}));
  }
  my $comment = $arg{suppresscomment} ? "" : (qq[<span class="comment occasioncomment">] . encode_entities($$or{comment}) . qq[</span>]);
  my $when = qq[<abbr title="from ] . $sdt->ymd() . ' at ' . $sdt->hms() . ' to ' . $edt->ymd() . ' at' . $edt->hms() . qq[">$date$time</abbr>];
  return qq[<div class="$class">] . (join " ", grep { $_ } $when, $name, $location, $comment, $flags) . "</div>"
    if $arg{datefirst};
  return qq[<div class="$class"><!-- format_occasion -->] . (join " ", grep { $_ } $name, $location, $comment, $flags, $when) . "</div>";
}

sub formatshortname {
  my ($sr, %arg) = @_;
  my $name = encode_entities($$sr{shortname});
  if ($arg{possessive}) { $name = encode_entities(include::possessive($$sr{shortname})); }
  if (not $arg{suppressabbr}) {
    my $fname = encode_entities($$sr{fullname});
    $name = qq[<abbr title="$fname">$name</abbr>];
  }
  my $color = $$sr{color} || 'black';
  my $sclr  = $backgroundcolor{$$sr{color}} || $defaultbackgroundcolor;
  my $shadowprop = (getvariable('resched', 'staff_schedule_expand_shadow_to_bg'))
    ? qq[background-color:] : qq[text-shadow: 1px 1px 1px];
  return qq[<span class="staffschname" style=" color: $color; $shadowprop $sclr; ">$name</span>];
}

sub liststaff {
  my @staff = getrecord('resched_staff');
  @staff = grep { not $$_{flags} =~ /X/ } @staff
    unless $input{listall} eq 'yes';
  my $personalschedule = getvariable('resched', 'wording_personal_schedule') || 'Personal Schedule';
  my $scheduleaction   = ((($user{flags} =~ /A/) or ($$sr{userid} eq $user{id}) or getvariable('resched', 'staff_schedule_lax_security'))
			  and getvariable('resched', 'staff_schedule_jump_to_edit')) ? 'editstaffhours' : 'staffschedule';
  my @li = map {
    my $sr = $_;
    my $sname = formatshortname($sr, suppressabbr => 1);
    my $fname = encode_entities($$sr{fullname});
    # TODO: take args that specify other fields to show.
    my $editlink = (($user{flags} =~ /A/) or getvariable('resched', 'staff_schedule_lax_security'))
      ? qq[<a class="adminlink" href="staffsch.cgi?action=editstaff&amp;staffid=$$sr{id}&amp;$persistentvars">Staff Record</a>] : '';
    qq[<tr><td>$sname</td><td>$fname</td>
           <td><a href="staffsch.cgi?action=${scheduleaction}&amp;staffid=$$sr{id}&amp;$persistentvars">$personalschedule</a></td>
           <td>$editlink</td></tr>];
  } @staff;
  my $addstafflink = (($$user{flags} =~ /A/) or getvariable('resched', 'staff_schedule_lax_security'))
    ? qq[<td><a class="button" href="staffsch.cgi?action=newstaff&amp;$persistentvars">Add Staff</a></td>] : '';
  my $listalllink  = (($$user{flags} =~ /A/) or getvariable('resched', 'staff_schedule_lax_security'))
    ? (($input{listall} eq 'yes')
       ? qq[<td colspan="2"><a class="button" href="staffsch.cgi?action=liststaff">Hide Former Staff</a></td>]
       : qq[<td colspan="2"><a class="button" href="staffsch.cgi?action=liststaff&amp;listall=yes">Show Former Staff</a></td>]) : '';
  my $links = ($addstafflink || $listalllink) ? qq[<tr>$addstafflink$listalllink</tr>] : '';
  return qq[<table class="stafflist table"><thead>
       <tr><td>Short Name</td><td>Full Name</td><td>Personal Schedule</td></tr>
     </thead><tbody>] . (join "\n         ", @li ). qq[$links</tbody></table>];
}

sub updatestaff {
  my ($sr) = getrecord('resched_staff', include::getnum('staffid'));
  return qq[<div class="error"><div class="h">No Such Staff</div>
    Oops!  I cannot seem to find staff record ID <q>$input{staffid}</q> in the database.</div>] if not ref $sr;
  for my $f (qw(shortname fullname jobtitle jobdesc phone email contact)) {
    $$sr{$f} = $input{$f} || $$sr{$f};
  }
  $$sr{color} = $input{color} || $$sr{color}
    unless $input{color} =~ /[<>&;]/; # No Monkey Business
  $$sr{flags} = '';
  for my $f (grep { not $$_{obsolete} } getrecord('resched_staff_flag')) {
    $$sr{flags} .= $$f{flagchar} if $input{qq[flag$$f{flagchar}]};
  }
  $$sr{userid} = include::getnum('userid');
  my $urec = getrecord('users', $$sr{userid});
  return qq[<div class="error"><div class="h">Error: No Such Account</div>
        You specified that this staff member has user account ID '$$sr{userid}',
        but I cannot seem to find that account in the database.</div>] if not ref $urec;
  updaterecord('resched_staff', $sr);
  return staffform(getrecord('resched_staff', $$sr{id}));
}

sub createstaff {
  my $newrec = +{
                 userid    => include::getnum("userid"),
                 shortname => $input{shortname},
                 fullname  => $input{fullname} || $input{shortname},
                 jobtitle  => $input{jobtitle},
                 jobdesc   => $input{jobdesc},
                 phone     => $input{phone},
                 email     => $input{email},
                 contact   => $input{contact},
                 color     => $input{color},
                 flags     => '',
                };
  for my $f (grep { not $$_{obsolete} } getrecord('resched_staff_flag')) {
    $$newrec{flags} .= $$f{flagchar} if $input{qq[flag$$f{flagchar}]};
  }
  if (($user{flags} =~ /A/)  or getvariable('resched', 'staff_schedule_lax_security')) {
    my $urec = getrecord('users', $$newrec{userid});
    return qq[<div class="error"><div class="h">Error: No Such Account</div>
        You specified that this staff member has user account ID '$$newrec{userid}',
        but I cannot seem to find that account in the database.</div>] if not ref $urec;
    if ($$newrec{color} =~ /[<>&;]/) { # Monkey Business
      $$newrec{color} = 'black';
    }
    addrecord('resched_staff', $newrec);
  }
  my $id = $db::added_record_id;
  if ($id) {
    my $sname   = encode_entities($$newrec{shortname});
    my $bgcolor = $backgroundcolor{$$newrec{color}};
    my $shadowprop = (getvariable('resched', 'staff_schedule_expand_shadow_to_bg'))
    ? qq[background-color:] : qq[text-shadow: 1px 1px 1px];
    return qq[<div class="info"><div class="h">Record Added</div>
       A record for <span class="staffschname" style=" color: $$newrec{color}; $shadowprop $bgcolor; ">$sname</span> has been added.
       You can use the form below if you wish to edit it.</div>\n]
      . staffform(getrecord('resched_staff', $id));
  }
  return qq[<div class="error"><div class="h">Error: Record Not Created</div>
    The staff record was not successfully created.</div>];
}

sub staffform {
  my ($record) = @_;
  my %dflt = (
              userid    => 0,
              shortname => '',
              fullname  => '',
              jobtitle  => '',
              jobdesc   => '',
              phone     => '',
              email     => '',
              contact   => '',
             );
  my ($action, $savewords, $staffid) = ('createstaff', 'Create Staff Record', '');
  if (ref $record) {
    for my $k (keys %$record) {
      $dflt{$k} = encode_entities($$record{$k});
    }
    $action    = 'updatestaff';
    $savewords = 'Save Changes';
    $staffid   = qq[<input type="hidden" name="staffid" value="$$record{id}" />];
  }
  my %flag;
  for my $f (getrecord('resched_staff_flag')) {
    if (ref $record) {
      $flag{$$f{flagchar}} = ($$record{flags} =~ /$$f{flagchar}/)   ? ' checked="checked"' : '';
    } else {
      $flag{$$f{flagchar}} = ($$f{isdefault} and not $$f{obsolete}) ? ' checked="checked"' : '';
    }
  }
  my %clrused = map { $$_[0] => 0 } @color;
  for my $staff (getrecord('resched_staff')) {
    $clrused{$$staff{color}}++;
  }
  $clrused{$$record{color}} = -1;
  @color = sort { $clrused{$$a[0]} <=> $clrused{$$b[0]} } @color;
  $dflt{color} = $color[0][0];
  my $maxcolors = getvariable('resched', 'max_color_choices') || 16;
  while ($maxcolors < scalar @color) {
    pop @color;
  }
  my $colorswatch = join ", ", map {
    my ($fg, $name, $bg) = @$_;
    $bg ||= $defaultbackgroundcolor;
    my $shadowprop = (getvariable('resched', 'staff_schedule_expand_shadow_to_bg'))
      ? qq[background-color:] : qq[text-shadow: 1px 1px 1px];
    qq[<span class="staffschname" style="color: $fg; $shadowprop $bg;">$name</span>]
  } @color;

  my $userselect = include::optionlist('userid', +{ 0 => '[none]',
                                                    map { $$_{id} => $$_{username} } getrecord('users'),
                                                  }, $dflt{userid});
  my $colorselect = include::orderedoptionlist('color', \@color, $dflt{color});
  my @flagrow = map {
    my $f = $_;
    my $checked = ($$record{flags} =~ /$$f{flagchar}/) ? ' checked="checked"' : '';
    my $longd   = encode_entities($$f{longdesc});
    my $shortd  = encode_entities($$f{shortdesc});
    qq[<tr><td><input type="checkbox" id="flag$$f{flagchar}" name="flag$$f{flagchar}"$checked />&nbsp;<label for="flag$$f{flagchar}">$shortd</label></td><td class="explan">$longd</td></tr>\n           ];
  } grep { not $$_{obsolete} } getrecord('resched_staff_flag');
  my $flagrows = 1 + scalar @flagrow;

  return qq[<form class="newstaffform" action="staffsch.cgi" method="post">
    <input type="hidden" name="action" value="$action" />
    $hiddenpersist
    $staffid
    <table class="addstaff"><tbody>
       <tr><th><label for="userid">Login</label></th><td>$userselect</td>
           <td class="explan">If they log into this account, they can edit their own schedule.</td></tr>
       <tr><th><label for="shortname">Short Name</label></th>
           <td><input type="text" size="12" id="shortname" name="shortname" value="$dflt{shortname}" /></td>
           <td class="explan">The short name is shown on schedules and things where compactness is desirable.
               You can use just a first name, or initials.</td></tr>
       <tr><th><label for="fullname">Full Name</label></th>
           <td><input type="text" size="30" id="fullname" name="fullname" value="$dflt{fullname}" /></td>
           <td class="explan">The full name should be enough information to clearly identify the person.
                Hovering over the shortname (e.g., on a schedule) will show the full name in a tooltip.</td></tr>
       <tr><th><label for="color">Name Color</label></th>
           <td>$colorselect</td>
           <td class="explan"><div class="p">The name will be shown in this color on schedules and things,
                as an added visual clue to make it easier to find the person you are looking for.</div>
                <div class="p colorsamples">Samples: $colorswatch.</div></td></tr>
       <tr><th rowspan="$flagrows">Flags</th></tr>
           @flagrow
       <tr><th><label for="jobtitle">Job Title</label></th>
           <td><input type="text" size="30" id="jobtitle" name="jobtitle" value="$dflt{jobtitle}" /></td>
           <td rowspan="5" class="explan"><div class="p">These fields exist for the sake of completeness, but the software currently does not use them for anything.</div>
                                          <div class="p">It does display them, so anyone who can log into this staff scheduling utility can see them.  If desired, you can fill them out with information the staff might need about each other.</div>
                                          <div class="p">If you do not need them, you can just leave them blank.</div>
                                          </td></tr>
       <tr><th><label for="jobdesc">Job Description</label></th>
           <td><textarea rows="3" cols="30" id="jobdesc" name="jobdesc">$dflt{jobdesc}</textarea></td></tr>
       <tr><th><label for="phone">Phone</label></th>
           <td><input type="text" size="13" id="phone" name="phone" value="$dflt{phone}" /></td></tr>
       <tr><th><label for="email">Email Address</label></th>
           <td><input type="text" size="30" id="email" name="email" value="$dflt{email}" /></td></tr>
       <tr><th><label for="contact">Other Contact Info</label></th>
           <td><textarea id="contact" name="contact" rows="3" cols="30">$dflt{contact}</textarea></td></tr>
       <tr><td></td>
           <td><input type="submit" value="$savewords" /></td></tr>
    </tbody></table>
  </form>];
}

sub updatecolors {
  my @color = getrecord('resched_staffsch_color');
  my %cflag = ( X => 'Do not suggest this color.' );
  for my $c (@color) {
    for my $field (qw(name fg shadow)) {
      $$c{$field} = $input{"color$field$$c{id}"} || $$c{$field};
    }
    $$c{flags} = join '', grep { $input{"colorflag$_$$c{id}"} } keys %cflag;
    updaterecord('resched_staffsch_color', $c);
  }
  return editcolors();
}

sub editcolors {
  my @color = getrecord('resched_staffsch_color');
  my %cflag = ( X => 'Do not suggest this color.' );
  my $shadowprop = (getvariable('resched', 'staff_schedule_expand_shadow_to_bg'))
      ? qq[background-color:] : qq[text-shadow: 1px 1px 1px];
  return qq[<form id="configform" class="configform colorconfig" action="staffsch.cgi" method="post">
  <input type="hidden" name="action" value="updatecolors" />
  $hiddenpersist
  <div class="p explan">The <strong>foreground</strong> and <strong>shadow</strong> fields must
      be in a valid CSS color format.  The most widely used format is #RRGGBB, where RR, GG, and BB
      are two-digit hexadecimal numbers specifying the amount of red, green, and blue, respectively.
      Lower numbers are darker, and higher ones are brighter.  So for example
          <span style="$shadowprop black; color: #FF7F00;">#FF7F00</span>
      has the red turned all the way up, the green at half, and the blue all the way off.
      The previews are only updated when you save.</div>
  <table><thead>
     <tr><td></td><th>Name</th><th>Foreground</th><th>Shadow</th><th>Preview</th><th>Flags</th></tr>
  </thead><tbody>
     ] . (join "\n     ", map {
       my $c = $_;
       my $name   = encode_entities($$c{name});
       my $fg     = encode_entities($$_{fg});
       my $shadow = encode_entities($$_{shadow});
       my $flags  = join "\n                  ", (map {
         my $f = $_;
         my $checked = ($$c{flags} =~ /$f/) ? qq[ checked="checked"] : '';
         qq[<div class="flagform"><input type="checkbox" name="colorflag$f$$c{id}" id="colorflag$f$$c{id}" $checked />
                    <label for="colorflag$f$$c{id}">$cflag{$f}</label></div>];
       } sort { $a cmp $b } keys %cflag);
       my $shadowprop = (getvariable('resched', 'staff_schedule_expand_shadow_to_bg'))
         ? qq[background-color:] : qq[text-shadow: 1px 1px 1px];
       my $preview = qq[<span class="staffschname" style="color: $fg; $shadowprop $shadow; ">$name</span>];
       qq[<tr><td><input type="text" size="4" disabled="disabled" name="colorid$$c{id}" value="$$c{id}" /></td>
              <td><input type="text" size="10" name="colorname$$c{id}" value="$name" /></td>
              <td><input type="text" size="10" name="colorfg$$c{id}" value="$fg" /></td>
              <td><input type="text" size="10" name="colorshadow$$c{id}" value="$shadow" /></td>
              <td>$preview</td>
              <td>$flags</td></tr>];
     } @color) . qq[
  </tbody></table>
  <input type="submit" value="Save Changes" />
  </form>];
}

sub sidebardateoptions {
  my ($dt) = @_;
  return qq[startyear=] . $dt->year() . '&amp;' . qq[startmonth=] . $dt->month() . '&amp;' . qq[startmday=] . $dt->day();
}

sub usersidebar {
  my $addstaff  = (($user{flags} =~ /A/) or getvariable('resched', 'staff_schedule_lax_security'))
    ? qq[<div><a href="staffsch.cgi?action=newstaff&amp;$persistentvars">Add Staff</a></div>] : '<!-- Add Staff -->';
  my $editcolor = (($user{flags} =~ /A/) or getvariable('resched', 'staff_schedule_lax_security'))
    ? qq[<div><a href="staffsch.cgi?action=editcolors&amp;$persistentvars">Edit Colors</a></div>] : '<!-- Edit Colors -->';
  my $tomorrow  = sidebardateoptions($now->clone()->add( days   => 1 ));
  my $nextweek  = sidebardateoptions($now->clone()->add( days   => 7 ));
  my $nextmonth = sidebardateoptions($now->clone()->add( months => 1 ));
  my @tf = ([
             showday => [
                         ['Today'    => '', ],
                         ['Tomorrow' => $tomorrow, ],
                        ],
            ],
            [
             showweek => [
                          ['This Week' => '', ],
                          ['Next Week' => $nextweek, ],
                         ],
            ],
            [
             showmonth => [
                           ['This Month' => '',],
                           ['Next Month' => $nextmonth,],
                          ],
            ]);
  my @schflag   = grep { $$_{flags} =~ /A|S/ } getrecord('resched_staffsch_flag');
  my $namefield = ((scalar @schflag) > 2) ? 'flagchar' : 'shortdesc';
  my @tfline;
  for my $tfgroup (@tf) {
    my ($action, $timeframes) = @$tfgroup;
    #use Data::Dumper; warn Dumper(+{ action => $action, timeframes => $timeframes });
    push @tfline, qq[<hr />];
    for my $tf (@{$timeframes}) {
      my ($label, $tfvars) = @$tf;
      #warn Dumper(+{ label => $label, tfvars => $tfvars });
      $tfvars = $tfvars ? qq[&amp;$tfvars] : '';
      my $flagsch = join "", map {
        my $f = $_;
        qq[ <a class="button" href="staffsch.cgi?action=$action&amp;requireflag=$$f{flagchar}&amp;$persistentvars$tfvars">$$f{$namefield}</a>]
      } @schflag;
      push @tfline, qq[<div><a class="button" href="staffsch.cgi?action=$action&amp;$persistentvars$tfvars">$label</a>$flagsch</div>];
    }
  }
  my $tflines = join "\n       ", @tfline;
  my $preserve = join '&amp;', map { encode_entities(qq[$_=$input{$_}])
                                                                 } grep { not /usestyle|ajax/
                                                                        } grep { $input{$_}
                                                                               } keys %input;
  my $adminlinks = (getvariable('resched', 'sidebar_show_admin_link')
		    and (($user{flags} =~ /A/) or getvariable('resched', 'staff_schedule_lax_security')))
    ? qq[<div><a href="admin.cgi">ReSched Administration</a></div>] : '';
  #warn "Preserving Variables: $preserve";
  my $stylesec  = include::sidebarstylesection($preserve, 'staffsch.cgi');
  my @wecanedit = findrecord('resched_staff', 'userid', $user{id});
  my $editsch   = (1 == scalar @wecanedit)
    ? qq[<div><a href="staffsch.cgi?action=editstaffhours&amp;staffid=$wecanedit[0]{id}&amp;$persistentvars">My Schedule</a></div>]
    : (getvariable('resched', 'staff_schedule_show_redundant_change_link')
       ? qq[<div><a href="staffsch.cgi?action=liststaff&amp;$persistentvars">Change Staff Schedules</a></div>] : '');
  return qq[<div class="sidebar">
     <div class="h sidebarsec">Schedules:</div>
       $tflines
  </div>
  <div class="sidebar">
     <div class="h sidebarsec">Staff:</div>
       <hr />
       $editsch
       <div><a href="staffsch.cgi?action=liststaff&amp;$persistentvars">List Staff</a></div>
       $addstaff
       $editcolor
  </div>
  <div class="sidebar">
      <div class="h sidebarsec">Other Stuff:</div>
      <hr />
      <div><a href="index.cgi?usestyle=$input{usestyle}">Resource Scheduling</a></div>
      <div><a href="program-signup.cgi?usestyle=$input{usestyle}">Program Signup</a></div>
      $adminlinks
      $stylesec
  </div>\n];
}
