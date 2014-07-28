#!/usr/bin/perl
# -*- cperl -*-

use strict;
package sitecode;

# This file holds *code* that is site-specific.  Mere *variables* go
# in the database, but I am not comfortable storing *code* in there,
# for a variety of reasons, not least that it multiplies security
# considerations that have to be taken into account.

sub normalisebookedfor {
    my ($name) = @_;
    # Here you can do any site-specific normalization.  Note that
    # basic normalization, like changing "last, firstname" to
    # "firstname last", is done in include.pl, so this is just for
    # site-specific stuff.

    # In Galion we use this to remove certain semantic tags that
    # aren't really a part of the patron's name but are stored in that
    # field due to ILS limitations, so that names copy-and-pasted from
    # the ILS don't have that extra unrelated junk attached to them on
    # the internet schedule.

    return $name;
}

42;
