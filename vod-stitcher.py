#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# vim: set ts=4 sw=4 tw=0 et pm=:
import util
import fileinput
import sys

"""
VOC: i-1443338945.6543-t1 033399141 1625872817  81% 0.027 179 L:no LCW(0,001111,100000000000000000000 E1) 01111001000100010010010011011011011001111    011000010000100001110101111011110010010111011001010001011101010001100000000110010100000110111110010101110101001111010100111001000110100110001110110    1010101010010010001000001110011000001001001010011110011100110100111110001101110010110101010110011101011100011101011000000000 descr_extra:

"""

def chunks(l, n):
    """ Yield successive n-sized chunks from l.
    """
    for i in range(0, len(l), n):
        yield l[i:i+n]


def grouped(iterable, n):
    "s -> (s0,s1,s2,...sn-1), (sn,sn+1,sn+2,...s2n-1), ..."
    return zip(*[iter(iterable)]*n)

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

infile = sys.argv[1]
outfile = open(sys.argv[2], 'wb')

data = ''

a_seq = None
a_data = ''

b_seq = None
b_data = ''

c_data=bytearray([0]*10)

ts_old = 0

for line in fileinput.input(infile):
    line = line.split()
    if line[0] == 'VOD:':
        if int(line[6]) < 179:
            continue
        ts = float(line[2])
        if line[9][0].startswith("["):
            data = line[9]
        else:
            data = line[10]
        content=bytearray()
        for pos in range(1,len(data),3):
            byte=int(data[pos:pos+2],16)
            byte=int('{:08b}'.format(byte)[::-1], 2)
            #byte=int('{:08b}'.format(byte)[::], 2)
            content.append(byte)
        hdr='{:08b}'.format(content[0])
        hdr=hdr[::-1]
        content=content[1:]
#        print(data)
        print(hdr, end=' ')
        print("".join("%02x"%x for x in content), end=' ')

        if hdr.startswith("11000") or hdr.startswith("10000") or hdr.startswith("01000"):
            print("A1", end=' ')
            #if a_data!='':
            #    outfile.write(a_data)
            #    outfile.write(c_data)
            a_seq = hdr[5:8]
            a_data = content[0:29]
            a_ts = ts

        if hdr.startswith("00001"):
            print("B1", end=' ')
            b_seq = hdr[5:8]
            b_data = content[20:30]
            b_ts = ts

        if hdr.startswith("00010"):
            print("B2", end=' ')
            b_seq = hdr[5:8]
            b_data = content[10:20]
            b_ts = ts

        if hdr.startswith("00100"):
            print("B3", end=' ')
            b_seq = hdr[5:8]
            b_data = content[0:10]
            b_ts = ts

        print("> ",a_seq,b_seq, end=' ')
#        print "|", "".join("%x"%x for x in a_data),"[%02d]"%len(a_data),
#        print " ", "".join("%x"%x for x in b_data),"[%02d]"%len(b_data)
        if a_seq and b_seq and a_seq == b_seq and abs(a_ts - b_ts) < 3*90:
            #print "out!"
            data = a_data + b_data

            print('XXX: ', util.myhex(data, '.'))
            #outfile.write(data)

            #if data[0] == 0xc0:
            #if not (data[0] == 0x03 and data[1] == 0xc0):
            if (data[0] == 0x03 and data[1] == 0xc0):
                #print int(a_seq, 2), a_ts - ts_old, '.'.join([c.encode('hex') for c in str(data)])
                print(a_ts - ts_old, util.myhex(data, '.'))
                #outfile.write(data)

            outfile.write(data)

            ts_old = a_ts
            a_data=''
            b_data=''
            a_seq = None
            b_seq = None


        print("")

