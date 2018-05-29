#!/usr/bin/python
import argparse
import fileinput
import logging


import dateparser
import matplotlib.pyplot as plt
import numpy as np
import six


from .graph import add_chanel_lines_to_axis
from .line_parser import BaseLine


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def read_lines(input_files, start_time_filter, end_time_filter, type_filter):
    for line in fileinput.input(files=input_files):
        line = line.strip()
        if 'A:OK' in line and "Message: Couldn't parse:" not in line:
            raise RuntimeError('Expected "iridium-parser.py" parsed data. Found raw "iridium-extractor" data.')
        if line.startswith('ERR: '):
            continue

        base_line = BaseLine(line)
        if start_time_filter and start_time_filter > base_line.datetime:
            continue
        if end_time_filter and end_time_filter < base_line.datetime:
            continue
        if type_filter and base_line.frame_type not in type_filter:
            continue
        yield base_line


def main():
    parser = argparse.ArgumentParser(description='Visualise ????')  # TODO
    parser.add_argument('--start', metavar='DATETIME', default=None, help='Filter events before this time')
    parser.add_argument('--end', metavar='DATETIME', default=None, help='Filter events after this time')
    parser.add_argument('--filter-to-types', metavar='TYPE', default=None, help='Filter events by type (coma separated)')
    parser.add_argument('input', metavar='FILE', nargs='*', help='Files to read, if empty or -, stdin is used')
    args = parser.parse_args()

    input_files = args.input if len(args.input) > 0 else ['-']
    start_time_filter = dateparser.parse(args.start) if args.start else None
    end_time_filter = dateparser.parse(args.end) if args.end else None
    type_filter = [t.strip().upper() for t in args.filter_to_types.split(',')] if args.filter_to_types else None

    stats = {}
    number_of_lines = 0
    for base_line in read_lines(input_files, start_time_filter, end_time_filter, type_filter):
        number_of_lines += 1
        stats.setdefault(base_line.frame_type, []).append(base_line)

    logger.info('Read %d lines from input', number_of_lines)
    for frame_type, frames in six.iteritems(stats):
        logger.info(' - Read %d\t%s lines from input', len(frames), frame_type)

    fig = plt.figure()

    subplot = fig.add_subplot(1, 1, 1)
    for frame_type, frames in six.iteritems(stats):
        number_of_frames = len(frames)
        plot_data_time = np.empty(number_of_frames, dtype=np.float64)
        plot_data_freq = np.empty(number_of_frames, dtype=np.uint32)
        for i, base_line in enumerate(frames):
            plot_data_time[i] = np.uint32(base_line.datetime_unix)
            plot_data_freq[i] = np.float64(base_line.frequency)
        subplot.scatter(plot_data_time, plot_data_freq, label=frame_type)

    add_chanel_lines_to_axis(subplot)

    handles, labels = zip(*[(h, l) for (h, l) in zip(*subplot.get_legend_handles_labels()) if l in stats])
    subplot.legend(handles, labels, bbox_to_anchor=(1.04, 1), loc="upper left")

    del stats

    plt.title('frequency vs time color coded by frame type')
    plt.xlabel('time')
    plt.ylabel('frequency')
    plt.show()


if __name__ == "__main__":
    main()
