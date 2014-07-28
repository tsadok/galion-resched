#!/usr/bin/perl
# -*- cperl -*-

# CAVEAT:  This script is untested.

# This script is intended to be run from a cron job, to clear out old
# expired authcookies.  Note that it pulls in db.pl from the current
# directory, so the cron job should cd to the resched directory before
# calling this script.  A low volume site like Galion doesn't need
# this, but a site that has a lot of users logging in every day might
# find it useful.

# If you want to only clean out REALLY old cookies, you can pass a
# command line argument indicating the number of additional months'
# worth of login cookies you want to keep.

require "./db.pl";
use DateTime;

my ($extramonths) = @ARGV;
my $cutoff = DateTime->now()->subtract( days => 3, months => ($extramonths || 0), );

# Subtracting 3 days avoids the need to worry about time of day or
# timezones, which means we don't need include.pl, config variables,
# datetime-extensions.pl, or other complications.  Keep it simple.

my $db = dbconn();
my $q  = $db->prepare("DELETE FROM authcookies WHERE expires < ?");
$q->execute($cutoff->ymd());
