#!/usr/bin/env python3
# vim: set ts=4 sw=4 tw=0 et pm=:

import sys
import datetime
import re
import struct
import socket
import crcmod
from util import fmt_iritime, to_ascii, xyz, channelize, channelize_str

from .base import *
from ..config import config, outfile

_starttime=None
class ReassembleIDA(Reassemble):
    def __init__(self):
        self.topic="IDA"
        pass
    def filter(self,line):
        q=super().filter(line)
        if q==None: return None
        if q.typ!="IDA:": return None

        qqq=re.compile(r'.* CRC:OK')
        if not qqq.match(q.data):
            return None

        p=re.compile(r'.* cont=(\d) (\d) ctr=(\d+) \d+ len=(\d+) 0:.000 \[([0-9a-f.!]*)\]\s+..../.... CRC:OK')
        m=p.match(q.data)
        if(not m):
            print("Couldn't parse IDA: ",q.data, file=sys.stderr)
            return None

        q.ul=        (q.uldl=='UL')
        q.f1=         m.group(1)
        q.f2=     int(m.group(2))
        q.ctr=    int(m.group(3),2)
        q.length= int(m.group(4))
        q.data=   m.group(5)
        q.cont=(q.f1=='1')
        q.enrich()
        global _starttime
        if _starttime is None: _starttime=int(q.starttime)
#       print "%s %s ctr:%02d %s"%(q.time,q.frequency,q.ctr,q.data)
        return q

    buf=[]
    stat_broken=0
    stat_ok=0
    stat_fragments=0
    stat_dupes=0
    otime=0
    odata=None
    ofreq=0
    def process(self,m):
        # rudimentary De-Dupe
        if (self.otime-1)<=m.time<=(self.otime+1) and self.odata==m.data and (self.ofreq-200)<m.frequency<(self.ofreq+200):
            self.stat_dupes+=1
            if config.verbose:
                print("dupe: ",m.time,"(",m.cont,m.ctr,")",m.data)
            return
        self.otime=m.time
        self.odata=m.data
        self.ofreq=m.frequency
        self.olevel=m.level

        ok=False
        for (idx,(freq,time,ctr,dat,cont,ul)) in enumerate(self.buf[:]):
            if (freq-260)<m.frequency<(freq+260) and time[-1]<=m.time<=(time[-1]+280) and (ctr+1)%8==m.ctr and ul==m.ul:
                del self.buf[idx]
                dat=dat+"."+m.data
                time.append(m.time)
                if m.cont:
                    self.buf.append([m.frequency,time,m.ctr,dat,m.cont,m.ul])
                else:
                    self.stat_ok+=1
                    if config.verbose:
                        print(">assembled: [%s] %s"%(",".join(["%s"%x for x in time+[m.time]]),dat))
                    data=bytes().fromhex( dat.replace('.',' ').replace('!',' ') )
                    return [[data,m.time,ul,m.level,freq]]
                self.stat_fragments+=1
                ok=True
                break
        if ok:
            pass
        elif m.ctr==0 and not m.cont:
            if config.verbose:
                print(">single: [%s] %s"%(m.time,m.data))
            data=bytes().fromhex( m.data.replace('.',' ').replace('!',' ') )
            return [[data,m.time,m.ul,m.level,m.frequency]]
        elif m.ctr==0 and m.cont: # New long packet
            self.stat_fragments+=1
            if config.verbose:
                print("initial: ",m.time,"(",m.cont,m.ctr,")",m.data)
            self.buf.append([m.frequency,[m.time],m.ctr,m.data,m.cont,m.ul])
        elif m.ctr>0:
            self.stat_broken+=1
            self.stat_fragments+=1
            if config.verbose:
                print("orphan: ",m.time,"(",m.cont,m.ctr,")",m.data)
            pass
        else:
             print("unknown: ",m.time,m.cont,m.ctr,m.data)
        # expire packets
        for (idx,(freq,time,ctr,dat,cont,ul)) in enumerate(self.buf[:]):
            if time[-1]+1000<=m.time:
                self.stat_broken+=1
                del self.buf[idx]
                if config.verbose:
                    print("timeout:",time,"(",cont,ctr,")",dat)
                data=bytes().fromhex( dat.replace('.',' ').replace('!',' ') )
                #could be put into assembled if long enough to be interesting?
                break
    def end(self):
        super().end()
        print("%d valid packets assembled from %d fragments (1:%1.2f)."%(self.stat_ok,self.stat_fragments,((float)(self.stat_fragments)/(self.stat_ok or 1))))
        print("%d/%d (%3.1f%%) broken fragments."%(self.stat_broken,self.stat_fragments,(100.0*self.stat_broken/(self.stat_fragments or 1))))
        print("%d dupes removed."%(self.stat_dupes))

    def consume(self,q):
        (data,time,ul,level,freq)=q
        if ul:
            ul="UL"
        else:
            ul="DL"
        str=""
        str+=to_ascii(data,True)

        freq_print=channelize_str(freq)

        print("%15.6f %s %s %s | %s"%(time,freq_print,ul,data.hex(" "),str), file=outfile)

# Mobile station classmark 2 10.5.1.6
def p_cm2(data):
    cmlen=data[0] # Must be 3
    cmdata=data[1:cmlen+1]
    str="CM2:%s"%cmdata.hex()
    return (str, data[1+cmlen:])

