#!/usr/bin/env python3

# vim: set ts=4 sw=4 tw=0 et pm=:

# proper input format:
# iridium-parser.py --filter IridiumRAMessage --format ra_sat,ra_cell,ra_pos_x,ra_pos_y,ra_pos_z,globalns

from math import atan2,sqrt,pi,sin,cos
import fileinput
import getopt
import sys
import matplotlib.pyplot as plt
import numpy as np

options, remainder = getopt.getopt(sys.argv[1:], 'vd:s:', [
                                                         'verbose',
                                                         'direction=',
                                                         'sat='
                                                            ])
debugpos=False
verbose=False
satno=None
direction=None

# Inclination in deg
inc0=84.0

for opt, arg in options:
    if opt in ('-v', '--verbose'):
        verbose = True
    elif opt in ('-s','--sat'):
        satno=int(arg)
    elif opt in ('-d','--direction'):
        try:
            direction=int(arg)
        except ValueError:
            if arg=="n":
                direction=1
            elif arg=="s":
                direction=-1
            else:
                raise

# Preallocate arrays
xs=[[] for y in range(50)]
ys=[[] for y in range(50)]
seen=[0]* 255
north=[0]* 255
pos=[None]* 255

for line in fileinput.input(remainder):
        sat,cell,x,y,z,nstime=line.split(None,6)
        sat=int(sat)
        if satno and sat!=satno:
             continue

        cell=int(cell)
        # Convert position to km
        x=int(x)*4
        y=int(y)*4
        z=int(z)*4
        lat = atan2(z,sqrt(x**2+y**2))*180/pi
        lon = atan2(y,x)*180/pi
        alt = sqrt(x**2+y**2+z**2)

        gtime=float(nstime)/10e9
        if debugpos:
            print("")
            print("sat:",sat,"cell:",cell,"x/y/z",x,y,z,"alt:",alt)
        if alt>7000:
            if debugpos: print("High flyer")
            if seen[sat]>0:
                if debugpos: print("- timedelta",gtime-seen[sat])
                if gtime-seen[sat] < 10:
                    (ox,oy,oz)=pos[sat]
                    if debugpos: print("- posdelta",x-ox,y-oy,z-oz)
                    if z-oz==0:
                        continue
                    if(z-oz>0):
                        north[sat]=1
                    else:
                        north[sat]=-1
                else:
                    north[sat]=0
            if debugpos: print("- north:",north[sat])
            seen[sat]=gtime
            pos[sat]=(x,y,z)
        else:
            if debugpos: print("Low flyer")
            if not seen[sat]:
                    if debugpos: print("# Sat unknown")
                    continue

            td=gtime-seen[sat]
            if debugpos: print("- timedelta:",td)
            if debugpos: print("- north:",north[sat])
            if td > 10:
                if debugpos: print("# Too old")
                north[sat]=0
                continue
            if direction is not None:
                if direction!=north[sat]:
                    if debugpos: print("# ignore direction")
                    continue

            if north[sat] == 0:
                if debugpos: print("# Unknown direction")
                continue

            (ox,oy,oz)=pos[sat]

            lat = atan2(oz,sqrt(ox**2+oy**2))
            lon = atan2(oy,ox)
            alt = sqrt(ox**2+oy**2+oz**2)*4

            inc=-(90-inc0)/180*pi
            if (north[sat]<0):
                inc=-(180-(90-inc0))/180*pi

            if debugpos:
                print("- lat/lon/alt: %+06.2f/%+07.2f %+05d"%(lat*180/pi,lon*180/pi,alt))

                # rotate lon to 0 (around z)
                x1=ox*cos(-lon)-oy*sin(-lon)
                y1=ox*sin(-lon)+oy*cos(-lon)
                z1=oz
                # rotate lat to 0(equator)  (around y)
                x2=x1*cos(-lat)-z1*sin(-lat)
                y2=y1
                z2=x1*sin(-lat)+z1*cos(-lat)
                # rotate inclination to north (around x) [inclination]
                x3=x2
                y3=y2*cos(-inc)-z2*sin(-inc)
                z3=y2*sin(-inc)+z2*cos(-inc)

                print("- sat-ox/oy/oz: %7.1f %7.1f %7.1f"%(ox,oy,oz))
                print("- sat-x1/y1/z1: %7.1f %7.1f %7.1f"%(x1,y1,z1))
                print("- sat-x2/y2/z2: %7.1f %7.1f %7.1f"%(x2,y2,z2))
                print("- sat-x3/y3/z3: %7.1f %7.1f %7.1f"%(x3,y3,z3))
                print("")

            # rotate by lon to 0 (around z)
            x1=x*cos(-lon)-y*sin(-lon)
            y1=x*sin(-lon)+y*cos(-lon)
            z1=z
            # rotate by lat to equator  (around y)
            x2=x1*cos(-lat)-z1*sin(-lat)
            y2=y1
            z2=x1*sin(-lat)+z1*cos(-lat)
            # rotate inclination to north (around x) [inclination]
            x3=x2
            y3=y2*cos(-inc)-z2*sin(-inc)
            z3=y2*sin(-inc)+z2*cos(-inc)
            if debugpos:
                print("- POS-ox/oy/oz: %7.1f %7.1f %7.1f"%(ox,oy,oz))
                print("- POS-x1/y1/z1: %7.1f %7.1f %7.1f"%(x1,y1,z1))
                print("- POS-x2/y2/z2: %7.1f %7.1f %7.1f"%(x2,y2,z2))
                print("- POS-x3/y3/z3: %7.1f %7.1f %7.1f"%(x3,y3,z3))

            xs[cell].append(y3)
            ys[cell].append(z3)

