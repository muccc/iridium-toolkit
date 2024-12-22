#!/usr/bin/env python3
# vim: set ts=4 sw=4 tw=0 et pm=:

import sys
import datetime
import re
from util import to_ascii, dt

from .base import *
from .ida import ReassembleIDA
from ..config import config, outfile

class SBDObject(object):
    def __init__(self, typ, time, ul, prehdr, data):
        self.typ=    typ
        self.time=   time
        self.ul=     ul
        self.prehdr= prehdr
        self.data=   data

verb2=False
class ReassembleIDASBD(ReassembleIDA):
    outfile = sys.stdout
    multi=[]
    sbd_short=0
    sbd_single=0
    sbd_cnt=0
    sbd_multi=0
    sbd_assembled=0
    sbd_broken=0

    def __init__(self):
        super().__init__()
        if 'debug' in config.args:
            global verb2
            verb2=True
            print("DEBUG ENABLED")

    def consume(self,q):
        zz=self.process_l2(q)
        if zz is not None:
            self.consume_l2(zz)

    def process_l2(self,q):
        (data,time,ul,_,_)=q # level, freq

        # not enough data
        if len(data)<5:
            return

        # check for SBD
        if data[0]==0x76 and data[1]!=5:
            pass
        elif data[0]==0x06 and data[1]==0:
            pass
        else:
            return

        if data[0]==0x76:
            if ul:
                if data[1]<0x0c or data[1]>0x0e:
                    print("WARN: SBD: ul pkt with unclear type",data.hex(":"), file=sys.stderr)
                    return
            else:
                if data[1]<0x08 or data[1]>0x0b:
                    print("WARN: SBD: dl pkt with unclear type",data.hex(":"), file=sys.stderr)
                    return

        if data[0]==0x06:
            if data[1]!=0x00:
                print("WARN: SBD: HELLO pkt with unclear type",data.hex(":"), file=sys.stderr)
                return
            elif data[2] not in (0x00, 0x10,0x20,0x40,0x50,0x70):
                print("WARN: SBD: HELLO pkt with unknown sub-type",data.hex(":"), file=sys.stderr)
                return

        self.sbd_cnt+=1
        typ="%02x%02x"%(data[0],data[1])
        data=data[2:]

        if typ=="0600":
            if data[0] != 0x20:
                # Not an SBD packet, apparently
                return
            prehdr=data[:29]
            data=data[29:]
            msgcnt=prehdr[15]
            msgno=1
            if msgcnt==0:
                msgno=0
            hdr=bytes()
        else:
            if typ=="7608":
                if data[0]==0x26:
                    prehdr=data[:7]
                    data=data[7:]
                elif data[0]==0x20:
                    prehdr=data[:5]
                    data=data[5:]
                else:
                    print("WARN: SBD: DL pkt with unclear header",data.hex(":"), file=sys.stderr)
                    prehdr=data[:7]
                    data=data[7:]
                msgcnt=prehdr[3]
            else:
                prehdr=bytes()
                msgcnt=-1

            if ul and len(data)>=3 and data[0] in (0x50,0x51): # "ack" / nack?
                prehdr=data[:3] # remove
                data=data[3:]

            if len(data)==0:
                hdr=bytes()
                msgno=0
            elif len(data)>3 and data[0]==0x10:
                hdr=data[:3] # hdr: 0x10 len msg-cnt
                data=data[3:]
                msgno=hdr[2]

                if len(data)<hdr[1]:
                    if verb2:
                        print("SBD: Pkt too short", end=" ")
                        print("[%f] %2d/%2d %s <%s> <%s> %s"%(time, msgno, msgcnt, typ, prehdr.hex(":"), hdr.hex(":"), data.hex(":")))
                    return
                elif len(data)>hdr[1]:
                    if verb2:
                        print("SBD: Pkt too long", end=" ")
                        print("[%f] %2d/%2d %s <%s> <%s> %s"%(time, msgno, msgcnt, typ, prehdr.hex(":"), hdr.hex(":"), data.hex(":")))
                    data=data[:hdr[1]]
            else:
                hdr=bytes()
                msgno=0
                print("WARN: SBD: Data packet without header?",data.hex(":"), file=sys.stderr)
                if verb2:
                    print("SBD: Pkt weird:", end=" ")
                    print("[%f] %2d/%2d %s <%s> <%s> %s"%(time, msgno, msgcnt, typ, prehdr.hex(":"), hdr.hex(":"), data.hex(":")))

        pkt=SBDObject(typ, time, ul, prehdr, data)

        if verb2:
            if len(prehdr)>7:
                if prehdr[0]==0x20:
                    prehdrs=prehdr[:5].hex()+":"+prehdr[5:13].hex()+":"+prehdr[13:15].hex()+":"+prehdr[15:18].hex(":")+"."+prehdr[18:25].hex(":")+"@"+prehdr[25:].hex()
                else:
                    prehdrs=prehdr[:4].hex()+":"+prehdr[4:12].hex()+":"+prehdr[12:15].hex()+":"+prehdr[15:18].hex(":")+"."+prehdr[18:25].hex(":")+"@"+prehdr[25:].hex()
            else:
                prehdrs=prehdr.hex(":")

            print("[%f] %2d/%2d %s <%s> <%s> %s"%(time, msgno, msgcnt, typ, prehdrs, hdr.hex(":"), to_ascii(data, escape=True)))

        for (idx,(_,_,_,t)) in reversed(list(enumerate(self.multi[:]))):
            if t+5<time:
                if verb2:
                    print("Expired one:",idx)
                self.sbd_broken+=1
                self.multi.pop(idx)

        if msgno==0: # mboxcheck
            self.sbd_short+=1
            return pkt
        elif msgcnt==1 and msgno==1: # single-message
            self.sbd_single+=1
            return pkt
        elif msgcnt>1: # first new multi-packet
            self.multi.append([msgno,msgcnt,pkt,time])
            self.sbd_assembled+=1
            return None
        elif msgno>1: # addon
            ok=False
            for (idx,(no,cnt,p,t)) in reversed(list(enumerate(self.multi[:]))):
                if msgno==no+1 and msgno < cnt and p.ul == ul: # could check if "typ" seems right.
                    self.multi[idx][2].data+=data
                    self.multi[idx][2].typ+=typ
                    self.multi[idx][0]+=1
                    self.sbd_assembled+=1
                    if verb2:
                        print("Merged: %f s"%(time-t))
                    return None
                elif msgno==no+1 and msgno == cnt and p.ul == ul: # could check if "typ" seems right.
                    p.data+=data
                    p.typ+=typ
                    self.multi.pop(idx)
                    if verb2:
                        print("Merged & finished: %f s"%(time-t))
                    self.sbd_assembled+=1
                    self.sbd_multi+=1
                    return p
            self.sbd_broken+=1
            if verb2:
                print("Couldn't attach subpkt.")
            return None
        else:
            raise Exception("Shouldn't happen:"+str(msgno)+str(msgcnt)+str(pkt.__dict__))

    def end(self):
        super().end()
        print("SBD: %d short & %d single messages. (%1.1f%%)."%(self.sbd_short,self.sbd_single,(100*(float)(self.sbd_short+self.sbd_single)/(self.sbd_cnt or 1))))
