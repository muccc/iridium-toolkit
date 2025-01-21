#!/usr/bin/env python3
# vim: set ts=4 sw=4 tw=0 et pm=:

import re
from math import sqrt
from types import SimpleNamespace
from copy import deepcopy

import numpy as np
import pyproj
from scipy.optimize import minimize
from util import fmt_iritime, to_ascii, slice_extra, dt
from locations import get_locations, GetObserver

from .base import *
from ..config import config, outfile


SoL = 299792458. / 1e12 # km/ns

fileref = None
reftsu = None
reftsi = None
lastts = None
ppm = 0
do_update_ppm = False


def ppmcorr(ts):
    return ts - (ts-reftsu)*(ppm*1e-6)


def setppmrefts(its, uts, ref):
    global reftsu
    global reftsi
    global fileref
    fileref = ref
    reftsu = uts + np.timedelta64(0, 'ns')
    reftsi = its + np.timedelta64(0, 'ns')


def updateppm(itime, utime):
    if not do_update_ppm: return
    global lastts
    if lastts is not None and itime - lastts < np.timedelta64(300, 's'):
        return
    lastts = itime

    global ppm
    irun = itime - reftsi
    urun = utime - reftsu
    ppm = 1e6 * ((urun - irun) / irun)
    print(f"lla ppm updated: {ppm}")


ecef = pyproj.Proj(proj='geocent', ellps='WGS84', datum='WGS84')
lla = pyproj.Proj(proj='latlong', ellps='WGS84', datum='WGS84')

to_lla = pyproj.Transformer.from_proj(ecef, lla)
to_ecef = pyproj.Transformer.from_proj(lla, ecef)

do_delta = False
ref = None
drefalt = None

avg = []

saveresult = False
do_tof = False
max_age = 600 # seconds
min_dist = 200 # km
only_one = False
good_gdop = 1.5

oldguess = np.array([0, 0, 0, 0])


def dist(a, b):
    return np.linalg.norm(a-b)


def tdoa_solve(stations_coordinates, delays_to_stations):
    global oldguess

    def error(guess, stations, delays):
        e = 0
        for i in range(1, len(stations)):
            error = dist(guess, stations[i]) - dist(guess, stations[0]) - SoL * (delays[i] - delays[0])
            e += error**2
#        print("g",guess, e)
        return e

    guess = oldguess[:3]
    result = minimize(error, guess, args=(stations_coordinates, delays_to_stations), options={"maxiter": 4000})
    if saveresult and result.success:
        oldguess = result.x
    return result


def tof_solve(stations_coordinates, delays_to_stations):
    global oldguess
    if abs(oldguess[0]) > 5000:
        print("lla ERROR", oldguess)
        oldguess = np.array([0, 0, 0, 0])

    def error(guess_all, stations, tof):
        e = 0
        guess = guess_all[:3]
        guess_d = guess_all[-1]
#        guess_d=0
        for i in range(1, len(stations)):
            error = dist(guess, stations[i]) - SoL * (tof[i] - guess_d * 1e6)
            e += error**2
#        print("g",guess, e)
        return e

    guess = oldguess
    b = (-10000, 10000)
    bounds = [b, b, b, (None, None)]
#    result = minimize(error, guess, args=(stations_coordinates, delays_to_stations), method='Nelder-Mead', options = {"maxiter":4000}, bounds=bounds)
    result = minimize(error, guess, args=(stations_coordinates, delays_to_stations), method='L-BFGS-B', options={"maxiter": 4000}, bounds=bounds)
    if saveresult and result.success:
        oldguess = result.x
    return result


satref = {}
strikes = []

gctr = 0
gctrmod = 1


def npepoch(s, ns):
    ts = np.datetime64(int(s), 's')
    ts += np.timedelta64(ns, 'ns')
    return ts


