#!/usr/bin/env python3
import sys
import fileinput
import datetime
from math import sqrt,sin,cos,atan2
import astropy # just to make sure it is there for pymap3d
import pymap3d
import numpy
import interp_circ

#from skyfield.api import load, utc, Topos
#import iridium_next

debug = False
tlefile='tracking/iridium-NEXT.txt'
#tmax=500e9
tmax=60e9
#tmax=30e9
ppm = 0


# create input file like this:
# iridium-parser.py -p --filter=IridiumBCMessage+iri_time_ux --format=globalns,iri_time_ux,slot,sv_id,beam_id iridium.bits > iridium.ibc
# iridium-parser.py -p --filter=IridiumRAMessage,'q.ra_alt>7100' --format=globalns,ra_sat,ra_cell,ra_alt,ra_pos_x,ra_pos_y,ra_pos_z iridium.bits > iridium.ira

# call like this:
# python3 ibc_position_interpolator.py iridium.ibc iridium.ira > iridium.ibc_pos_interp
class InterpException(Exception):
    pass

"""
#https://stackoverflow.com/questions/30307311/python-pyproj-convert-ecef-to-lla
import pyproj
ecef = pyproj.Proj(proj='geocent', ellps='WGS84', datum='WGS84')
lla = pyproj.Proj(proj='latlong', ellps='WGS84', datum='WGS84')

# https://www.koordinaten-umrechner.de/decimal/48.153543,11.560702?karte=OpenStreetMap&zoom=19
lat=48.153543
lon=11.560702
alt=542

ox, oy, oz = pyproj.transform(lla, ecef, lon, lat, alt, radians=False)
observer = numpy.array((ox, oy, oz))

print("Observer:",lon,lat,alt)
print("Observer:",ox,oy,oz)
"""

ibc=open(sys.argv[1])
ira=open(sys.argv[2])

maxsat=127

def loadTLE(filename):
    satlist = load.tle_file(filename)
    print("%i satellites loaded into list"%len(satlist))
    return satlist

"""
satellites = loadTLE(tlefile)
timescale=load.timescale()
by_name = {sat.name: sat for sat in satellites}
"""

# initialize RA (position) array
ira_xyzt=[]
for p in range(maxsat):
    ira_xyzt.append([[0,0,0,0]])
ira_t=[0]*maxsat

def read_ira():
    while True:
        line=ira.readline()
        if len(line) == 0:
            return
        tu,s,b,alt,x,y,z=line.split(None,7) # time_unix, sat, beam, altitude, position(xyz)

        s=int(s)

        x = int(x) * 4000
        y = int(y) * 4000
        z = int(z) * 4000
        tu = int(tu)
        #print(ppm)
        #tu = float(tu) * (1-ppm/1e6)

        """
        #dist=sqrt( (x-ox)**2+ (y-oy)**2+ (y-oz)**2)
        #dist_s=float(dist) / 299792458
        #tu -= dist_s
        """

        x, y, z = pymap3d.ecef2eci(x, y, z, datetime.datetime.utcfromtimestamp(tu/1e9))
        ira_xyzt[s].append([x,y,z,tu])


satidx=[0]*maxsat
osatidx=[0]*maxsat

def interp_ira(sat, ts): # (linear) interpolate sat position
    global satidx,osatidx

    """
    # Option to interpolate based on TLEs
    geocentric = by_name[iridium_next.sv_map[sat]].at(timescale.utc(datetime.datetime.utcfromtimestamp(ts).replace(tzinfo=utc)))
    xyz = geocentric.position.m
    xyz[0], xyz[1], xyz[2] = pymap3d.eci2ecef(xyz[0], xyz[1], xyz[2], datetime.datetime.utcfromtimestamp(ts))
    return xyz
    """

    if ts > ira_xyzt[sat][satidx[sat]][3]:
        satidx[sat]=0

    if True or satidx[sat]==0:
        #print("Searching for sat %d..."%sat)
        osatidx[sat]=0
        for x in range(len(ira_xyzt[sat])):
            if osatidx[sat]==0 and ts-ira_xyzt[sat][x][3] < tmax:
                #print("` old=%d"%x, end=' ')
                osatidx[sat]=x
            if ira_xyzt[sat][x][3]-ts > tmax:
                #print("` new_exit=%d"%x)
                break
            satidx[sat]=x

    xyz=[None,None,None]

    idx=satidx[sat]
    idxo=osatidx[sat]

    tn=ira_xyzt[sat][idx][3]
    to=ira_xyzt[sat][idxo][3]
    delta=tn-to

    #print("Borders: %d -> %d"%(idxo, idx))
    #print("time %f -> %f: Δt: %f"%(to,tn,tn-to))

    # refuse to extrapolate
    if delta > 2000e9:
        raise InterpException("Too inaccurate (Δ=%d)"%(delta))
    if ts<to:
        raise InterpException("In the past")
    if ts>tn:
        raise InterpException("In the future")

    if idxo == idx:
        raise InterpException("Not enough data")


    step = 1
    T = [t for x,y,z,t in ira_xyzt[sat][idxo:idx+1:step]]
    X = [x for x,y,z,t in ira_xyzt[sat][idxo:idx+1:step]]
    Y = [y for x,y,z,t in ira_xyzt[sat][idxo:idx+1:step]]
    Z = [z for x,y,z,t in ira_xyzt[sat][idxo:idx+1:step]]

    if len(T) < 2:
        raise InterpException("Not enough data")

    xyz[0], xyz[1], xyz[2] = interp_circ.interp([X, Y, Z], T, ts, debug)
    xyz[0], xyz[1], xyz[2] = pymap3d.eci2ecef(xyz[0], xyz[1], xyz[2], datetime.datetime.utcfromtimestamp(ts/1e9))
    return xyz


read_ira()

xs=[]
ys=[]
cs=[]
t0=None

for line in ibc:
    tu,ti,slot,s,b=line.split(None,5) # time_unix, time_iridium, slot, sat, beam

    slot=int(slot)
    s=int(s)
    tu=int(tu)

    # Iridium timestamps ar in multiples of 90 ms.
    # First make an integer in ms, then bring it to ns
    ti=int(float(ti) * 1000) * 10**6

    # time correction based on BC slot
    # 8280 us per frame, 100 us for guard time
    if slot==1:
        ti+=3 * (8280 + 100) * 10**3

    # ppm correction
    if t0 is None:
        t0=tu

    tu=tu-(tu-t0)*ppm//10**6

    xyz = [0,0,0]
    try:
        xyz=interp_ira(s, tu)
        #xyz=interp_ira(s, ti)

        ys.append((tu, s, numpy.array(xyz), tu-ti))
        #xs.append(tu-t0)
        #cs.append(s)

        print(tu, s, xyz[0], xyz[1], xyz[2], tu-ti)

    except InterpException as e:
        #print("Warning:",repr(e))
        pass

print("Average delay to system time:", numpy.average([y[3] for y in ys]), file=sys.stderr)
