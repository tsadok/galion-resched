#!/usr/bin/perl

require "./db.pl";
require "./datetime-extensions.pl";
require "./sitecode.pl";

use Mail::Sendmail;

my $now   = DateTime::Format::ForDB(DateTime->now());
my $delay = getvariable('resched', "smtp_retry_delay") || 10;

my @queue = grep { $now gt $$_{tryafter} } findnullfield("resched_mailqueue", "sent");

print "Attempting to process " . @queue . " enqueued message(s)...\n" if not grep { /silent/ } @ARGV;
for my $q (@queue) {
  my ($body, $from, $subj);
  if ($$q{mailtype} eq 'meetingroompolicy') {
    eval {
      $body = meetingroompolicytext();
    }; if (not $body) {
      if (open MRP, "<", "meeting-room-policy.txt") {
        $body = join "", <MRP>;
        close MRP;
      } else {
        logit("Cannot send Meeting Room Policy:  do not have a copy of the policy.");
        logit("Please supply either meeting-room-policy.txt or meetingroompolicytext() in sitecode.pl")
      }}
    $from = getvariable("resched", "smtp_mrp_from_address");
    $subj = getvariable("resched", "smtp_mrp_subject") || "Meeting Room Policy";
    if ($from) {
      if (sendmessage( From    => $from,
                       Subject => $subj,
                       To      => $$q{toaddress},
                       Message => $body)) {
        $$q{sent} = $now;
        updaterecord("resched_mailqueue", $q);
      } else {
        delaymessage($q);
      }
    } else {
      warn "ERROR: config variable 'smtp_mrp_from_address' is not set.  Meeting room policy email message NOT SENT.\n";
      delaymessage($q);
    }
  } else {
    warn "Unrecognized mailtype: '$$q{mailtype}'.  No action taken.\n";
    delaymessage($q);
  }
}

sub logit {
  my (@msg) = @_;
  my $logfile = getvariable("resched", "smtp_failure_logfile") || "/var/log/resched-mailqueue.log";
  if (open LOG, ">", $logfile) {
    print LOG "$_\n" for @msg;
  } else {
    warn "Cannot write to logfile ($logfile): $!";
    warn $_ for @msg;
  }
}

sub sendmessage {
  my %arg = @_;
  @{$Mail::Sendmail::mailcfg{'smtp'}} = (split /,\s*/, getvariable("resched", "smtp_server"));
  if (not scalar @{$Mail::Sendmail::mailcfg{'smtp'}}) {
    logit("Config variable smtp_server not configured.  Unable to send mail without an outgoing mail server.");
    return; # Returning false indicates failure.
  }
  my $ok = sendmail(%arg);
  return $ok if $ok; # Returning a true value signals success.
                     # There's no need to log this: there's no error,
                     # and the sent bit on the record will get set.
  logit(qq[Failed to send message To $arg{To} From $arg{From} Subject $arg{Subject}],
        qq[ * Mail::Sendmail log says:  $Mail::Sendmail::log]);
  return; # returning false indicates failure.
}

sub delaymessage {
  my ($msg) = @_;
  $$msg{attempts}++;
  my $dt = DateTime::From::DB($$msg{tryafter})->add(seconds => $delay * $$msg{attempts});
  $$msg{tryafter} = DateTime::Format::ForDB($dt);
  updaterecord("resched_mailqueue", $msg);
}
