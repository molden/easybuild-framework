# #
# Copyright 2014-2015 Ghent University
#
# This file is part of EasyBuild,
# originally created by the HPC team of Ghent University (http://ugent.be/hpc/en),
# with support of Ghent University (http://ugent.be/hpc),
# the Flemish Supercomputer Centre (VSC) (https://vscentrum.be/nl/en),
# the Hercules foundation (http://www.herculesstichting.be/in_English)
# and the Department of Economy, Science and Innovation (EWI) (http://www.ewi-vlaanderen.be/en).
#
# http://github.com/hpcugent/easybuild
#
# EasyBuild is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation v2.
#
# EasyBuild is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with EasyBuild.  If not, see <http://www.gnu.org/licenses/>.
# #
"""
Module which allows the diffing of multiple files

@author: Toon Willems (Ghent University)
@author: Kenneth Hoste (Ghent University)
"""

import difflib
import math
import os
from vsc.utils import fancylogger

from easybuild.tools.filetools import read_file
from easybuild.tools.utilities import det_terminal_size


SEP_WIDTH = 5

# text colors
PURPLE = "\033[0;35m"
# background colors
GREEN_BACK = "\033[0;42m"
RED_BACK = "\033[0;41m"
# end character for colorized text
END_COLOR = "\033[0m"

# meaning characters in diff context
HAT = '^'
MINUS = '-'
PLUS = '+'
SPACE = ' '

END_LONG_LINE = '...'


_log = fancylogger.getLogger('multidiff', fname=False)


