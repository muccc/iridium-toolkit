#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# vim: set ts=4 sw=4 tw=0 et pm=:

import sys
import re
import struct
import fileinput
import datetime
from math import sqrt,atan2,pi,log

import crcmod
from bch import ndivide, nrepair, bch_repair, bch_repair1
import rs
import rs6

from util import *
import itl

iridium_access="001100000011000011110011" # Actually 0x789h in BPSK
uplink_access= "110011000011110011111100" # BPSK: 0xc4b
next_access_dl = "110011110011111111111100" # 0xdab
next_access_ul = "001111000000000011111111" # 0x40a
UW_DOWNLINK = [0,2,2,2,2,0,0,0,2,0,0,2]
UW_UPLINK   = [2,2,0,0,0,2,0,0,2,0,2,2]
NXT_UW_DOWNLINK = [2,2,0,2,2,0,2,0,2,0,2,2]
NXT_UW_UPLINK   = [0,2,0,0,0,0,0,0,2,0,2,0]
header_messaging="00110011111100110011001111110011" # 0x9669 in BPSK
header_time_location="11"+"0"*94
messaging_bch_poly=1897
ringalert_bch_poly=1207
acch_bch_poly=3545 # 1207 also works?
hdr_poly=29 # IBC header

f_doppler= 36e3  # maximum doppler_shift
f_jitter=   1e3  # iridium-extractor precision
sdr_ppm=  100e-6 # SDR freq offset

f_simplex = (1626104e3 - f_doppler - f_jitter ) * (1- sdr_ppm) # lower bound for simplex channel
f_duplex  = (1625979e3 + f_doppler + f_jitter ) * (1+ sdr_ppm) # upper bound for duplex cannel

# commandline arguments
args = None

def set_opts(new_args):
    global args
    args = new_args

