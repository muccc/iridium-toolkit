#!/usr/bin/env python3
# vim: set ts=4 sw=4 tw=0 et pm=:

import sys
import re
from util import dt

from .base import *
from ..config import config, outfile

class ReassembleIRA(Reassemble):
    def __init__(self):
        self.topic="IRA"
        pass
    def filter(self,line):
        q=super().filter(line)
        if q==None: return None
        if q.typ=="IRA:":
            p=re.compile(r'sat:(\d+) beam:(\d+) (?:(?:aps|xyz)=\(([+-]?[0-9]+),([+-]?[0-9]+),([+-]?[0-9]+)\) )?pos=\(([+-][0-9.]+)/([+-][0-9.]+)\) alt=(-?[0-9]+) .* bc_sb:\d+(?: (.*))?')
            m=p.search(q.data)
            if(not m):
                print("Couldn't parse IRA: ",q.data, end=' ', file=sys.stderr)
            else:
                q.sat=  int(m.group(1))
                q.beam= int(m.group(2))
                if m.group(3) is not None:
                    q.xyz= [4*int(m.group(3)), 4*int(m.group(4)), 4*int(m.group(5))]
                q.lat=float(m.group(6))
                q.lon=float(m.group(7))
                q.alt=  int(m.group(8))
                if m.group(9) is not None:
                    p=re.compile(r'PAGE\(tmsi:([0-9a-f]+) msc_id:([0-9]+)\)')
                    q.pages=p.findall(m.group(9))
                else: # Won't be printed, but just in case
                    q.pages=[]
                return q
    def process(self,q):
        q.enrich()
        strtime = dt.epoch(q.time).isoformat(timespec='centiseconds')
        for x in q.pages:
            return ["%s %03d %02d %6.2f %6.2f %03d : %s %s"%(strtime, q.sat,q.beam,q.lat,q.lon,q.alt,x[0],x[1])]
    def consume(self,q):
        print(q, file=outfile)

modes=[
["page",       ReassembleIRA,  ],
]
