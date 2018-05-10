#!/usr/bin/python
# vim: set ts=4 sw=4 tw=0 et fenc=utf8 pm=:
#VOC: i-1430527570.4954-t1 421036605 1625859953  66% 0.008 219 L:no LCW(0,001111,100000000000000000000 E1) 101110110101010100101101111000111111111001011111001011010001000010010001101110011010011001111111011101111100011001001001000111001101001011001011000101111111101110110011111000000001110010001110101101001010011001101001010111101100011100110011110010110110101010110001010000100100101011010010100100100011010110101001

import sys
import matplotlib.pyplot as plt
import os
import subprocess
import fileinput
import logging
import tempfile

import numpy as np
import scipy.cluster.hierarchy as hcluster

from bits_to_dfs import bits_to_dfs

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class VocLine(object):
    def __init__(self, line):
        self.line = line
        line_split = line.split()
        self.lcw = line[8]
        #ts_base = int(line[1].split('-')[1].split('.')[0])
        ts_base = 0
        self.ts = ts_base + int(line_split[2])/1000.
        self.f = int(line_split[3])/1000.


class OnClickHandler(object):
    def __init__(self, lines):
        self.lines = lines
        self.t_start = None
        self.t_stop = None
        self.f_min = None
        self.f_max = None

    def onclick(self, event):
        logger.info('button=%d, x=%d, y=%d, xdata=%f, ydata=%f',
            event.button, event.x, event.y, event.xdata, event.ydata)

        if event.button == 1:
            self.t_start = event.xdata
            self.f_min = event.ydata
            self.t_stop = None
            self.f_max = None
        if event.button == 3:
            self.t_stop = event.xdata
            self.f_max = event.ydata
        
        if self.t_start and self.t_stop:
            self.cut_convert_play(self.t_start, self.t_stop, self.f_min, self.f_max)

    def filter_voc(self, t_start, t_stop, f_min, f_max):
        filtered_lines = []

        for voc_line in self.lines:
            ts = voc_line.ts
            f = voc_line.f
            if t_start <= ts and ts <= t_stop and \
               f_min <= f and f <= f_max:
                filtered_lines.append(voc_line.line)

        return filtered_lines

    def cut_convert_play(self, t_start, t_stop, f_min, f_max):
        logger.info('Starting to play...')
        if t_start > t_stop:
            tmp = t_stop
            t_stop = t_start
            t_start = tmp
        if f_min > f_max:
            tmp = f_max
            f_max = f_min
            f_min = tmp

        filtered_lines = self.filter_voc(t_start, t_stop, f_min, f_max)

        _, dfs_file_path = tempfile.mkstemp(suffix='.dfs')
        _, wav_file_path = tempfile.mkstemp(suffix='.wav')

        logger.info('Making dfs file %s', dfs_file_path)
        with open(dfs_file_path, 'w') as dfs_file:
            bits_to_dfs(filtered_lines, dfs_file)

        logger.info('Making wav file %s', wav_file_path)
        subprocess.check_call(['ir77_ambe_decode', dfs_file_path, wav_file_path])
        
        logger.info('Cleaning up dfs')
        os.remove(dfs_file_path)

        subprocess.check_call(['aplay', wav_file_path])

        logger.info('Cleaning up wav')
        os.remove(wav_file_path)

        logger.info('Finished Playing')


def read_lines():
    lines = []
    for line in fileinput.input():
        line = line.strip()
        if 'A:OK' in line and "Message: Couldn't parse:" not in line:
            raise RuntimeError('Expected "iridium-parser.py" parsed data. Found raw "iridium-extractor" data.')
        if 'VOC: ' in line and not "LCW(0,001111,100000000000000000000" in line:
            lines.append(VocLine(line))
    return lines

def main():
    lines = read_lines()
    number_of_lines = len(lines)
    logger.info('Read %d VOC lines from input', number_of_lines)

    tsl = np.empty(number_of_lines)
    fl = np.empty(number_of_lines)
    plot_data = np.empty((number_of_lines, 2))
    for i, voc_line in enumerate(lines):
        tsl[i] = voc_line.ts
        fl[i] = voc_line.f
        plot_data[i][0] = voc_line.ts
        plot_data[i][1] = voc_line.f

    fig = plt.figure()
    thresh = 1.5
    clusters = hcluster.fclusterdata(plot_data, thresh, criterion="distance")

    ax = fig.add_subplot(1, 1, 1)
    ax.scatter(*np.transpose(plot_data), c=clusters)

    on_click_handler = OnClickHandler(lines)
    cid = fig.canvas.mpl_connect('button_press_event', on_click_handler.onclick)

    plt.title('Click once left and once right to define an area.\nThe script will try to play iridium using ir77_ambe_decode and aplay.')
    plt.xlabel('time')
    plt.ylabel('frequency')
    plt.show()


if __name__ == "__main__":
    main()
