#!/usr/bin/perl
# -*- cperl -*-

# This only needs to be run once, but it *should* be idempotent.

# Note that *before* you do this, you have to log into MySQL with an
# admin account (typically root), create the resched database, and
# grant privileges on it to the user.  The database name, username,
# and password also must match what's in dbconfig.pl

require "./db.pl";
my $db = dbconn();

$db->prepare("use $dbconfig::database")->execute();
$db->prepare(
    "CREATE TABLE IF NOT EXISTS
     resched_alias (
          id integer NOT NULL AUTO_INCREMENT PRIMARY KEY,
          alias mediumtext, canon mediumtext)"
    )->execute();

$db->prepare(
    "CREATE TABLE IF NOT EXISTS
     resched_bookings (
          id integer NOT NULL AUTO_INCREMENT PRIMARY KEY,
          resource integer,
          bookedfor longtext,
          bookedby integer,
          fromtime datetime,
          until datetime,
          doneearly datetime,
          followedby integer,
          isfollowup integer,
          staffinitials tinytext,
          latestart datetime,
          notes longtext,
          tsmod timestamp
     )"
    )->execute();


$db->prepare(
    "CREATE TABLE IF NOT EXISTS
     resched_resources (
          id integer NOT NULL AUTO_INCREMENT PRIMARY KEY,
          name mediumtext,
          schedule integer,
          switchwith tinytext,
          showwith tinytext,
          combine tinytext,
          requireinitials integer,
          requirenotes integer,
          autoex integer,
          bgcolor integer,
          flags tinytext
     )"
    )->execute();


$db->prepare(
    "CREATE TABLE IF NOT EXISTS
     resched_schedules (
          id integer NOT NULL AUTO_INCREMENT PRIMARY KEY,
          name tinytext,
          firsttime datetime,
          intervalmins integer,
          durationmins integer,
          durationlock integer,
          intervallock integer,
          booknow integer,
          alwaysbooknow integer
     )"
    )->execute();


$db->prepare(
    "CREATE TABLE IF NOT EXISTS
     resched_booking_color (
          id integer NOT NULL AUTO_INCREMENT PRIMARY KEY,
          colorname     tinytext,
          darkbg        tinytext,
          lightbg       tinytext,
          lowcontrastbg tinytext,
          sitenote      tinytext,
          flags         tinytext
     )"
    )->execute();
