import sys
import numpy
import pseudoranging

debug = False

# create input file like this:
# python3 ibc_position_interpolator.py iridium.ibc iridium.ira
# See ibc_position_interpolator.py how to create iridium.ibc and iridium.ira

#https://stackoverflow.com/questions/30307311/python-pyproj-convert-ecef-to-lla
import pyproj
ecef = pyproj.Proj(proj='geocent', ellps='WGS84', datum='WGS84')
lla = pyproj.Proj(proj='latlong', ellps='WGS84', datum='WGS84')

to_lla = pyproj.Transformer.from_proj(ecef, lla)
to_ecef = pyproj.Transformer.from_proj(lla, ecef)

# https://www.koordinaten-umrechner.de/decimal/48.153543,11.560702?karte=OpenStreetMap&zoom=19
lat=48.153543
lon=11.560702
alt=542

ox, oy, oz = to_ecef.transform(lon, lat, alt, radians=False)
observer = numpy.array((ox, oy, oz))

print("Observer:",lon,lat,alt)
print("Observer:",ox,oy,oz)


ibc_pos=open(sys.argv[1])

good = []
errors = []
height_errors = []
bad = 0
known_bad = 0
last_result = numpy.array([0, 0, 0])

last_observation = {}
for line in ibc_pos:
    tu,s,x,y,z,deltat=line.split(None,6) # time_unix, sat, x, z, y, time_unix - time_iridium

    tu = int(tu)/1e9
    s = int(s)
    xyz = [float(x), float(y), float(z)]
    dt = int(deltat)/1e9

    last_observation[s] = (tu, s, xyz, dt)

    # Find all SVs which we saw in the last 60 seconds
    concurent_observation = {}
    for lo in last_observation.values():
        if tu - lo[0] < 60:
            concurent_observation[lo[1]] = lo

    # If we have more than 3, try to solve
    if len(concurent_observation) > 3:
        pseudoranges = []

        for obs in concurent_observation.values():
            pseudoranges.append((obs[2], obs[3]))

        # Sometimes it needs a few iterations to converge
        result = last_result
        for i in range(4):
            result = pseudoranging.solve(pseudoranges, result)

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

print("average cartesian error:", numpy.average(errors), "(", numpy.average(height_errors), ")")

average_position = numpy.average(good, 0)

print("average cartesian position:", average_position)
print("average cartesian position error:", numpy.linalg.norm(average_position - observer))
print("average cartesian position height error:", numpy.linalg.norm(average_position) - numpy.linalg.norm(observer))

lat, lon, alt = to_lla.transform(average_position[0], average_position[1], average_position[2], radians=False)
print("average cartesian position to lla", lon, lat, alt)

