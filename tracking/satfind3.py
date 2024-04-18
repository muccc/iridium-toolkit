#!/usr/bin/env python3
import sys
import math
from datetime import datetime, timezone, timedelta
import argparse
import re
import os
import termios
import select
from skyfield.api import load, Topos
from numpy import identity
from configparser import ConfigParser
import pyproj

ecef = pyproj.Proj(proj='geocent', ellps='WGS84', datum='WGS84')
lla = pyproj.Proj(proj='latlong', ellps='WGS84', datum='WGS84')

to_lla = pyproj.Transformer.from_proj(ecef, lla)
to_ecef = pyproj.Transformer.from_proj(lla, ecef)

degrees_per_radian = 180.0 / math.pi
speed_of_light = 299792458

args = None

def parseangle(value):
    z = re.match(r"(?P<sign>[+-]?)(?P<deg>\d+(\.\d+)?)(° *((?P<min>\d+(\.\d+)?)['′] *)?((?P<sec>\d+(\.\d+)?)\")?(?P<dir>[NEOSW]?))?$", value)
#    print(value,end=" -> ")
    if z is None:
        raise ValueError("could not convert string to angle: '%s'"%value)
    parsed = z.groupdict()
    result = float(parsed['deg'])
    if parsed['min'] is not None:
        result += float(parsed['min'])/60
    if parsed['sec'] is not None:
        result += float(parsed['sec'])/60/60
    if parsed['dir'] == 'S' or parsed['dir'] == 'W' or parsed['sign'] == '-':
        result = -result
    return result

assert parseangle("123") == 123
assert parseangle("-13.30") == -13.30
assert parseangle("13°") == 13
assert parseangle("13°30'S") == -13.5
assert parseangle("13°30'S") == -13.5
assert parseangle("13°30'1\"") == 13 + 30/60 + 1/3600
assert parseangle("174° 47′ O") == 174 + 47/60

def read_observer(location):
    observer = {}

    config = ConfigParser(converters={'angle': parseangle})
    config.read(['locations.ini', os.path.join(os.path.dirname(__file__), 'locations.ini'), os.path.join(os.path.dirname(__file__), '..', 'locations.ini')])

    if location not in config:
        print("Location %s not defined" %location, file=sys.stderr)
        print("Available locations: ", ", ".join(config.sections()), file=sys.stderr)
        sys.exit(1)

    if 'name' in config[location]:
        observer['name'] = config[location]['name']
        args.loc = observer['name']
    else:
        observer['name'] = location

    if 'lat' in config[location]:
        lat = config.getangle(location, 'lat')
        lon = config.getangle(location, 'lon')
        alt = config.getfloat(location, 'alt')
        observer.update(lat=lat, lon=lon, alt=alt)

#        x, y, z = to_ecef.transform(lon, lat, alt, radians=False)
#        observer['xyz'] = np.array([x, y, z])/1000
    elif 'x' in config[location]:
        x = config.getfloat(location, 'x')
        y = config.getfloat(location, 'y')
        z = config.getfloat(location, 'z')
#        observer['xyz'] = np.array([x, y, z])/1000

        lon, lat, alt = to_lla.transform(x, y, z, radians=False)
        observer.update(lat=lat, lon=lon, alt=alt)
    else:
        print("Location %s has no location information" %location, file=sys.stderr)
        sys.exit(1)

    return observer

def get_locations():
    config = ConfigParser()
    config.read(['locations.ini', os.path.join(os.path.dirname(__file__), 'locations.ini'), os.path.join(os.path.dirname(__file__), '..', 'locations.ini')])

    if config.sections():
        return config.sections()

    raise SystemExit("locations.ini missing or empty")

def parse_args():
    global args

    parser = argparse.ArgumentParser()

    parser.add_argument("-v", "--verbose",   action="store_true",                        help="verbose output")
    parser.add_argument(      "--debug",     action="store_true",                        help="debug output")
    parser.add_argument("-l", "--loc",       choices=get_locations(), default="default", help="observer location")
    parser.add_argument("-m", "--minutes",   type=int, default=60,                       help="minutes in the future to scan")
    parser.add_argument("-r", "--repeat",    action="store_true",                        help="interactive mode")
    parser.add_argument("-a", "--angle",     type=float, default=18,                     help="elevation angle")
    parser.add_argument("-t", "--tlefile",   default="iridium-NEXT.txt",                 help="TLE filename")

    parser.add_argument("items", default=3, nargs='?', type=int, help=argparse.SUPPRESS)

    args = parser.parse_args()

    return args


