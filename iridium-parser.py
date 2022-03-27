#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# vim: set ts=4 sw=4 tw=0 et pm=:

import os
import sys
import re
import fileinput
import getopt
import datetime
import time
import collections.abc

import bitsparser

options, remainder = getopt.getopt(sys.argv[1:], 'vgi:o:pes', [
                                                         'verbose',
                                                         'good',
                                                         'uw-ec',
                                                         'harder',
                                                         'confidence=',
                                                         'input=',
                                                         'output=',
                                                         'perfect',
                                                         'disable-freqclass',
                                                         'errorfree',
                                                         'interesting',
                                                         'satclass',
                                                         'plot=',
                                                         'filter=',
                                                         'voice-dump=',
                                                         'format=',
                                                         'errorfile=',
                                                         'errorstats',
                                                         'forcetype=',
                                                         'channelize',
                                                         'sigmf-annotate=',
                                                         'stats',
                                                         ])

verbose = False
perfect = False
errorfree = False
interesting = False
good = False
dosatclass = False
input= "raw"
output= "line"
ofmt= None
linefilter={ 'type': 'All', 'attr': None, 'check': None }
plotargs=["time", "frequency"]
vdumpfile=None
errorfile=None
errorstats=None
sigmffile=None
do_stats=False

for opt, arg in options:
    if opt in ['-v', '--verbose']:
        bitsparser.verbose = True
    elif opt in ['-g','--good']:
        good = True
        min_confidence=90
    elif opt in ['--uw-ec']:
        bitsparser.uwec = True
    elif opt in ['--harder']:
        bitsparser.harder = True
    elif opt in ['--confidence']:
        good = True
        min_confidence=int(arg)
    elif opt in ['--interesting']:
        interesting = True
    elif opt in ['-p', '--perfect']:
        bitsparser.perfect = True
        perfect = True
    elif opt in ['--disable-freqclass']:
        bitsparser.freqclass = False
    elif opt in ['-e', '--errorfree']:
        errorfree = True
    elif opt in ['-s', '--satclass']:
        dosatclass = True
    elif opt in ['--plot']:
        plotargs=arg.split(',')
    elif opt in ['--filter']:
        linefilter['type']=arg
        if ',' in linefilter['type']:
            (linefilter['type'],linefilter['check'])=linefilter['type'].split(',',2)
        if '+' in linefilter['type']:
            (linefilter['type'],linefilter['attr'])=linefilter['type'].split('+')
        bitsparser.linefilter=linefilter
    elif opt in ['--voice-dump']:
        vdumpfile=arg
    elif opt in ['-i', '--input']:
        input=arg
    elif opt in ['-o', '--output']:
        output=arg
    elif opt in ['--errorfile']:
        errorfile=arg
        bitsparser.errorfile=arg
    elif opt in ['--errorstats']:
        errorstats={}
    elif opt in ['--forcetype']:
        bitsparser.forcetype=arg
    elif opt in ['--channelize']:
        bitsparser.channelize=True
    elif opt in ['--format']:
        ofmt=arg.split(',');
    elif opt in ['--sigmf-annotate']:
        sigmffile=arg
        output="sigmf"
    elif opt in ['--stats']:
        do_stats=True
    else:
        raise Exception("unknown argument?")

if input == "dump" or output == "dump":
    import pickle as pickle
    dumpfile="pickle.dump"

if output == "sigmf":
    import json

if output == "zmq":
    do_stats=True
    errorfree=True

if do_stats:
    import curses
    curses.setupterm(fd=sys.stderr.fileno())
    statsfile=sys.stderr
    eol=(curses.tigetstr('el')+curses.tigetstr('cr')).decode("ascii")
    eolnl=(curses.tigetstr('el')+b'\n').decode("ascii")
    stats={}

