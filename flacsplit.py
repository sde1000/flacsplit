#!/usr/bin/env python3

# Requires python 3.6 for the "encoding" parameter for Popen

"""Split a flac file with cuesheet and embedded tags into multiple
files, optionally re-encoded as mp3.
"""

version = "0.2"

import os
import os.path
import subprocess
import re
import sys
import argparse

errorlog = []

def report_error(message):
    print(message)
    errorlog.append(message)
    if not args.cont:
        print("Aborting (to continue on errors use the '-c' option)")
        sys.exit(1)

class flactags:
    def __init__(self, filename):
        mf = subprocess.Popen(["metaflac", "--export-tags-to=-", filename],
                              stdout=subprocess.PIPE, encoding="utf-8")
        tags, xxx = mf.communicate()
        if mf.returncode != 0:
            self.tracks = None
            return
        taglines = [x.strip() for x in tags.split("\n")]
        defaults = {} # Tags with no track number specified
        tracks = {}
        for x in taglines:
            s = x.split('=', 1)
            if len(s) != 2:
                continue
            tag, value = s
            m = re.search(r'(.*)\[(\d+)\]', tag)
            if m is None:
                defaults[tag] = value
            else:
                tagname = m.groups()[0]
                tracknumber = int(m.groups()[1])
                if tracknumber not in tracks:
                    tracks[tracknumber] = defaults.copy()
                tracks[tracknumber][tagname] = value
        # Deal with single-track files
        if tracks == {}:
            tracks[1] = defaults
        self.tracks = tracks

def checktags(tags):
    """Check that at least ARTIST and TITLE tags are present.

    """
    if 'ARTIST' not in tags:
        return False
    if 'TITLE' not in tags:
        return False
    return True

class cuesheet:
    """The cuesheet will tell us how many tracks are present.  We
    ignore the timing information because we will be using the --cue
    option to flac to select each track.  If there is no cuesheet we
    will treat this as a single-track file.

    """
    def __init__(self, filename):
        mf = subprocess.Popen(["metaflac","--export-cuesheet-to=-", filename],
                              stdout=subprocess.PIPE, encoding="utf-8")
        cues, xxx = mf.communicate()
        if mf.returncode != 0:
            if args.verbose:
                print("no cuesheet in '%s'; assuming single track" % filename)
            self.tracks = {1: None}
            self.lasttrack = 1
            return
        cuelines = [x.strip() for x in cues.split("\n")]
        tracks = {}
        tracknum = None
        for x in cuelines:
            m = re.search(r'TRACK (\d\d) AUDIO', x)
            if m != None:
                tracknum = int(m.groups()[0])
                tracks[tracknum] = None
                continue
            m = re.search(r'ISRC (.*)', x)
            if m != None:
                tracks[tracknum] = m.groups()[0]
        self.tracks = tracks
        self.lasttrack = tracknum

def output_track(filename, destfile, tracknum, tags):
    fields = [('TITLE', '--tt'),
              ('ARTIST', '--ta'),
              ('ALBUM', '--tl'),
              ('DATE', '--ty'),
              ('TRACKNUMBER', '--tn'),
    ]
    id3opts = []
    for name, opt in fields:
        if name in tags:
            id3opts = id3opts + [opt, tags[name]]
        
    flac = subprocess.Popen(
        ["flac", "--decode",
         "--totally-silent",
         "--cue=%d.1-%d.1" % (tracknum, tracknum + 1),
         "--output-name=-", filename],
        stdout=subprocess.PIPE)
    lame = subprocess.Popen(
        ["lame", "--preset", args.lamepreset, "--silent"] + id3opts + [
        "-", destfile],
        stdin=flac.stdout)
    try:
        lame.communicate()
    except KeyboardInterrupt:
        try:
            print("Removing incomplete file '%s'" % destfile)
            os.remove(destfile)
        except:
            pass
        raise
    flac.wait()
    lame.wait()
    if flac.returncode != 0 or lame.returncode != 0:
        try:
            os.remove(destfile)
        except:
            pass
        report_error("Error writing %s: flac returncode %d, "+
                     "lame returncode %d" % (destfile, flac.returncode,
                                             lame.returncode))

def fatsafe(name):
    invalid_fat_characters = ['?', ':', '|', '"']
    for i in invalid_fat_characters:
        name = name.replace(i, '')
    return name

