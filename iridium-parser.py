#!/usr/bin/env python
# vim: set ts=4 sw=4 tw=0 et pm=:
import sys
import re
from bch import repair
import fileinput
import getopt
import types
import copy
import datetime
from itertools import izip

options, remainder = getopt.getopt(sys.argv[1:], 'vi:o:ps', [
                                                         'verbose',
                                                         'input=',
                                                         'output=',
                                                         'perfect',
                                                         'satclass',
                                                         'plot=',
                                                         'filter=',
                                                         ])

iridium_access="001100000011000011110011" # Actually 0x789h in BPSK
iridium_lead_out="100101111010110110110011001111"
header_messaging="00110011111100110011001111110011" # 0x9669 in BPSK
messaging_bch_poly=1897
ringalert_bch_poly=1207

verbose = False
perfect = False
dosatclass = False
input= "raw"
output= "line"
linefilter=[]
plotargs=["time", "frequency"]

for opt, arg in options:
    if opt in ('-v', '--verbose'):
        verbose = True
    elif opt in ('-p', '--perfect'):
        perfect = True
    elif opt in ('-s', '--satclass'):
        dosatclass = True
    elif opt in ('--plot'):
        plotargs=arg.split(',')
    elif opt in ('--filter'):
        linefilter=arg.split(',')
    elif opt in ('-i', '--input'):
        input=arg
    elif opt in ('-o', '--output'):
        output=arg
    else:
        raise Exception("unknown argument?")

if input == "dump" or output == "dump":
    import cPickle as pickle
    dumpfile="pickle.dump"

if dosatclass == True:
    import satclass
    satclass.init()

class ParserError(Exception):
    pass
        
tswarning=False
tsoffset=0
maxts=0
class Message(object):
    def __init__(self,line):
        self.parse_error=False
        self.error=False
        self.error_msg=[]
        p=re.compile('RAW: ([^ ]*) (\d+) (\d+) A:(\w+) L:(\w+) +(\d+)% ([\d.]+) +(\d+) ([\[\]<> 01]+)(.*)')
        m=p.match(line)
        if(not m):
            self._new_error("Couldn't parse: "+line)
            self.parse_error=True
            return
        self.filename=m.group(1)
        if self.filename=="/dev/stdin":
            self.filename="-";
        self.timestamp=int(m.group(2))
        self.frequency=int(m.group(3))
#        self.access_ok=(m.group(4)=="OK")
#        self.leadout_ok=(m.group(5)=="OK")
        self.confidence=int(m.group(6))
        self.level=float(m.group(7))
#        self.raw_length=m.group(8)
        self.bitstream_raw=re.sub("[\[\]<> ]","",m.group(9)) # raw bitstring
        self.symbols=len(self.bitstream_raw)/2
        if m.group(10):
            self.extra_data=m.group(10)
            self._new_error("There is crap at the end in extra_data")
        # Make a "global" timestamp
        global tswarning,tsoffset,maxts
        mm=re.match("(\d\d)-(\d\d)-(20\d\d)T(\d\d)-(\d\d)-(\d\d)-[sr]1",self.filename)
        if mm:
            month, day, year, hour, minute, second = map(int, mm.groups())
            ts=datetime.datetime(year,month,day,hour,minute,second)
            ts=(ts- datetime.datetime(1970,1,1)).total_seconds()
            ts+=float(self.timestamp)/1000
            self.globaltime=ts
            return
        mm=re.match("i-(\d+(?:\.\d+)?)-[vbsrtl]1.([a-z])([a-z])",self.filename)
        if mm:
            b26=(ord(mm.group(2))-ord('a'))*26+ ord(mm.group(3))-ord('a')
            self.b26=b26
            ts=float(mm.group(1))+float(self.timestamp)/1000+b26*600
            self.globaltime=ts
            return
        mm=re.match("i-(\d+(?:\.\d+)?)-[vbsrtl]1(?:-o[+-]\d+)?$",self.filename)
        if mm:
            ts=float(mm.group(1))+float(self.timestamp)/1000
            self.globaltime=ts
            return
        if not tswarning:
            print "Warning: no timestamp found in filename"
            tswarning=True
        ts=tsoffset+float(self.timestamp)/1000
        if ts<maxts:
            tsoffset=maxts
            ts=tsoffset+float(self.timestamp)/1000
        maxts=ts
        self.globaltime=ts

    def upgrade(self):
        if self.error: return self
        if(self.bitstream_raw.startswith(iridium_access)):
            try:
                return IridiumMessage(self).upgrade()
            except ParserError,e:
                self._new_error(str(e))
                return self
        return self
    def _new_error(self,msg):
        self.error=True
        msg=str(type(self).__name__) + ": "+msg
        if not self.error_msg or self.error_msg[-1] != msg:
            self.error_msg.append(msg)
    def _pretty_header(self):
        return "%s %09d %010d %3d%% %.3f"%(self.filename,self.timestamp,self.frequency,self.confidence,self.level)
    def _pretty_trailer(self):
        return ""
    def pretty(self):
        if self.parse_error:
            return "ERR: "
        str= "RAW: "+self._pretty_header()
        str+= " "+self.bitstream_raw
        if("extra_data" in self.__dict__):
            str+=" "+self.extra_data
        str+=self._pretty_trailer()
        return str

