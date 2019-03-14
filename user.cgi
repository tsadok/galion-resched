#!/usr/bin/perl
# -*- cperl -*-

use HTML::Entities qw(); sub encode_entities{ my $x = HTML::Entities::encode_entities(shift @_);
                                              $x =~ s/[-][-]/&mdash;/g;
                                              return $x; }
use Data::Dumper;
require "./forminput.pl";
require "./include.pl";
require "./auth.pl";
require "./db.pl";
require "./datetime-extensions.pl";
require "./userform.pl";
our %input = %{getforminput()};

sub usersidebar; # Defined below.

my $ab = authbox(sub { my $x = getrecord('users', shift); "<!-- Hello, $$x{nickname} -->"; });
if ($auth::user) {
  my $title   = "User Info - Galion ReSched";
  my $content = qq[<h1>Error: Fallthrough Condition</h1><p>user.cgi doesn't know what you want to do.</p>];
  if ($input{userid}) {
    $content = userpage(include::getnum('userid'));
  } elsif ($input{user}) {
    $content = userpage(include::getnum('user'));
  }
  print include::standardoutput($title, $content, $ab, $input{userstyle});
} else {
  # User is not authorized for squat.
  print include::standardoutput('Authentication Needed',
                                "<p>In order to access Resource Scheduling you need to log in.</p>",
                                $ab, $input{usestyle});
}


exit 0;

sub userpage {
  my ($userid) = @_;
  my $user  = getrecord('users', $userid);
  ref $user or return include::errordiv('Error:  User Record Not Found', qq[I cannot seem to find user ID <q>$userid</q> in the database.]);
  my $actor = getrecord('users', $auth::user);
  my $admin = ($$actor{flags} =~ /A/) ? 1 : 0;
  if ($input{action} eq "saveuser") {
    # Update the record with supplied data, permissions permitting.
    if (($userid eq $auth::user) or $admin) {
      # Some things, the user can do for themselves, or admin can do it:
      for my $f (qw(fullname nickname initials)) {
        $$user{$f} = $input{$f} || $$user{$f};
      }
      if ($input{setpass} eq 'unsetpass') {
        $$user{password}   = undef;
        $$user{hashedpass} = undef;
      } elsif ($input{setpass} eq 'setnewpass') {
        my $minlength = getvariable('minimum_password_length') || 12;
        if ((length $input{newpassonce}) < $minlength) {
          return include::errordiv('Password Too Short', qq[New passwords must be at least $minlength bytes long.]);
        } elsif ($input{newpassonce} ne $input{newpasstwice}) {
          return include::errordiv('Password Mismatch', qq[The password you typed does not match the second time you typed it.  Please type the same password both times to ensure that the new password is known.]);
        }
        $$user{salt}       = newsalt();
        $$user{hashedpass} = md5_base64($input{newpassonce} . $$user{salt});
        $$user{password}   = undef unless getvariable('resched', 'retain_cleartext_passwords');
      } elsif ($$user{password} and not $$user{hashedpass}) {
        $$user{salt}       = newsalt();
        $$user{hashedpass} = md5_base64($$user{password} . $$user{salt});
        $$user{password}   = undef unless getvariable('resched', 'retain_cleartext_passwords');
      }
      # Other things are admin-only:
      if ($admin) {
        my $username = lc($input{userusername} || $$user{username});
        $username =~ s/[^a-z0-9]+/_/gi;
        $username =~ s/^_+//g;
        $username =~ s/_+$//g;
        $username =~ s/^[^a-z]//gi;
        while (grep { $$_{id} ne $$user{id} } findrecord('users', 'username', $username)) {
          if (not $username =~ /\d$/) { $username .= "0"; }
          $username++;
        }
        $$user{username} = $username;
        $$user{flags}    = join '', grep { $input{"userflag$_"} } keys %include::userflag;
      }
      updaterecord('users', $user);
    }}
  return userform($user, undef,
                  action    => "user.cgi",
                  theuser   => "you",
                  theuser_s => "your",
                  conjs     => "<!-- s -->",
                 )
    . (($userid eq $auth::user) ? prefsform($user) : "");
}

sub prefsform {
  return qq[<div class="prefsform"><form class="prefsform" action="user.cgi" method="post">[TODO:  User Preferences]</form></div>]
}

sub usersidebar {
  return qq[<!-- User Sidebar Goes Here -->];
}
