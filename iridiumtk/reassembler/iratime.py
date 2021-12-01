#!/usr/bin/env python3
# vim: set ts=4 sw=4 tw=0 et pm=:

import sys
import re
import collections

from .base import *
from ..config import config, outfile

class ReassembleIRATime(Reassemble):
    def __init__(self):
        pass
    def filter(self,line):
        q=super(ReassembleIRATime,self).filter(line)
        if q==None: return None
        if q.typ!="IRA:": return None
        q.enrich()

        p=re.compile(r'sat:(\d+) beam:(\d+)')
        m=p.match(q.data)
        if(not m):
            print("Couldn't parse IRA:",q.data, end=' ', file=sys.stderr)
            return None

        q.sat=     int(m.group(1))
        q.beam=    int(m.group(2))

        return q

    buf=collections.defaultdict(lambda:collections.defaultdict(int))
    def process(self,q):
        if q.beam in self.buf[q.sat]:
            if q.time-self.buf[q.sat][q.beam] < 4.2:
                strtime=datetime.datetime.fromtimestamp(q.time,tz=Z).strftime("%Y-%m-%dT%H:%M:%S")
                print("%3d %3d: %s %f"%(q.beam,q.sat,strtime,q.time-self.buf[q.sat][q.beam]))

        self.buf[q.sat][q.beam]=q.time

    def consume(self,q):
        raise Exception("unreachable")

modes=[
["ira",       ReassembleIRATime,  ],
]
