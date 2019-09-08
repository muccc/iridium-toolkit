#!/usr/bin/python
# vim: set ts=4 sw=4 tw=0 et fenc=utf8 pm=:
import sys
import matplotlib.pyplot as plt
import collections

f = open(sys.argv[1])

f.readline()

max_f = None
min_f = None
min_ts = None
max_ts = None

colors =['#cab2d6','#33a02c','#fdbf6f','#ffff99','#6a3d9a','#e31a1c','#ff7f00','#fb9a99','#b2df8a','#1f78b4','#aaaaaa', '#a6cee3']

frames = collections.OrderedDict()
frames['IMS'] = [colors[ 0], 'x', 1]
frames['MSG'] = [colors[ 1], 'o', 1]

frames['IRA'] = [colors[ 2], 'x', 1]

frames['ISY'] = [colors[ 3], 'o', 1]

frames['IBC'] = [colors[ 4], 'o', 1]

frames['IU3'] = [colors[ 5], 'o', 1]

frames['IDA'] = [colors[ 6], 'o', 1]

frames['IIU'] = [colors[ 7], 'o', 1]
frames['IIR'] = [colors[10], 'o', 1]
frames['IIP'] = [colors[ 9], 'o', 1]
frames['IIQ'] = [colors[ 8], 'o', 1]

frames['VOC'] = [colors[11], 'o', 1]
frames['VOD'] = [colors[ 1], 'x', 1]
frames['VDA'] = [colors[ 2], 'o', 1]

frames['IRI'] = ['purple',   'x', 0]
frames['RAW'] = ['grey',     'x', 0]

data=collections.OrderedDict()
for t in frames:
    data[t]=[[],[]]

for line in f:
    line = line.strip().split()
    type = line[0][:-1]
    #ts_base = int(line[1].split('-')[1].split('.')[0])
    ts_base = 0
    ts = ts_base + float(line[2])/1000.
    f = int(line[3])
    #len = int(line[6])
    #strength = float(line[5])

    if max_f == None or max_f < f:
        max_f = f
    if min_f == None or min_f > f:
        min_f = f
    if max_ts == None or max_ts < ts:
        max_ts = ts
    if min_ts == None or min_ts > ts:
        min_ts = ts

    if type in data:
        data[type][0].append(ts)
        data[type][1].append(f)

for t in frames:
    f = frames[t]
    if f[2]==0:
        continue
    plt.scatter(y=data[t][1], x=data[t][0], c=f[0], label=t, alpha=1, edgecolors=f[0], marker=f[1], s=20)

#plt.colorbar()
#plt.ylim([min_f, max_f])
#plt.ylim([1624.95e6, 1626.5e6])
#plt.ylim([1616e6, 1627e6])
plt.ylim([1618e6, 1626.7e6])
#plt.xlim([1618e6, 1626.7e6])
#ax = plt.gca()
#ax.ticklabel_format(useOffset=False)
#ax.set_axis_bgcolor('white')


plt.xlim([min_ts, max_ts])
#plt.ylim([min_ts, max_ts])

plt.legend()
plt.show()

