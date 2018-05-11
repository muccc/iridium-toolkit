#!/usr/bin/env python

# -*- coding: utf-8 -*-
# vim: set ts=4 sw=4 tw=0 et pm=:
import fileinput
import sys
import argparse

"""
VOC: i-1443338945.6543-t1 033399141 1625872817  81% 0.027 179 L:no LCW(0,001111,100000000000000000000 E1) 01111001000100010010010011011011011001111    011000010000100001110101111011110010010111011001010001011101010001100000000110010100000110111110010101110101001111010100111001000110100110001110110    1010101010010010001000001110011000001001001010011110011100110100111110001101110010110101010110011101011100011101011000000000 descr_extra:

"""

def chunks(l, n):
    """ Yield successive n-sized chunks from l.
    """
    for i in xrange(0, len(l), n):
        yield l[i:i+n]


def bits_to_dfs(lines, output):
    data = ''
    for line in lines:
        line = line.split()
        if line[0] != 'VOC:':
            continue
        if int(line[6]) < 179:
            continue

        data = line[10]
        if data[0] == "[":
            for pos in xrange(1,len(data),3):
                byte=int(data[pos:pos+2],16)
                byte=int('{:08b}'.format(byte)[::-1], 2)
                output.write(chr(byte))
        else:
            for bits in chunks(data, 8):
                byte = int(bits[::-1],2)
                output.write(chr(byte))

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