def loadTLE(filename):
    satlist = load.tle_file(filename)
    if args.verbose:
        print("%i satellites loaded into list"%len(satlist))
    return satlist

def print_sat(date, sat):
    print('%s %20s: altitude %4.1f deg, azimuth %5.1f deg, range %5.1f km' %
        (date, sat.name, sat.alt * degrees_per_radian, sat.az * degrees_per_radian, sat.range/1000.))


timescale=load.timescale(builtin=True)
def mytsutc(tm):
    """ speed up skyfield a bit / https://github.com/skyfielders/python-skyfield/issues/389 """
    t=timescale.utc(tm)
    t.gast = t.tt * 0.0
    t.M = t.MT = identity(3)
    return t


def generate_events(satlist, tnow=mytsutc(datetime.now(timezone.utc))):
    t0 = mytsutc(tnow.utc_datetime() - timedelta(minutes=5))
    t1 = mytsutc(tnow.utc_datetime() + timedelta(minutes=args.minutes))
    satev=[]
    for sat in satlist:
        t, ev = sat.find_events(recpos, t0, t1, altitude_degrees=args.angle)
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
            name = ('rise', 'above %d°'%args.angle, 'culminate', 'below %d°'%args.angle, 'set')[event]
            name="%-10s"%name
            if event==1:
                sts=ti.utc_datetime()
            if event==3 and sts is not None:
                add+=" [visible for %s]"%deltat(ti.utc_datetime(),sts)
            if args.verbose and (event==3 or event==5):
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
    t_=mytsutc(now)
    for sat,out in nice:
        print()
        print("%s:"%sat.name, end="")
#        (el,az,dist)= (sat-recpos).at(t_).altaz()
        (el,az,dist,el_r,az_r,dist_r)=(sat-recpos).at(t_).frame_latlon_and_rates(recpos)
        shift=(speed_of_light-dist_r.m_per_s)/speed_of_light*1.626e9-1.626e9
        print(" [az=%5.1f° el=%5.1f° dist=%5dkm/%4.1fms ds~%6dHz]"%(az.degrees,el.degrees,dist.km,dist.m/ 299792.458,shift),end="")
        if args.verbose:
            print(" [ar=%+5.2f°/s er=%+5.2f°/s dr=%+5.2fkm/s]"%(az_r.degrees.per_second,el_r.degrees.per_second,dist_r.km_per_s),end="")
        print("")
        for t,o in out:
            print(t.utc_datetime().astimezone().strftime("%H:%M:%S"),"-",deltatstr(t.utc_datetime()), o)


if __name__ == "__main__":
    parse_args()
    observer=read_observer(args.loc)
    recpos=Topos(latitude_degrees=observer['lat'], longitude_degrees=observer['lon'], elevation_m=observer['alt'])
    satlist = loadTLE(args.tlefile)
    now=datetime.now(timezone.utc)
    tnow = mytsutc(now)

    if len(satlist) == 0:
        print('could not read TLE: %s'% args.tlefile, file=sys.stderr)
        sys.exit(-1)
    sat0=satlist[0]
    days = tnow - sat0.epoch
    if args.verbose:
        print('TLE file is %.2f days old'%days)

    if abs(days)>5:
        print('SAT EPOCH too far away. (%.2f days)'%days, file=sys.stderr)
        sys.exit(-1)

    satev=generate_events(satlist)
    nice=format_events(satev, nitems=args.items)

    if not args.repeat:
        print_events(nice)
        exit(0)

    try:
        fd=None
        old_term=None
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

        while True:
            items=args.items
            now=datetime.now(timezone.utc)
            sys.stdout.buffer.write(curses.tigetstr("home"))
            print(os.path.basename(__file__)," - ",now.astimezone().strftime("%H:%M:%S")," - ",args.loc)
            print_events(nice)
            if nice[-1][1][-1][0].utc_datetime()<now: # Exit when last sat in list has set.
                print()
                print("done.")
                break
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
        print("^C")
        pass

    finally:
        sys.stdout.buffer.write(curses.tigetstr("cnorm"))
        termios.tcsetattr(fd, termios.TCSAFLUSH, old_term)
