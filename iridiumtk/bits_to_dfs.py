#!/usr/bin/env python

import fileinput
import sys
import argparse


from .voc import VocLine


def bits_to_dfs(lines, output):
    for line in lines:
        if 'A:OK' in line and "Message: Couldn't parse:" not in line:
            raise RuntimeError('Expected "iridium-parser.py" parsed data. Found raw "iridium-extractor" data.')

        if not line.startswith('VOC:'):
            continue

        raw_voice_bits = VocLine(line).raw_voice_bits()
        if raw_voice_bits is not None:
            output.write(raw_voice_bits)


def main():
    parser = argparse.ArgumentParser(description='Convert iridium-parser.py VOC output to DFS')
    parser.add_argument('output', metavar='OUTPUT', help='Output file for DFS content. If - stdout is used ')
    parser.add_argument('input', metavar='FILE', nargs='*', help='Files to read, if empty or -, stdin is used')
    args = parser.parse_args()

    output_file = sys.stdout if args.output == '-' else open(args.output, 'w')
    input_files = args.input if len(args.input) > 0 else ['-']

    bits_to_dfs(fileinput.input(files=input_files), output_file)

    if output_file is not sys.stdout:
        output_file.close()


if __name__ == '__main__':
    main()
