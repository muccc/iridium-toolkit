#!/usr/bin/env python
# vim: set ts=4 sw=4 tw=0 et pm=:

import sys
import fileinput
import getopt
import datetime
import re
import struct
import math
import os

verbose = False
ifile= None
ofile= None
mode= "undef"

options, remainder = getopt.getopt(sys.argv[1:], 'vi:o:m:', [
                                                         'verbose',
                                                         'input=',
                                                         'output=',
                                                         'mode=',
                                                         ])

for opt, arg in options:
    if opt in ('-v', '--verbose'):
        verbose = True
    elif opt in ('-i', '--input'):
        ifile=arg
    elif opt in ('-o', '--output'):
        ofile=arg
    elif opt in ('-m', '--mode'):
        mode=arg
    else:
        raise Exception("unknown argument?")

basename=None
if ifile == None:
    if not remainder:
        basename="stdin"
        ifile = "/dev/stdin"
    else:
        ifile = remainder[0]

if not basename:
    basename=re.sub('\.[^.]*$','',ifile)
#    basename=os.path.basename(re.sub('\.[^.]*$','',ifile))

if ofile == None:
    ofile="%s.%s" % (basename, mode)
    outfile=sys.stdout
elif ofile == "" or ofile == "=":
    ofile="%s.%s" % (basename, mode)
    outfile=open(ofile,"w")
else:
    basename=re.sub('\.[^.]*$','',ofile)
    outfile=open(ofile,"w")

if verbose:
    print "ifile",ifile
    print "ofile",ofile
    print "basen",basename

def fixtime(n,t):
    try:
        (crap,ts,fnord)=n.split("-",3)
        return (float(ts)+int(t)/1000)
    except:
        return int(t)/1000

class MyObject(object):
    pass

class Reassemble(object):
    def __init__(self):
        raise Exception("undef")
    stat_line=0
    stat_filter=0
    def run(self,producer):
        for line in producer:
            res=self.filter(line)
            if res != None:
                self.stat_filter+=1
                zz=self.process(res)
                if zz != None:
                    for mo in zz:
                        self.consume(mo)
        self.end()
    def filter(self,line):
        self.stat_line+=1
        q=MyObject()
        q.typ,q.name,q.time,q.frequency,q.confidence,q.level,q.symbols,q.uldl,q.data=line.split(None,8)
        q.frequency=int(q.frequency)
        q.time=int(q.time)
        q.level=float(q.level)
        return q
    def end(self):
        print "Kept %d/%d (%3.1f%%) lines"%(self.stat_filter,self.stat_line,100.0*self.stat_filter/self.stat_line)

class ReassembleIRA(Reassemble):
    def __init__(self):
        pass
    def filter(self,line):
        q=super(ReassembleIRA,self).filter(line)
        if q.typ=="IRA:":
            p=re.compile('.*sat:(\d+) beam:(\d+) pos=\((.[0-9.]+)/(.[0-9.]+)\) alt=([-0-9]+) .* bc_sb:\d+ (.*)')
            m=p.match(q.data)
            if(not m):
                print >> sys.stderr, "Couldn't parse IRA: ",q.data
            else:
                q.sat=  int(m.group(1))
                q.beam= int(m.group(2))
                q.posx= m.group(3)
                q.posy= m.group(4)
                q.alt=  int(m.group(5))
                p=re.compile('PAGE\(tmsi:([0-9a-f]+) msc_id:([0-9]+)\)')
                q.pages=p.findall(m.group(6))
                return q
    def process(self,q):
        for x in q.pages:
            return ["%02d %02d %s %s %03d : %s %s"%(q.sat,q.beam,q.posx,q.posy,q.alt,x[0],x[1])]
    def consume(self,q):
        print >> outfile, q