def p_mi(data):
    iei_dig = data[0]>>4
    iei_odd = (data[0]>>3)&1
    iei_typ = data[0]&7

    if iei_typ==2 or iei_typ==1: # IMEI / IMSI
        if iei_odd==1:
            str="%x"%(iei_dig)
            str+="".join("%x%x"%((x)&0xf,(x)>>4) for x in data[1:])
            return "%s:%s"%(["","imsi","imei"][iei_typ],str)
        else:
            return "ERR_MI_PARSE_FAIL[%s]"%data.hex()
    elif iei_typ==4: # TMSI
        if iei_odd==0 and iei_dig==0xf:
            str="tmsi:%s"%(data[1:].hex())
            return str
        else:
            return "ERR_MI_PARSE_FAIL[%s]"%data.hex()
    else:
        return "ERR_PARSE_FAIL[%s]"%data.hex()

def p_lai(lai): # 10.5.1.3
    str="MCC=%x%x%x"%(lai[0]&0xf,lai[0]>>4,lai[1]&0xf)
    if lai[1]>>4 == 0xf:
        str+="/MNC=%x%x"%(lai[2]&0xf,lai[2]>>4)
    else:
        str+="/MNC=%x%x%x"%(lai[2]&0xf,lai[2]>>4,lai[1]>>4)
    str+="/LAC=%02x%02x"%(lai[3],lai[4])
    return str

def p_disc(disc):
    ext        = (disc[0]&0b10000000)>>7
    coding     = (disc[0]&0b01100000)>>5
    location   = (disc[0]&0b00001111)>>0

    if coding != 3 or ext != 1:
        return "ERR:PARSE_FAIL"

    if location==0:
        str="Loc:user "
    elif location==2:
        str="Net:local"
    elif location==3:
        str="Net:trans"
    elif location==4:
        str="Net:remot"
    else:
        str="Loc:%3d "%location

    if len(disc)<2:
        return "ERR:SHORT"

    cause=disc[1]&0x7f

    if cause==1:
        str+=" Cause(01) Unassigned number"
    elif cause==16:
        str+=" Cause(16) Normal call clearing"
    elif cause==17:
        str+=" Cause(17) User busy"
    elif cause==21:
        str+=" Cause(21) Rejected"
    elif cause==31:
        str+=" Cause(31) Normal, unspecified"
    elif cause==34:
        str+=" Cause(34) No channel available"
    elif cause==41:
        str+=" Cause(41) Temporary failure"
    elif cause==57:
        str+=" Cause(57) Bearer cap. not authorized"
    elif cause==127:
        str+=" Cause(127) Interworking, unspecified"
    else:
        str+=" Cause: %d"%cause

    if len(disc)>2:
        if (disc[0]>>7)==1 and len(disc)==3 and disc[2]==0x88: # Diagnostic
            str+=" (CCBS not poss.)" # ref. Wireshark
        else:
            str+= " ERR:ADD_"+ disc[2:].hex(":")

    return str

def p_bearer_capa(data):
    txt=""
    ext        = (data[0]&0b10000000)>>7
    rcr        = (data[0]&0b01100000)>>5
    coding     = (data[0]&0b00010000)>>4
    trans_mode = (data[0]&0b00001000)>>3
    trans_capa = (data[0]&0b00000111)>>0

    txt = ["rate:reserved", "full rate only", "half rate pref.", "full rate pref."][rcr]
    if coding != 0:
        txt +=",coding:reserved"
    if trans_mode != 0:
        txt += ","
        txt +=["mode:packet"]
    txt += ","
    if trans_capa<4:
        txt +=["speech", "digital", "3.1 kHz audio", "fax" ][trans_capa]
    else:
        txt += "transfer:%x"%trans_capa

    if len(data)>1:
        txt += ":"+data[1:].hex(":")

    return txt

def p_bcd_num(data):
    if len(data)<1:
        return "PARSE_FAIL"

    txt=""
    ext        = (data[0]&0b10000000)>>7
    numtype    = (data[0]&0b01110000)>>4
    numplan    = (data[0]&0b00001111)>>0

    if ext==0: # Table 10.5.120 / technically only for calling party
        pi        = (data[1]&0b01100000)>>5
        si        = (data[1]&0b00000011)>>7
        if pi == 2:
            txt += "Number_not_available "
            if numplan == 0:
                numplan = 1 # XXX: Skip unneccessary output
        elif pi != 0:
            txt += "present=%d "%pi
        if si != 0:
            txt += "screen=%d "%pi
        num=data[2:]
    else:
        num=data[1:]

    # BCD
    num="".join("%x%x"%((x)&0xf,(x)>>4) for x in num)
    if len(num)>0 and num[-1]=="f":
        num=num[:-1]

    # 04.08 Table 10.5.118
    num.replace('a', '*')
    num.replace('b', '#')
    num.replace('c', 'a')
    num.replace('d', 'b')
    num.replace('e', 'f')

    if numtype == 1: # international
        num="+"+num
    elif numtype == 0: # unspecified
        pass
    else:
        txt+="type:%d "%numtype

    if numplan !=1:
        txt+="plan:%d "%numplan

    txt+=num
    return txt

def p_progress(data):
    if len(data) != 2:
        return "PARSE_FAIL[%s]"%data.hex(":")

    txt = ""
    ext        = (data[0]&0b10000000)>>7
    cs         = (data[0]&0b01100000)>>5
    loc        = (data[0]&0b00001111)>>0

    progress = data[1] & 0x7f

    if cs != 3:
        txt =  "cs:%d "%cs

    if loc != 2:
        txt +=  "loc:%x"%loc

    if progress == 3:
        txt += "Origination address is non-local"
    elif progress == 2:
        txt += "Destination address is non-local"
    elif progress == 2:
        txt += "Call is non-local"
    elif progress == 8:
        txt += "In-band available"
    elif progress == 32:
        txt += "Call is local"
    else:
        txt +=  "progress:%02x"%(progress)
    return txt

