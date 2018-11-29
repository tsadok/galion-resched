#!/usr/bin/perl -T
# -*- cperl -*-

our $debug = 0;#"parse_message_parts";

$ENV{PATH}='';
$ENV{ENV}='';

use HTML::Entities qw();
use Email::MIME;
use MIME::Base64;
use HTML::TreeBuilder;
use Image::Size;

require "./forminput.pl";
require "./include.pl";
require "./auth.pl";
require "./db.pl";
require "./datetime-extensions.pl";
our %html_mail_policy;
do "./html-mail-policy.pl" if -e "./html-mail-policy.pl"; # See html-mail-policy.pl.sample
%html_mail_policy = default_html_mail_policy() if not keys %html_mail_policy;

our %input = %{getforminput()};
our %mailstatus = ( 0 => "Unread",
                    1 => "Not Acted Upon",
                    2 => "Claimed", # This "2" is hardcoded in a findrecord() below, search for YxUikWq
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
  } elsif ($input{action} eq "rawattachmentdata") {
    print include::rawoutput(raw_attachment_data($input{headerid}, $input{partnum}));
    exit 0;
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
       <tr><th></th><td><a href="mail.cgi?action=showmessage&amp;showheaders=yes&amp;headerid=$hid&amp;viewsource=$input{viewsource}&amp;usestyle=$input{usestyle}">(show all headers)</a></td></tr>];
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
   ] . msgbody($$b{body}, $$b{rawheaders}) . qq[
   </div></form>];
}

sub msgbody {
  my ($body, $headers) = @_;
  warn("msgbody()\n") if $debug =~ /msgbody\b/;
  my ($ismime, @part) = parse_message_parts($body, $headers);
  if ($ismime) {
    return qq[<div class="msgbody_whole_wrapper">] . (join "\n", map { msgbody_part($_) } @part) . qq[</div>];
  } else {
    return msgbody_text($body, "N/A");
  }
}

