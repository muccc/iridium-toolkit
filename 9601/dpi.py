#!/usr/bin/env python

import serial
import sys

''' Set of functions to interface with the 9601 DPI interface.

Based on reverse engineering the firmware of an 9601 SBD modem.
Use at your own risk.

Supported functions:

Read/Write debug flags
Read/Write IMEI
'''

s = serial.Serial(sys.argv[1], 115200)

'''
Available commands

Note: these are based on their location in the jump table.

The DPI adds a constant of 21 to them before transmitting
it over the serial line.
'''
RQVN = 0xC2
RQEE = 0xC4
ETST = 0xB3
SEEP = 0xC6

def to_hex(msg):
    return ' '.join(["%02x" % ord(x) for x in msg] )

def to_ascii(msg):
    a = ''
    for x in msg:
        if 32 <= ord(x) < 127:
            a += x
        else:
            a += '.'
    return a

def imei_parse_nibble(nibble):
    """Parse one nibble of an IMEI and return its ASCII representation."""
    if nibble < 10:
        return chr(nibble + ord('0'))
    if nibble == 0xa:
        return '*'
    if nibble == 0xb:
        return '#'
    if nibble == 0xc:
        return 'C'
    if nibble == 0xd:
        return '.'
    if nibble == 0xe:
        return '!'
    return ''

def parse_imei(msg):
    """Parse an IMEI (in BCD format) into ASCII format."""
    imei = ''
    for octet in msg[1:]:
        imei += imei_parse_nibble(ord(octet) & 0x0f)
        imei += imei_parse_nibble(ord(octet) >> 4)
    return imei

def send_cmd(cmd, data):
    """Send a DPI command via the serial line.

    The checksum is computed automatically.
    """
    msg = chr(cmd + 21) + data

    msg = chr(2) + chr(len(msg)) + msg

    checksum = reduce(lambda x, y: chr(ord(x)^ord(y)), [x for x in msg])

    msg = msg + checksum + chr(3)

    print ["%02x" % ord(x) for x in msg]
    s.write(msg)

def read_message():
    """Read a message from the serial line and handle ACK/NACK processing.

    Received ACKs and NACKs are ignored.

    Received checksums are ignored.

    When a message gets received, an ACK is sent to the device,
    before returning the message to the caller.

    If an error (currently only 0xF2) is received, None gets
    returned to the caller.
    """
    d = ''
    msg = ''
    stx = None
    length = 0
    checksum = None

    while 1:
        x = s.read()
        #print ord(x)
        if not stx:
            stx = ord(x)
            if stx == 6:
                print "RX: ACK"
                stx = None
            if stx == 21:
                print "RX: NACK"
                stx = None
            length = None
            continue

        if not length:
            length = ord(x)
            msg = ''
            checksum = None
            continue

        if len(msg) < length:
            msg += x
            continue

        if not checksum:
            checksum = ord(x)
            continue

        print "TX: ACK"
        s.write(chr(6))
       
        if msg != '\xf2':
            return msg
        else:
            print "Error F2"
            return None

        return msg

def read_eeprom(location, a2=1):
    """Read data from an EEPROM location.

    location is the "logical" location of the data in the EEPROM.
    
    a2 is a yet unknwon parameter known to vary between 1 and 7.
    """
    a1 = ''
    a1 += chr((location >> 24) & 0xFF)
    a1 += chr((location >> 16) & 0xFF)
    a1 += chr((location >> 8) & 0xFF)
    a1 += chr((location >> 0) & 0xFF)

    a2 = chr(a2)
    send_cmd(RQEE, a1 + a2)
    msg = read_message()
    if not msg:
        print 'Unable to read EEPROM location', hex(location)
        return None
    print "EEPROM 0x%05x: %s" % (location, to_hex(msg[1:]))
    return msg[1:]

def write_eeprom(location, data, a2=1):
    """Write data to an eeprom location.

    See read_eeprom for information on location and a2.

    Return None if there was no error.
    """
    a1 = ''
    a1 += chr((location >> 24) & 0xFF)
    a1 += chr((location >> 16) & 0xFF)
    a1 += chr((location >> 8) & 0xFF)
    a1 += chr((location >> 0) & 0xFF)

    a2 = chr(a2)
    send_cmd(SEEP, a1 + a2 + data)
    return read_message()

def read_version_information():
    send_cmd(RQVN, "")
    return read_message()

def go_to_tpi_level_1():
    """Got to TPI level "1".

    This activates access to more commands on the TPI.

    The command also has some unknown side effects, but
    seems to be safe to execute.
    """
    send_cmd(ETST, '')

def read_imei():
    """Read and return the IMEI of the device.
    
    Return None if there if the read fails.
    """
    imei = None
    data = read_eeprom(0x106)
    if data:
        imei = parse_imei(data)
    return imei

def write_imei(imei):
    return write_eeprom(0x106, imei)

def read_debug_flags():
    """Read and return the debug flags.

    The debug flags are a bit field which enables/disables
    different debug messages on the debug UART.

    There seems to be a general "enable debug" flag and
    some flags to enable logging from different modules.
    """
    return read_eeprom(0x10804)

def write_debug_flags(debug_flags):
    return write_eeprom(0x10804, debug_flags)

go_to_tpi_level_1()

print write_debug_flags('\x00\x00\x85\x13')

print "IMEI: " + read_imei()

print read_version_information()

print "Debug Flags:", to_hex(read_debug_flags())

#for i in range(0, 0x200):
#    msg = read_eeprom(i)
#    if msg:
#        print "EEPROM 0x%05x: %s (%s)" % (i, to_ascii(msg), to_hex(msg))

#for a1 in range(16):
#    i = 0xc
#    msg = read_eeprom(i, a1)
#    if msg:
#        print "EEPROM 0x%05x: %s (%s)" % (i, to_ascii(msg), to_hex(msg))

