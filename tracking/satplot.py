#!/usr/bin/env python
# vim: set ts=4 sw=4 tw=0 et fenc=utf8 pm=:
import sys
import matplotlib.pyplot as plt
import ephem
from datetime import datetime
import sats
import math
import time

degrees_per_radian = 180.0 / math.pi
radian_per_degree = math.pi / 180.0
satlist = sats.loadTLE(sys.argv[1])
start = int(sys.argv[2])
duration = int(sys.argv[3])

visible = []
for dt in range(0, duration, 10):
    sats.home.date = datetime.utcfromtimestamp(start + dt)

    for sat in satlist:
        sat.compute(sats.home)
        if sat.alt > radian_per_degree * 8:
        #    sats.print_sat(sat)
            #visible.append((start + dt, sat.az * degrees_per_radian, int(sat.name.split()[1])))
            visible.append((start + dt, math.sin(sat.sublat), int(sat.name.split()[1])))

    #near_sat = satlist[0]
    #for sat in satlist:
    #    if sat.range < near_sat.range:
    #        near_sat = sat

    #print "nearest sat:"
    #sats.print_sat(near_sat)

    #time.sleep(1)

plt.scatter([v[0] for v in visible], [v[1] for v in visible], c = [v[2] for v in visible])

#plt.scatter(x = tsl, y = fl, s = 400, c = cl, alpha=.5)
#plt.colorbar()
#plt.plot(tsl,cl)
#plt.scatter(tsl,cl)
#plt.hist(cl, 500)
#plt.scatter(mystery, [1]*len(mystery))
#plt.scatter([m[0] for m in mystery], [m[1] for m in mystery])
#print mystery
plt.show()

