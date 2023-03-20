#!/usr/bin/env python3
# vim: set ts=4 sw=4 tw=0 et pm=:

import sys
import datetime
import re
import math

from .base import *
from ..config import config, outfile

class StatsSNR(Reassemble):
    def __init__(self):
        self.stats={}
        pass

    def filter(self,line):
        q=super().filter(line)

        if q==None: return None
        if q.typ[3]!=":": return None
        if q.typ=="RAW:": return None
        if q.typ=="IME:": return None

        q.enrich()

        if 'perfect' in config.args:
            if not q.perfect: return None

        return q

    def process(self,q):
        typ=q.typ[0:3]

        if typ not in self.stats:
            self.stats[typ]={}
            for x in ['cnt', 'ncnt', 'scnt', 'signal', 'snr', 'noise', 'confidence', 'symbols', 'frequency']:
                self.stats[typ][x]=0

        self.stats[typ]["cnt"]+=1
        if q.snr is not None:
            self.stats[typ]["snr"]+=pow(10,q.snr/20)
            self.stats[typ]["noise"]+=pow(10,q.noise/20)
            self.stats[typ]["ncnt"]+=1

        if q.level > 0 or math.isnan(q.level): # Invalid signal level
            pass
        else:
            self.stats[typ]["signal"]+=pow(10,q.level/20)
            self.stats[typ]["scnt"]+=1

        self.stats[typ]["confidence"]+=q.confidence
        self.stats[typ]["symbols"]+=int(q.symbols)
        self.stats[typ]["frequency"]+=q.frequency
        return None

    def consume(self,to):
        pass

    def end(self):
        totalc=0
        totalcs=0
        totalcn=0
        for t in self.stats:
            totalc+=self.stats[t]["cnt"]
            totalcs+=self.stats[t]["scnt"]
            totalcn+=self.stats[t]["ncnt"]
#        print "%d %s.%s"%(totalc,"total","cnt")

        if totalc == 0: return
        for x in self.stats["IDA"]:
            totalv=0
            for t in self.stats:
                if x == "ncnt": continue
                if x == "scnt": continue
                if x == "cnt":
#                    print "%d %s.%s"%(self.stats[t]["cnt"],"cnt",t)
                    continue
                totalv+=self.stats[t][x]
                # ignore packet types with less than 0.01% of total volume
                if float(self.stats[t]["cnt"])/totalc > 0.0001 and self.stats[t][x]!=0:
                    if x in ["signal"]:
                        if self.stats[t]["scnt"] > 0:
                            print("%f %s.%s"%(20*math.log(float(self.stats[t][x])/self.stats[t]["scnt"],10),x,t))
                    elif x in ["snr","noise"]:
                        if self.stats[t]["ncnt"] > 0:
                            print("%f %s.%s"%(20*math.log(float(self.stats[t][x])/self.stats[t]["ncnt"],10),x,t))
                    elif x in ["frequency"]:
                        print("%10d %s.%s"%(self.stats[t][x]/self.stats[t]["cnt"],x,t))
                    else:
                        print("%f %s.%s"%(float(self.stats[t][x])/self.stats[t]["cnt"],x,t))
            if totalv !=0:
                if x in ["signal"]:
                    if totalcs > 0:
                        print("%f %s.%s"%(20*math.log(float(totalv)/totalcs,10),"total",x))
                elif x in ["snr","noise"]:
                    if totalcn > 0:
                        print("%f %s.%s"%(20*math.log(float(totalv)/totalcn,10),"total",x))
                elif x in ["frequency"]:
                    print("%10d %s.%s"%(totalv/totalc,"total",x))
                else:
                    print("%f %s.%s"%(float(totalv)/totalc,"total",x))
        for n,tl in (
                ('MS', ['IMS', 'MSG', 'MS3']),
                ('TL', ['ITL']),
                ('BC', ['IBC']),
                ('LW', ['IDA', 'IIP', 'IIQ', 'IIR', 'IIU', 'IRI', 'ISY', 'IU3', 'I36', 'I38', 'VDA', 'VO6', 'VOC', 'VOD', 'VOZ']),
                ('RA', ['IRA']),
                ('NP', ['INP']),
                ):
            ct=0
            freq=0
            for t in tl:
                if t in self.stats:
                    ct+=self.stats[t]["cnt"]
                    freq+=self.stats[t]["frequency"]
            if ct>0:
                print("%10d freq.%s"%(freq/ct,n))

modes=[
["stats-snr",  StatsSNR,              ('perfect') ],
]