def p_facility(data):
    if data.hex(":") == "a1:0e:02:01:01:02:01:10:30:06:81:01:28:84:01:07":
        str="allCondForwardingSS"
        str+="(Provisioned+Registered+Active)"
        return str
    elif data.hex(":") == "a1:0e:02:01:01:02:01:10:30:06:81:01:21:84:01:07":
        str="cfu" # call forwarding unconditional
        str+="(Provisioned+Registered+Active)"
        return str
    else:
        return "facility[%s]"%(data.hex(":"))

# Minimalistic TV & TLV parser
# 04.07     11.2.1.1.4
# type1: TV(0.5) # list of tags
# type2: T(0)    # list of tags
# type3: TV(1+)  # list of (tag, len)
# type4: TLV     # list of tags
# start: Tag-less elements at the beginning # list of (tag, len) -- [len<0 means it's LV]
#
# iridium extensions:
#   type1i: list of (tag, len), where tag is just the high nibble (like type1)
#   type3i: list of (tag, len)

def p_opt_tlv(data, type1=[], type2=[], type3=[], type4=[], start=[], type1i=[], type3i=[]):
    out = ""
    type3_d={t:l for (t,l) in type3+type3i}
    type3i_d={t:l for (t,l) in type3i}
    type1i_d={t:l for (t,l) in type1i}
    for t, l in start:
        if l<0:
            l = data[0]
            data=data[1:]
        if len(data) < l:
            out += "ERR:SHORT:"+data.hex(":")
            break
        else:
            rv = p_tv(t, data[:l])
            out+= " " + rv
            data = data[l:]
    while len(data)>0:
        if data[0] & 0xf0 in type1:
            rv = p_tv(data[0] & 0xf0, data[0] & 0x0f)
            out+= " " + rv
            data = data[1:]
            continue
        if data[0] & 0xf0 in type1i_d:
            iei_len = type1i_d[data[0]&0xf0]
            if len(data) < 1+iei_len:
                out += "ERR:SHORT(1i):"+data.hex(":")
                break
            rv = p_tv((data[0]&0xf0)+0x100, data[0:1+iei_len])
            out+= " " + rv
            data = data[1+iei_len:]
            continue
        if data[0] in type2:
            rv = p_tv(data[0], None)
            out+= " " + rv
            data = data[1:]
            continue
        if len(data) < 1:
            break
        if data[0] in type3_d:
            iei_len = type3_d[data[0]]
            if len(data) < 1+iei_len:
                out += "ERR:SHORT:"+data.hex(":")
                break
            if data[0] in type3i_d:
                rv = p_tv(data[0]+0x100, data[1:1+iei_len])
            else:
                rv = p_tv(data[0], data[1:1+iei_len])
            out+= " " + rv
            data = data[1+iei_len:]
            continue
        if data[0] in type4:
            iei_len = data[1]
            if len(data) < 2+iei_len:
                out += "ERR:SHORT:"+data.hex(":")
                break
            rv = p_tv(data[0], data[2:2+iei_len])
            out+= " " + rv
            data = data[2+iei_len:]
            continue
        break

    return (out[1:], data)

def p_tv(iei, data):
    if False:
        pass
# Type 1i/3i
    elif iei == 0x201: # AccessDisposition + AccessDetailCode  / ff: lock?
        ad=data[0]>>4
        adc=data[0]&0xf
        rv=""
        if ad==0:
            rv="R:ok   "
        else:
            rv="R:NOT[%x]"%ad
        if adc==2:
            rv+=" (Location Update was not accepted)"
        elif adc==0:
            pass
        else:
            rv+=" (unknown:%x)"%(data[0]&0xf)
        return rv
    elif iei == 0x140: # GridCode
        pos=xyz(data, 4)
        return "xyz=(%+05d,%+05d,%+05d)"%(pos['x'],pos['y'],pos['z'])
    elif iei == 0x150: # Crc
        if data[0]&0xf ==0:
            return "crc:%02x%02x"%(data[2],data[1])
        else:
            return "crc[%d]:%02x%02x"%(data[0]&0x0f,data[2],data[1])
    elif iei == 0x1d0: # UnlockKey
        return "unlock:%s"%data.hex()

    elif iei == 0x202: # AccessDisposition + AccessDenialCause
        return "AD:%s ADC:%s"%(data[0]>>4, data[0]&0xf)
    elif iei == 0x203: # GwInternalGeoloc (sat + beam + (c1/c6) + "usually zero")
        return "sat:%03d beam:%02d %x %s"%(data[0],data[1],data[2],data[3:].hex()) # data[3:] usually zero
    elif iei == 0x1e0: # ManualRegistration IEI
        return "mre:%x"%(data[0]&0xf)
    elif iei == 0x1a0: # TeleService support IEI
        return "tss:%x"%(data[0]&0xf)
    elif iei == 0x104: # Location Area Code
        return "lac:%s"%data.hex()
    elif iei == 0x161: # Service Control Area
        return "sca:%s"%data.hex()
    elif iei == 0x119: # ReRegistration distance
        return "rrd:%s"%data.hex()
    elif iei == 0x11a: # ReRegistration error
        return "rre:%s"%data.hex()
    elif iei == 0x118: # AttachEnabled prob
        return "aep:%s"%data.hex()
    elif iei == 0x11b: # GridCode
        pos=xyz(data, 0)
        if data[4]&0x4 == 0:
            return "xyz=(%+05d,%+05d,%+05d)"%(pos['x'],pos['y'],pos['z'])
        else:
            return "xyz=(%+05d,%+05d,%+05d) [%d]"%(pos['x'],pos['y'],pos['z'],data[4]&0xf)

# Type 1
    elif iei == 0xd0: # Repeat indicator             - 10.5.4.22
        return "repeat indi.: %d"%data
    elif iei == 0x80: # Priority                     - 10.5.1.11
        pv=data&0x7
        return "prio:"+["none", "4", "3", "2", "1", "0", "B", "A"][pv]
