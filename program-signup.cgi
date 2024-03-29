#!/usr/bin/perl -T
# -*- cperl -*-

our $debug = 0;

$ENV{PATH}='';
$ENV{ENV}='';

use strict;
use DateTime;
use DateTime::Span;
use HTML::Entities qw(); sub encode_entities{ my $x = HTML::Entities::encode_entities(shift@_);
                                              $x =~ s/[-][-]/&mdash;/g;
                                             return $x; }
use Data::Dumper;
use Carp;

require "./forminput.pl";
require "./include.pl";
require "./auth.pl";
require "./db.pl";
require "./ajax.pl";
require "./datetime-extensions.pl";

our %input = %{getforminput() || +{}};
our $persistentvars = qq[usestyle=$input{usestyle}&amp;useajax=$input{useajax}];
our $hiddenpersist  = qq[<input type="hidden" name="usestyle" value="$input{usestyle}" />\n  <input type="hidden" name="useajax" value="$input{useajax}" />];

sub usersidebar; # Defined below.

my $ab = authbox(sub { my $x = getrecord('users', shift); "<!-- Hello, $$x{nickname} -->"; });

my %categoryflag = (
                    'D' => ['D', 'Default',         'This is the default category for new programs.'],
                    'L' => ['L', 'Library program', 'Programs in this category are our official programs.', 'inherited'],
                    'T' => ['T', 'Third-party',     'Programs in this category are unofficial or run by a third party.', 'inherited'],
                    'X' => ['X', 'Obsolete',        'This category is no longer used for new programs.'],
                    '#' => ['#', 'DEBUG',           'Programs in this category are not real programs.  They exist only for testing the booking software.', 'inherited'],
                   );
my %programflag = (
                   'L' => ['L', 'Library program', 'This is one of our official programs.'],
                   'O' => ['O', 'Ongoing program', 'Program is not on any specific date or is ongoing over a period of time.'],
                   'R' => ['R', 'Reminder call',   'Provide a checkbox for tracking which patrons have been called to remind them of the program.'],
                   'S' => ['S', 'Self-Signup',     'Allow patrons to sign themselves up using the public self-signup interface.'],
                   'T' => ['T', 'Third-party',     'This program is unofficial or is run by a third party.'],
                   'W' => ['W', 'Waiting list',    'If this program fills up to the limit, a waiting list will be started.'],
                   'X' => ['X', 'Canceled',        'This program has been canceled.'],
                   '#' => ['#', 'DEBUG',           'This is not a real program.  It exists only for testing the booking software.', 'inherited'],
                  );
my %signupflag = ('R' => ['R', 'Reminded',    'This person has received a reminder call.'],
                  'S' => ['S', 'Self-Signup', 'This information was entered via the public signup form.'],
                  'W' => ['W', 'Waitlist',    'This person signed up for the wait list, before the program filled up.'],
                  'X' => ['X', 'Canceled',    'This person no longer plans to attend.'],
                  '?' => ['?', 'Maybe',       'This person is unsure whether they will attend.'],
                  '#' => ['#', 'DEBUG',       'You can ignore this signup: we were just testing the booking software.']
                 );

sub respondtouser { # This is the non-AJAX way.
  my ($content, $title, $redirect, %o) = @_;
  $content or die "No content.";
  $title ||= 'Program Signup';
  print include::standardoutput($title, $content,
                                $o{omitsidebar} ? "<!-- signmeup needs no auth -->" : $ab,
                                $input{usestyle}, $redirect, undef,
                                $o{omitsidebar});
  exit 0;
}

if ($auth::user) {
  $input{usestyle} ||= getpref("usestyle", $auth::user);
  $input{useajax}  ||= getpref("useajax", $auth::user);
  if ($input{signmeup}) { # Allow staff to access the public signup form too.  If nothing else, I need to for testing.
    respondtouser(public_signup());
  } elsif ($input{action} eq 'newprogram') {
    respondtouser(programform(undef), "Create New Program");
  } elsif ($input{action} eq 'createprogram') {
    respondtouser(createprogram());
  } elsif ($input{action} eq 'editprogram') {
    respondtouser(programform(getrecord('resched_program', $input{program})));
  } elsif ($input{action} eq 'updateprogram') {
    respondtouser(updateprogram(), "Program Details");
  } elsif ($input{action} eq 'showprogram') {
    my $progtitle = "Program Signup";
    my $prog = getrecord('resched_program', $input{program});
    if (ref $prog) {
      $progtitle = "Program Signup - $$prog{title}";
    }
    respondtouser(showprogram(), $progtitle);
  } elsif ($input{action} eq 'dosignup') {
    respondtouser(dosignup());
  } elsif ($input{action} eq 'editsignup') {
    respondtouser(editsignup(), "Edit Program Signup");
  } elsif ($input{action} eq 'updatesignup') {
    respondtouser(updatesignup(), "Edit Program Signup");
  } elsif ($input{action} eq 'AjaxAddSignup') {
    my $num = $input{numofnewsignups} + 1;
    my $ewt = $input{explicitwait};
    sendresponse(ajaxvarupdate('numofnewsignups', $num)
                 . ajaxtoggledisplay('addmoresignupsbutton', 'inline')
                 . ajaxtoggledisplay('onemomentnoticegoeshere', 'none')
                 . ajaxinsert('insertemptysignupshere',
                              blankattender($num, $ewt) # both content and focus
                             )
                );
  } else {
    respondtouser(listprograms(), "Upcoming Programs");
  }
} elsif ($input{signmeup}) {
  respondtouser(public_signup(), undef, undef, omitsidebar => 1);
} else {
  respondtouser(qq[You probably need to log in.], "Not Authorized");
}

