#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# vim: set ts=4 sw=4 tw=0 et pm=:
import fileinput
import sys

"""
VOC: i-1443338945.6543-t1 033399141 1625872817  81% 0.027 179 L:no LCW(0,001111,100000000000000000000 E1) 01111001000100010010010011011011011001111    011000010000100001110101111011110010010111011001010001011101010001100000000110010100000110111110010101110101001111010100111001000110100110001110110    1010101010010010001000001110011000001001001010011110011100110100111110001101110010110101010110011101011100011101011000000000 descr_extra:

"""

def turn_symbols(byte):
    out = 0
    if byte & 0x01:
        out |= 0x02
    if byte & 0x02:
        out |= 0x01
    if byte & 0x04:
        out |= 0x08
    if byte & 0x08:
        out |= 0x04

    if byte & 0x10:
        out |= 0x20
    if byte & 0x20:
        out |= 0x10
    if byte & 0x40:
        out |= 0x80
    if byte & 0x80:
        out |= 0x40

    return out

def chunks(l, n):
    """ Yield successive n-sized chunks from l.
    """
    for i in range(0, len(l), n):
        yield l[i:i+n]

infile = sys.argv[1]
outfile = open(sys.argv[2], 'wb')

data = ''

for line in fileinput.input(infile):
    line = line.split()
    if line[0] == 'VOC:':
        if int(line[6]) < 179:
            continue
        if line[9][0].startswith("["):
            data = line[9]
        else:
            data = line[10]
        if (data[0] == "["):
            for pos in range(1,len(data),3):
                byte=int(data[pos:pos+2],16)
                byte=int('{:08b}'.format(byte)[::-1], 2)
                outfile.write(bytes([byte]))
        else:
            for bits in chunks(data, 8):
                byte = int(bits[::-1],2)
                outfile.write(chr(byte))