sigmfjson=None
sigmfout=None
if sigmffile is not None:
    try:
        sigmfjson=json.load(open(sigmffile,'r'))
        sigmfjson.pop('annotations', None)
    except FileNotFoundError:
        print("WARN: no sigmf-meta source file. Using (probably-wrong) hardcoded defaults", file=sys.stderr)
        sigmfjson={
            "global":
                {"core:datatype": "cf32_le", "core:sample_rate": 10e6, "core:version": "0.0.1"},
            "captures": [
                {"core:sample_start": 0, "core:frequency": 1626000000}
            ]
        }
    sigmfout=open(sigmffile+'.tmp','w')
    print("{", file=sigmfout)
    for key in sigmfjson:
        print('"%s":'%key, file=sigmfout)
        json.dump(sigmfjson[key],sigmfout)
        print(',', file=sigmfout)
    print('"%s": ['%"annotations", file=sigmfout)

if sigmfout is None:
    sigmfout=sys.stdout

if dosatclass == True:
    import satclass
    satclass.init()

if (linefilter['type'] != 'All') and bitsparser.harder:
    raise Exception("--harder and --filter (except type=Any) can't be use at the same time")

if vdumpfile != None:
    vdumpfile=open(vdumpfile,"wb")

if errorfile != None:
    errorfile=open(errorfile,"w")

if output == "dump":
    file=open(dumpfile,"wb")

if output == "plot":
    import matplotlib.pyplot as plt
    import matplotlib.ticker as ticker
    xl=[]
    yl=[]
    cl=[]
    sl=[]

if output == "zmq":
    import zmq

    url = "tcp://127.0.0.1:4223"

    context = zmq.Context()
    socket = context.socket(zmq.XPUB)
    socket.setsockopt(zmq.XPUB_VERBOSE, True)
    socket.bind(url)

    stats['clients']=0
    def zmq_thread(socket, stats):
        try:
            while True:
                event = socket.recv()
                 # Event is one byte 0=unsub or 1=sub, followed by topic
                if event[0] == 1:
                    log("new subscriber for", event[1:])
                    stats['clients'] += 1
                elif event[0] == 0:
                    log("unsubscribed",event[1:])
                    stats['clients'] -= 1
        except zmq.error.ContextTerminated:
            pass

    def log(*msg):
        s=time.strftime("%Y-%m-%d %H:%M:%S",time.localtime())
        print("%s:"%s,*msg, end=eolnl, file=statsfile)

    from threading import Thread
    zthread = Thread(target = zmq_thread, args = [socket, stats], daemon= True, name='zmq')
    zthread.start()

def stats_thread(stats):
    ltime=time.time()
    lline=0
    stime=stats['start']
    stop=stats['stop']

    while not stop.wait(timeout=1.0):
        now=time.time()
        nowl=stats['in']
        td=now-stime
        s=time.strftime("%Y-%m-%d %H:%M:%S",time.localtime())
        ts="%02d:%02d:%02d"%(td/60/60,td/60%60,td%60)
        hdr="%s [%s]"%(s, ts)
        progress=""
        if 'files' in stats and stats['files']>1:
            progress+="%d/%d:"%(stats['fileno'],stats['files'])
        if 'size' in stats and stats['size']>0:
            pos=os.lseek(fileinput.fileno(),0,os.SEEK_CUR)
            progress+="%4.1f%%"%(100*pos/stats['size'])
            eta=stats['size']/(pos/td) - td
            te="%02d:%02d"%(eta/60%60,eta%60)
            if eta>60*60:
                te="%02d:"%(eta/60/60)+te
            progress+="/"+te
        if progress:
            hdr+=" [%s]"%progress
        else:
            hdr+=" l:%6d"%stats['in']
        if output=='zmq':
            hdr+=" %2d clients"%stats['clients']
        print (hdr, "[%.1f l/s] filtered:%3d%%"%((nowl-lline)/(now-ltime),100*(1-stats['out']/(stats['in'] or 1))), end=eol, file=statsfile)
        ltime=now
        lline=nowl
    if eol=='\r':
        print(file=of)

selected=[]

def openhook(filename, mode):
    ext = os.path.splitext(filename)[1]
    if ext == '.gz':
        import gzip
        return gzip.open(filename, 'rt')
    elif ext == '.bz2':
        import bz2
        return bz2.open(filename, 'rt')
    elif ext == '.xz':
        import lzma
        return lzma.open(filename, 'rt')
    else:
        return open(filename, 'rt')

