#!/usr/bin/env python3
# vim: set ts=4 sw=4 tw=0 et fenc=utf8 pm=:
import sys
import matplotlib.pyplot as plt
import collections
from util import parse_channel

if len(sys.argv)<2:
    f = open("/dev/stdin")
else:
    f = open(sys.argv[1])

f.readline()

max_f = None
min_f = None
min_ts = None
max_ts = None

colors =['#cab2d6','#33a02c','#fdbf6f','#ffff99','#6a3d9a','#e31a1c','#ff7f00','#fb9a99','#b2df8a','#1f78b4','#aaaaaa', '#a6cee3', '#dddd77']

frames = collections.OrderedDict()
frames['IMS'] = [colors[ 0], 'x', 1]
frames['MSG'] = [colors[ 1], 'o', 1]

frames['IRA'] = [colors[ 2], 'x', 1]

frames['ITL'] = [colors[ 9], 'x', 1]

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
frames['VO6'] = [colors[12], 'o', 1]

frames['IRI'] = ['purple',   'x', 0]
frames['RAW'] = ['grey',     'x', 0]
frames['NC1'] = ['grey',     'x', 0]

frames['NXT'] = [colors[ 6], 'x', 1]

data=collections.OrderedDict()
for t in frames:
    data[t]=[[],[],None]

newtypes=[]
for line in f:
    line = line.strip().split()
    ftype = line[0][:-1]
    if ftype == "ERR":
        continue
    #ts_base = int(line[1].split('-')[1].split('.')[0])
    ts_base = 0
    ts = ts_base + float(line[2])/1000.
    f = line[3]
    if "|" in f:
        f = parse_channel(f)
    else:
        f = int(f)

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

    if ftype in data:
        data[ftype][0].append(ts)
        data[ftype][1].append(f)
    else:
        if not ftype in newtypes:
            print("unhandled frame type:",ftype)
            newtypes.append(ftype)

for t in frames:
    f = frames[t]
    if len(data[t][0])==0:
        del data[t]
        continue
    data[t][2]= plt.scatter(y=data[t][1], x=data[t][0], c=f[0], label=t, alpha=1, facecolors=f[0], marker=f[1], s=20)

leg=plt.legend(loc='upper right')
leg.set_draggable(1)

# Get to the legend entries
pat=leg.get_children()
#print "pat:",pat
#print "c:",pat[0].get_children()
#print "cc:",pat[0].get_children()[1].get_children()
#print "ccc:",pat[0].get_children()[1].get_children()[0].get_children()
leg_items=pat[0].get_children()[1].get_children()[0].get_children()

def legend_set(leg_item,onoff):
    # find orig plot collection corresponding to the legend item line
    ft=leg_map[leg_item]
    item=data[ft][2]
    if onoff==-1:
        onoff = not item.get_visible()
    item.set_visible(onoff)

    dots,txts=leg_item.get_children()
    dot=dots.get_children()[0]
    txt=txts.get_children()[0]

    if onoff:
        txt.set_alpha(1.0)
        dot.set_alpha(1.0)
    else:
        txt.set_alpha(0.2)
        dot.set_alpha(0.2)

leg_map=dict()
for i, ft in enumerate(data):
    # Make legend items pickable and save references to plot collection object
    leg_items[i].set_picker(5)  # 5 pts tolerance
    leg_map[leg_items[i]]=ft
    if frames[ft][2]==0:
        legend_set(leg_items[i],0)

fig=plt.gcf()

def onpick(event):
    # on pick event toggle the visibility
    x=event.artist
    if type(event.artist).__name__ == 'Legend':
        return
    leg_item = event.artist
    legend_set(event.artist,-1)
    fig.canvas.draw()

fig.canvas.mpl_connect('pick_event', onpick)

#plt.colorbar()
#plt.ylim([min_f, max_f])
#plt.ylim([1624.95e6, 1626.5e6])
#plt.ylim([1616e6, 1627e6])
plt.ylim([1618e6, 1626.7e6])
#plt.xlim([1618e6, 1626.7e6])
ax = plt.gca()
ax.set_title('Click on legend line to toggle line on/off')
#ax.ticklabel_format(useOffset=False)
#ax.set_axis_bgcolor('white')

plt.subplots_adjust(left=0.1, right=0.95, top=0.95, bottom=0.05)

plt.xlim([min_ts, max_ts])
#plt.ylim([min_ts, max_ts])

plt.show()

