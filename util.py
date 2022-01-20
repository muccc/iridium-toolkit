#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# vim: set ts=4 sw=4 tw=0 et pm=:

import re
import types
import datetime

class Zulu(datetime.tzinfo):
    def utcoffset(self, dt):
        return datetime.timedelta(0)
    def dst(self, dt):
        return datetime.timedelta(0)
    def tzname(self,dt):
         return "Z"

Z=Zulu()

def myhex(data, sep):
    return sep.join(["%02x"%(x) for x in data])

def fmt_iritime(iritime):
    # Different Iridium epochs that we know about:
    # ERA2: 2014-05-11T14:23:55Z : 1399818235 active since 2015-03-03T18:00:00Z
    # ERA1: 2007-03-08T03:50:21Z : 1173325821
    #       1996-06-01T00:00:11Z :  833587211 the original one (~1997-05-05)
    uxtime= float(iritime)*90/1000+1399818235
    if uxtime>1435708799: uxtime-=1 # Leap second: 2015-06-30 23:59:59
    if uxtime>1483228799: uxtime-=1 # Leap second: 2016-12-31 23:59:59
    strtime=datetime.datetime.fromtimestamp(uxtime,tz=Z).strftime("%Y-%m-%dT%H:%M:%S.{:02.0f}Z".format((uxtime%1)*100))
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

def group(string,n): # similar to grouped, but keeps rest at the end
    string=re.sub('(.{%d})'%n,'\\1 ',string)
    return string.rstrip()

def slice_extra(string,n):
    blocks=[string[x:x+n] for x in range(0,len(string)+1,n)]
    extra=blocks.pop()
    return (blocks,extra)

def slice(string,n):
    return [string[x:x+n] for x in range(0,len(string),n)]

def bitdiff(a, b):
    return sum(x != y for x, y in zip(a, b))

def objprint(q):
    for i in dir(q):
        attr=getattr(q,i)
        if i.startswith('_'):
            continue
        if isinstance(attr, types.MethodType):
            continue
        print("%s: %s"%(i,attr))
