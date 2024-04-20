#!/usr/bin/env python3
# vim: set ts=4 sw=4 tw=0 et pm=:

import sys
import datetime
from util import dt

from .base import *
from .ira import ReassembleIRA
from ..config import config, outfile

class InfoIRAMAP(ReassembleIRA):
    satlist=None
    sats={}
    ts=None
    first=True
    MAX_DIST=100 # Maximum distance in km for a match to be accepted
    stats_cnt=0
    stats_sum=0

    def __init__(self):
        global load, utc, Topos
        global TEME_to_ITRF, SatrecArray, angle_between, length_of, tau, DAY_S
        global np
        from skyfield.api import load, utc, Topos
        from skyfield.sgp4lib import TEME_to_ITRF
        from sgp4.api import SatrecArray
        from skyfield.functions import angle_between, length_of
        from skyfield.constants import tau, DAY_S
        import numpy as np

        filename="tracking/iridium-NEXT.txt"
        self.satlist = load.tle_file(filename)
        if config.verbose:
            print(("%i satellites loaded into list"%len(self.satlist)))
        self.epoc = self.satlist[0].epoch
        self.ts=load.timescale(builtin=True)

        if config.verbose:
            tnow = self.ts.utc(datetime.datetime.now(datetime.timezone.utc))
            days = tnow - self.epoc
            print('TLE file is %.2f days old'%days)

    def filter(self,line):
        q=super().filter(line)
        if q is None: return None
        if q.alt < 100: return None
        q.enrich()
        return q

    def find_closest_satellite(self, t, xyz, satlist):
        a = SatrecArray([sat.model for sat in satlist])
#        jd = np.array([t._utc_float()]) # skyfield 1.2x or so....
        jd = np.array([t.whole + t.tai_fraction - t._leap_seconds() / DAY_S])
        e, r, v = a.sgp4(jd, jd * 0.0)

        r = r[:,0,:]  # eliminate t axis since we only have one time
        v = v[:,0,:]
        r = r.T       # move x,y,z to top level like Skyfield expects
        v = v.T

        ut1 = np.array([t.ut1])
        r, v = TEME_to_ITRF(ut1, r, v)

        r2=np.array(xyz)
        r2.shape = 3, 1  # add extra dimension to stand in for time

#        sep_a = angle_between(r, r2)
        sep_d = length_of(r-r2)

        i = np.argmin(sep_d)

        closest_satellite = satlist[i]
#        closest_angle = sep_a[i] / tau * 360.0
        closest_distance = sep_d[i]

        if False:
            print("Position:",xyz,"at",t.utc_strftime(),":")
            for idx,s in enumerate(sorted(satlist, key=lambda sat: sat.name)):
                print("  %s: %8.2fkm %s"%(s.name,sep_d[idx],["","*"][i==idx]))

        return closest_satellite, closest_distance

    def process(self,q):
        time = dt.epoch(q.time)
        t = self.ts.utc(time)
        if self.first:
            self.first=False
            days = t - self.epoc
            if abs(days)>3:
                print('WARNING: TLE relative age is %.2f days. Expect poor results.'%abs(days), file=sys.stderr)
            elif config.verbose:
                print('TLE relative age is %.2f days'%abs(days))

        if "xyz" not in q.__dict__: # Compat for old parsed files
            alt=int(q.alt)*1000
            sat= Topos(latitude_degrees=q.lat, longitude_degrees=q.lon, elevation_m=alt)
            q.xyz= sat.itrf_xyz().km

        (best,sep)=self.find_closest_satellite(t, q.xyz, self.satlist)

        q.name=best.name
        q.sep=sep

        return [q]

    def consume(self,q):
        if config.verbose:
            #print("%s: sat %02d beam %02d [%d %8.2f %8.2f %s] matched %-20s @ %5.2f°" %
            print("%s: sat %02d beam %02d [%d %8.4f %8.4f %s] matched %-20s @ %5fkm" %
                  (dt.epoch(q.time), q.sat, q.beam, q.time, q.lat, q.lon, q.alt, q.name, q.sep))

        if q.sep > self.MAX_DIST:
            q.name="NONE"
        if not q.sat in self.sats:
            self.sats[q.sat]={}
        if not q.name in self.sats[q.sat]:
            self.sats[q.sat][q.name]=0
        self.sats[q.sat][q.name]+=1
        if q.name=="NONE":
            return
        self.stats_cnt+=1
        self.stats_sum+=q.sep

    def end(self):
        for x in sorted(self.sats):
            sum=0
            for n in sorted(self.sats[x]):
                sum+=self.sats[x][n]

            for n in sorted(self.sats[x]):
                print("%03d seen: %5d times - matched to %-20s %5.1f%%"%(x,sum,n,self.sats[x][n]/float(sum)*100))

        if self.stats_cnt==0:
            print("No matches. Wrong input file?")
        else:
            print("%d matches. Avg distance: %5.2fkm"%(self.stats_cnt,self.stats_sum/self.stats_cnt))

modes=[
["satmap",     InfoIRAMAP,  ],
]
