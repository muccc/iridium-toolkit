#!/usr/bin/env python3

# vim: set ts=4 sw=4 tw=0 et pm=:

#
# plots beam reception relative to satellite position at a given location
#
# input: "IRA" lines from iridium-parser
#
# requires "locations.ini" with reciever location like this:
#
#[default]
#name=Home
#lat= 123.45
#lon=  67.89
#alt= 123

import fileinput
import argparse
import re
import sys
import os
from math import sqrt, pi, cos, acos
from itertools import compress
from configparser import ConfigParser
import matplotlib.pyplot as plt
import numpy as np
import pyproj

np.set_printoptions(floatmode='maxprec', suppress=True, precision=4)

ecef = pyproj.Proj(proj='geocent', ellps='WGS84', datum='WGS84')
lla = pyproj.Proj(proj='latlong', ellps='WGS84', datum='WGS84')

to_lla = pyproj.Transformer.from_proj(ecef, lla)
to_ecef = pyproj.Transformer.from_proj(lla, ecef)

# Satellite inclination
INC = 86.4/180*pi
#INC = 90.0


debugpos = None

####


def read_observer(location):
    observer = {}

    config = ConfigParser()
    config.read(['locations.ini', os.path.join(os.path.dirname(__file__), 'locations.ini')])

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
        lat = config.getfloat(location, 'lat')
        lon = config.getfloat(location, 'lon')
        alt = config.getfloat(location, 'alt')
        observer.update(lat=lat, lon=lon, alt=alt)

        x, y, z = to_ecef.transform(lon, lat, alt, radians=False)
        observer['xyz'] = np.array([x, y, z])/1000
    elif 'x' in config[location]:
        x = config.getfloat(location, 'x')
        y = config.getfloat(location, 'y')
        z = config.getfloat(location, 'z')
        observer['xyz'] = np.array([x, y, z])/1000

        #lon, lat, alt = to_lla.transform(x*1000, y*1000, z*1000, radians=False)
        #observer.update(lat=lat, lon=lon, alt=alt)
    else:
        print("Location %s has no location information" %location, file=sys.stderr)
        sys.exit(1)

    return observer


def get_locations():
    config = ConfigParser()
    config.read(['locations.ini', os.path.join(os.path.dirname(__file__), 'locations.ini')])

    if config.sections():
        return config.sections()

    raise SystemExit("locations.ini missing or empty")


def parse_args():
    global debugpos
    global args

    parser = argparse.ArgumentParser()

    beams = { 'outer': '5,10,1,38,43,36,23,19,18,25', 'inner': '32,31,48,47,16,15', 'mid': '12,24,28,40,44,8' }

    def parse_comma(arg):  # parse integers separated by comma
        if arg in beams:
            arg=beams[arg]
        return [int(x)for x in arg.split(',')]

    parser.add_argument("-v", "--verbose",   action="store_true",                        help="verbose output")
    parser.add_argument(      "--debug",     action="store_true",                        help="debug output")
    parser.add_argument("-b", "--beam",      type=parse_comma, default=None,             help="beam(s) to plot")
    parser.add_argument("-d", "--direction", choices=['n', 's', 'b'], default='n',       help="direction of flight")
    parser.add_argument("-s", "--sat",       type=int, default=None,                     help="satellite to plot")
    parser.add_argument("-l", "--loc",       choices=get_locations(), default="default", help="observer location")
    parser.add_argument(      "--snr",       type=int, default=25,                       help="SNR dB cutoff")

    parser.add_argument("remainder", nargs='*', help=argparse.SUPPRESS)

    args = parser.parse_args()

    debugpos = args.debug

    if args.direction=="n":
        args.direction=1
    elif args.direction=="s":
        args.direction=-1
    elif args.direction=="b":
        args.direction=0
    else:
        raise ValueError("Unknown direction?")

    return args