sub parse_message_parts {
  my ($body, $headers) = @_;
  if ($headers =~ m!^Content-Type:\s+multipart/?(\w+);\s+boundary=["'](.*?)['"]\s*$!im) {
    my ($multitype, $boundary) = ($1, $2);
    warn ("multipart\n") if $debug =~ /parse_message_parts/;
    my @rawpart = split /\r?\n?--\Q$boundary\E\r?\n?/, $body;
    warn "" . @rawpart . " raw parts.\n" if $debug =~ /rawparts/;
    my $partnum=0;
    if ($rawpart[0] =~ /This is.*MIME.formatted message/) {
      shift @rawpart;
      warn qq[Discarded "This is a MIME-formatted message" stuff.\n] if $debug =~ /rawparts/; $partnum++;
    }
    my @part = grep { defined $_ } map {
      my $rawdata = $_; $partnum++;
      warn "Processing part $partnum.\n" if $debug =~ /parse_message_parts/;
      my @line = split /\r?\n/, $rawdata;
      warn "" . @line . " lines in part $partnum.\n" if $debug =~ /parse_message_parts/;
      my @nwl = grep { not /^\s*$/ } @line;
      warn "" . @nwl . " non-whitespace lines in part $partnum.\n" if $debug =~ /parse_message_parts/;
      my $thispart = undef;
      if (scalar @nwl) {
        my (@rawheader, @bodyline);
        my ($ctype, $charset, $bound, $encoding, $disposition, $filename, $description, $decoded);
        my $headersdone = 0;
        while (scalar @line) {
          my $l = shift @line;
          if ((not $headersdone) and ($l =~ /^([A-Za-z0-9_-]+)[:]\s*(.*)/)) {
            my ($hname, $value) = ($1, $2);
            push @rawheader, $l;
          } elsif ((not $headersdone) and ($l =~ /^\s+(.*?)\s*$/)) {
            my $prev = pop @rawheader;
            push @rawheader, $prev . $l;
          } elsif (not $headersdone) {
            $headersdone++;
          } else {
            push @bodyline, $l;
          }}
        warn "" . @rawheader . " raw headers and " . @bodyline . " body lines in part $partnum.\n" if $debug =~ /parse_message_parts/;
        if ((scalar @rawheader) or (grep { not /^\s*$/ } @bodyline)) {
          for my $h (@rawheader) {
            if ($h =~ m!Content-Type:\s+(.*?)\s*$!i) {
              my ($raw) = $1;
              my ($mimetype, @info) = split /;\s*/, $raw;
              if ($mimetype =~ m!(\w+)[/](\w+)!) {
                #my ($basetype, $subtype) = ($1, $2);
                $ctype = $mimetype;
              }
              for my $i (@info) {
                if ($i =~ /charset=(.*)/) {
                  $charset = $1;
                }
                if ($i =~ /boundary=["]([^"]+)["]/) {
                  $bound = $1;
                }
              }
            } elsif ($h =~ /Content-Transfer-Encoding:\s+(.*)/i) {
              $encoding = $1;
            } elsif ($h =~ /Content-Disposition:\s+(.*?)(?:; filename=(.*?))?\s*$/i) {
              $disposition = $1;
              $filename = $2 if $2;
            } elsif ($h =~ /Content-Description:\s+(.*)/i) {
              $description = $1;
            } else {
              warn "Unrecognized MIME part header (in part $partnum): $h" if $debug =~ /parse_message_parts/;
            }}
          warn "Part $partnum headers processed.\n" if $debug =~ /parse_message_parts/;
          if ($encoding =~ /base64/i) {
            warn "Decoding part $partnum using base64.\n" if $debug =~ /parse_message_parts/;
            $decoded = decode_base64(join "\n", @bodyline);
          } else { # No other encodings specially supported at this time.
            warn "Not decoding part $partnum.\n" if $debug =~ /parse_message_parts/;
            $decoded = join "\n", @bodyline;
          }
          $thispart = +{ content_type => $ctype,
                         charset      => $charset,
                         boundary     => $bound,
                         encoding     => $encoding,
                         disposition  => $disposition,
                         filename     => $filename,
                         description  => $description,
                         content      => $decoded,
                         rawdata      => $rawdata,
                         partnum      => $partnum,
                       },
                     }
      }
      $thispart;
    } @rawpart;
    return ("Success", @part);
  } else {
    return; # Not multipart.
  }
}

sub msgbody_part {
  my ($part) = @_;
  my $partbody;
  warn "msgbody_part([part $$part{partnum}])\n" if $debug =~ /msgbodypart/;
  if ($$part{content_type} =~ m!^text/plain!) {
    warn "text/plain\n" if $debug =~ /msgbodypart/;
    $partbody = msgbody_text($$part{content}, $$part{partnum});
  } elsif ($$part{content_type} =~ m!^text/html!) {
    warn "text/html\n" if $debug =~ /msgbodypart/;
    if ($input{viewsource}) {
      $partbody = msgbody_text($$part{content}, $$part{partnum}, "nolinks"); # This does encode_entities()
    } else {
      $partbody = msgbody_html($$part{content}, $$part{partnum});
    }
  } elsif ($$part{content_type} =~ m!image[/](png|jpg|jpeg)!) {
    $partbody = msgbody_image($part);
  } elsif ($$part{content_type} =~ m!^multipart[/]!) {
    my ($subhead, $subbod) = split /^\r?\n/m, $$part{content}, 2;
      #$$part{content} =~ /^(.*?)\r?\n\r?\n(.*)$/s;
    use Data::Dumper;
    $partbody =
      qq[<!-- ] . (Dumper(+{ head => $subhead, body => $subbod, whole => $$part{content} })) . qq[ -->]
       . msgbody($subbod, $subhead);
      #. msgbody_binary($part);
  } else {
    warn "application/octet-stream or whatever\n" if $debug =~ /msgbodypart/;
    $partbody = msgbody_binary($part);
  }
  return qq[<div class="msgbody_part_wrapper">
   <!-- MIME Part #:  $$part{partnum} -->
   <!-- Content-Type: $$part{content_type} -->
   <!-- Charset:      $$part{charset} -->
   <!-- Encoding:     $$part{encoding} -->
   <!-- Disposition:  $$part{disposition} -->
   <!-- Filename:     $$part{filename} -->
   <!-- Description:  $$part{description} -->
   $partbody</div>\n];
}

