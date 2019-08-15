#!/usr/bin/perl -T
# -*- cperl -*-

use strict;
use Carp;

sub userform {
  my ($u, $hiddenpersist, %arg) = @_;
  $u ||= +{ };
  $arg{persistentvars} ||= "";
  $arg{hiddenpersist}  ||= "";
  $arg{action}         ||= "admin.cgi";
  $arg{theuser}        ||= "the user";
  $arg{theuser_s}      ||= "the";
  $arg{conjs}          ||= 's';
  my $notauth   = include::errordiv("Not Authorized", "You may need to log in, or something.");
  return $notauth if not $auth::user;
  my $actor     = getrecord('users', $auth::user);
  return $notauth if not ref $actor;
  my $admin     = ($$actor{flags} =~ /A/) ? 1 : 0;
  my $sameuser  = ($$u{id} eq $$actor{id}) ? 1 : 0;
  my $idfield   = $$u{id} ? qq[<input type="hidden" name="userid" value="$$u{id}" />] : '';
  my $savewords = $$u{id} ? 'Save Changes' : 'Create User';
  my $username  = encode_entities($$u{username});
  my $fullname  = encode_entities($$u{fullname});
  my $nickname  = encode_entities($$u{nickname});
  my $initials  = encode_entities($$u{initials} || "");
  my $password  = $$u{password} ? 'Legacy' : ($$u{salt} and $$u{hashedpass}) ? 'Salted' : $$u{hashedpass} ? 'Unsalted' : 'Unset';
  my $flaglabel = 'Flags:';
  my $flagrows  = $admin ? (join "\n               ", map {
    my ($flagchar, $flagshortname, $flagdetails) = map { encode_entities($_) } @{$include::userflag{$_}};
    my $checked = ($$u{flags} =~ /$flagchar/) ? 'checked="checked"' : '';
    my $label;
    ($label, $flaglabel) = ($flaglabel, '');
    qq[<tr><th>$label</th>
           <td><input type="checkbox" id="userflag$flagchar" name="userflag$flagchar" $checked />
               <label for="userflag$flagchar">$flagshortname</label></td>
           <td class="explan"><label for="userflag$flagchar">$flagdetails</label></td></tr>]
  } sort { $a cmp $b } keys %include::userflag)
    : qq[<!-- TODO: perhaps some flags could be shown to any user? -->];
  my $passexplan = '';
  if (($password eq 'Salted') or ($password eq 'Unsalted') or ($password eq 'Legacy')) {
    $passexplan    = ucfirst($arg{theuser_s}) . qq[ password allows $arg{theuser} to log into $arg{theuser_s} account.  ];
    if ($password eq 'Legacy') {
      $passexplan .= 'Currently, it is stored in the database in cleartext.  ';
    } elsif ($password eq 'Unsalted') {
      $passexplan .= 'Currently, it is stored in the database without any per-user salt, which makes it vulnerable to precomputed-hash attacks (<q>Rainbow Tables</q>, etc.)';
    } elsif ($password eq 'Salted') {
      $passexplan .= 'It is hashed with ' . (length $$u{salt}) . ' bytes of per-user salt.  ';
    }
  } else {
    $passexplan    = qq[Currently this account has no password.  Setting one would allow $arg{theuser} to log in using $arg{theuser_s} username and password.  ];
  }
  if (($password eq 'Unsalted') or ($password eq 'Legacy')) {
    $passexplan   .= 'Ideally, all passwords should either be Unset or Salted.  ';
    if ($password eq 'Legacy') {
      $passexplan .= qq[If you save the record, $arg{theuser_s} existing password will be hashed with $auth::saltlength bytes of per-user salt.  ];
      if (getvariable('resched', 'retain_cleartext_passwords')) {
        $passexplan .= qq[However, the Legacy (unhashed) password will be retained, per <a href="config.cgi?$arg{persistentvars}">site configuration</a>.];
      }
    } else {
      if (not getvariable('resched', 'retain_cleartext_passwords')) {
        $passexplan .= ucfirst($arg{theuser_s}) . qq[ existing password will be salted (and hashed) automatically the next time $arg{theuser} log$arg{conjs} in with it, or if ];
      } else {
        $passexplan .= 'If ';
      }
      $passexplan   .= qq[you set a new password, it will be hashed with $auth::saltlength bytes of per-user salt.  ];
    }
  }
  if (($password eq 'Salted') or ($password eq 'Unsalted') or ($password eq 'Legacy')) {
    $passexplan   .= qq[If $arg{theuser_s} password is Unset, $arg{theuser} will no longer be able to log in with it.  ];
  }
  $passexplan .= qq[If you set a new password, it will be hashed with $auth::saltlength bytes of per-user salt]
    . (getvariable('resched', 'retain_cleartext_passwords')
       ? qq[, but the clear-text password will also be stored (because <code>retain_cleartext_passwords</code> is set in the per-site configuration)]
       : "") . qq[.  ];
  my $ipauthpointer = () ? qq[See also: <a href="admin.cgi?action=ipauthlist">authentication via IP address settings</a>] : "";
  my $usernamerow = $admin ? qq[<tr><th><label for="userusername">username:</label></th>
           <td><input type="text" size="20" id="userusername" name="userusername" value="$username" /></td>
           <td class="explan">] . ucfirst($arg{theuser_s}) . qq[ username should consist of lowercase letters, with no spaces or other weird characters.
                              This field is <strong>required</strong>.</td></tr>]
    : qq[<tr><th>username:</th><td>$username</td></tr>];
  my $fullnamerow = ($admin or $sameuser) ? qq[<tr><th><label for="fullname">Full Name:</label></th>
           <td><input type="text" size="30" id="fullname" name="fullname" value="$fullname" /></td>
           <td class="explan">This is where you put $arg{theuser_s} human-readable name.  This field
                              <strong>can</strong> contain Mixed Case, spaces, apostrophes, etc.</td></tr>]
    : qq[<tr><th>Full Name:</th><td>$fullname</td></tr>];
  my $nicknamerow = ($admin or $sameuser) ? qq[<tr><th><label for="nickname"><q>Nickname:</q></label></th>
           <td><input type="text" size="30" id="nickname" name="nickname" value="$nickname" /></td>
           <td class="explan">] . ucfirst($arg{theuser_s}) . qq[ nickname is what the software will call $arg{theuser}.
                              It can be whatever $arg{theuser} want$arg{conjs}, but it defaults to $arg{theuser_s} username.</td></tr>]
             : qq[<tr><th><q>Nickname</q>:</th><td>$nickname</td></tr>];
  my $initialsrow = ($admin or $sameuser) ? qq[<tr><th><label for="initials">Initials:</label></th>
           <td><input type="text" size="5" id="initials" name="initials" value="$initials" /></td></tr>]
    : qq[<tr><th>Initials:</th><td>$initials</td></tr>];
  my $passwordrow = ($admin or $sameuser) ? qq[<tr><th>Password:</th>
           <td>$password</td>
           <td class="explan" rowspan="2">$passexplan</td></tr>
       <tr><th></th><td><div><input type="radio" name="setpass" id="leavepassalone" value="leavepassalone" checked="checked" />
                             <label for="leavepassalone">Do Not Change</label></div>
                        <div><input type="radio" name="setpass" id="unsetpass" value="unsetpass" />
                             <label for="unsetpass">Unset / Disable</label></div></tr>
       <tr><th></th><td><div><input type="radio" name="setpass" id="setnewpass" value="setnewpass" />
                             <label for="setnewpass">Set New Password:</label></div></td>
                    <td><table><tbody>
                          <tr><td><label for="newpassonce">New Password:</label></td>
                              <td><input type="text" id="newpassonce" name="newpassonce" size="30" /></td></tr>
                          <tr><td><label for="newpasstwice">Type Again:</label></td>
                              <td><input type="text" id="newpasstwice" name="newpasstwice" size="30" /></td></tr>
                        </tbody></table></td></tr>]
    : '<!-- You do not need password info about another user if you are not admin, no. -->';
  my $saverow = ($admin or $sameuser) ? qq[<tr><td colspan="3"><input type="submit" value="$savewords" /></td></tr>] : "";
  return qq[<form class="edituserform" action="$arg{action}" method="post">
     <input type="hidden" name="action" value="saveuser" />
     $idfield
     <table class="table settingsform"><tbody>
       $usernamerow
       $fullnamerow
       $nicknamerow
       $initialsrow
       $passwordrow
       $flagrows
       $saverow
     </tbody></table>
  </form>\n]
}

42;