#        print("SBD: %d fragments"%(self.sbd_cnt))
        print("SBD: %d successful multi-pkt messages."%(self.sbd_multi))
        print("SBD: %d/%d fragments could not be assembled. (%1.1f%%)."%(self.sbd_broken,self.sbd_assembled,(100*(float)(self.sbd_broken)/(self.sbd_assembled or 1))))

    def consume_l2(self,q):
        if q.ul:
            ult="UL"
        else:
            ult="DL"

        hdr="%s[%s]"%(ult,q.typ[3::4])
        hdr="%-8s <%s>"%(hdr,q.prehdr.hex(":"))

        if len(q.data)>0:
            print("%s %-99s %s | %s"%(
                        dt.epoch_local(int(q.time)).isoformat(),
                        hdr,q.data.hex(" "),to_ascii(q.data, dot=True)), file=self.outfile)
        else:
            print("%s %s"%(
                        dt.epoch_local(int(q.time)).isoformat(),
                        hdr), file=self.outfile)

acars_labels={ # ref. http://www.hoka.it/oldweb/tech_info/systems/acarslabel.htm
    b"_\x7f": "Demand mode",
    b"H1": "Message to/from terminal",
    b"52": "Ground UTC request",
    b"C1": "Uplink to cockpit printer No.1",
    b"C2": "Uplink to cockpit printer No.2",
    b"C3": "Uplink to cockpit printer No.3",
    b"Q0": "Link Test",
}

