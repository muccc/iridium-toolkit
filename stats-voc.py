#!/usr/bin/python
# vim: set ts=4 sw=4 tw=0 et fenc=utf8 pm=:
#VOC: i-1430527570.4954-t1 421036605 1625859953  66% 0.008 219 L:no LCW(0,001111,100000000000000000000 E1) 101110110101010100101101111000111111111001011111001011010001000010010001101110011010011001111111011101111100011001001001000111001101001011001011000101111111101110110011111000000001110010001110101101001010011001101001010111101100011100110011110010110110101010110001010000100100101011010010100100100011010110101001

import sys
import matplotlib.pyplot as plt
import os

f = open(sys.argv[1])

tsl = []
fl = []
for line in f:
    line = line.strip()
    if 'VOC: ' in line and not "LCW(0,001111,100000000000000000000" in line:
        line = line.split()
        lcw = line[8]
        #if lcw.split(',')[2][0] == '0':
        #    continue
        ts_base = int(line[1].split('-')[1].split('.')[0])
        ts = ts_base + int(line[2])/1000.
        f = int(line[3])/1000.
        tsl.append(ts)
        fl.append(f)

print len(tsl)

fig = plt.figure()
ax = fig.add_subplot(111)
ax.scatter(x = tsl, y = fl)

t_start = None
t_stop = None
f_min = None
f_max = None

def cut_convert_play(t_start, t_stop, f_min, f_max):
    if t_start and t_stop:
        if t_start > t_stop:
            tmp = t_stop
            t_stop = t_start
            t_start = tmp
        if f_min > f_max:
            tmp = f_max
            f_max = f_min
            f_min = tmp

    f = open(sys.argv[1])
    f_out = open('/tmp/sample.bits', 'w')
    for line in f:
        line = line.strip()
        if 'VOC: ' in line and not "LCW(0,001111,100000000000000000000" in line:
            split_line = line.split()
            lcw = split_line[8]
            #if lcw.split(',')[2][0] == '0':
            #    continue
            ts_base = int(split_line[1].split('-')[1].split('.')[0])
            ts = ts_base + int(split_line[2])/1000.
            f = int(split_line[3])/1000.
            if t_start <= ts <= t_stop and f_min <= f <= f_max:
                f_out.write(line + "\n")
    f_out.close()
    os.system("mangle-sample")


def onclick(event):
    global t_start, t_stop, f_min, f_max
    print 'button=%d, x=%d, y=%d, xdata=%f, ydata=%f'%(
        event.button, event.x, event.y, event.xdata, event.ydata)
    if event.button == 1:
        t_start = event.xdata
        f_min = event.ydata
        t_stop = None
        f_max = None
    if event.button == 3:
        t_stop = event.xdata
        f_max = event.ydata
    
    if t_start and t_stop:
        cut_convert_play(t_start, t_stop, f_min, f_max)


cid = fig.canvas.mpl_connect('button_press_event', onclick)


plt.show()