sub raw_attachment_data {
  my ($hid, $partnum) = @_;
  #return ("text/plain", "raw_attachment_data($hid, $partnum);");
  my $h = getrecord('circdeskmail_header', $hid);
  return ("text/plain", "Error: Message not found: I could not find message number '$hid' at all, sorry.") if not $h;
  my ($b) = findrecord('circdeskmail_message', 'headerid', $hid);
  return ("text/plain", "Error: Message Not Found: I could only find headers for message number '$hid', not the actual message, sorry.") if not $h;
  my ($ismime, @part) = parse_message_parts($$b{body}, $$b{rawheaders});
  return ("text/plain", "Error: Cannot parse raw attachment data from part '$partnum' of non-multipart message number '$hid'.") if not $ismime;
  my ($thispart) = grep { $$_{partnum} == $partnum } @part;
  return ("text/plain", "Error: Cannot find part number '$partnum' in multipart message number '$hid', sorry.") if not $thispart;
  return ($$thispart{content_type}, $$thispart{content} ? $$thispart{content} : "ERROR: no decoded content.\n$$thispart{rawdata}");
}

sub msgbody_image {
  my ($part) = @_;
  my ($x, $y);
  my $content = $$part{content};
  eval { ($x, $y) = imgsize(\$content) };
  my $error = $@;
  my $fn = $$part{filename} ? (": " . encode_entities($$part{filename})) : "";
  return "<!-- $error -->" . msgbody_binary($part) if not ($x and $y);
  return qq[<div class="mailattachment imgattachment">
     <img src="mail.cgi?action=rawattachmentdata&amp;headerid=$input{headerid}&amp;partnum=$$part{partnum}" width="$x" height="$y" alt="[attached image$fn]" />
  </div>];
}
sub msgbody_binary {
  my ($part) = @_;
  my ($preview) = map { encode_entities($_) } $$part{content} =~ /^\s*(.{0,60})/;
  my $filename = $$part{filename} ? encode_entities($$part{filename}) : qq[<span class="defaultfilename">attachment.dat</span>];
  return qq[<div class="mailattachment">
     <span class="mailattachpaperclip"><img alt="Attachment: " src="paperclip-green-ryanlerch-64px.png" width="64" height="49" /></span>
     <span class="mailattachpartnum">[MIME part $$part{partnum}]</span>
     <span class="mailattachctype">$$part{content_type}</span>
     <span class="mailattachfilename" title="$preview">$filename</span>
     <span class="mailattachmentdownloadlink"><a href="mail.cgi?action=rawattachmentdata&amp;headerid=$input{headerid}&amp;partnum=$$part{partnum}">[Download]</a></span>
  </div>];
}
sub msgbody_html {
  my ($html, $pn) = @_;
  my $parser = HTML::TreeBuilder->new( store_declarations => undef, );
  my $tree   = $parser->parse_content($html);
  return "Failed to parse the following as HTML:\n" . msgbody_text($html, $pn) if not ref $tree;
  sanitize_html($tree);
  return qq[<div class="msgbody_html"><div>HTML document: <a href="mail.cgi?action=showmessage&amp;headerid=$input{headerid}&amp;viewsource=yes&amp;showheaders=$input{showheaders}&amp;usestyle=$input{usestyle}">View Source</a></div>
  ] . $tree->as_HTML() . qq[</div>];
}

