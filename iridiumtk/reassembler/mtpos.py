#!/usr/bin/env python3
# vim: set ts=4 sw=4 tw=0 et pm=:

import sys
import datetime
import re
import crcmod
import os

from util import fmt_iritime, xyz, dt

from .base import *
from .ida import ReassembleIDA
from ..config import config, outfile


class ReassembleIDAMap(ReassembleIDA):
    """Extract coordinates from access decision messages"""

    intvl = 60
    exptime = 60 * 8
    last_output = 0

    mt_pos = []

    def __init__(self):
        super().__init__()
        global json
        import json
        if config.stats:
            from util import curses_eol
            global eol
            eol = curses_eol()

    def consume(self, q):
        (data, time, ul, _, freq) = q
        if len(data) < 2:
            return

        m_type = data[:2].hex()

        if m_type != "0605" and m_type != "7605":
            return

        if ul:
            ul = "UL"
        else:
            ul = "DL"

        if m_type == "7605":
            if len(data) > 5 and data[2] == 0 and data[3]&0xf0 == 0x40:
                type = 'sbd'
                pos = xyz(data[3:], 4)
            elif len(data) > 3 and data[3] == 0x50: # ack only
                return
            else: # no match
                return
        elif m_type == "0605":
            off = (2+1+20+1+3+3+2+2+2)
            if len(data) > off+2 and data[off] == 0x1b:
                type = 'gsm'
                pos = xyz(data[off+1:], 0)
                #lac_o=2+1+20
                #if data[lac_o] == 0x04:
                #    print("lac=",data[lac_o+1:lac_o+3].hex())
                #if data[lac_o+3] == 0x61:
                #    print("sca=",data[lac_o+4:lac_o+6].hex())
            else: # no match
                return
        else:
            raise ValueError

        self.mt_pos.append({"xyz": [pos['x']*4+2, pos['y']*4+2, pos['z']*4+2], "type": type, "ts": int(time)})

        if time >= self.last_output + self.intvl:
            self.last_output = time
            self.mt_pos = [x for x in self.mt_pos if x['ts'] > time - self.exptime]

            ofile = config.output
            if ofile is None:
                ofile = "mt.json"
            temp_file_path = "%s.tmp" % (ofile)
            with open(temp_file_path, "w") as f:
                print(json.dumps({"time": int(time), "interval": self.intvl, "mt_pos": self.mt_pos}, separators=(',', ':')), file=f)
            os.rename(temp_file_path, ofile)
            if config.stats:
                sts = dt.epoch(int(time))
                mts = len(self.mt_pos)
                print("%s: %d MTs" % (sts, mts), end=eol, file=sys.stderr)


modes = [
    ["live-mt-map", ReassembleIDAMap, ],
]
