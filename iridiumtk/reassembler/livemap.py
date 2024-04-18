#!/usr/bin/env python3
# vim: set ts=4 sw=4 tw=0 et pm=:

import sys
import datetime
import re
import os
from copy import deepcopy

from .base import *
from ..config import config, outfile

class LiveMap(Reassemble):
    intvl=60
    exptime=60*8
    timeslot=-1

    def __init__(self):
        global json
        import json
        self.positions={}
        self.ground={}
        self.topic="IRA"
        if config.stats:
            from util import curses_eol
            global eol
            eol=curses_eol()
        pass

    r2=re.compile(r' *sat:(\d+) beam:(\d+) (?:xyz=\S+ )?pos=.([+-][0-9.]+)\/([+-][0-9.]+). alt=(-?\d+).*')

    def filter(self,line):
        q=super().filter(line)

        if q==None: return None
        if q.typ!="IRA:": return None

        q.enrich()

        if 'perfect' in config.args:
            if not q.perfect: return None

        return q

    def process(self,q):
        # Parse out IRA info
        m=self.r2.match(q.data)
        if not m: return None
        q.sat=  int(m.group(1))
        q.beam= int(m.group(2))
        q.lat=float(m.group(3))
        q.lon=float(m.group(4))
        q.alt=  int(m.group(5))

        rv=None
        maptime=q.time-(q.time%self.intvl)

        if maptime > self.timeslot:
            # expire
            for sat in self.positions:
                eidx=0
                for idx,el in enumerate(self.positions[sat]):
                    if el['time']+self.exptime < q.time:
                        eidx=idx+1
                    else:
                        break
                del self.positions[sat][:eidx]
            for sat in self.ground:
                eidx=0
                for idx,el in enumerate(self.ground[sat]):
                    if el['time']+self.exptime/2 < q.time:
                        eidx=idx+1
                    else:
                        break
                del self.ground[sat][:eidx]

            #cleanup
            for sat in list(self.positions.keys()):
                if len(self.positions[sat])==0:
                    del self.positions[sat]
            for sat in list(self.ground.keys()):
                if len(self.ground[sat])==0:
                    del self.ground[sat]

            # send to output
            if self.timeslot is not None:
                rv=[[self.timeslot, { "sats": deepcopy(self.positions), "beam": deepcopy(self.ground)}]]
            self.timeslot=maptime

        if q.sat not in self.positions:
            self.positions[q.sat]=[]

        if q.sat not in self.ground:
            self.ground[q.sat]=[]

        if q.alt>700 and q.alt<850: # Sat positions
            dupe=False
            if len(self.positions[q.sat])>0:
                lastpos=self.positions[q.sat][-1]
                if lastpos['lat']==q.lat and lastpos['lon']==q.lon:
                    dupe=True
            if not dupe:
                self.positions[q.sat].append({"lat": q.lat, "lon": q.lon, "alt": q.alt, "time": q.time})
        elif q.alt<100: # Ground positions
            self.ground[q.sat].append({"lat": q.lat, "lon": q.lon, "alt": q.alt, "beam": q.beam, "time": q.time})

        return rv

    def printstats(self, timeslot, stats):
        ts=timeslot+self.intvl
        if config.stats:
            sts=datetime.datetime.fromtimestamp(ts)
            sats=len(stats['sats'])
            ssats=", ".join([str(x) for x in sorted(stats['sats'])])
            beams=0
            for b in stats['beam']:
                beams+=len(set([x['beam'] for x in stats['beam'][b]]))
            print("%s: %d sats {%s}, %d beams"%(sts,sats,ssats,beams), end=eol, file=sys.stderr)
        else:
            print("# @ %s L:"%(datetime.datetime.fromtimestamp(ts)), file=sys.stderr)
        stats["time"]=ts

        ofile=config.output
        if ofile is None:
            ofile="sats.json"
        temp_file_path="%s.tmp"%(ofile)
        with open(temp_file_path, "w") as f:
            print(json.dumps(stats, separators=(',', ':')), file=f)
        os.rename(temp_file_path, ofile)

    def consume(self,to):
        (ts,stats)=to
        self.printstats(ts, stats)

    def end(self):
        self.printstats(self.timeslot, {"sats": self.positions, "beam": self.ground} )

modes=[
["live-map",   LiveMap,               ('perfect') ],
]
