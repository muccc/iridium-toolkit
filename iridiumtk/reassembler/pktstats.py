#!/usr/bin/env python3
# vim: set ts=4 sw=4 tw=0 et pm=:

import sys
import datetime
from copy import deepcopy
from util import dt

from .base import *
from ..config import config, outfile, state

class LivePktStats(Reassemble):
    intvl=600
    timeslot=-1
    default=None
    stats={}
    first=True
    loaded=False

    def __init__(self):
        if state is not None:
            (self.timeslot,self.stats)=state
            self.loaded=True
            self.first=False
        self.default={}
        for k in ['UL', 'DL']:
            self.default[k]={}
            for x in ['IBC', 'IDA', 'IIP', 'IIQ', 'IIR', 'IIU', 'IMS', 'IRA', 'IRI', 'ISY', 'ITL', 'IU3', 'I36', 'I38', 'MSG', 'VDA', 'VO6', 'VOC', 'VOD', 'MS3', 'VOZ', 'IAQ', 'NXT']:
                self.default[k][x]=0
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
        maptime=q.time-(q.time%self.intvl)
        typ=q.typ[0:3]
        rv=None

        if maptime > self.timeslot:
            # dump last time interval
            if self.loaded:
                print("# Statefile (%s) not relevant to current file: %s"%(self.timeslot,maptime), file=sys.stderr)
                sys.exit(1)
            if self.timeslot is not None:
                if self.first:
                    print("# First period may be incomplete, skipping.", file=sys.stderr)
                    self.first=False
                    rv=[[self.timeslot,self.stats,True]]
                else:
                    rv=[[self.timeslot,self.stats,False]]
            # reset for next slot
            self.timeslot=maptime
            self.stats=deepcopy(self.default)

        self.loaded=False

        if maptime == self.timeslot:
            if typ not in self.stats['UL']:
                print("Unexpected frame %s found @ %s"%(typ,q.time), file=sys.stderr)
                pass
            self.stats[q.uldl][typ]+=1
        else:
            print("Time ordering violation: %f is before %f"%(q.time,self.timeslot), file=sys.stderr)
            sys.exit(1)
        return rv

    def printstats(self, timeslot, stats, skip=False):
        ts=timeslot+self.intvl
        comment=''
        if skip:
            comment='#!'
            print("#!@ %s L:"%(dt.epoch_local(ts)), file=sys.stderr)
        else:
            print("# @ %s L:"%(dt.epoch_local(ts)), file=sys.stderr)
        for k in stats:
            for t in stats[k]:
                print("%siridium.parsed.%s.%s %7d %8d"%(comment,k,t,stats[k][t],ts))
        sys.stdout.flush()

    def consume(self,to):
        (ts,stats,skip)=to
        self.printstats(ts, stats, skip=skip)

    def end(self):
        if 'state' in config.args:
            with open(statefile,'wb') as f:
                pickle.dump([self.timeslot,self.stats],f)

        self.printstats(self.timeslot, self.stats, skip=True)

modes=[
["live-stats", LivePktStats,          ('perfect','state') ],
]