class IridiumMessage(Message):
    def __init__(self,msg):
        self.__dict__=copy.deepcopy(msg.__dict__)
        data=self.bitstream_raw[len(iridium_access):]

        if data[:32] == header_messaging:
            self.msgtype="MSG"
        elif  1626229167<self.frequency<1626312500:
            self.msgtype="RA"
        else:
#            raise ParserError("unknown Iridium message type")
            self.msgtype="BC" # XXX: need to do better
        if self.msgtype=="MSG":

            self.header=data[:32]
            self.bitstream_descrambled=""
            data=data[32:]
        elif self.msgtype=="RA":
            if  len(data)<96:
                raise ParserError("No data to descramble")
            self.header=""
            self.bitstream_descrambled=de_interleave3(data[:96])
            data=data[96:]
        elif self.msgtype=="BC":
            self.header=data[:6]
            data=data[6:]
            self.bitstream_descrambled=""

        m=re.compile('(\d{64})').findall(data)
        for (group) in m:
            self.bitstream_descrambled+=de_interleave(group)
            data=data[64:]
        if(not self.bitstream_descrambled):
            raise ParserError("No data to descramble")
        self.lead_out_ok= data.startswith(iridium_lead_out)
        if(data):
            self.descramble_extra=data
        else:
            self.descramble_extra=""
    def upgrade(self):
        if self.error: return self
        try:
            return IridiumECCMessage(self).upgrade()
        except ParserError,e:
            self._new_error(str(e))
            return self
        return self
    def _pretty_header(self):
        str= super(IridiumMessage,self)._pretty_header()
        str+= " %03d"%(len(self.header+self.bitstream_descrambled+self.descramble_extra)/2)
        str+=" L:"+("no","OK")[self.lead_out_ok]
        if self.header:
            str+=" "+self.header
        return str
    def _pretty_trailer(self):
        str= super(IridiumMessage,self)._pretty_trailer()
        str+= " descr_extra:"+re.sub(iridium_lead_out,"["+iridium_lead_out+"]",self.descramble_extra)
        return str
    def pretty(self):
        str= "IRI: "+self._pretty_header()
        str+= " %3s"%self.msgtype
        str+= " "+re.sub("(\d)(\d{20})(\d{10})(\d)","{\\1 \\2 \\3 \\4} ",self.bitstream_descrambled)
        str+= self._pretty_trailer()
        return str