# ref. http://www.hoka.it/oldweb/tech_info/systems/acars.htm
class ReassembleIDASBDACARS(ReassembleIDASBD):
    def __init__(self):
        super().__init__()
        import crcmod
        global json
        import json
        self.acars_crc16=crcmod.predefined.mkPredefinedCrcFun("kermit")

    def consume_l2(self,q):
        if len(q.data)==0: # Currently not interested :)
            return

        if q.data[0]!=1: # prelim. check for ACARS
            return

        if len(q.data)<=2: # No contents
            return

        def parity7(data):
            ok = True
            for c in data:
                bits=bin(c).count("1")
                if bits%2==0:
                    ok=False
            return ok, bytes([x&0x7f for x in data])

        q.errors=0

        csum=bytes()
        q.hdr=bytes()
        q.errors=[]
        q.data=q.data[1:]

        if q.data[-1]==0x7f:
            csum=q.data[-3:-1]
            q.data=q.data[:-3]

        if q.data[0]==0x3: # header of unknown meaning
            q.hdr=q.data[0:8]
            q.data=q.data[8:]

        if len(csum)>0:
            q.the_crc=self.acars_crc16(q.data+csum)
            if q.the_crc!=0:
                q.errors.append("CRC_FAIL")
        else:
            q.errors.append("CRC_MISSING")

        if len(q.data)<13:
            q.errors.append("TRUNCATED")
            return # throw away for now

        ok, data=parity7(q.data)

        if not ok:
            q.errors.append("PARITY_FAIL")

        q.mode= data[ 0: 1]
        q.f_reg=data[ 1: 8] # address / aircraft registration
        q.ack=  data[ 8: 9]
        q.label=data[ 9:11]
        q.b_id =data[11:12] # block id

        data=data[12:]

        q.cont=False
        if data[-1] == 0x03: # ETX
            data=data[:-1]
        elif data[-1] == 0x17: # ETB
            q.cont=True
            data=data[:-1]
        else:
            q.errors.append("ETX incorrect")

        if len(data)>0 and data[0] == 2: # Additional content
            if data[0] == 2:
                if q.ul:
                    q.seqn=data[1:5] # sequence number
                    q.f_no=data[5:11] # flight number
                    q.txt=data[11:]
                else:
                    q.txt=data[1:]
            else:
                q.txt=data
                q.errors.append("STX missing")
        else:
            q.txt=bytes()

        if len(q.errors)>0 and not 'showerrs' in config.args:
            return

        if q.label == b'_\x7f' and 'nopings' in config.args:
            return

        q.timestamp = dt.epoch(q.time).isoformat(timespec='seconds')

        while len(q.f_reg)>0 and q.f_reg[0:1]==b'.':
            q.f_reg=q.f_reg[1:]

        # PRETTY-PRINT (json)
        if 'json' in config.args:
            out = {}

            # TODO: Replace version value with dynamic version that reflects the version of muccc/iridium-toolkit (preferably explicit version numbers, but can represent as git commit hash)
            out['app'] = { 'name': 'iridium-toolkit', 'version': '0.0.1' }

            out['source'] = { 'transport': 'iridium', 'protocol': 'acars' }
            if config.station:
                # Station ident can be in the form of an ident (e.g. 'KE-KMHR-IRIDIUM1') or a UUID (e.g. 'a1b2c3d4-e5f6-7a8b-9c0d-e1f2a3b4c5d6')
                # The UUID support is useful for cases where the station ident is not known in advance, and allows the station's name ident to be
                # updated later on the airframes.io website without breaking the link between the station and the airframes.io station.
                out['source']['station_id'] = config.station

            # Construct the ACARS content
            out['acars'] = {
                'timestamp': q.timestamp,
                'errors': len(q.errors),
                'link_direction': 'uplink' if q.ul else 'downlink',
                'block_end': q.cont == False,
            }
            for key in ('mode', 'f_reg:tail', 'f_no:flight', 'label', 'b_id:block_id', 'seqn:message_number', 'ack', 'txt:text'):
                old, _, new = key.partition(':')
                if new == '': new = old
                if old in q.__dict__:
                    val = q.__dict__[old]
                    if isinstance(val, bytes):
                        val = val.decode('ascii')
                    if old == 'label':
                        val = val.replace('_\u007f', '_d')
                    if old == 'ack':
                        val = val.replace('\u0015', '!')
                    out['acars'][new] = val

            # TODO: In theory we could put other content here unrelated to ACARS if there is anything else in the SBD message
            #       that we want to include in the output. For example, we could include the raw SBD message in the output.
            #       Or possibly other embedded modes if they are present in the SBD message.

            out['freq'] = self.ofreq
            out['level'] = self.olevel
            out['header'] = q.hdr.hex()

            print(json.dumps(out), file=self.outfile)
            return

        # PRETTY-PRINT (ascii)
        out=""

        out += q.timestamp + " "

        if len(q.hdr)>0:
            out+="[hdr: %s]"%q.hdr.hex()
        else:
            out+="%-23s"%""
        out+=" "

        if q.ul:
            out+="Dir:%s"%"UL"
        else:
            out+="Dir:%s"%"DL"
        out+=" "

        out+="Mode:%s"%q.mode.decode('latin-1')
        out+=" "

        out+="REG:%-7s"%q.f_reg.decode('latin-1')
        out+=" "

        if q.ack[0]==21:
            out+="NAK  "
        else:
            out+="ACK:%s"%q.ack.decode('latin-1')
        out+=" "

        out+="Label:"
        if q.label== b'_\x7f':
            out+='_?'
        else:
            out+=to_ascii(q.label, escape=True)
        out+=" "

        if q.label in acars_labels:
            out+="(%s)"%acars_labels[q.label]
        else:
            out+="(?)"
        out+=" "

        out+="bID:%s"%(to_ascii(q.b_id, escape=True))
        out+=" "

        if q.ul:
            out+="SEQ: %s, FNO: %s"%(to_ascii(q.seqn, escape=True), to_ascii(q.f_no, escape=True))
            out+=" "

        if len(q.txt)>0:
            out+="[%s]"%to_ascii(q.txt, escape=True)

        if q.cont:
            out+=" CONT'd"

        if len(q.errors)>0:
            out+=" " + " ".join(q.errors)

        print(out, file=self.outfile)