class MultiDiff(object):
    """
    Class representing a multi-diff.
    """
    def __init__(self, base, files, colored=True):
        """
        MultiDiff constructor
        @param base: base to compare with
        @param files: list of files to compare with base
        @param colored: boolean indicating whether a colored multi-diff should be generated
        """
        self.base = base
        self.base_lines = read_file(self.base).split('\n')
        self.files = files
        self.colored = colored
        self.diff_info = {}

    # FIXME's in docstring
    def parse_line(self, line_no, diff_line, meta, squigly_line=None):
        """
        Parse a line as generated by difflib
        @param line_no: line number
        @param diff_lin: line generated by difflib
        @param meta: FIXME
        @param squigly_line: FIXME
        """
        # register (diff_line, meta, squigly_line) tuple for specified line number and determined key
        key = diff_line[0]
        if not key in [MINUS, PLUS]:
            _log.error("diff line starts with unexpected character: %s" % diff_line)
        line_key_tuples = self.diff_info.setdefault(line_no, {}).setdefault(key, [])
        line_key_tuples.append((diff_line.rstrip(), meta, squigly_line))

    def color_line(self, line, color):
        """Create colored version of given line, with given color, if color mode is enabled."""
        if self.colored:
            line = ''.join([color, line, END_COLOR])
        return line

    def merge_squigly(self, squigly1, squigly2):
        """Combine two diff lines into a single diff line."""
        sq1 = list(squigly1)
        sq2 = list(squigly2)
        # longest line is base
        base, other = (sq1, sq2) if len(sq1) > len(sq2) else (sq2, sq1)

        for i, o in enumerate(other):
            if base[i] in [HAT, SPACE] and base[i] != o:
                base[i] = o

        return ''.join(base)

    def colorize(self, line, squigly):
        """Add colors to the diff line based on the squiqly line"""
        if not self.colored:
            return line

        chars = list(line)
        flag = ' '
        compensator = 0
        color_map = {
            HAT: GREEN_BACK if line.startswith(PLUS) else RED_BACK,
            MINUS: RED_BACK,
            PLUS: GREEN_BACK,
        }
        if squigly:
            for i, s in enumerate(squigly):
                if s != flag:
                    chars.insert(i + compensator, END_COLOR)
                    compensator += 1
                    if s in [HAT, MINUS, PLUS]:
                        chars.insert(i + compensator, color_map.get(s, ''))
                        compensator += 1
                    flag = s
            chars.insert(len(squigly)+compensator, END_COLOR)
        else:
            chars.insert(0, color_map.get(line[0], ''))
            chars.append(END_COLOR)

        return ''.join(chars)

    def get_line(self, line_no):
        """
        Return the line information for a specific line
        @param line_no: line number to obtain information for
        @return: list with text lines providing line information
        """
        output = []
        diff_dict = self.diff_info.get(line_no, {})
        for key in [MINUS, PLUS]:
            lines, changes_dict, squigly_dict = set(), {}, {}

            if key in diff_dict:
                for (diff_line, meta, squigly_line) in diff_dict[key]:
                    if squigly_line:
                        squigly_line2 = squigly_dict.get(diff_line, squigly_line)
                        squigly_dict[diff_line] = self.merge_squigly(squigly_line, squigly_line2)
                    lines.add(diff_line)
                    changes_dict.setdefault(diff_line,set()).add(meta)

            # restrict displaying of removals to max_groups
            max_groups = 2
            # sort highest first
            lines = sorted(lines, key=lambda line: len(changes_dict[line]))
            # limit to max_groups
            lines = lines[::-1][:max_groups]

            for diff_line in lines:
                line = [str(line_no)]
                squigly_line = squigly_dict.get(diff_line,'')
                line.append(self.colorize(diff_line, squigly_line))

                files = changes_dict[diff_line]
                num_files = len(self.files)

                line.append("(%d/%d)" % (len(files), num_files))
                if len(files) != num_files:
                        line.append(', '.join(files))

                output.append(' '.join(line))
                # prepend spaces to match line number length
                if not self.colored and squigly_line:
                    prepend = ' ' * (2 + int(math.log10(line_no)))
                    output.append(''.join([prepend,squigly_line]))

        # print seperator only if needed
        if diff_dict and not self.diff_info.get(line_no + 1, {}):
            output.extend([' ', '-' * SEP_WIDTH, ' '])

        return output

    def __str__(self):
        """
        Create a string representation of this multi-diff
        """
        def limit(text, length):
            """Limit text to specified length, terminate color mode and add END_LONG_LINE if trimmed."""
            if len(text) > length:
                maxlen = length - len(END_LONG_LINE)
                res = text[:maxlen]
                if self.colored:
                    res += END_COLOR
                return res + END_LONG_LINE
            else:
                return text

        term_width, _ = det_terminal_size()

        base = self.color_line(os.path.basename(self.base), PURPLE)
        filenames = ', '.join(map(os.path.basename, self.files))
        output = [
            "Comparing %s with %s" % (base, filenames),
            '=' * SEP_WIDTH,
        ]

        diff = False
        for i in range(len(self.base_lines)):
            lines = filter(None, self.get_line(i))
            if lines:
                output.append('\n'.join([limit(line, term_width) for line in lines]))
                diff = True

        if not diff:
            output.append("(no diff)")

        output.append('=' * SEP_WIDTH)

        return '\n'.join(output)

def multidiff(base, files, colored=True):
    """
    Generate a diff for multiple files, all compared to base.
    @param base: base to compare with
    @param files: list of files to compare with base
    @param colored: boolean indicating whether a colored multi-diff should be generated
    @return: text with multidiff overview
    """
    differ = difflib.Differ()
    mdiff = MultiDiff(base, files, colored)

    # use the MultiDiff class to store the information
    for filepath in files:
        lines = read_file(filepath).split('\n')
        diff = differ.compare(lines, mdiff.base_lines)
        filename = os.path.basename(filepath)

        local_diff = dict()
        squigly_dict = dict()
        last_added = None
        compensator = 1
        for (i, line) in enumerate(diff):
            if line.startswith('?'):
                squigly_dict[last_added] = line
                compensator -= 1
            elif line.startswith(PLUS):
                local_diff.setdefault(i + compensator, []).append((line, filename))
                last_added = line
            elif line.startswith(MINUS):
                local_diff.setdefault(i + compensator, []).append((line, filename))
                last_added = line
                compensator -= 1

        # construct the multi-diff based on the constructed dict
        for line_no in local_diff:
            for (line, filename) in local_diff[line_no]:
                mdiff.parse_line(line_no, line, filename, squigly_dict.get(line, '').rstrip())

    return str(mdiff)
