#!/usr/bin/env python3
# vim: set ts=4 sw=4 tw=0 et pm=:

import sys
import re
from util import to_ascii

from .base import *
from .sbd import ReassembleIDASBD
from ..config import config, outfile

class ReassembleIDASBDNal(ReassembleIDASBD):
    def consume_l2(self,q):
#        print(repr(q.__dict__))
        typ=q.typ
        time=q.time
        prehdr=q.prehdr
        data=q.data

        if len(data)!=10:
            return

        lat_raw = _extract_bits(data, 4, 25)
        long_raw = _extract_bits(data, 29, 25)
        seconds = _extract_bits(data, 55, 17)
        pdop_index = _extract_bits(data, 72, 4)
        bits = _extract_bits(data, 76, 4)

        if lat_raw > 18000000:
            print("NALException: Invalid latitude value", file=sys.stderr)
            return
        if long_raw > 36000000:
            print("NALException: Invalid longitude value", file=sys.stderr)
            return
        if seconds >= 86400:
            print("NALException: Invalid seconds value", file=sys.stderr)
            return
        if pdop_index >= 8:
            print("NALException: Invalid PDOP value", file=sys.stderr)
            return

        lat = (lat_raw - 9000000) / 100000
        lon = (long_raw - 18000000) / 100000

        #minutes, seconds = divmod(seconds, 60)
        #hours, minutes = divmod(minutes, 60)

        pdop = [1, 2, 5, 10, 20, 40, 70, 100][pdop_index]

        fix = bool(bits & 0b0001)
        emergency = bool(bits & 0b0010)
        emergency_acknowledged = bool(bits & 0b0100)
        motion = bool(bits & 0b1000)


        bcd=["%x"%(x>>s&0xf) for x in prehdr[5:13] for s in (0,4)]

        print("".join(bcd[1:]),f"lat=%.6f lon=%.6f, pdop={pdop}, emerg/ack: {emergency}/{emergency_acknowledged}, motion: {motion}, fix: {fix}, time: %02d:%02d:%02d"%(lat,lon,seconds//3600,(seconds//60)%60,seconds%60), file=outfile)

def _extract_bits(data: bytes, start: int, amount: int) -> int:
    value = 0
    num = start + amount
    for index in range(start, num):
        if (data[index // 8] & (1 << (index % 8))) != 0:
            value += (1 << (index - start))
    return value

modes=[
["nal10",        ReassembleIDASBDNal, ],
]
