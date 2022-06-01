#!/usr/bin/env python3
# vim: set ts=4 sw=4 tw=0 et pm=:

import sys
import datetime
import re
import struct
import socket
from util import fmt_iritime, to_ascii, xyz

from .base import *
from ..config import config, outfile

base_freq=1616*10**6
channel_width=41667

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

        fbase=freq-base_freq
        fchan=int(fbase/channel_width)
        foff =fbase%channel_width
        freq_print="%3d|%05d"%(fchan,foff)

        print("%15.6f %s %s %s | %s"%(time,freq_print,ul,data.hex(" "),str), file=outfile)

# Mobile station classmark 2 10.5.1.6
def p_cm2(data):
    cmlen=data[0] # Must be 3
    cmdata=data[1:cmlen+1]
    str="CM2:%s"%cmdata.hex()
    return (str, data[1+cmlen:])

def p_mi_iei(data):
    iei_len = data[0]
    iei_dig = data[1]>>4
    iei_odd = (data[1]>>3)&1
    iei_typ = data[1]&7

    if iei_typ==2 or iei_typ==1: # IMEI / IMSI
        if iei_odd==1 and iei_len==8:
            str="%x"%(iei_dig)
            str+="".join("%x%x"%((x)&0xf,(x)>>4) for x in data[2:2+7])
            return ("%s:%s"%(["","imsi","imei"][iei_typ],str),data[2+7:])
        else:
            return ("PARSE_FAIL",data)
    elif iei_typ==4: # TMSI
        if iei_odd==0 and iei_len==5 and iei_dig==0xf:
            str="tmsi:%02x%02x%02x%02x"%(data[2],data[3],data[4],data[5])
            return (str,data[6:])
        else:
            return ("PARSE_FAIL",data)
    else:
        return ("PARSE_FAIL",data)

def p_lai(lai): # 10.5.1.3
    if lai[1]>>4 != 15 or len(lai)<4:
        return ("PARSE_FAIL",lai)
    else:
        str="MCC=%d%d%d"%(lai[0]&0xf,lai[0]>>4,lai[1]&0xf)
        if lai[1]>>4 == 0xf:
            str+="/MNC=%d%d"%(lai[2]&0xf,lai[2]>>4)
        else:
            str+="/MNC=%d%d%d"%(lai[2]&0xf,lai[2]>>4,lai[1]>>4)
        str+="/LAC=%02x%02x"%(lai[3],lai[4])
        return (str,lai[5:])

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
        str+= " ERR:ADD_"+ disc[2:].hex(":")
#        if (disc[0]>>7)==1 and disc[0]==3 and disc[3]==0x88:
#            str+=" CCBS not poss."
#            return (str,disc[4:])

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
    else:
        return None

# Minimalistic TV & TLV parser
# 04.07     11.2.1.1.4
def p_opt_tlv(data, type4, type1=[], type3=[]):
    out = ""
    while len(data)>0:
        if data[0] & 0xf0 in type1:
            rv = p_tv(data[0] & 0xf0, data[0] & 0x0f)
            out+= " " + rv
            data = data[1:]
            continue
        if len(data) < 1:
            break
        if data[0] in type3:
            rv = p_tv(data[0], data[1])
            out+= " " + rv
            data = data[2:]
            continue
        if data[0] in type4:
            iei_len = data[1]
            if len(data) < 2+iei_len:
                out += "ERR:SHORT:"+data.hex(":")
                break
            rv = p_tlv(data[0], data[2:2+iei_len])
            if rv is not None:
                out+= " " + rv
            else:
                out+= " %02x:[%s]"%(data[0], data[2:2+iei_len].hex(":"))
            data = data[2+iei_len:]
            continue
        break

    return (out[1:], data)

def p_tv(iei, data):
    if iei == 0xd0: # Repeat indicator 10.5.4.22
        return "repeat indi.: %d"%data
    elif iei == 0x80: # Priority 10.5.1.11
        pv=data&0x7
        return "prio:"+["none", "4", "3", "2", "1", "0", "B", "A"][pv]
    elif iei == 0x34: # Signal 10.5.4.23
        return "signal:%02x"%data
    else:
        return "unknown_type1[%02x]=%02x"%(iei, data)

def p_tlv(iei, data):
    if iei == 0x5c:   # Calling party BCD num.       - 10.5.4.9
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
    elif iei in (0x1c, 0x5d, 0x6d, 0x74, 0x75, 0x7c, 0x7d, 0x7e, 0x19, 0x4d):
        return "%02x:[%s]"%(iei, data.hex(":"))
    else:
        return "UK_TLV:%02x:[%s]"%(iei, data.hex(":"))