# Type 2
    elif iei == 0xa1: # Follow on proceed            - 10.5.3.7
        return "Follow-on Proceed"
    elif iei == 0xa2: # CTS permission               - 10.5.3.10
        return "CTS permission"
# Type 3
    elif iei == 0x34: # Signal                       - 10.5.4.23
        return "signal:%02x"%data
# Type 4
    elif iei == 0x5c: # Calling party BCD num.       - 10.5.4.9
        return "src:[%s]"%p_bcd_num(data)
    elif iei == 0x5e: # Called party BCD num.        - 10.5.4.7
        return "dest:[%s]"%p_bcd_num(data)
    elif iei == 0x1e: # Progress indicator           - 10.5.4.21
        return "Progress[%s]"% p_progress(data)
    elif iei == 0x04: # Bearer capa                  - 10.5.4.5
        return "BC[%s]"%p_bearer_capa(data)
    elif iei == 0x4c: # Connected number             - 10.5.4.13
        return "num:[%s]"%p_bcd_num(data)
    elif iei == 0x08: # Cause                        - 10.5.4.11
        return "%s"%p_disc(data)
    elif iei == 0x1c: # Facility                     - 10.5.4.15
        return p_facility(data)
    elif iei == 0x17: # Mobile identity              - 10.5.1.4
        return p_mi(data)
    elif iei == 0x13: # Location Area Identification - 10.5.1.3
        return p_lai(data)
    elif iei == 0x41: # Mobile station classmark 1   - 10.5.1.5 (0x41 is a guess)
        if data[0]==0x28:
            return ""
        return "CM1[%02x]"%data[0]
    #5D Calling party subaddr.       - 10.5.4.10
    #6D Called party subaddr.        - 10.5.4.8
    #74 Redirecting party BCD num.   - 10.5.4.21a
    #75 Redirecting party subaddress - 10.5.4.21b
    #7C Low layer comp.              - 10.5.4.18
    #7D High layer comp.             - 10.5.4.16
    #7E User-user                    - 10.5.4.25
    #19 Alerting Pattern             - 10.5.4.26
    #4D Connected subaddress         - 10.5.4.14
    #15 Call Control Capabilities    - 10.5.4.5a
    elif iei in (0x5d, 0x6d, 0x74, 0x75, 0x7c, 0x7d, 0x7e, 0x19, 0x4d, 0x15):
        return "%02x:[%s]"%(iei, data.hex(":"))
# Unmatched
    else:
        if data == None:
            return "ERR:UK_T:%02x"%(iei)
        else:
            return "ERR:UK_TV:%02x:[%s]"%(iei, data.hex(":"))

sbd_crc=crcmod.mkCrcFun(poly=0x11021,initCrc=0,rev=True,xorOut=0xffff)

# Ad-Hoc parsing of the reassembled LAPDm-like frames
class ReassembleIDAPP(ReassembleIDA):
    def consume(self,q):
        (data,time,ul,_,freq)=q
        if len(data)<2:
            return

        freq_print=channelize_str(freq)

        if ul:
            ul="UL"
        else:
            ul="DL"

        tmaj="%02x"%(data[0])
        tmin="%02x%02x"%(data[0],data[1])

        typ=tmin
        if tmaj=="83" or tmaj=="89": # Transaction Identifier set (destination side)
            typ="%02x%02x"%(data[0]&0x7f,data[1])
        data=data[2:]
        majmap={ # 04.07 - Table 11.2
            "03": "CC",       # Call Control
            "83": "CC(dest)",
            "05": "MM",       # Mobility Management
            "06": "06",       # Iridium-specific (Radio Resource)
            "08": "08",       # Iridium-specific (GPRS Mobility mgmt)
            "09": "SMS",      # SMS
            "89": "SMS(dest)",
            "76": "SBD",      # Iridum-specific
        }
        minmap={
            "0301": "Alerting", # 04.08 - Table 10.3
            "0302": "Call Proceeding",
            "0303": "Progress",
            "0305": "Setup",
            "0307": "Connect",
            "0308": "Call Confirmed",
            "030f": "Connect Acknowledge",
            "0325": "Disconnect",
            "032a": "Release Complete",
            "032d": "Release",
            "0502": "Location Updating Accept", # 04.08 - Table 10.2
            "0504": "Location Updating Reject",
            "0508": "Location Updating Request",
            "0512": "Authentication Request",
            "0514": "Authentication Response",
            "0518": "Identity request",
            "0519": "Identity response",
            "051a": "TMSI Reallocation Command",
            "051b": "TMSI Reallocation Complete",
            "0521": "CM Service Accept",
            "0524": "CM Service Request",
            "0901": "CP-DATA", # 04.11 - Table 8.1
            "0904": "CP-ACK",
            "0910": "CP-ERROR",
            "0600": "Access Request Message", # no spec
            "0605": "Access decision",
            "7605": "Access decision",
            "7608": "downlink #1",
            "7609": "downlink #2",
            "760a": "downlink #3+",
            "760c": "uplink initial",
            "760d": "uplink #2",
            "760e": "uplink #3",
        }

        if tmin in ("063a", "083a", "7608", "7609", "760c")  and len(data)==0:
            return

        if typ in minmap:
            tstr="["+majmap[tmaj]+": "+minmap[typ]+"]"
        else:
            if tmaj in majmap:
                tstr="["+majmap[tmaj]+": ?]"
            else:
                tstr="[?]"

