#!/usr/bin/env python3
import sys
import math
import time
from datetime import datetime,timezone,timedelta
from skyfield.api import load, utc, Topos
import getopt

degrees_per_radian = 180.0 / math.pi

options, remainder = getopt.getopt(sys.argv[1:], 'vhm:', [
                                                         'pos=',
                                                         'tle=',
                                                         'minutes=',
                                                         ])

pos='ata'
tlefile='iridium-NEXT.txt'
minutes=60
verbose=False
items=3

for opt, arg in options:
    if opt in ['--tle']:
        tlefile=arg
    elif opt in ['--pos']:
        pos=arg
    elif opt in ['-m', '--minutes']:
        minutes=float(arg)
    elif opt in ['-v']:
        verbose=True
    else:
        raise Exception("unknown argument: "+opt+".")

if len(remainder)>0:
    items=int(remainder[0])

def loadTLE(filename):
    satlist = load.tle_file(filename)
    if verbose:
        print("%i satellites loaded into list"%len(satlist))
    return satlist

def print_sat(date, sat):
    print('%s %20s: altitude %4.1f deg, azimuth %5.1f deg, range %5.1f km' %
        (date, sat.name, sat.alt * degrees_per_radian, sat.az * degrees_per_radian, sat.range/1000.))

satlist = loadTLE(tlefile)
ts=load.timescale(builtin=True)

locations={
    'club':  { 'lat': 48.153543,            'lon': 11.560702,                'alt': 516 },
    'ata':   { 'lat': 40+49./60+ 3  /60/60, 'lon': -(121+28./60+24  /60/60), 'alt': 1008},
    'ata1h': { 'lat': 40+48./60+59.1/60/60, 'lon': -(121+28./60+18.6/60/60), 'alt': 1008},
}

if pos not in locations:
    print("Location",pos,"unknown. Known locations: ",",".join([str(x) for x in locations]))
    sys.exit(1)


lat=locations[pos]['lat']
lon=locations[pos]['lon']
alt=locations[pos]['alt']

recpos = Topos(latitude_degrees=lat, longitude_degrees=lon, elevation_m=alt)

near_list = []

now=datetime.now(timezone.utc)
tnow = ts.utc(now)

#print("Now:",t0)

t0 = ts.utc(tnow.utc_datetime() - timedelta(minutes=5))
t1 = ts.utc(tnow.utc_datetime() + timedelta(minutes=minutes))

sat0=satlist[0]
days = tnow - sat0.epoch
if verbose:
    print('TLE file is %.2f days old'%days)

if abs(days)>5:
    print('SAT EPOCH too far away. (%.2f days)'%days, file=sys.stderr)
    sys.exit(-1)

satev=[]
for sat in satlist:
    t, ev = sat.find_events(recpos, t0, t1, altitude_degrees=18.0)
    if len(t)>0:
        t2, ev2 = sat.find_events(recpos, t0, t1, altitude_degrees=0)
        events=[]
        # Merge the two events lists
        events+=zip(t,[x+1 for x in ev])
        events+=zip(t2,[[0,-1,4][x] for x in ev2])
        # sort by time
        events=sorted(events, key=lambda tup: tup[0].utc_datetime())
        # filter out duplicate culminations
        events=filter(lambda tup: tup[1]>=0, events)
        satev.append((t[0].utc_datetime(),sat,events))

def deltat(future, past):
    delta=(future-past).seconds
    if delta>60:
        str="%dm%02ds"%divmod(delta,60)
    else:
        str="%02ds"%(delta%60)
    return str

def deltatstr(ts):
    if (ts>now):
        str="in "+"%6s"%deltat(ts,now)
    else:
        str="%5s"%deltat(now,ts)+" ago"
    return str


first=True
ad=30 # azimuth-maximum delta for north/south/east/west
for item in sorted(satev, key=lambda tup: tup[0]) :
    if items==0:
        break
    items-=1
    if not first:
        print()
    first=False
    print("%s:"%item[1].name)
    sts=None
    for ti, event in item[2]:
        add=""
#        if event==4: continue
        name = ('above 18°', 'culminate', 'below 18°', 'rise', '<dummy>', 'set')[event]
        name = ('rise', 'above 18°', 'culminate', 'below 18°', 'set')[event]
        name="%-10s"%name
        if event==1:
            sts=ti.utc_datetime()
        if event==3 and sts is not None:
            add+=" [visible for %s]"%deltat(ti.utc_datetime(),sts)
        if verbose and (event==3 or event==5):
            (el,az,dist)= (item[1]-recpos).at(ti).altaz()
            add+=" [az=%3d°]"%az.degrees
        if event==0:
            (el,az,dist)= (item[1]-recpos).at(ti).altaz()
            if az.degrees<90-ad or az.degrees>270+ad:
                add+=" flying south"
            elif az.degrees>90+ad and az.degrees<270-ad:
                add+=" flying north"
        if event==2:
            (el,az,dist)= (item[1]-recpos).at(ti).altaz()
            add+=" [el=%2d°]"%el.degrees
            if az.degrees>0+ad and az.degrees<180-ad:
                add+=" passing east"
            elif az.degrees<360-ad and az.degrees>180+ad:
                add+=" passing west"
        print(ti.utc_datetime().astimezone().strftime("%H:%M:%S"),"-",deltatstr(ti.utc_datetime()), name, add)