class IridiumECCMessage(IridiumMessage):
    def __init__(self,imsg):
        self.__dict__=copy.deepcopy(imsg.__dict__)
        if self.msgtype == "MSG":
            poly="{0:011b}".format(messaging_bch_poly)
        elif self.msgtype == "RA":
            poly="{0:011b}".format(ringalert_bch_poly)
        elif self.msgtype == "BC":
            poly="{0:011b}".format(ringalert_bch_poly)
        else:
            raise ParserError("unknown Iridium message type")
        self.bitstream_messaging=""
        self.bitstream_bch=""
        self.oddbits=""
        self.fixederrs=0
        m=re.compile('(\d)(\d{20})(\d{10})(\d)').findall(self.bitstream_descrambled)
        # TODO: bch_ok and parity_ok arrays
        for (odd,msg,bch,parity) in m:
            (errs,bnew)=repair(poly, odd+msg+bch)
            if(errs>0):
                self.fixederrs+=1
                odd=bnew[0]
                msg=bnew[1:21]
                bch=bnew[21:]
            if(errs<0):
                raise ParserError("BCH decode failed")
            parity=len(re.sub("0","",odd+msg+bch+parity))%2
            if parity==1:
                raise ParserError("Parity error")
            self.bitstream_messaging+=msg
            self.bitstream_bch+=odd+msg
            self.oddbits+=odd
    def upgrade(self):
        if self.error: return self
        try:
            if self.msgtype == "MSG":
                return IridiumMessagingMessage(self).upgrade()
            elif self.msgtype == "RA":
                return IridiumRAMessage(self).upgrade()
            elif self.msgtype == "BC":
                return IridiumBCMessage(self).upgrade()
            else:
                self._new_error("Unknown message type")
        except ParserError,e:
            self._new_error(str(e))
            return self
        return self
    def _pretty_header(self):
        str= super(IridiumECCMessage,self)._pretty_header()
        return str
    def _pretty_trailer(self):
        return super(IridiumECCMessage,self)._pretty_trailer()
    def pretty(self):
        str= "IME: "+self._pretty_header()
        str+= " fix:%d"%self.fixederrs
        str+= " "+group(self.bitstream_bch,21)
        str+=self._pretty_trailer()
        return str

class IridiumBCMessage(IridiumECCMessage):
    def __init__(self,imsg):
        self.__dict__=copy.deepcopy(imsg.__dict__)
        # Decode stuff from self.bitstream_bch
        self.bc_type= int(self.bitstream_bch[46:48],2)
        self.bc_uplink_ch= int(self.bitstream_bch[32:37],2)
        self.bc_aqch_av= int(self.bitstream_bch[37:40],2)
    def upgrade(self):
        if self.error: return self
        try:
            return self
        except ParserError,e:
            self._new_error(str(e))
            return self
        return self
    def _pretty_header(self):
        return super(IridiumBCMessage,self)._pretty_header()
    def _pretty_trailer(self):
        return super(IridiumBCMessage,self)._pretty_trailer()
    def pretty(self):
        str= "IBC: "+self._pretty_header()
        str+= " sat:%02d"%int(self.bitstream_bch[:7], 2)
        str+= " cell:%02d"%int(self.bitstream_bch[7:13], 2)
        str+= " %s"%self.bitstream_bch[13:16]
        str+= " %s"%self.bitstream_bch[16:32]
        str+= " %s"%self.bitstream_bch[32:37]
        str+= "[%d]"%self.bc_uplink_ch
        str+= " %s"%self.bitstream_bch[37:40]
        str+= "[%d]"%self.bc_aqch_av
        str+= " %s"%self.bitstream_bch[40:46]
        str+= " %s"%self.bitstream_bch[46:48]
        str+= "[%d]"%self.bc_type
        if self.bc_type==1:
            str+= " %s"%self.bitstream_bch[48:64]
            str+= " "+self.bitstream_bch[64:74]
            str+= " ctr=[%04d]"%int(self.bitstream_bch[74:83],2)
            str+= " "+group(self.bitstream_bch[83:],16)
        else:
            str+= " %s"%self.bitstream_bch[48:64]
            str+= " "+group(self.bitstream_bch[64:],16)
        str+=self._pretty_trailer()
        return str