sub redirectheader {
  my ($action) = @_;
  return unless $action;
  my $seconds = getvariable('resched', 'redirect_seconds') || 15;
  my $uri = getvariable('resched', 'url_base')
    . qq[program-signup.cgi?action=$action&amp;$persistentvars];
  foreach my $key (qw(program category attender id sortby cutoffdate)) {
    $uri .= qq[&amp;$key=$input{$key}] if $input{$key};
  }
  if ($0 =~ m~resched-dev/~) {
    # Some sites (such as Galion) may choose deploy a stable version
    # for production use and a development version for testing.  If
    # the two versions are in directories called resched and
    # resched-dev (respectively) under the same parent directory,
    # this makes it work out right:
    $uri =~ s~resched/~resched-dev/~;
  }
  return qq[<meta http-equiv="refresh" content="$seconds; URL=$uri" />]
}

sub dateform {
  my ($dt, $nameprefix, $idprefix, $timeonly) = @_;
  $nameprefix ||= '';
  $idprefix   ||= $nameprefix;
  my %monthname   = ( 1 => "January", 2 => "February", 3 => "March", 4 => "April", 5 => "May", 6 => "June",
                      7 => "July", 8 => "August", 9 => "September", 10 => "October", 11 => "November", 12 => "December" );
  my @monthoption = map { my $m = $_;
                          my $sel = ($m == $dt->month()) ? ' selected="selected"' : '';
                          qq[<option value="$m"$sel>$monthname{$m}</option>]# . "\n                 "
                        } 1 .. 12;
  my $houroptions = include::houroptions($dt->hour(), $dt->dow());
  my $timeform = qq[<select id="${idprefix}hour" name="${nameprefix}hour">$houroptions</select> :
                   <input type="text" id="${idprefix}minute" name="${nameprefix}minute" size="3" value="] . (sprintf "%02d", $dt->minute()) . qq[" />];
  return $timeform if $timeonly;
  return qq[<input type="text" id="${idprefix}year"  name="${nameprefix}year"  value="] . $dt->year() . qq[" size="5" />
             <select id="${idprefix}month" name="${nameprefix}month">@monthoption</select>
             <input type="text" id="${idprefix}day" name="${nameprefix}day" size="3" value="] . $dt->mday() . qq[" />
             <nobr>at $timeform</nobr>]
}

sub programform {
  my ($record) = @_;
  my ($categoryform, $untilform, $startdateform, $hidden, $savebutton);
  my @dfltsort = ( # Values here must be kept in sync with what showprogram() knows how to handle.
                  [ num      => 'Sort sign-up list numerically.'  ],
                  [ lastname => 'Sort sign-up list by last name.' ],
                 );
  my @category   = grep { not ($$_{flags} =~ /X/) } getrecord('resched_program_category');
  my %category   = map { $$_{id} => $$_{category} } @category;
  my @defaultcategory = map { $$_{id} } grep { $$_{flags} =~ /D/ } @category;
  my $footnotes = "";
  #use Data::Dumper; warn Dumper(+{ category_array => \@category, category_hash  => \%category, default        => \@defaultcategory,  });
  if (ref $record) {
    $categoryform  = include::optionlist('category', \%category, $$record{category});
    $startdateform = dateform(DateTime::From::MySQL($$record{starttime}), 'start');
    $untilform     = dateform(DateTime::From::MySQL($$record{endtime}), 'end');
    $savebutton    = 'Save Changes';
    $hidden        = qq[<input type="hidden" name="action" value="updateprogram" />
    <input type="hidden" name="program" value="$$record{id}" />];
  } else {
    $categoryform  = include::optionlist('category', \%category, $defaultcategory[0], 'newprogramcategory');
    my $startdate = DateTime->now(time_zone => $include::localtimezone)->add(months => 1);
    $startdateform = dateform($startdate, 'start');
    $untilform     = dateform($startdate, 'end', undef, 'timeonly') . qq[*];
    $footnotes     = qq[<div class="footnotes">* To create a multi-day event, first create the event, then edit it to change the ending date/time.</div>];
    $savebutton    = 'Create This Program';
    $hidden        = qq[<input type="hidden" name="action" value="createprogram" />];
    $record = +{# Defaults for new programs:
                agegroup       => '',
                title          => '',
                signuplimit    => (getvariable('resched', 'program_signup_default_limit') || 0),
               };
    if (0 + getvariable('resched', 'program_signup_waitlist')) {
      $$record{flags} = 'W';
    }
  }
  my $limitsize = ($$record{limit} >= 100) ? 6 : 4;
  my $notesrows = 3 + int((length $$record{notes}) / 50); $notesrows = 10 if $notesrows > 10;
  my $dfsort    = include::orderedoptionlist('defaultsort', \@dfltsort,
                                             ($$record{defaultsort} || getvariable('resched', 'program_signup_default_sort') || 'num'),
                                            );
  return qq[<form action="program-signup.cgi" method="post">\n  $hiddenpersist
  $hidden
  <table class="dbrecord">
     <tr><th><label for="category">Category:</label></th>
         <td>$categoryform</td></tr>
     <tr><th><label for="title">Program Title:</label></th>
         <td><input type="text" id="newprogramtitle" name="title" size="30" value="$$record{title}" /></td>
         <td class="explan">(You can use the same title repeatedly if the date or time is different.)</td></tr>
     <tr><th><label for="agegroup">Age Group:</label></th>
         <td><input type="text" id="newprogramagegroup" name="agegroup" size="10" value="$$record{agegroup}" /></td>
         <td class="explan">(The computer doesn't know what the age group means; it's just for our reference.)</td></tr>
     <tr><th><label for="startyear">Date:</label></th>
         <td>$startdateform</td></tr>
     <tr><th><label for="endhour">Until:</label></th>
         <td>$untilform</td></tr>
     <tr><th><label for="limit">Limit:</label></th>
         <td><input type="text" id="signuplimit" name="signuplimit" size="$limitsize" value="$$record{signuplimit}" />
             <span class="explan">(0 means no limit.)</span></td></tr>
     <tr><th><label for="defaultsort">Sort:</label></th>
         <td>$dfsort</td></tr>
     <tr><th><label>Flags:</label></th>
         <td>] . flagcheckboxes($$record{flags}, \%programflag) . qq[</td></tr>
     <tr><th><label for="programnotes">Notes:</label></th>
         <td><textarea id="programnotes" name="notes" cols="40" rows="$notesrows">$$record{notes}</textarea></td>
         <td><span class="explan">Anything you type here will be shown at the top of the signup sheet.</span></td></tr>
  </table>
  <input type="submit" value="$savebutton" />
  $footnotes
</form>];
}

