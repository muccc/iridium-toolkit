#!/usr/bin/env python3
# vim: set ts=4 sw=4 tw=0 et pm=:

import re
import sys
import datetime

from .base import *
from ..config import config, outfile, state

class StatsIRI(Reassemble):
    stats={}

    def __init__(self):
        for x in ['VO', 'TL', 'DA', 'BC', 'IP', 'MS', 'U3', 'U4', 'U5', 'U6']:
                self.stats[x]=0
        pass

    def filter(self,line):
        q=super().filter(line)

        if q==None: return None
        if q.typ!="IRI:": return None

        p=re.compile(r'(?:^|.* )([A-Z0-9][A-Z0-9]) \[')
        m=p.match(q.data)
        if(not m):
            print("Couldn't parse IRI: ",q.data, file=sys.stderr)
            return None
        q.subtype = m.group(1)

        return q

    def process(self,q):
        self.stats[q.subtype]+=1
        return None

    def end(self):
        total=0
        perfect=0
        uplink=0
        downlink=0
        for t in self.stats:
            tsum=self.stats[t]
            total+=tsum
            print("%7d iri.%s"%(tsum,t))
        print("%7d iri.total"%(total))

modes=[
["stats-iri", StatsIRI,          ],
]
