flacsplit — split flac files into multiple mp3 files
====================================================

Tool that uses `flac`, `metaflac` and `lame` to split single album
[FLAC](https://xiph.org/flac/) files with embedded cue sheets into
multiple mp3 files.

See [flactag](http://flactag.sourceforge.net/) for tools to generate
and maintain these flac files.

See [LAME](http://lame.sourceforge.net/) for more information on the
MP3 encoder.

Copying
-------

flacsplit is Copyright (C) 2009–2025 Stephen Early <steve@assorted.org.uk>

It is distributed under the terms of the GNU General Public License
as published by the Free Software Foundation, either version 3
of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but
WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see [this
link](http://www.gnu.org/licenses/).

Features
--------

 * Run multiple instances of lame in parallel to speed up conversion

 * Copy metadata and embedded album art into the output files

 * Options to make output filenames safe for FAT filesystems

 * Options to make the output directory structure duplicate that of
   the input

It should be possible to run this program on any system that supports
python 3.6 or above.

Examples
--------

Run the program to get a list of options:

    ./flacsplit.py --help

Run the program on a single input file:

    ./flacsplit.py input-file.flac

Run the program on a whole tree of flac files in
`~/Music/flac-archive`, generating a directory structure to match in
`~/large/mp3-out`, making the output filenames safe to use on a FAT
filesystem and skipping any files that haven't changed since the last
run:

```
find ~/Music/flac-archive -name "*.flac" -print0 | ./flacsplit.py \
  --verbose \
  --keep-directory-structure \
  --subdir \
  --fat-safe \
  --truncate-filenames 240 \
  --skip-newer \
  --null \
  --continue-on-error \
  --output-dir ~/large/mp3-out
```