sub updateprogram {
  my $prog = getrecord('resched_program', $input{program});
  if (not ref $prog) {
    return include::errordiv("Error", qq[Something is wrong.  I was unable to find program number $input{program} in the database.]);
  } else {
    my ($when)  = assembledatetime('start', \%input, $include::localtimezone, 'cleanup');
    my ($until) = assembledatetime('end',   \%input, $include::localtimezone, 'cleanup');
    if ($until < $when) {
      $until = $when->clone()->add( hours => 1);
    }
    $$prog{starttime}     = DateTime::Format::ForDB($when);
    $$prog{endtime}       = DateTime::Format::ForDB($until);
    $$prog{flags}         = join '', map { $input{"flag" . $_} ? $_ : '' } keys %programflag;
    $$prog{notes}         = encode_entities($input{notes});
    $$prog{title}         = encode_entities($input{title});
    $$prog{agegroup}      = encode_entities($input{agegroup});
    $$prog{defaultsort}   = encode_entities($input{defaultsort}); # Invalid values will cause it to fall back to the default.
    ($$prog{signuplimit}) = $input{signuplimit}    =~ /(\d+)/;
    my ($catid)           = $input{category} =~ /(\d+)/;
    my $category          = getrecord('resched_program_category', $catid);
    if (ref $category) {
      $$prog{category}    = $catid;
    }
    my @change = @{updaterecord('resched_program', $prog)};
    return programform(getrecord('resched_program', $$prog{id}));
  }
}

sub updatesignup {
  my ($id) = ($input{id} =~ m/(\d+)/);
  my $s = getrecord('resched_program_signup', $id);
  if (not ref $s) {
    return include::errordiv("Error", qq[Unfortunately, I was not able to find signup record $id in the database.]);
  } else {
    $$s{attender} = (encode_entities($input{attender}) || $$s{attender});
    $$s{phone}    = (encode_entities($input{phone})    || $$s{phone});
    $$s{flags}    = join '', map { $input{"flag" . $_} ? $_ : '' } keys %signupflag;
    $$s{comments} = (encode_entities($input{comments}) || $$s{comments});
    my @change = @{updaterecord('resched_program_signup', $s)};
    return editsignup();
  }
}

sub editsignup {
  my ($id) = ($input{id} =~ m/(\d+)/);
  my $s = getrecord('resched_program_signup', $id);
  if (not ref $s) {
    return include::errordiv("Error", qq[Unfortunately, I was not able to find signup record $id in the database.]);
  } else {
    my $flagcheckboxes = flagcheckboxes($$s{flags}, \%signupflag);
    return qq[<form action="program-signup.cgi" method="post">\n  $hiddenpersist
    <input type="hidden" name="action" value="updatesignup" />
    <input type="hidden" name="id"     value="$id" />
    <table class="dbrecord">
       <tr><th><label for="attender">Name:</label></th>
           <td><input id="attender" name="attender" type="text" size="35" value="$$s{attender}" /></td></tr>
       <tr><th><label for="phone">Phone:</label></th>
           <td><input id="phone" name="phone" type="text" size="20" value="$$s{phone}" /></td></tr>
       <tr><th><label>Flags:</label></th>
           <td>$flagcheckboxes
           </td></tr>
       <tr><th><label for="comments">Comments:</label></th>
           <td><textarea id="comments" name="comments" rows="5" cols="35">$$s{comments}</textarea></td></tr>
    </table>
    <input type="submit" value="Save Changes" />
   </form>];
  }
}

sub public_signup_program_desc {
  my ($p) = @_;
  my $dt   = DateTime::From::MySQL($$p{starttime});
  my $when = "on " . $dt->year() . " " . ucfirst($dt->month_name()) . " " . include::htmlordinal($dt->mday())
    . " at " . $dt->hour_12() . (($dt->minute > 0) ? (":" . sprintf("%02d", $dt->minute())) : ($dt->hour() == 12) ? " Noon" : ($dt->hour() > 12) ? "pm" : "am");
  return encode_entities($$p{title}) . " $when" . ($$p{agegroup} ? " for $$p{agegroup}" : "");
}

sub public_signup {
  my ($p);
  if ($input{attender} and $input{program_id} and
      ($p = getrecord("resched_program", $input{program_id})) and
      ($$p{flags} =~ /S/)) {
    return public_signup_add_attender($p);
  } else {
    return public_signup_form();
  }
}

