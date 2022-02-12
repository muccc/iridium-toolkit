#!/usr/bin/env python3
# vim: set ts=4 sw=4 tw=0 et pm=:

from __future__ import print_function
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
from util import fmt_iritime

verbose = False
ifile= None
ofile= None
mode= "undef"
base_freq=1616*10**6
channel_width=41667
args={}
do_stats=False

options, remainder = getopt.getopt(sys.argv[1:], 'vhi:o:m:sa:', [
                                                         'verbose',
                                                         'help',
                                                         'input=',
                                                         'output=',
                                                         'mode=',
                                                         'args=',
                                                         'stats',
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
    elif opt in ('-s', '--stats'):
        do_stats=True
        import curses
        curses.setupterm(fd=sys.stderr.fileno())
        eol=(curses.tigetstr('el')+curses.tigetstr('cr')).decode("ascii")
    elif opt in ('-a', '--args'):
        for a in arg.split(","):
            args[a]=True
    elif opt in ('-h', '--help'):
        print("Usage:", file=sys.stderr)
        print("\t",os.path.basename(sys.argv[0]),"[-v] [--input foo.parsed] --mode [ida|idapp|lap|sbd|acars|page|msg|stats-pkt|ppm|satmap] [--args option[,...]] [--output out.txt]", file=sys.stderr)
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
    basename=re.sub(r'\.[^.]*$','',ifile)
#    basename=os.path.basename(re.sub(r'\.[^.]*$','',ifile))

if ofile == None:
    ofile="/dev/stdout"
    outfile=sys.stdout
elif ofile == "" or ofile == "=":
    ofile="%s.%s" % (basename, mode)
    outfile=open(ofile,"w")
else:
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
    print("ifile",ifile)
    print("ofile",ofile)
    print("basen",basename)

class Zulu(datetime.tzinfo):
    def utcoffset(self, dt):
        return datetime.timedelta(0)
    def dst(self, dt):
        return datetime.timedelta(0)
    def tzname(self,dt):
         return "Z"

Z=Zulu()

pwarn=False

class MyObject(object):
    def enrich(self):
        if "|" in self.frequency:
            chan, off=self.frequency.split('|')
            self.frequency=base_freq+channel_width*int(chan)+int(off)
        else:
            self.frequency=int(self.frequency)

        if len(self.name) > 3 and self.name[1]=='-':
            self.ftype=self.name[0]
            self.starttime, _, self.attr = self.name[2:].partition('-')
        else:
            self.ftype = self.starttime = self.attr = ''

        self.confidence=int(self.confidence.strip("%"))
        self.mstime=float(self.mstime)

        if '|' in self.level:
            self.level, self.noise, self.snr = self.level.split('|')
            self.snr = float(self.snr)
            self.noise = float(self.noise)
            self.level=float(self.level)
        else:
            self.snr=None
            self.noise=None
            if float(self.level)==0:
                self.level+="1"
            try:
                self.level=math.log(float(self.level),10)*20
            except ValueError:
                print("Invalid signal level:",self.level, file=sys.stderr)
                self.level=0

        if self.ftype=='p':
            self.time=float(self.starttime)+self.mstime/1000
        elif self.ftype=='j': # deperec
            self.time=self.mstime
            self.timens=int(self.mstime*(10**9))
        else:
            try:
                # XXX: Does not handle really old time format.
                self.time=float(self.starttime)+self.mstime/1000
            except ValueError:
                self.time=self.mstime/1000

        if self.attr.startswith("e"):
            if self.attr != 'e000':
                self.perfect=False
            else:
                self.perfect=True
        else:
            if self.attr == 'UW:0-LCW:0-FIX:00':
                self.perfect=True
            else:
                self.perfect=False
            if 'perfect' in args:
                global pwarn
                if pwarn is False:
                    pwarn = True
                    print("'perfect' requested, but no EC info found", file=sys.stderr)

def ascii(data, dot=False, escape=False):
    str=""
    for c in data:
        if( c>=32 and c<127):
            str+=chr(c)
        else:
            if dot:
                str+="."
            elif escape:
                if c==0x0d:
                    str+='\\r'
                elif c==0x0a:
                    str+='\\n'
                else:
                    str+='\\x{%02x}'%c
            else:
                str+="[%02x]"%c
    return str

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
            q.typ,q.name,q.mstime,q.frequency,q.confidence,q.level,q.symbols,q.uldl,q.data=line.split(None,8)
            return q
        except ValueError:
            print("Couldn't parse input line: ",line, end=' ', file=sys.stderr)
            return None

    def end(self):
        if self.stat_line>0:
            print("Kept %d/%d (%3.1f%%) lines"%(self.stat_filter,self.stat_line,100.0*self.stat_filter/self.stat_line))
        else:
            print("No lines?")


class StatsSNR(Reassemble):
    def __init__(self):
        self.stats={}
        pass

    def filter(self,line):
        q=super().filter(line)

        if q==None: return None
        if q.typ[3]!=":": return None
        if q.typ=="RAW:": return None
        if q.typ=="IME:": return None

        q.enrich()

        if 'perfect' in args:
            if not q.perfect: return None

        return q

    def process(self,q):
        typ=q.typ[0:3]

        if typ not in self.stats:
            self.stats[typ]={}
            for x in ['cnt', 'ncnt', 'scnt', 'signal', 'snr', 'noise', 'confidence', 'symbols']:
                self.stats[typ][x]=0

        self.stats[typ]["cnt"]+=1
        if q.snr is not None:
            self.stats[typ]["snr"]+=pow(10,q.snr/20)
            self.stats[typ]["noise"]+=pow(10,q.noise/20)
            self.stats[typ]["ncnt"]+=1

        if q.level > 0: # Invalid signal level
            pass
        else:
            self.stats[typ]["signal"]+=pow(10,q.level/20)
            self.stats[typ]["scnt"]+=1

        self.stats[typ]["confidence"]+=q.confidence
        self.stats[typ]["symbols"]+=int(q.symbols)
        return None

    def consume(self,to):
        pass

    def end(self):
        totalc=0
        totalcs=0
        totalcn=0
        for t in self.stats:
            totalc+=self.stats[t]["cnt"]
            totalcs+=self.stats[t]["scnt"]
            totalcn+=self.stats[t]["ncnt"]
#        print "%d %s.%s"%(totalc,"total","cnt")

        if totalc == 0: return
        for x in self.stats["IDA"]:
            totalv=0
            for t in self.stats:
                if x == "ncnt": continue
                if x == "scnt": continue
                if x == "cnt":
#                    print "%d %s.%s"%(self.stats[t]["cnt"],"cnt",t)
                    continue
                totalv+=self.stats[t][x]
                # ignore packet types with less than 0.01% of total volume
                if float(self.stats[t]["cnt"])/totalc > 0.0001 and self.stats[t][x]!=0:
                    if x in ["signal"]:
                        if self.stats[t]["scnt"] > 0:
                            print("%f %s.%s"%(20*math.log(float(self.stats[t][x])/self.stats[t]["scnt"],10),x,t))
                    elif x in ["snr","noise"]:
                        if self.stats[t]["ncnt"] > 0:
                            print("%f %s.%s"%(20*math.log(float(self.stats[t][x])/self.stats[t]["ncnt"],10),x,t))
                    else:
                        print("%f %s.%s"%(float(self.stats[t][x])/self.stats[t]["cnt"],x,t))
            if totalv !=0:
                if x in ["signal"]:
                    if totalcs > 0:
                        print("%f %s.%s"%(20*math.log(float(totalv)/totalcs,10),"total",x))
                elif x in ["snr","noise"]:
                    if totalcn > 0:
                        print("%f %s.%s"%(20*math.log(float(totalv)/totalcn,10),"total",x))
                else:
                    print("%f %s.%s"%(float(totalv)/totalc,"total",x))

class LivePktStats(Reassemble):
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

    def filter(self,line):
        q=super().filter(line)

        if q==None: return None
        if q.typ[3]!=":": return None
        if q.typ=="RAW:": return None
        if q.typ=="IME:": return None

        q.enrich()

        if 'perfect' in args:
            if not q.perfect: return None

        return q

    def process(self,q):
        maptime=q.time-(q.time%self.intvl)
        typ=q.typ[0:3]
        rv=None

        if maptime > self.timeslot:
            # dump last time interval
            if self.loaded:
                print("# Statefile (%s) not relevant to current file: %s"%(self.timeslot,maptime), file=sys.stderr)
                sys.exit(1)
            if self.timeslot is not None:
                if self.first:
                    print("# First period may be incomplete, skipping.", file=sys.stderr)
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
                print("Unexpected frame %s found @ %s"%(typ,q.time), file=sys.stderr)
                pass
            self.stats[q.uldl][typ]+=1
        else:
            print("Time ordering violation: %f is before %f"%(q.time,self.timeslot), file=sys.stderr)
            sys.exit(1)
        return rv

    def printstats(self, timeslot, stats, skip=False):
        ts=timeslot+self.intvl
        comment=''
        if skip:
            comment='#!'
            print("#!@ %s L:"%(datetime.datetime.fromtimestamp(ts)), file=sys.stderr)
        else:
            print("# @ %s L:"%(datetime.datetime.fromtimestamp(ts)), file=sys.stderr)
        for k in stats:
            for t in stats[k]:
                print("%siridium.parsed.%s.%s %7d %8d"%(comment,k,t,stats[k][t],ts))
        sys.stdout.flush()

    def consume(self,to):
        (ts,stats,skip)=to
        self.printstats(ts, stats, skip=skip)

    def end(self):
        if 'state' in args:
            with open(statefile,'w') as f:
                state=pickle.dump([self.timeslot,self.stats],f)

        self.printstats(self.timeslot, self.stats, skip=True)

import json
class LiveMap(Reassemble):
    intvl=60
    exptime=60*8
    timeslot=-1

    def __init__(self):
        self.positions={}
        self.ground={}
        self.topic="IRA"
        pass

    r2=re.compile(r' *sat:(\d+) beam:(\d+) (?:xyz=\S+ )?pos=.([+-][0-9.]+)\/([+-][0-9.]+). alt=(-?\d+).*')

    def filter(self,line):
        q=super().filter(line)

        if q==None: return None
        if q.typ!="IRA:": return None

        q.enrich()

        if 'perfect' in args:
            if not q.perfect: return None

        return q

    def process(self,q):
        # Parse out IRA info
        m=self.r2.match(q.data)
        if not m: return None
        q.sat=  int(m.group(1))
        q.beam= int(m.group(2))
        q.lat=float(m.group(3))
        q.lon=float(m.group(4))
        q.alt=  int(m.group(5))

        rv=None
        maptime=q.time-(q.time%self.intvl)

        if maptime > self.timeslot:
            # expire
            for sat in self.positions:
                eidx=0
                for idx,el in enumerate(self.positions[sat]):
                    if el['time']+self.exptime < q.time:
                        eidx=idx+1
                    else:
                        break
                del self.positions[sat][:eidx]
            for sat in self.ground:
                eidx=0
                for idx,el in enumerate(self.ground[sat]):
                    if el['time']+self.exptime/2 < q.time:
                        eidx=idx+1
                    else:
                        break
                del self.ground[sat][:eidx]

            #cleanup
            for sat in list(self.positions.keys()):
                if len(self.positions[sat])==0:
                    del self.positions[sat]
            for sat in list(self.ground.keys()):
                if len(self.ground[sat])==0:
                    del self.ground[sat]

            # send to output
            if self.timeslot is not None:
                rv=[[self.timeslot, { "sats": deepcopy(self.positions), "beam": deepcopy(self.ground)}]]
            self.timeslot=maptime

        if q.sat not in self.positions:
            self.positions[q.sat]=[]

        if q.sat not in self.ground:
            self.ground[q.sat]=[]

        if q.alt>700 and q.alt<800: # Sat positions
            dupe=False
            if len(self.positions[q.sat])>0:
                lastpos=self.positions[q.sat][-1]
                if lastpos['lat']==q.lat and lastpos['lon']==q.lon:
                    dupe=True
            if not dupe:
                self.positions[q.sat].append({"lat": q.lat, "lon": q.lon, "alt": q.alt, "time": q.time})
        elif q.alt<100: # Ground positions
            self.ground[q.sat].append({"lat": q.lat, "lon": q.lon, "alt": q.alt, "beam": q.beam, "time": q.time})

        return rv

    def printstats(self, timeslot, stats):
        ts=timeslot+self.intvl
        if do_stats:
            sts=datetime.datetime.fromtimestamp(ts)
            sats=len(stats['sats'])
            ssats=", ".join([str(x) for x in sorted(stats['sats'])])
            beams=0
            for b in stats['beam']:
                beams+=len(set([x['beam'] for x in stats['beam'][b]]))
            print("%s: %d sats {%s}, %d beams"%(sts,sats,ssats,beams), end=eol, file=sys.stderr)
        else:
            print("# @ %s L:"%(datetime.datetime.fromtimestamp(ts)), file=sys.stderr)
        stats["time"]=ts
        with open("sats.json.new", "w") as f:
            print(json.dumps(stats, separators=(',', ':')), file=f)
        os.rename("sats.json.new", "sats.json")

    def consume(self,to):
        (ts,stats)=to
        self.printstats(ts, stats)

    def end(self):
        self.printstats(self.timeslot, {"sats": self.positions, "beam": self.ground} )

class ReassemblePPM(Reassemble):
    def __init__(self):
        self.idx=None
        pass

    r1=re.compile(r'.* slot:(\d)')
    r2=re.compile(r'.* time:([0-9:T-]+(\.\d+)?)Z')

    def filter(self,line):
        q=super().filter(line)
        if q==None: return None
        if q.typ!="IBC:": return None

        q.enrich()
        if q.confidence<95: return None

        if 'perfect' in args:
            if not q.perfect: return None

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
        q.uxtime=datetime.datetime.utcfromtimestamp(q.time)

        # correct for slot:
        # 1st vs. 4th slot is 3 * (downlink + guard)
        q.itime+=datetime.timedelta(seconds=q.slot*(3 * float(8.28 + 0.1))/1000)

        # correct to beginning of frame:
        # guard + simplex + guard + 4*(uplink + guard) + extra_guard
        q.itime+=datetime.timedelta(seconds=(1 + 20.32 + 1.24 + 4 * float(8.28 + 0.22) + 0.02)/1000)

        # correct to beginning of signal:
        # our timestamp is "the middle of the first symbol of the 12-symbol BPSK Iridium sync word"
        # so correct for 64 symbols preamble & one half symbol.
        q.itime+=datetime.timedelta(seconds=(64.5/25000))

        # no correction (yet?) for signal travel time: ~ 2.6ms-10ms (780-3000 km)

        return [[q.uxtime,q.itime,q.starttime]]

    ini=None
    def consume(self, data):
        tdelta=(data[0]-data[1]).total_seconds()
        if self.ini is None: # First PKT
            self.idx=0
            self.ini=[data]
            self.fin=[data]
            self.cur=data
            self.tmin=tdelta
            self.tmax=tdelta
        if data[2]!=self.ini[self.idx][2]: # New Recording
            self.idx += 1
            self.ini.append(data)
            self.fin.append(data)
            self.cur=data
        self.fin[-1]=data

        if tdelta < self.tmin:
            self.tmin=tdelta
        if tdelta > self.tmax:
            self.tmax=tdelta
        if 'tdelta' in args:
            print("tdelta %sZ %f"%(data[0].isoformat(),tdelta))

        # "interactive" statistics per INVTL(600)
        if (data[1]-self.cur[1]).total_seconds() > 600:
            (irun,toff,ppm)=self.onedelta(self.cur,data, verbose=False)
            if 'grafana' in args:
                print("iridium.live.ppm %.5f %d"%(ppm,(data[1]-datetime.datetime.fromtimestamp(0)).total_seconds()))
                sys.stdout.flush()
            else:
                print("@ %s: ppm: % 6.3f ds: % 8.5f "%(data[1],ppm,(data[1]-data[0]).total_seconds()))
            self.cur=data
        elif (data[1]-self.cur[1]).total_seconds() <0:
            self.cur=data

    def onedelta(self, start, end, verbose=False):
        irun=(end[1]-start[1]).total_seconds()
        urun=(end[0]-start[0]).total_seconds()
        toff=urun-irun
        if irun==0: return (0,0,0)
        ppm=toff/irun*1000000
        if verbose:
            print("Blob:")
            print("- Start Itime  : %s"%(start[1]))
            print("- End   Itime  : %s"%(end[1]))
            print("- Start Utime  : %s"%(start[0]))
            print("- End   Utime  : %s"%(end[0]))
            print("- Runtime      : %s"%(str(datetime.timedelta(seconds=int(irun)))))
            print("- PPM          : %.3f"%(ppm))
        return (irun,toff,ppm)

    def end(self):
        alltime=0
        delta=0
        if self.idx is None: return
        for ppms in range(1+self.idx):
            (irun,toff,ppm)=self.onedelta(self.ini[ppms],self.fin[ppms], verbose=True)
            alltime += irun
            delta += toff
        print("rec.tmin %f"%(self.tmin))
        print("rec.tmax %f"%(self.tmax))
        print("rec.ppm %.3f"%(delta/alltime*1000000))

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
            if verbose:
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
                    if verbose:
                        print(">assembled: [%s] %s"%(",".join(["%s"%x for x in time+[m.time]]),dat))
                    data=bytes().fromhex( dat.replace('.',' ').replace('!',' ') )
                    return [[data,m.time,ul,m.level,freq]]
                self.stat_fragments+=1
                ok=True
                break
        if ok:
            pass
        elif m.ctr==0 and not m.cont:
            if verbose:
                print(">single: [%s] %s"%(m.time,m.data))
            data=bytes().fromhex( m.data.replace('.',' ').replace('!',' ') )
            return [[data,m.time,m.ul,m.level,m.frequency]]
        elif m.ctr==0 and m.cont: # New long packet
            self.stat_fragments+=1
            if verbose:
                print("initial: ",m.time,"(",m.cont,m.ctr,")",m.data)
            self.buf.append([m.frequency,[m.time],m.ctr,m.data,m.cont,m.ul])
        elif m.ctr>0:
            self.stat_broken+=1
            self.stat_fragments+=1
            if verbose:
                print("orphan: ",m.time,"(",m.cont,m.ctr,")",m.data)
            pass
        else:
             print("unknown: ",m.time,m.cont,m.ctr,m.data)
        # expire packets
        for (idx,(freq,time,ctr,dat,cont,ul)) in enumerate(self.buf[:]):
            if time[-1]+1000<=m.time:
                self.stat_broken+=1
                del self.buf[idx]
                if verbose:
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
        str+=ascii(data,True)

        fbase=freq-base_freq
        fchan=int(fbase/channel_width)
        foff =fbase%channel_width
        freq_print="%3d|%05d"%(fchan,foff)

        print("%15.6f %s %s %s | %s"%(time,freq_print,ul,data.hex(" "),str), file=outfile)

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

def p_lai(lai):
    if lai[1]>>4 != 15 or len(lai)<4:
        return ("PARSE_FAIL",lai)
    else:
        str="MCC=%d%d%d"%(lai[0]&0xf,lai[0]>>4,lai[1]&0xf)
        str+="/MNC=%d%d"%(lai[2]>>4,lai[2]&0xf)
        str+="/LAC=%02x%02x"%(lai[3],lai[4])
        return (str,lai[5:])

def p_disc(disc):
    if disc[0] < 2 or disc[1]>>4 != 0xe:
        return ("PARSE_FAIL",disc)
    else:
        net=disc[1]&0xf
        cause=disc[2]&0x7f
        if net==0:
            str="Loc:user "
        elif net==2:
            str="Net:local"
        elif net==3:
            str="Net:trans"
        elif net==4:
            str="Net:remot"
        else:
            str="Net: %3d "%net

        if cause==17:
            str+=" Cause(17) User busy"
        elif cause==31:
            str+=" Cause(31) Normal, unspecified"
        elif cause==1:
            str+=" Cause(01) Unassigned number"
        elif cause==41:
            str+=" Cause(41) Temporary failure"
        elif cause==16:
            str+=" Cause(16) Normal call clearing"
        elif cause==57:
            str+=" Cause(57) Bearer cap. not authorized"
        elif cause==34:
            str+=" Cause(34) No channel available"
        elif cause==127:
            str+=" Cause(127) Interworking, unspecified"
        else:
            str+=" Cause: %d"%cause

        if (disc[2]>>7)==1 and disc[0]==3 and disc[3]==0x88:
            str+=" CCBS not poss."
            return (str,disc[4:])

        return (str,disc[3:])

class ReassembleIDAPP(ReassembleIDA):
    def consume(self,q):
        (data,time,ul,_,freq)=q
        if len(data)<=2:
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
        majmap={
            "03": "CC",
            "83": "CC(dest)",
            "05": "MM",
            "06": "06",
            "08": "08",
            "09": "SMS",
            "89": "SMS(dest)",
            "76": "SBD",
        }
        minmap={
            "0301": "Alerting",
            "0302": "Call Proceeding",
            "0303": "Progress",
            "0305": "Setup",
            "030f": "Connect Acknowledge",
            "0325": "Disconnect",
            "032a": "Release Complete",
            "032d": "Release",
            "0502": "Location Updating Accept",
            "0504": "Location Updating Reject",
            "0508": "Location Updating Request",
            "0512": "Authentication Request",
            "0514": "Authentication Response",
            "0518": "Identity request",
            "0519": "Identity response",
            "051a": "TMSI Reallocation Command",
            "0600": "Register/SBD:uplink",
            "0901": "CP-DATA",
            "0904": "CP-ACK",
            "0910": "CP-ERROR",
            "7605": "7605",
            "7608": "downlink #1",
            "7609": "downlink #2",
            "760a": "downlink #3+",
            "760c": "uplink initial",
            "760d": "uplink #2",
            "760e": "uplink #3",
        }

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

        if typ in ("0600","760c","760d","760e","7608","7609","760a"): # SBD
            prehdr=""
            hdr=""
            addlen=None

            if ul=='UL' and typ in ("0600"):
                #       0  1  2  3  4  5  6  7  8  9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28
                #      20:13:f0:10:02|IMEI                   |MOMSN|MC|_c|LEN|                   |TIME
                #      10:13:f0:10|TMSI?      |LAC? |LAC? |00:00:00|MC|                          |TIME
                hdr=data[:29]
                if len(hdr)<29:
                    # packet too short
                    print("ERR:short", file=outfile)
                    return

                data=data[29:]
                prehdr="<"+hdr[0:4].hex(":")

                if hdr[0]==0x20:
                    prehdr+=",%02x"%hdr[4]
                    bcd=["%x"%(x>>s&0xf) for x in hdr[5:13] for s in (0,4)]
                    prehdr+=","+bcd[0]+",imei:"+"".join(bcd[1:])
                    prehdr+=" MOMSN=%02x%02x"%(hdr[13],hdr[14])

                    addlen=hdr[17]
                elif hdr[0] in (0x10,0x40,0x50,0x70):
                    prehdr+=","+ "".join(["%02x"%x for x in hdr[4:8]])
                    prehdr+=",%02x%02x"%(hdr[8],hdr[9])
                    prehdr+=",%02x%02x"%(hdr[10],hdr[11])
                    prehdr+=",%02x%02x%02x"%(hdr[12],hdr[13],hdr[14])
                else:
                    prehdr+="[ERR:hdrtype]"
                    prehdr+=" "+hdr[4:15].hex(":")

                prehdr+=" msgct:%d"%hdr[15]
                prehdr+=" "+hdr[16:25].hex(":")

                ts=hdr[25:]
                tsi=int(ts.hex(), 16)
                _, strtime=fmt_iritime(tsi)
                prehdr+=" t:"+strtime
                prehdr+=">"
                hdr=""
            elif ul=='UL' and typ in ("760c","760d","760e"):
                if data[0]==0x50:
                    # <50:xx:xx> MTMSN echoback?
                    prehdr=data[:3]
                    data=data[3:]

                    prehdr="<"+prehdr.hex(":")+">"

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
                        prehdr=data[:7]
                        data=data[7:]
                        prehdr="<"+prehdr.hex(":")+">"
                    elif data[0]==0x20:
                        prehdr=data[:5]
                        data=data[5:]
                        prehdr="<"+prehdr.hex(":")+">"
                    else:
                        prehdr="<ERR:prehdr_type?>"

            else:
                prehdr="<ERR:nomatch>"
            print("%-22s %-10s "%(prehdr,hdr), end=' ', file=outfile)

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

            if addlen is not None and len(data)!=addlen:
                print("ERR:len(%d!=%d)"%(len(data),addlen), end=" ", file=outfile)

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

        elif typ=="032d": # CC Release
            if len(data)==4 and data[0]==8:
                data=data[1:]
                (rv,data)=p_disc(data)
                print("%s"%(rv), end=' ', file=outfile)
        elif typ=="032a": # CC Release Complete
            if len(data)==4 and data[0]==8:
                data=data[1:]
                (rv,data)=p_disc(data)
                print("%s"%(rv), end=' ', file=outfile)
        elif typ=="0325": # CC Disconnect
            (rv,data)=p_disc(data)
            print("%s"%(rv), end=' ', file=outfile)
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
        elif typ=="051a": # TMSI realloc.
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

        if len(data)>0:
            print(" ".join("%02x"%x for x in data), end=' ', file=outfile)
            print(" | %s"%ascii(data, dot=True), file=outfile)
        else:
            print("", file=outfile)
        return

verb2=False
class ReassembleIDASBD(ReassembleIDA):
    multi=[]
    sbd_short=0
    sbd_single=0
    sbd_cnt=0
    sbd_multi=0
    sbd_assembled=0
    sbd_broken=0

    def __init__(self):
        super().__init__()
        if 'debug' in args:
            global verb2
            verb2=True
            print("DEBUG ENABLED")

    def consume(self,q):
        zz=self.process_l2(q)
        if zz is not None:
            self.consume_l2(zz)

    def process_l2(self,q):
        (data,time,ul,_,_)=q # level, freq

        # check for SBD
        if data[0]==0x76:
            pass
        elif data[0]==0x06 and data[1]==0:
            pass
        else:
            return

        # corrupt / no data
        if len(data)<5:
            return

        # uninteresing (unclear)
        if data[0]==0x76 and data[1]==5:
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
            elif data[2] not in (0x10,0x20,0x40,0x50,0x70):
                print("WARN: SBD: HELLO pkt with unknown sub-type",data.hex(":"), file=sys.stderr)
                return

        self.sbd_cnt+=1
        typ="%02x%02x"%(data[0],data[1])
        data=data[2:]

        if typ=="0600":
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

            if ul and len(data)>=3 and data[0]==0x50:
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
                if verb2:
                    print("SBD: Pkt weird:", end=" ")
                    print("[%f] %2d/%2d %s <%s> <%s> %s"%(time, msgno, msgcnt, typ, prehdr.hex(":"), hdr.hex(":"), data.hex(":")))

        pkt=[typ, time, ul, prehdr, data]

        if verb2 and (msgno>1 or msgcnt>1):
            print("[%f] %2d/%2d %s <%s> <%s> %s"%(time, msgno, msgcnt, typ, prehdr.hex(":"), hdr.hex(":"), ascii(data, escape=True)))

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
                if msgno==no+1 and msgno < cnt and p[2] == ul: # could check if "typ" seems right.
                    self.multi[idx][2][4]+=data
                    self.multi[idx][0]+=1
                    ok=True
                    self.sbd_assembled+=1
                    if verb2:
                        print("Merged: %f s"%(time-t))
                    return None
                elif msgno==no+1 and msgno == cnt and p[2] == ul: # could check if "typ" seems right.
                    p[4]+=data
                    p[0]+=typ
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
            raise Exception("Shouldn't happen:"+str(msgno)+str(msgcnt)+str(pkt))

    def end(self):
        super().end()
        print("SBD: %d short & %d single messages. (%1.1f%%)."%(self.sbd_short,self.sbd_single,(100*(float)(self.sbd_short+self.sbd_single)/(self.sbd_cnt or 1))))
#        print("SBD: %d fragments"%(self.sbd_cnt))
        print("SBD: %d successful multi-pkt messages."%(self.sbd_multi))
        print("SBD: %d/%d fragments could not be assembled. (%1.1f%%)."%(self.sbd_broken,self.sbd_assembled,(100*(float)(self.sbd_broken)/(self.sbd_assembled or 1))))

    def consume_l2(self,q):
        (typ,time,ul,prehdr,data)=q

        if ul:
            ult="UL"
        else:
            ult="DL"

        print("%s %s <%-20s> %s"%(
                    datetime.datetime.fromtimestamp(time).strftime("%Y-%m-%dT%H:%M:%S"),
                    ult,prehdr.hex(":"),ascii(data, escape=True)), file=outfile)

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
        self.acars_crc16=crcmod.predefined.mkPredefinedCrcFun("kermit")

    def consume_l2(self,q):
        (typ,time,ul,prehdr,data)=q

        if len(data)==0: # Currently not interested :)
            return

        if data[0]!=1: # prelim. check for ACARS
            return

        def parity7(data):
            ok = True
            for c in data:
                bits=bin(c).count("1")
                if bits%2==0:
                    ok=False
            return ok, bytes([x&0x7f for x in data])

        self.errors=0

        csum=bytes()
        self.hdr=bytes()
        self.errors=[]
        data=data[1:]

        if data[-1]==0x7f:
            csum=data[-3:-1]
            data=data[:-3]

        if data[0]==0x3: # header of unknown meaning
            self.hdr=data[0:8]
            data=data[8:]

        if len(csum)>0:
            self.the_crc=self.acars_crc16(data+csum)
            if self.the_crc!=0:
                self.errors.append("CRC_FAIL")
        else:
            self.errors.append("CRC_MISSING")

        if len(data)<12:
            self.errors.append("SHORT")
            return

        ok, data=parity7(data)

        if not ok:
            self.errors.append("PARITY_FAIL")

        self.mode= data[ 0: 1]
        self.f_reg=data[ 1: 8] # address / aircraft registration
        self.ack=  data[ 8: 9]
        self.label=data[ 9:11]
        self.b_id =data[11:12] # block id

        data=data[12:]

        self.cont=False
        if data[-1] == 0x03: # ETX
            data=data[:-1]
        elif data[-1] == 0x17: # ETB
            self.cont=True
            data=data[:-1]
        else:
            self.errors.append("ETX incorrect")

        if len(data)>0 and data[0] == 2: # Additional content
            if data[0] == 2:
                if ul:
                    self.seqn=data[1:5] # sequence number
                    self.f_no=data[5:11] # flight number
                    self.txt=data[11:]
                else:
                    self.txt=data[1:]
            else:
                self.txt=data
                self.errors.append("STX missing")
        else:
            self.txt=bytes()

        if len(self.errors)>0 and not 'showerrs' in args:
            return

        # PRETTY-PRINT
        out=""

        out+=datetime.datetime.fromtimestamp(time).strftime("%Y-%m-%dT%H:%M:%S")
        out+=" "

        if len(self.hdr)>0:
            out+="[hdr: %s]"%self.hdr.hex()
        else:
            out+="%-23s"%""
        out+=" "

        if ul:
            out+="Dir:%s"%"UL"
        else:
            out+="Dir:%s"%"DL"
        out+=" "

        out+="Mode:%s"%self.mode.decode('latin-1')
        out+=" "

        f_reg=self.f_reg.decode('latin-1')
        while len(f_reg)>0 and f_reg[0]=='.':
            f_reg=f_reg[1:]
        out+="REG:%-7s"%f_reg
        out+=" "

        if self.ack[0]==21:
            out+="NAK  "
        else:
            out+="ACK:%s"%self.ack.decode('latin-1')
        out+=" "

        out+="Label:"
        if self.label== b'_\x7f':
            out+='_?'
        else:
            out+=ascii(self.label, escape=True)
        out+=" "

        if self.label in acars_labels:
            out+="(%s)"%acars_labels[self.label]
        else:
            out+="(?)"
        out+=" "

        out+="bID:%s"%(ascii(self.b_id, escape=True))
        out+=" "

        if ul:
            out+="SEQ: %s, FNO: %s"%(ascii(self.seqn, escape=True), ascii(self.f_no, escape=True))
            out+=" "

        if len(self.txt)>0:
            out+="[%s]"%ascii(self.txt, escape=True)

        if self.cont:
            out+=" CONT'd"

        if len(self.errors)>0:
            out+=" " + " ".join(self.errors)

        print(out, file=outfile)

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

        if verbose:
            if ul:
                ul="UL"
            else:
                ul="DL"
            print("%15.6f %.3f %s %s"%(time,level,ul,".".join("%02x"%ord(x) for x in data)))

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
        if 'all' in args:
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

class ReassembleIRA(Reassemble):
    def __init__(self):
        self.topic="IRA"
        pass
    def filter(self,line):
        q=super().filter(line)
        if q==None: return None
        if q.typ=="IRA:":
            p=re.compile(r'sat:(\d+) beam:(\d+) (?:(?:aps|xyz)=\(([+-]?[0-9]+),([+-]?[0-9]+),([+-]?[0-9]+)\) )?pos=\(([+-][0-9.]+)/([+-][0-9.]+)\) alt=(-?[0-9]+) .* bc_sb:\d+(?: (.*))?')
            m=p.search(q.data)
            if(not m):
                print("Couldn't parse IRA: ",q.data, end=' ', file=sys.stderr)
            else:
                q.sat=  int(m.group(1))
                q.beam= int(m.group(2))
                if m.group(3) is not None:
                    q.xyz= [4*int(m.group(3)), 4*int(m.group(4)), 4*int(m.group(5))]
                q.lat=float(m.group(6))
                q.lon=float(m.group(7))
                q.alt=  int(m.group(8))
                if m.group(9) is not None:
                    p=re.compile(r'PAGE\(tmsi:([0-9a-f]+) msc_id:([0-9]+)\)')
                    q.pages=p.findall(m.group(9))
                else: # Won't be printed, but just in case
                    q.pages=[]
                return q
    def process(self,q):
        for x in q.pages:
            return ["%03d %02d %6.2f %6.2f %03d : %s %s"%(q.sat,q.beam,q.lat,q.lon,q.alt,x[0],x[1])]
    def consume(self,q):
        print(q, file=outfile)


class InfoIRAMAP(ReassembleIRA):
    satlist=None
    sats={}
    ts=None
    first=True
    MAX_DIST=100 # Maximum distance in km for a match to be accepted
    stats_cnt=0
    stats_sum=0

    def __init__(self):
        filename="tracking/iridium-NEXT.txt"
        self.satlist = load.tle_file(filename)
        if verbose:
            print(("%i satellites loaded into list"%len(self.satlist)))
        self.epoc = self.satlist[0].epoch
        self.ts=load.timescale(builtin=True)

        if verbose:
            tnow = self.ts.utc(datetime.datetime.now(datetime.timezone.utc))
            days = tnow - self.epoc
            print('TLE file is %.2f days old'%days)

    def filter(self,line):
        q=super().filter(line)
        if q is None: return None
        if q.alt < 100: return None
        q.enrich()
        return q

    def find_closest_satellite(self, t, xyz, satlist):
        a = SatrecArray([sat.model for sat in satlist])
#        jd = np.array([t._utc_float()]) # skyfield 1.2x or so....
        jd = np.array([t.whole + t.tai_fraction - t._leap_seconds() / DAY_S])
        e, r, v = a.sgp4(jd, jd * 0.0)

        r = r[:,0,:]  # eliminate t axis since we only have one time
        v = v[:,0,:]
        r = r.T       # move x,y,z to top level like Skyfield expects
        v = v.T

        ut1 = np.array([t.ut1])
        r, v = TEME_to_ITRF(ut1, r, v)

        r2=np.array(xyz)
        r2.shape = 3, 1  # add extra dimension to stand in for time

#        sep_a = angle_between(r, r2)
        sep_d = length_of(r-r2)

        i = np.argmin(sep_d)

        closest_satellite = satlist[i]
#        closest_angle = sep_a[i] / tau * 360.0
        closest_distance = sep_d[i]

        if False:
            print("Position:",xyz,"at",t.utc_strftime(),":")
            for idx,s in enumerate(sorted(satlist, key=lambda sat: sat.name)):
                print("  %s: %8.2fkm %s"%(s.name,sep_d[idx],["","*"][i==idx]))

        return closest_satellite, closest_distance

    def process(self,q):
        time = datetime.datetime.utcfromtimestamp(q.time)
        time = time.replace(tzinfo=utc)
        t = self.ts.utc(time)
        if self.first:
            self.first=False
            days = t - self.epoc
            if abs(days)>3:
                print('WARNING: TLE relative age is %.2f days. Expect poor results.'%abs(days), file=sys.stderr)
            elif verbose:
                print('TLE relative age is %.2f days'%abs(days))

        if "xyz" not in q.__dict__: # Compat for old parsed files
            alt=int(q.alt)*1000
            sat= Topos(latitude_degrees=q.lat, longitude_degrees=q.lon, elevation_m=alt)
            q.xyz= sat.itrf_xyz().km

        (best,sep)=self.find_closest_satellite(t, q.xyz, self.satlist)

        q.name=best.name
        q.sep=sep

        return [q]

    def consume(self,q):
        if verbose:
#            print("%s: sat %02d beam %02d [%d %4.2f %4.2f %s] matched %-20s @ %5.2f°"%( datetime.datetime.utcfromtimestamp(q.time), q.sat,q.beam,q.time,q.lat,q.lon,q.alt,q.name,q.sep))
            print("%s: sat %02d beam %02d [%d %8.4f %8.4f %s] matched %-20s @ %5fkm"%( datetime.datetime.utcfromtimestamp(q.time), q.sat,q.beam,q.time,q.lat,q.lon,q.alt,q.name,q.sep))
        if q.sep > self.MAX_DIST:
            q.name="NONE"
        if not q.sat in self.sats:
            self.sats[q.sat]={}
        if not q.name in self.sats[q.sat]:
            self.sats[q.sat][q.name]=0
        self.sats[q.sat][q.name]+=1
        self.stats_cnt+=1
        self.stats_sum+=q.sep

    def end(self):
        for x in sorted(self.sats):
            sum=0
            for n in sorted(self.sats[x]):
                sum+=self.sats[x][n]

            for n in sorted(self.sats[x]):
                print("%03d seen: %5d times - matched to %-20s %5.1f%%"%(x,sum,n,self.sats[x][n]/float(sum)*100))

        print("%d matches. Avg distance: %5.2fkm"%(self.stats_cnt,self.stats_sum/self.stats_cnt))

class ReassembleMSG(Reassemble):
    def __init__(self):
        pass
    def filter(self,line):
        q=super().filter(line)
        if q == None: return None
        if q.typ == "MSG:":
            p=re.compile(r'.* ric:(\d+) fmt:(\d+) seq:(\d+) [01]+ (\d)/(\d) csum:([0-9a-f][0-9a-f]) msg:([0-9a-f]+)\.([01]*) ')
            m=p.match(q.data)
            if(not m):
                print("Couldn't parse MSG: ",q.data, file=sys.stderr)
            else:
                q.msg_ric=     int(m.group(1))
                q.fmt=         int(m.group(2))
                q.msg_seq=     int(m.group(3))
                q.msg_ctr=     int(m.group(4))
                q.msg_ctr_max= int(m.group(5))
                q.msg_checksum=int(m.group(6),16)
                q.msg_hex=         m.group(7)
                q.msg_brest=       m.group(8)
                q.enrich()


                q.msg_msgdata = ''.join(["{0:08b}".format(int(q.msg_hex[i:i+2], 16)) for i in range(0, len(q.msg_hex), 2)])
                q.msg_msgdata+=q.msg_brest

                # convert to 7bit thingies
                m=re.compile(r'(\d{7})').findall(q.msg_msgdata)
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
        if q.typ == "MS3:":
            p=re.compile(r'.* ric:(\d+) fmt:(\d+) seq:(\d+) [01]+ \d BCD: ([0-9a-f]+)')
            m=p.match(q.data)
            if(not m):
                print("Couldn't parse MS3: ",q.data, file=sys.stderr)
            else:
                q.msg_ric=     int(m.group(1))
                q.fmt=         int(m.group(2))
                q.msg_seq=     int(m.group(3))
                q.msg_ctr=     0
                q.msg_ctr_max= 0
                q.msg_checksum=-1
                q.msg_ascii=         m.group(4)
                q.enrich()
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
                print("Whoa! Checksum changed? Message %s (1: @%d checksum %d/2: @%d checksum %d)"%(id,self.buf[id].time,self.buf[id].msg_checksum,m.time,m.msg_checksum))
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
        print("consume()")
        pass

    def end(self): # XXX should be rewritten to consume
        for b in sorted(self.buf, key=lambda x: self.buf[x].time):
            msg="".join(self.buf[b].msgs[:1+self.buf[b].msg_ctr_max])
            str="Message %s @%s (len:%d)"%(b,datetime.datetime.fromtimestamp(self.buf[b].time).strftime("%Y-%m-%dT%H:%M:%S"),self.buf[b].msg_ctr_max)
            if self.buf[b].fmt==5:
                msg=re.sub(r"(\[3\])+$","",msg) # XXX: should be done differently
                cmsg=re.sub(r"\[10\]","\n",msg) # XXX: should be done differently
                csum=self.messagechecksum(cmsg)
                str+= " %3d"%self.buf[b].msg_checksum
                str+= (" fail"," OK  ")[self.buf[b].msg_checksum == csum]
            elif self.buf[b].fmt==3:
                msg=re.sub(r"c+$","",msg) # XXX: should be done differently
                str+= " BCD"
                str+= " OK  "
            str+= ": %s"%(msg)
            print(str, file=outfile)

validargs=()
zx=None

if mode == "ida":
    zx=ReassembleIDA()
elif mode == "idapp":
    zx=ReassembleIDAPP()
elif mode == "gsmtap":
    zx=ReassembleIDALAP()
elif mode == "lap":
    validargs=('all')
    if outfile == sys.stdout: # Force file, since it's binary
        ofile="%s.%s" % (basename, "pcap")
    outfile=open(ofile,"wb")
    zx=ReassembleIDALAPPCAP()
elif mode == "sbd":
    validargs=('perfect', 'debug')
    zx=ReassembleIDASBD()
elif mode == "acars":
    validargs=('perfect', 'showerrs')
    zx=ReassembleIDASBDACARS()
elif mode == "page":
    zx=ReassembleIRA()
elif mode == "satmap":
    from skyfield.api import load, utc, Topos
    from skyfield.sgp4lib import TEME_to_ITRF
    from sgp4.api import SatrecArray
    from skyfield.functions import angle_between, length_of
    from skyfield.constants import tau, DAY_S
    import numpy as np
    zx=InfoIRAMAP()
elif mode == "msg":
    zx=ReassembleMSG()
elif mode == "stats-snr":
    validargs=('perfect')
    zx=StatsSNR()
elif mode == "live-stats":
    validargs=('perfect','state')
    zx=LivePktStats()
elif mode == "live-map":
    validargs=('perfect')
    zx=LiveMap()
elif mode == "ppm":
    validargs=('perfect','grafana','tdelta')
    zx=ReassemblePPM()
else:
    print("Unknown mode selected", file=sys.stderr)
    sys.exit(1)

for x in args.keys():
    if x not in validargs:
        raise Exception("unknown -a option: "+x)

if ifile.startswith("zmq:"):
    try:
        topic=zx.topic
    except AttributeError:
        print("mode '%s' does not support streaming"%mode, file=sys.stderr)
        sys.exit(1)
    import zmq
    context = zmq.Context()
    socket = context.socket(zmq.SUB)
    socket.connect ("tcp://localhost:4223")
    socket.setsockopt(zmq.SUBSCRIBE, bytes(topic,"ascii"))
    try:
        zx.run(iter(socket.recv_string,""))
    except KeyboardInterrupt:
        print("")
else:
    zx.run(fileinput.input(ifile))
