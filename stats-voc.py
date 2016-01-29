#!/usr/bin/python
# vim: set ts=4 sw=4 tw=0 et fenc=utf8 pm=:
#VOC: i-1430527570.4954-t1 421036605 1625859953  66% 0.008 219 L:no LCW(0,001111,100000000000000000000 E1) 101110110101010100101101111000111111111001011111001011010001000010010001101110011010011001111111011101111100011001001001000111001101001011001011000101111111101110110011111000000001110010001110101101001010011001101001010111101100011100110011110010110110101010110001010000100100101011010010100100100011010110101001

import sys
import matplotlib.pyplot as plt
import os

def filter_voc(t_start = None, t_stop = None, f_min = None, f_max = None):
    tsl = []
    fl = []
    lines = []
    f = open(sys.argv[1])

    for line in f:
        line = line.strip()
        if 'VOC: ' in line and not "LCW(0,001111,100000000000000000000" in line:
            line_split = line.split()
            lcw = line[8]
            #ts_base = int(line[1].split('-')[1].split('.')[0])
            ts_base = 0
            ts = ts_base + int(line_split[2])/1000.
            f = int(line_split[3])/1000.
            if ((not t_start or t_start <= ts) and
                    (not t_stop or ts <= t_stop) and
                    (not f_min or f_min <= f) and
                    (not f_max or f <= f_max)):
                tsl.append(ts)
                fl.append(f)
                lines.append(line)
    return tsl, fl, lines


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

    f_out = open('/tmp/voice.bits', 'w')
    _, _, lines = filter_voc(t_start, t_stop, f_min, f_max)
    for line in lines:
        f_out.write(line + "\n")
    f_out.close()
    os.system("play-iridium-ambe /tmp/voice.bits")


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

def main():
    tsl, fl, _ = filter_voc()

    print len(tsl)

    fig = plt.figure()
    ax = fig.add_subplot(111)
    ax.scatter(x = tsl, y = fl)

    t_start = None
    t_stop = None
    f_min = None
    f_max = None


    cid = fig.canvas.mpl_connect('button_press_event', onclick)

    plt.title("Click once left and once rigth to define an aerea. The script will try to play iridium using the play-iridium-ambe shell script.")
    plt.show()


if __name__ == "__main__":
    main()