sub public_signup_form {
  my ($p, $chooseprogram);
  if ($input{program_id} and
      ($p = getrecord("resched_program", $input{program_id})) and
      ($$p{flags} =~ /S/)) {
    $chooseprogram = qq[<input type="hidden" name="program_id" value="$$p{id}" />
    ] . public_signup_program_desc($p);
  } elsif (ref $p) {
    return include::errordiv("Self-Signup Not Available", qq[I am sorry, but $$p{title} does not appear to have self-signup enabled.  Please call the library to ask about this program.]);
  } elsif ($input{program_id}) {
    return include::errordiv("Program Not Found", qq[I am sorry.  I cannot find any record of program number $input{program_id}.  How can I sign you up for a program, when I cannot find record of it?]);
  } else {
    my @p = getprogramlist(99, undef, require_flag => "S");
    if (not scalar @p) {
      return include::errordiv("Error: No Self-Signup Programs Available",
                      qq[There are currently no scheduled programs with self-signup enabled.  (Some programs may not allow self-signup.  Call the library for more information or to sign up for one of those.)]);
    }
    $chooseprogram = include::orderedoptionlist("program_id", [map {
      [$$_{id}, public_signup_program_desc($_)],
    } @p], undef, "program_id");
  }
  # The value of signmeup doesn't matter as long as it's true in
  # boolean context.  I set it to something that looks kinda like a
  # hash key, as a cheap red herring and potential distraction, for
  # anyone who is only seeing the HTML/UI side of things.
  my @fkc = ("A" .. "Z", "a" .. "z", 0 .. 9);
  my $fakekey = "Ux" . join("", map { $fkc[rand @fkc]} 1 .. 60);
  return qq[<form class="publicsignup" action="program-signup.cgi" method="post">
  <input type="hidden" name="signmeup" value="$fakekey" />
  <table class="formtable"><tbody>
     <tr><th><label for="program_id">Program:</label></th>
         <td>$chooseprogram</td></tr>
     <tr><th><label for="attender">Name:</label></th>
         <td><input id="attender" name="attender" type="text" size="60" /></td></tr>
     <tr><th><label for="phone">Phone:</label></th>
         <td><input id="phone" name="phone" type="text" size="15" /></td></tr>
     <tr><th><label for="barcode">Library Card #:</label></th>
         <td><input id="barcode" name="barcode" type="text" size="15" /></td></tr>
     <tr><td>&nbsp;</td><td><input type="submit" value="Sign Me Up" /></td></tr>
  </tbody></table></form>];
}

sub public_signup_add_attender {
  my ($program) = @_;
  my $s = +{ program_id => $$program{id},
             attender   => encode_entities($input{attender}),
             phone      => encode_entities($input{phone} || ""),
             supdate    => DateTime::Format::ForDB(DateTime->now(time_zone => $include::localtimezone)),
             flags      => "S", # Self-signup
             comments   => (encode_entities($input{comments} | "") . "\n"
                            . "Public Signup Additional Info:" . "\n"
                            . "IP: " . $ENV{"REMOTE_ADDR"} . "\n"
                            . "BC: " . encode_entities($input{barcode}) . "\n"
                            . "UA: " . encode_entities($ENV{"HTTP_USER_AGENT"}) . "\n"
                           ),
           };
  my (@count) = findrecord("resched_program_signup",
                          "program_id" => $$s{program_id});
  my (@dupe)  = grep { lc($$_{attender}) eq lc($$s{attender}) } @count;
  return include::errordiv("Error: Duplicate Signup",
                  qq[We already have ] . (join " and ", map {
                    qq[someone named <q>$$_{attender}</q>] . (($$_{flags} =~ /W/) ? qq[ (on the waiting list)] : qq[ signed up])
                  } @dupe) . qq[ for $$program{title}<!-- program $$program{id} -->.])
    if @dupe;
  my $title   = "Signed Up";
  my $message = qq[I have added <q>$$s{attender}</q> to the signup list for $$program{title}.];
  if (($$program{signuplimit} > 0) and ((scalar @count) >= $$program{signuplimit})) {
    $$s{flags} .= "W";
    $title   = "Waiting List";
    $message = qq[<strong>This program is full.</strong>  There are ] . @count . qq[ people signed up ahead of you, out of $$program{signuplimit} permitted.
       However, I have added <q>$$s{attender}</q> to the <strong>waiting list</strong> for this program.];
  }
  addrecord("resched_program_signup", $s);
  my ($r) = findrecord("resched_program_signup",
                       "program_id" => $$s{program_id},
                       "attender"   => $$s{attender},
                      );
  if ($r) {
    return include::infobox($title, $message);
  } else {
    return include::errordiv("Unexpected Sign-Up Failure?",
                             "I attempted to sign you up, but when I double-checked, I can't find the record of your having signed up.");
  }
}

sub blankattender {
  my ($num, $explicitwait) = @_;
  my @flagcb = ();
  if ($explicitwait) {
    push @flagcb, qq[<input type="checkbox" id="signup${num}flagW" name="signup${num}flagW" />&nbsp;<label for="signup${num}flagW"><abbr title="Place on the waiting list">Wait</abbr></label>];
  }
  my $html = qq[      <tr>
        <td> </td><td><input type="text" id="signup${num}attender" name="signup${num}attender" size="30" /></td>
                   <td><input type="text" id="signup${num}phone"    name="signup${num}phone"    size="15" /></td>
                   <td>@flagcb</td>
                   <td><textarea id="signup${num}comments" name="signup${num}comments" rows="3" cols="25"></textarea></td>
      </tr>\n];
  if (wantarray) {
    return ($html, "signup${num}attender");
  } else {
    return $html;
  }
}

sub createprogram {
  my ($when) = assembledatetime('start', \%input, $include::localtimezone, 'cleanup');
  my $until = $when->clone()->set( hour => $input{endhour}, minute => ($input{endminute} || 0));
  if ($until < $when) {
    $until = $when->clone()->add( hours => 1);
  }
  my ($catid) = $input{category} =~ /(\d+)/;
  $catid += 0;
  my $category = getrecord('resched_program_category', $catid);
  if (ref $category) {
    my $flags = inheritflags($$category{flags}, \%categoryflag);
    for my $f (keys %programflag) {
      if ($input{'flag' . $f}) {
        $flags .= $f unless $flags =~ /[$f]/;
      }}
    my $newprogram = +{
                       category    => $catid,
                       title       => encode_entities($input{title}),
                       agegroup    => encode_entities($input{agegroup}),
                       starttime   => DateTime::Format::ForDB($when),
                       endtime     => DateTime::Format::ForDB($until),
                       flags       => $flags,
                       notes       => encode_entities($input{notes}),
		       signuplimit => include::getnum('signuplimit'),
                      };
    my $result = addrecord('resched_program', $newprogram);
    if ($result) {
      $input{program} = $db::added_record_id; # both showprogram() and redirectheader() need this.
      return ((qq[<div class="info"><div><strong>Program Created</strong></div>
  Here is the signup sheet for your new program:</div>]
               . showprogram()),
              "Program Created: $$newprogram{title}",
              redirectheader('showprogram'));
    } else {
      return include::errordiv("Error",
                               qq[Something went wrong when attempting to add your new program to the database.
                It may not have been successfully added.
                <!-- DBI says: $DBI::errstr -->]);
    }
  } else {
    return include::errordiv("Error",
                             qq{I tried to find category $catid in the database, but I could not find it.
                                I am not programed to create a program with an unknown category.});
  }
}

