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

frames = collections.OrderedDict()
frames['IMS'] = ['darkgreen', 'x', [], []]
frames['MSG'] = ['cyan', 'o', [], []]

frames['IRA'] = ['red', 'x', [], []]

frames['ISY'] = ['grey', 'o', [], []]

frames['IBC'] = ['pink', 'o', [], []]

frames['IDA'] = ['orange', 'o', [], []]

frames['IIU'] = ['magenta', 'o', [], []]
frames['IIQ'] = ['lightgreen', 'o', [], []]
frames['IIP'] = ['green', 'o', [], []]

frames['VOC'] = ['blue', 'o', [], []]
frames['VDA'] = ['red', 'o', [], []]
frames['VOD'] = ['cyan', 'x', [], []]

#frames['IRI'] = ['purple', 'x', [], []]
#frames['RAW'] = ['grey', 'x', [], []]

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

    if type in frames:
        frames[type][2].append(ts)
        frames[type][3].append(f)

for t in frames:
    f = frames[t]
    plt.scatter(y=f[3], x=f[2], c=f[0], label=t, alpha=1, edgecolors=f[0], marker=f[1], s=20)

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

