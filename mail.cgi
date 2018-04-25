#!/usr/bin/perl -T
# -*- cperl -*-

our $debug = 0;

$ENV{PATH}='';
$ENV{ENV}='';

use HTML::Entities qw();

require "./forminput.pl";
require "./include.pl";
require "./auth.pl";
require "./db.pl";
require "./datetime-extensions.pl";

our %input = %{getforminput()};
our %mailstatus = ( 0 => "Unread",
                    1 => "Not Acted Upon",
                    2 => "Claimed",
                    4 => "Answered",
                    8 => "Resolved",
                    9 => "Archived",);
our %user;

my $ab = authbox(sub { my $x = getrecord('users', shift); "<!-- Hello, $$x{nickname} -->"; });

if ($auth::user) {
  # ****************************************************************************************************************
  # User is authorized as staff.
  %user = %{getrecord('users',$auth::user)}; # Some things below want to know which staff.
  my $title   = "Circ Desk Mail";
  my $content = include::errordiv("Unknown Action", qq[I don't know how to complete the '$input{action} action, sorry.  Maybe Nathan forgot to program that part?']);
  if (not getvariable('resched', 'mail_enable')) {
    $content = include::errordiv("Mail Not Enabled", qq[The <q>Circ Desk Mail</q> feature of Galion ReSched is not enabled and configured.]);
  } elsif ($input{action} eq "showfolder") {
    $content = showfolder($input{folder});
  } elsif ($input{action} eq "showmessage") {
    $content = showmessage($input{headerid});
  } elsif ($input{action} eq "updateheader") {
    $content = updateheader($input{headerid});
  } elsif ($input{action}) {
    $title = "Error: Fallthrough Condition (Unknown Action)"
  } else {
    $content = showfolder("inbox");
  }
  print include::standardoutput($title, $content, $ab, $input{usestyle});
} else {
  print include::standardoutput('Authentication Needed',
                                "<p>In order to access the Circ Desk Mail you need to log in.</p>",
                                $ab, $input{usestyle});
}

exit 0; # Subroutines Follow

sub listmessages {
  my ($messages, $criteria) = @_;
  my $atonce = ($input{showatonce} || getvariable('resched', 'mail_msglist_showatonce') || 20);
  my $totalcount = scalar @$messages;
  my ($prev, $more) = ([], []);
  my $startfrom = $input{startfrom} || 1;
  my $status = $mailstatus{($input{status} || 0)};
  my $folder = encode_entities($input{folder} || 'inbox');
  if ($totalcount < 1) {
    return qq[<div id="messagelistwrapper" class="listwrapper">
    <div class="emptymessagelist">No <q>$status</q> messages found in <q>$folder</q>
         <span class="explan">(criteria: $criteria)</span>.</div></div>];
  }
  if ($startfrom > 0) {
    for (1 .. ($startfrom - 1)) {
      push @$prev, shift @$messages;
    }
  }
  if ((scalar @$messages) > $atonce) {
    $more = $messages;
    $show = [];
    for (1 .. $atonce) {
      push @$show, shift @$more;
    }
  }
  my $max = $startfrom + (scalar @$messages) - 1;
  my $prevlink = ($startfrom > 1) ?
    qq[<span class="prevlink"><a href="mail.cgi?action=showfolder&amp;startfrom=] .
    (($startfrom - $atonce >= 1) ? ($startfrom - $atonce) : 1) .
    qq[&amp;$criteria&amp;usestyle=$input{usestyle}">◀━</a></span>] : "";
  my $nextlink = (scalar @$more) ?
    qq[<span class="nextlink"><a href="mail.cgi?action=showfolder&amp;startfrom=] .
    (($startfrom + $atonce <= $totalcount) ? ($startfrom + $atonce) : 1) .
    qq[&amp;$criteria&amp;usestyle=$input{usestyle}">━▶</a></span>] : "";
  my $n = $startfrom;
  return qq[<div id="messagelistwrapper" class="listwrapper">
  <div class="listnav">$prevlink Showing $startfrom&mdash;$max of $totalcount $status messages in $folder. $nextlink</div>
    <table class="msglist table"><thead>
      <tr><th>#</th><th><span class="msgstatus">Status</span></th>
           <th class="msgfromline">From</th>
          <th><span class="msgsubject">Subject</span> (or <span class="msgfirstline">first line</span>)</th>
          <th class="msginitials">who</th>
      </tr>
    </thead><tbody>] . (join "\n    ", map {
      my $m = $_;
      my $number = $n; $n++;
      my $status = $mailstatus{$$m{status} || 0};
      my $from   = encode_entities($$m{fromline});
      my $subj   = ($$m{subject}) ? (qq[<span class="msgsubject">] . encode_entities($$m{subject}) . qq[</span>]) :
        $$m{firstline} ? (qq[<span class="msgfirstline">] . encode_entities($$m{firstline}) . qq[</span>]) :
        qq[<span class="nosubject">[No Subject]</span>];
      my $inits  = encode_entities($$m{initials});
      my $href   = qq[mail.cgi?action=showmessage&amp;headerid=$$m{id}&amp;usestyle=$input{usestyle}];
      qq[<tr class="msglistitem"><td><a href="$href">$n</a></td>
         <td class="msgstatus">$status</td>
         <td class="msgfromline">$from</td>
         <td><a href="$href">$subj</a></td>
         <td class="msginitials">$inits</td></tr>]
    } @$messages) . qq[
   </tbody></table>
  </div>]
}

sub showfolder {
  my ($f, $s) = @_;
  $s ||= ($input{status} || 0);
  my @m = findrecord('circdeskmail_header', 'folder', $f, 'status', $s);
  return listmessages(\@m, 'folder=' . encode_entities($f) . '&amp;status=' . $s);
}

sub updateheader {
  my ($hid) = @_;
  my $h = getrecord('circdeskmail_header', $hid);
  return include::errordiv("Message Not Found", qq[I could not find message number '$hid' at all, sorry.]) if not $h;
  my ($b) = findrecord('circdeskmail_message', 'headerid', $hid);
  return include::errordiv("Message Not Found", qq[I could only find headers for message number '$hid', not the actual message, sorry.]) if not $h;
  my ($changedanything, $changedeverything) = (0,0);
  for my $k (qw(status folder initials)) {
    if ($input{"msg" . $k} ne $$h{$k}) {
      $$h{$k} = $input{"msg" . $k};
      $changedanything++;
    }}
  for my $k (qw(annotate)) {
    if ($input{"msg" . $k} ne $$b{$k}) {
      $$b{$k} = $input{"msg" . $k};
      $changedanything++;
      $changedeverything++;
    }}
  if ($changedanything) {
    $$h{lastseen} = DateTime::Format::ForDB(DateTime->now( time_zone => $include::localtimezone ));
    updaterecord('circdeskmail_header', $h);
    updaterecord('circdeskmail_message', $b) if $changedeverything;
    return include::infobox("Updated", qq[Your changes have been saved.])
      . showmessage($$h{id});
  } else {
    return include::infobox("No Changes", "You do not seem to have made any changes.");
  }
}

sub showmessage {
  my ($hid) = @_;
  my $h = getrecord('circdeskmail_header', $hid);
  return include::errordiv("Message Not Found", qq[I could not find message number '$hid' at all, sorry.]) if not $h;
  my ($b) = findrecord('circdeskmail_message', 'headerid', $hid);
  return include::errordiv("Message Not Found", qq[I could only find headers for message number '$hid', not the actual message, sorry.]) if not $h;
  my $delivered = include::datewithtwelvehourtime(DateTime::From::MySQL($$h{retrieved}));
  my $from      = encode_entities($$h{fromline});
  my $subject   = $$h{subject} ? encode_entities($$h{subject}) : '[No Subject]';
  my $status    = include::orderedoptionlist('msgstatus', [map { [ $_ => $mailstatus{$_} ] } sort keys %mailstatus], $$h{status});
  my @folder    = ('inbox', (grep { $_ } split/,\s*/, getvariable('resched', 'mail_folders')));
  my $folder    = include::orderedoptionlist('msgfolder', [map { [ $_ => $_ ] } @folder ], $$h{folder});
  my $inits     = encode_entities($$h{initials});
  my $me        = $user{initials} ? (qq[<a class="button" onclick="document.getElementById('msginitials').value = '] . encode_entities($user{initials}) . qq['">&lt;-- ] . encode_entities($user{initials}) . qq[</a>]) : '';
  my $lastseen  = ($$h{lastseen}) ? qq[ <span class="msglastseen">on $$h{lastseen}.</span>] : "";
  my $annotate  = encode_entities($$b{annotate});
  my $headers   = $input{showheaders} ? (qq[<tr class="fullheaders"><td colspan="2">] . showheaders($h, $b) . qq[</tr>]) :
    qq[<tr class="msgfromline"><th>From:</th><td>$from</td></tr>
       <tr class="msgsubject"><th>Subject:</th><td>$subject</td></tr>
       <tr><th></th><td><a href="mail.cgi?action=showmessage&amp;showheaders=yes&amp;headerid=$hid&amp;usestyle=$input{usestyle}">(show all headers)</a></td></tr>];
  return qq[<form class="showmessage"><div class="showmessage">
   <input type="hidden" name="headerid" value="$$h{id}" />
   <input type="hidden" name="action"   value="updateheader" />
   <input type="hidden" name="usestyle" value="$input{usestyle}" />
   <table class="msgmetadata"><tbody>
      <tr class="msgfolder"><th><label for="msgfolder">Folder</label></th>
         <td>$folder</td></tr>
      <tr class="msgstatus"><th><label for="msgstatus">Status</label></th>
         <td>$status</td></tr>
      <tr class="msgannotate">
         <th><label for="msgannotate">Staff Annotation:</label></th>
         <td><input type="text" id="msgannotate" name="msgannotate" size="60" value="$annotate" /></td></tr>
      <tr><th><label for="msginitials">Last touched by</label></th>
          <td><input type="text" id="msginitials" name="msginitials" size="5" value="$inits" /> $me
          $lastseen
          </td></tr>
      <tr><th></th><td><input type="submit" value="Update the Above Info" /></td></tr>
      <tr class="msgretrieved date"><th>Delivered:</th><td>$$h{retrieved}</td></tr>
      $headers
   </tbody></table>

   <div class="msgbody"><pre>] . encode_entities($$b{body}) . qq[</pre></div>
   </div></form>];
}

sub showheaders {
  my ($h, $m) = @_;
  return qq[<div class="headers fullheaders"><pre>] . encode_entities($$m{rawheaders}) . qq[</pre></div>];
}

sub usersidebar {
  my @folder    = ('inbox', (grep { $_ } split/,\s*/, getvariable('resched', 'mail_folders')));
  my @more = map { $$_{folder} } findnotin('circdeskmail_header', 'folder', \@folder);
  @folder = include::uniq(@folder, @more);
  my %total  = %{countfield('circdeskmail_header', 'folder')};
  my %unread = %{countfield('circdeskmail_header', 'folder', undef, undef, 'status', [0])};
  my $folders = qq[<div class="mailfoldersidebar">
  <div id="mailfoldersection"><strong>Mail Folders:</strong></div>
  <ul>] . (join "\n     ", map {
       my $f    = $_;
       my $fenc = encode_entities($f);
       my $unr  = $unread{$f} || 0;
       my $tot  = $total{$f} || 0;
       my $stats  = qq[<span class="folderstats">(] . ($unr ? qq[<span class="unreadcount">$unr</span>/] : '<span class="allread">0</span>/')
         . qq[<span class="msgcount">$tot</span>)</span>];
       my $stati = '';
       if ($f eq ($input{folder} || 'inbox')) {
         my %cnt = %{countfield('circdeskmail_header', 'status', undef, undef, 'folder', [$f])};
         $stati = qq[<ul>
                ] . (join "\n                ",
                     map {
                       my $s = $_;
                       my $count = ($s == 0 and $unread{$f} > 0)
                         ? qq[<span class="unreadcount">$unread{$f}</span>]
                         : ($cnt{$s} || 0);
                       qq[<li>$count <a href="mail.cgi?action=showfolder&amp;folder=$fenc&amp;status=$s&amp;usestyle=$input{usestyle}">$mailstatus{$s}</a></li>]
                     } sort keys %mailstatus) . qq[</ul>];
       }
       qq[<li>$stats <a href="mail.cgi?action=showfolder&amp;folder=$fenc&amp;usestyle=$input{usestyle}">$fenc</a>$stati</li>]
     } @folder) . qq[</ul></div>];
  return qq[<div class="sidebar" id="circdeskmailsidebar">
      <!-- Circ Desk Mail Sidebar -->
      $folders
      <div><a href="index.cgi">Resource Scheduling</a></div>
      <div><a href="program-signup.cgi">Program Signup</a></div>
      <div><a href="staffsch.cgi">Staff Schedules</a></div>
  </div>];
}