#        print >>outfile, "%15.6f"%(time),
        if 'alt' in config.args:
            print("     p-%d      %014.4f"%(_starttime, 1000*(time-_starttime)), end=' ', file=outfile)
        else:
            strtime=datetime.datetime.fromtimestamp(time,tz=Z).strftime("%Y-%m-%dT%H:%M:%S.{:02.0f}Z".format(int((time%1)*100)))
            print("%s"%strtime, end=' ', file=outfile)
        print("%s %s [%s] %-36s"%(freq_print,ul,tmin,tstr), end=' ', file=outfile)

        if typ in ("0600","760c","760d","760e","7608","7609","760a") and len(data)>0: # SBD
            prehdr=""
            hdr=""
            addlen=None

            if ul=='UL' and typ in ("0600"):
                #       0  1  2  3  4  5  6  7  8  9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28
                #      20:13:f0:10:02|5+IMEI                 |MOMSN|MC|_c|LN|??|MID  |           |TIME
                #      10:13:f0:10|TMSI       |LAC1 |LAC2 |00:00:00|MC|xx xy yy zz z0|           |TIME
                hdr=data[:29]
                if len(hdr)<29:
                    # packet too short
                    print("ERR:short", file=outfile)
                    return

                data=data[29:]
                prehdr="%02x"%hdr[0]

                sc=hdr[1:4].hex() # service center
                if sc == "13f010":
                    sc="ISC   "
                elif sc == "07F010":
                    sc="TSC   "

                doppler, delay=struct.unpack(">hH",hdr[21:25]) # doppler shift/10Hz, propagation delay/us

                if hdr[0] in (0x20,):
                    prehdr+="(SBD)"

                    prehdr+=" "+sc

                    prot_rev=hdr[4]
                    prehdr+=" v:%02x"%prot_rev

                    bcd=["%x"%(x>>s&0xf) for x in hdr[5:13] for s in (0,4)]
                    prehdr+=" "+bcd[0]+",imei:"+"".join(bcd[1:])
                    prehdr+=" MOMSN=%02x%02x"%(hdr[13],hdr[14])
                    prehdr+=" msgct:%d"%hdr[15]

                    if prot_rev==0: # Old
                        addlen=hdr[18]

                        prehdr+=" "+hdr[16:18].hex(":")
                        prehdr+=" "
                        prehdr+=" len=%03d"%addlen
                    elif prot_rev==1: # Old
                        addlen=hdr[17]

                        prehdr+=" "+hdr[16:17].hex(":")
                        prehdr+=" "
                        prehdr+=" len=%03d"%addlen
                        prehdr+=" "+hdr[18:19].hex(":")
                    elif prot_rev==2: # Current
                        addlen=hdr[17]

                        sessiontype_ringalertflags = hdr[16]
                        if sessiontype_ringalertflags == 0x0:
                            prehdr+= " STD" # STANDARD
                        elif sessiontype_ringalertflags == 0x0c:
                            prehdr+= " EXT" # EXTENDED
                        elif sessiontype_ringalertflags == 0x1c:
                            prehdr+= " EXA" # EXTENDED_ATTR
                        elif sessiontype_ringalertflags == 0x3c:
                            prehdr+= " REG" # REGISTRATION
                        elif sessiontype_ringalertflags == 0x2c:
                            prehdr+= " ARG" # AUTO_REGISTRATION
                        elif sessiontype_ringalertflags == 0x20:
                            prehdr+= " DET" # DETACH
                        else:
                            prehdr+= " ???"
                        prehdr+=" len=%03d"%addlen
                        prehdr+=" "+hdr[18:19].hex(":") # Delivery shortcode (0x80: hold MT delivery, 0x40: leave MT msg after deliv., 0x20: Destination in MO payload)

                    else: # Future/Unknown?
                        addlen=hdr[17]

                        prehdr+=" "+hdr[16:17].hex(":")
                        prehdr+=" len=%03d"%addlen
                        prehdr+=" "+hdr[18:19].hex(":")

                    # crc(payload + 5:imei + MOMSN + timestamp )
                    crcval=sbd_crc( data + hdr[5:13] + hdr[13:15] + hdr[25:29] )
                    pktcrc=struct.unpack("<H",hdr[19:21])[0]

                    if crcval==pktcrc:
                        prehdr+=" crc:OK"
                    else:
                        prehdr+=" crc:no"

                    prehdr+="[%04x]"%pktcrc

                    prehdr+=f" ds:{doppler:+05}0Hz pd:{delay:05}us"

                    ts=hdr[25:]
                    tsi=int(ts.hex(), 16)
                    _, strtime=fmt_iritime(tsi)
                    prehdr+=" t:"+strtime
                    if addlen>0:
                        prehdr+=" -"
                elif hdr[0] in (0x10,0x40,0x70): # 0x50 EMERGENCY,  0x30 DETACH
                    # lower nibble: ISO_POWER_CLASS (from EPROM)
                    if hdr[0] == 0x10:
                        prehdr+="(REG)" # REQ_TYPE_LOCATION_UPDATE
                    elif hdr[0] == 0x40:
                        prehdr+="(SMS)" # UTIL_MOBILE_TERM
                    elif hdr[0] == 0x70:
                        prehdr+="(CAL)" # OUTGOING?

                    prehdr+=" "+sc
                    prehdr+=" tmsi:"+ "".join(["%02x"%x for x in hdr[4:8]])
                    prehdr+=" lac:%02x%02x"%(hdr[8],hdr[9])
                    prehdr+=" sca:%02x%02x"%(hdr[10],hdr[11]) # service control area
                    parameter_master_version=int(hdr[12:16].hex(),16) # Always 1
                    prehdr+=" v:%d"%parameter_master_version

                    pos=xyz(hdr[16:])
                    prehdr+=" xyz=(%+05d,%+05d,%+05d)"%(pos['x'],pos['y'],pos['z'])
                    prehdr+=",%x"%(hdr[20]&0xf)

                    prehdr+="%13s"%"" # padding to sync up with SBD variant

                    prehdr+=f" ds:{doppler:+05}0Hz pd:{delay:05}us"

                    ts=hdr[25:]
                    tsi=int(ts.hex(), 16)
                    _, strtime=fmt_iritime(tsi)
                    prehdr+=" t:"+strtime

                    if len(data)>=21 and data[0] == 0x1c: # fixed length 'gateway location data'
                        t1=data[:21]
                        data=data[21:]
                        prehdr+=" {%02x:%s}"%(0x1c,t1[1:].hex("."))
                    if len(data)>=2 and data[0] == 0x6c: # TLV
                        # candidates for handoff.
                        # List of beam_id and some power value as seen by the ISU
                        prehdr+=" CAND-POWER:"
                        t2l=data[1]
                        if len(data)>=2+t2l and t2l%2==0:
                            t2v=struct.unpack(f">{t2l//2}H",data[2:2+t2l])

                            svloc_enum=[
                                "SAME",
                                "IN_FORE", # same plane
                                "IN_AFT",
                                "CROSS_RIGHT_CO_FORE", # CO-rotating plane
                                "CROSS_LEFT_CO_FORE",
                                "CROSS_RIGHT_CO_AFT",
                                "CROSS_LEFT_CO_AFT",
                                "CROSS_RIGHT_COUNTER_FORE", # COUNTER-rotating plane
                                "CROSS_LEFT_COUNTER_FORE",
                                "CROSS_RIGHT_COUNTER_AFT",
                                "CROSS_LEFT_COUNTER_AFT",
                                "?" # should not happen
                            ]

                            for x in t2v:
                                power= x & 0x3f
                                beam = (x >> 6)& 0x3f
                                svloc = x >>12
                                if svloc>10: svloc=11
                                prehdr+=" %s(%02d)=%02d"%(svloc_enum[svloc], beam, power)

                            data=data[2+t2l:]
                        else:
                            prehdr+="[ERR:invalid_len]"
                else:
                    prehdr+="[ERR:hdrtype]"
                    prehdr+=" "+hdr[1:4].hex(":")
                    prehdr+=" "+hdr[4:13].hex(":")
                    prehdr+=" "+hdr[13:15].hex(":")
                    prehdr+=" msgct:%d"%hdr[15]
                    prehdr+=" "+hdr[16:21].hex(":")

                    prehdr+=" "+hdr[21:25].hex(":")
                    prehdr+=" "+hdr[25:].hex(":")

            elif ul=='UL' and typ in ("760c","760d","760e"):
                if data[0]==0x50:
                    # <50:xx:xx> MTMSN echoback?
                    hdr=data[:3]
                    data=data[3:]

                    pktcrc=struct.unpack("<H",hdr[1:3])[0]

                    prehdr="[%02x crc:%04x]"%(hdr[0],pktcrc)

            elif ul=='DL' and typ in ("7608","7609","760a"):
                if typ=="7608":
                    # <26:44:9a:01:00:ba:85> <20:44:9a:01:00>
                    # 1: 26 or 20
                    # 2+3: sequence number (MTMSN)
                    # 4: number of packets in message
                    # 5: number of messages waiting to be delivered / backlog
                    # 6+7: "ack request" (answer: <50:xx:xx>) -- only for <26>

                    if data[0]==0x26:
#                        prehdr=data[:7]
                        prehdr="<%02x MTMSN=(%02x%02x) msgct:%d backlog=%d mid=(%02x:%02x)>"%(data[0],data[1],data[2],data[3],data[4],data[5],data[6])
                        data=data[7:]
                    elif data[0]==0x20:
#                        prehdr=data[:5]
                        prehdr="<%02x MTMSN=(%02x%02x) msgct:%d backlog=%d>"%(data[0],data[1],data[2],data[3],data[4])
                        data=data[5:]
                    else:
                        prehdr="<ERR:prehdr_type?>"

            else:
                prehdr="<ERR:nomatch>"

            print("%s"%(prehdr), end=' ', file=outfile)

            if typ != "0600" and len(data)>0:
                if data[0]==0x10:
                    # <10:87:01>
                    # 1: always 10
                    # 2: length in bytes of message
                    # 3: number of packet (760c => 2, 760d => 3, 760e => 4)
                    #                     (7608 => 1, 7609 => 2, 760a => 3+)
                    hdr=data[:3]
                    data=data[3:]
                    addlen=hdr[1]
                    print("<%s>"%hdr.hex(":"), end=' ', file=outfile)
                else:
                    print("ERR:no_0x10", end=" ", file=outfile)

            if addlen is not None and len(data)!=addlen:
                print("ERR:len(%d!=%d)"%(len(data),addlen), end=" ", file=outfile)

        elif typ=="7605": # Access decision notification
            (rv, data) = p_opt_tlv(data,
                    start=[(0x201,1)],
                    type1i=[(0x40,4),(0x50,2),(0xd0,9)])
            print(rv, end=' ', file=outfile)

        elif typ=="0605": # Access decision notification
            (rv, data) = p_opt_tlv(data,
                    start=[(0x202, 1),(0x203, 20)],
                    type1i=[(0xe0,0),(0xa0,0)],
                    type3i=[(0x04,2),(0x61,2),(0x19,1),(0x1a,1),(0x18,1),(0x1b,5),(0xa0,1)])
            print(rv, end=' ', file=outfile)

# > 0600 / 10:13:f0:10: tmsi+lac+lac+00 +bytes
# < 0605 ?
# > 0508 Location Updating Request
#  < 0512 Authentication Request
#  > 0514 Authentication Response
#  < 051a TMSI reallocation command [09 f1 30](MCC/MNC/LAC) + [08 f4]TMSI
#  < 0518 Identity request 02: IMEI
#  > 0519 Identity response (IMEI)
# < 0502 Location Updating Accept (MCC/MNC/LAC)

