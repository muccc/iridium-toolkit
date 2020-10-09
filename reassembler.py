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
import socket
from copy import deepcopy

verbose = False
ifile= None
ofile= None
mode= "undef"
base_freq=1616e6
channel_width=41667
args={}

options, remainder = getopt.getopt(sys.argv[1:], 'vhi:o:m:sa:', [
                                                         'verbose',
                                                         'help',
                                                         'input=',
                                                         'output=',
                                                         'mode=',
                                                         'state',
                                                         'args=',
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
    elif opt in ('-a', '--args'):
        for a in arg.split(","):
            args[a]=True
    elif opt in ('-h', '--help'):
        print >> sys.stderr, "Usage:"
        print >> sys.stderr, "\t",os.path.basename(sys.argv[0]),"[-v] [--input foo.parsed] --mode [ida|lap|sbd|page|msg|sat] [--output foo.parsed]"
        exit(1)
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

state=None
if 'state' in args:
    import pickle
    statefile="%s.state" % (mode)
    try:
        with open(statefile) as f:
            state=pickle.load(f)
    except (IOError, EOFError):
        pass

if verbose:
    print "ifile",ifile
    print "ofile",ofile
    print "basen",basename

class MyObject(object):
    def fixtime(self):
        if (self.name.startswith("j")):
            return float(self.time)
        try:
            return (float(self.starttime)+float(self.time)/1000)
        except AttributeError:
            return float(self.time)/1000
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
        try:
            q=MyObject()
            q.typ,q.name,q.time,q.frequency,q.confidence,q.level,q.symbols,q.uldl,q.data=line.split(None,8)
            if "|" in q.frequency:
                chan, off=q.frequency.split('|')
                q.frequency=base_freq+channel_width*int(chan)+int(off)
            else:
                q.frequency=int(q.frequency)
            q.starttime, _, q.attr = q.name[1+q.name.index('-'):].partition('-')
            q.confidence=int(q.confidence.strip("%"))
            q.time=float(q.time)
            q.level=float(q.level)
            return q
        except ValueError:
            print >> sys.stderr, "Couldn't parse input line: ",line,
            return None

    def end(self):
        print "Kept %d/%d (%3.1f%%) lines"%(self.stat_filter,self.stat_line,100.0*self.stat_filter/self.stat_line)

class StatsPKT(Reassemble):
    intvl=600
    timeslot=None
    default=None
    stats={}
    first=True
    loaded=False

    def __init__(self):
        if state is not None:
            (self.timeslot,self.stats)=state
            self.loaded=True
            self.first=False
        self.default={}
        for k in ['UL', 'DL']:
            self.default[k]={}
            for x in ['IBC', 'IDA', 'IIP', 'IIQ', 'IIR', 'IIU', 'IMS', 'IRA', 'IRI', 'ISY', 'ITL', 'IU3', 'I36', 'I38', 'MSG', 'VDA', 'VO6', 'VOC', 'VOD', 'MS3']:
                self.default[k][x]=0
        pass

    r1=re.compile('UW:0-LCW:0-FIX:0')

    def filter(self,line):
        q=super(StatsPKT,self).filter(line)

        if q==None: return None
        if q.typ[3]!=":": return None
        if q.typ=="RAW:": return None
        if q.typ=="IME:": return None
        if 'perfect' in args:
            m=self.r1.match(q.attr)
            if not m: return None

        return q

    def process(self,q):
        globaltime=q.fixtime()
        maptime=globaltime-(globaltime%self.intvl)
        typ=q.typ[0:3]
        rv=None

        if maptime > self.timeslot:
            # dump last time interval
            if self.loaded:
                print >> sys.stderr, "# Statefile (%s) not relevant to current file: %s"%(self.timeslot,maptime)
                sys.exit(1)
            if self.timeslot is not None:
                if self.first:
                    print >> sys.stderr, "# First period may be incomplete, skipping."
                    self.first=False
                    rv=[[self.timeslot,self.stats,True]]
                else:
                    rv=[[self.timeslot,self.stats,False]]
            # reset for next slot
            self.timeslot=maptime
            self.stats=deepcopy(self.default)

        self.loaded=False

        if maptime == self.timeslot:
            if typ not in self.stats['UL']:
                print >> sys.stderr, "Unexpected frame %s found @ %s"%(typ,globaltime)
                pass
            self.stats[q.uldl][typ]+=1
        else:
            print >> sys.stderr, "Time ordering violation: %f is before %f"%(globaltime,self.timeslot)
            sys.exit(1)
        return rv

    def printstats(self, timeslot, stats, skip=False):
        ts=timeslot+self.intvl
        comment=''
        if skip:
            comment='#!'
            print >>sys.stderr, "#!@ %s L:"%(datetime.datetime.fromtimestamp(ts))
        else:
            print >>sys.stderr, "# @ %s L:"%(datetime.datetime.fromtimestamp(ts))
        for k in stats:
            for t in stats[k]:
                print "%siridium.parsed.%s.%s %7d %8d"%(comment,k,t,stats[k][t],ts)
        sys.stdout.flush()

    def consume(self,to):
        (ts,stats,skip)=to
        self.printstats(ts, stats, skip=skip)

    def end(self):
        if 'state' in args:
            with open(statefile,'w') as f:
                state=pickle.dump([self.timeslot,self.stats],f)

        self.printstats(self.timeslot, self.stats, skip=True)

class ReassemblePPM(Reassemble):
    qqq=None
    def __init__(self):
        pass

    r1=re.compile('.* slot:(\d)')
    r2=re.compile('.* time:([0-9:T-]+(\.\d+)?)Z')

    def filter(self,line):
        q=super(ReassemblePPM,self).filter(line)
        if q==None: return None
        if q.typ!="IBC:": return None
        if q.confidence<95: return None


        m=self.r1.match(q.data)
        if not m: return
        q.slot=int(m.group(1))

        m=self.r2.match(q.data)
        if not m: return
        if m.group(2):
            q.itime = datetime.datetime.strptime(m.group(1), '%Y-%m-%dT%H:%M:%S.%f')
        else:
            q.itime = datetime.datetime.strptime(m.group(1), '%Y-%m-%dT%H:%M:%S')
        return q

    def process(self,q):
        q.globaltime=q.fixtime()
        q.uxtime=datetime.datetime.utcfromtimestamp(q.globaltime)

        # correct for slot
        q.itime+=datetime.timedelta(seconds=q.slot*(3 * float(8.28 + 0.1))/1000)

        q.timediff=q.uxtime-q.itime # missing correction for sat travel time

        return [[q.timediff.total_seconds(),q.itime,q.starttime]]

    ini=None
    def consume(self, data):
        if self.ini is None:
            self.ini=[data]
            self.fin=[data]
            self.idx=0
        if data[2]!=self.ini[self.idx][2]:
            self.idx += 1
            self.ini.append(data)
            self.fin.append(data)
        self.fin[-1]=data

    def end(self):
        alltime=0
        delta=0
        for ppms in range(1+self.idx):
            td=(self.fin[ppms][1]-self.ini[ppms][1]).total_seconds()
            toff=(self.fin[ppms][0]-self.ini[ppms][0])
            ppm=toff/td*1000000
            if False:
                print "Blob %d:"%ppms
                print "- Start time  : %s"%(self.ini[ppms][1])
                print "- End   time  : %s"%(self.fin[ppms][1])
                print "- Runtime     : %.2fh"%(td/60/60)
                print "- PPM         : %.3f"%(ppm)
            alltime += td
            delta += toff
        print "rec.ppm %.3f"%(delta/alltime*1000000)

class ReassembleIDA(Reassemble):
    def __init__(self):
        pass
    def filter(self,line):
        q=super(ReassembleIDA,self).filter(line)
        if q==None: return None
        if q.typ=="IDA:":
            q.time=q.fixtime()
            qqq=re.compile('.* CRC:OK')
            if not qqq.match(q.data):
                return
            # 0010 0 ctr=000 000 len=02 0:0000 [06.3a]                                                       7456/0000 CRC:OK 0000
            # 0000 0 ctr=000 000 len=00 0:0000 [8a.ed.09.b2.e0.a9.e7.0b.06.78.c9.49.0d.9b.60.6f.c0.07.fc.00.00.00.00]  ---    0000

            p=re.compile('.* cont=(\d) (\d) ctr=(\d+) \d+ len=(\d+) 0:.000 \[([0-9a-f.!]*)\]\s+..../.... CRC:OK')
            m=p.match(q.data)
            if(not m):
                print >> sys.stderr, "Couldn't parse IDA: ",q.data
            else:
                q.ul=        (q.uldl=='UL')
                q.f1=         m.group(1)
                q.f2=     int(m.group(2))
                q.ctr=    int(m.group(3),2)
                q.length= int(m.group(4))
                q.data=   m.group(5)
                q.cont=(q.f1=='1')
#                print "%s %s ctr:%02d %s"%(q.time,q.frequency,q.ctr,q.data)
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
            if verbose:
                print "dupe: ",m.time,"(",m.cont,m.ctr,")",m.data
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
                    if verbose:
                        print ">assembled: [%s] %s"%(",".join(["%s"%x for x in time+[m.time]]),dat)
                    data="".join([chr(int(x,16)) for x in re.split("[.!]",dat)])
                    return [[data,m.time,ul,m.level,freq]]
                self.stat_fragments+=1
                ok=True
                break
        if ok:
            pass
        elif m.ctr==0 and not m.cont:
            if verbose:
                print ">single: [%s] %s"%(m.time,m.data)
            data="".join([chr(int(x,16)) for x in re.split("[.!]",m.data)])
            return [[data,m.time,m.ul,m.level,m.frequency]]
        elif m.ctr==0 and m.cont: # New long packet
            self.stat_fragments+=1
            if verbose:
                print "initial: ",m.time,"(",m.cont,m.ctr,")",m.data
            self.buf.append([m.frequency,[m.time],m.ctr,m.data,m.cont,m.ul])
        elif m.ctr>0:
            self.stat_broken+=1
            self.stat_fragments+=1
            if verbose:
                print "orphan: ",m.time,"(",m.cont,m.ctr,")",m.data
            pass
        else:
             print "unknown: ",m.time,m.cont,m.ctr,m.data
        # expire packets
        for (idx,(freq,time,ctr,dat,cont,ul)) in enumerate(self.buf[:]):
            if time[-1]+1000<=m.time:
                self.stat_broken+=1
                del self.buf[idx]
                if verbose:
                    print "timeout:",time,"(",cont,ctr,")",dat
                data="".join([chr(int(x,16)) for x in re.split("[.!]",dat)])
                #could be put into assembled if long enough to be interesting?
                break
    def end(self):
        super(ReassembleIDA,self).end()
        print "%d valid packets assembled from %d fragments (1:%1.2f)."%(self.stat_ok,self.stat_fragments,((float)(self.stat_fragments)/self.stat_ok))
        print "%d/%d (%3.1f%%) broken fragments."%(self.stat_broken,self.stat_fragments,(100.0*self.stat_broken/self.stat_fragments))
        print "%d dupes removed."%(self.stat_dupes)
    def consume(self,q):
        (data,time,ul,level,freq)=q
        if ul:
            ul="UL"
        else:
            ul="DL"
        str=""
        for c in data:
            if( ord(c)>=32 and ord(c)<127):
                str+=c
            else:
                str+="."
        print >>outfile, "%15.6f %s %s | %s"%(time,ul," ".join("%02x"%ord(x) for x in data),str)

class ReassembleIDASBD(ReassembleIDA):
    def consume(self,q):
        (data,time,ul,_,_)=q
        if ord(data[0])!=0x76:
            return
        if len(data)<=2:
            return
        if ord(data[1])==5:
            return

        if ul:
            ul="UL"
        else:
            ul="DL"

        typ="%02x%02x"%(ord(data[0]),ord(data[1]))
        data=data[2:]

        prehdr=""
        if typ=="7608":
            # <26:44:9a:01:00:ba:85>
            # 1: always? 26
            # 2+3: sequence number (MTMSN)
            # 4: number of packets in message
            # 5: number of messages waiting to be delivered / backlog
            # 6+7: unknown / maybe MOMSN?
            prehdr=data[:7]
            data=data[7:]
            prehdr="<"+":".join("%02x"%ord(x) for x in prehdr)+">"

        # UL <50:0b:65>
        # 1: always 50 (nothing to send / message received)
        # 2+3: MOMSN mirror

        # <10:87:01>
        # 1: always 10 (message follows)
        # 2: length in bytes of message
        # 3: number of packet
        hdr=data[:3]
        data=data[3:]

        # skip empty messages
        if len(data)==0: return

        hdr=":".join("%02x"%ord(x) for x in hdr)

        str=""
        for c in data:
            if( ord(c)>=32 and ord(c)<127):
                str+=c
            elif ord(c)>127+32 and ord(c)<255:
                str+=chr(ord(c)-128)
            else:
                str+="."

        append="| "+" ".join("%02x"%ord(x) for x in data)
#        append=""

        print >>outfile, "%s %s [%s] {%02x} %-22s %-10s %-200s %s"%(datetime.datetime.fromtimestamp(time).strftime("%Y-%m-%dT%H:%M:%S"),ul,typ,len(data),prehdr,"<"+hdr+">",str,append)

class ReassembleIDALAP(ReassembleIDA):
    first=True
    sock = None
    def gsmwrap(self,q):
        (data,time,ul,level,freq)=q
        lapdm=data
        try:
            olvl=int(10*math.log(level,10))
        except:
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
        #        uint8_t sub_type;       /* Type of burst/channel, see above */    7
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

        (data,_,ul,_,_)=q
        if ord(data[0])&0xf==6 or ord(data[0])&0xf==8 or (ord(data[0])>>8)==7:
            return
        if len(data)==1:
            return
        pkt=self.gsmwrap(q)
        self.sock.sendto(pkt, ("127.0.0.1", 4729)) # 4729 == GSMTAP

        if verbose:
            if ul:
                ul="UL"
            else:
                ul="DL"
            print "%15.6f %.3f %s %s"%(time,level,ul,".".join("%02x"%ord(x) for x in data))

class ReassembleIDALAPPCAP(ReassembleIDALAP):
    first=True
    outfile=None
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
        if ord(data[0])&0xf==6 or ord(data[0])&0xf==8 or (ord(data[0])>>8)==7:
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

        pcap=struct.pack("<IIII",time,1000000*(time%1),len(eth),len(eth))+eth
        outfile.write(pcap)

class ReassembleIRA(Reassemble):
    def __init__(self):
        pass
    def filter(self,line):
        q=super(ReassembleIRA,self).filter(line)
        if q==None: return None
        if q.typ=="IRA:":
            p=re.compile('.*sat:(\d+) beam:(\d+) pos=\((.[0-9.]+)/(.[0-9.]+)\) alt=([-0-9]+) .* bc_sb:\d+ (.*)')
            m=p.match(q.data)
            if(not m):
                print >> sys.stderr, "Couldn't parse IRA: ",q.data
            else:
                q.sat=  int(m.group(1))
                q.beam= int(m.group(2))
                q.lat=float(m.group(3))
                q.lon=float(m.group(4))
                q.alt=  int(m.group(5))
                p=re.compile('PAGE\(tmsi:([0-9a-f]+) msc_id:([0-9]+)\)')
                q.pages=p.findall(m.group(6))
                return q
    def process(self,q):
        for x in q.pages:
            return ["%02d %02d %s %s %03d : %s %s"%(q.sat,q.beam,q.lat,q.lon,q.alt,x[0],x[1])]
    def consume(self,q):
        print >> outfile, q

class ReassembleMSG(Reassemble):
    def __init__(self):
        pass
    def filter(self,line):
        q=super(ReassembleMSG,self).filter(line)
        if q == None: return None
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
                q.time=        q.fixtime()


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

validargs=()
zx=None
if False:
    pass
if mode == "ida":
    zx=ReassembleIDA()
if mode == "gsmtap":
    zx=ReassembleIDALAP()
elif mode == "lap":
    if outfile == sys.stdout: # Force file, since it's binary
        ofile="%s.%s" % (basename, "pcap")
        outfile=open(ofile,"w")
    zx=ReassembleIDALAPPCAP()
if mode == "sbd":
    zx=ReassembleIDASBD()
elif mode == "page":
    zx=ReassembleIRA()
elif mode == "msg":
    zx=ReassembleMSG()
elif mode == "stats":
    validargs=('perfect','state')
    zx=StatsPKT()
elif mode == "ppm":
    zx=ReassemblePPM()

for x in args.keys():
    if x not in validargs:
        raise Exception("unknown -a option: "+x)

zx.run(fileinput.input(ifile))
