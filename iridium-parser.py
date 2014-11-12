#!/usr/bin/env python
# vim: set ts=4 sw=4 tw=0 et pm=:
import sys
import re
from bch import repair
import fileinput
import getopt
import types
import copy
from itertools import izip

options, remainder = getopt.getopt(sys.argv[1:], 'vi:o:', [
                                                         'verbose',
                                                         'input',
                                                         'output',
                                                         ])

iridium_access="001100000011000011110011" # Actually 0x789h in BPSK
iridium_lead_out="100101111010110110110011001111"
header_messaging="00110011111100110011001111110011"
messaging_bch_poly=1897

verbose = False
input= "raw"
output= "line"

for opt, arg in options:
    if opt in ('-v', '--verbose'):
        verbose = True
    elif opt in ('-i', '--input'):
        input=arg
    elif opt in ('-o', '--output'):
        output=arg

class ParserError(Exception):
    pass
        
class Message(object):
    def __init__(self,line):
        p=re.compile('RAW: ([^ ]*) (\d+) (\d+) A:(\w+) L:(\w+) +(\d+)% ([\d.]+) +(\d+) ([\[\]<> 01]+)(.*)')
        m=p.match(line)
        if(not m):
            raise Exception("did not match")
        self.filename=m.group(1)
        self.timestamp=int(m.group(2))
        self.frequency=int(m.group(3))
#        self.access_ok=(m.group(4)=="OK")
#        self.leadout_ok=(m.group(5)=="OK")
        self.confidence=int(m.group(6))
        self.level=float(m.group(7))
#        self.raw_length=m.group(8)
        self.bitstream_raw=re.sub("[\[\]<> ]","",m.group(9)) # raw bitstring
        self.error=False
        self.error_msg=[]
        if m.group(10):
            self.extra_data=m.group(10)
            self._new_error("There is crap at the end in extra_data")
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
       return "%s %07d %010d %3d%% %.3f"%(self.filename,self.timestamp,self.frequency,self.confidence,self.level)
    def _pretty_trailer(self):
        return ""
    def pretty(self):
        str= "MSG: "+self._pretty_header()
        str+= " "+self.bitstream_raw
        if("extra_data" in self.__dict__):
            str+=" "+self.extra_data
        str+=self._pretty_trailer()
        return str

class IridiumMessage(Message):
    def __init__(self,msg):
        self.__dict__=copy.deepcopy(msg.__dict__)
        data=self.bitstream_raw[len(iridium_access):]
        self.header=data[:32]
        data=data[32:]
        m=re.compile('(\d{64})').findall(data)
        self.bitstream_descrambled=""
        for (group) in m:
            self.bitstream_descrambled+=de_interleave(group)
        if(not self.bitstream_descrambled):
            self._new_error("No data to descramble")
        data=data[len(self.bitstream_descrambled):]
        self.lead_out_ok= data.startswith(iridium_lead_out)
        if(data):
            self.descramble_extra=data
        else:
            self.descramble_extra=""
    def upgrade(self):
        if self.error: return self
        try:
            if(self.header == header_messaging):
                return IridiumECCMessage(self).upgrade()
            else:
                self._new_error("unknown Iridium message type")
        except ParserError,e:
            self._new_error(str(e))
            return self
        return self
    def _pretty_header(self):
        str= super(IridiumMessage,self)._pretty_header()
        str+= " %03d"%(len(self.header+self.bitstream_descrambled+self.descramble_extra)/2)
        str+=" L:"+("no","OK")[self.lead_out_ok]+" "+self.header
        return str
    def _pretty_trailer(self):
        str= super(IridiumMessage,self)._pretty_trailer()
        str+= " descr_extra:"+re.sub(iridium_lead_out,"["+iridium_lead_out+"]",self.descramble_extra)
        return str
    def pretty(self):
        str= "IRI: "+self._pretty_header()
        str+= " "+group(self.bitstream_descrambled,32)
        str+= self._pretty_trailer()
        return str

