#!/usr/bin/env python
# vim: set ts=4 sw=4 tw=0 et fileencoding=utf8 pm=:
import sys
import matplotlib.pyplot as plt
import pyorbital
from pyorbital import orbital
from pyorbital import tlefile
from datetime import datetime
import sats
import math
import time
import re
import sqlite3



verbose= False
if sys.argv[1]=="-v":
    verbose=True
    sys.argv[1:]=sys.argv[2:]

degrees_per_radian = 180.0 / math.pi
radian_per_degree = math.pi / 180.0

mu= 398600        # Standard gravitational parameter for the earth
R0= 6378.137      # Earth equatorial radius
J2= 0.00108262668 # Earth second dynamic form factor

# "ideal" iridium sat - used for "plane" calculations
inc0=86.4    # From Wikipedia
e0=1.069e-3  # excentricity (could be assumed 0)
n=14.336     # Mean motion [Revs per day]

# https://en.wikipedia.org/wiki/Nodal_precession
a= (mu/(n*2*math.pi/(24*3600))**2)**(1./3) # Semi-major axis [km]
omega= n*2*math.pi/60/60/24                # angular frequency
omega_p= -3./2.*((R0**2)/((a*(1-e0**2))**2))*J2*omega*math.cos(math.radians(inc0))
#print "a=",a
#print "omega_p=",omega_p/math.pi*180 *60*60*24

conn = sqlite3.connect("tle/space-track.sqlite3")
c = conn.cursor()

def getdata(satnum):
    c.execute('SELECT EPOCH,TLE_LINE0,TLE_LINE1,TLE_LINE2,FILE FROM DATA WHERE NORAD_CAT_ID = {satnum} ORDER BY EPOCH'.format(satnum=satnum));
    all_rows= c.fetchall()

    if len(all_rows)==0:
        print "Sat ",satname," not found"
        exit(1)
    data=[]
    print "[%5d] %s (%s-%s) latest=%s"%(satnum,all_rows[0][1][2:],all_rows[0][0],all_rows[-1][0],all_rows[-1][4])
    for line in all_rows:
        ep,l0,l1,l2,file=line
        tle=tlefile.read(ep, line1=l1,line2=l2)
        dt=datetime.strptime(ep,"%Y-%m-%d %H:%M:%S")
        inc=tle.inclination
        raan=tle.right_ascension # Right Ascension of the Ascending Node [deg]
        e=tle.excentricity       # (Ra-Rp)/(Ra+Rp)
        w=tle.arg_perigee        # Argument of periapsis [deg]
        n=tle.mean_motion        # Mean motion [Revs per day]
        Sm=(mu/(n*2*math.pi/(24*3600))**2)**(1./3) # Semi-major axis [km]
        Ra=e*Sm+Sm               # Apogee (farthest point)
        Rp=-e*Sm+Sm              # Perigree (nearest point)
        raan_off= (tle.epoch-datetime.strptime("1996", "%Y")).total_seconds()*1
        plane=(raan-raan_off*omega_p/math.pi*180)%360

        if verbose:
            print "time:",ep
            print "Sm  [km]:",Sm
            print "Ra  [km]:",Ra-R0
            print "Rp  [km]:",Rp-R0
            print "e       :",e
            print "inc  [°]:",inc
            print "RAAN [°]:",raan
            print "w    [°]:",w
            print "B*      :",tle.bstar
            print "plane[°]:",plane
            print ""
        if raan>180: raan-=360
        if plane>180: plane-=360
        data.append((dt, inc, Sm-R0, plane, e, w, raan, Ra-R0, Rp-R0, tle.bstar))
    return data

if len(sys.argv)==0:
    print "Need argument."
    exit(1)

numplot=len(sys.argv[1:])

titles= ['Time','Inclination','Altitude','Plane','Excentricity', 'Periapsis','RAAN','Apogee','Perigree','B*']
yplots= [1,2,4,3,9]

f, axarr= plt.subplots(len(yplots), sharex=True)

for satname in sys.argv[1:]:
    try:
        satnum=int(satname)
    except:
        c.execute('SELECT NORAD_CAT_ID from SATS where SATNAME = "{name}";'.format(name=satname));
        sats=c.fetchall()
        satnum=sats[0][0]
    
    data=getdata(satnum)

    for n,t in enumerate(yplots):
        axarr[n].plot([v[0] for v in data], [v[t] for v in data],'-',label=satname)

for n,t in enumerate(yplots):
    axarr[n].set_title(titles[t])

axarr[0].legend(bbox_to_anchor=(1.01, 1), loc=2, borderaxespad=0.)
#plt.legend(bbox_to_anchor=(0.05, -0.10), ncol=6, loc=2, borderaxespad=0.)

plt.subplots_adjust(left=0.05, right=0.9, top=0.95, bottom=0.05)
plt.show()
