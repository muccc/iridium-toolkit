#!/usr/bin/env python

import sys
import fileinput
import getopt
import datetime
import re

verbose = False
ifmt= "line"
ofmt= "undef"

options, remainder = getopt.getopt(sys.argv[1:], 'vi:o:', [
                                                         'verbose',
                                                         'input=',
                                                         'output=',
                                                         ])

for opt, arg in options:
    if opt in ('-v', '--verbose'):
        verbose = True
    elif opt in ('-i', '--input'):
        ifmt=arg
    elif opt in ('-o', '--output'):
        ofmt=arg
    else:
        raise Exception("unknown argument?")

class Message(object):
    def __init__(self,line):
            self.typ,self.name,self.time,self.frequency,self.confidence,self.level,self.symbols,self.uldl,self.data=line.split(None,8)
    def upgrade(self):
#            return IridiumMessage(self).upgrade()
        return self
    def _pretty_header(self):
        return "%s %s %09d %010d %3d%% %.3f"%(self.typ,self.filename,self.time,self.frequency,self.confidence,self.level)
    def _pretty_trailer(self):
        return ""
    def pretty(self):
        str= "RAW: "+self._pretty_header()
        bs=self.bitstream_raw
        str+=self._pretty_trailer()
        return str

selected=[]

def do_input(type):
    if ifmt=="line":
        for line in fileinput.input(remainder):
            qqq=re.compile('Warning:')
            if qqq.match(line):
                print "Skip: ",line
                continue
#            try:
            perline(Message(line.strip()).upgrade())
#            except ValueError:
#                print >> sys.stderr, "Couldn't parse line",line
    else:
        print "Unknown input mode."
        exit(1)

def fixtime(n,t):
    try:
        (crap,ts,fnord)=n.split("-",3)
        return (float(ts)+int(t)/1000)
    except:
        return int(t)/1000

def perline(q):
    if False:
        pass
    elif ofmt == "page":
        if q.typ=="IRA:":
            p=re.compile('.*sat:(\d+) beam:(\d+) pos=\((.[0-9.]+)/(.[0-9.]+)\) alt=([-0-9]+) .* bch:\d+ (.*)')
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
                m=p.findall(m.group(6))
                for x in m:
                    print "%02d %02d %s %s %03d : %s %s"%(q.sat,q.beam,q.posx,q.posy,q.alt,x[0],x[1])

    elif ofmt == "msg":
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
                m=re.compile('(\d{7})').findall(q.msg_msgdata)
                q.msg_ascii=""
                for (group) in m:
                    character = int(group, 2)
                    if(character<32 or character==127):
                        q.msg_ascii+="[%d]"%character
                    else:
                        q.msg_ascii+=chr(character)
                if len(q.msg_msgdata)%7:
                    q.msg_rest=q.msg_msgdata[-(len(q.msg_msgdata)%7):]
                else:
                    q.msg_rest=""

                selected.append(q)
    else:
        print "Unknown output mode."
        exit(1)


def main():
    do_input(input)

    if ofmt == "msg":
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
            id="%07d %04d"%(m.msg_ric,(m.msg_seq+ricseq[m.msg_ric][0]))
            ts=m.time
            if id in buf:
                if buf[id].msg_checksum != m.msg_checksum:
                    print "Whoa! Checksum changed? Message %s (1: @%d checksum %d/2: @%d checksum %d)"%(id,buf[id].time,buf[id].msg_checksum,m.time,m.msg_checksum)
                    # "Wrap around" to not miss the changed packet.
                    ricseq[m.msg_ric][0]+=62
                    id="%07d %04d"%(m.msg_ric,(m.msg_seq+ricseq[m.msg_ric][0]))
                    m.msgs=['[MISSING]']*3
                    buf[id]=m
            else:
                m.msgs=['[MISSING]']*3
                buf[id]=m
            buf[id].msgs[m.msg_ctr]=m.msg_ascii

        def messagechecksum(msg):
            csum=0
            for x in msg:
                csum=(csum+ord(x))%128
            return (~csum)%128

        for b in sorted(buf, key=lambda x: buf[x].time):
            msg="".join(buf[b].msgs[:1+buf[b].msg_ctr_max])
            msg=re.sub("(\[3\])+$","",msg) # XXX: should be done differently
            cmsg=re.sub("\[10\]","\n",msg) # XXX: should be done differently
    #        csum=""
            csum=messagechecksum(cmsg)
            str="Message %s @%s (len:%d)"%(b,datetime.datetime.fromtimestamp(buf[b].time).strftime("%Y-%m-%dT%H:%M:%S"),buf[b].msg_ctr_max)
            str+= " %3d"%buf[b].msg_checksum
            str+= (" fail"," OK  ")[buf[b].msg_checksum == csum]
            str+= ": %s"%(msg)
            print str

if __name__ == '__main__':
    main()
