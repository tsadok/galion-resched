#!/usr/bin/perl -T
# -*- cperl -*-

$cgidb::version = "0.0.3";
# Version 0.0.1 was developed by jonadab at home.
# Version 0.0.2 was enhanced by Nathan at GPL for use in the inventory database.
# Version 0.0.3 was adjusted with optimizations for the resource scheduling database.
# Version 0.0.4 was updated with the multi-field version of findrecord()
#               and augmented with findbetween(), for staff scheduling purposes.

# Database functions for inclusion.
# ADD:     $result  = addrecord(tablename, $record_as_hashref);
# UPDATE:  @changes = @{updaterecord(tablename, $record_as_hashref)};
# GET:     %record  = %{getrecord(tablename, id)};
# GETALL:  @records =   getrecord(tablename);     # Not for enormous tables.
# GETNEW:  @records =   getsince(tablename, timestampfield, datetimeobject);
# BETWEEN: @records = findbetween(tablename, datetimefield, startdatetimeobject, enddatetimeobject [, fieldname, exact_value, ... ]);
# OVERLAP: @records = finddateoverlap(tablename, starttimefield, endtimefield, startdt, enddt, [, fieldname, exact_value, ... ]);
# FIND:    @records = findrecord(tablename, fieldname, exact_value [, fieldname, exact_value, ...]);
# SEARCH:  @records =   searchrecord(tablename, fieldname, value_substring);
# COUNT:   %counts  = %{countfield(tablename, fieldname)}; # Returns a hash with counts for each value.
# COUNT:   %counts  = %{countfield(tablename, fieldname, start_dt, end_dt)}; # Ditto, but within the date range; pass DateTime objects.
# Special variables stored in the database:
# GET:     $value   = getvariable(namespace, varname);
# SET:     $result  = setvariable(namespace, varname, value);

# MySQL also provides regular expression capabilities; I might add a
# function for that here at some future point.

use strict;
use DBI();
use Carp;
require "./dbconfig.pl";

sub washbookingrecord {
  my ($unwashed) = @_;
  my $washed;
  $washed = +{ map { $_ => $$unwashed{$_} } keys %$unwashed };
  delete $$washed{fromtime_datetime};
  delete $$washed{until_datetime};
  delete $$washed{donetime_datetime};
  if ($$washed{latestart} eq $$washed{fromtime}) {
    $$washed{latestart} = undef;
  }
  return $washed;
}

my $db;
sub dbconn {
  # Returns a connection to the database.
  # Used by the other functions in this file.
  $db = DBI->connect("DBI:mysql:database=$dbconfig::database;host=$dbconfig::host",
                     $dbconfig::user, $dbconfig::password, {'RaiseError' => 1})
    or die ("Cannot Connect: $DBI::errstr\n");
  #my $q = $db->prepare("use $dbconfig::database");
  #$q->execute();
  return $db;
}

sub finddateoverlap {
  # OVERLAP: @records = finddateoverlap(tablename, starttimefield, endtimefield, startdt, enddt, [, fieldname, exact_value, ... ]);
  my ($table, $startfield, $endfield, $startdt, $enddt, @more) = @_;
  my (%fv, @field, $field, $value);
  while (scalar @more) {
    ($field, $value, @more) = @more;
    die "findspanning called with unbalanced arguments (no value for $field field)" if not defined $value;
    push @field, $field;
    $fv{$field} = $value;
  }
  my $db = dbconn();
  my $q = $db->prepare("SELECT * FROM $table WHERE "
                       . (join " AND ", (qq[$startfield <= ?],
                                         qq[$endfield >= ?],
                                         map { qq[$_=?] } @field )));
  $q->execute(DateTime::Format::ts($enddt),
              DateTime::Format::ts($startdt),
              map { $fv{$_} } @field);
  my @answer; my $r;
  while ($r = $q->fetchrow_hashref()) {
    if (wantarray) {
      push @answer, $r;
    } else {
      return $r;
    }
  }
  return @answer;
}

sub findbetween {
# BETWEEN:  @records = findbetween(tablename, datetimefield, startdatetimeobject, enddatetimeobject [, fieldname, exact_value, ... ]);
  my ($table, $dtfield, $start, $end, @more) = @_;
  my (%fv, @field, $field, $value);
  while (scalar @more) {
    ($field, $value, @more) = @more;
    die "findbetween called with unbalanced arguments (no value for $field field)" if not defined $value;
    push @field, $field;
    $fv{$field} = $value;
  }
  my $db = dbconn();
  my $q = $db->prepare("SELECT * FROM $table WHERE " . (join " AND ", (qq[$dtfield >= ?],
                                                                       qq[$dtfield <= ?],
                                                                       map { qq[$_=?] } @field )));
  $q->execute(DateTime::Format::ts($start),
              DateTime::Format::ts($end),
              map { $fv{$_} } @field);
  my @answer; my $r;
  while ($r = $q->fetchrow_hashref()) {
    if (wantarray) {
      push @answer, $r;
    } else {
      return $r;
    }
  }
  return @answer;
}

