#!/usr/bin/env python3
import sys
import math
import time
from datetime import datetime, timezone, timedelta
import getopt
import os
import termios
import select
from skyfield.api import load, utc, Topos
from numpy import identity

degrees_per_radian = 180.0 / math.pi

options, remainder = getopt.getopt(sys.argv[1:], 'vhm:r', [
                                                         'pos=',
                                                         'tle=',
                                                         'minutes=',
                                                         ])

pos='ata'
tlefile='iridium-NEXT.txt'
minutes=60
verbose=False
items=3
repeat=False

for opt, arg in options:
    if opt in ['--tle']:
        tlefile=arg
    elif opt in ['--pos']:
        pos=arg
    elif opt in ['-m', '--minutes']:
        minutes=float(arg)
    elif opt in ['-r']:
        repeat=True
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

def get_pos(pos):
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

    return Topos(latitude_degrees=lat, longitude_degrees=lon, elevation_m=alt)

recpos=get_pos(pos)

def mytsutc(tm):
    """ speed up skyfield a bit / https://github.com/skyfielders/python-skyfield/issues/389 """
    t=ts.utc(tm)
    t.gast = t.tt * 0.0
    t.M = t.MT = identity(3)
    return t

now=datetime.now(timezone.utc)
tnow = mytsutc(now)

sat0=satlist[0]
days = tnow - sat0.epoch
if verbose:
    print('TLE file is %.2f days old'%days)

if abs(days)>5:
    print('SAT EPOCH too far away. (%.2f days)'%days, file=sys.stderr)
    sys.exit(-1)

def generate_events(satlist, tnow=mytsutc(datetime.now(timezone.utc))):
    t0 = mytsutc(tnow.utc_datetime() - timedelta(minutes=5))
    t1 = mytsutc(tnow.utc_datetime() + timedelta(minutes=minutes))
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
    return satev

def deltat(future, past):
    delta=(future-past).seconds
    if delta>60:
        out="%dm%02ds"%divmod(delta,60)
    else:
        out="%02ds"%(delta%60)
    return out

def deltatstr(ts):
    if ts>now:
        out="in %6s"%deltat(ts,now)
    else:
        out="%5s ago"%deltat(now,ts)
    return out


def format_events(satev, nitems=3):
    ad=30 # azimuth-maximum delta for north/south/east/west
    nice=[]
    for item in sorted(satev, key=lambda tup: tup[0]) :
        if nitems==0:
            break
        nitems-=1
    #    print("%s:"%item[1].name)
        sts=None
        output=[]
        for ti, event in item[2]:
            add=""
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
    #        print(ti.utc_datetime().astimezone().strftime("%H:%M:%S"),"-",deltatstr(ti.utc_datetime()), name, add)
            output.append([ti,name+add])
        nice.append([item[1],output])
    return nice

def print_events(nice):
    global now
    t_=mytsutc(now)
    for sat,out in nice:
        print()
        print("%s:"%sat.name, end="")
        (el,az,dist)= (sat-recpos).at(t_).altaz()
        print(" [az=%5.1f° el=%5.1f° dist=%5dkm/%4.1fms]"%(az.degrees,el.degrees,dist.km,dist.m/ 299792.458),end="")
        print("")
        for t,o in out:
            print(t.utc_datetime().astimezone().strftime("%H:%M:%S"),"-",deltatstr(t.utc_datetime()), o)

satev=generate_events(satlist)
nice=format_events(satev, nitems=items)

try:
    fd=None
    old_term=None
    if repeat:
        import curses
        curses.initscr()
        curses.endwin()
        sys.stdout.buffer.write(curses.tigetstr("clear"))
        sys.stdout.buffer.write(curses.tigetstr("civis"))
        # Save the terminal settings
        fd = sys.stdin.fileno()
        old_term = termios.tcgetattr(fd)
        new_term = old_term
        # Turn on raw mode
        new_term[3] = (new_term[3] & ~termios.ICANON & ~termios.ECHO)
        termios.tcsetattr(fd, termios.TCSAFLUSH, new_term)

    while repeat:
        now=datetime.now(timezone.utc)
        if repeat:
            sys.stdout.buffer.write(curses.tigetstr("home"))
            print(os.path.basename(__file__)," - ",now.astimezone().strftime("%H:%M:%S"))
        print_events(nice)
        if nice[-1][1][-1][0].utc_datetime()<now: # Exit when last sat in list has set.
            print()
            print("done.")
            break
        if repeat:
#            sys.stdout.buffer.write(curses.tigetstr("el"))
            sys.stdout.flush()
            # sleep a bit if no input
            if select.select([sys.stdin], [], [], 1) == ([sys.stdin], [], []):
                c = sys.stdin.read(1)
                if c=='q':
                    break
                elif c in '123456789r':
                    try:
                        items=int(c)
                    except ValueError:
                        pass
                    satev=generate_events(satlist)
                    nice=format_events(satev, nitems=items)
                    sys.stdout.buffer.write(curses.tigetstr("clear"))
                elif c==' ':
                    pass
                else:
                    print("Unknown key pressed")
                    select.select([sys.stdin], [], [], 1)

except KeyboardInterrupt:
    pass

finally:
    if repeat:
        sys.stdout.buffer.write(curses.tigetstr("cnorm"))
        termios.tcsetattr(fd, termios.TCSAFLUSH, old_term)
