#!/usr/bin/env python3
# vim: set ts=4 sw=4 tw=0 et pm=:

import sys
import re
from util import dt

from .base import *
from ..config import config, outfile


class ReassembleTIME(Reassemble):
    toff = None

    def __init__(self):
        pass

    def filter(self, line):
        q = super().filter(line)
        if q is None: return None
        return q

    def process(self, q):
        q.enrich(channelize=True)
        if self.toff is None:
            self.toff = q.mstime
        strtime = dt.epoch(q.time).isoformat(timespec='centiseconds')
        lbfc_c = (q.mstime-self.toff+45)//90
        lbfc_o = q.mstime-self.toff-lbfc_c*90
        return [f"{strtime} {lbfc_c%48:02.0f}#{lbfc_o:+07.3f} {q.typ} {q.freq_print} {q.confidence:3d}% {q.level:6.2f} {q.symbols} {q.uldl} {q.data}"]

    def consume(self, q):
        print(q, end="", file=outfile)

modes=[
["time",       ReassembleTIME,  ],
]
