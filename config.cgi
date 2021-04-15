#!/usr/bin/perl -T
# -*- cperl -*-

$ENV{PATH}='';
$ENV{ENV}='';

require "./forminput.pl";
require "./include.pl";
require "./auth.pl";

our %input = %{getforminput()};
my $ab = authbox(sub { my $x = getrecord('users', shift); "<!-- Hello, $$x{nickname} -->"; });
our $persistentvars = persist(undef,    [qw(category magicdate)]);
our $hiddenpersist  = persist('hidden', [qw(category magicdate)]);

my %cfgvar =
  (
   sysadmin_name => +{  default     => 'the system administrator',
                        description => 'Name of the person responsible for administration of this installation of resched.',
                        sortkey     => 1,
                     },
   url_base => +{ default => '/resched/',
                  description => 'URL path to the directory where resched is installed.  This should end with a slash.  It may be absolute (with protocol and <abbr title="fully qualified domain name">FQDN</abbr>) or may begin with slash.',
                  sortkey => 5,
                },
   time_zone => +{ default       => 'America/New_York',
                   description   => 'Timezone for your site.  Specify a time_zone designation recognizeable by <a href="http://search.cpan.org/search?query=DateTime&mode=all">DateTime</a>.',
                   sortkey       => 9,
                 },
   openingtimes => +{
                     default     => '0-7:9:0',
                     description => qq[<a href="config.cgi?action=octimeswiz&amp;$persistentvars">See Opening &amp; Closing Times</a>], #'List of what time you normally open in the morning, for each day of the week, separated by commas.  Each day is specified in the form n:h:m where n is the number from 0 to 6 indicating day of week (or a hyphenated range thereof), h is the hour in 24-hour time, and m is the number of minutes past the hour.  Note that each resource is linked to a schedule, which overrides this.',
                     sortkey     => 12,
                    },
   closingtimes => +{
                     default     => '0:12:00,1-2:20:00,3:15:00,4-5:20:00,6:15:00',
                     description => qq[<a href="config.cgi?action=octimeswiz&amp;$persistentvars">See Opening &amp; Closing Times</a>], #'List of what time you normally close up at night, for each day of the week, separated by commas.  Each day is specified in the form n:h:m where n is the number from 0 to 6 indicating day of week (or a hyphenated range thereof), h is the hour in 24-hour time, and m is the number of minutes past the hour.',
                     sortkey     => 13,
                    },
   daysclosed => +{
                   default       => '0',
                   description   => 'Comma-separated list of numbers indicating days (of the week) you are always closed.  0 means Sunday, 1 means Monday, and so on.  This is different from booking everything closed for holidays and special occasions, because this variable indicates that you are ALWAYS closed on certain days of the week, so for example month-calendar views can omit the day entirely, saving a column.',
                   sortkey       => 15,
                  },
   ils_name => +{ default => 'the ILS',
                  description => 'The name of the Integrated Library System software your library uses.',
                  sortkey => 20,
                },
   allow_duplicate_names => +{
                              default     => 0,
                              description => 'Allow the human-readable names for things like schedules and resources to be duplicated.  The risk here is human confusion:  the software can always tell them apart by their database record ID number, but that is not always apparent to the user.',
                              sortkey     => 55,
                             },
   categories => +{
                   default => '',
                   description => 'If you divide your resources into categories, list them here, one per line.  (Follow the name of each category by a comma, and the ID numbers of the resources in that category, also separated by commas.)  Links in the sidebar (e.g., under Today) will point to entire categories, showing the resources in that category side-by-side.  Also, the statistics will be grouped and subtotaled by category.  The default is for each resource to be its own category, which works well if you only have two or three resources.',
                   sortkey => 210, multiline => 1,
                  },
   statgraphcategories => +{ default     => '',
                             description => qq[The same as 'categories', above, except used for month-by-month stat tables and graphs.  If you leave this blank, the value of 'categories', above, will be used.],
                             sortkey     => 211, multiline => 1,
                           },
   statgraphcolors => +{ default => '',
                         description => qq[If some of your resource categories have subcategories, you can customize subcategory colors in the stat graphs here, by listing each subcategory on a line, followed by a colon and a color in hex format (e.g., #ff0000 for bright red).],
                         sortkey     => 220, multiline => 1,
                       },
   sidebar_post_today => +{ default     => '',
                            description => 'Wellformed XHTML snippet to insert in the sidebar between the Today section and the Rooms (1 week) section.  Must be allowable inside a block-level element.',
                            multiline   => 1, sortkey => 230,
                            allow_xhtml => 1,
                          },
   max_sidebar_programs => +{
                             default     => 12,
                             description => 'Maximum number of upcoming programs to list in the program signup sidebar.',
                             sortkey     => 250,
                            },
   sidebar_programs_showdate => +{
                                  default     => 0,
                                  description => 'If true, program listings in the sidebar show (abbreviated) date.',
                                  sortkey     => 255,
                                 },
   sidebar_programs_showtime => +{
                                   default     => 0,
                                   description => 'If true, program listings in the sidebar show time of day.',
                                   sortkey     => 256,
                                  },
   sidebar_show_admin_link => +{
				default     => 0,
				description => 'If true, the sidebar will link to admin.cgi (which in turn links to config.cgi) if the user has the admin privileges (A flag set or lax security enabled).',
				sortkey     => 299,
			       },
   nonusers => +{
                 default => 'closed,maintenance,out of order',
                 description => 'Comma-separated list of special names that resources can be booked for, which should not count toward usage statistics.',
                 sortkey => 310,
                },
   show_booking_timestamp => +{
                               default     => 1,
                               description => 'Should the booking timestamp be shown? (1=yes, 0=no)',
                               sortkey     => 501,
                              },
   allow_extend_past_midnight => +{
                                   default     => 0,
                                   description => 'Allow bookings to be extended beyond midnight into a new day? (1=yes, 0=no)',
                                   sortkey     => 502,
                                  },
   confirm_extend_past_midnight => +{
                                     default     => 0,
                                     description => 'Prompt for confirmation when extending a booking beyond midnight? (1=yes, 0=no)',
                                     sortkey     => 503,
                                    },
   redirect_seconds => +{
                         description  => 'After signing someone up, resched shows the adjusted schedule or signup sheet; however, since hitting refresh would result in performing the action again, resched redirects after a few seconds to a fresh copy of the schedule or signup sheet.  This controls how many seconds it waits before doing so.',
                         default      => 15,
                         sortkey      => 551,
                        },
   automatic_late_start_time => +{
                                  description => 'When making a booking using the short ("quick") form, if the booking is made during the timeslot, automatically fill in the Starting Late information with the current time.  0 = No, 1 = Yes.',
                                  default     => 0,
                                  sortkey     => 580,
                                 },
   time_list_quarter_hours_first => +{
                                      description => 'In the minutes fields for times, list :00, :15, :30, and :45 before all the other options.  0=No, 1=Yes.',
                                      default     => 0,
                                      sortkey     => 605,
                                     },

   privacy_cutoff_old_schedules => +{
                                     description => "Number of months' worth of old schedules to allow people to look at.  0 means no limit.  Note that overviews are only viewable if the first of the month is viewable, so setting this to 1 means last month's overview will be unavailable.",
                                     default     => 12,
                                     sortkey     => 650,
                                    },
   privacy_cutoff_old_searches => +{
                                    description => "Number of months' worth of old bookings to keep searchable.  0 means no limit.",
                                    default     => 24,
                                    sortkey     => 651,
                                   },

   program_signup_show_in_sidebar => +{
                                       default     => 0,
                                       description => 'If true, the resource scheduling sidebar contains a link to the program signup facility.',
                                       sortkey     => 700,
                                      },
   program_signup_waitlist => +{
                                default     => 1,
                                description => 'If the number of people signed up for a program reaches the limit, do we allow more names to be taken for a waiting list?  0 = No, 1 = Yes.  Either way, it can be changed on a per-program basis with the W flag, but new programs are created according to this preference.',
                                sortkey     => 712,
                               },
   program_signup_waitlist_checkbox => +{
                                         default     => 0,
                                         description => qq[When signing someone up for a program that is not yet full but is allowed to have a waiting list, provide a checkbox to place the person explicitly on the waiting list.  0 = No, 1 = Yes.],
                                         sortkey     => 714,
                                        },
   program_signup_default_limit => +{
                                     default     => 0,
                                     description => 'By default, how many people can sign up for any given one of your programs.  This can still be changed on a per-program basis, but new programs get this value if you do not change it.  0 means no limit.  The fire-safety capacity of your primary meeting room makes a good value here.',
                                     sortkey     => 720,
                                    },
   program_signup_default_sort => +{
                                    default     => 'num',
                                    description => 'Order in which program signup lists are shown by default.  This can be overridden for individual programs, which in turn can be overridden by clicking a different column header to sort by that column.  "num" means sort numerically; "lastname" means sort by last name.',
                                    sortkey     => 725,
                                   },

   normal_name_order => +{
                          default     => 0,
                          description => 'When normalizing names, how should they usually be shown?  0 means Western order ("First M. Lastname Jr."), and 1 means collating order ("Lastname, First M. Jr.").',
                          sortkey     => 1105,
                         },
   alternate_name_order => +{
                             default     => 1,
                             description => 'In some circumstances an alternate name-normalization order is available to the user (by clicking a link).  This variable determines what the alternate order is.  The numbers have the same meaning as for normal_name_order, above.',
                             sortkey     => 1106,
                            },
   signup_sheets_use_alt_norm => +{
                                   default     => 1,
                                   description => 'If true, program signup sheets default to using the alternate name-normalization order instead of the normal one.',
                                   sortkey     => 1107,
                                  },
   staff_schedule_show_in_sidebar => +{
                                       default     => 0,
                                       description => 'If true, the resource scheduling sidebar contains a link to the staff schedule facility.',
                                       sortkey     => 2000,
                                      },
   staff_schedule_show_redundant_change_link => +{
                                                  default     => 0,
                                                  description => 'If true, the staff schedule section in the sidebar will have an "edit schedule" link even if this is technically redundant.',
                                                  sortkey     => 2003,
                                                 },
   staff_schedule_lax_security => +{
                                    default     => 0,
                                    description => 'If true, anyone who can log in can edit staff and staff schedule records.',
                                    sortkey     => 2010,
                                  },
   staff_schedule_first_day_of_week => +{
                                         default     => 0,
                                         description => 'First day of the week, for staff schedule purposes.  0 means Sunday, 1 means Monday, etc.',
                                         sortkey     => 2030,
                                        },
   staff_schedule_jump_to_edit => +{
				    default     => 0,
				    description => "If true, when you click the link to a staff member's schedule, if you have permission to edit it, you skip straight to the edit screen.",
				    sortkey     => 2041,
				   },
   max_color_choices => +{
                          default     => 16,
                          description => 'Maximum number of color choices to display (when assigning colors to people for staff scheduling).',
                          sortkey     => 2050,
                         },
   staff_schedule_expand_shadow_to_bg => +{
                                           default     => 0,
                                           description => 'If true, staff names on the staff schedule will have an opaque background rather than just a text shadow.',
                                           sortkey     => 2055,
                                          },
   staff_schedule_suppress_locations => +{
                                          default     => 0,
                                          description => 'If true, the location field for staff schedule records will not be used at all.',
                                          sortkey     => 2070,
                                         },
   staff_schedule_suppress_hours_when_closed => +{
                                                  default     => 0,
                                                  description => 'If true, staff hours will not be shown on closed dates.',
                                                  sortkey     => 2075,
                                                 },
   staff_schedule_show_redundant_flags => +{
                                            default     => 0,
                                            description => 'If true, list flags that may be redundant, e.g., an auxiliary-schedule flag on the auxiliary schedule.',
                                            sortkey     => 2080,
                                           },
   mail_enable => +{ default     => 0,
                     description => "If true, attempt to use the 'circ desk mail' feature.",
                     sortkey     => 4001,
                   },
   mail_sidebar_link_text => +{ default     => "Circ Desk Mail",
                                description => "If mail_enable is true, a link will be generated in the sidebar, pointing to the mail feature, with this name.  However, if this name is blank, the link will not appear after all.",
                                sortkey     => 4002,
                                allowblank  => 1,
                              },
   mail_folders => +{ default     => 'old stuff,spam',
                      description => "Comma-separated list of mail folders for the 'circ desk mail' feature.",
                      sortkey     => 4005,
                    },
   mail_pop3server => +{ default     => "",
                         description => "Fully qualified domain name (or IP address) of the POP3 mail server that hosts the account Circ Desk Mail should use.",
                         sortkey     => 4010,
                       },
   mail_pop3username => +{ default     => "",
                           description => "POP3 username of the mail account Circ Desk Mail should use.",
                           sortkey     => 4012,
                         },
   mail_pop3password => +{ default     => "",
                           description => "Password that should be used to get the mail from the POP3 server.",
                           sortkey     => 4014,
                         },
   mail_pop3iterdelay => +{ default     => "0.2",
                            description => "If nonzero, wait this many seconds after retrieving each message, for rate-limiting purposes.",
                            sortkey     => 4081,
                          },
   mail_msglist_showatonce => +{
                               default     => 20,
                               description => "In lists of messages, show up to this many at once",
                               sortkey     => 4100,
                               },
   smtp_server => +{ default     => "",
                     description => "Domain name of your outgoing mail server.  Only needed if you use the automated sending feature for meeting room policy.  If this is not set, no mail will be sent.",
                     sortkey     => 4201,
                   },
   smtp_retry_delay => +{ default     => 30,
                          description => "If an SMTP send fails, wait this many seconds before retrying.  On subsequent retries, wait this many seconds multiplied by the number of retries.",
                          sortkey     => 4205,
                        },
   smtp_mrp_from_address => +{ default     => "",
                               description => "Email address to be used in the From: field and SMTP envelope when sending out meeting room policy by email.  If this is not set, meeting room policy messages will not be sent.",
                               sortkey     => 4210,
                             },
   smtp_mrp_subject => +{ default     => "Meeting Room Policy",
                          description => "Contents of the Subject: header when sending out the meeting room policy by email.",
                          sortkey     => 4211,
                        },
   minimum_password_length => +{ default     => 12,
                                 description => 'Minimum length requirement for new user account passwords.',
                                 sortkey     => 7000,
                               },
   retain_cleartext_passwords => +{  default     => 0,
                                     description => 'If true, leave existing clear-text passwords in the database, even if the user can authenticate via hashed password.  This is not recommended.  This option only exists in case user records are shared with legacy software that requires it.',
                                     sortkey     => 7005,
                                  },
   salt_length => +{ default     => 250,
                     description => 'Number of bytes of salt to use when creating new passwords.  This value MUST NOT exceed the size of the salt field in the users table.  Prior to version 0.9.3, the salt field was created as a tinytext field, and the size of the field is not usually changed on upgrade; so if you originally installed version 0.9.2 or earlier you are probably limited to at most 255 bytes of salt, unless you change the users table by hand.  New installations from version 0.9.3 forward can safely use a larger value, but obscenely large values (e.g., in the millions) can cause login failures.  The value 65535 is known to be safe, provided the salt field can hold that many characters.',
                     sortkey     => 7010,
                   },
   svg_graphs_install_dir => +{ default     => "",
                                description => 'Directory path where the svg_graph software is installed.  Only needed if you want SVG graphs of the month-by-month and year-by-year statistics.  See INSTALL.txt for details.',
                                sortkey     => 7050,
                              },
   bookmark_icon => +{
                      default     => 'resched.ico',
                      description => 'Bookmark icon (favicon) to suggest that the browser use to represent (your installation of) resched.',
                      sortkey     => 9000,
                     },
   wording_personal_schedule => +{
				  default     => 'Personal Schedule',
				  description => "Wording to use for the link to a staff member's personal schedule.",
				  sortkey     => 99800,
                                 },
  );

if ($auth::user) {
  my $user = getrecord('users', $auth::user);
  ref $user or die "Unable to retrieve user record for $auth::user";
  $input{usestyle} ||= getpref("usestyle", $auth::user);
  $input{useajax}  ||= getpref("useajax", $auth::user);
  if ($$user{flags} =~ /A/) {
    my $notice = '';
    my $title = "resched configuration";
    if ($input{action} eq 'save') {
      ($notice, $title) = savechanges();
    }
    if ($input{action} eq "calcoctimes") {
      ($notice, $title) = calculate_octimes();
    }
    if ($input{action} eq "octimeswiz") {
      print include::standardoutput("Open / Close Times Wizard",
                                    octimeswizard(),
                                    $ab, $input{usestyle});
    } else {
      print include::standardoutput($title,
                                    $notice . configform(),
                                    $ab, $input{usestyle});
    }
  } else {
    print include::standardoutput('Administrative Access Needed',
                                  "<p>In order to access this page you need to log into an account that has the Administrator flag set.</p>",
                                  $ab, $input{usestyle});
  }
} else {
  print include::standardoutput('Authentication Needed',
                                "<p>In order to access this page you need to log in.</p>",
                                $ab, $input{usestyle});
}

sub savechanges {
  my $changecount;
  for my $var (keys %cfgvar) {
    my $oldvalue = getvariable('resched', $var);
    my $newvalue = encode_entities($input{'cfgvar_'.$var});
    if ($cfgvar{$var}{allow_xhtml}) {
      $newvalue = $input{'cfgvar_'.$var};
    }
    if ($newvalue ne $oldvalue) {
      setvariable('resched', $var, $newvalue) if $newvalue ne $oldvalue;
      ++$changecount;
    }
  }
  my $title = $changecount ? include::sgorpl($changecount, 'change') . ' saved' : 'Nothing Changed';
  my $notice = $changecount
    ? qq[<div class="info">Saved changes to ] . include::sgorpl($changecount, 'variable') . qq[</div>]
    : qq[<div class="error">No changes were made!</div>];
  return ($notice, $title);
}

sub octimeswizard {
  my @dow = qw(Sunday Monday Tuesday Wednesday Thursday Friday Saturday);
  my $allhours = [ [ 0 => "Midnight"], [ 1 => "1am"], [ 2 => "2am"],  [ 3 => "3am"],
                   [ 4 => "4am"],      [ 5 => "5am"], [ 6 => "6am"],  [ 7 => "7am"],
                   [ 8 => "8am"],      [ 9 => "9am"], [10 => "10am"], [11 => "11am"],
                   [12 => "12"],       [13 => "1pm"], [14 => "2pm"],  [15 => "3pm"],
                   [16 => "4pm"],      [17 => "5pm"], [18 => "6pm"],  [19 => "7pm"],
                   [20 => "8pm"],      [21 => "9pm"], [22 => "10pm"], [23 => "11pm"], ];
  my $ot = include::openingtimes();
  my $ct = include::closingtimes();
  return qq[<form action="config.cgi" method="POST">
     $hiddenpersist
     <div class="h">Opening &amp; Closing Times:</div>
     <input type="hidden" name="action" value="calcoctimes" />
     <table><thead>
      <tr>
      </tr>
     </thead><tbody>
        ] . (join "\n     ", map {
          my $n = $_;
          my $fromhoursel = include::orderedoptionlist("fromhour$n", $allhours, $$ot{$n}[0]);
          my $tillhoursel = include::orderedoptionlist("tillhour$n", $allhours, $$ct{$n}[0]);
          my $frommin     = sprintf("%02d", ($$ot{$n}[1] || 0));
          my $tillmin     = sprintf("%02d", ($$ct{$n}[1] || 0));
          my $isclosed    = ($$ct{$n}[0] > $$ot{$n}[0] or (($$ct{$n}[0] == $$ot{$n}[0]) and ($$ct{$n}[1] > $$ot{$n}[1])))
            ? "" : qq[ checked="checked"];
          my $issame      = $isclosed ? "" : ($n == 0) ? "" :
            (($$ot{$n}[0] == $$ot{$n - 1}[0]) and ($$ot{$n}[1] == $$ot{$n - 1}[1]) and
             ($$ct{$n}[0] == $$ct{$n - 1}[0]) and ($$ct{$n}[1] == $$ct{$n - 1}[1]))
            ? qq[ checked="checked"] : "";
          my $isopen      = ($isclosed or $issame) ? "" : qq[ checked="checked"];
          my $samediv = ($n > 0)
            ? qq[<div><input id="same$n" name="open$n" value="same" type="radio"$issame />&nbsp;<label for="same$n">Same times as ] . $dow[$n-1] . qq[</label></div>]
            : "";
          qq[<tr><th>$dow[$n]</th>
              <td><div><input id="closed$n" name="open$n" value="closed" type="radio"$isclosed />&nbsp;<label for="closed$n">Closed</label></div>
                  $samediv
                  <div><input id="open$n" name="open$n" value="open" type="radio"$isopen />&nbsp;<label for="open$n">Open</label>
                       <label for="fromhour$n">from</label>&nbsp;$fromhoursel
                          :<input type="text" size="3" id="frommin$n" name="frommin$n" value="$frommin" />
                       <label for="tillhour$n">until</label>&nbsp;$tillhoursel
                          :<input type="text" size="3" id="tillmin$n" name="tillmin$n" value="$tillmin" />
                       </div>
                  </td></tr>]
     } 0 .. 6) . qq[
     </tbody></table>
     <input type="submit" value="Save Changes" />
  </form>]
}

sub calculate_octimes {
  my ($gnum, @group); $gnum = -1;
  for my $n (0 .. 6) {
    if ($input{"open" . $n} eq "closed") {
      # Nothing to do.
    } elsif (($n > 0) and ($input{"open" . $n} eq "same")) {
      $group[$gnum]{lastn} = $n;
    } else {
      $gnum++;
      $group[$gnum] = +{ firstn => $n,
                         lastn  => $n,
                         ohour  => include::getnum("fromhour" . $n),
                         omin   => include::getnum("frommin" . $n),
                         chour  => include::getnum("tillhour" . $n),
                         cmin   => include::getnum("tillmin" . $n),
                       };
    }
  }
  my $openspec = join ",", map {
    my $g = $_;
    "" . ($$g{lastn} > $$g{firstn} ? qq[$$g{firstn}-$$g{lastn}] : $$g{firstn})
      . ":" . $$g{ohour} . ":" . $$g{omin};
  } @group;
  my $closespec = join ",", map {
    my $g = $_;
    "" . ($$g{lastn} > $$g{firstn} ? qq[$$g{firstn}-$$g{lastn}] : $$g{firstn})
      . ":" . $$g{chour} . ":" . $$g{cmin};
  } @group;
  setvariable("resched", "openingtimes", $openspec);
  setvariable("resched", "closingtimes", $closespec);
  return include::infobox("Opening and Closing Times Set",
                          qq[<table><tbody>
        <tr><th>openingtimes</th><td>$openspec</td></tr>
        <tr><th>closingtimes</th><td>$closespec</td></tr>
   </tbody></table>]);
}

sub configform {
  for my $var (keys %cfgvar) {
    my $value = getvariable('resched', $var);
    if (($value eq '0') or ($cfgvar{$var}{allowblank})) {
      ${$cfgvar{$var}}{value} = $value;
    } else {
      ${$cfgvar{$var}}{value} = $value || ${$cfgvar{$var}}{default};
    }
  }
  return qq[<form id="configform" action="config.cgi" method="POST">
    $hiddenpersist
    <input type="hidden" name="action" value="save" />
    <table class="configtable settingsform"><tbody>] . (join "\n", map {
      my $var = $_;
      my $value = ${$cfgvar{$var}}{value};
      my $inputelt = ${$cfgvar{$var}}{multiline}
        ? qq[<textarea cols="40" rows="5" name="cfgvar_$var">$value</textarea>]
        : qq[<input size="40" name="cfgvar_$var" value="$value" />];
      qq[<tr class="cfgvar"><td>$var</td>
         <td>$inputelt</td>
         <td>${$cfgvar{$var}}{description}
             (Default: <q>${$cfgvar{$var}}{default}</q>)</td></tr>]
    } sort { ${$cfgvar{$a}}{sortkey} <=> ${$cfgvar{$b}}{sortkey} } keys %cfgvar) . qq[</tbody></table>
    <input type="submit" value="Save Changes" />
  </form>]
}

sub usersidebar {
  return '<div class="sidebar"><div><a href="index.cgi?$persistentvars">Return to the index.</a></div></div>';
}