def print_system(system):
    print("System:")
    print("-", "sat   plane:", system[0])
    print("-", "orbit plane:", system[1])
    print("-", "heading:    ", system[2], end=" ")
    if system[2][2] > 0:
        print("(north)")
    elif system[2][2] < 0:
        print("(south)")
    else:
        print("(???)")


####
NORTH_POLE = np.array(to_ecef.transform(0, 90, 0, radians=False))
NORTH_POLE = NORTH_POLE/1000  # in km
NORTH_POLE[0] = 0
NORTH_POLE[1] = 0


def simple_north_system(pos_sat, north):
    '''calculates a satellite coordinate system where the sat flies towards the north/south pole'''
    sat_plane=pos_sat/np.linalg.norm(pos_sat)

    direction_sat=-(NORTH_POLE-pos_sat)
    if north < 0:  # Invert if flying south
        direction_sat=-direction_sat

    # project direction vector onto satellite plane & normalize
    direction_projected=direction_sat-direction_sat.dot(sat_plane)*sat_plane
    direction_projected_normal=direction_projected/np.linalg.norm(direction_projected)

    third_axis=np.cross(direction_projected_normal, sat_plane)  # a.k.a. orbital plane

    system = np.array([sat_plane, third_axis, direction_projected_normal])

    if debugpos:
        print_system(system)

    return system


# Z-plane (equator)
ZPLANE = np.array([0, 0, 1])
# Precision for assertions
EPSILON = 1e-11


def incl_system(pos_sat, north):
    '''returns a satellite coordinate system where the sat flies on the default iridium inclination'''
    # Requirements for the orbital plane N=<a,b,c>:

    # (1) Origin
    # the plane contains the origin

    # (2) Normalized
    # we want the plane to be normalized:
    #
    # N= sqrt(a^2 + b^2 + c^2) == 1

    # (3) Angle
    # plane N intersects with plane Z=<0,0,1> with angle inc° (Z also goes through origin)
    # N (dot) Z / norm(Z)*norm(N) == cos(inc)
    # both are already normalized, so:
    #
    # A= (0*a + 0*b + 1*c) / (1 * 1) == cos(inc)

    # (4) Satellite
    # plane N contains the satellite at <x,y,z>
    #
    # S= a*x + b*y + c*z == 0

    # Solve S for b:
    # sage: S.solve(b)
    # [b == -(a*x + c*z)/y]

    # Substitute in N and solve for a
    # sage: N.subs(S.solve(b)).solve(a)[0]
    # a == -(c*x*z + sqrt(-c^2*z^2 - (c^2 - 1)*x^2 - (c^2 - 1)*y^2)*y)/(x^2 + y^2)
    # sage: N.subs(S.solve(b)).solve(a)[1]
    # a == -(c*x*z - sqrt(-c^2*z^2 - (c^2 - 1)*x^2 - (c^2 - 1)*y^2)*y)/(x^2 + y^2)

    # Note: this will fail for sat positions with y=0.
    #       For that case, we can solve the other way around
    # sage: N.subs(S.solve(a)).solve(b) ...

    x, y, z = pos_sat
    sat_plane = pos_sat / np.linalg.norm(pos_sat)

    try:
        c = cos(INC)

        if y!=0:
            a1 = -(c*x*z + sqrt(-c*c*z*z - (c*c - 1)*x*x - (c*c - 1)*y*y)*y)/(x*x + y*y)
            b1 = -(a1*x + c*z)/y

            a2 = -(c*x*z - sqrt(-c*c*z*z - (c*c - 1)*x*x - (c*c - 1)*y*y)*y)/(x*x + y*y)
            b2 = -(a2*x + c*z)/y

            v1 = np.array([a1, b1, c])
            v2 = np.array([a2, b2, c])
        else:
            b1 = -(c*y*z + sqrt(-c*c*z*z - (c*c - 1)*x*x - (c*c - 1)*y*y)*x)/(x*x + y*y)
            a1 = -(b1*y + c*z)/x

            b2 = -(c*y*z - sqrt(-c*c*z*z - (c*c - 1)*x*x - (c*c - 1)*y*y)*x)/(x*x + y*y)
            a2 = -(b2*y + c*z)/x

            v2 = np.array([a1, b1, c])
            v1 = np.array([a2, b2, c])

    except ValueError as e:
        # Happens when position is too far north/south to be reached with that inclination
        print(e)
        return None
    except ZeroDivisionError as e:
        # Should not happen anymore
        print(e)
        return None

    # Every sat position has two possible planes
    # Use the correct one based on travel direction
    # (see assert below)
    if north>0:
        orbit_plane=v2
    elif north<0:
        orbit_plane=v1

    direction_vec=np.cross(sat_plane, orbit_plane)

    try:
        assert abs(np.linalg.norm(ZPLANE)-1)       < EPSILON, "zplane not normal?"

        assert abs(v1.dot(pos_sat))                < EPSILON, "sat not on plane#1"
        assert abs(np.linalg.norm(v1)-1)           < EPSILON, "plane#1 not normalized"
        assert abs(abs(ZPLANE.dot(v1))-cos(INC))   < EPSILON, "plane#1 not correct inclination"

        assert abs(v2.dot(pos_sat))                < EPSILON, "sat not on plane#2"
        assert abs(np.linalg.norm(v2)-1)           < EPSILON, "plane#2 not normalized"
        assert abs(abs(ZPLANE.dot(v2))-cos(INC))   < EPSILON, "plane#2 not correct inclination"

        assert north == -np.sign(direction_vec[2]),           "Travelling in wrong direction"

    except AssertionError:
        print("")
        print("orbit_plane_1:", v1)
        print("sat_on_plane1:", v1.dot(pos_sat))
        print("norm_1:", np.linalg.norm(v1))
        print("Angle to Z-plane:", acos(ZPLANE.dot(v1) /
                                        (np.linalg.norm(ZPLANE)*np.linalg.norm(v2)))/pi*180)
        print("")

        print("orbit_plane_2:", v2)
        print("sat_on_plane2:", v2.dot(pos_sat))
        print("norm_2:", np.linalg.norm(v2))
        print("Angle to Z-plane:", acos(ZPLANE.dot(v2) /
                                        (np.linalg.norm(ZPLANE)*np.linalg.norm(v2)))/pi*180)
        print("")
        raise

    system = sat_plane, orbit_plane, direction_vec

    if debugpos:
        print_system(system)

    return system