my @bkcolor = getrecord('resched_booking_color');
if (not scalar @schflag) {
    addrecord('resched_booking_color', +{ colorname     => 'Blue A', #res16, res17, main internet
                                          darkbg        => '#494975',
                                          lightbg       => '#BBDDFF',
                                          lowcontrastbg => '#7F99CC',
                                        });
    addrecord('resched_booking_color', +{ colorname     => 'Yellow A', # res6, CR w.p.
                                          darkbg        => '#7F7F00',
                                          lightbg       => '#FFFFA0',
                                          lowcontrastbg => '#DDDD7F',
                                        });
    addrecord('resched_booking_color', +{ colorname     => 'Green A', # res4, res5, res19, res20
                                          darkbg        => '#497549',
                                          lightbg       => '#CCFFDD',
                                          lowcontrastbg => '#55AA6F',
                                        });
    addrecord('resched_booking_color', +{ colorname     => 'Red A', # res8, community room
                                          darkbg        => '#7F0000',
                                          lightbg       => '#FF9999',
                                          lowcontrastbg => '#EE9999',
                                        });
    addrecord('resched_booking_color', +{ colorname     => 'Purple A', #res15, res18, side internet
                                          darkbg        => '#332060',
                                          lightbg       => '#E3CCFF',
                                          lowcontrastbg => '#AA99CC',
                                        });
    addrecord('resched_booking_color', +{ colorname     => 'Brown A', # res10, staff room
                                          darkbg        => '#7F4900',
                                          lightbg       => '#FFCC99',
                                          lowcontrastbg => '#EE9966',
                                        });
    addrecord('resched_booking_color', +{ colorname     => 'Blue B',
                                          darkbg        => '#1B3651',
                                          lightbg       => '#B7C3DB',
                                          lowcontrastbg => '#A8B2C7',
                                        });
    addrecord('resched_booking_color', +{ colorname     => 'Yellow B', # res3, CR internet
                                          darkbg        => '#3E3E00',
                                          lightbg       => '#FFFFCC',
                                          lowcontrastbg => '#DDDDAF',
                                        });
    addrecord('resched_booking_color', +{ colorname     => 'Green B', # res7, typewriter
                                          darkbg        => '#355535',
                                          lightbg       => '#A0B4A7',
                                          lowcontrastbg => '#89AA93',
                                        });
    addrecord('resched_booking_color', +{ colorname     => 'Red B', # res9, board room
                                          darkbg        => '#603333',
                                          lightbg       => '#E3A4A4',
                                          lowcontrastbg => '#996666',
                                        });
    addrecord('resched_booking_color', +{ colorname     => 'Purple B', # res13, bball court
                                          darkbg        => '#662251',
                                          lightbg       => '#FFB9E4',
                                          lowcontrastbg => '#D392C1',
                                        });
    addrecord('resched_booking_color', +{ colorname     => 'Brown B', #res14, lecture hall
                                          darkbg        => '#664422',
                                          lightbg       => '#CCAA99',
                                          lowcontrastbg => '#CCAA99',
                                        });
    addrecord('resched_booking_color', +{ colorname     => 'Blue C', # res12, jukebox
                                          darkbg        => '#224466',
                                          lightbg       => '#99AACC',
                                          lowcontrastbg => '#99AACC',
                                        });
    addrecord('resched_booking_color', +{ colorname     => 'Yellow C',
                                          darkbg        => '#5C5C1D',
                                          lightbg       => '#FFFFBB',
                                          lowcontrastbg => '#DDDD9F',
                                        });
    addrecord('resched_booking_color', +{ colorname     => 'Green C', # res11, sandbox
                                          darkbg        => '#446622',
                                          lightbg       => '#AACC99',
                                          lowcontrastbg => '#AACC99',
                                        });
    addrecord('resched_booking_color', +{ colorname     => 'Red C',
                                          darkbg        => '#500000',
                                          lightbg       => '#FF8484',
                                          lowcontrastbg => '#996666',
                                        });
    addrecord('resched_booking_color', +{ colorname     => 'Purple C',
                                          darkbg        => '#3B0046',
                                          lightbg       => '#E293F0',
                                          lowcontrastbg => '#916699',
                                        });
    addrecord('resched_booking_color', +{ colorname     => 'Brown C',
                                          darkbg        => '#462800',
                                          lightbg       => '#F5DBB8',
                                          lowcontrastbg => '#998366',
                                        });
}


$db->prepare(
    "CREATE TABLE IF NOT EXISTS
     authcookies (
          id integer NOT NULL AUTO_INCREMENT PRIMARY KEY,
          cookiestring mediumtext,
          user integer,
          restrictip tinytext,
          expires datetime
     )"
    )->execute();

$db->prepare(
    "CREATE TABLE IF NOT EXISTS
     users (
          id integer NOT NULL AUTO_INCREMENT PRIMARY KEY,
          username   tinytext,
          hashedpass tinytext,
          fullname   mediumtext,
          nickname   mediumtext,
          prefs      mediumtext,
          salt       mediumtext,
          flags      tinytext
     )"
    )->execute();

$db->prepare(
    "CREATE TABLE IF NOT EXISTS
     misc_variables (
          id integer NOT NULL AUTO_INCREMENT PRIMARY KEY,
          namespace  tinytext,
          name       mediumtext,
          value      longtext
     )"
    )->execute();