class ReassembleIDASBDlibACARS(ReassembleIDASBD):
    def __init__(self):
        global libacars, la_msg_dir
        from libacars import libacars, la_msg_dir
        if 'json' in config.args:
            global json
            import json
        super().__init__()

    def consume_l2(self, q):
        if len(q.data) <= 2: # No contents
            return

        if q.data[0] != 1: # prelim. check for ACARS
            return

        if q.ul:
            d = la_msg_dir.LA_MSG_DIR_AIR2GND
        else:
            d = la_msg_dir.LA_MSG_DIR_GND2AIR

        o = libacars(q.data, d, q.time)

        if o.is_err() and 'showerrs' not in config.args:
            return

        if o.is_ping() and 'nopings' in config.args:
            return

        q.timestamp = dt.epoch(q.time).isoformat(timespec='seconds')

        if 'json' in config.args:
            out = {}

            out['app'] = { 'name': 'iridium-toolkit', 'version': '0.0.2' }
            out['source'] = { 'transport': 'iridium', 'parser': 'libacars', 'version': libacars.version }
            out['timestamp'] = q.timestamp
            out['link_direction'] = 'uplink' if q.ul else 'downlink'
            if config.station:
                out['source']['station_id'] = config.station
            out['acars']=json.loads(o.json())['acars']
            print(json.dumps(out), file=self.outfile)
            return

        print(q.timestamp, end=" ")

        if q.ul:
            print("UL", end=" ")
        else:
            print("DL", end=" ")

        if q.data[1] == 0x3: # header of unknown meaning
            print("[hdr: %s]"%q.data[1:9].hex(), end=" ")

        if o.is_interesting():
            print("INTERESTING", end=" ")
        print(o)


modes=[
["sbd",        ReassembleIDASBD,      ('perfect', 'debug') ],
["acars",      ReassembleIDASBDACARS, ('json', 'perfect', 'showerrs', 'nopings') ],
["libacars",   ReassembleIDASBDlibACARS, ('json', 'perfect', 'showerrs', 'nopings') ],
]
