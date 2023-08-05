#!/usr/bin/env python3
# vim: set ts=4 sw=4 tw=0 et pm=:

import sys
import re

from .base import *
from ..config import config, outfile

class InfoITLSatMap(Reassemble):
    def __init__(self):
        self.itl=None
        self.ira=None
        self.store= {}
        pass
    def filter(self,line):
        q=super().filter(line)
        if q==None: return None
        if q.typ!="IRA:" and q.typ!="ITL:": return None
        if q.typ=="IRA:":
            p=re.compile(r'sat:(\d+) beam:(\d+)')
            m=p.search(q.data)
            if(not m):
                print("Couldn't parse IRA: ",q.data, end=' ', file=sys.stderr)
                return None
            else:
                q.enrich(True)
                q.sat=  int(m.group(1))
                q.beam= int(m.group(2))
                self.ira=q
        elif q.typ=="ITL:":
            p=re.compile(r'V[12] OK(?:\[\d\])? P(\d+) (?:---|R\d\d|S(\d+)) ')
            m=p.search(q.data)
            if(not m):
                print("Couldn't parse ITL: ",q.data, end=' ', file=sys.stderr)
                return None
            elif m.group(2) is None:
                return None
            else:
                q.enrich(True)
                q.plane= int(m.group(1))
                q.satno= int(m.group(2))
                self.itl=q

        if self.itl is None or self.ira is None:
            return None

        if abs(self.itl.mstime - self.ira.mstime)<0.01:
            df=self.ira.frequency-self.itl.frequency
            if config.verbose:
                print("Match: delta_f=%d"%df)
                print("- IRA",self.ira.mstime,self.ira.frequency,self.ira.freq_print,self.ira.sat)
                print("- ITL",self.itl.mstime,self.itl.frequency,self.itl.freq_print,"P%dS%02d"%(self.itl.plane,self.itl.satno))
            if abs(df-(4*channel_width))<300:
                q=MyObject()
                q.sat=self.ira.sat
                q.plane=self.itl.plane
                q.itlsatno=self.itl.satno
                return q

        return None

    def process(self,q):
        ps="P%dS%02d"%(q.plane,q.itlsatno)
        if ps not in self.store:
            self.store[ps]={}
        if q.sat not in self.store[ps]:
            self.store[ps][q.sat]=0
        self.store[ps][q.sat]+=1


    def consume(self,q):
        raise Exception("unreachable")

    def end(self):
        print("Iridium satellite ordering (using iridium-internal identifiers)")
        print("")
        print("        ",end=' ')
        for x in range(1,12):
            print("%3d"%x,end=' ')
        print("")

        for plane in range(1,7):
            print("Plane %d:"%plane,end=' ')
            for idx in range(1,12):
                i="P%dS%02d"%(plane,idx)

                _sum=0
                _max=0
                maxname=None
                try:
                    for sat,count in self.store[i].items():
                        _sum+=count
                        if count > _max:
                            maxname=sat
                            _max=count
                    conf=_max*100/_sum
                except KeyError:
                    maxname="?"
                    conf=100

                if conf<98:
                    print("%3s(%2d%%)"%(maxname,conf),end=' ')
                else:
                    print("%3s"%(maxname),end=' ')
            print("")

modes=[
["itlmap",     InfoITLSatMap,  ],
]
