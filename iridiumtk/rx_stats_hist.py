#!/usr/bin/env python
# vim: set ts=4 sw=4 tw=0 et pm=:

# Parses .bits files and displays the distribution
# of the "HIST_DIMENTION_KEY" of received frames

from __future__ import print_function

import argparse
from collections import namedtuple
from datetime import datetime
import fileinput
import logging
import re
import sys


import dateparser
try:
    import matplotlib.pyplot as plt
except ImportError:
    print('Failed to import matplotlib. This prevents any GUI.' , file=sys.stderr)


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


Dimension = namedtuple('Dimension', ['key', 'bin_size'])
HIST_DIMENSIONS = {
    'frequency': Dimension('freq', 10000),
    'length': Dimension('length', 1),
    'time': Dimension('timestamp', 3600),
}


def extract_timestamp(filename, dt):
    mm = re.match(r'i-(\d+(?:\.\d+)?)-[vbsrtl]1.([a-z])([a-z])', filename)
    if mm:
        b26 = (ord(mm.group(2)) - ord('a')) * 26 + ord(mm.group(3)) - ord('a')
        timestamp = float(mm.group(1)) + float(dt) / 1000 + b26 * 600
        return timestamp

    mm = re.match(r'i-(\d+(?:\.\d+)?)-[vbsrtl]1(?:-o[+-]\d+)?$', filename)
    if mm:
        timestamp = float(mm.group(1)) + float(dt) / 1000
        return timestamp

    mm = re.match(r'(\d\d)-(\d\d)-(20\d\d)T(\d\d)-(\d\d)-(\d\d)-[sr]1', filename)
    if mm:
        month, day, year, hour, minute, second = map(int, mm.groups())
        timestamp = datetime(year, month, day, hour, minute, second)
        timestamp = (timestamp - datetime(1970, 1, 1)).total_seconds()
        timestamp += float(dt) / 1000
        return timestamp

    return 0


def parse_line_to_message(line):
    line = line.split()
    if not line[0] == 'RX' and ('A:OK' not in line or len(line) < 10):
        return None
    access = True
    lead_out = 'L:OK' in line
    name = line[1]
    if name == "X":
        timestamp = float(line[2])
    else:
        timestamp = extract_timestamp(name, line[2])
    freq = int(line[3])
    confidence = int(line[6][:-1])
    strength = float(line[7])
    length = int(line[8])
    if name == "X":
        error = line[9] == 'True'
        msgtype = line[10]
    else:
        error = False
        msgtype = None

    return {
        'name': name,
        'timestamp': timestamp,
        'freq': freq,
        'access': access,
        'lead_out': lead_out,
        'confidence': confidence,
        'strength': strength,
        'length': length,
        'error': error,
        'msgtype': msgtype,
    }


def read_lines(input_files, start_time_filter, end_time_filter):
    for line in fileinput.input(files=input_files):
        try:
            message = parse_line_to_message(line)
        except (IndexError, ValueError):
            continue
        if not message:
            continue
        timestamp = datetime.utcfromtimestamp(message['timestamp'])
        if start_time_filter and start_time_filter > timestamp:
            continue
        if end_time_filter and end_time_filter < timestamp:
            continue
        yield message


def main():
    parser = argparse.ArgumentParser(description='Convert iridium-parser.py VOC output to DFS')
    parser.add_argument('--start', metavar='DATETIME', type=str, default=None, help='Filter events before this time')
    parser.add_argument('--end', metavar='DATETIME', type=str, default=None, help='Filter events after this time')

    parser.add_argument('--bin-size', metavar='INT', type=int, default=None, help='Size of bins')
    parser.add_argument('--minimum-length', metavar='INT', type=int, default=0)
    parser.add_argument('--minimum-confidence', metavar='INT', type=int, default=0)
    parser.add_argument('--lead-out-required', metavar='INT', type=bool, default=False)
    parser.add_argument('--show-errors', metavar='INT', type=bool, default=False)

    parser.add_argument('--dimension', choices=HIST_DIMENSIONS.keys(), required=True)

    parser.add_argument('input', metavar='FILE', nargs='*', help='Files to read, if empty or -, stdin is used')
    args = parser.parse_args()

    input_files = args.input if len(args.input) > 0 else ['-']
    start_time_filter = dateparser.parse(args.start) if args.start else None
    end_time_filter = dateparser.parse(args.end) if args.end else None

    dimension = HIST_DIMENSIONS[args.dimension]

    bin_size = args.bin_size if args.bin_size else dimension.bin_size
    minimum_confidence = args.minimum_confidence
    minimum_length = args.minimum_length
    lead_out_required = args.lead_out_required
    show_errors = args.show_errors

    lines = list(read_lines(input_files, start_time_filter, end_time_filter))
    number_of_lines = len(lines)
    logger.info('Read %d lines from input', number_of_lines)

    if number_of_lines == 0:
        print('No usable data found', file=sys.stderr)
        sys.exit(1)

    data = [s[dimension.key] for s in lines if s['length'] > minimum_length and s['confidence'] > minimum_confidence and (s['lead_out'] or not lead_out_required) and (s['error'] == show_errors) and s['freq'] < 1.626e9]

    bins = int((max(data) - min(data)) / bin_size)

    title = "File: %s : Distribution of message %s. Bin Size: %d, Minimum Confidence: %d" % (input_files, args.dimension, bin_size, minimum_confidence)
    if lead_out_required:
        title += ', lead out needs to be present'
    else:
        title += ', lead out does not need to be present'
    if show_errors:
        title += " and having decoding errors"

    fig = plt.figure()
    subplot = fig.add_subplot(1, 1, 1)
    subplot.hist(data, bins)

    plt.title(title)
    plt.xlabel(args.dimension)
    plt.ylabel('count')
    plt.show()


if __name__ == '__main__':
    main()