$db->prepare(
    "CREATE TABLE IF NOT EXISTS
    auth_by_ip (
          id integer NOT NULL AUTO_INCREMENT PRIMARY KEY,
          ip tinytext,
          user integer
    )"
    )->execute();

$db->prepare(
    "CREATE TABLE IF NOT EXISTS
    resched_program_category (
          id INTEGER NOT NULL AUTO_INCREMENT PRIMARY KEY,
          category mediumtext,
          flags    tinytext
    )"
    )->execute();
my @category = getrecord('resched_program_category');
if (not scalar @category) {
    addrecord('resched_program_category', +{ category => 'Test/Debug',           flags => '#' });
    addrecord('resched_program_category', +{ category => 'Our Programs',         flags => 'LD' });
    addrecord('resched_program_category', +{ category => 'Third-Party Programs', flags => 'T' });
}

$db->prepare(
    "CREATE TABLE IF NOT EXISTS
     resched_program (
          id INTEGER NOT NULL AUTO_INCREMENT PRIMARY KEY,
          category    integer,
          title       mediumtext,
          agegroup    tinytext,
          starttime   datetime,
          endtime     datetime,
          signuplimit integer,
          flags       tinytext,
          notes       longtext
     )"
     )->execute();

$db->prepare(
    "CREATE TABLE IF NOT EXISTS
     resched_program_signup (
          id INTEGER NOT NULL AUTO_INCREMENT PRIMARY KEY,
          program_id integer,
          attender   mediumtext,
          phone      tinytext,
          flags      tinytext,
          comments   longtext
     )"
     )->execute();

$db->prepare(
    "CREATE TABLE IF NOT EXISTS
     resched_staff (
          id        INTEGER NOT NULL AUTO_INCREMENT PRIMARY KEY,
          userid    integer,
          shortname tinytext,
          fullname  tinytext,
          jobtitle  tinytext,
          jobdesc   mediumtext,
          phone     tinytext,
          email     tinytext,
          contact   text,
          color     tinytext,
          flags     tinytext
     )"
     )->execute();

$db->prepare(
    "CREATE TABLE IF NOT EXISTS
     resched_staffsch_location (
          id          INTEGER NOT NULL AUTO_INCREMENT PRIMARY KEY,
          briefname   tinytext,
          description mediumtext,
          flags       tinytext
     )"
     )->execute();

$db->prepare(
    "CREATE TABLE IF NOT EXISTS
     resched_staffsch_regular (
          id        INTEGER NOT NULL AUTO_INCREMENT PRIMARY KEY,
          staffid   integer,
          effective datetime,
          obsolete  datetime,
          dow       integer,
          starthour integer,
          startmin  integer,
          endhour   integer,
          endmin    integer,
          location  integer,
          flags     tinytext
     )"
     )->execute();

$db->prepare(
    "CREATE TABLE IF NOT EXISTS
     resched_staffsch_occasion (
          id        INTEGER NOT NULL AUTO_INCREMENT PRIMARY KEY,
          staffid   integer,
          starttime datetime,
          endtime   datetime,
          location  integer,
          flags     tinytext,
          comment   text
     )"
     )->execute();

$db->prepare(
    "CREATE TABLE IF NOT EXISTS
     resched_staff_flag (
          id        INTEGER NOT NULL AUTO_INCREMENT PRIMARY KEY,
          flagchar  tinytext,
          shortdesc tinytext,
          longdesc  mediumtext,
          obsolete  datetime,
          isdefault integer
     )"
     )->execute();
my @sflag = getrecord('resched_staff_flag');
if (not scalar @sflag) {
    addrecord('resched_staff_flag', +{ flagchar => 'X', shortdesc => 'No Longer Works Here', longdesc => 'Regularly-scheduled times for this person are no longer relevant, and when making out schedules they will not be automatically suggested.', });
}

$db->prepare(
    "CREATE TABLE IF NOT EXISTS
     resched_staffsch_flag (
          id        INTEGER NOT NULL AUTO_INCREMENT PRIMARY KEY,
          flagchar  tinytext,
          shortdesc tinytext,
          longdesc  mediumtext,
          obsolete  datetime,
          flags     tinytext
     )"
     )->execute();