# Ad-Hoc parsing of the reassembled LAPDm-like frames
class ReassembleIDAPP(ReassembleIDA):
    def consume(self,q):
        (data,time,ul,_,freq)=q
        if len(data)<2:
            return

        fbase=freq-base_freq
        fchan=int(fbase/channel_width)
        foff =fbase%channel_width
        freq_print="%3d|%05d"%(fchan,foff)

        if ul:
            ul="UL"
        else:
            ul="DL"

        tmaj="%02x"%(data[0])
        tmin="%02x%02x"%(data[0],data[1])
        if tmaj=="83" or tmaj=="89": # Transaction Identifier set (destination side)
            tmin="%02x%02x"%(data[0]&0x7f,data[1])
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
            "0600": "Register/SBD:uplink", # no spec
            "0605": "(info)",
            "7605": "Access notification",
            "7608": "downlink #1",
            "7609": "downlink #2",
            "760a": "downlink #3+",
            "760c": "uplink initial",
            "760d": "uplink #2",
            "760e": "uplink #3",
        }

        if tmin in ("063a", "083a", "7608", "7609", "760c")  and len(data)==0:
            return

        if tmin in minmap:
            tstr="["+majmap[tmaj]+": "+minmap[tmin]+"]"
        else:
            if tmaj in majmap:
                tstr="["+majmap[tmaj]+": ?]"
            else:
                tstr="[?]"

        typ=tmin