sub dosignup {
  my ($progid) = $input{program};
  my @result;
  my $prog = getrecord('resched_program', $progid);
  #warn "Incorrect program lookup, signup will probably be bollocks" if $$prog{id} ne $progid;
  if ($prog) {
    if ($$prog{R}) {
      for my $s (findrecord('resched_program_signup', 'program_id', $$prog{id})) {
        if ($input{"flagR$$s{id}"}) {
          my %f = map { $_ => 1 } split //, $$s{flags};
          $f{R}++;
          $$s{flags} = join "", grep { $f{$_} } sort { $a cmp $b } keys %f;
          updaterecord('resched_program_signup', $s);
        }
      }
    }
    for my $n (1 .. ($input{numofnewsignups} || 1)) {
      my $attender = encode_entities($input{"signup" . $n . "attender"});
      my $phone    = encode_entities($input{"signup" . $n . "phone"});
      my $flags    = inheritflags($$prog{flags}, \%programflag)
        . join "", #map { encode_entities($_) }
          grep { $input{"signup" . $n . "flag" . $_} } keys %signupflag;
      my $comments = encode_entities($input{"signup" . $n . "comments"});
      if ($attender) {
        my $category = getrecord('resched_program_category', $$prog{category});
        push @result, addrecord("resched_program_signup",
                                +{
                                  program_id => $progid,
                                  attender   => $attender,
                                  phone      => $phone,
                                  comments   => $comments,
                                  supdate    => DateTime::Format::ForDB(DateTime->now(time_zone => $include::localtimezone)),
                                  flags      => $flags,
                                 });
      }}
    return (showprogram(), "Program Signup", redirectheader('showprogram'));
  } else {
    return qq[<div class="error"><div><strong>Error:</strong></div>
     I cannot seem to find any record of program number $progid in the database.</div>];
  }
}

sub inheritflags {
  my ($sourceflags, $flaghash) = @_;
  my $flags  = '';
  my @considered;
  for my $f (split //, $sourceflags) {
    push @considered, $f;
    my $fr = $$flaghash{$f};
    if (ref $fr) {
      my ($char, $name, $description, $inherited) = @$fr;
      if (defined $inherited and ($inherited eq 'inherited')) {
        $flags .= $char;
      }}}
  #use Data::Dumper; warn Dumper( +{ sourceflags => $sourceflags, flaghash => $flaghash, result => $flags, considered => \@considered, } );
  return $flags;
}

