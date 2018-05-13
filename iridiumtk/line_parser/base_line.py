#!/usr/bin/env python

from datetime import datetime
import logging


import six


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Example lines
# VOC: i-1430527570.4954-t1 421036605 1625859953  66% 0.008 219 L:no LCW(0,001111,100000000000000000000 E1) 101110110101010100101101111000111111111001011111001011010001000010010001101110011010011001111111011101111100011001001001000111001101001011001011000101111111101110110011111000000001110010001110101101001010011001101001010111101100011100110011110010110110101010110001010000100100101011010010100100100011010110101001
# VOC: i-1526039037-t1 000065686 1620359296 100%   0.003 179 DL LCW(0,T:maint,C:maint[2][lqi:3,power:0,f_dtoa:0,f_dfoa:127](3),786686 E0)                                       [df.ff.f3.fc.10.33.c3.1f.0c.83.c3.cc.cc.30.ff.f3.ef.00.bc.0c.b4.0f.dc.d0.1a.cc.9c.c5.0c.fc.28.01.cc.38.c2.33.e0.ff.4f]
class BaseLine(object):
    def __init__(self, line):
        try:
            self._raw_line = line
            line_split = line.split()

            self._frame_type = line_split[0][:-1]

            raw_time_base = line_split[1]
            ts_base_ms = int(raw_time_base.split('-')[1].split('.')[0])

            time_offset_ns = int(line_split[2])
            self._timestamp = ts_base_ms + (time_offset_ns / 1000)

            self._frequnecy = int(line_split[3])
        except Exception as e:
            logger.error('Failed to parse line "%s"', line)
            six.raise_from(Exception('Failed to parse line "{}"'.format(line), e), e)

    @property
    def raw_line(self):
        return self._raw_line

    @property
    def frame_type(self):
        return self._frame_type

    @property
    def frequency(self):
        return self._frequnecy

    @property
    def datetime(self):
        return datetime.utcfromtimestamp(self._timestamp)

    @property
    def datetime_unix(self):
        return self._timestamp