#        print >>outfile, "%15.6f"%(time),
        strtime=datetime.datetime.fromtimestamp(time,tz=Z).strftime("%Y-%m-%dT%H:%M:%S.{:02.0f}Z".format(int((time%1)*100)))
        print("%s"%strtime, end=' ', file=outfile)
        print("%s %s [%s] %-36s"%(freq_print,ul,typ,tstr), end=' ', file=outfile)

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
                prehdr="<"+hdr[0:4].hex(":")

                if hdr[0] in (0x20,):
                    prehdr+=" %02x"%hdr[4]
                    bcd=["%x"%(x>>s&0xf) for x in hdr[5:13] for s in (0,4)]
                    prehdr+=","+bcd[0]+",imei:"+"".join(bcd[1:])
                    prehdr+=" MOMSN=%02x%02x"%(hdr[13],hdr[14])
                    prehdr+=" msgct:%d"%hdr[15]

                    addlen=hdr[17]

                    prehdr+=" "+hdr[16:17].hex(":")
                    prehdr+=" len="+hdr[17:18].hex(":")
                    prehdr+=" "+hdr[18:19].hex(":")
                    prehdr+=" mid=("+hdr[19:21].hex(":")+")"

                    prehdr+=" "+hdr[21:25].hex(":")

                    ts=hdr[25:]
                    tsi=int(ts.hex(), 16)
                    _, strtime=fmt_iritime(tsi)
                    prehdr+=" t:"+strtime
                elif hdr[0] in (0x10,0x40,0x50,0x70):
                    prehdr+=" tmsi:"+ "".join(["%02x"%x for x in hdr[4:8]])
                    prehdr+=",lac1:%02x%02x"%(hdr[8],hdr[9])
                    prehdr+=",lac2:%02x%02x"%(hdr[10],hdr[11])
                    prehdr+=",%02x%02x%02x"%(hdr[12],hdr[13],hdr[14])
                    prehdr+=" msgct:%d"%hdr[15]

                    pos=xyz(hdr[16:])
                    prehdr+=" xyz=(%+05d,%+05d,%+05d)"%(pos['x'],pos['y'],pos['z'])
                    prehdr+=",%x"%(hdr[20]&0xf)
                    if pos['x'] == -1 and pos['y'] == -1 and pos['z'] == -1:
                        pass
                    else:
                        prehdr+=" pos=(%+06.2f/%+07.2f)"%(pos['lat'],pos['lon'])
                        prehdr+=" alt=%03d"%(pos['alt']-6378+23)

                    prehdr+=" "+hdr[21:25].hex(":")

                    ts=hdr[25:]
                    tsi=int(ts.hex(), 16)
                    _, strtime=fmt_iritime(tsi)
                    prehdr+=" t:"+strtime
                else:
                    prehdr+="[ERR:hdrtype]"
                    prehdr+=" "+hdr[4:15].hex(":")
                    prehdr+=" msgct:%d"%hdr[15]
                    prehdr+=" "+hdr[16:21].hex(":")

                    prehdr+=" "+hdr[21:25].hex(":")
                    prehdr+=" "+hdr[25:].hex(":")

                prehdr+=">"
                hdr=""
            elif ul=='UL' and typ in ("760c","760d","760e"):
                if data[0]==0x50:
                    # <50:xx:xx> MTMSN echoback?
                    prehdr=data[:3]
                    data=data[3:]

                    prehdr="<%02x mid=(%s)>"%(prehdr[0],prehdr[1:].hex(":"))

            elif ul=='DL' and typ in ("7608","7609","760a"):
                if typ=="7608":
                    # <26:44:9a:01:00:ba:85>
                    # 1: always? 26
                    # 2+3: sequence number (MTMSN)
                    # 4: number of packets in message
                    # 5: number of messages waiting to be delivered / backlog
                    # 6+7: unknown / maybe MOMSN?
                    #
                    # <20:33:17:03:01>
                    # fields same as above except 6+7

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
                    hdr="<"+hdr.hex(":")+">"
                else:
                    print("ERR:no_0x10", end=" ", file=outfile)

            print("%-22s %-10s "%(prehdr,hdr), end=' ', file=outfile)

            if addlen is not None and len(data)!=addlen:
                print("ERR:len(%d!=%d)"%(len(data),addlen), end=" ", file=outfile)

        elif typ=="7605": # Access decision notification
            # 00 43 b3 0e 44 e9 50 7f c0
            #   ||COORD        |  |MID
            if len(data)>0:
                if data[0]&0xf0 == 0:
                    print("R:ok   ", end=" ", file=outfile)
                else:
                    print("R:NOT[%x]"%((data[0]&0xf0)>>4), end=" ", file=outfile)

                if data[0]&0xf == 2:
                    print("(Location Update was not accepted)", end=" ", file=outfile)
                elif data[0]&0xf ==0:
                    pass
                else:
                    print("(unknown:%x)"%(data[0]&0xf), end=" ", file=outfile)
                data=data[1:]

            if len(data)> 4 and data[0]&0xf0 == 0x40:
                pos=xyz(data, 4)
                print("xyz=(%+05d,%+05d,%+05d)"%(pos['x'],pos['y'],pos['z']), end=" ", file=outfile)
                print("pos=(%+06.2f/%+07.2f)"%(pos['lat'],pos['lon']), end=" ", file=outfile)
                print("alt=%03d"%(pos['alt']-6378+23), end=" ", file=outfile)
                data=data[5:]

            if len(data)> 2 and data[0]&0xf0 == 0x50:
                print("[%02x mid=(%s)]"%(data[0],data[1:3].hex(":")), end=" ", file=outfile)
                data=data[3:]

        elif typ=="0605": # ?
            # 00 5a 14 c1 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
            #   |^ |^ |  | mostly zero                                      |
            #    |  Beam
            #    Sat
            # >> 04 18 c9 61 18 5d e0 19 0a 1a 4c 18 00 1b 3b 50 89 4f 50
            #      |LAC  |  |LAC  |  |LAC  |              | COORD       |
            if len(data)>=20:
                print("%02x sat:%03d beam:%02d %02x"%(data[0],data[1],data[2],data[3]), end=" ", file=outfile)
                print(data[4:21].hex(), end=" ", file=outfile)
                data=data[21:]
                if len(data)==19:
                    if data[0]==4:
                        print(data[0:1].hex(), end=" ", file=outfile)
                        print("LAC1=%s"%data[1:3].hex(), end=" ", file=outfile)
                        print(data[3:4].hex(), end=" ", file=outfile)
                        print("LAC2=%s"%data[4:6].hex(), end=" ", file=outfile)
                        print(data[6:7].hex(), end=" ", file=outfile)
                        print("LAC3=%s"%data[7:9].hex(), end=" ", file=outfile)
                        print(data[9:14].hex(":"), end=" ", file=outfile)

                        pos=xyz(data[14:])
                        print("xyz=(%+05d,%+05d,%+05d)"%(pos['x'],pos['y'],pos['z']), end=" ", file=outfile)
                        print("pos=(%+06.2f/%+07.2f)"%(pos['lat'],pos['lon']), end=" ", file=outfile)
                        print("alt=%03d"%(pos['alt']-6378+23), end=" ", file=outfile)

                        print("[%d]"%(data[14+4]&0xf), end=" ", file=outfile)
                        data=data[14+5:]

# > 0600 / 10:13:f0:10: tmsi+lac+lac+00 +bytes
# < 0605 ?
# > 0508 Location Updating Request
#  < 0512 Authentication Request
#  > 0514 Authentication Response
#  < 051a TMSI reallocation command [09 f1 30](MCC/MNC/LAC) + [08 f4]TMSI
#  < 0518 Identity request 02: IMEI
#  > 0519 Identity response (IMEI)
# < 0502 Location Updating Accept (MCC/MNC/LAC)