class IridiumRAMessage(IridiumECCMessage):
    def __init__(self,imsg):
        self.__dict__=copy.deepcopy(imsg.__dict__)
        # Decode stuff from self.bitstream_bch
        self.ra_sat= int(self.bitstream_bch[0:7],2)
        self.ra_cell= int(self.bitstream_bch[7:13],2)
        self.ra_ctr1= int(self.bitstream_bch[14:25],2)
        self.ra_ctr2= int(self.bitstream_bch[27:37],2)
        self.ra_ctr3= int(self.bitstream_bch[37:49],2)
        self.ra_f4=   int(self.bitstream_bch[58:63],2)
    def upgrade(self):
        if self.error: return self
        try:
            return self
        except ParserError,e:
            self._new_error(str(e))
            return self
        return self
    def _pretty_header(self):
        return super(IridiumRAMessage,self)._pretty_header()
    def _pretty_trailer(self):
        return super(IridiumRAMessage,self)._pretty_trailer()
    def pretty(self):
        str= "IRA: "+self._pretty_header()
        str+= " ts:%04d"%(self.globaltime/4.320)
        str+= " sat:%02d"%self.ra_sat
        str+= " cell:%02d"%self.ra_cell
        str+= " %s"%self.bitstream_bch[13]

        str+= " %s"%self.bitstream_bch[14:22]
        str+= ","+self.bitstream_bch[22:25]
        str+= "[%04d]"%self.ra_ctr1

        str+= " "+self.bitstream_bch[25:27]

        str+= " "+self.bitstream_bch[27:37]
        str+= "[%04d]"%self.ra_ctr2

        str+= " "+self.bitstream_bch[37:42]
        str+= ","+self.bitstream_bch[42:49]
        str+= "[%04d]"%self.ra_ctr3

        str+= " "+self.bitstream_bch[49:56]
        str+= " "+self.bitstream_bch[56:58]
        str+= " "+self.bitstream_bch[58:63]
        str+= "{%02d}"%self.ra_f4

        str+= " "+group(self.bitstream_bch[63:],21)
        str+=self._pretty_trailer()
        return str

class IridiumMessagingMessage(IridiumECCMessage):
    def __init__(self,imsg):
        self.__dict__=copy.deepcopy(imsg.__dict__)
        rest=self.bitstream_messaging

        self.zero1 = rest[0:4]
        if self.zero1 != '0000':
            self._new_error("zero1 not 0000")

        self.block = int(rest[4:4+4], 2)        # Block number in the super frame
        self.frame = int(rest[8:8+6], 2)        # Current frame number (OR: Current cell number)
        self.bch_blocks = int(rest[14:18], 2)   # Number of BCH blocks in this message
        self.unknown1=rest[18]                  # ?
        self.secondary = int(rest[19])          # Something like secondary SV
        self.ctr1=int(rest[19]+self.oddbits[1]+rest[20:32],2)

        if(self.oddbits[0]=="1"):
            self.group="A"
            self.agroup=0
        else:
            self.group=int(rest[18:20],2)
            self.agroup=1+self.group
        self.tdiff=((self.block*5+self.agroup)*48+self.frame)*90

        if len(self.bitstream_messaging) != self.bch_blocks * 40:
            self._new_error("Incorrect amount of data received")

        # If oddbits ends in 1, this is an all-1 block -- remove it
        self.msg_trailer=""
        if(self.oddbits[-1]=="1"):
            self.msg_trailer=rest[-20:]
            if(self.msg_trailer != "1"*20):
                self._new_error("trailer exists, but not all-1")
            rest=rest[0:-20]
            # If oddbits still ends in 1, probably also an all-1 block
            if(self.oddbits[-2]=="1"):
                self.msg_trailer=rest[-20:]+self.msg_trailer
                if(self.msg_trailer != "1"*40):
                    self._new_error("second trailer exists, but not all-1")
                rest=rest[0:-20]
        # If oddbits starts with 1, there is a 80-bit "pre" message
        if self.oddbits[0]=="1":
            self.msg_pre=rest[20:100]
            rest=rest[100:]
        else:
            self.msg_pre=""
            rest=rest[20:]
        # If enough  bits are left, there will be a pager message
        if len(rest)>20:
            self.msg_ric=int(rest[0:22][::-1],2)
            self.msg_format=int(rest[22:27],2)
            self.msg_data=rest[27:]
    def upgrade(self):
        if self.error: return self
        try:
            if("msg_format" in self.__dict__):
                if(self.msg_format == 5):
                    return IridiumMessagingAscii(self).upgrade()
                elif(self.msg_format == 3):
                    return IridiumMessagingUnknown(self).upgrade()
                else:
                    self._new_error("unknown msg_format")
        except ParserError,e:
            self._new_error(str(e))
            return self
        return self
    def _pretty_header(self):
        str= super(IridiumMessagingMessage,self)._pretty_header()
        str+= " odd:%-26s" % (self.oddbits)
        str+= " %1d:%s:%02d" % (self.block, self.group,self.frame)
        if(self.oddbits == "1011"):
            str+= " %s sec:%d %-83s" % (self.unknown1, self.secondary, group(self.msg_pre,20))
        elif(self.group == "A"):
            str+= " %s c=%05d           %s %-62s" % (self.unknown1, self.ctr1, self.msg_pre[12:20],group(self.msg_pre[20:],20))
        else:
            str+= "         %-83s" % (group(self.msg_pre,20))
        if("msg_format" in self.__dict__):
            str += " ric:%07d fmt:%02d"%(self.msg_ric,self.msg_format)
        return str
    def _pretty_trailer(self):
        return super(IridiumMessagingMessage,self)._pretty_trailer()
    def pretty(self):
        str= "IMS: "+self._pretty_header()
        if("msg_format" in self.__dict__):
            str+= " "+group(self.msg_data,20)
        str+=self._pretty_trailer()
        return str
        