def do_input(type):
    if type=="raw":
        if do_stats:
            stats['files']=len(remainder)
            stats['fileno']=0
        for line in fileinput.input(remainder, openhook=openhook):
            if do_stats:
                if fileinput.isfirstline():
                    stats['fileno']+=1
                    stat=os.fstat(fileinput.fileno())
                    stats['size']=stat.st_size
                stats['in']+=1
            if good:
                q=bitsparser.Message(line.strip())
                try:
                    if q.confidence<min_confidence:
                        continue
                except AttributeError:
                    continue
                perline(q.upgrade())
            else:
                perline(bitsparser.Message(line.strip()).upgrade())
    elif type=="dump":
        file=open(dumpfile,"rb")
        try:
            while True:
                q=pickle.load(file)
                perline(q)
        except EOFError:
            pass
    else:
        print("Unknown input mode.", file=sys.stderr)
        exit(1)

def perline(q):
    if dosatclass == True:
        sat=satclass.classify(q.frequency,q.globaltime)
        q.satno=int(sat.name)
    if interesting:
        if type(q).__name__ == "IridiumMessage" or type(q).__name__ == "IridiumECCMessage" or type(q).__name__ == "IridiumBCMessage" or type(q).__name__ == "Message" or type(q).__name__ == "IridiumSYMessage" or type(q).__name__ == "IridiumMSMessage" or q.error:
            return
        del q.bitstream_raw
        if("descrambled" in q.__dict__): del q.descrambled
        del q.descramble_extra
    if q.error:
        if isinstance(errorstats, collections.abc.Mapping):
            msg=q.error_msg[0]
            if(msg in errorstats):
                errorstats[msg]+=1
            else:
                errorstats[msg]=1
        if errorfile != None:
            print(q.line+" ERR:"+", ".join(q.error_msg), file=errorfile)
            return
    if perfect:
        if q.error or ("fixederrs" in q.__dict__ and q.fixederrs>0):
            return
        q.descramble_extra=""
    if errorfree:
        if q.error:
            return
        q.descramble_extra=""
    if linefilter['type']!="All" and type(q).__name__ != linefilter['type']:
        return
    if linefilter['attr'] and linefilter['attr'] not in q.__dict__:
        return
    if linefilter['check'] and not eval(linefilter['check']):
        return
    if do_stats:
        stats["out"]+=1
    if vdumpfile != None and type(q).__name__ == "IridiumVOMessage":
        if len(q.voice)!=312:
            raise Exception("illegal Voice frame length")
        for bits in slice(q.voice, 8):
            byte = int(bits[::-1],2)
            vdumpfile.write(chr(byte))
    if output == "err":
        if(q.error):
            selected.append(q)
    elif output == "sat":
        if not q.error:
            selected.append(q)
    elif output == "dump":
        pickle.dump(q,file,1)
    elif output == "plot":
        selected.append(q)
    elif output == "line":
        if (q.error):
            print(q.pretty()+" ERR:"+", ".join(q.error_msg))
        else:
            if not ofmt:
                print(q.pretty())
            else:
                print(" ".join([str(q.__dict__[x]) for x in ofmt]))
    elif output == "zmq":
        socket.send_string(q.pretty())
    elif output == "rxstats":
        print("RX","X",q.globaltime, q.frequency,"X","X", q.confidence, q.level, q.symbols, q.error, type(q).__name__)
    elif output == "sigmf":
        try:
            sr=sigmfjson['global']["core:sample_rate"]
            center=sigmfjson['captures'][0]["core:frequency"]
        except TypeError:
            sr=10e6
            center=1626000000
        SYMBOLS_PER_SECOND = 25000
        if q.error:
            desc=q.error_msg[0]
        elif "msgtype" in q.__dict__:
            desc=""
            if q.uplink:
                desc+="UL"
            else:
                desc+="DL"
            desc+="_"+q.msgtype
        else:
            desc=type(q).__name__
        print(json.dumps({
            "core:comment": "Frame #%d: "%int(q.id)+type(q).__name__,
            "core:description": desc+"#%d"%int(q.id),
            "core:freq_lower_edge": q.frequency-20e3,
            "core:freq_upper_edge": q.frequency+20e3,
            "core:sample_count": int(q.symbols * (sr/SYMBOLS_PER_SECOND)),
            "core:sample_start": int(q.timestamp * (sr/1000))
            }), end=",\n", file=sigmfout)
    else:
        print("Unknown output mode.", file=sys.stderr)
        exit(1)

