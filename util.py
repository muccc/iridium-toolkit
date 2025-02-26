#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# vim: set ts=4 sw=4 tw=0 et pm=:

import re
import sys
import types
import datetime
from math import atan2, sqrt, pi

class Zulu(datetime.tzinfo):
    def utcoffset(self, dt):
        return datetime.timedelta(0)
    def dst(self, dt):
        return datetime.timedelta(0)
    def tzname(self, dt):
        return "Z"

Z = Zulu()

def myhex(data, sep):
    return sep.join(["%02x"%(x) for x in data])

# XXX: our own slice() is in the way.
slice_ = slice

#fallback class for python3 <3.8
class mybytes(bytes):
    def hex(self, sep=''):
        return sep.join(["%02x"%(x) for x in self])

    def __getitem__(self, key):
        if isinstance(key, slice_):
            return mybytes(super().__getitem__(key))
        else:
            return super().__getitem__(key)

    def __add__(self, key):
        return mybytes(super().__add__(key))

class mybytearray(bytearray):
    def hex(self, sep=''):
        return sep.join(["%02x"%(x) for x in self])

    def __getitem__(self, key):
        if isinstance(key, slice_):
            return mybytearray(super().__getitem__(key))
        else:
            return super().__getitem__(key)

def hex2bin(hexstr):
    l= len(hexstr)*4
    return ("{0:0%db}"%l).format(int(hexstr,16))

def fmt_iritime(iritime):
    # Different Iridium epochs that we know about:
    # ERA3: 2025-02-14T18:14:17Z : 1739556857 planned for 2026-01-14
    # ERA2: 2014-05-11T14:23:55Z : 1399818235 active since 2015-03-03T18:00:00Z
    # ERA1: 2007-03-08T03:50:21Z : 1173325821
    #       1996-06-01T00:00:11Z :  833587211 the original one (~1997-05-05)
    uxtime= float(iritime)*90/1000+1399818235
    if uxtime>1435708799: uxtime-=1 # Leap second: 2015-06-30 23:59:59
    if uxtime>1483228799: uxtime-=1 # Leap second: 2016-12-31 23:59:59
    strtime = datetime.datetime.fromtimestamp(uxtime,tz=Z).strftime("%Y-%m-%dT%H:%M:%S.{:02.0f}Z".format((uxtime%1)*100))
    return (uxtime, strtime)

def grouped(iterable, n):
    "s -> (s0,s1,s2,...sn-1), (sn,sn+1,sn+2,...s2n-1), ..."
    return zip(*[iter(iterable)]*n)

def remove_zeros(l):
    for ele in reversed(l):
        if not ele:
            del l[-1]
        else:
            break


def group(string, n): # similar to grouped, but keeps rest at the end
    string = re.sub('(.{%d})'%n,'\\1 ', string)
    return string.rstrip()


def slice_extra(string, n):
    blocks = [string[x:x+n] for x in range(0, len(string)+1, n)]
    extra = blocks.pop()
    return (blocks,extra)


def slice(string, n):
    return [string[x:x+n] for x in range(0, len(string),n)]

def to_ascii(data, dot=False, escape=False, mask=False):
    str=""
    for c in data:
        if mask:
            c=c&0x7f
        if( c>=32 and c<127):
            str+=chr(c)
        else:
            if dot:
                str+="."
            elif escape:
                if c==0x0d:
                    str+='\\r'
                elif c==0x0a:
                    str+='\\n'
                else:
                    str+='\\x{%02x}'%c
            else:
                str+="[%02x]"%c
    return str

def bitdiff(a, b):
    return sum(x != y for x, y in zip(a, b))

def objprint(q):
    for i in dir(q):
        attr = getattr(q, i)
        if i.startswith('_'):
            continue
        if isinstance(attr, types.MethodType):
            continue
        print("%s: %s"%(i, attr))


def curses_eol(file=sys.stderr):
    import curses
    curses.setupterm(fd=file.fileno())
    el = curses.tigetstr('el')
    cr = curses.tigetstr('cr') or b'\r'
    nl = curses.tigetstr('nl') or b'\n'
    if el is None:
        eol =   (nl).decode("ascii")
        eolnl = (nl).decode("ascii")
    else:
        eol =   (el+cr).decode("ascii")
        eolnl = (el+nl).decode("ascii")
    return eol