class IridiumMessagingAscii(IridiumMessagingMessage):
    def __init__(self,immsg):
        self.__dict__=copy.deepcopy(immsg.__dict__)
        rest=self.msg_data
        self.msg_seq=int(rest[0:6],2) # 0-61 (62/63 seem unused)
        self.msg_zero1=int(rest[6:10],2)
        if(self.msg_zero1 != 0):
            self._new_error("zero1 is not all-zero")
        self.msg_unknown1=rest[10:20]
        self.msg_len_bit=rest[20]
        rest=rest[21:]
        if(self.msg_len_bit=="1"):
            lfl=int(rest[0:4],2)
            self.msg_len_field_len=lfl
            if(lfl == 0):
                raise ParserError("len_field_len unexpectedly 0")
            self.msg_ctr=    int(rest[4:4+lfl],2)
            self.msg_ctr_max=int(rest[4+lfl:4+lfl*2],2)
            rest=rest[4+lfl*2:]
            if(lfl<1 or lfl>2):
                self._new_error("len_field_len not 1 or 2")
        else:
            self.msg_len=0
            self.msg_ctr=0
            self.msg_ctr_max=0
        self.msg_zero2=rest[0]
        if(self.msg_zero2 != "0"):
            self._new_error("zero2 is not zero")
        self.msg_checksum=int(rest[1:8],2)
        self.msg_msgdata=rest[8:]
        m=re.compile('(\d{7})').findall(self.msg_msgdata)
        self.msg_ascii=""
        end=0
        for (group) in m:
            character = int(group, 2)
            if(character==3):
                end=1
            elif(end==1):
                self._new_error("ETX inside ascii")
            if(character<32 or character==127):
                self.msg_ascii+="[%d]"%character
            else:
                self.msg_ascii+=chr(character)
        if len(self.msg_msgdata)%7:
            self.msg_rest=self.msg_msgdata[-(len(self.msg_msgdata)%7):]
        else:
            self.msg_rest=""
        #TODO: maybe checksum checks
    def upgrade(self):
        if self.error: return self
        return self
    def _pretty_header(self):
        str= super(IridiumMessagingAscii,self)._pretty_header()
        return str+ " seq:%02d %10s %1d/%1d"%(self.msg_seq,self.msg_unknown1,self.msg_ctr,self.msg_ctr_max)
    def _pretty_trailer(self):
        return super(IridiumMessagingAscii,self)._pretty_trailer()
    def pretty(self):
       str= "MSG: "+self._pretty_header()
       str+= " %-65s"%self.msg_ascii+" +%-6s"%self.msg_rest
       str+= self._pretty_trailer()
       return str
        
class IridiumMessagingUnknown(IridiumMessagingMessage):
    def __init__(self,immsg):
        self.__dict__=copy.deepcopy(immsg.__dict__)
        rest=self.msg_data
        self.msg_seq=int(rest[0:6],2)
        self.msg_zero1=int(rest[6:10],2)
        if(self.msg_zero1 != 0):
            self._new_error("zero1 is not all-zero")
        self.msg_unknown1=rest[10:20]
        rest=rest[20:]
        self.msg_unknown2=rest[:1]
        self.msg_msgdata=rest[1:]
    def upgrade(self):
        if self.error: return self
        return self
    def _pretty_header(self):
        str= super(IridiumMessagingUnknown,self)._pretty_header()
        return str+ " seq:%02d %10s %s"%(self.msg_seq,self.msg_unknown1,self.msg_unknown2)
    def _pretty_trailer(self):
        return super(IridiumMessagingUnknown,self)._pretty_trailer()
    def pretty(self):
       str= "MS3: "+self._pretty_header()
       str+= " %-65s"%group(self.msg_msgdata,4)
       str+= self._pretty_trailer()
       return str
        