def c_transform(position, system, translation):
    # ref. https://cs184.eecs.berkeley.edu/uploads/lectures/05_transforms-2/05_transforms-2_slides.pdf

    # rotation matrix
    F1 = np.identity(4)
    F1[:3,:3] = system

    # translation matrix
    F2 = np.identity(4)
    F2[:3,3] = -translation

    # conversion matrix
    F = np.matmul(F1, F2)

    def pos_dbg(dbgpos, txt=""):
        print(txt, "in:", dbgpos, "norm:", np.linalg.norm(dbgpos))
        rel = dbgpos-translation
        print(txt, "relnorm:", np.linalg.norm(rel))
        out = np.matmul(F, np.append(dbgpos, 1))
        print(txt, "out:", out, "norm:", np.linalg.norm(np.delete(out, 3)))

    if debugpos and False:  # coordinate transformation debugging
        pos_dbg(np.array([0, 0, 0]), "zero")
        pos_dbg(translation, "satpos")
        pos_dbg(position, "obs")
        print("sat_lla:", to_lla.transform(*translation*1000, radians=False))
        print("obs_lla:", to_lla.transform(*position*1000, radians=False))

    res=np.matmul(F, np.append(position, 1))

    if debugpos:
        print("distance to sat:", np.linalg.norm(res[:3]))

    return res[:3]


