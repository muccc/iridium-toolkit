#!/usr/bin/env python3
# vim: set ts=4 sw=4 tw=0 et pm=:

import sys
import re
from util import dt
import numpy as np

from .base import *
from ..config import config, outfile

early_frame = 3

conv_start = None


def lbfc_str(ts, start=0):
    """Convert milliseconds into L-Band frame counter"""
    global conv_start

    if start != 0:
        conv_start = start

    if conv_start is None:
        return "            "

    ts = ts - conv_start
    lbfc_c = int((ts)//90)
    lbfc_o = ts-lbfc_c*90

    # guard + simplex + guard + 4* uplink + 4* downlink
    # 1 + 20.32 + 1.24 + 4 * (8.28 + 0.22) + 0.02 + 4 * (8.28 + 0.1) - 0.1

    # moved the first guard from the begining to the end
    slots = (20.32+1.24,
             8.28+0.22, 8.28+0.22, 8.28+0.22, 8.28+0.22+0.02,
             8.28+0.1,  8.28+0.1,  8.28+0.1,  8.28+1 + early_frame, )

    sname = ("S", "U1", "U2", "U3", "U4", "D1", "D2", "D3", "D4", )

    st = 0
    for i, t in enumerate(slots):
        if lbfc_o < st + t - early_frame: # allow slots to start slightly early
            if len(sname[i]) == 1:
                slot = f"{sname[i]}{round(lbfc_o - st):+03d}"
            else:
                slot = f"{sname[i]}{round(lbfc_o - st):+2d}"
            break
        st += t
    return f"{lbfc_c:03d}∆{lbfc_o:+03.0f}#{slot}"


class ReassembleTIME(Reassemble):
    toff = None

    def __init__(self):
        pass

    def filter(self, line):
        q = super().filter(line)
        if q is None:
            print("-", line, end="")
            return None
        return q

    def process(self, q):
        q.enrich(channelize=True)
        if self.toff is None and q.typ in ("IRA:", "ITL:", "INP:", "IMS:", "MSG:"):
            self.toff = q.mstime
        q.uxtime = np.datetime64(int(q.starttime), 's')
        q.uxtime += np.timedelta64(q.nstime, 'ns')
        strtime = str(q.uxtime)[:-2]
        if False:
            lbfc_c = (q.mstime-self.toff+45)//90
            lbfc_o = q.mstime-self.toff-lbfc_c*90
            return [f"{strtime} {lbfc_c%48:02.0f}#{lbfc_o:+07.3f} {q.typ} {q.freq_print} {q.confidence:3d}% {q.level:6.2f} {q.symbols} {q.uldl} {q.data}"]
        lbs = lbfc_str(q.mstime, self.toff)
        return [f"{strtime} {lbs} {q.typ} {q.freq_print} {q.confidence:3d}% {q.level:6.2f} {q.symbols} {q.uldl} {q.data}"]

    def consume(self, q):
        print(q, end="", file=outfile)

modes=[
["time",       ReassembleTIME,  ],
]