# extract position (x/y/z) from 5 bytes
# skip=(0-4) bits at the beginning
def xyz(data, skip=0):
    val = int(data[0:5].hex(), 16)
    sb = 4-skip

    loc_x = (val>>(12*2+sb)) & 0xfff
    if loc_x > 0x800: loc_x = -(0x1000 - loc_x)

    loc_y = (val>>(12*1+sb)) & 0xfff
    if loc_y > 0x800: loc_y = -(0x1000 - loc_y)

    loc_z = (val>>(12*0+sb)) & 0xfff
    if loc_z > 0x800: loc_z = -(0x1000 - loc_z)

    # From bitsparser.py: ad-hoc quick conversion
    lat = atan2(loc_z, sqrt(loc_x**2+loc_y**2))*180/pi
    lon = atan2(loc_y, loc_x)*180/pi
    alt = sqrt(loc_x**2+loc_y**2+loc_z**2)*4

    return dict(x=loc_x, y=loc_y, z=loc_z, lat=lat, lon=lon, alt=alt)

base_freq=1616*(10**6)   # int
channel_width=1e7/(30*8) # 30 sub-bands with 8 "frequency accesses" each

def channelize(freq):
    fbase = freq - base_freq
    freq_chan = int(fbase / channel_width)
    foff = fbase%channel_width
    freq_off = foff - (channel_width/2)
    return (freq_chan, freq_off)


def channelize_str(freq):
    fbase = freq-base_freq
    freq_chan = int(fbase / channel_width)
    sb = int(freq_chan/8)+1
    fa = (freq_chan % 8)+1
    sx = freq_chan-30*8+1
    foff = fbase%channel_width
    freq_off = foff-(channel_width/2)
    if sb > 30:
        return f"S.{sx:02}|{freq_off:+06.0f}"
    else:
        return f"{sb:02}.{fa:1}|{freq_off:+06.0f}"


def get_channel(subband, fa, strict=True):
    """Convert subband & frequency_access to frequency"""

    if subband == 'S': # "simplex" frequencies
        subband = 31

    if strict:
        if not 0 <= int(subband) <= 31:
            raise ValueError(f"subband {subband} out of range S or 1-30")

        if int(subband) == 31 and not 0 <= int(fa) <= 12:
            raise ValueError(f"frequency access {fa} out of range 1-12 for simplex")

        if int(subband) != 31 and not 0 <= int(fa) <= 8:
            raise ValueError(f"frequency access {fa} out of range 1-8")

    return round(base_freq + channel_width / 2 +
                 channel_width * 8 * (int(subband)-1) +
                 channel_width * (int(fa)-1))


def parse_handoff(lcwstr):
    """Parse handoff response out of LCW string"""
    # LCW(7,T:hndof,C:handoff_resp[cand:P,denied:0,ref:0,slot:3,sband_up:16,sband_dn:16,access:4],00)
    fields = lcwstr[lcwstr.index("["):lcwstr.index("]")][1:].split(',')
    handoff = dict(f.split(':') for f in fields)
    handoff.update({k: int(v) for k, v in handoff.items() if v.isdecimal()})
    return handoff


def parse_channel(fstr):
    if "|" in fstr:
        chan, off = fstr.split('|')
        if '.' in chan:
            sb, fa = chan.split('.')
            frequency = get_channel(sb, fa, strict=False) + int(off)
        else:
            frequency = base_freq+channel_width*int(chan)+int(off)+channel_width/2
    else:
        frequency = int(fstr)
    return int(frequency)

class dt(datetime.datetime):
    def isoformat(self, sep='T', timespec='auto'):
        """Return the time formatted according to ISO.

        The full format looks like 'YYYY-MM-DD HH:MM:SS.mmmmmm'.
        By default, the fractional part is omitted if self.microsecond == 0
        or shortened to 'YYYY-MM-DD HH:MM:SS.mmm' if possible.

        If self.tzinfo is not None, the UTC offset is also attached, giving
        giving a full format of 'YYYY-MM-DD HH:MM:SS.mmmmmm+HHMM'.

        if the UTC offset is 0, a 'Z' will be used, so the format is
        shortened to 'YYYY-MM-DD HH:MM:SS.mmmmmmZ'.

        Optional arguments exist for compability but should not be used.
        """

        if self.microsecond != 0 and self.microsecond % 1000 == 0 and timespec == 'auto':
            timespec = 'milliseconds'

        trunc = False
        if timespec == 'centiseconds':
            timespec = 'milliseconds'
            trunc = True

        _iso = super().isoformat(sep, timespec)

        if trunc and _iso[-6] == '+' and _iso[-10] == '.':
            _iso = _iso[:-7] + _iso[-6:]
        if _iso[-6:] == '+00:00':
            _iso = _iso[:-6] + 'Z'
        if (_iso[-6] == '+' or _iso[-6] == '-') and _iso[-3] == ':':
            _iso = _iso[:-3] + _iso[-2:]
        return _iso

    @classmethod
    def epoch(cls, t):
        """Construct a correct UTC datetime from a POSIX timestamp."""
        return cls.fromtimestamp(t, datetime.timezone.utc)

    @classmethod
    def epoch_local(cls, t):
        """Construct a datetime from a POSIX timestamp in the local timezone."""
        return cls.fromtimestamp(t, datetime.timezone.utc).astimezone()