sub sanitize_html {
  my ($element) = @_;
  return encode_entities($element) if not ref $element;
  if ($html_mail_policy{filter_element} and
      $html_mail_policy{filter_element}{__ALL__}) {
    $html_mail_policy{filter_element}{__ALL__}->($element); }
  if ($html_mail_policy{filter_element} and
      $html_mail_policy{filter_element}{$element->tag()}) {
    $html_mail_policy{filter_element}{$element->tag()}->($element); }
  if ($html_mail_policy{whitelist_element}) {
    if (not grep { $_ eq $element->tag() } @{$html_mail_policy{whitelist_element}}) {
      my $old_parent = $element->destroy(); # Bye-bye.
      return;
    }
  } elsif ($html_mail_policy{blacklist_element}) {
    if (grep { $_ eq $element->tag() } @{$html_mail_policy{blacklist_element}}) {
      my $old_parent = $element->destroy(); # So long, screwy.  See you in St. Louis.
      return;
    }
  }
  for my $attrib (grep {
    (not /^_/) and not ($_ eq "text") # skip HTML::Element special attributes
  } $element->all_attr_names()) {
    if ($html_mail_policy{filter_attribute} and
        $html_mail_policy{filter_attribute}{$attrib}) {
      $html_mail_policy{filter_attribute}{$attrib}->($element, $attrib);
    } elsif ($html_mail_policy{whitelist_attribute}) {
      if (not grep { $_ eq $attrib} @{$html_mail_policy{whitelist_attribute}}) {
        $element->attr($attrib, undef); # Nuke it.
      }
    } else {
      if (($html_mail_policy{blacklist_attribute_re} and
           $attrib =~ $html_mail_policy{blacklist_attribute_re}) or
          ($html_mail_policy{blacklist_attribute} and
           (grep { $_ eq $attrib} @{$html_mail_policy{blacklist_attribute}}))) {
        $element->attr($attrib, undef); # Terminated.
      }
    }
  }
  # Now do the children (if any):
  for my $child ($element->content_list()) {
    sanitize_html($child);
  }
}

