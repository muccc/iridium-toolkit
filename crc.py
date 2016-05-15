#!/usr/bin/python
# vim: set ts=4 sw=4 tw=0 et pm=:

def crc24(data):
    crc = 0xffffff
    for byte in data:
        crc=crc^(byte)
        for bit in range(0, 8):
            if (crc&0x1):
                crc = ((crc >> 1) ^ 0xAD85DD)
            else:
                crc = crc >> 1
    return crc ^0x0c91b6 # Check value