# > 0600 / 20:13:f0:10: 02 imei + momsn + msgcnt + XC + len + mid(A) + bytes + time + (len>0: msg)
# < 7608 <26:00:00:00:00:xx:xx> + misgcnt + backlog + mid(B) + message(optional)
# > 760c <50:xx:xx> ack(mid(B))
# < 7605 Access notification (+ack(mid(A))




        elif typ=="0305": # CC Setup 04.08 9.3.23
            (rv, data) = p_opt_tlv(data,
                    type4=(0x04, 0x1c, 0x1e, 0x34, 0x5c, 0x5d, 0x5e, 0x6d, 0x74, 0x75, 0x7c, 0x7d, 0x7e, 0x19),
                    type1=(0xd0, 0x80), type3=[(0x34,1)])
            print(rv, end=' ', file=outfile)

        elif typ=="0301": # CC Alerting 04.08 9.3.1
            (rv, data) = p_opt_tlv(data, type4=(0x1c, 0x1e, 0x7e))
            print(rv, end=' ', file=outfile)

        elif typ=="0307": # CC Connect 04.08 9.3.5
            (rv, data) = p_opt_tlv(data, type4=(0x1c, 0x1e, 0x4c, 0x4d, 0x7e))
            print(rv, end=' ', file=outfile)

        elif typ=="0308": # CC Call Confirmed 04.08 9.3.2
            (rv, data) = p_opt_tlv(data, type4=(0x04, 0x08, 0x15), type1=(0xd0, ))
            print(rv, end=' ', file=outfile)

        elif typ=="032d": # CC Release 04.08 9.3.18
            (rv, data) = p_opt_tlv(data, type4=(0x08, 0x1c, 0x7e))
            print(rv, end=' ', file=outfile)

        elif typ=="032a": # CC Release Complete 04.08 9.3.19
            (rv, data) = p_opt_tlv(data, type4=(0x08, 0x1c, 0x7e))
            print(rv, end=' ', file=outfile)

        elif typ=="0325": # CC Disconnect 04.08 9.3.7
            data=bytes([0x08]) + data # Prepend Type for Cause
            (rv, data) = p_opt_tlv(data, type4=(0x08, 0x1c, 0x1e, 0x7e, 0x7b))
            print(rv, end=' ', file=outfile)

        elif typ=="0302": # CC Call Proceeding 04.08 9.3.3
            (rv, data) = p_opt_tlv(data, type4=(0x04, 0x1c, 0x1e), type1=(0xd0, 0x80))
            print(rv, end=' ', file=outfile)

        elif typ=="0303": # CC Progress 04.08 9.3.17
            data=bytes([0x1e]) + data # Prepend Type for Progress
            (rv, data) = p_opt_tlv(data, type4=(0x1e, 0x7e))
            print(rv, end=' ', file=outfile)

        elif typ=="0502": # MM Location updating accept 04.08 9.2.13
            (rv, data) = p_opt_tlv(data, type4=(0x17,), type2=(0xa1, 0xa2), start=[(0x13,5)])
            print(rv, end=' ', file=outfile)

        elif typ=="0508": # MM Location updating request 04.08 9.2.15
            if data[0]&0xf!=0:
                print("Type=%x", end=' ', file=outfile)
            if data[0]>>4 == 7: # Ciphering Key Sequence Number 10.5.1.2
                print("key=none", end=' ', file=outfile)
            else:
                print("key=%x"%(data[0]>>4), end=' ', file=outfile)

            (rv, data) = p_opt_tlv(data[1:], start=[(0x13,5),(0x41,1),(0x17,-1)])
            print(rv, end=' ', file=outfile)

        elif typ=="051a": # MM TMSI realloc. 9.2.17
            (rv, data) = p_opt_tlv(data, start=[(0x13,5),(0x17,-1)])
            print(rv, end=' ', file=outfile)

        elif typ=="0504": # Loc up rej.
            if data[0]==2:
                print("02(IMSI unknown in HLR)", end=' ', file=outfile)
                data=data[1:]
        elif typ=="0518": # Identity Req
            if data[0]==2:
                print("02(IMEI)", end=' ', file=outfile)
                data=data[1:]
            elif data[0]==1:
                print("01(IMSI)", end=' ', file=outfile)
                data=data[1:]
        elif typ=="0519": # Identity Resp. 9.2.11
            (rv, data) = p_opt_tlv(data, start=[(0x17,-1)])
            print(rv, end=' ', file=outfile)
        elif typ=="0524": # CM Service Req. 9.2.9
            # Ciphering key seqno 10.5.1.2
            if data[0]>>4 == 7: # 10.5.1.2
                print("key=none", end=' ', file=outfile)
            else:
                print("key=%d"%(data[0]>>4), end=' ', file=outfile)

            # CM service type 10.5.3.3
            if data[0]&0xf == 4:
                print("[SMS]", end=' ', file=outfile)
            elif data[0]&0xf == 1:
                print("[MO call/pkt mode]", end=' ', file=outfile)
            else:
                print("[SVC:%d]"%(data[0]&0xf), end=' ', file=outfile)

            data=data[1:]

            # Mobile station classmark 2 10.5.1.6
            (rv,data)=p_cm2(data)
            print("[%s]"%(rv), end=' ', file=outfile)

            (rv, data) = p_opt_tlv(data, type1=(0x80), start=[(0x17,-1)])
            print(rv, end=' ', file=outfile)

        if len(data)>0:
            print(" ".join("%02x"%x for x in data), end=' ', file=outfile)
            print(" | %s"%to_ascii(data, dot=True), file=outfile)
        else:
            print("", file=outfile)
        return

