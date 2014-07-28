#!/usr/bin/perl -T
# -*- cperl -*-

sub ajaxfailure {
  my (%arg) = @_;
  return qq[Error: $arg{error}\n\nLikely cause:\n$arg{likelycause}\n\nSuggestion:\n$arg{suggestion}];
}

sub ajaxalert {
  return qq[<alert>@_</alert>];
}

sub ajaxreplace {
  my ($id, $newstuff, $focus) = @_;
  my $focelt = $focus ? qq[<focus>$focus</focus>] : '';
  return qq[<replace>
  <replace_within>$id</replace_within>
  <replacement xmlns="http://www.w3.org/1999/xhtml">$newstuff</replacement>
</replace>
$focelt];
}
sub ajaxvarupdate {
  my ($id, $newvalue, $focus) = @_;
  my $focelt = $focus ? qq[<focus>$focus</focus>] : '';
  return qq[<varupdate>
  <variable>$id</variable>
  <newvalue>$newvalue</newvalue>
</varupdate>
$focelt];
}
sub ajaxtoggledisplay {
  my ($id, $force, $markerid, $focus) = @_;
  my $focelt = $focus    ? qq[<focus>$focus</focus>] : '';
  my $coerce = $force    ? qq[  <togglecoerce>$force</togglecoerce>\n] : ''; # ajax.js only supports coercing to inline right now, but block support could be added.
  my $marker = $markerid ? qq[  <togglemarker>$markerid</togglemarker>\n] : '';
  return qq[<toggledisplay>
  <toggleelement>$id</toggleelement>\n$coerce$marker</toggledisplay>\n$focelt];
}

sub sendfailure {
  sendalert(ajaxfailure(@_));
}
sub sendalert {
  sendresponse(ajaxalert(@_));
}
sub sendalertandreplace { # Exists for legacy reasons.  Deprecated.
  my ($id, $alert, $newstuff) = @_;
  sendresponse(ajaxalert($alert) . ajaxreplace($id, $newstuff));
}
sub sendreplace {
  sendresponse(ajaxreplace(@_));
}
sub sendvarupdate {
  sendresponse(ajaxvarupdate(@_));
}

sub sendresponse {
  my ($stuff) = @_;
  my $response = qq[Content-type: application/xml\n\n
<dynamic_info>
$stuff
</dynamic_info>
];
  #warn $response;
  print $response;
  exit 0;
}

1;