my @schflag = getrecord('resched_staffsch_flag');
if (not scalar @schflag) {
    addrecord('resched_staffsch_flag', +{ flagchar => 'A', shortdesc => 'All Day',      longdesc => 'Starting and ending times are moot on this date.', });
    addrecord('resched_staffsch_flag', +{ flagchar => 'P', shortdesc => 'Plus-Regular', longdesc => 'This is in addition to (not replacing) regular hours.', flags => 'PO', });
    addrecord('resched_staffsch_flag', +{ flagchar => 'X', shortdesc => 'X-Cancel',     longdesc => 'These special hours are canceled', flags => 'OX', });
}


$db->prepare(
    "CREATE TABLE IF NOT EXISTS
     resched_staffsch_color (
          id        INTEGER NOT NULL AUTO_INCREMENT PRIMARY KEY,
          name      tinytext,
          fg        tinytext,
          shadow    tinytext,
          flags     tinytext
     )"
     )->execute();
my @schcolor = getrecord('resched_staffsch_color');
if (not scalar @schcolor) {
    my @color = (
              ['#7F0000' => 'red'           => '#AAAAAA' ],
              ['#007F00' => 'green'         => '#AAAAAA' ],
              ['#00007F' => 'blue'          => '#AAAAAA' ],
              ['#600060' => 'violet'        => '#9C6DA5' ],
              ['#6C3461' => 'grape'         => '#FFE0FF' ],
              ['#502000' => 'brown'         => '#B9A281' ],
              ['#006633' => 'turquoise'     => '#7F7F7F' ],
              ['#505000' => 'ochre'         => '#7F7F7F' ],
              ['#666666' => 'gray'          => '#7F7F7F' ],
              ['#AA0000' => 'medium red'    => '#7F7F7F' ],
              ['#980002' => 'blood red'     => '#FF6666' ],
              ['#FD3C06' => 'red orange'    => '#FFD600' ],
              ['#00AA00' => 'medium green'  => '#006600' ],
              ['#02AB2E' => 'kelly green'   => '#FFFFCC' ],
              ['#0000AA' => 'medium blue'   => '#7F7F7F' ],
              ['#0485D1' => 'cerulean'      => '#AAAAAA' ],
              ['#CC5500' => 'medium orange' => '#AAAAAA' ],
              ['#C04E01' => 'burnt orange'  => '#4A0100' ],
              ['#7F007F' => 'magenta'       => '#7F7F7F' ],
              ['#FFB07C' => 'peach'          => '#502000'],
              ['#995500' => 'tan'            => '#B9A281'],
              ['#AF884A' => 'yellow tan'     => '#574425'],
              ['#9C6DA5' => 'lilac'          => '#333333'],
              ['#13EAC9' => 'aqua'           => '#666666'],
              ['#3C7575' => 'aquamaroon'     => '#AAAAAA'],
              ['#677A04' => 'olive'          => 'black'],
              ['#AE7181' => 'mauve'          => '#555555'],
              ['#7F4E1E' => 'milk chocolate' => '#7F7F7F'],
              ['#88B378' => 'sage green'     => '#003300'],
              ['#3D736E' => 'medium slate'   => '#203B39'],
              ['#7F7F00' => 'medium ochre'   => '#999999'],
              ['#999999' => 'medium gray'    => '#444444'],
              ['#550000' => 'dark red'       => '#7F7F7F'],
              ['#005000' => 'dark green'     => '#00AA00'],
              ['#0B5509' => 'forest green'   => '#7F7F7F'],
              ['#000055' => 'dark blue'      => '#7F7F7F'],
              ['#020035' => 'midnight'       => '#AAAAAA', 'disabled'],
              ['#3D1C02' => 'dark chocolate' => '#7F7F7F'],
              ['#FFD600' => 'gold'           => 'black'],
              ['#FF796C' => 'salmon'         => 'black'],
              ['#75BBFD' => 'sky blue'       => 'black'],
              ['#DD00DD' => 'bright magenta' => 'black'],
              ['#F97306' => 'bright orange'  => 'black'],
              ['#00FFFF' => 'bright cyan'    => 'black'],
              ['#FF028D' => 'hot pink'       => 'black'],
              ['#FFFF00' => 'yellow'         => 'black'],
              ['#FFFFFF' => 'white'          => 'black'],
              ['#FBDD7E' => 'wheat'          => '#203B39'],
              ['#330033' => 'dark purple'    => '#7F7F7F', 'disabled'],
              ['#34013F' => 'dark violet'    => '#AAAAAA'],
              ['#380282' => 'indigo'         => '#7F7F7F'],
              ['#004020' => 'dark turquoise' => '#7F7F7F', 'disabled'],
              ['#294D4A' => 'dark slate'     => '#7F7F7F', 'disabled'],
              ['#333300' => 'dark ochre'     => '#7F7F7F', 'disabled'],
              ['#404040' => 'dark grey'      => '#AAAAAA'],
              ['black'   => 'black'          => '#AAAAAA'],
              ['#FF3333' => 'bright red'     => 'black'],
              ['#00FF00' => 'bright green'   => 'black'],
              ['#3333FF' => 'bright blue'    => 'black'],
              ['#FF81C0' => 'kawaii pink'    => 'black'],
              ['#89FE05' => 'lime green'     => 'black'],
              ['#C79FEF' => 'lavender'       => 'black'],
              ['#FFFFC2' => 'cream'          => 'black'],
              ['#FFF3DE' => 'paleface'       => '#7F7F7F'],
              ['#A2CFFE' => 'baby blue'      => 'black', 'disabled'],
              ['#ACC2D9' => 'cloudy day'     => '#000033'],
              ['#FFFFAA' => 'light yellow'   => '#7F7F00'],
              ['#8FFF9F' => 'mint'           => '#447F44'],
              ['#AAA662' => 'khaki'          => '#333300', 'disabled'],
              ['#AD8150' => 'light brown'    => '#333300'],
              ['#B9A281' => 'taupe'          => '#333300'],
              ['#5A7D9A' => 'steel blue'     => '#000033'],
              ['#E7F0FF' => 'pastel blue'    => '#7F7F7F'],
              ['#E7FFE7' => 'pastel green'   => '#7F7F7F'],
              ['#FFE4E4' => 'pastel pink'    => '#7F7F7F'],
              ['#FFE0FF' => 'pastel purple'  => '#7F7F7F'],
              ['#FFFFCC' => 'pastel yellow'  => '#7F7F7F'],
              ['#CA6641' => 'terra cotta'    => '#663320'],
              ['#BE0119' => 'scarlet'        => '#7F7F7F'],
              ['#6A79F7' => 'cornflower'     => '#35407D'],
              ['#FFCFDC' => 'pale pink'      => '#FF81C0'],
              ['#E17701' => 'pumpkin'        => '#333333'],
              ['#C875C4' => 'orchid'         => '#333333'],
              ['#01A049' => 'emerald'        => '#006600', 'disabled'],
              ['#4A0100' => 'mahogany'       => '#DE7E5D'],
              ['#DE7E5D' => 'dark peach'     => '#666666'],
              ['#048243' => 'jungle'         => '#AAAAAA'],
              ['#954567' => 'razzleberry'    => '#AAAAAA'],
    );
    for my $clr (@color) {
       my ($fg, $name, $shadow, $disabled) = @$clr;
       $shadow ||= '#7F7F7F';
       my $flags = ($disabled) ? 'X' : '';
       addrecord('resched_staffsch_color', +{ name => $name, fg => $fg, shadow => $shadow, flags => $flags });
    }
}
