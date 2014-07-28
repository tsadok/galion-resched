#!/usr/bin/perl -T
$ENV{PATH}='';

require "./forminput.pl";
require "./include.pl";
%input = %{getforminput()}; @input = map { ($_, $input{$_}) } keys %input;
require "./auth.pl";


my $ab = authbox(sub { my $x = getrecord('users', shift); "<div>Hi, $$x{nickname}</div>"; });
my $blah = "<div>Blah, blah, blah, ...</div>";
my @letter = qw(a b c d e f g h i j k l m n o p q r s t u v w x y z);
for (1..10) {
  $blah .= " ";
  for (1..(2+rand(30))) {
    $blah .= $letter[rand@letter];
  }
}

print "Content-type: $include::content_type\n" . $auth::cookie . "\n";

print qq[$include::doctype
<html>
<head>
<title>Testing the Authbox</title>
$include::style
</head>
<body><!-- @input -->
<table>
  <tr><td>$blah
  </td><td class="authbox">$ab
  </td></tr>
</table>
$include::footer
</body>
</html>\n];
