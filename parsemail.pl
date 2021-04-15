#!/usr/bin/perl -wT
# -*- cperl -*-

# NOTE: Only edit this file as part of the UWM project.
# The copy in Galion ReSched is a _copy_.  Don't fork.

use Encode;
use MIME::Base64;
use MIME::QuotedPrint;
use Carp;
use utf8;

sub parse_message_parts {
  my ($body, $headers) = @_;
  carp("parse_message_parts(): no body") if not $body;
  if ($headers =~ m!^Content-Type:\s+multipart/?(\w+);\s+boundary=["'](.*?)['"]\s*$!im) {
    my ($multitype, $boundary) = ($1, $2);
    mimelog("multipart");
    my @rawpart = split /\r?\n?--\Q$boundary\E\r?\n?/, $body;
    #mimelog(" " . @rawpart . " raw parts.");
    my $partnum=0;
    if ($rawpart[0] =~ /This is.*MIME.formatted message/) {
      shift @rawpart;
      mimelog(qq[ Discarded "This is a MIME-formatted message" stuff.]);
      $partnum++;
    }
    if ($rawpart[-1] =~ /^--\s*$/s) {
      pop @rawpart;
    }
    my @part = #grep { defined $_ }
      map {
      my $rawdata = $_; $partnum++;
      mimelog(" Processing part $partnum.");
      my @line = split /\r?\n/, $rawdata;
      mimelog("  " . @line . " lines in part $partnum.");
      my @nwl = grep { not /^\s*$/ } @line;
      mimelog("  " . @nwl . " non-whitespace lines in part $partnum.");
      my $thispart = undef;
      if (scalar @nwl) {
        my (@rawheader, @bodyline);
        my ($ctype, $charset, $bound, $encoding, $disposition, $filename, $description, $decoded);
        my $headersdone = 0;
        while (scalar @line) {
          my $l = shift @line;
          if ((not $headersdone) and ($l =~ /^([A-Za-z0-9_-]+)[:]\s*(.*)/)) {
            my ($hname, $value) = ($1, $2);
            push @rawheader, $l;
          } elsif ((not $headersdone) and ($l =~ /^\s+(.*?)\s*$/)) {
            my $prev = pop @rawheader;
            push @rawheader, $prev . $l;
          } elsif (not $headersdone) {
            $headersdone++;
          } else {
            push @bodyline, $l;
          }}
        mimelog("  " . @rawheader . " raw headers and " . @bodyline . " body lines in part $partnum.\n");
        if ((scalar @rawheader) or (grep { not /^\s*$/ } @bodyline)) {
          for my $h (@rawheader) {
            if ($h =~ m!Content-Type:\s+(.*?)\s*$!i) {
              my ($raw) = $1;
              my ($mimetype, @info) = split /;\s*/, $raw;
              if ($mimetype =~ m!(\w+)[/](\w+)!) {
                #my ($basetype, $subtype) = ($1, $2);
                $ctype = $mimetype;
              }
              for my $i (@info) {
                if ($i =~ /charset=(.*)/) {
                  $charset = $1;
                }
                if ($i =~ /boundary=["]([^"]+)["]/) {
                  $bound = $1;
                }
              }
            } elsif ($h =~ /Content-Transfer-Encoding:\s+(.*)/i) {
              $encoding = $1;
            } elsif ($h =~ /Content-Disposition:\s+(.*?)(?:; filename=(.*?))?\s*$/i) {
              $disposition = $1;
              $filename = $2 if $2;
            } elsif ($h =~ /Content-Description:\s+(.*)/i) {
              $description = $1;
            } else {
              mimelog("  Unrecognized MIME part header (in part $partnum): $h");
            }}
          mimelog("  Part $partnum headers processed.");
          if ((not $encoding) or ($encoding eq "7bit")) {
            mimelog("  No need to decode part $partnum, not encoded.");
            $decoded = join "\n", @bodyline;
          } elsif ($encoding =~ /base64/i) {
            mimelog("  Decoding part $partnum using base64.");
            $decoded = decode_base64(join "\n", @bodyline);
          } elsif ($encoding =~ /quoted-printable/) {
            mimelog("  Decoding quoted-printable part $partnum");
            $decoded = decode_quoted_printable(join "\n", @bodyline);
          } else { # No other encodings specially supported at this time.
            mimelog("  Not decoding part $partnum: unknown encoding, '$encoding'");
            $decoded = join "\n", @bodyline;
          }
          eval {
            $decoded = decode($charset, $decoded) if $charset;
          };
          $thispart = +{ content_type => $ctype,
                         charset      => $charset,
                         boundary     => $bound,
                         encoding     => $encoding,
                         disposition  => $disposition,
                         filename     => $filename,
                         description  => $description,
                         content      => $decoded,
                         rawdata      => $rawdata,
                         partnum      => $partnum,
                       },
                     }
      }
      $thispart;
    } @rawpart;
    return ("Success", @part);
  } else {
    return; # Not multipart.
  }
}

sub decode_quoted_printable {
  my ($encoded, $charset) = @_;
  $encoded =~ s/=\r?\n//gm;
  # This works, but then HTML::TreeBuilder pitches a fit when it gets "undecoded UTF-8", whatever that means.
  eval { use MIME::QuotedPrint qw(decode_qp);
         my $decoded = decode_qp($encoded);
         $encoded = $decoded;
       };
  mimelog("Failed to decode string using MIME::QuotedPrint")
    if $encoded =~ /=([A-F0-9]{2})/;
  $encoded =~ s/=([0-9A-F]{2})/encodeasciichar($1,$charset)/eg;
  return $encoded;
}

sub encodeasciichar {
  my ($h, $charset) = @_;
  if (hex($h) < 128) {
    return chr(hex($h));
  } else {
    return "=" . $h;
  }
}

42;
