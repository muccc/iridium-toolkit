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
    mt_heat = {}

    def __init__(self):
        super().__init__()
        global json
        import json
        if config.stats:
            from util import curses_eol
            global eol
            eol = curses_eol()

    def args(self, parser):
        global config

        parser.add_argument("--uplink", "--ul", action='store_true', help="do uplink positions instead")
        parser.add_argument("--heatmap", action='store_true', help="produce json for heatmap instead")
        config = parser.parse_args()

        return config


    def consume(self, q):
        (data, time, ul, _, freq) = q
        if len(data) < 2:
            return

        m_type = data[:2].hex()

        if m_type != "0605" and m_type != "7605" and not config.uplink:
            return

        if m_type != "0600" and config.uplink:
            return

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
        elif m_type == "0600": # UL
            off = 16+2
            if data[0+2] in (0x10, 0x40, 0x70) and len(data) > off+2 and data[off-1] == 0x01:
                type = 'ul'
                pos = xyz(data[off:], 0)
            else:
                return
        else:
            raise ValueError

        if config.heatmap:
            key = str([pos['x'], pos['y'], pos['z']])
            if key not in self.mt_heat:
                p = [pos['x']*4000+2000, pos['y']*4000+2000, pos['z']*4000+2000]
                self.mt_heat[key] = {"type": "Feature", "geometry": {"type": "Point", "coordinates": p}, "properties": {"weight": 0}}
            if self.mt_heat[key]["properties"]["weight"] < 10:
                self.mt_heat[key]["properties"]["weight"] += 1
            if config.stats:
                if time >= self.last_output + self.intvl*10:
                    self.last_output = time
                    sts = dt.epoch(int(time))
                    mts = len(self.mt_heat)
                    print("%s: %d MTs" % (sts, mts), end=eol, file=sys.stderr)
            return

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

    def end(self):
        if config.stats:
            print("", file=sys.stderr)
        if config.heatmap:
            ofile = config.output
            if ofile is None:
                ofile = "mt-heat.json"
            temp_file_path = "%s.tmp" % (ofile)
            with open(temp_file_path, "w") as f:
                print(json.dumps({"type": "FeatureCollection", "features": list(self.mt_heat.values())}, separators=(',', ':')), file=f)
            os.rename(temp_file_path, ofile)


modes = [
    ["live-mt-map", ReassembleIDAMap, ],
]