## Tried to use Email::MIME, but it's not clear how to get the de-part-ified main body.
## sub msgbody {
##   my ($body, $headers) = @_;
##   my $parsed;
##   eval { $parsed = Email::MIME->new($headers . "\n\n" . $body); };
##   warn "Failed to parse message body: $@" if $@;
##   return "<!-- Email::MIME failed to parse the message body, treating it as plain text. -->\n"
##     . msgbody_part($body) if not $parsed;
##   my @part = $parsed->parts();
##   if (scalar @part) {
##     return qq[<div class="msgbodywrapper">
##     ] . (join "\n", map { msgbody_part($_) } @part) . qq[\n</div>\n];
##   } else {
##     return qq[<div class="msgbodywrapper nomimeparts">] . msgbody_text($body) . qq[</div>]
##   }
## }
## 
## sub msgbody_part {
##   my ($part) = @_;
##   return msgbody_text($part) if not ref $part;
##   my $ct = $part->content_type();
##   if ($ct eq "text/plain") {
##     return qq[<div class="mimepart mimeparttext">\n  ] . msgbody_text($part->body_str) . qq[</div>\n];
##   } elsif (($ct eq "text/html")# and ($part->disposition() ne "attachment")
##           ) {
##     return qq[<div class="mimepart mimeparthtml">\n  ] . msgbody_html($part->body_str) . qq[</div>\n];
##   } else {
##     my $fname = encode_entities($part->filename() || $part->invent_filename() || "attachment.dat");
##     return qq[<div class="mimepart mimepartbinary">\n  ] . msgbody_binary($part->body, $fname) . qq[</div>\n];
##   }
## }
## 
## sub msgbody_binary {
##   my ($part, $fn) = @_;
##   my ($preview) = map { encode_entities($_) } $part =~ /^\s*(.{0,60})/;
##   return qq[<div class="mailattachment">
##      <span class="mailattachpaperclip"><img alt="Attachment: " src="paperclip-green-ryanlerch-64px.png" width="64" height="49" /></span>
##      <span class="mailattachfilename" title="$preview">$fn</span>
##   </div>];
## }
## 
## sub msgbody_html {
##   my ($html) = @_;
##   # TODO
##   return msgbody_text($html); # This will encode_entities it.
## }
## 
sub msgbody_text {
  my ($text, $pn, $nolinks) = @_;
  warn "msgbody_text([text], $pn)\n" if $debug =~ /msgbodypart/;
  my ($main, $sig) = map {
    my $x = $_;
    @l = map { my $l = $_;
               $l =~ s!((https?|s?ftp)[:][/]+\S+)!<a href="$1">$1</a>!g
                 if not $nolinks;
               $l;
             } split /\r?\n/, $x;
    while ($l[0] =~ /^\s+$/) {
      shift @l;
    }
    while ($l[-1] =~ /^\s+$/) {
      pop @l;
    }
    join "\n", @l;
  } map { encode_entities($_) } split/^[-]{2}\s+$/m, $text, 2;
  warn "  split off signature" if $debug =~ /msgbodypart/;
  #my ($main, $sig) = ($text, undef);
  #if ($text =~ /\s*(.*)^[-][-]\s+$(.*)/ms) {
  #  ($main, $sig) = ($1, $2);
  #}
  return qq[<div class="msgbody"><pre>]
    . qq[<div class="msgbodymain">$main</div>\n]
    . ((defined $sig) ? (qq[<div class="mailsignature"><div class="sigdash">-- </div>$sig</div>\n])
                      : '<!-- no email signature found -->')
    . qq[</pre></div>\n];
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
  my $claimed = '';
  if ($input{initials} or $user{initials}) {
    my @c = findrecord('circdeskmail_header', 'status', 2, # Hardcoded key from %mailstatus above, search for YxUikWq
                       'initials', ($input{initials} || $user{initials}));
    my $listthrough = (scalar @c) - 1;
    $listthrough = 9 if $listthrough > 9; # Note: it starts at 0, so this allows 10.
    $claimed = qq[<div id="mailclaimedsection"><strong>Claims (] . (scalar @c) . qq[):</strong><ul>
       ] . (join "\n       ", map {
         my $claim = $c[$_];
         qq[<li><a href="mail.cgi?action=showmessage&amp;headerid=$$claim{id}&amp;usestyle=$input{usestyle}">]
           . encode_entities($$claim{subject} || '[No Subject]') . qq[</a></li>]
       } 0 .. $listthrough) . qq[
    </ul></div>];
  }
  return qq[<div class="sidebar" id="circdeskmailsidebar">
      <!-- Circ Desk Mail Sidebar -->$claimed
      $folders
      <div><a href="index.cgi">Resource Scheduling</a></div>
      <div><a href="program-signup.cgi">Program Signup</a></div>
      <div><a href="staffsch.cgi">Staff Schedules</a></div>
  </div>];
}

sub convert_element {
  my ($newtag, $element) = @_;
  my $oldtag = $element->tag;
  $element->tag($newtag);
  $element->attr("class", (join " ", grep { $_ } ($element->attr("class"), $oldtag)));
}

sub convert_to_div {
  convert_element("div", @_);
}

sub default_html_mail_policy {
  return (
          filter_element => +{ __ALL__ => sub { my ($e) = @_; $e->tag(lc $e->tag); },
                               html    => sub { convert_to_div(@_) },
                               head    => sub { convert_to_div(@_) },
                               body    => sub { convert_to_div(@_) },
                             },
          blacklist_element => [qw(applet audio base basefont button canvas dialog embed form frame frameset iframe
                                   link menu menuitem meta nav object script source style track video)],
          blacklist_attribute_re => qr/^on/,
          blacklist_attribute => [qw(action autofocus autoplay bgcolor border buffered code codebase color content
                                     contextmenu controls crossorigin default defer download formaction
                                     href http-equiv icon integrity loop manifest method pattern ping
                                     poster preload shape src srcdoc style target)],
         );
}


