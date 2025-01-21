#!/usr/bin/env python3
# vim: set ts=4 sw=4 tw=0 et pm=:

import sys
import datetime
import re
import struct
import math
import os
import socket
import numpy as np
from copy import deepcopy
from util import fmt_iritime, to_ascii, slice_extra, dt

from .base import *
from ..config import config, outfile

SECOND = np.timedelta64(1, 's')

class ReassemblePPM(Reassemble):
    def __init__(self):
        self.idx=None
        pass

    r1=re.compile(r'.* slot:(\d)')
    r2=re.compile(r'.* time:([0-9:T-]+(?:\.\d+)?)Z')

    def filter(self,line):
        q=super().filter(line)
        if q==None: return None
        if q.typ!="IBC:": return None

        q.enrich()
        if q.confidence<95: return None

        if 'perfect' in config.args:
            if not q.perfect: return None

        m=self.r1.match(q.data)
        if not m: return
        q.slot=int(m.group(1))

        m=self.r2.match(q.data)
        if not m: return
        q.itime = np.datetime64(m.group(1))
        return q

    def process(self,q):
        q.uxtime = np.datetime64(int(q.starttime), 's')
        q.uxtime += np.timedelta64(q.nstime, 'ns')

        # correct for slot:
        # 1st vs. 4th slot is 3 * (downlink + guard)
        q.itime += np.timedelta64(q.slot*(3 * (8280 + 100)), 'us')

        # correct to beginning of frame:
        # guard + simplex + guard + 4*(uplink + guard) + extra_guard
        q.itime += np.timedelta64(1000 + 20320 + 1240 + 4 * (8280 + 220) + 20, 'us')

        # correct to beginning of signal:
        # our timestamp is "the middle of the first symbol of the 12-symbol BPSK Iridium sync word"
        # so correct for 64 symbols preamble & one half symbol.
        q.itime += np.timedelta64(64500//25, 'us')

        # no correction (yet?) for signal travel time: ~ 2.6ms-10ms (780-3000 km)

        return [[q.uxtime,q.itime,q.starttime]]

    ini=None
    def consume(self, data):
        tdelta = (data[0]-data[1]) / SECOND
        if self.ini is None: # First PKT
            self.idx=0
            self.ini=[data]
            self.fin=[data]
            self.cur=data
            self.tmin=tdelta
            self.tmax=tdelta
        if data[2]!=self.ini[self.idx][2]: # New Recording
            self.idx += 1
            self.ini.append(data)
            self.fin.append(data)
            self.cur=data
        self.fin[-1]=data

        if tdelta < self.tmin:
            self.tmin=tdelta
        if tdelta > self.tmax:
            self.tmax=tdelta
        if 'tdelta' in config.args:
            print("tdelta %sZ %f"%(data[0], tdelta))

        # "interactive" statistics per INVTL(600)
        if (data[1]-self.cur[1]) / SECOND > 600:
            (irun,toff,ppm)=self.onedelta(self.cur,data, verbose=False)
            if 'grafana' in config.args:
                print("iridium.live.ppm %.5f %d" % (ppm, data[1].astype('datetime64[s]').astype(np.int64)))
                sys.stdout.flush()
            else:
                print("@ %s: ppm: % 6.3f ds: % 8.5f "%(data[1], ppm, (data[1]-data[0]) / SECOND))
            self.cur=data
        elif (data[1]-self.cur[1]) / SECOND < 0:
            self.cur=data

    def onedelta(self, start, end, verbose=False):
        irun = (end[1]-start[1]) / SECOND
        urun = (end[0]-start[0]) / SECOND
        toff=urun-irun
        if irun==0: return (0,0,0)
        ppm=toff/irun*1000000
        if verbose:
            print("Blob:")
            print("- Start Itime  : %s"%(start[1]))
            print("- End   Itime  : %s"%(end[1]))
            print("- Start Utime  : %s"%(start[0]))
            print("- End   Utime  : %s"%(end[0]))
            print("- Runtime      : %s"%(str(datetime.timedelta(seconds=int(irun)))))
            print("- PPM          : %.3f"%(ppm))
        return (irun,toff,ppm)

    def end(self):
        alltime=0
        delta=0
        if self.idx is None: return
        for ppms in range(1+self.idx):
            (irun,toff,ppm)=self.onedelta(self.ini[ppms],self.fin[ppms], verbose=True)
            alltime += irun
            delta += toff
        print("rec.tmin %f"%(self.tmin))
        print("rec.tmax %f"%(self.tmax))
        print("rec.ppm %.3f"%(delta/alltime*1000000))

modes=[
["ppm",        ReassemblePPM,         ('perfect','grafana','tdelta') ],
]