def grouped(iterable, n):
    "s -> (s0,s1,s2,...sn-1), (sn,sn+1,sn+2,...s2n-1), ..."
    return izip(*[iter(iterable)]*n)

def de_interleave(group):
    symbols = [''.join(symbol) for symbol in grouped(group, 2)]
    even = ''.join([symbols[x] for x in range(len(symbols)-2,-1, -2)])
    odd  = ''.join([symbols[x] for x in range(len(symbols)-1, 0, -2)])
    field = odd + even
    return field

def de_interleave3(group):
    symbols = [''.join(symbol) for symbol in grouped(group, 2)]
    third  = ''.join([symbols[x] for x in range(len(symbols)-3, -1, -3)])
    second = ''.join([symbols[x] for x in range(len(symbols)-2, -1, -3)])
    first  = ''.join([symbols[x] for x in range(len(symbols)-1, -1, -3)])
    return first+second+third

def messagechecksum(msg):
    csum=0
    for x in re.findall(".",msg):
        csum=(csum+ord(x))%128
    return (~csum)%128

def group(string,n): # similar to grouped, but keeps rest at the end
    string=re.sub('(.{%d})'%n,'\\1 ',string)
    return string.rstrip()

if output == "dump":
    file=open(dumpfile,"wb")

if output == "plot":
    import matplotlib.pyplot as plt
    xl=[]
    yl=[]
    cl=[]
    sl=[]

selected=[]

def do_input(type):
    if type=="raw":
        for line in fileinput.input(remainder):
            line=line.strip()
            q=Message(line.strip()).upgrade()
            perline(q)
    elif type=="dump":
        file=open(dumpfile,"rb")
        try:
            while True:
                q=pickle.load(file)
                perline(q)
        except EOFError:
            pass
    else:
        print "Unknown input mode."
        exit(1)

def perline(q):
    if dosatclass == True:
        sat=satclass.classify(q.frequency,q.globaltime)
        q.satno=int(sat.name)
    if len(linefilter)>0:
        if linefilter[0]!="All" and type(q).__name__ != linefilter[0]:
            return
        if len(linefilter)>1:
            if not eval(linefilter[1]):
                return
    if output == "err":
        if(q.error):
            selected.append(q)
    elif output == "msg":
        if type(q).__name__ == "IridiumMessagingAscii" and not q.error:
            selected.append(q)
    elif output == "sat":
        if not q.error and not q.oddbits == "1011":
            selected.append(q)
    elif output == "dump":
        pickle.dump(q,file,1)
    elif output == "plot":
        selected.append(q)
    elif output == "line":
        if(q.error):
            if(not perfect):
                print q.pretty()+" ERR:"+", ".join(q.error_msg)
        else:
            print q.pretty()
    elif output == "rxstats":
        print "RX","X",q.globaltime, q.frequency,"X","X", q.confidence, q.level, q.symbols, q.error, type(q).__name__
    else:
        print "Unknown output mode."
        exit(1)

do_input(input)

if output == "sat":
    print "SATs:"
    sats=[]
    for m in selected:
        f=m.frequency
        t=m.globaltime
        no=-1
        for s in xrange(len(sats)):
            fdiff=(sats[s][0]-f)/(t-sats[s][1])
            if f<sats[s][0] and fdiff<250:
                no=s
        if no>-1:
            m.fdiff=(sats[no][0]-f)/(t-sats[no][1])
            sats[no][0]=f
            sats[no][1]=t
        else:
            no=len(sats)
            sats.append([f,t])
            m.fdiff=0
        m.satno=no
    for s in xrange(len(sats)):
        print "Sat: %02d"%s
        for m in selected:
            if m.satno == s: print m.pretty()

if output == "err":
    print "### "
    print "### Error listing:"
    print "### "
    sort={}
    for m in selected:
        msg=m.error_msg[0]
        if(msg in sort):
            sort[msg].append(m)
        else:
            sort[msg]=[m]
    for msg in sort:
        print msg+":"
        for m in sort[msg]:
            print "- "+m.pretty()