if verbose: print("------------ PLOT --------------")

colormap = plt.cm.gist_ncar
colorst = [colormap(i) for i in np.linspace(0, 0.9,len(xs))]
for cnt in range(len(xs)):
    if len(xs[cnt])==0:
        continue
    # Calculate center of mass for circle
    if verbose: print("Cell: ",cnt)
    if verbose: print("- Points: ",len(xs[cnt]))
    xc=sum(xs[cnt])/len(xs[cnt])
    yc=sum(ys[cnt])/len(ys[cnt])
    if verbose: print("- Center: ",xc,yc)
    md=0
    for t in range(len(xs[cnt])):
        d=((xs[cnt][t]-xc)**2+(ys[cnt][t]-yc)**2)**0.5
        if md<d:
            md=d
    if verbose: print("- Dist: ",md)
    ax=plt.gcf().gca()
    ax.add_artist(plt.Circle((xc, yc), md+10, edgecolor=colorst[cnt], facecolor="none"))
    p=plt.scatter(x=xs[cnt], y=ys[cnt], color=colorst[cnt], edgecolor="none",label="%02d (%d)"%(cnt,len(xs[cnt])) )
    plt.annotate(str(cnt),(xc+10+md,yc+10+md))

#plt.scatter(x=0,y=0,c='black')
plt.xlabel('Y/km')
plt.ylabel('Z/km',labelpad=-30)

fig = plt.gcf()
ax = fig.gca()

ax.legend(fontsize='small')
ax.spines['right'].set_position('zero')
ax.spines['top'].set_position('zero')
ax.set_aspect('equal', 'datalim')
#plt.colorbar(p)

if satno:
    title='Beam Pattern for Sat %d'%satno
else:
    title='Beam Pattern plot'
if direction is not None:
    if direction == 1:
        title=title+' (North)'
    elif direction == -1:
        title=title+' (South)'
    else:
        raise

plt.title(title)
fig.canvas.manager.set_window_title(title)

# Make plot area larger
fig.tight_layout()
plt.subplots_adjust(left=0.05,bottom=0.05, top=0.95)

plt.show()