sub showprogram {
  my ($id) = $input{program};
  my ($prog) = findrecord('resched_program', 'id', $id);
  my $when   = include::datewithtwelvehourtime(DateTime::From::MySQL($$prog{starttime}));
  my $cancelednote = '<!-- no canceled signups -->';
  if ($prog) {
    my @signup = findrecord('resched_program_signup', 'program_id', $id);
    if (not $input{showcanceled}) {
      my @c = grep { $$_{flags} =~ /X/ } @signup;
      if (scalar @c) {
        my $number  = scalar @c;
        my $were    = include::inflectverbfornumber($number, 'was', 'were');
        my $npeople = include::sgorpl($number, 'person', 'people');
        my $have    = include::inflectverbfornumber($number, 'has', 'have');
        my $ncancel = include::sgorpl($number, 'cancelation');
        $cancelednote = qq[<div class="info">There $were also $npeople previously
           signed up for this program who $have since canceled.
           <a href="program-signup.cgi?action=showprogram&amp;program=$id&amp;showcanceled=yes&amp;$persistentvars">Click here to show a list that includes the $ncancel.</a></div>];
        @signup = grep { not ($$_{flags} =~ /X/) } @signup;
      }
    }
    my $num = 0;
    my $category = getrecord('resched_program_category', $$prog{category});
    my $explicitwait = (main::getvariable('resched', "program_signup_waitlist_checkbox")
                        and ($$prog{flags} =~ /W/)) ? 1 : 0;
    my ($waitlistnote, @waitlist, $showwaitlist) = ('');
    for my $i (0 .. $#signup) {
      if ($signup[$i]{flags} =~ /X/) {
        $signup[$i]{num} = '<abbr title="X - Canceled">X</abbr>';
      } elsif ($explicitwait and $signup[$i]{flags} =~ /W/) {
        $signup[$i]{num} = '<abbr title="W - Waiting list">W</abbr>';
        $waitlistnote = qq[<tr><td colspan="5"><div><strong><hr />Waiting List:</strong></div></td></tr>\n      ];
      } else {
        $signup[$i]{num} = ++$num;
      }
    }
    if ($waitlistnote) {
      @waitlist = grep { $$_{num} eq '<abbr title="W - Waiting list">W</abbr>' } @signup;
      @signup   = grep { $$_{num} ne '<abbr title="W - Waiting list">W</abbr>' } @signup;
    }

    my $digits = ($num > 900) ? "%04d" : (($num > 90) ? "%03d" : (($num > 8) ? "%02d" : "%0d"));
    if (($$prog{signuplimit} > 0) and ($num >= $$prog{signuplimit})) {
      $waitlistnote = qq[<tr><td colspan="5"><div><strong><hr />Waiting List:</strong></div></td></tr>\n      ];
      while ($num > $$prog{signuplimit}) {
        my $w = pop @signup;
        $num--;
        $$w{num} = 'W' . sprintf $digits, $$w{num};
        unshift @waitlist, $w;
      }}
    my $sortorder = $input{sortby} || $$prog{defaultsort} || getvariable('resched', 'program_signup_default_sort') || 'num';
    # Any values of sortby that are handled here should also be listed in %dfltsort in programform() and documented in config.cgi under program_signup_default_sort.
    if ($sortorder eq 'num') {
      @signup = sort { $$a{id} <=> $$b{id} } @signup;
    } elsif ($sortorder eq 'lastname') {
      @signup = sortbylastname(@signup);
    } else {
      warn "Unsupported sort order: $sortorder";
    }
    my $enddt = DateTime::From::MySQL($$prog{endtime});
    my ($newsignup, $submitbutton);
    if ($$prog{flags} =~ /X/) {
      $newsignup = '<tr><td colspan="4"><div class="info">This program is canceled.</div></td></tr>';
      $submitbutton = '<!-- no submit -->';
    } elsif ($enddt < DateTime->now(time_zone => $include::localtimezone)) {
      $newsignup = '<tr><td colspan="4"><div class="info">This program ended ' . include::datewithtwelvehourtime($enddt) . '.</div></td></tr>';
      $submitbutton = '<!-- no submit -->';
    } elsif (($$prog{signuplimit} > 0) and ($num >= $$prog{signuplimit}) and (not ($$prog{flags} =~ /W/))) {
      $newsignup = '<tr><td colspan="4"><div class="info">This program is full.</div></td></tr>';
    } else {
      my $newsignuplimit = $$prog{signuplimit} - (scalar @signup);
      my $limit = (($$prog{signuplimit} > 0) and (not ($$prog{flags} =~ /W/)))
        ? qq[<input type="hidden" id="signuplimit" name="signuplimit" value="$newsignuplimit" />\n                        ]
        : '';
      $newsignup = blankattender(1, $explicitwait)
        . ($input{useajax} eq 'off' ? '' : qq[
      <tr id="insertemptysignupshere">
        <td colspan="4">$limit<input type="hidden" id="numofnewsignups" name="numofnewsignups" value="1" />
                        <span id="onemomentnoticegoeshere"><span id="onemomentnotice" style="display: none;">One moment...</span></span>
                        <input type="button" id="addmoresignupsbutton" value="Add More" onclick="augmentprogramsignupform($explicitwait);" /></td>
       </tr>]);
      $submitbutton = qq[<input type="submit" value="Submit" />];
    }
    my $limit = $$prog{signuplimit} ? qq[ out of $$prog{signuplimit} permitted] : '';
    my $howmany = $input{showcanceled}
      ? qq[Altogether there have been $num people signed up for this program.]
      : qq[There are currently $num people signed up for this program$limit.];
    my $selflink = ($$prog{flags} =~ /S/)
      ? qq[<div id="selfsignuplink" class="p"><a href="program-signup.cgi?signmeup=form&amp;program_id=$$prog{id}">Self-Signup is enabled for this program.  Click here to go to the public self-signup form.</a></div>] : "";
    my $title = ($$prog{flags} =~ /X/)
      ? qq[Canceled: $$prog{title} <div>(was scheduled $when)</div>]
      : qq[$$prog{title}, $when];
    my $notes = $$prog{notes} ? qq[<div id="programnotes">$$prog{notes}</div>] : '';
    my $programflags = showflags($$prog{flags}, \%programflag);
    my $programflags = $programflags ? (qq[<div id="programflags" class="box">Flags: ] . $programflags . '</div>') : '';
    my $makerow = sub {
      my ($s) = @_;
      for my $flagchar (keys %signupflag) {
        if ($input{"flag" . $flagchar . $$s{id}}) {
          my %f = map { $_ => 1 } split //, $$s{flags};
          $f{$flagchar}++;
          $$s{flags} = join "", grep { $f{$_} } sort { $a cmp $b } keys %f;
          updaterecord('resched_program_signup', $s);
        } elsif (($flagchar eq 'R') and
                 (($input{action} eq 'dosignup' or $input{action} eq 'updatesignup')
                  and $$prog{flags} =~ /R/)) {
          $$s{flags} =~ s/R//g;
          updaterecord('resched_program_signup', $s);
        }
      }
      my $flags = showflags($$s{flags}, \%signupflag);
      my $usealt = getvariable('resched', 'signup_sheets_use_alt_norm');
      $usealt = 1 if not defined $usealt;
      my $order    = $usealt ? (getvariable('resched', 'alternate_name_order') || 1)
                             : (getvariable('resched', 'normal_name_order') || 0);
      my $normal   = include::normalisebookedfor($$s{attender}, $order);
      my $attender = include::capitalise(include::dealias($normal));
      my $rcalled  = ($$s{flags} =~ /R/) ? ' checked="checked"' : "";
      my $rcallcb  = ($$prog{flags} =~ /R/) ? qq[<input type="checkbox" name="flagR$$s{id}"$rcalled />] : '';
      my $supdate  = ""; if ($$s{supdate}) {
        $supdate = friendlydt(DateTime::From::DB($$s{supdate}));
      }
      #use Data::Dumper; warn Dumper(+{ usealt => $usealt, order => $order, raw => $$s{attender}, normal => $normal, final => $attender });
      return qq[<tr class="signup"><td class="numeric">$$s{num}</td><td><a href="program-signup.cgi?action=editsignup&amp;id=$$s{id}&amp;$persistentvars">$attender</a></td><td>$rcallcb$$s{phone}</td><td>$supdate</td><td>$flags</td><td>$$s{comments}</td></tr>\n      ]
    };
    my $existingsignups = join "", map { $makerow->($_) } @signup;
    my $waitlistsignups = join "", map { $makerow->($_) } @waitlist;
    return qq[
<div style=" text-align: center; font-size: 1.2em; ">
  <div id="programtitle"><strong>$title</strong></div>
  <div id="agegroupandcategory">
       <span class="programagegroup">for $$prog{agegroup}</span>
       <span class="programcategory">(category: $$category{category})</span></div>
  <div id="programtotal">$howmany</div>
  $selflink
</div>
$notes$programflags
<form action="program-signup.cgi" method="post">\n  $hiddenpersist
    <input type="hidden" name="program" value="$id" />
    <input type="hidden" name="action" value="dosignup" />
    <input type="hidden" name="dummyvar" value="thisdoesnothing" />
    <table class="table signupsheet"><thead>
      <tr><td class="numeric"><a title="Click here to sort by this column." href="program-signup.cgi?action=showprogram&amp;program=$input{program}&amp;sortby=num&amp;$persistentvars&amp;showcanceled=$input{showcanceled}">#</a></td>
          <td><a title="Click here to sort by last name." href="program-signup.cgi?action=showprogram&amp;program=$input{program}&amp;sortby=lastname&amp;$persistentvars&amp;showcanceled=$input{showcanceled}">Attender</a></td>
          <td>Phone</td><td>Signed Up</td><td>Flags</td><td>Comments</td></tr>
    </thead><tbody>
      ]. $existingsignups . $waitlistnote . $waitlistsignups . $newsignup . qq[
    </tbody></table>
    $submitbutton
    </form>\n$cancelednote\n
    <div class="wholeprogramactions"><a class="button" href="program-signup.cgi?action=editprogram&amp;program=$$prog{id}&amp;$persistentvars">Edit Program Details</a></div>];
  } else {
    return qq[<div class="error"><div><strong>Error:</strong></div>
     I cannot seem to find any record of program number $id in the database.</div>];
  }
}