class CalcTDOA(Reassemble):
    def __init__(self):
        self.topic = ["IRA", "IBC"]
        pass

    def args(self, parser):
        global do_delta
        global ref, drefalt
        global gctrmod
        global saveresult
        global do_tof
        global max_age, min_dist
        global ppm, do_update_ppm, only_one
        global good_gdop

        parser.add_argument("-l", "--loc", choices=get_locations(), action=GetObserver, help="location")
        parser.add_argument("--reduce", type=int, metavar="NUM", help="only calulate ever n'th position")
        parser.add_argument("--save", action='store_true', help="keep old position for next iteration")
        parser.add_argument("--tof", action='store_true', help="do tof instead of tdoa")
        parser.add_argument("--age", type=int, metavar="SECONDS", help="max age of strikes")
        parser.add_argument("--dist", type=int, metavar="KM", help="min distance for new strike")
        parser.add_argument("--ppm", type=float, help="clock accuracy")
        parser.add_argument("--gdop", type=float, help="threshold for good gdop")
        parser.add_argument("--updateppm", action='store_true', help="try to estimate ppm (every 5m)")
        parser.add_argument("--onlyone", action='store_true', help="only keep one strike per sat")
        parser.add_argument("--help2", action="help")
        config = parser.parse_args()

        if config.loc:
            do_delta = True
            ref = config.loc.xyz * 1000
            drefalt = config.loc.alt
        if config.reduce:
            gctrmod = config.reduce
        if config.save:
            saveresult = True
        if config.tof:
            do_tof = True
        if config.age:
            max_age = config.age
        if config.dist:
            min_dist = config.dist
        if config.ppm:
            ppm = config.ppm
        if config.gdop:
            good_gdop = config.gdop
        if config.updateppm:
            do_update_ppm = True
        if config.onlyone:
            only_one = True
        print("options:", "reduce:", gctrmod, "save:", saveresult, "tof:", do_tof, "strike_age:", max_age, "strike_dist:", min_dist, "ppm:", ppm, "update_ppm:", do_update_ppm, "only_one:", only_one, "gdop:", good_gdop)
        return config

    r1 = re.compile(r' sat:(\d+) cell:\d+ 0 slot:(\d)')
    r2 = re.compile(r' time:([0-9:T-]+(?:\.\d+)?)Z')
    r3 = re.compile(r'^sat:(\d+) beam:\d+ xyz=\(([+-]?[0-9]+),([+-]?[0-9]+),([+-]?[0-9]+)\) ')
    r4 = re.compile(r' alt=(\d+) ')

    def filter(self, line):
        q = super().filter(line)
        if q is None: return None
        if q.typ not in ("IBC:", "IRA:"): return None

        q.enrich()
        if q.confidence<95: return None

        if 'perfect' in config.args:
            if not q.perfect: return None

        return q

    def process(self, q):
        global gctr
        global strikes
        if q.typ == "IBC:":

            m = self.r1.search(q.data)
            if not m: return
            q.sat = int(m.group(1))
            q.slot = int(m.group(2))

            m = self.r2.search(q.data)
            if not m: return
            q.itime = np.datetime64(m.group(1))