def read_file(observer):
    # Preallocate arrays
    xs = [[] for i in range(50)]
    ys = [[] for i in range(50)]
    ss = [[] for i in range(50)]
    seen = [0]* 255
    north = [0]* 255
    pos = [None]* 255

    ira_warn = False

    for line in fileinput.input(args.remainder):
        if line[0:4] != 'IRA:':
            if not ira_warn:
                print("Ignoring non IRA-lines...", file=sys.stderr)
                ira_warn = True
            continue

        mm=re.match(r"IRA: \S+-\d+\S+ ([\d.]+) \S+\s+\d+% +(?:\S+\|)?([\d.]+) .* sat:(\d+) beam:(\d+) xyz=.(.\d+),(.\d+),(.\d+).", line)

        if mm is None:
            print("Unmatch:", line)
            continue

        mstime, snr, sat, cell, x, y, z = mm.groups()

        sat  = int(sat)
        cell = int(cell)

        # Filter
        if args.sat and sat!=args.sat:
            continue

        if args.beam is not None:
            if cell not in args.beam:
                continue

        x = int(x)*4  # km
        y = int(y)*4  # km
        z = int(z)*4  # km
        snr = float(snr)
        gtime = float(mstime)/1e3

        alt = sqrt(x**2+y**2+z**2)

        if alt<7000:  # ignore "down" i.e. beam positions
            continue

        if debugpos:
            print("")
            print("sat:", sat, "cell:", cell, "x/y/z", x, y, z, "alt:", alt)

        if seen[sat]>0:
            if debugpos: print("- timedelta", gtime-seen[sat])
            if gtime-seen[sat] < 60:
                (ox, oy, oz)=pos[sat]
                if debugpos: print("- posdelta", x-ox, y-oy, z-oz)
                if z-oz==0:
                    continue
                if z-oz>0:
                    north[sat]=1
                else:
                    north[sat]=-1
            else:
                north[sat]=0

        if debugpos: print("- north:", north[sat])

        seen[sat]=gtime
        pos[sat]=(x, y, z)

        if args.direction != 0:
            if args.direction!=north[sat]:
                if debugpos: print("# ignoring direction")
                continue

        if north[sat] == 0:
            if debugpos: print("# Unknown direction")
            continue

        # x: -> (null island), z: -> (north pole)
        pos_sat=np.array([x, y, z])

#        sat_system = simple_north_system(pos_sat, north[sat])
        sat_system = incl_system(pos_sat, north[sat])

        if sat_system is None:
            continue

        if debugpos:
            p1, p2, p3 = sat_system
            print("orthogonal system?", p1.dot(p2), p1.dot(p3), p2.dot(p3))
            print("normalized?", np.linalg.norm(p1), np.linalg.norm(p2), np.linalg.norm(p3))
            print("Angle to Z-plane:", acos(ZPLANE.dot(p2)/
                                            (np.linalg.norm(ZPLANE)*np.linalg.norm(p2)))/pi*180, "°")

        res = c_transform(observer['xyz'], sat_system, pos_sat)

        xs[cell].append(res[1])
        ys[cell].append(res[2])
        ss[cell].append(snr)
    return (xs, ys, ss)

####


def set_plot_title():
    fig = plt.gcf()
    # Construct title / filename
    title = 'Beam reception'
    fname = 'beam'

    if args.sat:
        title += ' for Sat %d' %args.sat
        fname += '-sat%03d'    %args.sat
    else:
        title += ' plot'

    if args.beam:
        beamstr=",".join([str(x) for x in args.beam])
        beams = { 'outer': '5,10,1,38,43,36,23,19,18,25', 'inner': '32,31,48,47,16,15', 'mid': '12,24,28,40,44,8' }
        bname = {v: k for k, v in beams.items()}
        if beamstr in bname:
            beamstr=bname[beamstr]
        title += ' (%s beams)' %beamstr
        fname += '-%s'    %beamstr

    title += ' at %s' %args.loc
    fname += '-%s' %"".join(args.loc.lower().split())

    if args.direction == 1:
        title += ' (North)'
        fname += '-north'
    elif args.direction == -1:
        title += ' (South)'
        fname += '-south'

    plt.title(title)
    fig.canvas.manager.set_window_title(title)
    fig.canvas.get_default_filename = lambda: fname+'.png'

####


