#!/usr/bin/perl
# -*- cperl -*-

require "./db.pl";
use Digest::MD5 qw(md5_base64);

print qq[This script creates a resched user, in the users table in the
resched database.  This account can then be used to log into
resched via the web interface.\n];
my $fullname = gettrueinput("Enter a human-readable name for the user you wish to create:");
my ($dfnick) = $fullname =~ /(\w+)/;
my $nickname = getinput("Enter a nickname for this user (default: $dfnick):");
$nickname  ||= $dfnick;
my $defusern = lc $nickname; $dfusern =~ s/\s*/_/g;
my $username = getinput("Enter a username for this user (default: $defusern):");
$username  ||= $defusern;
my $extant   = findrecord('users', 'username', $username);
die "User already exists: $username" if ref $extant;
my ($password, $passchek) = ('A', 1337);
while ($password ne $passchek) {
  $password = gettrueinput("Enter a password for this user:");
  $passchek = gettrueinput("Enter the same password again:");
  print "Oops, that didn't match.\n" if $password ne $passchek;
}
my $userrec    = +{
                   username   => $username,
                   hashedpass => $hashedpass,
                   fullname   => $fullname,
                   nickname   => $nickname,
                  };
my $salt = '';
my $usesalt    = getinput("Use salt? (default: yes)");
if (not ($usesalt =~ /n/)) {
  my @schar       = ('a' .. 'z', 'A' .. 'Z', 0 .. 9);
  $salt           = join "", map { $schar[rand @schar] } 1 .. 250;
  warn "Using salt: $salt\n";
  $$userrec{salt} = $salt;
}
#warn "Hash without salt: " . md5_base64($password) . "\n";
warn "Salted Hash:    " . md5_base64($password . $salt) . "\n";
$$userrec{hashedpass} = md5_base64($password . $salt);

my $flags = '';
my $admin = getinput("Do you want this user to have administrative privileges,
   for editing schedules and resources and users?");
if (($admin =~ m/y/i) and not ($admin =~ m/n/i)) { $flags .= 'A'; }

$$userrec{flags} = $flags;
use Data::Dumper; warn Dumper($userrec);
addrecord('users', $userrec);

my $id = $db::added_record_id;
my $rec = getrecord('users', $id);
if (ref $rec) {
  print "Successfully added user $id\n";
} else {
  print "Failed.\n";
}
exit 0;


sub getinput {
  my ($prompt) = @_;
  $prompt ||= 'Enter a value:';
  print $prompt . "\n";
  $line = <STDIN>;
  ($answer) = $line =~ /(.*?)$/;
  return $answer;
}

sub gettrueinput {
  my $answer;
  while (not $answer) {
    $answer = getinput(@_);
  }
  return $answer;
}
