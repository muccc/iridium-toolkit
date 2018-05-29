#!/usr/bin/env python

import argparse
import sys
import fileinput
import getopt
import datetime
import re
import logging


import dateparser


from .line_parser import BaseLine, IraLine, MsgLine


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MessageTypeProcessor(object):
    def __init__(self, base_frames):
        self._base_frames = base_frames

    def frames(self):
        selected = []
        for base_frame in self._base_frames:
            if base_frame.frame_type != 'MSG':
                continue
            message_frame = MsgLine(base_frame.raw_line)
            yield 'Message "{}"'.format(message_frame.message_data_escaped)


class PageTypeProcessor(object):
    def __init__(self, base_frames):
        self._base_frames = base_frames

    def frames(self):
        for base_frame in self._base_frames:
            if base_frame.frame_type != 'IRA':
                continue
            ira_frame = IraLine(base_frame.raw_line)
            
            for page in ira_frame.pages:
                yield "%02d %02d %s %s %03d : %s %s" % (ira_frame.satellite, ira_frame.beam, ira_frame.position.x, ira_frame.position.y, ira_frame.altitude, page.tmsi, page.msc_id)


FRAME_TYPES = {
    'messages': MessageTypeProcessor,
    'pages': PageTypeProcessor,
}


def parse_to_base_frame_and_filter_time(input_files, start_time_filter, end_time_filter):
    for line in fileinput.input(files=input_files):
        line = line.strip()
        if 'A:OK' in line and "Message: Couldn't parse:" not in line:
            raise RuntimeError('Expected "iridium-parser.py" parsed data. Found raw "iridium-extractor" data.')
        if line.startswith('ERR: '):
            continue
        if line.startswith('Warning:'):
            continue

        base_line = BaseLine(line)
        if start_time_filter and start_time_filter > base_line.datetime:
            continue
        if end_time_filter and end_time_filter < base_line.datetime:
            continue
        yield base_line

def main():
    parser = argparse.ArgumentParser(description='Convert iridium-parser.py VOC output to DFS')
    parser.add_argument('--start', metavar='DATETIME', type=str, default=None, help='Filter events before this time')
    parser.add_argument('--end', metavar='DATETIME', type=str, default=None, help='Filter events after this time')

    parser.add_argument('--type', choices=FRAME_TYPES.keys(), required=True)

    parser.add_argument('input', metavar='FILE', nargs='*', help='Files to read, if empty or -, stdin is used')
    args = parser.parse_args()

    input_files = args.input if len(args.input) > 0 else ['-']
    start_time_filter = dateparser.parse(args.start) if args.start else None
    end_time_filter = dateparser.parse(args.end) if args.end else None

    type_processor = FRAME_TYPES[args.type]

    base_frames = parse_to_base_frame_and_filter_time(input_files, start_time_filter, end_time_filter)

    logger.info('Staring to parse frames')
    for frame in type_processor(base_frames).frames():
        print(frame)
    logger.info('Finished parsing frames')



if __name__ == '__main__':
    main()
