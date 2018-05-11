#!/usr/bin/python

import sys
import os
import subprocess
import fileinput
import logging
import tempfile
from datetime import datetime
import argparse


import matplotlib.pyplot as plt
import numpy as np
import scipy.cluster.hierarchy as hcluster
import dateparser


from .voc import VocLine


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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


def read_lines(input_files, start_time_filter, end_time_filter):
    lines = []
    for line in fileinput.input(files=input_files):
        line = line.strip()
        if 'A:OK' in line and "Message: Couldn't parse:" not in line:
            raise RuntimeError('Expected "iridium-parser.py" parsed data. Found raw "iridium-extractor" data.')
        if 'VOC: ' in line and not "LCW(0,001111,100000000000000000000" in line:
            voc_line = VocLine(line)
            if start_time_filter and start_time_filter > voc_line.datetime():
                continue
            if end_time_filter and end_time_filter < voc_line.datetime():
                continue
            lines.append(voc_line)
    return lines

def main():
    parser = argparse.ArgumentParser(description='Convert iridium-parser.py VOC output to DFS')
    parser.add_argument('--start', metavar='DATETIME', default=None, help='Filter events before this time')
    parser.add_argument('--end', metavar='DATETIME', default=None, help='Filter events after this time')
    parser.add_argument('input', metavar='FILE', nargs='*', help='Files to read, if empty or -, stdin is used')
    args = parser.parse_args()

    input_files = args.input if len(args.input) > 0 else ['-']
    start_time_filter = dateparser.parse(args.start) if args.start else None
    end_time_filter = dateparser.parse(args.end) if args.end else None

    lines = read_lines(input_files, start_time_filter, end_time_filter)
    number_of_lines = len(lines)
    logger.info('Read %d VOC lines from input', number_of_lines)

    if number_of_lines == 0:
        print('No usable data found')
        sys.exit(1)

    plot_data = np.empty((number_of_lines, 2))
    for i, voc_line in enumerate(lines):
        plot_data[i][0] = voc_line.ts
        plot_data[i][1] = np.float64(voc_line.f)

    distances = hcluster.distance.pdist(plot_data)
    thresh = 2 * distances.min()
    clusters = hcluster.fclusterdata(plot_data, thresh, criterion="distance")

    fig = plt.figure()
    #fig.autofmt_xdate()
    on_click_handler = OnClickHandler(lines)
    fig.canvas.mpl_connect('button_press_event', on_click_handler.onclick)
    
    ax = fig.add_subplot(1, 1, 1)
    ax.scatter(*np.transpose(plot_data), c=clusters)
    #ax.xaxis_date()
    ax.grid(True)

    plt.title('Click once left and once right to define an area.\nThe script will try to play iridium using ir77_ambe_decode and aplay.')
    plt.xlabel('time')
    plt.ylabel('frequency')
    plt.show()


if __name__ == "__main__":
    main()
