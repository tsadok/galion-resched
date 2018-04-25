#!/usr/bin/perl -T
# -*- cperl -*-

# This script is designed to be run periodically, e.g., from a cron job.
# It retrieves mail from a POP3 server and inserts it into the database,
# where mail.cgi can find it and interact with it.

our $debug = 0;

$ENV{PATH}='';
$ENV{ENV}='';

use HTML::Entities qw();
use Mail::POP3Client;
use DateTime;
require "./db.pl";
require "./include.pl";
require "./datetime-extensions.pl";

my $stopat = DateTime->now( time_zone => $include::localtimezone )->add( seconds => 50 );

exit if not getvariable('resched', 'mail_enable');
my $server   = getvariable('resched', 'mail_pop3server');
my $username = getvariable('resched', 'mail_pop3username');
my $password = getvariable('resched', 'mail_pop3password');
my $delay    = getvariable('resched', 'mail_pop3iterdelay');
die "Not configured:  mail_pop3server (see config.cgi)" if not $server;
die "Not configured:  mail_pop3username (see config.cgi)" if not $username;
die "Not configured:  mail_pop3password (see config.cgi)" if not $password;

while (DateTime->now( time_zone => $include::localtimezone ) < $stopat) {
  $pop = new Mail::POP3Client( USER     => $username,
                               PASSWORD => $password,
                               HOST     => $server, );
  my $last = $pop->Count();
  my $this = 1;
  while (($this <= $last) and (DateTime->now( time_zone => $include::localtimezone ) < $stopat)) {
    my $headers     = $pop->Head($this);
    my $body        = $pop->Body($this);
    my ($subject)   = $headers =~ /^Subject:\s+(.*?)\s*$/m; # This is horribly oversimplified, may need better handling.
    my ($fromline)  = $headers =~ /^From:\s+(.*?)\s*$/m;    # Ditto
    my ($firstline) = (grep { $_ } map { chomp; $_ } split /$/, $body);
    if (addrecord('circdeskmail_header', +{ retrieved => DateTime::Format::ForDB(DateTime->now( time_zone => $include::localtimezone )),
                                            subject   => $subject,
                                            fromline  => $fromline,
                                            status    => 0,
                                            folder    => 'inbox', })) {
      my $h = $db::added_record_id;
      if ($h and addrecord('circdeskmail_message',
                           +{ headerid   => $h,
                              rawheaders => $headers,
                              body       => $body, })) {
        # Successfully inserted into the database.
        $pop->Delete($this);
      }}
    select undef, undef, undef, $delay if $delay;
    $this++;
  }
  $pop->Close();
  sleep 5;
}
