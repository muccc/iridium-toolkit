#import numpy as np
import sys
import fileinput
import matplotlib.pyplot as plt
import datetime
import matplotlib.ticker as ticker
import traceback
from math import sqrt,sin,cos,atan2
import astropy # just to make sure it is there for pymap3d
import pymap3d
import numpy
import interp_circ
from skyfield.api import load, utc, Topos
#import iridium_next
from scipy.optimize import minimize, LbfgsInvHessProduct

debug = False
#tlefile='tracking/iridium-NEXT.txt'

# create input file like this:
# iridium-parser.py -p --filter=IridiumBCMessage+iri_time_ux --format=globaltime,iri_time_ux,slot,sv_id,beam_id > muccc-2020-07-17.ibc
# iridium-parser.py -p --filter=IridiumRAMessage,'q.ra_alt>7100' --format globaltime,ra_sat,ra_cell,ra_alt,ra_pos_x,ra_pos_y,ra_pos_z > muccc-2020-07-17.ira

class InterpException(Exception):
    pass

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


xs=[]
ys=[]
cs=[]

ibc=open(sys.argv[1])
ira=open(sys.argv[2])

maxsat=127

def loadTLE(filename):
    satlist = load.tle_file(filename)
    print("%i satellites loaded into list"%len(satlist))
    return satlist

#satellites = loadTLE(tlefile)
#timescale=load.timescale()
#by_name = {sat.name: sat for sat in satellites}


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
        tu = float(tu)
        #print(ppm)
        #tu = float(tu) * (1-ppm/1e6)

        #dist=sqrt( (x-ox)**2+ (y-oy)**2+ (y-oz)**2)
        #dist_s=float(dist) / 299792458
        #tu -= dist_s

        x, y, z = pymap3d.ecef2eci(x, y, z, datetime.datetime.utcfromtimestamp(tu))

        ira_xyzt[s].append([x,y,z,tu])


satidx=[0]*maxsat
osatidx=[0]*maxsat

#tmax=500
tmax=60
#tmax=30

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
    if delta > 2000:
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
    xyz[0], xyz[1], xyz[2] = pymap3d.eci2ecef(xyz[0], xyz[1], xyz[2], datetime.datetime.utcfromtimestamp(ts))
    return xyz

ppm = 0

read_ira()

xyz=None
t0=None
t0i = None

for line in ibc:
    tu,ti,slot,s,b=line.split(None,5) # time_unix, time_iridium, slot, sat, beam

    slot=int(slot)
    s=int(s)
    tu=float(tu)
    ti=float(ti)

    # time correction based on BC slot
    if slot==1:
        ti+=3 * float(8.28 + 0.1)/1000

    # ppm correction
    if t0 is None:
        t0=tu

    if t0i is None:
        t0i=ti

    tu=tu-(tu-t0)*ppm/1e6

    try:
        xyz = [0,0,0]
        xyz=interp_ira(s, tu)
        #xyz=interp_ira(s, ti)
    except InterpException as e:
        print("Error:",repr(e))
        continue

    ys.append((s, numpy.array(xyz), tu-ti, tu))

    #print(s, xyz, tu-ti, tu)

    xs.append(tu-t0)
    cs.append(s)

print("Average delay to system time:", numpy.average([y[2] for y in ys]))

def dist(a, b):
    return numpy.linalg.norm(a-b)

def cost_function(approx, measurements):
    """
    Cost function for the 3D problem

    Based on code from https://github.com/AlexisTM/MultilaterationTDOA
    TODO: Use weighed least square cost function
    """
    e = 0
    for mea in measurements:
        error = mea[2] - (dist(mea[1], approx) - dist(mea[0], approx))
        e += error**2

    #print("cost", approx, measurements, "->", e)
    return e


def solve(measurements, last_result):
    """Optimize the position for LSE using in a 3D problem."""
    approx = last_result
    result = minimize(cost_function, approx, args=(measurements))
    position = result.x

    #if(type(result.hess_inv) == LbfgsInvHessProduct):
    #    hess_inv = result.hess_inv.todense()
    #else:
    #    hess_inv = result.hess_inv
    #dist = self.scalar_hess_squared(hess_inv)
    #if dist < self.max_dist_hess_squared:
    #    self.last_result = position

    last_result = position
    #return position, hess_inv
    return position


good = []
errors = []
height_errors = []
bad = 0
known_bad = 0
last_result = numpy.array([0, 0, 0])

last_observation = {}
for o in ys:
    last_observation[o[0]] = o

    tu = o[3]

    # Find all SVs which we saw in the last 10 seconds
    concurent_observation = {}
    for lo in last_observation.values():
        if tu - lo[3] < 10:
            concurent_observation[lo[0]] = lo

    # If we have more than 3, try to solve
    if len(concurent_observation) > 3:
        measurements = []

        svs = list(concurent_observation.keys())
        ref_sv = svs[0]
        for sv in svs[1:]:
            measurements.append(
                (
                    concurent_observation[ref_sv][1], # Position of reference SV
                    concurent_observation[sv][1], # Position of second SV
                    (concurent_observation[sv][2] - concurent_observation[ref_sv][2]) * 299792458.) # Distance delta
                )

        # Sometimes it needs a few iterations to converge
        result = last_result
        for i in range(4):
            result = solve(measurements, result)

        # Make sure we are not in space or inside the earth
        height = numpy.linalg.norm(result)
        if abs(height - 6372e3) > 100e3:
            known_bad += 1
            continue

        last_result = result
        error = numpy.linalg.norm(result - observer)
        height_error = numpy.linalg.norm(result) - numpy.linalg.norm(observer)
        print("Error:", int(error), "(", int(height_error), ")", result)

        if error < 10000:
            good.append(result)
            errors.append(error)
            height_errors.append(height_error)
        else:
            bad += 1

print("good", len(good), "bad", bad, "known_bad", known_bad)

print("average error:", numpy.average(errors), "(", numpy.average(height_error), ")")

average_position = numpy.average(good, 0)

print("average position:", average_position)
print("average position error:", numpy.linalg.norm(average_position - observer))
print("average position height error:", numpy.linalg.norm(average_position) - numpy.linalg.norm(observer))


lat, lon, alt = pyproj.transform(ecef, lla, average_position[0], average_position[1], average_position[2], radians=False)


print("average position", lon, lat, alt)
