#!/usr/bin/env python3

# Requires python 3.6 for the "encoding" parameter for Popen and for
# os.path.commonpath to accept a sequence of path-like objects

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
import pathlib
import itertools
import multiprocessing
import signal

class flactags:
    def __init__(self, path):
        mf = subprocess.Popen(["metaflac", "--export-tags-to=-", str(path)],
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
    def __init__(self, path):
        mf = subprocess.Popen(["metaflac","--export-cuesheet-to=-", str(path)],
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

def fatsafe(name):
    invalid_fat_characters = ['?', ':', '|', '"']
    for i in invalid_fat_characters:
        name = name.replace(i, '')
    return name

class flacfile:
    def __init__(self, file_with_info):
        path, inputbase, args = file_with_info
        self.path = path
        self.args = args

        self.cuesheet = cuesheet(path)
        self.tags = flactags(path)
        self.jobs = []

        if args.verbose:
            print("%s: %d tracks in file." % (path, self.cuesheet.lasttrack))

        outdir = args.outputdir
        if args.keepdirs:
            relative = path.relative_to(inputbase) if inputbase \
                       else path
            # If the fatsafe flag is specified, every component that we add
            # to the output path must be fatsafe
            if args.fatsafe:
                for part in relative.parent.parts:
                    outdir = outdir / fatsafe(part)
            else:
                outdir = outdir.joinpath(relative.parent)
        if args.subdir:
            if args.fatsafe:
                outdir = outdir / fatsafe(path.stem)
            else:
                outdir = outdir / path.stem

        self.badtracks = []
        for track in range(1, self.cuesheet.lasttrack + 1):
            if track not in self.cuesheet.tracks:
                self.badtracks.append(
                    "track %d not present" % track)
                continue
            if track not in self.tags.tracks:
                self.badtracks.append("track %d has no tags" % track)
                continue
            if not checktags(self.tags.tracks[track]):
                self.badtracks.append("track %d is missing required tags" % track)
                continue
            if args.verbose:
                print("%02d: %s by %s" % (
                    track, self.tags.tracks[track]['TITLE'],
                    self.tags.tracks[track]['ARTIST']))
            outfilename = "%02d %s (%s).mp3" % (
                track,
                self.tags.tracks[track]['TITLE'],
                self.tags.tracks[track]['ARTIST'])
            outfilename = outfilename.replace(os.sep, '')
            if args.fatsafe:
                outfilename = fatsafe(outfilename)
            outputfile = outdir / outfilename
            try:
                output_mtime = outputfile.stat().st_mtime
            except:
                output_mtime = 0
            if args.update:
                if output_mtime > input_mtime:
                    if args.verbose:
                        print("  - skipping %s because it is newer" % outputfile)
                continue
            self.jobs.append((self, track, outputfile))

    @staticmethod
    def process_job(jobinfo):
        self, tracknum, outputfile = jobinfo
        # Make sure the output directory exists
        outputfile.parent.mkdir(parents=True, exist_ok=True)
        tags = self.tags.tracks[tracknum]
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
             "--output-name=-", str(self.path)],
            stdout=subprocess.PIPE)
        lame = subprocess.Popen(
            ["lame", "--preset", args.lamepreset, "--silent"] + id3opts + [
                "-", str(outputfile)],
            stdin=flac.stdout)
        try:
            lame.communicate()
        except KeyboardInterrupt:
            try:
                ouputfile.unlink()
            except:
                pass
            return "Aborted"
        flac.wait()
        lame.wait()
        if flac.returncode != 0 or lame.returncode != 0:
            try:
                outputfile.unlink()
            except:
                pass
            return ("Error writing %s: flac returncode %d, "
                    "lame returncode %d" % (outputfile, flac.returncode,
                                            lame.returncode))
        return "%s track %d -> %s" % (self.path, tracknum, outputfile)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description="Split flac files into multiple mp3 files")
    parser.add_argument('--version', action='version', version=version)
    parser.add_argument(
        "-o", "--output-dir", action="store", type=pathlib.Path,
        dest="outputdir", help="Output directory, default '.'",
        default=pathlib.Path.cwd())
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
        "-j", "--jobs", action="store", type=int, default=os.cpu_count(),
        help="Number of tracks to work on in parallel")
    inputs = parser.add_mutually_exclusive_group()
    inputs.add_argument(
        "-x", "--from-stdin", action="store_true", dest="fromstdin",
        help="Read list of filenames from stdin, one per line")
    inputs.add_argument(
        "-0", "--null", action="store_true", dest="null",
        help="Read list of filenames from stdin, each terminated by "
        "a null character.  The GNU find -print0 option produces input "
        "suitable for this mode.")

    parser.add_argument('filenames', metavar='filename.flac', type=str,
                        nargs='*', help="file to process")

    args = parser.parse_args()

    if (args.fromstdin or args.null) and args.filenames:
        parser.error("You can't specify filenames on the command line and "
                     "also read them from stdin")
        sys.exit(1)

    if args.fromstdin:
        filesource = sys.stdin.read()
        filenames = filesource.split('\n')
    elif args.null:
        filesource = sys.stdin.read()
        filenames = filesource.split('\0')
    else:
        filenames = args.filenames

    files = [ pathlib.Path(x) for x in filenames if x ]

    if len(files) < 1:
        parser.error("please supply at least one input filename")

    inputbase = os.path.commonpath(files)
    inputbase = pathlib.Path(inputbase) if inputbase else None

    if not args.outputdir.is_dir():
        print("Output location '%s' is not a directory" % args.outputdir)
        sys.exit(1)

    def pool_init():
        """Ignore SIGINT in worker processes
        """
        signal.signal(signal.SIGINT, signal.SIG_IGN)

    pool = multiprocessing.Pool(args.jobs, initializer=pool_init)

    files_with_info = ((f, inputbase, args) for f in files)
    flacs = list(pool.imap_unordered(flacfile, files_with_info))
    jobs = itertools.chain.from_iterable((f.jobs for f in flacs))
    statuses = pool.imap_unordered(flacfile.process_job, jobs)

    try:
        for s in statuses:
            print(s)

        for f in flacs:
            if f.badtracks:
                print("%s problems:" % f.path)
                for t in f.badtracks:
                    print("  %s" % t)

    except KeyboardInterrupt:
        print("Exiting - output files may be incomplete")
        pool.terminate()

    pool.close()
    pool.join()