class ReassembleIDALAP(ReassembleIDA):
    first=True
    sock = None
    def gsmwrap(self,q):
        (data,time,ul,level,freq)=q
        lapdm=data
        try:
            olvl=int(level)
        except (ValueError, OverflowError):
            olvl=0
        if olvl>127:
            olvl=127
        if olvl<-126:
            olvl=-126

        fchan, foff = channelize(freq)

        if fchan < 0: # Can happen if frequencies are off
            fchan += 0x2000

        # GSMTAP:
        #
        #struct gsmtap_hdr {
        #        uint8_t version;        /* version, set to 0x01 currently */      2
        #        uint8_t hdr_len;        /* length in number of 32bit words */     4
        #        uint8_t type;           /* see GSMTAP_TYPE_* */                   2 (ABIS) / 0x13 (IRIDIUM)
        #        uint8_t timeslot;       /* timeslot (0..7 on Um) */               0
        #
        #        uint16_t arfcn;         /* ARFCN (frequency) */                   0x0/0x4000
        #        int8_t signal_dbm;      /* signal level in dBm */                 olvl
        #        int8_t snr_db;          /* signal/noise ratio in dB */            0 ?
        #        uint32_t frame_number;  /* GSM Frame Number (FN) */               freq??
        #        uint8_t sub_type;       /* Type of burst/channel, see above */    1 (BCCH) / 7 (?)
        #        uint8_t antenna_nr;     /* Antenna Number */                      0 ?
        #        uint8_t sub_slot;       /* sub-slot within timeslot */            0 ?
        #        uint8_t res;            /* reserved for future use (RFU) */       0 ?
        #} +attribute+((packed));
        if ul:
            gsm=struct.pack("!BBBBHbBLBBBB",2,4,2,0,0x4000+fchan,olvl,0,int(freq),1,0,0,0)+lapdm
        else:
            gsm=struct.pack("!BBBBHbBLBBBB",2,4,2,0,0x0000+fchan,olvl,0,int(freq),1,0,0,0)+lapdm

        return gsm

    def consume(self,q):
        # Filter non-GSM packets (see IDA-GSM.txt)
        if self.first:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.first=False
            print("Sending GSMTAP via UDP 4729")

        (data,time,ul,level,freq)=q
#        if ord(data[0])&0xf==6 or ord(data[0])&0xf==8 or (ord(data[0])>>8)==7:
#            return
        if len(data)==1:
            return
        pkt=self.gsmwrap(q)
        self.sock.sendto(pkt, ("127.0.0.1", 4729)) # 4729 == GSMTAP

        if config.verbose:
            if ul:
                ul="UL"
            else:
                ul="DL"
            print("%15.6f %.3f %s %s"%(time,level,ul,".".join("%02x"%ord(x) for x in data)))

class ReassembleIDALAPPCAP(ReassembleIDALAP):
    def __init__(self):
        super().__init__()
        global outfile
        if outfile == sys.stdout: # Force file, since it's binary
            config.output="%s.%s" % (config.outbase, "pcap")
        outfile=open(config.output,"wb")

    first=True
    def consume(self,q):
        # Most of this constructs fake ip packets around the gsmtap data so it can be written as pcap
        if self.first:
            #typedef struct pcap_hdr_s {
            #        guint32 magic_number;   /* magic number */            0xa1b2c3d4
            #        guint16 version_major;  /* major version number */    2
            #        guint16 version_minor;  /* minor version number */    4
            #        gint32  thiszone;       /* GMT to local correction */ 0
            #        guint32 sigfigs;        /* accuracy of timestamps */  0
            #        guint32 snaplen;        /* max length of captured packets, in octets */
            #                                                              (must be > largest pkt)
            #        guint32 network;        /* data link type */          1 (ethernet)
            #} pcap_hdr_t;
            pcap_hdr=struct.pack("<LHHlLLL",0xa1b2c3d4,0x2,0x4,0x0,0,0xffff,1)
            outfile.write(pcap_hdr)
            self.first=False

        # Filter non-GSM packets (see IDA-GSM.txt)
        (data,time,ul,_,_)=q
        if 'all' in config.args:
            pass
        else:
            if data[0]&0xf==6 or data[0]&0xf==8 or (data[0]>>8)==7: # XXX: should be >>4?
                return
            if len(data)==1:
                return
        gsm=self.gsmwrap(q)
        udp=struct.pack("!HHHH",45988,4729,8+len(gsm),0xffff)+gsm  # 4729 == GSMTAP

        if ul:
            ip=struct.pack("!BBHHBBBBHBBBBBBBB",(0x4<<4)+5,0,len(udp)+20,0xdaae,0x40,0x0,0x40,17,0xffff,10,0,0,1,127,0,0,1)+udp
        else:
            ip=struct.pack("!BBHHBBBBHBBBBBBBB",(0x4<<4)+5,0,len(udp)+20,0xdaae,0x40,0x0,0x40,17,0xffff,127,0,0,1,10,0,0,1)+udp

        if ul:
            eth=struct.pack("!BBBBBBBBBBBBH",0xaa,0xbb,0xcc,0xdd,0xee,0xff,0x10,0x22,0x33,0x44,0x55,0x66,0x800)+ip
        else:
            eth=struct.pack("!BBBBBBBBBBBBH",0x10,0x22,0x33,0x44,0x55,0x66,0xaa,0xbb,0xcc,0xdd,0xee,0xff,0x800)+ip

        pcap=struct.pack("<IIII",int(time),int(1000000*(time%1)),len(eth),len(eth))+eth
        outfile.write(pcap)

modes=[
["ida",        ReassembleIDA,  ],
["idapp",      ReassembleIDAPP,  ('alt') ],
["gsmtap",     ReassembleIDALAP,  ],
["lap",        ReassembleIDALAPPCAP,  ('all') ],
]