class IridiumECCMessage(IridiumMessage):
    def __init__(self,imsg):
        self.__dict__=copy.deepcopy(imsg.__dict__)
        poly="{0:011b}".format(messaging_bch_poly)
        self.bitstream_messaging=""
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
            self.oddbits+=odd
    def upgrade(self):
        if self.error: return self
        try:
            return IridiumMessagingMessage(self).upgrade()
        except ParserError,e:
            self._new_error(str(e))
            return self
        return self
    def _pretty_header(self):
        str= super(IridiumECCMessage,self)._pretty_header()
        str+= " odd:%-26s" % (self.oddbits)
        return str
    def _pretty_trailer(self):
        return super(IridiumECCMessage,self)._pretty_trailer()
    def pretty(self):
        str= "IME: "+self._pretty_header()
        str+= " "+group(self.bitstream_messaging,20)
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
        str+= " %1d:%02d %s sec:%d %-83s" % (self.block, self.frame, self.unknown1, self.secondary, group(self.msg_pre,20))
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
        self.msg_seq=int(rest[0:6],2)
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

def faketimestamp(self):
    mm=re.match("(\d\d)-(\d\d)-(20\d\d)T(\d\d)-(\d\d)-(\d\d)-s1",self.filename)
    if mm:
        fdt=float(mm.group(3))-2014
        fdt*=12
        fdt+=int(mm.group(1))
        fdt*=31
        fdt+=int(mm.group(2))
        fdt*=24
        fdt+=int(mm.group(4))
        fdt*=60
        fdt+=int(mm.group(5))
        fdt*=60
        fdt+=int(mm.group(6))
        fdt*=2
        fdt+=float(self.timestamp)/1000
        self.globaltime=fdt

def messagechecksum(msg):
    csum=0
    for x in re.findall(".",msg):
        csum=(csum+ord(x))%128
    return (~csum)%128

def group(string,n): # similar to grouped, but keeps rest at the end
    string=re.sub('(.{%d})'%n,'\\1 ',string)
    return string.rstrip()

messages=[]
errors=[]
for line in fileinput.input(remainder):
    line=line.strip()
    q=Message(line.strip()).upgrade()
    if(q.error):
        errors.append(q)
    elif type(q).__name__ == "IridiumMessagingAscii":
        faketimestamp(q)
        messages.append(q)
    if output == "line":
        if(q.error):
            print q.pretty()+" ERR:"+", ".join(q.error_msg)
        else:
            print q.pretty()

if output == "errors":
    print "### "
    print "### Error listing:"
    print "### "
    sort={}
    for m in errors:
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
    for m in messages:
        str="%12.3f"%m.globaltime
        str+=" %7d %2d"%(m.msg_ric,m.msg_seq)
        str+=" %d/%d"%(m.msg_ctr,m.msg_ctr_max)
        str+=" %s"%m.msg_ascii
#        print str
        id="%07d[%02d]"%(m.msg_ric,m.msg_seq)
        ts=m.globaltime
        if id in buf:
            buf[id].msgs[m.msg_ctr]=m.msg_ascii # XXX: check if already something there
        else:
            m.msgs=['[NOTYET]']*3
            m.msgs[m.msg_ctr]=m.msg_ascii
            buf[id]=m
        dellist=[]
        for b in buf:
            if buf[b].globaltime +2000 < ts:
                msg="".join(buf[b].msgs[:1+buf[b].msg_ctr_max])
                msg=re.sub("\[3\]","",msg) # XXX: should be done differently
                csum=messagechecksum(msg)
                str="Message %s (len:%d)"%(b,buf[b].msg_ctr_max)
                str+= (" fail"," OK  ")[buf[b].msg_checksum == csum]
                str+= ": %s"%(msg)
                print str
                dellist.append(b)
        for d in dellist:
            del buf[d]

def objprint(q):
    for i in dir(q):
        attr=getattr(q,i)
        if i.startswith('_'):
            continue
        if isinstance(attr, types.MethodType):
            continue
        print "%s: %s"%(i,attr)