def process_file(inputfile, tracks):
    basename = os.path.basename(inputfile)
    if basename[-5:] == '.flac':
        basename = basename[:-5]
    try:
        input_mtime = os.stat(inputfile).st_mtime
    except:
        report_error("could not stat input file '%s'" % inputfile)
        return

    c = cuesheet(inputfile)
    t = flactags(inputfile)
    if t.tracks is None:
        report_error("tags could not be read from file '%s'" % inputfile)
        return

    if tracks is None:
        tracks = range(1, c.lasttrack + 1)

    # Single-track files do not need tags, because we name the output file
    # after the input file rather than the track title
    if c.lasttrack > 1:
        # Check that tracks are present and have tags
        badtracks = []
        for x in tracks:
            if x not in c.tracks:
                badtracks.append(x)
                report_error("track %d not present in file '%s'"%(x, inputfile))
            if x not in t.tracks:
                badtracks.append(x)
                report_error("track %d has no tags in file '%s'"%(x, inputfile))
            else:
                if not checktags(t.tracks[x]):
                    badtracks.append(x)
                    report_error("track %d is missing required tags " +
                                 "in file '%s'" % (x, inputfile))
        tracks = [x for x in tracks if x not in badtracks]

    if args.verbose:
        print("%s: %d tracks in file." % (inputfile, c.lasttrack))
        for i in tracks:
            print("%02d: %s by %s" % (
                i,t.tracks[i]['TITLE'], t.tracks[i]['ARTIST']))
    for i in tracks:
        outdir = args.outputdir
        if args.keepdirs:
            outdir = outdir + os.sep + os.path.dirname(inputfile)
        if args.subdir and c.lasttrack != 1:
            outdir = outdir + os.sep + basename
        if args.verbose:
            print("Working on %s track %d..." % (inputfile, i))
        if args.fatsafe:
            outdir = fatsafe(outdir)
        if args.keepdirs or args.subdir:
            try:
                os.makedirs(outdir)
            except OSError:
                pass # probably already exists; os.makedirs() is not
                     # the same as mkdir -p
        if c.lasttrack != 1:
            outfilename = "%02d %s (%s).mp3" % (
                i, t.tracks[i]['TITLE'], t.tracks[i]['ARTIST'])
        else:
            outfilename = basename + ".mp3"
        outfilename = outfilename.replace(os.sep, '')
        if args.fatsafe:
            outfilename = fatsafe(outfilename)
        outputname = outdir + os.sep + outfilename
        try:
            output_mtime = os.stat(outputname).st_mtime
        except:
            output_mtime = 0
        if args.update:
            if output_mtime > input_mtime:
                if args.verbose:
                    print("  - skipping %s because it is newer" % outputname)
                continue
        if args.verbose:
            print("  - writing to %s" % outputname)
        output_track(inputfile, outputname, i, t.tracks[i])

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description="Split flac files into multiple mp3 files")
    parser.add_argument('--version', action='version', version=version)
    parser.add_argument(
        "-o", "--output-dir", action="store", type=str,
        dest="outputdir", help="Output directory, default '.'",
        default='.')
    parser.add_argument(
        "-v", "--verbose", action="store_true", dest="verbose",
        help="Show track lists and progress details",
        default=False)
    parser.add_argument(
        "-k", "--keep-directory-structure", action="store_true",
        dest="keepdirs", help="Reproduce the directory structure "
        "of the input when creating the output files",
        default=False)
    parser.add_argument(
        "-s", "--subdir", action="store_true",
        dest="subdir", help="Create the output files in a "
        "directory named after the input file; ignored if "
        "the input file only contains one track", default=False)
    parser.add_argument(
        "-f", "--fat-safe", action="store_true", dest="fatsafe",
        help="Remove characters from output pathnames that "
        "are not safe for FAT filesystems", default=False)
    parser.add_argument(
        "-n", "--skip-newer", action="store_true", dest="update",
        help="Do not overwrite an output file if it is "
        "newer than the input file", default=False)
    parser.add_argument(
        "-c", "--continue-on-error", action="store_true",
        help="Continue working after an error and report all "
        "the errors at the end", dest="cont", default=False)
    parser.add_argument(
        "-p", "--lame-preset", action="store", type=str,
        dest="lamepreset", default="extreme",
        help="Preset to pass to lame, default 'extreme'")
    parser.add_argument(
        "-t", "--tracks", action="store", type=str,
        dest="tracks",
        help="List of tracks to work on, default all; example "+
        "'1-3,5,7-10'", default=None)
    parser.add_argument('filenames', metavar='filename.flac', type=str,
                        nargs='+', help="file to process")

    args = parser.parse_args()
    if len(args.filenames) < 1:
        parser.error("please supply at least one input filename")

    if args.tracks is None:
        tracks = None
    else:
        try:
            tracks = []
            for tr in args.tracks.split(','):
                r = tr.split('-')
                if len(r) == 1:
                    tracks.append(int(r[0]))
                elif len(r) == 2:
                    tracks += list(range(int(r[0]), int(r[1]) + 1))
                else:
                    raise
        except:
            parser.error("invalid track list supplied")

    for i in args.filenames:
        process_file(i, tracks)

    if len(errorlog) > 0:
        print("Errors recorded in this run:")
        for i in errorlog:
            print(i)
