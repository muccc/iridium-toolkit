#!/usr/bin/env python3
# vim: set ts=4 sw=4 tw=0 et pm=:

import datetime

from .base import *
from ..config import config, outfile
from .msg import ReassembleMSG

STANDARD_ALPHABET = b'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'


class BurstObject:
    def __init__(self, mid, total):
        self.mid =   mid
        self.total = total
        self.parts = [None] * (self.total)

        self.done =  False

    def add(self, nr, content):
        self.parts[nr] = content

    @property
    def complete(self):
        return None not in self.parts

    @property
    def content(self):
        txt = b''.join(self.parts)
        return txt


class ReassembleMSGBurst(ReassembleMSG):
    def __init__(self):
        super().__init__()
        self.topic = ["MSG"]
        self.TRANSLATION =   bytes.maketrans(b'*', b'/')
        self.TRANS_PADDING = bytes.maketrans(b'-', b'=')

        global base64
        import base64
        global binascii
        import binascii
        import crcmod

        self.crc16 = crcmod.predefined.mkPredefinedCrcFun("xmodem")

    def consume(self, msg):
        zz = self.process_l2(msg)
        if zz is not None:
            self.consume_l2(zz)

    multi = {}

    def process_l2(self, msg):
        if not msg.correct:
            return

        ct = msg.content

        if b'*' in ct:
            ct = ct.translate(self.TRANSLATION)

        if not all(c in STANDARD_ALPHABET for c in ct.rstrip(b'-')):
            if config.verbose:
                print("charsetERR:", ct)
            return

        if ct[-1:] == b'-':
            ct = ct.translate(self.TRANS_PADDING)

        try:
            dec = base64.b64decode(ct)
        except binascii.Error as e:
            if config.verbose:
                print("b64ERR:", e, ct)
            return

        if len(dec) < 7:
            if config.verbose:
                print("shortERR:", ct)
            return

        uid = dec[0:3]  # uniq id (for reassembly)
        # XXX: should probably use RICs for uniqueness

        mid = dec[1] * 256 + dec[0]  # message-id

        total = dec[2]  # total number of parts
        current = dec[3]  # current part (0<current<total)
        clen = dec[4]  # content length

        if current >= total:
            if config.verbose:
                print("invalid part:", mid, current, total, ct)

        if clen != len(dec) - 7:
            if config.verbose:
                print("lenERR:", ct)
            return

        crcv = self.crc16(dec)

        if crcv != 0:
            if config.verbose:
                print("crcERR:", ct)

        if current + 1 < total and clen != 38:
            if config.verbose:
                print("non-last part has wrong length", ct)
            return

        if uid not in self.multi:
            self.multi[uid] = BurstObject(mid, total)

        bmsg = self.multi[uid]

        bmsg.add(current, dec[5:-2])

        self.multi[uid] = bmsg

        # XXX: needs expiry/timeout handling
        if bmsg.complete and not bmsg.done:
            bmsg.done = True
            return bmsg

    def consume_l2(self, msg):
        ct = msg.content

        # length is encoded as variable length quantity
        vlq = 0
        ptr = 1
        while ct[ptr] > 0x7f:
            vlq = vlq * 128 + ct[ptr] & 0x7f
            ptr += 1
        vlq = vlq * 128 + ct[ptr]

        if vlq != len(ct) - ptr - 3:
            print("ERR: content len wrong")

        if ct[-2:] != bytes([0, 0]):
            print("ERR: not ending in 0,0")

        print("burst %04x[%03d]:" % (msg.mid, msg.total), ct.hex(":"), file=outfile)

    def end(self):
        pass


modes = [
    ["burst", ReassembleMSGBurst, ],
]