sub getsince {
# GETNEW:  @records =   getsince(tablename, timestampfield, datetimeobject);
  my ($table, $dtfield, $dt, $q) = @_;
  die "Too many arguments: getrecord(".(join', ',@_).")" if $q;
  ref $dt or confess "getsince() called without a DateTime object.";
  my $when = DateTime::Format::ts($dt);
  my $db = dbconn();
  $q = $db->prepare("SELECT * FROM $table WHERE $dtfield >= $when");  $q->execute();
  my @answer; my $r;
  while ($r = $q->fetchrow_hashref()) {
    push @answer, $r;
  }
  return @answer;
}

sub getrecord {
# GET:     %record  = %{getrecord(tablename, id)};
# GETALL:  @recrefs = getrecord(tablename);     # Don't use this way on enormous tables.
  my ($table, $id, $q) = @_;
  die "Too many arguments: getrecord(".(join', ',@_).")" if $q;
  my $db = dbconn();
  $q = $db->prepare("SELECT * FROM $table".(($id)?" WHERE id = '$id'":""));  $q->execute();
  my @answer; my $r;
  while ($r = $q->fetchrow_hashref()) {
    if (wantarray) {
      push @answer, $r;
    } else {
      return $r;
    }
  }
  return @answer;
}

sub changerecord {
  # Used by updaterecord.  Do not call directly; use updaterecord instead.
  my ($table, $id, $field, $value) = @_;
  my $db = dbconn();
  my $q = $db->prepare("update $table set $field=? where id='$id'");
  my $answer;
  eval { $answer = $q->execute($value); };
  carp "Unable to change record: $@" if $@;
  return $answer;
}

sub updaterecord {
# UPDATE:  @changes = @{updaterecord(tablename, $record_as_hashref)};
# See end of function for format of the returned changes arrayref
  my ($table, $r, $f) = @_;
  die "Too many arguments: updaterecord(".(join', ',@_).")" if $f;
  my %r;
  if ($table eq 'resched_booking') {
    my $w = washbookingrecord($r);
    %r = %$w;
  } else {
    %r = %$r;
  }
  my %o = %{getrecord($table, $r{id})};
  my @changes = ();
  foreach $f (keys %r) {
    if ((not defined $r{$f}) or ($r{$f} ne $o{$f})) {
      my $result = changerecord($table, $r{id}, $f, $r{$f});
      push @changes, [$f, $r{$f}, $o{$f}, $result];
    }
  }
  return \@changes;
  # Each entry in this arrayref is an arrayref containing:
  # field changed, new value, old value, result
}

sub addrecord {
# ADD:     $result  = addrecord(tablename, $record_as_hashref);
  my ($table, $r, $f) = @_;
  die "Too many arguments: addrecord(".(join', ',@_).")" if $f;
  my %r = %{$r};
  my $db = dbconn();
  my @clauses = map { "$_=?" } sort keys %r;
  my @values  = map { $r{$_} } sort keys %r;
  my $q = $db->prepare("INSERT INTO $table SET ". (join ", ", @clauses));
  my $result = $q->execute(@values);
  $db::added_record_id=$q->{mysql_insertid}; # Calling code can read this magic variable if desired.
  return $result;
}

sub countfield {
# COUNT:   $number  = countfind(tablename, fieldname);
  my ($table, $field, $startdt, $enddt, %crit) = @_;
  my $q;
  die "Incorrect arguments: date arguments, if defined, must be DateTime objects." if (defined $startdt and not ref $startdt) or (defined $enddt and not ref $enddt);
  die "Incorrect arguments: you must define both dates or neither" if (ref $startdt and not ref $enddt) or (ref $enddt and not ref $startdt);
  for my $criterion (keys %crit) {
    die "Incorrect arguments:  criterion $criterion specified without values." if not $crit{$criterion};
  }
  my $whereclause;
  my @value;
  if (ref $enddt) {
    my $start = DateTime::Format::MySQL->format_datetime($startdt);
    my $end   = DateTime::Format::MySQL->format_datetime($enddt);
    $whereclause = " WHERE fromtime > '$start' AND fromtime < '$end'";
  }
  for my $f (keys %crit) {
    my $v = $crit{$f};
    my $whereword = $whereclause ? 'AND' : 'WHERE';
    if (ref $v eq 'ARRAY') {
      $whereclause .= " $whereword $f IN (" . (join ',', map { "?" } @$v) . ") ";
      push @value, $_ for @$v;
    } else {
      warn "Skipping criterion of unknown type: $field => $v";
    }
  }
  warn "countfield query: SELECT id, $field FROM $table $whereclause";
  warn "countfield values: @value" if scalar @value;
  my $db = dbconn();
  $q = $db->prepare("SELECT id, $field FROM $table $whereclause");
  $q->execute(@value);
  my %c;
  while (my $r = $q->fetchrow_hashref()) {
    ++$c{$$r{$field}};
  }
  return \%c;
}

