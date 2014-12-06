import ephem
import math
degrees_per_radian = 180.0 / math.pi

def loadTLE(filename):
    """ Loads a TLE file and creates a list of satellites."""
    f = open(filename)
    satlist = []
    l1 = f.readline()
    while l1:
        l2 = f.readline()
        l3 = f.readline()
        if not '-' in l1:
            sat = ephem.readtle(l1,l2,l3)
            satlist.append(sat)
        #print sat.name
        l1 = f.readline()

    f.close()
    print "%i satellites loaded into list"%len(satlist)
    return satlist

def print_sat(sat):
    print('%s: altitude %4.1f deg, azimuth %5.1f deg, range %5f km' %
        (sat.name, sat.alt * degrees_per_radian, sat.az * degrees_per_radian, sat.range/1000.))

home = ephem.Observer()
home.lon = '11.566666'   # +E
home.lat = '48.133333'      # +N
home.elevation = 519 # meters