if output == "msg":
    buf={}
    ricseq={}
    wrapmargin=10
    for m in selected:
        # msg_seq wraps around after 61, detect it, and fix it.
        if m.msg_ric in ricseq:
            if (m.msg_seq + wrapmargin) < ricseq[m.msg_ric][1]: # seq wrapped around
                ricseq[m.msg_ric][0]+=62
            if (m.msg_seq + wrapmargin - 62) > ricseq[m.msg_ric][1]: # "wrapped back" (out-of-order old message)
                ricseq[m.msg_ric][0]-=62
        else:
            ricseq[m.msg_ric]=[0,0]
        ricseq[m.msg_ric][1]=m.msg_seq
        id="%07d[%03d]"%(m.msg_ric,(m.msg_seq+ricseq[m.msg_ric][0]))
        ts=m.globaltime
        if id in buf:
            if buf[id].msg_checksum != m.msg_checksum:
                print "Whoa! Checksum changed? Message %s (1: @%d checksum %d/2: @%d checksum %d)"%(id,buf[id].globaltime,buf[id].msg_checksum,m.globaltime,m.msg_checksum)
                # "Wrap around" to not miss the changed packet.
                ricseq[m.msg_ric][0]+=62
                id="%07d[%03d]"%(m.msg_ric,(m.msg_seq+ricseq[m.msg_ric][0]))
                m.msgs=['[NOTYET]']*3
                buf[id]=m
        else:
            m.msgs=['[NOTYET]']*3
            buf[id]=m
        buf[id].msgs[m.msg_ctr]=m.msg_ascii

    for b in sorted(buf, key=lambda x: buf[x].globaltime):
        msg="".join(buf[b].msgs[:1+buf[b].msg_ctr_max])
        msg=re.sub("(\[3\])+$","",msg) # XXX: should be done differently
        csum=messagechecksum(msg)
        str="Message %s @%s (len:%d)"%(b,datetime.datetime.fromtimestamp(buf[b].globaltime).strftime("%Y-%m-%dT%H:%M:%S"),buf[b].msg_ctr_max)
        str+= " %3d"%buf[b].msg_checksum
        str+= (" fail"," OK  ")[buf[b].msg_checksum == csum]
        str+= ": %s"%(msg)
        print str

def plotsats(plt, _s, _e):
    for ts in range(int(_s),int(_e),10):
        for v in satclass.timelist(ts):
            plt.scatter( x=v[0], y=v[1], c=int(v[2]), alpha=0.3, edgecolor="none", vmin=10, vmax=90)

if output == "plot":
    name="%s over %s"%(plotargs[1],plotargs[0])
    if len(plotargs)>2:
        name+=" with %s"%plotargs[2]
    filter=""
    if len(linefilter)>0 and linefilter[0]!="All":
        filter+="type==%s"%linefilter[0]
        name=("%s "%linefilter[0])+name
    if len(linefilter)>1:
        x=linefilter[1]
        if x.startswith("q."):
            x=x[2:]
        filter+=" and %s"%x
        name+=" where %s"%x
    plt.suptitle(filter)
    plt.xlabel(plotargs[0])
    plt.ylabel(plotargs[1])
    if plotargs[0]=="time":
        plotargs[0]="globaltime"

    if False:
        plotsats(plt,selected[0].globaltime,selected[-1].globaltime)

    for m in selected:
        xl.append(m.__dict__[plotargs[0]])
        yl.append(m.__dict__[plotargs[1]])
        if len(plotargs)>2:
            cl.append(m.__dict__[plotargs[2]])

    if len(plotargs)>2:
        plt.scatter(x = xl, y= yl, c= cl)
        plt.colorbar().set_label(plotargs[2])
    else:
        plt.scatter(x = xl, y= yl)

    mng = plt.get_current_fig_manager()
    mng.resize(*mng.window.maxsize())
    plt.savefig(re.sub('[/ ]','_',name)+".png")
    plt.show()

def objprint(q):
    for i in dir(q):
        attr=getattr(q,i)
        if i.startswith('_'):
            continue
        if isinstance(attr, types.MethodType):
            continue
        print "%s: %s"%(i,attr)
