#!/usr/bin/env python3
# vim: set ts=4 sw=4 tw=0 et pm=:

import sys
import datetime
import re
from util import to_ascii, slice_extra, dt

from .base import *
from ..config import config, outfile

class MSGObject(object):
    def __init__(self, line):
        self.ric=  line.msg_ric
        self.fmt=  line.fmt
        self.seq=  line.msg_seq
        self.id=   line.id
        self.pcnt= line.msg_ctr_max
        self.csum= line.msg_checksum
        self.time= line.time

        self.done= False
        self.sent= False
        self.parts = [None]*(self.pcnt+1)
        if self.fmt not in (3,5):
            raise ValueError("unknown message format")

    def add(self, nr, content):
        self.done= False
        self.parts[nr]=content

    @property
    def complete(self):
        return None not in self.parts

    @property
    def content(self):
        if self.fmt==5:
            txt=b''.join(self.parts)
            while txt[-1]==3: # remove ETX at end
                txt=txt[:-1]
            return txt
        elif self.fmt==3:
            txt=''.join(self.parts)
            while txt[-1]=='c': # remove c's at end
                txt=txt[:-1]
            return txt

    def messagechecksum(self, msg):
        csum=0
        for x in msg:
            csum=(csum+x)%128
        return (~csum)%128

    @property
    def correct(self):
        if self.fmt==5:
            txt=self.content
            return self.csum == self.messagechecksum(txt)
        elif self.fmt==3:
            txt=self.content
            return txt.isdigit()

class ReassembleMSG(Reassemble):
    def __init__(self):
        self.topic=["MSG","MS3"]
        self.err=re.compile(r' ERR:')
        self.msg=re.compile(r'.* ric:(\d+) fmt:(\d+) seq:(\d+) (?:C:(..)\S*|[01 ]+) (\d)/(\d) csum:([0-9a-f][0-9a-f]) msg:([0-9a-f]*)\.([01]*) ')
        self.ms3=re.compile(r'.* ric:(\d+) fmt:(\d+) seq:(\d+) [01]+ \d BCD: ([0-9a-f]+)')
        if 'noburst' in config.args:
            global base64
            import base64
            import crcmod
            self.crc16 = crcmod.predefined.mkPredefinedCrcFun("xmodem")
            self.BURST_TRANS = bytes.maketrans(b'*-',b'/=')

    def filter(self,line):
        q=super().filter(line)
        if q == None: return None
        if self.err.search(q.data): return None
        if q.typ != "MSG:" and q.typ != "MS3:":
            return None

        if q.typ == "MSG:":
            m=self.msg.match(q.data)
            if(not m):
                print("Couldn't parse MSG: ",q.data, file=sys.stderr, end="")
                return None

            q.line_ok=         m.group(4)
            if q.line_ok is not None and q.line_ok != "OK":
                return None # Don't bother with broken packets

            q.msg_ric=     int(m.group(1))
            q.fmt=         int(m.group(2))
            q.msg_seq=     int(m.group(3))
            q.msg_ctr=     int(m.group(5))
            q.msg_ctr_max= int(m.group(6))
            q.msg_checksum=int(m.group(7),16)
            q.msg_hex=         m.group(8)
            q.msg_brest=       m.group(9)
            q.enrich()

            q.msg_msgdata = ''.join(["{0:08b}".format(int(q.msg_hex[i:i+2], 16)) for i in range(0, len(q.msg_hex), 2)])
            q.msg_msgdata+=q.msg_brest

            # convert to 7bit thingies
            message, rest= slice_extra(q.msg_msgdata, 7)
            q.msg_bytes=bytes([int(c, 2) for c in message])
            if rest != "": # could check if all 1
                pass

            return q

        if q.typ == "MS3:":
            m=self.ms3.match(q.data)
            if(not m):
                print("Couldn't parse MS3: ",q.data, file=sys.stderr)
                return None
            else:
                q.msg_ric=     int(m.group(1))
                q.fmt=         int(m.group(2))
                q.msg_seq=     int(m.group(3))
                q.msg_ctr=     0
                q.msg_ctr_max= 0
                q.msg_checksum=-1
                q.msg_bytes=         m.group(4)
                q.enrich()
                return q

    buf={}
    def process(self,m):
        idstr="%07d %04d %d"%(m.msg_ric,m.msg_seq,m.fmt)

        if idstr in self.buf and self.buf[idstr].csum != m.msg_checksum:
            if config.verbose:
                print("Whoa! Checksum changed? Message %s (1: @%d checksum %d/2: @%d checksum %d)"%
                        (idstr,self.buf[idstr].time,self.buf[idstr].csum,m.time,m.msg_checksum))
            tdiff = m.time-self.buf[idstr].time
            if tdiff > 600: # Older than 10 minutes, throw away existing fragments.
                del self.buf[idstr]
            elif m.msg_ctr >= len(self.buf[idstr].parts):
                # We have to keep the longer one
                del self.buf[idstr]

        if idstr not in self.buf:
            m.id=idstr
            msg=MSGObject(m)
            self.buf[idstr]=msg

        self.buf[idstr].add(m.msg_ctr, m.msg_bytes)

        for idx, msg in self.buf.copy().items():
            if msg.complete and not msg.done and not msg.sent:
                msg.done=True
                if msg.correct:
                    msg.sent=True
                    return [msg]

            if msg.time+2000<=m.time: # expire after ~ 30 mins
                del self.buf[idx]
                if not msg.sent:
                    if not msg.done:
                        if config.verbose:
                            print("timeout incomplete @",m.time,"(",msg.__dict__,")")
                        if 'incomplete' in config.args:
                            for x,y in enumerate(msg.parts):
                                if y is None:
                                    msg.parts[x]=b'[MISSING]'
                            return [msg]
                    else:
                        if config.verbose:
                            print("timeout failed @",m.time,"(",msg.__dict__,")")
                        return [msg]
                break

    def consume(self, msg):
        if 'fail' not in config.args:
            if not msg.correct:
                return

        date = dt.epoch_local(msg.time).isoformat(timespec='seconds')
        str="Message %07d %02d @%s (len:%d)"%(msg.ric, msg.seq, date, msg.pcnt)
        txt= msg.content
        if 'noburst' in config.args:
            try:
                ct = txt.translate(self.BURST_TRANS)
                dec = base64.b64decode(ct)
                crcv = self.crc16(dec)
                if crcv == 0:
                    return
            except Exception:
                pass

        if msg.fmt==5:
            out=to_ascii(txt, escape=True)
            str+= " %3d"%msg.csum
        elif msg.fmt==3:
            out=txt
            str+= " BCD"
        str+= (" fail:","   OK:")[msg.correct]
        str+= " %s"%(out)
        print(str, file=outfile)

    def end(self): # flush()
        for msg in self.buf.values():
            if not msg.sent:
                if not msg.done:
                    if config.verbose:
                        print("flush incomplete @",msg.time,"(",msg.__dict__,")")
                    if 'incomplete' in config.args:
                        for x,y in enumerate(msg.parts):
                            if y is None:
                                msg.parts[x]=b'[MISSING]'
                        self.consume(msg)
                else:
                    if config.verbose:
                        print("flush failed @",msg.time,"(",msg.__dict__,")")
                    self.consume(msg)

modes=[
["msg",        ReassembleMSG,         ('incomplete', 'fail', 'noburst') ],
]