sub flagcheckboxes {
  my ($flags, $flaghash, $prefix) = @_;
  $flaghash ||= \%signupflag;
  $prefix   ||= 'flag';
  my @f = map {
    my ($char, $name, $description, $inherit) = @{$$flaghash{$_}};
    my $checked = ($flags =~ /[$char]/) ? ' checked="checked"' : '';
    my $lcname = lc $name;
    qq[<nobr><input id="cb$prefix$lcname" type="checkbox" name="$prefix$char"$checked />
                     <label for="cb$prefix$lcname"><span class="flagchar">$char</span> - </label><span class="flagname"><abbr title="$description">$name</abbr></span></nobr>]
  } sort {
    $a cmp $b
  } keys %$flaghash;
  return join ' ', @f;
}

sub showflags {
  my ($flags, $flaghash, $abbrev) = @_;
  $flaghash ||= \%signupflag;
  my @f = map {
    my $f = $_;
    my ($char, $name, $description, $inherit) = @{$$flaghash{$f}};
    $abbrev ? qq[<abbr title="$name">$char</abbr>]
      : qq[<abbr title="$description" class="flag"><nobr><span class="flagchar">$char</span> - <span class="flagname">$name</span></nobr></abbr>]
  } sort { $a cmp $b } split //, $flags;
  return join ' ', @f;
}

sub sortbylastname {
  return map {
    #my ($r, $s) = 
    $$_[0]
    #  , $$_[1]; $$r{flags} = $s;
    #$r;
  } sort {
    $$a[1] cmp $$b[1]
  } map {
    my $rec = $_;
    my ($last, $rest, $sortby);
    if ($$rec{attender} =~ /,/) {
      # If it's got a comma in it, assume it's already in surname-first order.
      $sortby = lc $$rec{attender};
    } else {
      ($rest, $last) = $$rec{attender} =~ /^(.*?)\s*(\w+)\s*$/;
      $sortby = lc "$last, $rest";
    }
    #use Data::Dumper; warn Dumper(+{ rec => $rec, sortby => $sortby });
    [ $rec, $sortby ];
  } @_;
}

sub listprograms {
    my $cutoff      = $input{cutoffdate} ? DateTime::From::MySQL($input{cutoffdate}) : undef;
    #warn "Cutoff Date: $cutoff\n";
    my $prev        = join "\n", map {
      my ($increment, $unit, $unitcount) = @$_;
      my $prevcodt    = $cutoff ? DateTime::From::MySQL($input{cutoffdate})->subtract( $unit => $unitcount )
                                : DateTime->now( time_zone => $include::localtimezone )->subtract( $unit => $unitcount );
      my $prevcod     = DateTime::Format::ForURL($prevcodt);
      qq[<a class="button" href="program-signup.cgi?action=listprograms&amp;$persistentvars&amp;cutoffdate=$prevcod&amp;showcanceled=$input{showcanceled}">$increment</a>];
    } (['Day', 'days', 1], ['Week', 'days', 7], ['Month', 'months', 1], ['Quarter', 'months', 3], ['Year', 'years', 1]);
    my $cutoffnote  = $cutoff ? qq[<div class="info">Showing programs ending by ] . include::datewithtwelvehourtime($cutoff) . qq[</div>\n       ] : '';
    my @program     = getprogramlist(100, $cutoff);
    my @ongoing     = grep { $$_{flags} =~ /O/ } @program;
    my @upcoming    = grep { not ($$_{flags} =~ /O/ ) } @program;
    my $programli   = sub {
      my ($prec) = @_;
      my $title     = ($$prec{flags} =~ /X/)
                        ? '<del class="redcancel">' . encode_entities($$prec{title}) . '</del>'
                        : encode_entities($$prec{title});
      my $dt        = DateTime::From::MySQL($$prec{starttime});
      my $when      = include::datewithtwelvehourtime($dt);
      my $dow       = $dt->day_name();
      my $ages      = $$prec{agegroup};
      my $flags     = showflags($$prec{flags}, \%programflag, "abbreviate");
      return qq[<li><a href="program-signup.cgi?action=showprogram&amp;program=$$prec{id}&amp;$persistentvars" title="$when">$title</a>
           for $ages, $dow, $when $flags</li>]
    };
    my $programlist = join "\n       ", map { $programli->($_); } @upcoming;
    my $ongoing = (scalar @ongoing) ? (qq[<div><strong>Ongoing Programs:</strong></div><ul>]
				       . (join "\n       ", map { $programli->($_) } @ongoing) . qq[</ul>]) : "";
  return qq[$cutoffnote$ongoing
<div><strong>Upcoming Programs:</strong></div><ul>$programlist</ul>
  <div class="listactions">Show Previous: $prev</div>
  <div class="listactions"><a class="button" href="program-signup.cgi?action=listprograms&amp;$persistentvars&amp;cutoffdate=] . ($cutoff ? DateTime::Format::ForURL($cutoff) : '') . qq[&amp;showcanceled=1">Show Canceled Programs</a></div>];
}

