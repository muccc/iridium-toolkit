#!/usr/bin/env python3
# vim: set ts=4 sw=4 tw=0 et pm=:

import re
import datetime

from .base import *
from ..config import config, outfile, state

ft=['IBC', 'IDA', 'IIP', 'IIQ', 'IIR', 'IIU', 'IMS', 'IRA', 'IRI', 'ISY', 'ITL', 'IU3', 'I36', 'I38', 'MSG', 'VDA', 'VO6', 'VOC', 'VOD', 'MS3', 'VOZ', 'IAQ', 'NXT']

class StatsPKT(Reassemble):
    stats={}

    def __init__(self):
        for k in ['UL', 'DL', 'perfect']:
            self.stats[k]={}
            for x in ft:
                self.stats[k][x]=0
        del self.stats['UL']['ITL']
        del self.stats['UL']['IMS']
        del self.stats['UL']['MSG']
        del self.stats['UL']['MS3']
        del self.stats['DL']['IAQ']
        pass

    def filter(self,line):
        q=super().filter(line)

        if q==None: return None
        if q.typ[3]!=":": return None
        if q.typ=="RAW:": return None
        if q.typ=="IME:": return None
        return q

    def process(self,q):
        typ=q.typ[0:3]
        self.stats[q.uldl][typ]+=1
        if q.uldl == 'DL' and q.name.endswith("-e000"):
            self.stats["perfect"][typ]+=1
        return None

    def end(self):
        total=0
        perfect=0
        uplink=0
        downlink=0
        for t in ft:
            if t in self.stats["DL"]:
                print("%7d good.%s"%(self.stats["DL"][t],t))
                downlink+=self.stats["DL"][t]
                total+=self.stats["DL"][t]
                print("%7d perfect.%s"%(self.stats["perfect"][t],t))
                perfect+=self.stats["perfect"][t]
            if t in self.stats["UL"]:
                print("%7d uplink.%s"%(self.stats["UL"][t],t))
                uplink+=self.stats["UL"][t]
                total+=self.stats["UL"][t]

        print("%7d total.parsed"%(total))
        print("%7d total.perfect"%(perfect))
        print("%7d total.downlink"%(downlink))
        print("%7d total.uplink"%(uplink))

class StatsECC(Reassemble):
    stats={}

    def __init__(self):
        self.r_uw=re.compile('-e[1-9][0-9][0-9]$')
        self.r_lcw=re.compile('-e0[1-9][0-9]$')
        self.r_fix=re.compile('-e00[1-9]$')
        self.r_ok=re.compile('-e000$')
        self.uw=0
        self.lcw=0
        self.fix=0
        pass

    def filter(self,line):
        q=super().filter(line)

        if q==None: return None
        if q.typ[3]!=":": return None
        if q.typ=="RAW:": return None
        if q.typ=="IME:": return None
        return q

    def process(self,q):
        if (self.r_uw.search(q.name)):
            self.uw+=1
        elif (self.r_lcw.search(q.name)):
            self.lcw+=1
        elif (self.r_fix.search(q.name)):
            self.fix+=1
        elif (self.r_ok.search(q.name)):
            pass
        else:
            raise Exception("No ECC info found: "+q.name)
        return None

    def end(self):
        print("%7d ecc.uniq_word"%(self.uw))
        print("%7d ecc.link_control_word"%(self.lcw))
        print("%7d ecc.content"%(self.fix))
#        print "%7d total.unparsed"%()

modes=[
["stats-pkt", StatsPKT,          ],
["stats-ecc", StatsECC,          ],
]
