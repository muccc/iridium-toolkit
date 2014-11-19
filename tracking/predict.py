import sys
import math
import time
import datetime
import ephem

degrees_per_radian = 180.0 / math.pi

def loadTLE(filename):
    """ Loads a TLE file and creates a list of satellites."""
    f = open(filename)
    satlist = []
    l1 = f.readline()
    while l1:
        l2 = f.readline()
        l3 = f.readline()
        sat = ephem.readtle(l1,l2,l3)
        satlist.append(sat)
        #print sat.name
        l1 = f.readline()

    f.close()
    print "%i satellites loaded into list"%len(satlist)
    return satlist

def print_sat(date, sat):
    print('%s %20s: altitude %4.1f deg, azimuth %5.1f deg, range %5.1f km' %
        (date, sat.name, sat.alt * degrees_per_radian, sat.az * degrees_per_radian, sat.range/1000.))

satlist = loadTLE(sys.argv[1])

home = ephem.Observer()
home.lon = '11.566666'   # +E
home.lat = '48.133333'      # +N
home.elevation = 519 # meters

near_list = []
t = datetime.datetime.utcnow()
print 'All times in UTC!'

for dt in range(3600 * int(sys.argv[2])):
    home.date = t + datetime.timedelta(seconds = dt)
    for sat in satlist:
        sat.compute(home)

    near_sat = satlist[0]
    for sat in satlist:
        if sat.range < near_sat.range:
            near_sat = sat
    
    near_list.append((home.date, near_sat.copy()))

    #print "nearest sat:"
    #print_sat(home.date, near_sat)

near_date = near_list[0][0]
near_sat = near_list[0][1]
for date, sat in near_list:
    if near_sat.name != sat.name:
        if near_sat.range < int(sys.argv[3]) * 1000:
            print_sat(date, near_sat)
        near_sat = sat
    else:
        if sat.range < near_sat.range:
            near_sat = sat