## sub findrecord {
## # FIND:    @records = findrecord(tablename, fieldname, exact_value);
##   my ($table, $field, $value, $q) = @_;
##   die "Too many arguments: findrecord(".(join', ',@_).")" if $q;
##   my $db = dbconn();
##   $q = $db->prepare("SELECT * FROM $table WHERE $field=?");  $q->execute($value);
##   my @answer; my $r;
##   while ($r = $q->fetchrow_hashref()) {
##     if (wantarray) {
##       push @answer, $r;
##     } else {
##       return $r;
##     }
##   }
##   return @answer;
## }

sub findnotin {
  my ($table, @more) = @_;
  my (%fv, @field);
  while (@more) {
    my ($field, $values);
    ($field, $values, @more) = @more;
    die "findnotin called with unbalanced arguments (no values aref for $field field)" if not ref $values;
    push @field, $field;
    $fv{$field} = $values;
  }
  my $db = dbconn();
  my $q = $db->prepare("SELECT * FROM $table WHERE "
                       . (join " AND ", map { my $f = $_;
                                              qq[$f NOT IN (] . join (", ", map { "?" } @{$fv{$f}}) . qq[)]
                                            } @field ));
  $q->execute(map { @{$fv{$_}} } @field);
  my @answer; my $r;
  while ($r = $q->fetchrow_hashref()) {
    if (wantarray) {
      push @answer, $r;
    } else {
      return $r;
    }
  }
  return @answer;
}

sub findrecord {
# FIND:    @records = findrecord(tablename, fieldname, exact_value);
  my ($table, $field, $value, @more) = @_;
  my (%fv, @field);
  croak "findrecord called with unbalanced arguments (no value for $field field)" if not defined $value;
  push @field, $field; $fv{$field} = $value;
  while (@more) {
    ($field, $value, @more) = @more;
    die "findrecord called with unbalanced arguments (no value for $field field)" if not defined $value;
    push @field, $field;
    $fv{$field} = $value;
  }
  my $db = dbconn();
  my $q = $db->prepare("SELECT * FROM $table WHERE " . (join " AND ", map { qq[$_=?] } @field ));
  $q->execute(map { $fv{$_} } @field);
  my @answer; my $r;
  while ($r = $q->fetchrow_hashref()) {
    if (wantarray) {
      push @answer, $r;
    } else {
      return $r;
    }
  }
  return @answer;
}

sub searchrecord {
# SEARCH:  @records = @{searchrecord(tablename, fieldname, value_substring)};
  my ($table, $field, $value, $q) = @_;
  die "Too many arguments: searchrecord(".(join', ',@_).")" if $q;
  my $db = dbconn();
  $q = $db->prepare("SELECT * FROM $table WHERE $field LIKE '%$value%'");  $q->execute();
  my @answer; my $r;
  while ($r = $q->fetchrow_hashref()) {
    if (wantarray) {
      push @answer, $r;
    } else {
      return $r;
    }
  }
  return @answer;
}

sub getvariable {
  my ($namespace, $var, $q) = @_;
  die "Too many arguments: searchrecord(".(join', ',@_).")" if $q;
  my $db = dbconn();
  $q = $db->prepare("SELECT * FROM misc_variables WHERE namespace=? AND name=?");  $q->execute($namespace, $var);
  my $r = $q->fetchrow_hashref();
  return $$r{value};
}
sub setvariable {
  my ($namespace, $var, $value, $q) = @_;
  die "Too many arguments: searchrecord(".(join', ',@_).")" if $q;
  my $db = dbconn();
  $q = $db->prepare("SELECT * FROM misc_variables WHERE namespace=? AND name=?");  $q->execute($namespace, $var);
  my $r = $q->fetchrow_hashref();
  if ($r) {
    return changerecord('misc_variables', $$r{id}, 'value', $value);
  } else {
    return addrecord('misc_variables', +{
                                         namespace => $namespace,
                                         name      => $var,
                                         value     => $value
                                        });
  }
}

42;