def make_legend_clickable(ps):
    fig = plt.gcf()

    leg=plt.legend(loc='upper right')
    leg.set_draggable(1)

    # Get to the legend entries
    pat=leg.get_children()
    # print "pat:",pat
    # print "c:",pat[0].get_children()
    # print "cc:",pat[0].get_children()[1].get_children()
    # print "ccc:",pat[0].get_children()[1].get_children()[0].get_children()
    leg_items=pat[0].get_children()[1].get_children()[0].get_children()

    def legend_set(leg_item, onoff):
        # find orig plot collection corresponding to the legend item line
        item=leg_map[leg_item]

        if onoff==-1:
            onoff = not item.get_visible()
        item.set_visible(onoff)

        dots, txts=leg_item.get_children()
        dot=dots.get_children()[0]
        txt=txts.get_children()[0]

        if onoff:
            txt.set_alpha(1.0)
            dot.set_alpha(1.0)
        else:
            txt.set_alpha(0.2)
            dot.set_alpha(0.2)

    leg_map={}
    for i, p in enumerate(ps):
        # Make legend items pickable and save references to plot collection object
        leg_items[i].set_picker(5)  # 5 pts tolerance
        leg_map[leg_items[i]]=p
        # default some to off?
        # legend_set(leg_items[i],0)

    def onpick(event):
        # on pick event toggle the visibility
        if type(event.artist).__name__ == 'Legend':
            return
        
        leg_item = event.artist

        if all([leg_map[i].get_visible() for i in leg_items]):
            for i in leg_items:
                if i != leg_item:
                    legend_set(i, -1)
        else:
            legend_set(leg_item, -1)

        if all([not leg_map[i].get_visible() for i in leg_items]):
            for i in leg_items:
                legend_set(i, 1)
        fig.canvas.draw()

    fig.canvas.mpl_connect('pick_event', onpick)


def plotme(xs, ys, ss):
    if args.verbose: print("------------ PLOT --------------")

    colormap = plt.cm.gist_ncar
    colorst = [colormap(i) for i in np.linspace(0, 0.9, len(xs))]
    plt.xlabel('Y/km')
    plt.ylabel('Z/km', labelpad=-30)

    ps=[]
    for cnt in range(len(xs)):
        if len(xs[cnt])==0:
            continue

        # Calculate center of mass for circle
        if args.verbose: print("Cell: ", cnt)
        if args.verbose: print("- Points: ", len(xs[cnt]))
        xc=sum(xs[cnt])/len(xs[cnt])
        yc=sum(ys[cnt])/len(ys[cnt])
        if args.verbose: print("- Center: ", xc, yc)
        if args.verbose: print("snr: ", min(ss[cnt]), "-", max(ss[cnt]))

        ax=plt.gcf().gca()

        selectors=[x > args.snr for x in ss[cnt]]

        p=plt.scatter(
            x=list(compress(xs[cnt], selectors)),
            y=list(compress(ys[cnt], selectors)),
            alpha=0.1, color=colorst[cnt], edgecolor="none",
            label="%02d (%d)" %(cnt, len(list(compress(xs[cnt], selectors)))))
        ps.append(p)

    if not ps:
        raise SystemExit("No data to plot")

    fig = plt.gcf()
    ax = fig.gca()

    ax.legend(fontsize='small')
    ax.spines['right'].set_position('zero')
    ax.spines['top'].set_position('zero')
    ax.set_aspect('equal', 'datalim')

    set_plot_title()

    # Make plot area larger
    fig.tight_layout()
    plt.subplots_adjust(left=0.05, bottom=0.05, top=0.95)
    #fig.set_size_inches(10, 9, forward=True)

    plt.ylim([-4000, 4000])
    plt.xlim([-4000, 4000])

    make_legend_clickable(ps)

    plt.show()


args = None
if __name__ == "__main__":
    try:
        parse_args()
        obs = read_observer(args.loc)
        data = read_file(obs)
        plotme(*data)
    except KeyboardInterrupt:
        print("^C")
