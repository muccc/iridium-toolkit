#!/usr/bin/env python

import logging
from io import BytesIO
from datetime import datetime


import six


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def chunks(l, n):
    """ Yield successive n-sized chunks from l.
    """
    for i in xrange(0, len(l), n):
        yield l[i:i+n]


# Example lines
# VOC: i-1430527570.4954-t1 421036605 1625859953  66% 0.008 219 L:no LCW(0,001111,100000000000000000000 E1) 101110110101010100101101111000111111111001011111001011010001000010010001101110011010011001111111011101111100011001001001000111001101001011001011000101111111101110110011111000000001110010001110101101001010011001101001010111101100011100110011110010110110101010110001010000100100101011010010100100100011010110101001
# VOC: i-1526039037-t1 000065686 1620359296 100%   0.003 179 DL LCW(0,T:maint,C:maint[2][lqi:3,power:0,f_dtoa:0,f_dfoa:127](3),786686 E0)                                       [df.ff.f3.fc.10.33.c3.1f.0c.83.c3.cc.cc.30.ff.f3.ef.00.bc.0c.b4.0f.dc.d0.1a.cc.9c.c5.0c.fc.28.01.cc.38.c2.33.e0.ff.4f]
class VocLine(object):
    def __init__(self, line):
        try:
            line_split = line.split()

            raw_time_base = line_split[1]
            ts_base_ms = int(raw_time_base.split('-')[1].split('.')[0])

            time_offset_ns = int(line_split[2])
            self.ts = ts_base_ms + (time_offset_ns / 1000)

            self.f = int(line_split[3])/1000.
            self.lcw = line[8]

            if int(line_split[6]) < 179:
                self.data = None
            else:
                self.data = line_split[10]
        except Exception as e:
            logger.error('Failed to parse line "%s"', line)
            six.raise_from(Exception('Failed to parse line "{}"'.format(line), e), e)

    def datetime(self):
        return datetime.utcfromtimestamp(self.ts)

    def raw_voice_bits(self):
        data = self.data
        if data is None:
            return None
        byte_stream = BytesIO()
        if data[0] == "[":
            for pos in xrange(1,len(data),3):
                byte=int(data[pos:pos+2],16)
                byte=int('{:08b}'.format(byte)[::-1], 2)
                byte_stream.write(chr(byte))
        else:
            for bits in chunks(data, 8):
                byte = int(bits[::-1],2)
                byte_stream.write(chr(byte))
        return byte_stream.getvalue() 