def bitdiff(a, b):
    return sum(x != y for x, y in zip(a, b))

if do_stats:
    from threading import Thread, Event
    stats['start']=time.time()
    stats['in']=0
    stats['out']=0
    stats['stop']= Event()
    sthread = Thread(target = stats_thread, args = [stats], daemon= True, name= 'stats')
    sthread.start()

try:
    do_input(input)
except KeyboardInterrupt:
    pass

if do_stats:
    stats['stop'].set()
    sthread.join()

if output=='zmq':
    socket.close()
    context.term()

if sigmffile is not None:
    import os
    print("{}]}", file=sigmfout)
    sigmfout.close()
    os.rename(sigmffile,        sigmffile+".bak")
    os.rename(sigmffile+".tmp", sigmffile)

if output == "sat":
    print("SATs:")
    sats=[]
    for m in selected:
        f=m.frequency
        t=m.globalns/1e9
        no=-1
        for s in range(len(sats)):
            fdiff=(sats[s][0]-f)//(t+.000001-sats[s][1])
            if f<sats[s][0] and fdiff<250:
                no=s
        if no>-1:
            m.fdiff=(sats[no][0]-f)//(t-sats[no][1])
            sats[no][0]=f
            sats[no][1]=t
        else:
            no=len(sats)
            sats.append([f,t])
            m.fdiff=0
        m.satno=no
    for s in range(len(sats)):
        print("Sat: %03d"%s)
        for m in selected:
            if m.satno == s: print(m.pretty())

if isinstance(errorstats, collections.abc.Mapping):
    total=0
    for (msg,count) in sorted(errorstats.items()):
        total+=count
        print("%7d: %s"%(count, msg), file=sys.stderr)
    print("%7d: %s"%(total, "Total"), file=sys.stderr)

if output == "err":
    print("### ")
    print("### Error listing:")
    print("### ")
    sort={}
    for m in selected:
        msg=m.error_msg[0]
        if(msg in sort):
            sort[msg].append(m)
        else:
            sort[msg]=[m]
    for msg in sort:
        print(msg+":")
        for m in sort[msg]:
            print("- "+m.pretty())

def plotsats(plt, _s, _e):
    for ts in range(int(_s),int(_e),10):
        for v in satclass.timelist(ts):
            plt.scatter( x=v[0], y=v[1], c=int(v[2]), alpha=0.3, edgecolor="none", vmin=10, vmax=90)

if output == "plot":
    name="%s over %s"%(plotargs[1],plotargs[0])
    if len(plotargs)>2:
        name+=" with %s"%plotargs[2]
    filter=""
    if len(linefilter)>0 and linefilter['type']!="All":
        filter+="type==%s"%linefilter['type']
        name=("%s "%linefilter['type'])+name
    if linefilter['attr']:
        filter+=" containing %s"%linefilter['attr']
        name+=" having %s"%linefilter['attr']
    if linefilter['check']:
        x=linefilter['check']
        if x.startswith("q."):
            x=x[2:]
        filter+=" and %s"%x
        name+=" where %s"%x
    plt.suptitle(filter)
    plt.xlabel(plotargs[0])
    plt.ylabel(plotargs[1])
    if plotargs[0]=="time":
        plotargs[0]="globalns"
        def format_date(x, pos=None):
            return datetime.datetime.fromtimestamp(x/10**9).strftime('%Y-%m-%d %H:%M:%S')
        plt.gca().xaxis.set_major_formatter(ticker.FuncFormatter(format_date))
        plt.gcf().autofmt_xdate()

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
    plt.savefig(re.sub(r'[/ ]','_',name)+".png")
    plt.show()