class ReassembleMSG(Reassemble):
    def __init__(self):
        pass
    def filter(self,line):
        q=super(ReassembleMSG,self).filter(line)
        if q.typ == "MSG:":
            #ric:0098049 fmt:05 seq:43 1010010000 1/1 oNEZCOuxvM3PuiQHujzQYd5n0Q8ra0wfMG2WnnhoxAnunT9xzIBSkXyvNP[3]     +11111
            p=re.compile('.* ric:(\d+) fmt:(\d+) seq:(\d+) [01]+ (\d)/(\d) csum:([0-9a-f][0-9a-f]) msg:([0-9a-f]+)\.([01]*) ')
            m=p.match(q.data)
            if(not m):
                print >> sys.stderr, "Couldn't parse MSG: ",q.data
            else:
                q.msg_ric=     int(m.group(1))
                q.fmt=         int(m.group(2))
                q.msg_seq=     int(m.group(3))
                q.msg_ctr=     int(m.group(4))
                q.msg_ctr_max= int(m.group(5))
                q.msg_checksum=int(m.group(6),16)
                q.msg_hex=         m.group(7)
                q.msg_brest=       m.group(8)
                q.time=        fixtime(q.name,q.time)


                q.msg_msgdata = ''.join(["{0:08b}".format(int(q.msg_hex[i:i+2], 16)) for i in range(0, len(q.msg_hex), 2)])
                q.msg_msgdata+=q.msg_brest

                # convert to 7bit thingies 
                m=re.compile('(\d{7})').findall(q.msg_msgdata)
                q.msg_ascii=""
                q.msg=[]
                for (group) in m:
                    character = int(group, 2)
                    q.msg.append(character)
                    if(character<32 or character==127):
                        q.msg_ascii+="[%d]"%character
                    else:
                        q.msg_ascii+=chr(character)
                if len(q.msg_msgdata)%7:
                    q.msg_rest=q.msg_msgdata[-(len(q.msg_msgdata)%7):]
                else:
                    q.msg_rest=""
                return q
    buf={}
    ricseq={}
    wrapmargin=10
    def process(self,m):
        # msg_seq wraps around after 61, detect it, and fix it.
        if m.msg_ric in self.ricseq:
            if (m.msg_seq + self.wrapmargin) < self.ricseq[m.msg_ric][1]: # seq wrapped around
                self.ricseq[m.msg_ric][0]+=62
            if (m.msg_seq + self.wrapmargin - 62) > self.ricseq[m.msg_ric][1]: # "wrapped back" (out-of-order old message)
                self.ricseq[m.msg_ric][0]-=62
        else:
            self.ricseq[m.msg_ric]=[0,0]
        self.ricseq[m.msg_ric][1]=m.msg_seq
        id="%07d %04d"%(m.msg_ric,(m.msg_seq+self.ricseq[m.msg_ric][0]))
        ts=m.time
        if id in self.buf:
            if self.buf[id].msg_checksum != m.msg_checksum:
                print "Whoa! Checksum changed? Message %s (1: @%d checksum %d/2: @%d checksum %d)"%(id,self.buf[id].time,self.buf[id].msg_checksum,m.time,m.msg_checksum)
                # "Wrap around" to not miss the changed packet.
                self.ricseq[m.msg_ric][0]+=62
                id="%07d %04d"%(m.msg_ric,(m.msg_seq+self.ricseq[m.msg_ric][0]))
                m.msgs=['[MISSING]']*3
                self.buf[id]=m
        else:
            m.msgs=['[MISSING]']*3
            self.buf[id]=m
        self.buf[id].msgs[m.msg_ctr]=m.msg_ascii

    def messagechecksum(self,msg):
        csum=0
        for x in msg:
            csum=(csum+ord(x))%128
        return (~csum)%128

    def consume(self,q):
        print "consume()"
        pass

    def end(self): # XXX should be rewritten to consume
        for b in sorted(self.buf, key=lambda x: self.buf[x].time):
            msg="".join(self.buf[b].msgs[:1+self.buf[b].msg_ctr_max])
            msg=re.sub("(\[3\])+$","",msg) # XXX: should be done differently
            cmsg=re.sub("\[10\]","\n",msg) # XXX: should be done differently
            csum=self.messagechecksum(cmsg)
            str="Message %s @%s (len:%d)"%(b,datetime.datetime.fromtimestamp(self.buf[b].time).strftime("%Y-%m-%dT%H:%M:%S"),self.buf[b].msg_ctr_max)
            str+= " %3d"%self.buf[b].msg_checksum
            str+= (" fail"," OK  ")[self.buf[b].msg_checksum == csum]
            str+= ": %s"%(msg)
            print >> outfile, str

zx=None
if False:
    pass
elif mode == "page":
    zx=ReassembleIRA()
elif mode == "msg":
    zx=ReassembleMSG()

zx.run(fileinput.input(ifile))
