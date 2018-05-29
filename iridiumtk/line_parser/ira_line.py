#!/usr/bin/env python

from collections import namedtuple
import logging
import re


import six


from .base_line import BaseLine, LineParseException


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


IRA_META_REGEX = re.compile(r'.*sat:(\d+) beam:(\d+) pos=\((.[0-9.]+)/(.[0-9.]+)\) alt=([-0-9]+) .* bc_sb:\d+ (.*)')
IRA_PAGE_REGEX = re.compile(r'PAGE\(tmsi:([0-9a-f]+) msc_id:([0-9]+)\)')


Coordinates = namedtuple('Coordinates', ['x', 'y'])
Page = namedtuple('Page', ['tmsi', 'msc_id'])


# Example lines
# IRA: i-1526300857-t1 000159537 1626299264 100%   0.003 130 DL sat:80 beam:30 pos=(+54.57/-001.24) alt=001 RAI:48 ?00 bc_sb:07 PAGE(tmsi:0cf155ab msc_id:03) PAGE(NONE) descr_extra:011010110101111001110011001111100110
class IraLine(BaseLine):
    def __init__(self, line):
        super(IraLine, self).__init__(line)
        try:
            line_split = line.split()
            assert line_split[0] == 'IRA:', 'Non VOC line passed to VocLine'

            data = line.split(None, 8)[8]
            matches = IRA_META_REGEX.match(data)
            if not matches:
                raise ValueError('Failed to parse IRA data section: {}'.format(data))

            self._satellite = int(matches.group(1))
            self._beam = int(matches.group(2))
            self._position = Coordinates(x=float(matches.group(3)), y=float(matches.group(4)))
            self._altitude = int(matches.group(5))

            self._pages = []
            matches = IRA_PAGE_REGEX.findall(matches.group(6))
            for match in matches:
                self._pages.append(Page(tmsi=match[0], msc_id=int(match[1])))
        except (IndexError, ValueError) as e:
            logger.error('Failed to parse line "%s"', line)
            six.raise_from(LineParseException('Failed to parse line "{}"'.format(line), e), e)

    @property
    def satellite(self):
        return self._satellite

    @property
    def beam(self):
        return self._beam

    @property
    def position(self):
        return self._position

    @property
    def altitude(self):
        return self._altitude

    @property
    def pages(self):
        return self._pages