sub getprogramlist {
  my ($maxprogs, $cutoff, %arg) = @_;
  $cutoff ||= DateTime->now(time_zone => $include::localtimezone);
  $maxprogs = 12 if $maxprogs < 1;
  my @program = getsince('resched_program', 'endtime', $cutoff);
  if ($arg{require_flag}) {
    @program = grep { index($$_{flags}, $arg{require_flag}) >= 0 } @program;
  }
  @program = sort {
    $$a{starttime} cmp $$b{starttime}
      or $$a{endtime} cmp $$b{endtime}
        or $$a{id} cmp $$b{id}
      } @program;
  if (not $input{showcanceled}) {
    @program = grep { not $$_{flags} =~ /X/ } @program;
  }
  if ($maxprogs < scalar @program) {
    @program = @program[ 0 .. ($maxprogs - 1)];
  }
  return @program;
}

sub usersidebar {
  my @program = getprogramlist(getvariable('resched', 'max_sidebar_programs'));
  my $programlist = join "\n       ", map {
    my $prec     = $_;
    my $title    = ($$prec{flags} =~ /X/)
      ? '<del class="redcancel">' . encode_entities($$prec{title}) . '</del>'
      : encode_entities($$prec{title});
    my $dt       = DateTime::From::MySQL($$prec{starttime});
    my $when     = include::datewithtwelvehourtime($dt);
    my $showdate = getvariable('resched', 'sidebar_programs_showdate') ? (' ' . $dt->month_abbr() . '&nbsp;' . $dt->mday()) : '';
    my $showtime = getvariable('resched', 'sidebar_programs_showtime') ? (' ' . include::twelvehourtimefromdt($dt)) : '';
    qq[<li><a href="program-signup.cgi?action=showprogram&amp;program=$$prec{id}&amp;$persistentvars" title="$when">$title$showdate$showtime</a></li>]
  } @program;
  my @rescat = include::categories();
  my $resourcestoday = qq[<div><strong><span onclick="toggledisplay('todaysectionlist','todaysectionmark');" id="todaysectionmark" class="expmark">-</span>
      <span onclick="toggledisplay('todaysectionlist','todaysectionmark','expand');">Today's Bookings:</span></strong>
   <div id="todaysectionlist"><ul>
      ] . (join "\n      ", map {
        my ($catname, @id) = @$_;
        qq[<li><a href="./?view=] . (join ',', @id)
        . qq[&amp;$persistentvars&amp;magicdate=today">$catname</a></li>]
      } @rescat) . qq[   </ul></div></div>];
  my $stylesection = include::sidebarstylesection('', 'program-signup.cgi');
  return qq[<div class="sidebar">
   <div><strong>Program Signup:</strong><ul>
       <li><a href="program-signup.cgi?action=newprogram&amp;$persistentvars">Create New Program</a></li>
       $programlist
       <li><a href="program-signup.cgi?action=listprograms&amp;$persistentvars">List Programs</a></li>
     </ul></div>
   $resourcestoday
   $stylesection
</div>]
}

sub friendlydt {
  my ($dt) = @_;
  carp "friendlydt(): not a valid DateTime object ($dt)" if not ref $dt;
  my $now = DateTime->now(time_zone => $include::localtimezone);
  if ($dt->ymd() eq $now->ymd()) {
    return friendlytime_from_dt($dt, $now);
  } elsif (($dt->clone->add( days => 1)->hms()) eq ($now->hms())) {
    return "yesterday";
  } elsif (($now->clone->add( days => 1)->hms()) eq ($dt->hms())) {
    return "tomorrow";
  } elsif ((($dt->year) eq ($now->year())) and
           (abs($dt->month() - $now->month()) < 6)) {
    return $dt->month_abbr() . " " . include::htmlordinal($dt->mday());
  } else {
    return $dt->year() . " " . $dt->month_abbr() . " " . include::htmlordinal($dt->mday());
  }
}

sub friendlytime_from_dt {
  my ($dt, $now) = @_;
  carp "friendlydt(): not a valid DateTime object ($dt)" if not ref $dt;
  $now ||= DateTime->now(time_zone => $include::localtimezone);
  if (abs($dt->hour() - $now->hour()) > 3) {
    my $h = $dt->clone()->add(minutes => 30)->hour();
    return "Noon" if ($h == 12);
    return "Midnight" if (($h % 24) == 0);
    return (($h % 12) . (($h > 12) ? "pm" : "am"));
  } else {
    my $h = ($dt->hour() % 12) || 12;
    return $h . ":" . sprintf("%02d", $dt->minute())
      . (($dt->hour >= 12) ? "pm" : "am");
  }
}
