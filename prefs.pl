#!/usr/bin/perl
# -*- cperl -*-

require "./db.pl";

our %pref = ( useajax => +{ prefname  => "useajax",
                            sortorder => 100,
                            shortdesc => "Use optional Javascript/AJAX features.",
                            longdesc  => "If your web browser has Javascript disabled for some reason, turning this off will result in traditional links that will still work, instead of scripted links that don't.",
                            type      => "boolean",
                            default   => "true",
                          },
              usestyle => +{ prefname  => "usestyle",
                             sortorder => 200,
                             shortdesc => "Visual Style",
                             longdesc  => "Which color scheme do you prefer?",
                             type      => "enum",
                             enum      => [ [ darkonlight => "Dark on Light" ],
                                            [ lightondark => "Light on Dark" ],
                                            [ lowcontrast => "Low Contrast"],
                                          ],
                             default   => "lowcontrast",
                           },
            );

sub main::updatepref {
  my ($pname, $uid, $value) = @_;
  return if not $uid;
  my ($p) = findrecord("resched_preference", user => $uid, prefname => $pname);
  if ($p) {
    $$p{value} = $value;
    my $result = updaterecord("resched_preference", $p);
    return if not @$result; return 1;
  } else {
    my $result = addrecord("resched_preference", +{ prefname => $pname,
                                                    user     => $uid,
                                                    value    => $value,
                                                  });
    return if not $result; return 1;
  }
}

sub main::getpref {
  my ($pname, $uid) = @_;
  return $pref{$pname}{default} if not $uid;
  my ($p) = findrecord("resched_preference", user => $uid, prefname => $pname);
  if (ref $p) {
    return $$p{value};
  } else {
    return $pref{$pname}{default};
  }
}

42;