# > 0600 / 20:13:f0:10: 02 imei + momsn + msgcnt + XC + len + bytes + time + (len>0: msg)
# < 7608 <26:00:00:00:00:xx:xx> 0 messages (xx=MTMSN?)
# > 760c <50:xx:xx> MTMSN echoback?
# < 7605 ?




        elif typ=="0305": # CC Setup 04.08 9.3.23
            (rv, data) = p_opt_tlv(data,
                    (0x04, 0x1c, 0x1e, 0x34, 0x5c, 0x5d, 0x5e, 0x6d, 0x74, 0x75, 0x7c, 0x7d, 0x7e, 0x19),
                    type1=(0xd0, 0x80), type3=(0x34,))
            print(rv, end=' ', file=outfile)

        elif typ=="0301": # CC Alerting 04.08 9.3.1
            (rv, data) = p_opt_tlv(data, (0x1c, 0x1e, 0x7e))
            print(rv, end=' ', file=outfile)

        elif typ=="0307": # CC Connect 04.08 9.3.5
            (rv, data) = p_opt_tlv(data, (0x1c, 0x1e, 0x4c, 0x4d, 0x7e))
            print(rv, end=' ', file=outfile)

        elif typ=="0308": # CC Call Confirmed 04.08 9.3.2
            (rv, data) = p_opt_tlv(data, (0x04, 0x08, 0x15), type1=(0xd0, ))
            print(rv, end=' ', file=outfile)

        elif typ=="032d": # CC Release 04.08 9.3.18
            (rv, data) = p_opt_tlv(data, (0x08, 0x1c, 0x7e))
            print(rv, end=' ', file=outfile)

        elif typ=="032a": # CC Release Complete 04.08 9.3.19
            (rv, data) = p_opt_tlv(data, (0x08, 0x1c, 0x7e))
            print(rv, end=' ', file=outfile)

        elif typ=="0325": # CC Disconnect 04.08 9.3.7
            data=bytes([0x08]) + data # Prepend Type for Cause
            (rv, data) = p_opt_tlv(data, (0x08, 0x1c, 0x1e, 0x7e, 0x7b))
            print(rv, end=' ', file=outfile)

        elif typ=="0302": # CC Call Proceeding 04.08 9.3.3
            (rv, data) = p_opt_tlv(data, (0x04, 0x1c, 0x1e), type1=(0xd0, 0x80))
            print(rv, end=' ', file=outfile)

        elif typ=="0303": # CC Progress 04.08 9.3.17
            data=bytes([0x1e]) + data # Prepend Type for Progress
            (rv, data) = p_opt_tlv(data, (0x1e, 0x7e))
            print(rv, end=' ', file=outfile)

        elif typ=="0502": # Loc up acc.
            (rv,data)=p_lai(data)
            print("%s"%(rv), end=' ', file=outfile)
            if len(data)>=1 and data[0]==0x17:
                data=data[1:]
                (rv,data)=p_mi_iei(data)
                print("%s"%(rv), end=' ', file=outfile)
            if len(data)>=1 and data[0]==0xa1:
                print("Follow-on Proceed", end=' ', file=outfile)
                data=data[1:]
        elif typ=="0508": # Loc up req.
            if data[0]&0xf==0 and data[6]==0x28: # 6 == Mobile station classmark
                if data[0]>>4 == 7:
                    print("key=none", end=' ', file=outfile)
                else:
                    print("key=%d"%(data[0]>>4), end=' ', file=outfile)
                data=data[1:]

                (rv,data)=p_lai(data)
                print("%s"%(rv), end=' ', file=outfile)

                data=data[1:] # skip classmark

                (rv,data)=p_mi_iei(data)
                print("%s"%(rv), end=' ', file=outfile)
        elif typ=="051a": # TMSI realloc. 9.2.17
            (rv,data)=p_lai(data)
            print("%s"%(rv), end=' ', file=outfile)
            (rv,data)=p_mi_iei(data)
            print("%s"%(rv), end=' ', file=outfile)
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
        elif typ=="0519": # Identity Resp.
            (rv,data)=p_mi_iei(data)
            print("[%s]"%(rv), end=' ', file=outfile)
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

            # Mobile identity 10.5.1.4
            (rv,data)=p_mi_iei(data)
            print("[%s]"%(rv), end=' ', file=outfile)

            # Priority 10.5.1.11
            if len(data)>0:
                print("[PRIO:%02x]"%data[0], end=' ', file=outfile)
                data=data[1:]

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

        fbase=freq-base_freq
        fchan=int(fbase/channel_width)
        foff =fbase%channel_width

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
            gsm=struct.pack("!BBBBHbBLBBBB",2,4,2,0,0x4000+fchan,olvl,0,freq,1,0,0,0)+lapdm
        else:
            gsm=struct.pack("!BBBBHbBLBBBB",2,4,2,0,0x0000+fchan,olvl,0,freq,1,0,0,0)+lapdm

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
["idapp",      ReassembleIDAPP,  ],
["gsmtap",     ReassembleIDALAP,  ],
["lap",        ReassembleIDALAPPCAP,  ('all') ],
]