class ParserError(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.cls=sys._getframe(1).f_locals['self'].__class__.__name__

tswarning=False
tsoffset=0
maxts=0

class Message(object):
    p = re.compile(r'(RAW|RWA|NC1): ([^ ]*) (-?[\d.]+) (\d+) (?:N:([+-]?\d+(?:\.\d+)?)([+-]\d+(?:\.\d+)?)|A:(\w+)) [IL]:(\w+) +(\d+)% ([\d.]+|inf|nan) +(\d+) ([\[\]<> 01]+)(.*)')
    parse_error=False
    error=False
    def __init__(self,line):
        self.error_msg=[]
        self.lineno=fileinput.lineno()
        m=self.p.match(line)
        if(args.errorfile != None):
            self.line=line
        if(not m):
            self._new_error("Couldn't parse: "+line)
            self.parse_error=True
            return
        self.swapped = (m.group(1) != "RWA")
        self.next = (m.group(1) == "NC1")
        self.filename=m.group(2)
        if self.filename=="/dev/stdin":
            self.filename="-";
        self.timestamp=float(m.group(3))
        if self.timestamp<0 or self.timestamp>1000*60*60*24*999: # 999d
            self._new_error("Timestamp out of range")
        self.frequency=int(m.group(4))

        if args.channelize:
            self.freq_print=channelize_str(self.frequency)
        else:
            self.freq_print="%010d"%(self.frequency)

        if m.group(5) is not None:
            self.snr=float(m.group(5))
            self.noise=float(m.group(6))
        else:
            self.access_ok=(m.group(7)=="OK")

        self.id=m.group(8)

        self.confidence=int(m.group(9))
        self.level=float(m.group(10))
        if self.level==0:
            self.level=float(m.group(10)+"1")
        self.leveldb=20*log(self.level,10)
#        self.raw_length=m.group(11)
        self.bitstream_raw=(re.sub(r"[\[\]<> ]","",m.group(12))) # raw bitstring with correct symbols
        if self.swapped:
            self.bitstream_raw=symbol_reverse(self.bitstream_raw)
        self.symbols=len(self.bitstream_raw)//2
        if m.group(13):
            self.extra_data=m.group(13)
            self._new_error("There is crap at the end in extra_data")

        # Make a "global" timestamp - needs to be an int to avoid precision loss
        # Current format:
        mm=re.match(r"i-(\d+)-t1$",self.filename)
        if mm:
            startts=int(mm.group(1))
            self.fileinfo="p-%d"%startts
            self.globalns=startts*(10**9)+int(float(self.timestamp)*(10**6))
            return
        # Older file formats:
        mm=re.match(r"(\d\d)-(\d\d)-(20\d\d)T(\d\d)-(\d\d)-(\d\d)-[sr]1",self.filename)
        if mm:
            month, day, year, hour, minute, second = map(int, mm.groups())
            ts=datetime.datetime(year,month,day,hour,minute,second)
            startts=int(ts.timestamp())
            self.fileinfo="p-%d"%startts
            self.globalns=startts*(10**9)+int(float(self.timestamp)*(10**6))
            return
        mm=re.match(r"i-(\d+(?:\.\d+)?)-[vbsrtl]1.([a-z])([a-z])",self.filename)
        if mm:
            self.b26=(ord(mm.group(2))-ord('a'))*26+ ord(mm.group(3))-ord('a')
            startts=float(mm.group(1))+self.b26*600
            if startts != int(startts):
                self.timestamp+=(startts%1)*(10**3)
            startts=int(startts)
            self.fileinfo="p-%d"%startts
            self.globalns=startts*(10**9)+int(float(self.timestamp)*(10**6))
            return
        mm=re.match(r"i-(\d+(?:\.\d+)?)-[vbsrtl]1(?:-o[+-]\d+)?$",self.filename)
        if mm:
            startts=float(mm.group(1))
            if startts != int(startts):
                self.timestamp+=(startts%1)*(10**3)
            startts=int(startts)
            self.fileinfo="p-%d"%startts
            self.globalns=startts*(10**9)+int(float(self.timestamp)*(10**6))
            return

        global tswarning,tsoffset,maxts
        self.fileinfo="u-"+self.filename.replace("-",".")
        if not tswarning:
            print("Warning: no timestamp found in filename", file=sys.stderr)
            tswarning=True
        ts=tsoffset+float(self.timestamp)/1000
        if ts<maxts:
            tsoffset=maxts
            ts=tsoffset+float(self.timestamp)/1000
        maxts=ts
        self.globalns=int(ts*(10**9))

    def upgrade(self):
        if self.error: return self
        if(not self.next and self.bitstream_raw.startswith(iridium_access)):
            self.uplink=0
        elif(not self.next and self.bitstream_raw.startswith(uplink_access)):
            self.uplink=1
        elif(self.bitstream_raw.startswith(next_access_dl)):
            self.uplink = 0
            self.next = True
        elif(self.bitstream_raw.startswith(next_access_ul)):
            self.uplink = 1
            self.next = True
        else:
            if args.uwec and len(self.bitstream_raw)>=len(iridium_access):
                access=de_dqpsk(self.bitstream_raw[:len(iridium_access)])

                if not self.next and bitdiff(access, UW_DOWNLINK) < 4:
                    self.uplink=0
                    self.ec_uw=bitdiff(access,UW_DOWNLINK)
                elif not self.next and bitdiff(access, UW_UPLINK) < 4:
                    self.uplink=1
                    self.ec_uw=bitdiff(access,UW_UPLINK)
                elif self.next and bitdiff(access, NXT_UW_DOWNLINK) < 4:
                    self.uplink = 0
                    self.ec_uw = bitdiff(access, NXT_UW_DOWNLINK)
                elif self.next and bitdiff(access, NXT_UW_UPLINK) < 4:
                    self.uplink = 1
                    self.ec_uw = bitdiff(access, NXT_UW_UPLINK)
                else:
                    self._new_error("Access code distance too big: %d/%d "%(bitdiff(access,UW_DOWNLINK),bitdiff(access,UW_UPLINK)))
            if("uplink" not in self.__dict__):
                self._new_error("Access code missing")
                return self
        try:
            return IridiumMessage(self).upgrade()
        except ParserError as e:
            self._new_error(str(e), e.cls)
            return self
    def _new_error(self,msg, cls=None):
        self.error=True
        if cls is None:
            msg=str(type(self).__name__) + ": "+msg
        else:
            msg=cls + ": "+msg
        if not self.error_msg or self.error_msg[-1] != msg:
            self.error_msg.append(msg)
    def _pretty_header(self):
        flags=""
        if args.uwec or args.harder or not args.perfect:
            flags="-e"
            if("ec_uw" in self.__dict__):
                flags+="%d"%self.ec_uw
            else:
                flags+="0"

            if("ec_lcw" in self.__dict__):
                flags+="%d"%self.ec_lcw
            else:
                flags+="0"

            if("fixederrs" in self.__dict__):
                if self.fixederrs>9:
                    flags+="9"
                else:
                    flags+="%d"%self.fixederrs
            else:
                flags+="0"
        hdr="%s%s %014.4f"%(self.fileinfo,flags,self.timestamp)
        if "snr" not in self.__dict__:
            return "%s %s %3d%% %7.3f"%(hdr,self.freq_print,self.confidence,self.level)
        else:
            return "%s %s %3d%% %06.2f|%07.2f|%05.2f"%(hdr,self.freq_print,self.confidence,self.leveldb,self.noise,self.snr)
    def _pretty_trailer(self):
        return ""
    def pretty(self):
        if self.parse_error:
            return "ERR: "
        if "next" in self.__dict__ and self.next:
            str = "NC1: "
        else:
            str = "RAW: "
        str += self._pretty_header()
        bs=self.bitstream_raw
        if "uplink" in self.__dict__:
            str+= " %03d"%(self.symbols-len(iridium_access)//2)
            if (self.uplink):
                str+=" UL"
            else:
                str+=" DL"
            str+=" <%s>"%bs[:len(iridium_access)]
            bs=bs[len(iridium_access):]
        str+=" "+" ".join(slice(bs,16))
        if("extra_data" in self.__dict__):
            str+=" "+self.extra_data
        str+=self._pretty_trailer()
        return str

class IridiumMessage(Message):
    def __init__(self,msg):
        self.__dict__=msg.__dict__
        if self.next:
            data = self.bitstream_raw[len(next_access_dl):]
            self.msgtype = "NX"
            self.header = self.bitstream_raw[:len(next_access_dl)]
            self.descrambled = data
            return
        elif self.uplink:
            data=self.bitstream_raw[len(uplink_access):]
        else:
            data=self.bitstream_raw[len(iridium_access):]

        # Try to detect packet type.
        # Will not detect packets with correctable bit errors at the beginning
        # unless '--harder' is specifed
        if "msgtype" not in self.__dict__ and (not args.freqclass or self.frequency > f_simplex) and not (args.freqclass and self.uplink):
            if data[:32] == header_messaging:
                self.msgtype="MS"

        if "msgtype" not in self.__dict__ and args.linefilter['type'] == "IridiumMSMessage":
            self._new_error("filtered message")
            return

        if "msgtype" not in self.__dict__ and (not args.freqclass or self.frequency > f_simplex) and not (args.freqclass and self.uplink):
            if data[:96]==header_time_location:
                self.msgtype="TL"

        if "msgtype" not in self.__dict__ and args.linefilter['type'] == "IridiumSTLMessage":
            self._new_error("filtered message")
            return

        if "msgtype" not in self.__dict__ and (not args.freqclass or self.frequency < f_duplex) and not (args.freqclass and self.uplink):
            hdrlen=6
            blocklen=64
            if len(data)>hdrlen+blocklen:
                if ndivide(hdr_poly,data[:hdrlen])==0:
                    (o_bc1,o_bc2)=de_interleave(data[hdrlen:hdrlen+blocklen])
                    if ndivide(ringalert_bch_poly,o_bc1[:31])==0:
                        if ndivide(ringalert_bch_poly,o_bc2[:31])==0:
                            self.msgtype="BC"

        if "msgtype" not in self.__dict__ and args.linefilter['type'] == "IridiumBCMessage":
            self._new_error("filtered message")
            return

        if "msgtype" not in self.__dict__ and (not args.freqclass or self.frequency < f_duplex):
            if len(data)>64: # XXX: heuristic based on LCW / first BCH block, can we do better?
                (o_lcw1,o_lcw2,o_lcw3)=de_interleave_lcw(data[:46])
                if ndivide( 29,o_lcw1)==0:
                    if ndivide( 41,o_lcw3)==0:
                        (e2,lcw2,bch)= bch_repair(465,o_lcw2+'0')  # One bit missing, so we guess
                        if (e2==1): # Maybe the other one...
                            (e2,lcw2,bch)= bch_repair(465,o_lcw2+'1')
                        if e2==0:
                            self.msgtype="LW"

        if "msgtype" not in self.__dict__ and args.linefilter['type'] == "IridiumLCWMessage":
            self._new_error("filtered message")
            return

        if "msgtype" not in self.__dict__ and (not args.freqclass or self.frequency > f_simplex) and not (args.freqclass and self.uplink):
            firstlen=3*32
            if len(data)>=3*32:
                (o_ra1,o_ra2,o_ra3)=de_interleave3(data[:firstlen])
                if ndivide(ringalert_bch_poly,o_ra1[:31])==0:
                    if ndivide(ringalert_bch_poly,o_ra2[:31])==0:
                        if ndivide(ringalert_bch_poly,o_ra3[:31])==0:
                            self.msgtype="RA"

        if "msgtype" not in self.__dict__ and args.linefilter['type'] == "IridiumRAMessage":
            self._new_error("filtered message")
            return

        if "msgtype" not in self.__dict__ and (not args.freqclass or self.frequency < f_duplex) and self.uplink:
            if len(data)>=2*26 and len(data)<2*50:
                self.msgtype="AQ"

        if "msgtype" not in self.__dict__:
            if args.harder:
                # try IBC
                if len(data)>=70 and not (args.freqclass and self.uplink):
                    hdrlen=6
                    blocklen=64
                    (e1,_,_)=bch_repair1(hdr_poly,data[:hdrlen])
                    (o_bc1,o_bc2)=de_interleave(data[hdrlen:hdrlen+blocklen])
                    (e2,d2,b2)=bch_repair(ringalert_bch_poly,o_bc1[:31])
                    (e3,d3,b3)=bch_repair(ringalert_bch_poly,o_bc2[:31])
                    if e1>=0 and e2>=0 and e3>=0:
                        if ((d2+b2+o_bc1[31]).count('1') % 2)==0:
                            if ((d3+b3+o_bc2[31]).count('1') % 2)==0:
                                self.msgtype="BC"
                                self.ec_lcw=e1

                # try for LCW
                if "msgtype" not in self.__dict__ and len(data)>=64:
                    (o_lcw1,o_lcw2,o_lcw3)=de_interleave_lcw(data[:46])
                    (e1 ,lcw1,bch)=bch_repair( 29,o_lcw1)     # BCH(7,3)
                    (e2a,lcw2,bch)=bch_repair(465,o_lcw2+'0') # BCH(13,16)
                    (e2b,lcw2,bch)=bch_repair(465,o_lcw2+'1')
                    (e3 ,lcw3,bch)=bch_repair( 41,o_lcw3)     # BCH(26,21)

                    e2=e2a
                    if (e2b>=0 and e2b<e2a) or (e2a<0):
                        e2=e2b

                    if e1>=0 and e2>=0 and e3>=0:
                        self.msgtype="LW"
                        self.ec_lcw=(e1+e2+e3)

                # try for IRA
                firstlen=3*32
                if "msgtype" not in self.__dict__ and len(data)>=firstlen and not (args.freqclass and self.uplink):
                    (o_ra1,o_ra2,o_ra3)=de_interleave3(data[:firstlen])

                    (e1,d1,b1)=bch_repair(ringalert_bch_poly,o_ra1[:31])
                    (e2,d2,b2)=bch_repair(ringalert_bch_poly,o_ra2[:31])
                    (e3,d3,b3)=bch_repair(ringalert_bch_poly,o_ra3[:31])

                    if e1>=0 and e2>=0 and e3>=0:
                        if ((d1+b1+o_ra1[31]).count('1') % 2)==0:
                            if ((d2+b2+o_ra2[31]).count('1') % 2)==0:
                                if ((d3+b3+o_ra3[31]).count('1') % 2)==0:
                                    self.msgtype="RA"

                # try ITL
                if "msgtype" not in self.__dict__ and len(data)>=96+(8*8*12) and not (args.freqclass and self.uplink):
                    if bitdiff(data[:96],header_time_location)<4:
                        self.ec_lcw=1
                        self.msgtype="TL"

                # try IMS
                if "msgtype" not in self.__dict__ and len(data)>=32 and not (args.freqclass and self.uplink):
                    if bitdiff(data[:32],header_messaging)<2:
                        self.ec_lcw=1
                        self.msgtype="MS"

        if "msgtype" not in self.__dict__:
            if len(data)<64:
                raise ParserError("Iridium message too short")

        if args.forcetype:
            self.msgtype=args.forcetype.partition(':')[0]

        if "msgtype" not in self.__dict__:
            raise ParserError("unknown Iridium message type")

        if self.msgtype=="MS":
            hdrlen=32
            self.header=data[:hdrlen]
            if self.header==header_messaging:
                self.header=""
            self.descrambled=[]
            (blocks,self.descramble_extra)=slice_extra(data[hdrlen:],64)
            for x in blocks:
                self.descrambled+=de_interleave(x)
        elif self.msgtype=="AQ":
            datalen=2*26
            self.header=""
            self.descrambled=data[:datalen]
            self.descramble_extra=data[datalen:]
        elif self.msgtype=="TL":
            hdrlen=96
            self.header=data[:hdrlen]
            self.descrambled=data[hdrlen:hdrlen+(256*3)]
            self.descramble_extra=data[hdrlen+(256*3):]
        elif self.msgtype=="RA":
            firstlen=3*32
            if len(data)<firstlen:
                self._new_error("No data to descramble")
            self.header=""
            self.descrambled=[]
            self.descrambled+=de_interleave3(data[:firstlen])
            (blocks,self.descramble_extra)=slice_extra(data[firstlen:],64)
            for x in blocks:
                self.descrambled+=de_interleave(x)
        elif self.msgtype=="BC":
            hdrlen=6
            self.header=data[:hdrlen]
            (e,d,bch)=bch_repair1(hdr_poly,self.header)

            self.bc_type = int(d, 2)

            if e<0:
                self.header="%s/E%d"%(self.header,e)
                if not args.forcetype:
                    self._new_error("IBC header error")
            else:
                self.header=""

            # Duplex slot packets have a maximum length of 179 symbols
            # but IBC have a 64 sym preamble instead of 16 sym, which reduces
            # their max len to 131 sym.

            ibclen = 131 * 2

            self.descrambled=[]
            (blocks,self.descramble_extra)=slice_extra(data[hdrlen:ibclen],64)
            for x in blocks:
                self.descrambled+=de_interleave(x)
            self.descramble_extra += data[ibclen:]

            # gr-iridium enforces the general 179 sym length, but this means
            # that IBC can have extra symbols at the end.
            # Remove them here.

            if len(self.descrambled) == 8:
                self.symbols -= len(self.descramble_extra)//2
                self.descramble_extra = ""
        elif self.msgtype=="LW":
            lcwlen=46
            (o_lcw1,o_lcw2,o_lcw3)=de_interleave_lcw(data[:lcwlen])
            (e1, self.lcw1,bch)= bch_repair( 29,o_lcw1)
            (e2, self.lcw2,bch)= bch_repair(465,o_lcw2+'0')  # One bit error expected
            (e2b,lcw2b,    bch)= bch_repair(465,o_lcw2+'1')  # Other bit flip?
            (e3,self.lcw3, bch)= bch_repair( 41,o_lcw3)

            if (e2b>=0 and e2b<=e2) or (e2<0):
                e2=e2b
                self.lcw2=lcw2b

            self.ft=int(self.lcw1,2) # Frame type

            if e1<0 or e2<0 or e3<0:
                if not ( args.forcetype and ':' in args.forcetype):
                    self._new_error("LCW decode failed")
                self.header="LCW(%s_%s/%01dE%d,%s_%sx/%03dE%d,%s_%s/%06dE%d)"%(o_lcw1[:3],o_lcw1[3:],int(self.lcw1,2),e1,o_lcw2[:6],o_lcw2[6:],int(self.lcw2,2),e2,o_lcw3[:21],o_lcw3[21:],int(self.lcw3,2),e3)

            data=data[lcwlen:]
            self.descramble_extra=data[312:]
            self.descrambled=data[:312]

        else:
            raise Exception("Illegal Iridium frame type")

    def upgrade(self):
        if self.error: return self
        try:
            if self.msgtype=="LW":
                return IridiumLCWMessage(self).upgrade()
            elif self.msgtype=="TL":
                return IridiumSTLMessage(self).upgrade()
            elif self.msgtype=="AQ":
                return IridiumAQMessage(self).upgrade()
            elif self.msgtype in ("MS", "RA", "BC"):
                return IridiumECCMessage(self).upgrade()
            elif self.msgtype == "NX":
                return IridiumNXTMessage(self).upgrade()
            raise AssertionError("unknown frame type encountered")
        except ParserError as e:
            self._new_error(str(e), e.cls)
            return self
        return self
    def _pretty_header(self):
        str= super()._pretty_header()
        str+= " %03d"%(self.symbols-len(iridium_access)//2)
        if (self.uplink):
            str+=" UL"
        else:
            str+=" DL"
        if self.header:
            str+=" "+self.header
        return str
    def _pretty_trailer(self):
        str= super()._pretty_trailer()
        if("descramble_extra" in self.__dict__) and self.descramble_extra != "":
            str+= " descr_extra:"+self.descramble_extra
        return str
    def pretty(self):
        sstr= "IRI: "+self._pretty_header()
        sstr+= " %2s"%self.msgtype
        if self.msgtype == "TL" and "i" in self.__dict__:
            sstr+= " <"+" ".join(self.i)+">"
            sstr+= " <"+" ".join(self.q)+">"
        elif self.descrambled!="":
            sstr+= " ["
            sstr+=".".join(["%02x"%int("0"+x,2) for x in slice("".join(self.descrambled), 8) ])
            sstr+="]"
        sstr+= self._pretty_trailer()
        return sstr

class IridiumLCWMessage(IridiumMessage):
    def __init__(self,msg):
        self.__dict__=msg.__dict__

        if args.forcetype and ':' in args.forcetype:
            self.ft=int(args.forcetype.partition(':')[2])

        data=self.descrambled
        self.pretty_lcw()

        if self.ft<=3 and len(data)<312:
            self._new_error("Not enough data in data packet")

        self.descrambled=[]
        self.payload_r=[]
        self.payload_f=[]

        if self.ft==0: # Voice - Mission data - voice
            self.msgtype="VO"
            for x in slice(data,8):
                self.descrambled+=[x]
                self.payload_f+=[int(x,2)]
                self.payload_r+=[int(x[::-1],2)]
            self.payload_6=[int(x,2) for x in slice(data[:312], 6)]
        elif self.ft==1: # IP via PPP - Mission data - data
            self.msgtype="IP"
            for x in slice(data,8):
                self.descrambled+=[x[::-1]]
                self.payload_f+=[int(x,2)]
                self.payload_r+=[int(x[::-1],2)]
        elif self.ft==2: # DAta (SBD) - Mission control data - ISU/SV
            self.msgtype="DA"
            blocks=slice(data,124)
            end=blocks.pop()
            for x in blocks:
                (b1,b2)=de_interleave(x)
                (b1,b2,b3,b4)=slice(b1+b2,31)
                self.descrambled+=[b4,b2,b3,b1]
            (b1,b2)=de_interleave(end)
            self.descrambled+=[b2[1:],b1[1:]] # Throw away the extra bit
        elif self.ft==7: # Synchronisation
            self.msgtype="SY"
            self.descrambled=data
            self.sync=[int(x,2) for x in slice(self.descrambled, 8)]
        elif self.ft==3: # Mission control data - inband sig
            self.msgtype="U3"
            self.descrambled=data
            self.payload6=[int(x,2) for x in slice(self.descrambled, 6)]
            self.payload8=[int(x,2) for x in slice(self.descrambled, 8)]
        elif self.ft==6: # "PT=,"
            self.msgtype="U6"
            self.descrambled=data
        else: # Need to check what other ft are
            self.msgtype="U%d"%self.ft
            self.descrambled=data

        if self.msgtype!="VO" and self.msgtype!="IP" and len(self.descrambled)==0:
            self._new_error("No data to descramble")

    def upgrade(self):
        if args.linefilter['type']=='IridiumLCW3Message' and self.msgtype!="U3":
            self._new_error("filtered message")
        if self.error: return self
        try:
            if self.msgtype=="VO":
                return IridiumVOMessage(self).upgrade()
            elif self.msgtype=="IP":
                return IridiumIPMessage(self).upgrade()
            elif self.msgtype=="SY":
                return IridiumSYMessage(self).upgrade()
            elif self.msgtype=="DA":
                return IridiumLCWECCMessage(self).upgrade()
            elif self.msgtype=="U3":
                return IridiumLCW3Message(self).upgrade()
            elif self.msgtype.startswith("U"):
                return self # XXX: probably need to descramble/BCH it
            raise AssertionError("unknown frame type encountered")
        except ParserError as e:
            self._new_error(str(e), e.cls)
            return self
        return self

    def pretty_lcw(self):
# LCW:=xx[type] yyyy[code]
# 0: maint
#    6: geoloc
#    f: "no text"
#    c: maint [lqi[x1c,2], power[[x19,3]]
#    789abde: reserved
#    0: sync [status[xa,1], dtoa[xc,10], dfoa[x16,8]]
#    3: maint [lqi[xa,2], power[xc,3], fine dtoa[xf,7], fine dfoa[x16,3]]
#    245: reserved
#    1: switch [dtoa[xc,10], dfoa[x16,8]]
# 1: acchl
#    1: acchl
#    *: reserved
# 2: handoff
#    c: handoff cand.
#    f: "no text"
#    3: handoff resp. [cand[%c[0=P,1=S::0xb,1]], denied[0xc,1], ref[xd,1], slot[xf,2]+1, subband up[x11,5], subband down[x16,5], access[x1b,3]+1]
#    *: reserved
# 3: reserved
        self.lcw_ft=int(self.lcw2[:2],2)
        self.lcw_code=int(self.lcw2[2:],2)
        lcw3bits=self.lcw3
        if self.lcw_ft == 0:
            ty="maint"
            if self.lcw_code == 6:
                code="geoloc"
            elif self.lcw_code == 15:
                code="<silent>"
            elif self.lcw_code == 12:
                code="maint[1]"
                code+="[lqi:%d,power:%d]"%(int(self.lcw3[19:21],2),int(self.lcw3[16:19],2))
                lcw3bits="%s"%(self.lcw3[:16])
            elif self.lcw_code == 0:
                code="sync"
                code+="[status:%d,dtoa:%d,dfoa:%d]"%(int(self.lcw3[1:2],2),int(self.lcw3[3:13],2),int(self.lcw3[13:21],2))
                lcw3bits="%s|%s"%(self.lcw3[0],self.lcw3[2])
            elif self.lcw_code == 3:
                code="maint[2]"
                code+="[lqi:%d,power:%d,f_dtoa:%d,f_dfoa:%d]"%(int(self.lcw3[1:3],2),int(self.lcw3[3:6],2),int(self.lcw3[6:13],2),int(self.lcw3[13:20],2))
                lcw3bits="%s|%s"%(self.lcw3[0],self.lcw3[20:])
            elif self.lcw_code == 1:
                code="switch"
                code+="[dtoa:%d,dfoa:%d]"%(int(self.lcw3[3:13],2),int(self.lcw3[13:21],2))
                lcw3bits="%s"%(self.lcw3[0:3])
            else:
                code="rsrvd(%d)"%(self.lcw_code)
        elif self.lcw_ft == 1:
            ty="acchl"
            if self.lcw_code == 1:
                code="acchl" # 1(0), 3(msg_type), 1(block_num), 3(sapi_code), 8(segm_list), 5(unused)
                code+="[msg_type:%01x,bloc_num:%01x,sapi_code:%01x,segm_list:%08s]"%(int(self.lcw3[1:4],2),int(self.lcw3[4:5],2),int(self.lcw3[5:8],2),self.lcw3[8:16])
                lcw3bits="%s,%02x"%(self.lcw3[:1],int(self.lcw3[16:],2))
            else:
                code="rsrvd(%d)"%(self.lcw_code)
        elif self.lcw_ft == 2:
            ty="hndof"
            if self.lcw_code == 12:
                code="handoff_cand"
                lcw3bits="%s,%s"%(self.lcw3[:11],self.lcw3[11:])
            elif self.lcw_code == 3:
                code="handoff_resp"
                code+="[cand:%s,denied:%d,ref:%d,slot:%d,sband_up:%d,sband_dn:%d,access:%d]"%(['P','S'][int(self.lcw3[2:3],2)],int(self.lcw3[3:4],2),int(self.lcw3[4:5],2),1+int(self.lcw3[6:8],2),int(self.lcw3[8:13],2),int(self.lcw3[13:18],2),1+int(self.lcw3[18:21],2))
                lcw3bits="%s,%s"%(self.lcw3[0:2],self.lcw3[5:6])
            elif self.lcw_code == 15:
                code="<silent>"
            else:
                code="rsrvd(%d)"%(self.lcw_code)
        elif self.lcw_ft == 3:
            ty="rsrvd"
            code="<%d>"%(self.lcw_code)
        self.header="LCW(%d,T:%s,C:%s,%s)"%(self.ft,ty,code,lcw3bits)
        self.header="%-110s "%self.header

    def pretty(self):
        sstr= "IRI: "+self._pretty_header()
        sstr+= " %2s"%self.msgtype
        if self.descrambled!="":
            sstr+= " ["
            sstr+=".".join(["%02x"%int("0"+x,2) for x in slice("".join(self.descrambled), 8) ])
            sstr+="]"
        sstr+= self._pretty_trailer()
        return sstr

class IridiumSYMessage(IridiumLCWMessage):
    def __init__(self,imsg):
        self.__dict__=imsg.__dict__
    def upgrade(self):
        self.fixederrs=(1+bitdiff(self.descrambled,"10"*(len(self.descrambled)//2)))//2 # count symbols
        if self.uplink:
            fe=(1+bitdiff(self.descrambled,"11"*(len(self.descrambled)//2)))//2 # count symbols
            if fe + 5 < self.fixederrs:
                self.fixederrs=fe
                self.pattern="11"
            else:
                self.pattern="10"
        return self
    def pretty(self):
        str= "ISY: "+self._pretty_header()
        if self.fixederrs==0:
            str+=" Sync=OK"
        else:
            str+=" Sync=no errs=%d"%self.fixederrs
            if len(self.descrambled) < 312:
                str+=" short:%s "%len(self.descrambled)
        if self.uplink:
            str+=" pattern=%s"%self.pattern
        str+=self._pretty_trailer()
        return str

iaq_crc16=crcmod.mkCrcFun(poly=0x15101,initCrc=0,rev=False,xorOut=0)
class IridiumAQMessage(IridiumMessage):
    def __init__(self,imsg):
        self.__dict__=imsg.__dict__
        self.fixederrs=0

        self.sym=[]
        imap=['0','e','e','1']
        bits=self.descrambled
        for x in range(0,len(bits)-1,2):
            self.sym.append(imap[int(bits[x+0])*2 + int(bits[x+1])])

        if 'e' in self.sym:
            raise ParserError("IAQ content not BPSK")

        self.rid=int(self.sym[4]+self.sym[6]+self.sym[8]+self.sym[10]+self.sym[5]+self.sym[7]+self.sym[9]+self.sym[11],2)
        self.val=bytes([int("".join(self.sym[:4]),2),int("".join(self.sym[4:12]),2)])
        self.ridcrc=int("".join(self.sym[12:]),2)

        self.crcval=iaq_crc16( bytes(self.val)) >>2

    def upgrade(self):
        return self
    def pretty(self):
        st= "IAQ: "+self._pretty_header()

        st+= " " + "".join(self.sym[0:4])
        st+= " " + "Rid:%03d"%self.rid
        if self.ridcrc==self.crcval:
            st+= " " + "CRC:OK"
        else:
            st+= " " + "CRC:no[%04x]"%self.ridcrc


        st+=self._pretty_trailer()
        return st


class IridiumSTLMessage(IridiumMessage):
    def __init__(self,imsg):
        self.__dict__=imsg.__dict__
        if not args.forcetype:
            self.header="<11>"
        else:
            self.header="<"+self.header+">"
        self.fixederrs=0
        if len(self.descrambled) < 8*8*12: # 12 blocks of 8 bytes
            raise ParserError("ITL content too short")

        symbols=de_dqpsk(self.descrambled)

        (i_list,q_list)=split_qpsk(symbols)

        i_list=["%02x"%int(x,2) for x in slice(i_list,8)]
        q_list=["%02x"%int(x,2) for x in slice(q_list,8)]

        self.i=["".join(x) for x in (i_list[:16],i_list[16:])]
        self.q=["".join(x) for x in slice(q_list,12)]

        if args.harder:
            MAX_DIFF=10
            self.ib=[bin(int(x, 16))[2:].zfill(len(x*4)) for x in self.i]

        # Try to determine ITL version
        self.itl_version= None
        try:
            self.itl_version= itl.PRS_HDR.index(self.i[0])
        except ValueError:
            if args.harder: # harder only supports V2
                if bitdiff(self.ib[0],itl.BIN_HDR[2])<MAX_DIFF:
                    self.fixederrs+= 1
                    self.itl_version= 2
                else:
                    raise ParserError("ITL PRS I#0 (version) unknown")
            else:
                raise ParserError("ITL PRS I#0 (version) unknown")

        self.header="V%d"%self.itl_version

        if self.itl_version==0: # No decoding yet
            self.i= ["".join(x) for x in slice(i_list,16)]
            self.q= ["".join(x) for x in slice(q_list,16)]
            return
        elif self.itl_version==1:
            try:
                self.plane= itl.MAP_PLANE_V1[self.i[1]]
            except KeyError:
                raise ParserError("ITL V1 PRS I#1 (plane) unknown")

            self.msg=[]
            for i,x in enumerate(self.q):
                if x in itl.MAP_PRS_V1:
                    self.msg.append(itl.MAP_PRS_V1[x])
                else:
                    if i==0 or self.msg[0]<77: # M8 does not contain normal PRS'
                        raise ParserError("ITL V1 PRS Q#%d unknown"%i)
                    self.msg.append(x)
        elif self.itl_version==2 and not args.harder:
            try:
                self.plane= itl.MAP_PLANE[self.i[1]]
            except KeyError:
                raise ParserError("ITL V2 PRS I#1 (plane) unknown")

            self.msg=[]
            for i,x in enumerate(self.q):
                if x in itl.MAP_PRS:
                    self.msg.append(itl.MAP_PRS[x])
                else:
                    if i==0 or self.msg[0] != 108: # special message does not contain normal PRS
                        raise ParserError("ITL V2 PRS Q#%d unknown"%i)
                    self.msg.append(x)

            if self.msg[0] != 108:
                #sanity check the PRS sequence order
                sanity = "".join([str(itl.MAP_PRS_TYPE[x]) for x in self.q])
                if self.plane%2 == 0:
                    if sanity not in ("0123","1032"):
                        raise ParserError("ITL V2 PRS from unexpected set")
                else:
                    if sanity not in ("2301","3210"):
                        raise ParserError("ITL V2 PRS from unexpected set")

        elif self.itl_version==2 and args.harder:
            self.plane=None
            self.msg=[None]*4

            if self.i[1] in itl.MAP_PLANE:
                self.plane= itl.MAP_PLANE[self.i[1]]
            else:
                for i,p in enumerate(itl.BIN_PLANES):
                    if bitdiff(self.ib[1],p)<MAX_DIFF*2:
                        self.plane=i+1
                        self.fixederrs+=1
                        break
                if self.plane is None:
                    raise ParserError("ITL V2 PRS I#1 (plane) unknown")

            cat=None
            for qidx in range(len(self.q)):
                mindist=999
                if qidx > 0 and self.msg[0] == 108:
                    self.msg[qidx]=self.q[qidx]
                    next
                if self.q[qidx] in itl.MAP_PRS:
                    self.msg[qidx]= itl.MAP_PRS[self.q[qidx]]
                    cat=itl.MAP_PRS_TYPE[self.q[qidx]]
                else:
                    q=bin(int(self.q[qidx], 16))[2:].zfill(len(self.q[qidx]*4))
                    if qidx==0: # Only search in correct PRS subset
                        if self.plane%2==0:
                            s=0
                            e=256
                        else:
                            s=256
                            e=512
                    elif qidx==1 or qidx==3:
                        cat^=1
                        s=128*cat
                        e=128*(cat+1)
                    elif qidx==2:
                        cat^=3
                        s=128*cat
                        e=128*(cat+1)
                    else:
                        raise AssertionError("ITL category error")
                    for i,prs in enumerate(itl.BIN_PRS[s:e]):
                        dist=bitdiff(q,prs)
                        if dist<mindist: mindist=dist
                        if dist<MAX_DIFF:
                            self.msg[qidx]=i%128
                            if cat is None:
                                cat=(i+s)//128
                            self.fixederrs+=1
                            break
                if self.msg[qidx] is None:
                    self._new_error("ITL V2 PRS Q#%d unknown"%qidx)
                    raise ParserError("ITL PRS dist=%d"%mindist)
        else:
            raise AssertionError("ITL version error")

        try:
            (self.sat, self.mt)= itl.map_sat(self.msg[0], self.itl_version)
        except ValueError:
            raise ParserError("ITL invalid sat ID")
        self.msg=self.msg[1:]

    def upgrade(self):
        return self
    def pretty(self):
        st= "ITL: "+self._pretty_header()

        if self.itl_version==0:
            st+= " -"
            st+= " <"+" ".join(self.i)+">"
            st+= " <"+" ".join(self.q)+">"
        elif self.itl_version==1:
            st+= " OK P%d"%self.plane
            st+= " "+self.sat+" "+self.mt
            for x in self.msg:
                try:
                    st+= " "+"{0:07b}".format(x)
                except ValueError:
                    st+= " "+x
        else:
            st+=" OK P%d"%self.plane
            st+=" "+self.sat+" "+self.mt
            for x in self.msg:
                try:
                    st+= " "+"{0:07b}".format(x)
                except ValueError:
                    st+= " "+x

        st+=self._pretty_trailer()
        return st

class IridiumLCW3Message(IridiumLCWMessage):
    def __init__(self,imsg):
        self.__dict__=imsg.__dict__

        self.utype="IU3"
        self.rs8p=False
        self.rs6p=False
        self.fixederrs=0

        (ok,msg,csum)=rs.rs_fix(self.payload8)
        self.rs8=ok
        if ok:
            self.utype="I38"
            if bytearray(self.payload8)==msg+csum:
                self.rs8p=True
            else:
                self.fixederrs+=1
            self.rs8m=msg
            self.rs8c=csum
            self.csum=checksum_16(self.rs8m)
        else:
            (ok,msg,csum)=rs6.rs_fix(self.payload6)
            self.rs6=ok
            if ok:
                self.utype="I36"
                if bytearray(self.payload6)==msg+csum:
                    self.rs6p=True
                else:
                    self.fixederrs+=1
                self.rs6m=msg
                self.rs6c=csum

    def upgrade(self):
        return self
    def pretty(self):
        str= self.utype+": "+self._pretty_header()
        if self.utype=='I38':
            if self.rs8p:
                str+=" RS8=OK"
            else:
                str+=" RS8=ok"
            if self.csum==0:
                str+=" CS=OK"
                self.rs8m=self.rs8m[0:-3]
                remove_zeros(self.rs8m)
            else:
                str+=" CS=no"
            str+= " ["
            str+=" ".join(["%02x"%(x) for x in self.rs8m ])
            str+= "]"
        elif self.utype=='I36':
            if self.rs6p:
                str+=" RS6=OK"
            else:
                str+=" RS6=ok"
            str+=" {%02d}"%self.rs6m[0]
            str+= " ["

            num=None
            v="".join(["{0:06b}".format(x) for x in self.rs6m[1:] ])
            if self.rs6m[0]==0:
                str+=v[:2]+"| "+group(v[2:],10)
            elif self.rs6m[0]==6:
                str+=v[:2]+"| "+group(v[2:],24)
                num=[int(x,2) for x in slice(v[2:],24)]
                remove_zeros(num)
            elif self.rs6m[0]==32 or self.rs6m[0]==34:
                str+=v[:2]+"| "+group(v[2:],24)
                num=[int(x,2) for x in slice(v[2:-4],24)]
                if int(v[-4:],2)!=0:
                    num+=[int(v[-4:],2)]
                while len(num)>0 and num[-1]==0x7ffff:
                    num=num[:-1]
            else:
                str+=group(v,6)
            str+="]"

            if num is not None:
                str+=" <"+" ".join(["%06x"%x for x in num])+">"
        else:
            str+=" RS=no"
            str+= " ["
            str+=group(self.descrambled,8)
            str+="]"
        str+=self._pretty_trailer()
        return str

class IridiumVOMessage(IridiumLCWMessage):
    def __init__(self,imsg):
        self.__dict__=imsg.__dict__

        # Test if CRC24 is ok -> VDA
        self.crcval=iip_crc24( bytes(self.payload_r))
        if self.crcval==0:
            self.vtype="VDA"
            return

        # Test if rs6 accepts it -> VO6 (unknown)
        (ok,msg,csum)=rs6.rs_fix(self.payload_6)
        self.rs6p=False
        self.rs6=ok
        if ok:
            self.vtype="VO6"
            if bytearray(self.payload_6)==msg+csum:
                self.rs6p=True
            self.rs6m=msg
            self.rs6c=csum
            return

        # Test if rs accepts it -> VOD
        (ok,msg,rsc)=rs.rs_fix(self.payload_f)
        if ok:
            self.vtype="VOD"
            self.vdata=msg
            return

        # the check for zeros is a heuristic to minimize false matches
        # If sum mod 256 is 0 -> VOZ
        if all([x==0 for x in self.payload_f[-4:-1]]):
            vsum=sum(self.payload_f) % 0x100
            if vsum == 0:
                self.vtype="VOZ"
                for i in range(len(self.payload_f) - 2, -1, -1):
                    if self.payload_f[i] != 0:
                        break
                self.vdata=self.payload_f[:i+1]
                return

        # We can't sanity check the AMBE codec, so accept the remaining packets
        self.vtype="VOC"
        self.vdata=self.payload_f

    def upgrade(self):
        if self.vtype=="VDA":
            new= IridiumIPMessage(self).upgrade()
            new.itype="VDA"
            return new
        return self
    def pretty(self):
        str= self.vtype+": "+self._pretty_header()
        if self.vtype=="VDA":
            raise AssertionError("VDA handled in IIP")
        elif self.vtype=="VO6":
            v="".join(["{0:06b}".format(x) for x in self.rs6m ])
            if self.rs6p:
                str+=" RS=OK"
            else:
                str+=" RS=ok"
            str+=" "+group(v,6)
        else:
            str+= " ["+".".join(["%02x"%x for x in self.vdata])+"]"
        str+=self._pretty_trailer()
        return str

# Poly from GSM 04.64 / check value (reversed) is 0xC91B6
iip_crc24=crcmod.mkCrcFun(poly=0x1BBA1B5,initCrc=0xffffff^0x0c91b6,rev=True,xorOut=0x0c91b6)
class IridiumIPMessage(IridiumLCWMessage):
    def __init__(self,imsg):
        self.__dict__=imsg.__dict__

        self.crcval=iip_crc24( bytes(self.payload_r))
        if self.crcval==0:
            self.itype="IIP"
            self.ip_hdr=self.payload_r[0]
                        #  106099 01: ACK / IDLE
                        #  458499 04: Data
                        #    2476 0b:
                        #     504 0f:
                        #     173 14:
                        #    1477 11:
            self.ip_seq=self.payload_r[1]
            self.ip_ack=self.payload_r[2]
            self.ip_cs= self.payload_r[3]
            self.ip_cs_ok=self.ip_hdr+self.ip_seq+self.ip_ack+self.ip_cs
            while (self.ip_cs_ok>255):
                self.ip_cs_ok-=255
            self.ip_data=self.payload_r[4:31+5]
            self.ip_cksum, = struct.unpack(">L", bytearray([0]+self.payload_r[31+5:]))
        else:
            (ok,msg,rsc)=rs.rs_fix(self.payload_f)
            if ok:
                if bytearray(self.payload_f)!=msg+rsc:
                    self.fixederrs=1
                self.iiqcsum=checksum_16(msg)

                if self.iiqcsum == 0:
                    self.itype="IIR"
                    self.idata=msg[0:-2]
                else:
                    self.itype="IIQ"
                    val=struct.unpack("<H",msg[:2])[0]
                    self.flags=val&7
                    self.counter=val>>3
                    self.idata=msg[2:]
            else:
                self.itype="IIU"
    def upgrade(self):
        return self
    def pretty(self):
        s= self.itype+": "+self._pretty_header()
        if self.itype=="IIP" or self.itype=="VDA":
            s+= " type:%02x seq=%03d ack=%03d cs=%03d/%s "%(self.ip_hdr,self.ip_seq,self.ip_ack,self.ip_cs,["no","OK"][(self.ip_cs_ok==255)])
            if self.ip_hdr==4: # DATA
                self.ip_len=self.ip_data[0]
                self.ip_data=self.ip_data[1:]
                s+= " len=%03d"%(self.ip_len)
                if all([x==0 for x in self.ip_data[self.ip_len+1:]]):
                    data=self.ip_data[:self.ip_len]
                    mstr= " ["+myhex(data,".")+"]"
                else: # rest is not zero as it should be
                    data=self.ip_data
                    mstr= " ["+myhex(data,".")+"]"
                    if self.ip_len>0 and self.ip_len<31:
                        mstr=mstr[:3*self.ip_len-1]+'!'+mstr[3*self.ip_len:]
                s+= "%-95s"%(mstr)
            elif self.ip_hdr==1: # ACK?
                s+= "      "
                data=self.ip_data
                while data and data[-1] == 0:
                    data.pop()
                s+= "%-97s"%(myhex(data,"."))
            else: # UNKNOWN
                s+= "      "
                data=self.ip_data
                s+= "["+myhex(data,".")+"]"

            s+= " FCS:OK/%06x"%(self.ip_cksum)
            if len(data)>0 and self.ip_hdr!=1:
                ip_data = ' IP: '
                ip_data += to_ascii(data, dot=True)
                s += ip_data
        elif self.itype=="IIQ":
            s+= " f:%d c:%04x"%(self.flags,self.counter)
            s+= " ["+myhex(self.idata," ")+"]"
            ip_data = ' IP: '
            ip_data += to_ascii(self.idata, dot=True)
            s += ip_data
        elif self.itype=="IIR":
            s+= " ["+myhex(self.idata," ")+"]"
        else:
            s+= " ["+" ".join(["%s"%x for x in self.descrambled])+"]"

        s+=self._pretty_trailer()
        return s

class IridiumECCMessage(IridiumMessage):
    def __init__(self,imsg):
        self.__dict__=imsg.__dict__
        if self.msgtype == "MS":
            self.poly=messaging_bch_poly
        elif self.msgtype == "RA":
            self.poly=ringalert_bch_poly
        elif self.msgtype == "BC":
            self.poly=ringalert_bch_poly
        else:
            raise AssertionError("unknown Iridium message type")

        self.bitstream_bch=""
        self.fixederrs=0
        self.fill=0
        self.ecc_cut=False
        self.bch_blk=len(self.descrambled)
        parity=None

        if self.bch_blk==0:
            raise ParserError("No data to ECC")

        if self.msgtype in ('MS','RA'):
            # remove optional FILL pattern
            while True:
                (first,second)=self.descrambled[-2:]
                if (first+second == "1010001001110011101111110110110101010100010001011100001011100110") or \
                        (bitdiff(first, "10100010011100111011111101101101") <=2 and
                         bitdiff(second,"01010100010001011100001011100110") <=2):
                    # XXX: do it properly with BCH(ringalert_bch_poly)?
                    self.fill+=1
                    self.descrambled.pop()
                    self.descrambled.pop()
                else:
                    break

            if self.fill>0: self.descramble_extra=""

        for block in self.descrambled:
            assert len(block)==32, "unknown BCH block len:%d"%len(block)

            parity=block[31:]
            block=block[:31]

            (errs,data,bch)=bch_repair(self.poly, block)

            if errs<0: # cut packet on uncorrectable error
                self.ecc_cut=True
                self.fill=0
                self.descramble_extra=""
                break

            if ((data+bch+parity).count('1') % 2)==1:
                if args.harder:
                    errs+=1
                else:
                    if errs>0:
                        self._new_error("Parity error")
                        self.ecc_cut=True
                        self.fill=0
                        self.descramble_extra=""
                        break

            if errs>0:
                self.fixederrs+=1

            self.bitstream_bch+=data # TBD: keep blocks?

        if len(self.bitstream_bch) == 0:
            self._new_error("BCH decode failed")

    def upgrade(self):
        if self.error: return self
        try:
            if self.msgtype == "MS":
                return IridiumMSMessage(self).upgrade()
            elif self.msgtype == "RA":
                return IridiumRAMessage(self).upgrade()
            elif self.msgtype == "BC":
                return IridiumBCMessage(self).upgrade()
            else:
                raise AssertionError("unknown Iridium message type")
        except ParserError as e:
            self._new_error(str(e), e.cls)
            return self
        return self
    def pretty(self):
        str= "IME: "+self._pretty_header()+" "+self.msgtype+" "
        for block in range(len(self.descrambled)):
            b=self.descrambled[block]
            (errs,foo)=nrepair(self.poly,b[:31])
            res=ndivide(self.poly,b[:31])
            parity=(foo+b[31]).count('1') % 2
            str+="{%s %s %s/%04d E%s P%d}"%(b[:21],b[21:31],b[31],res,("0","1","2","-")[errs],parity)
        if self.fill>0:
            str+=" FILL=%02d"%self.fill
        str+=self._pretty_trailer()
        return str

class IridiumLCWECCMessage(IridiumMessage):
    def __init__(self,imsg):
        self.__dict__=imsg.__dict__
        if self.msgtype == "DA":
            self.poly=acch_bch_poly
        else:
            raise AssertionError("unknown Iridium message type")

        self.bitstream_bch=""
        self.fixederrs=0

        for block in self.descrambled:
            assert len(block)==31, "unknown BCH block len:%d"%len(block)

            (errs,data,bch)=bch_repair(self.poly, block)

            if errs<0:
                self.descramble_extra=""
                break

            if errs>0:
                self.fixederrs+=1

            self.bitstream_bch+=data

        if len(self.bitstream_bch)==0:
            self._new_error("BCH decode failed")

    def upgrade(self):
        if self.error: return self
        try:
            if self.msgtype == "DA":
                return IridiumDAMessage(self).upgrade()
            else:
                raise AssertionError("unknown Iridium message type")
        except ParserError as e:
            self._new_error(str(e), e.cls)
            return self
        return self
    def pretty(self):
        str= "IME: "+self._pretty_header()+" "+self.msgtype+" "
        for block in range(len(self.descrambled)):
            b=self.descrambled[block]
            (errs,foo)=nrepair(self.poly,b)
            res=ndivide(self.poly,b)
            parity=(foo).count('1') % 2
            str+="{%s %s/%04d E%s P%d}"%(b[:21],b[21:31],res,("0","1","2","-")[errs],parity)
        str+=self._pretty_trailer()
        return str #

ida_crc16=crcmod.predefined.mkPredefinedCrcFun("crc-ccitt-false")
class IridiumDAMessage(IridiumLCWECCMessage):
    def __init__(self,imsg):
        self.__dict__=imsg.__dict__
        # Decode stuff from self.bitstream_bch
        self.flags1=self.bitstream_bch[:4]
        self.flag1b=self.bitstream_bch[4:5]
        self.da_ctr=int(self.bitstream_bch[5:8],2)
        self.flags2=self.bitstream_bch[8:11]
        self.da_len=int(self.bitstream_bch[11:16],2)
        self.flags3=int(self.bitstream_bch[16:17],2)
        self.zero1=int(self.bitstream_bch[17:20],2)
        if self.zero1 != 0:
            self._new_error("zero1 not 0")

        if len(self.bitstream_bch) < 9*20+16:
            raise ParserError("Not enough data in data packet")

        if self.da_len>0:
            self.da_crc=int(self.bitstream_bch[9*20:9*20+16],2)
            self.da_ta=[int(x,2) for x in slice(self.bitstream_bch[20:9*20],8)]
            crcstream=self.bitstream_bch[:20]+"0"*12+self.bitstream_bch[20:-4]
#            the_crc=ida_crc16("".join([chr(int(x,2)) for x in slice(crcstream,8)]))
            the_crc=ida_crc16(bytes([int(x,2) for x in slice(crcstream,8)]))
            self.the_crc=the_crc
            self.crc_ok=(the_crc==0)
        else:
            self.crc_ok=False
            self.da_ta=[int(x,2) for x in slice(self.bitstream_bch[20:11*20],8)]

        self.zero2=int(self.bitstream_bch[9*20+16:],2)
        if self.zero2 != 0:
            self._new_error("zero2 not 0")

        sbd= self.bitstream_bch[1*20:9*20]
        self.data=[]
        for x in slice(sbd, 8):
            self.data+=[int(x,2)]

    def upgrade(self):
        if self.error: return self
        try:
            return self
        except ParserError as e:
            self._new_error(str(e), e.cls)
            return self
        return self
    def pretty(self):
        str= "IDA: "+self._pretty_header()
        str+= " "+self.bitstream_bch[:3]
        str+= " cont="+self.bitstream_bch[3:4]
        str+= " "+self.bitstream_bch[4:5]
        str+= " ctr="+self.bitstream_bch[5:8]
        str+= " "+self.bitstream_bch[8:11]
        str+= " len=%02d"%self.da_len
        str+= " 0:"+self.bitstream_bch[16:20]
        str+=" ["
        if self.da_len>0:
            if all([x==0 for x in self.da_ta[self.da_len+1:]]):
                mstr= ".".join(["%02x"%x for x in self.da_ta[:self.da_len]])
            else: # rest is not zero as it should be
                mstr= ".".join(["%02x"%x for x in self.da_ta])
                if self.da_len>0 and self.da_len<20:
                    mstr=mstr[:3*self.da_len-1]+'!'+mstr[3*self.da_len:]
        else:
            mstr= ".".join(["%02x"%x for x in self.da_ta])
        str+= "%-60s"%(mstr+"]")

        if self.da_len>0:
            str+= " %04x"%int(self.bitstream_bch[9*20:9*20+16],2)
            str+="/%04x"%self.the_crc
            if self.crc_ok:
                str+=" CRC:OK"
            else:
                str+=" CRC:no"
            str+= " "+self.bitstream_bch[9*20+16:]
        else:
            str+="  ---   "
            str+= " "+self.bitstream_bch[9*20+16:]

        if self.da_len>0:
            sbd= self.bitstream_bch[1*20:9*20]

            str+=' SBD: '
            for x in slice(sbd, 8):
                c=int(x,2)
                if( c>=32 and c<127):
                    str+=chr(c)
                else:
                    str+="."

        str+=self._pretty_trailer()
        return str

class IridiumBCMessage(IridiumECCMessage):
    def __init__(self,imsg):
        self.__dict__=imsg.__dict__
        blocks, _ =slice_extra(self.bitstream_bch,42)

        if len(blocks)>4: # IBC is exactly 4 "blocks" long
            blocks=blocks[:4]
            self.trailer='{LONG}'
        elif len(blocks)<4:
            self.trailer='{SHORT}'

        self.descramble_extra=""

        if blocks and self.bc_type == 0:
            data = blocks.pop(0)

            self.sv_id =         int(data[ 0: 7], 2)
            self.beam_id =       int(data[ 7:13], 2)
            self.unknown01 =         data[13:14]
            self.slot =          int(data[14:15], 2) # previously: timeslot
            self.sv_blocking =   int(data[15:16], 2) # aka: Acq
            self.acqu_classes =      data[16:32]
            self.acqu_subband =  int(data[32:37], 2)
            self.acqu_channels = int(data[37:40], 2)
            self.unknown02 =         data[40:42]

        if blocks and self.bc_type == 0:
            data = blocks.pop(0)

            self.type = int(data[0:6], 2)
            if self.type == 0:
                self.unknown11 = data[6:36]
                self.max_uplink_pwr = int(data[36:42], 2)
            elif self.type == 1:
                self.unknown21 = data[6:10]
                self.iri_time = int(data[10:42], 2) # a.k.a. LBFC (L-Band Frame Counter)
                (self.iri_time_ux, self.iri_time_str)= fmt_iritime(self.iri_time)
            elif self.type == 2:
                self.unknown31 = data[6:10]
                self.tmsi_expiry = int(data[10:42], 2)
                (self.tmsi_expiry_ux, self.tmsi_expiry_str)= fmt_iritime(self.tmsi_expiry)
            else: # Unknown Type
                self.type_data=data

        self.assignments=[]
        for data in blocks: # Parse assignments (if any)
            assignment={
                'type':      int(data[ 0: 3], 2),
            }
            if assignment['type'] == 0: # "classic" assignment
                assignment = {
                    **assignment,
                    'random_id':   int(data[ 3:11], 2),
                    'timeslot':  1+int(data[11:13], 2),
                    'ul_sb':       int(data[13:18], 2), # uplink_subband
                    'dl_sb':       int(data[18:23], 2), # downlink_subband
                    'access':    1+int(data[23:26], 2),
                    'dtoa':        int(data[26:34], 2),
                    'dfoa':        int(data[34:40], 2),
                    'unknown4':        data[40:42],
                }
                if assignment['dtoa'] > 128:
                    assignment['dtoa']=assignment['dtoa']-256
            elif data == '111000000000000000000000000000000000000000':
                assignment['empty']=True
            else:
                assignment = {
                    **assignment,
                    'unknown': data[3:42],
                }
            self.assignments.append(assignment)

    def upgrade(self):
        if self.error: return self
        try:
            return self
        except ParserError as e:
            self._new_error(str(e), e.cls)
            return self
        return self
    def _pretty_trailer(self):
        tmp= ""
        if "trailer" in self.__dict__:
            tmp+=" "+self.trailer
        tmp+= super()._pretty_trailer()
        return tmp
    def pretty(self):
        str= "IBC: "+self._pretty_header()
        str+= " bc:%d" % self.bc_type
        if self.bc_type == 0:
            str+= ' sat:%03d cell:%02d %s slot:%d sv_blkn:%d aq_cl:%s aq_sb:%02d aq_ch:%d %s' % (self.sv_id, self.beam_id, self.unknown01, self.slot, self.sv_blocking, self.acqu_classes, self.acqu_subband, self.acqu_channels, self.unknown02)
            if "type" in self.__dict__:
                if self.type == 0:
                    str += ' %s max_uplink_pwr:%02d' % (self.unknown11, self.max_uplink_pwr)
                elif self.type == 1:
                    str += ' %s time:%s' % (self.unknown21, self.iri_time_str)
                elif self.type == 2:
                    str += ' %s tmsi_expiry:%s' % (self.unknown31, self.tmsi_expiry_str)
                elif self.type == 4: # Not seen currently
                    str += ' st:%02d '%self.type
                    if self.type_data == "000100000000100001110000110000110011110000":
                        str += 'DFLT'
                    else:
                        str += self.type_data
                else: # Unknown Type
#                    raise ParserError("unknown BC subtype %s"%self.type)
                    str += ' st:%02d '%self.type
                    str += self.type_data

        str="%-214s"%str
        for a in self.assignments:
            if 'empty' in a:
                str += ' []'
            elif a['type'] == 0:
                str += ' [%d Rid:%03d ts:%d ul_sb:%02d dl_sb:%02d access:%d dtoa:%+04d dfoa:%02d %s]' % (a['type'], a['random_id'], a['timeslot'], a['ul_sb'], a['dl_sb'], a['access'], a['dtoa'], a['dfoa'], a['unknown4'])
            else:
                str += ' [%s %s]                     ' % (a['type'], a['unknown'])

        str+=self._pretty_trailer()
        return str

class IridiumRAMessage(IridiumECCMessage):
    def __init__(self,imsg):
        self.__dict__=imsg.__dict__
        # Decode stuff from self.bitstream_bch
        # 3 blocks (63 bits) fixed "header".
        if len(self.bitstream_bch)<63:
            raise ParserError("RA content too short")
        self.ra_sat=   int(self.bitstream_bch[0:7],2)   # sv_id
        self.ra_cell=  int(self.bitstream_bch[7:13],2)  # beam_id
        self.ra_pos_x= int(self.bitstream_bch[14:25],2) - int(self.bitstream_bch[13])*(1<<11)
        self.ra_pos_y= int(self.bitstream_bch[26:37],2) - int(self.bitstream_bch[25])*(1<<11)
        self.ra_pos_z= int(self.bitstream_bch[38:49],2) - int(self.bitstream_bch[37])*(1<<11)
        self.ra_int=   int(self.bitstream_bch[49:56],2) # 90ms interval of RA (within same sat/cell)
        self.ra_ts=    int(self.bitstream_bch[56:57],2) # Broadcast slot 1 or 4
        self.ra_eip=   int(self.bitstream_bch[57:58],2) # EPI ?
        self.ra_bc_sb= int(self.bitstream_bch[58:63],2) # BCH downlink sub-band

        # this calculates geocentric latitude (=arcsin(z/r)) instead of geodetic latitude:
        self.ra_lat = atan2(self.ra_pos_z,sqrt(self.ra_pos_x**2+self.ra_pos_y**2))*180/pi
        # this value is too small by up to 0.2°
        # https://www.wolframalpha.com/input/?i=max[phi-atan((1-0.081819190842622**2)*tan(phi*pi/180))*180/pi,0<phi<90]
        self.ra_lon = atan2(self.ra_pos_y,self.ra_pos_x)*180/pi
        self.ra_alt = sqrt(self.ra_pos_x**2+self.ra_pos_y**2+self.ra_pos_z**2)*4

        ra_msg=self.bitstream_bch[63:]

        # Up to 12 PAGEs(@ 42 bits each) for max 432 symbol frame
        # PAGEs end with an all-1 page.
        # Frame may be longer, in that case it is padded with "FILL" pattern
        # which should have be removed by the ECC layer
        # but some may be left in case of bit errors

        self.paging=[]
        self.page_cnt=len(ra_msg)//42

        if self.page_cnt==0:
            self.trailer="{TRUNCATED}"
            return

        if len(ra_msg)%42>0:
            self.page_cnt+=1

        blocks, _ = slice_extra(ra_msg,42)
        for page in blocks:
            paging={
                'tmsi':  int(page[ 0:32],2),
                'zero1': int(page[32:34],2),
                'msc_id':int(page[34:39],2),
                'zero2': int(page[39:42],2),
            }

            paging['str'] = "tmsi:%08x"%paging['tmsi']
            if paging['zero1']!=0: paging['str']+= " 0:%d"%paging['zero1']
            paging['str']+= " msc_id:%02d"%paging['msc_id']
            if paging['zero2']!=0: paging['str']+= " 0:%d"%paging['zero2']

            self.paging.append(paging)

            if page=="1"*42:
                paging['str']="END"
                break

        if self.paging[-1]['str']=="END":
            if len(self.paging)<self.page_cnt: # Bits left at the end
                self.ra_extra=ra_msg[42*(len(self.paging)):]
                if self.ra_extra.startswith("101000100111001110111"):
                    del(self.ra_extra)
                    self.trailer="{OK:UNCLEAN}"
                else:
                    self.trailer="{EXTRA_BITS}"
            else:
                if self.descramble_extra.startswith("011010110"):
                    self.descramble_extra=""
                self.trailer="{OK}"
            self.paging.pop()
        elif len(self.paging)<12:
            self.trailer="{TRUNCATED}"
        else:
            self.trailer="{OK}"

    def upgrade(self):
        if self.error: return self
        try:
            return self
        except ParserError as e:
            self._new_error(str(e), e.cls)
            return self
        return self

    def pretty(self):
        str= "IRA: "+self._pretty_header()
        str+= " sat:%03d"%self.ra_sat
        str+= " beam:%02d"%self.ra_cell
        str+= " xyz=(%+05d,%+05d,%+05d)"%(self.ra_pos_x,self.ra_pos_y,self.ra_pos_z)
        str+= " pos=(%+06.2f/%+07.2f)"%(self.ra_lat,self.ra_lon)
        str+= " alt=%03d"%(self.ra_alt-6378+23) # Maybe try WGS84 geoid? :-)
        str+= " RAI:%02d"%self.ra_int
        str+= " ?%d%d"%(self.ra_ts,self.ra_eip)
        str+= " bc_sb:%02d"%self.ra_bc_sb

        str+=" P%02d:"%len(self.paging)
        for p in self.paging:
            str+= " PAGE(%s)"%p['str']

        if "trailer" in self.__dict__:
            str+=" "+self.trailer
        if self.fill>0:
            str+=" FILL=%d"%self.fill
        if "ra_extra" in self.__dict__:
            str+= " +" + " ".join(slice(self.ra_extra,42))

        str+=self._pretty_trailer()
        return str

class IridiumMSMessage(IridiumECCMessage):
    def __init__(self,imsg):
        # Ref: US5596315
        self.__dict__=imsg.__dict__
        blocks= slice(self.bitstream_bch,21)

        self.ms_type=    int(blocks[0][0],     2) # 1 if Acq group
        self.zero1 =         blocks[0][ 1: 5]
        self.block =     int(blocks[0][ 5: 9], 2) # Block number in the super frame
        self.frame =     int(blocks[0][ 9:15], 2) # Current frame number (OR: Current cell number)
        self.bch_blocks= int(blocks[0][15:19], 2) # Number of (42-bit) BCH blocks in this message

        if self.ms_type==1:
            self.group="A"
            self.group_int=0
            self.unknown1  = blocks[0][19]        # ?
            self.secondary = int(blocks[0][20])   # Something like secondary SV
        else:
            self.group=      int(blocks[0][19:21], 2)
            self.group_int= 1+self.group

        if self.zero1 != '0000':
            self._new_error("zero1 not 0000")

        self.tdiff=((self.block*5+self.group_int)*48+self.frame)*90

        if self.bch_blocks < 2:
            raise ParserError("length field in header too small") # in-packet size too small

        self.bch_extra=""
        if self.bch_blocks*2 > len(blocks):
            self._new_error("Not enough data received")
            self._new_error("Need %d, got %d" % (self.bch_blocks*2, len(blocks)))
#            raise ParserError("")
        elif self.bch_blocks*2 < len(blocks):
            self.trailer="{EXTRA}"
            self.bch_extra=self.bitstream_bch[self.bch_blocks*42:]
            blocks=blocks[:2*self.bch_blocks]

        myodd="".join([x[:1] for x in blocks]) # collect "oddbits"
        if self.group=="A":
            myodd=myodd[0]+"_"+myodd[1:5]+"_"+myodd[5:]
        else:
            myodd=myodd[0]+myodd[1:]
#x#        print("IMS_ %d %s %s"%(self.bch_blocks,self.group,myodd), end=" ")
        blocks.pop(0)

        # Acquisition group messages have 2 "42-bit blocks" pre-message a.k.a. block header message
        if self.group=="A":
            if len(blocks)<2:
                raise ParserError("not enough data in acquisition group message")
            if len(blocks)>=4:
                self.ablocks=blocks.pop(0),blocks.pop(0),blocks.pop(0),blocks.pop(0)
            else:
                self.ablocks=blocks.pop(0),blocks.pop(0)
#            self.ctr1=int(self.ablocks[0][0:12],2)

        # Message may have up to two "all-1" trailer blocks
        self.msg_trailer=0
        trailer=""
        if len(blocks)>0 and blocks[-1][0]=="1":
            trailer=blocks.pop()
            if(trailer != "1"*21):
                self._new_error("trailer exists, but not all-1")
            self.msg_trailer+=1
            if len(blocks)>0 and blocks[-1][0]=="1":
                trailer=blocks.pop()
                if(trailer != "1"*21):
                    self._new_error("second trailer exists, but not all-1")
                self.msg_trailer+=1

#x#        print("T:%d"%(self.msg_trailer),"BR:",len(blocks),end=" ")

        self.blocks=blocks

    def upgrade(self):
        if len(self.blocks)>0:
            try:
                return IridiumMSMessageBody(self).upgrade()
            except ParserError as e:
                self._new_error(str(e), e.cls)
        return self

    def _pretty_header(self):
        str= super()._pretty_header()
        str+= " %1d:%s:%02d" % (self.block, self.group, self.frame)
        str+= " len:%02d" % (self.bch_blocks)
        str+= "/T%d" % (self.msg_trailer)
        str+= "/F%02d" % (self.fill)
        if(self.group == "A"):
            str+= " %s %s %-87s" % (self.unknown1, self.secondary, " ".join(self.ablocks))
        else:
            str+= " %s %s %-87s" % (" "," "," ")
        return str

    def _pretty_trailer(self):
        str= super()._pretty_trailer()
        if "bch_extra" in self.__dict__ and self.bch_extra!="":
            str+= " bch_extra:"+self.bch_extra
        return str

    def pretty(self):
        str= "IMS: "+self._pretty_header()
        str+=self._pretty_trailer()
        return str

class IridiumMSMessageBody(IridiumMSMessage):
    def __init__(self, imsg):
        self.__dict__=imsg.__dict__

        blocks=self.blocks


        self.msg_odd="".join([x[:1] for x in blocks]) # collect "oddbits"
        rest="".join([x[1:] for x in blocks]) # remove "oddbits"

        if len(rest)<=27:
            raise ParserError("message too short(body)")

        self.msg_ric=int(rest[0:22][::-1],2) # XXX: rest[20:22] maybe not part of RIC?
        self.msg_format=int(rest[22:27],2)
        rest=rest[27:]

        if len(rest)<=16:
            self._new_error("incomplete MSG body")
            return

        self.msg_seq=int(rest[0:6],2) # 0-61 (62/63 seem unused)
        self.msg_zero1=int(rest[6:10],2)
        if(self.msg_zero1 != 0):
            self._new_error("zero1 is not all-zero")
        self.pkt_cs1=rest[10:16]

        self.msg_data=rest[16:]

    def upgrade(self):
        if "msg_data" in self.__dict__ and len(self.msg_data) >= 5:
            try:
                if(self.msg_format == 5):
                    return IridiumMessagingAscii(self).upgrade()
                elif(self.msg_format == 3):
                    return IridiumMessagingBCD(self).upgrade()
                self._new_error("unknown msg_format")
            except ParserError as e:
                self._new_error(str(e), e.cls)
        return self

    def _pretty_header(self):
        str= super()._pretty_header()
        str += " ric:%07d fmt:%02d"%(self.msg_ric,self.msg_format)
        if "msg_seq" in self.__dict__:
            str += " seq:%02d"%(self.msg_seq)
        return str

    def _pretty_trailer(self):
        str= super()._pretty_trailer()
        return str

    def pretty(self):
        str= "MSG: "+self._pretty_header()
        if "msg_data" in self.__dict__:
            str+= " "+group(self.msg_data,20)
        str+=self._pretty_trailer()
        return str

# MSG checksum:
def msg_checksum(blocks):
    csum_val=int((blocks[0][-3:]+blocks[1][1:8])[::-1], 2)
    csum=0
    # sum of each 21-bit BCH block, split into 8,8,5 bit values
    # need to exclude the actual checksum bits from the sum
    for idx,contents in enumerate(blocks):
        if idx!=1:
            csum+=int(contents[:8],   2) # including "odd" bit
        csum+=int(contents[8:16], 2)
        if idx!=0:
            csum+=int(contents[16:],  2) # 5 bits

    # this sum plus the 10-bit checksum value should be 1023
    csum_ok= (csum_val+csum) % 1024 == 1023
    return (csum_ok, csum_val)

class IridiumMessagingAscii(IridiumMSMessageBody):
    def __init__(self,immsg):
        self.__dict__=immsg.__dict__

        rest=self.msg_data

        # first block (ric) is not part of the checksum
        self.pkt_csum_ok, self.pkt_csum= msg_checksum(self.blocks[1:])

        pkt_cs2=rest[0:4]
        self.msg_len_bit=rest[4]
        rest=rest[5:]
        if(self.msg_len_bit=="1"):
            lfl=int(rest[0:4],2)
            self.msg_len_field_len=lfl
            if(lfl == 0):
                raise ParserError("len_field_len unexpectedly 0")
            self.msg_ctr=    int(rest[4:4+lfl],2)
            if len(rest[4+lfl:4+lfl*2])==0:
                raise ParserError("message too short(lfl)")
            self.msg_ctr_max=int(rest[4+lfl:4+lfl*2],2)
            rest=rest[4+lfl*2:]
            if(lfl<1 or lfl>2):
                self._new_error("len_field_len not 1 or 2")
        else:
            self.msg_len=0
            self.msg_ctr=0
            self.msg_ctr_max=0

        if len(rest) < 8:
            raise ParserError("message too short(ascii)")

        self.msg_zero2=rest[0]
        if(self.msg_zero2 != "0"):
            self._new_error("zero2 is not zero")
        self.msg_checksum=int(rest[1:8],2)
        self.msg_msgdata=rest[8:]

        chars, self.msg_rest= slice_extra(self.msg_msgdata, 7)
        self.msg_ascii=""
        end=0
        errs=0
        for (group) in chars:
            character = int(group, 2)
            if(character==3):
                end=1
            elif(end==1):
                if args.harder:
                    errs+=1
                else:
                    self._new_error("ETX inside ascii")
            if(character<32 or character==127):
                self.msg_ascii+="[%d]"%character
            else:
                self.msg_ascii+=chr(character)
        if errs>0:
            self.fixederrs+=1
    def upgrade(self):
        if self.error: return self
        return self
    def _pretty_header(self):
        str= super()._pretty_header()
        str+=" "
        if self.pkt_csum_ok:
            str+= "C:OK/%04d"%(self.pkt_csum)
        else:
            str+= "C:no/%04d"%(self.pkt_csum)
        str+= " %1d/%1d"%(self.msg_ctr,self.msg_ctr_max)
        (full,rest)=slice_extra(self.msg_msgdata,8)
        msgx="".join(["%02x"%int(x,2) for x in full])
        return str+ " csum:%02x msg:%s.%s"%(self.msg_checksum,msgx,rest)
    def pretty(self):
        str= "MSG: "+self._pretty_header()
        str+= " TXT: %-65s"%self.msg_ascii+" +%-6s"%self.msg_rest
        str+= self._pretty_trailer()
        return str

class IridiumMessagingBCD(IridiumMSMessageBody):
    def __init__(self,immsg):
        self.__dict__=immsg.__dict__

        rest=self.msg_data

        self.msg_unknown2=rest[:1] # msg_len_bit ?
        self.msg_msgdata=rest[1:]
        bcd=slice(self.msg_msgdata,4)
        self.bcd="".join(["%01x"%int(x,2) for x in bcd])
    def upgrade(self):
        if self.error: return self
        return self
    def _pretty_header(self):
        str= super()._pretty_header()
        str+= " %6s"%(self.pkt_cs1)
        return str+ " %s"%(self.msg_unknown2)
    def pretty(self):
        str= "MS3: "+self._pretty_header()
        str+= " BCD: %-65s"%self.bcd
        str+= self._pretty_trailer()
        return str


class IridiumNXTMessage(IridiumMessage):
    def __init__(self, imsg):
        self.__dict__ = imsg.__dict__
        self.fixederrs = 0
        if len(self.descrambled) < 233:
            self._new_error("next frame too short")

        # fixed pattern of 30 "1"s
        ones = self.descrambled[176:206]
        zeroes = ones.count("0")
        if zeroes > 0:
            self.fixederrs += 1

    def upgrade(self):
        if self.error: return self
        return self

    def pretty(self):
        st = "NXT: " + self._pretty_header()
        st += " " + group(self.descrambled[:32], 8)
        st += " | "
        st += group(self.descrambled[32:36], 2)
        st += " > "
        st += group(self.descrambled[36:], 10)
        st += self._pretty_trailer()
        return st

def symbol_reverse(bits):
    r = bytearray(bits.encode("us-ascii"))
    for x in range(0,len(r)-1,2):
        i=r[x+0]
        r[x+0]=r[x+1]
        r[x+1]=i
    return r.decode("us-ascii")

def de_interleave(group):
    symbols = [group[z+1]+group[z] for z in range(0,len(group),2)]
    even = ''.join([symbols[x] for x in range(len(symbols)-2,-1, -2)])
    odd  = ''.join([symbols[x] for x in range(len(symbols)-1,-1, -2)])
    return (odd,even)

def de_interleave3(group):
    symbols = [group[z+1]+group[z] for z in range(0,len(group),2)]
    third  = ''.join([symbols[x] for x in range(len(symbols)-3, -1, -3)])
    second = ''.join([symbols[x] for x in range(len(symbols)-2, -1, -3)])
    first  = ''.join([symbols[x] for x in range(len(symbols)-1, -1, -3)])
    return (first,second,third)

def de_interleave_lcw(bits):
    tbl= [ 40, 39, 36, 35, 32, 31, 28, 27, 24, 23, 20, 19, 16, 15, 12, 11,  8,  7,  4,  3,
           41, 38, 37, 34, 33, 30, 29, 26, 25, 22, 21, 18, 17, 14, 13, 10,  9,  6,  5,  2,
            1, 46, 45, 44, 43, 42]
    lcw=[bits[x-1:x] for x in tbl]
    return (''.join(lcw[:7]),''.join(lcw[7:20]),''.join(lcw[20:]))

def messagechecksum(msg):
    csum=0
    for x in re.findall(".",msg):
        csum=(csum+ord(x))%128
    return (~csum)%128

def checksum_16(msg):
    csum=sum(struct.unpack("<14HBH",msg))
    csum=((csum&0xffff) + (csum>>16))
    return csum^0xffff

def de_dqpsk(bits):
    symbols=[]
    imap=[0,1,3,2]
    # back into bpsk symbols
    for x in range(0,len(bits)-1,2):
        symbols.append(imap[int(bits[x+0])*2 + int(bits[x+1])])

    # undo differential decoding
    for c in range(1,len(symbols)):
        symbols[c]=(symbols[c-1]+symbols[c])%4

    return symbols

def split_qpsk(symbols):
    i_list=""
    q_list=""
    for sym in symbols:
        if sym==0:
            i_list+="0"
            q_list+="0"
        elif sym==1:
            i_list+="1"
            q_list+="0"
        elif sym==2:
            i_list+="1"
            q_list+="1"
        elif sym==3:
            i_list+="0"
            q_list+="1"
    return (i_list,q_list)
