#!/usr/bin/perl -T
# -*- cperl -*-

our $defaultbackroundcolor = 'black';

our @color = map { [ $$_{fg}, $$_{name}, $$_{shadow}, $$_{flags} ]
                 } grep { not $$_{flags} =~ /X/ } getrecord('resched_staffsch_color');
our %backgroundcolor = map { $$_[0] => ($$_[2] || $defaultbackgroundcolor) } @color;