#            print("i",m.group(1),q.itime)

            q.uxtime = npepoch(q.starttime, q.nstime)

            # save first timestamp for ppm calculation
            if fileref != q.starttime:
                setppmrefts(q.itime, q.uxtime, q.starttime)

            if q.uxtime - reftsu > np.timedelta64(900, 's'):
                updateppm(q.itime, q.uxtime)

            q.uxtime = ppmcorr(q.uxtime)

            # correct for slot:
            # 1st vs. 4th slot is 3 * (downlink + guard)
            q.uxtime -= np.timedelta64(q.slot*(3 * (8280 + 100)), 'us')

            # correct to beginning of simplex:
            # simplex + guard + 4*(uplink + guard) + extra_guard
            q.uxtime -= np.timedelta64(20320 + 1240 + 4 * (8280 + 220) + 20, 'us')

            q.itime = q.itime
            satref[q.sat] = [q.uxtime, q.itime]
            return

        elif q.typ == "IRA:":
            if fileref != q.starttime: return # IBC first

            m = self.r3.search(q.data)
            if not m: return

            q.sat = int(m.group(1))
            q.xyz = np.array([int(m.group(2)), int(m.group(3)), int(m.group(4))])*4
            q.alt2 = sum([x*x for x in q.xyz])
            q.uxtime = npepoch(q.starttime, q.nstime)
            q.uxtime = ppmcorr(q.uxtime)

            if q.alt2 < 6800**2: return # ~6370 vs. ~7150
            if q.sat not in satref: return # No LBFC for this sat yet

            # Adjust LBFC timestamp corresponding to this IRA frame
            ru, ri = satref[q.sat]
            td = int((q.uxtime-ru) / np.timedelta64(1, 'ms'))
            f, r = divmod(td-45, 90)
            f += 1
            r -= 45
            ri2 = ri + np.timedelta64(f*90, 'ms')

            # correct to beginning of signal:
            # our timestamp is "the middle of the first symbol of the 12-symbol BPSK Iridium sync word"
            # so correct for 64 symbols preamble & one half symbol.
            # also correct for 1ms guard time before the simplex slot
            q.uxtime -= np.timedelta64(1000 + 64500//25, 'us')

            newstrike = SimpleNamespace(sat=q.sat, xyz=q.xyz, uxtime=q.uxtime, itime=ri2,
                                        tof=q.uxtime - ri2, idelta=np.timedelta64(f*90, 'ms'))

            if only_one: # only keep one strike per satellite
                strikes = [x for x in strikes if x.sat != q.sat]
            else:
                laststrike = None
                for strike in strikes:
                    if strike.sat == q.sat:
                        laststrike = strike

                if laststrike is not None:
                    d = laststrike.xyz-newstrike.xyz
#                    print(f"sat {q.sat} moved {dist(laststrike.xyz,newstrike.xyz):.2f}km in {newstrike.itime - laststrike.itime} since last strike")
                    if d.dot(d) < min_dist**2: # moved less than 200km
#                        print("... ignored")
                        return

            strikes.append(newstrike)

            # expire old strikes
            strikes = [x for x in strikes if x.itime > ri2 - np.timedelta64(max_age, 's')]

#            print("Strikes:", len(strikes))
#            for i in range(len(strikes)):
#                print(i, strikes[i])
#            print("")

            gctr += 1
            # 'reduce' amount of calculations
            if gctr % gctrmod != 0: return
            if len(strikes) > 3: # enough data to hazard a guess

                if do_tof:
                    stations = []
                    tofs = []

                    for s in strikes:
                        tofs.append(s.tof/np.timedelta64(1, 'ns'))
                        stations.append(s.xyz)

                    if config.verbose:
                        print("Solve:")
                        for i in range(len(tofs)):
                            print(f"{tofs[i]:8.0f} [{stations[i][0]:5d},{stations[i][1]:5d},{stations[i][2]:5d}]")
                        print("")

                    r = tof_solve(stations, tofs)
                else:
                    lst = strikes[0]
                    rel_zero = lst.itime
                    toas = []
                    for s in strikes:
#                        print(s)
#                        print(s.itime-rel_zero, s.uxtime - (s.itime - rel_zero))
                        toas.append([s.uxtime - (s.itime - rel_zero), s.xyz])

                    toas = sorted(toas, key=lambda x: x[0])
                    zero_toa = toas[0][0]

                    stations = []
                    dtoas = []

                    for x in toas:
                        dtoas.append((x[0]-zero_toa) / np.timedelta64(1, 'ns'))
                        stations.append(x[1])

                    if config.verbose:
                        print("Solve:")
                        for i in range(len(stations)):
                            print(f"{dtoas[i]:8.0f} [{stations[i][0]:5d},{stations[i][1]:5d},{stations[i][2]:5d}]")
                        print("")

#                    for i in range(len(stations)):
#                        print(f"SD ", end="")
#                        for j in range(0,i):
#                            print(f"{dist(np.array(stations[i]),stations[j]):.0f}", end=" ")
#                        print("")

                    r = tdoa_solve(stations, dtoas)

                failed = ":"
                if not r.success:
                    print("Solver failed", r.message, r.fun)
                    failed = "!"

                print("r:", r.x, "fun:", r.fun)
                print(strikes[-1].itime, end=" ")
                xyz = r.x[:3]
                (lon, lat, alt) = to_lla.transform(*xyz*1000, radians=False)
                print(f"lla{failed} ({len(strikes)}) {lat:.6f} {lon:.6f} {alt:7.0f}", end=" ")

                try:
                    avec = []
                    for x in range(len(stations)):
                        rel = stations[x]-xyz
                        rel = rel / np.linalg.norm(rel)
                        rel = np.append(rel, [1])
                        avec.append(rel)

                    avec = np.array(avec)
                    avec_t = avec.transpose()
                    cov_matrix = np.linalg.inv(avec_t.dot(avec))

                    pdop = cov_matrix[0][0]+cov_matrix[1][1]+cov_matrix[2][2]
                    tdop = cov_matrix[3][3]
                    gdop = sqrt(pdop+tdop)
                    pdop = sqrt(pdop)
                    tdop = sqrt(tdop)

                    print(f"GDOP {gdop:.1f} TDOP {tdop:.1f}", end=" ")

                    if do_delta:
                        delta = ref-(xyz*1000)
                        ds = np.linalg.norm(delta)

                        flatpos = to_ecef.transform(lon, lat, drefalt)
                        flatdelta = np.array(ref) - flatpos
                        fds = np.linalg.norm(flatdelta)
                        print(f"Δ {ds:6.0f} Δf {fds:6.0f}", end=" ")

                    if do_tof:
                        print(f"/ ppm {ppm:.1f} d={r.x[3]:-6.02}ms {r.nfev}x")
                    else:
                        print(f"/ ppm {ppm:.1f} {r.nfev}x")
                except (ValueError, np.linalg.LinAlgError) as e:
                    print("Exception!", e, r.x)

                if abs(alt) < 10000 and gdop < good_gdop:
                    return [xyz]

    def consume(self, data):
        global avg
        avg.append(data)

        apos = np.average(avg, axis=0)
        (lon, lat, alt) = to_lla.transform(*apos*1000, radians=False)

        print(f"AVG: {len(avg)} {lat:.6f} {lon:.6f} {alt:.0f}", end=" ")

        if do_delta:
            delta = ref-(apos*1000)
            ds = sqrt(sum([x*x for x in delta]))
            print(f"Δ {ds:.0f}")

        print()

    def end(self):
        if len(avg) == 0:
            print("No average available")
            return
        apos = np.average(avg, axis=0)
        (lon, lat, alt) = to_lla.transform(*apos*1000, radians=False)

        print(f"FINAL AVG: ({len(avg)}) {lat:.6f} {lon:.6f} {alt:.0f}", end=" ")

        if do_delta:
            delta = ref-(apos*1000)
            ds = sqrt(sum([x*x for x in delta]))
            print(f"Δ {ds:.0f}", end="")

        print()


modes = [
    ["tdoa",        CalcTDOA,         ('perfect', 'tdelta')],
]
