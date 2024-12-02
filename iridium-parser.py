#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# vim: set ts=4 sw=4 tw=0 et pm=:

import os
import sys
import re
import fileinput
import datetime
import time
import argparse
import collections.abc

import bitsparser

parser = argparse.ArgumentParser(formatter_class=lambda prog: argparse.HelpFormatter(prog, max_help_position=27))

def parse_comma(arg):
    return arg.split(',')

def parse_filter(arg):
    linefilter = {'type': arg, 'attr': None, 'check': None}
    if ',' in linefilter['type']:
        (linefilter['type'], linefilter['check']) = linefilter['type'].split(',', 2)
    if '+' in linefilter['type']:
        (linefilter['type'], linefilter['attr']) = linefilter['type'].split('+')
    return linefilter


class NegateAction(argparse.Action):
    def __call__(self, parser, ns, values, option):
        setattr(ns, self.dest, option[2:4] != 'no')


filters = parser.add_argument_group('filters')

filters.add_argument("-g", "--good",      action="store_const", const=90, dest='min_confidence',
                     help="drop if confidence < 90")
filters.add_argument("--confidence", type=int, dest="min_confidence", metavar='MIN',
                     help="drop if confidence < %(metavar)s")
filters.add_argument("-p", "--perfect",   action="store_true",
                     help="drop lines which only parsed after applying error correction")
filters.add_argument("-e", "--errorfree", action="store_true",
                     help="drop lines that could not be parsed")
filters.add_argument("--filter", type=parse_filter, default='All', dest='linefilter', metavar='FILTER',
                     help="filter output by class and/or attribute")

parser.add_argument("-v", "--verbose",     action="store_true",
                    help="increase output verbosity")
parser.add_argument("--uw-ec",             action="store_true", dest='uwec',
                    help="enable error correction on unique word")
parser.add_argument("--harder",            action="store_true",
                    help="try harder to parse input")
parser.add_argument("--disable-freqclass", action="store_false", dest='freqclass',
                    help="turn frequency classificiation off")
parser.add_argument("-s", "--satclass",    action="store_true", dest='dosatclass',
                    help="enable sat classification")
parser.add_argument("--plot", type=parse_comma, dest='plotargs', default='time,frequency', metavar='ARGS'
                    )
parser.add_argument("-o", "--output", metavar='MODE', choices=['json', 'sigmf', 'zmq', 'line', 'plot', 'err', 'sat', 'file'],
                    help="output mode")
parser.add_argument("--errorfile", metavar='FILE',
                    help="divert unparsable lines to separate file")
parser.add_argument("--errorstats", action='store_const', const={},
                    help="output statistics about parse errors")
parser.add_argument("--forcetype", metavar='TYPE'
                    )
parser.add_argument("--channelize", action="store_true"
                    )
parser.add_argument("--format", type=parse_comma, dest='ofmt'
                    )
parser.add_argument("--sigmf-annotate", dest='sigmffile'
                    )
parser.add_argument("--stats", "--no-stats", action=NegateAction, dest="do_stats", nargs=0,
                    help='enable incremental statistics on stderr')
parser.add_argument("remainder", nargs='*',
                    help=argparse.SUPPRESS)

args = parser.parse_args()

# sanity check
if args.perfect and (args.harder or args.uwec):
    print("WARN: --perfect contradicts --harder or --uw-ec", file=sys.stderr)

# push options into bitsparser
bitsparser.set_opts(args)

# forced settings
if args.sigmffile:
    args.output="sigmf"

# try to be "intelligent" about defaults
if args.output is None:
    if len(args.remainder) == 0:
        args.output = 'line'
    elif sys.stdout.isatty():
        args.output = 'file'
    elif sys.stderr.isatty():
        args.output = 'line'
    else:
        args.output = 'file'

if args.do_stats is None:
    args.do_stats = True
    if not sys.stderr.isatty():
        args.do_stats = False
    elif args.output == 'line':
        args.do_stats = False

# optional dependencies
if args.output == "json":
    import json

if args.output == "sigmf":
    import json

if args.output == "zmq":
    args.errorfree=True

if args.do_stats:
    import curses
    statsfile=sys.stderr
    curses.setupterm(fd=statsfile.fileno())
    el=curses.tigetstr('el')
    cr=curses.tigetstr('cr') or b'\r'
    nl=curses.tigetstr('nl') or b'\n'
    if el is None:
        eol=  (nl).decode("ascii")
        eolnl=(nl).decode("ascii")
    else:
        eol=  (el+cr).decode("ascii")
        eolnl=(el+nl).decode("ascii")
    stats={}

sigmfjson=None
sigmfout=None
if args.sigmffile is not None:
    try:
        sigmfjson=json.load(open(args.sigmffile,'r'))
        sigmfjson.pop('annotations', None)
    except FileNotFoundError:
        print("WARN: no sigmf-meta source file. Using (probably-wrong) hardcoded defaults", file=sys.stderr)
        sigmfjson={
            "global": {
                    "core:datatype": "cf32_le",
                    "core:sample_rate": 10e6,
                    "core:version": "0.0.1",
                    "core:description": "iridium-extractor auto-generated metafile",
                    },
            "captures": [
                {"core:sample_start": 0, "core:frequency": 1622000000}
            ]
        }
    sigmfout=open(args.sigmffile+'.tmp','w')
    print("{", file=sigmfout)
    for key in sigmfjson:
        print('"%s":'%key, file=sigmfout)
        json.dump(sigmfjson[key],sigmfout)
        print(',', file=sigmfout)
    print('"%s": ['%"annotations", file=sigmfout)

if sigmfout is None:
    sigmfout=sys.stdout

if args.dosatclass is True:
    import satclass
    satclass.init()

if (args.linefilter['type'] != 'All') and args.harder:
    raise Exception("--harder and --filter (except type=Any) can't be use at the same time")

if args.errorfile is not None:
    args.errorfile=open(args.errorfile,"w")

if args.output == "plot":
    import matplotlib.pyplot as plt
    import matplotlib.ticker as ticker
    xl=[]
    yl=[]
    cl=[]
    sl=[]

poller = None

if args.output == "zmq":
    import zmq

    url = "tcp://127.0.0.1:4223"

    context = zmq.Context()
    socket = context.socket(zmq.XPUB)
    if args.do_stats:
        socket.setsockopt(zmq.XPUB_VERBOSE, True)
        stats['clients']=0
        poller = zmq.Poller()
        poller.register(socket, zmq.POLLIN)
    socket.bind(url)


    def zmq_xpub(poller, stats):
        try:
            while len(rv:=poller.poll(0))>0:
                event = rv[0][0].recv()
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

def stats_thread(stats):
    ltime=time.time()
    lline=0
    stime=stats['start']
    stop=stats['stop']

    once=True
    while once or not stop.wait(timeout=1.0):
        once=False
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
            try:
                pos=os.lseek(fileinput.fileno(),0,os.SEEK_CUR)
            except OSError:
                pos=0
            progress+="%4.1f%%"%(100*pos/stats['size'])
            eta=stats['size']/pos*td - td
            te="%02d:%02d"%(eta/60%60,eta%60)
            if eta>60*60:
                te="%02d:"%(eta/60/60)+te
            progress+="/"+te
        if progress:
            hdr+=" [%s]"%progress
        else:
            hdr+=" l:%6d"%stats['in']
        if args.output=='zmq':
            hdr+=" %2d clients"%stats['clients']
        print (hdr, "[%.1f l/s] filtered:%3d%%"%((nowl-lline)/(now-ltime),100*(1-stats['out']/(stats['in'] or 1))), end=eol, file=statsfile)
        ltime=now
        lline=nowl
    print (hdr, "[%.1f l/s] drop:%3d%%"%((nowl)/(now-stime),100*(1-stats['out']/(stats['in'] or 1))), end=eolnl, file=statsfile)

selected=[]

def openhook(filename, mode):
    base, ext = os.path.splitext(os.path.basename(filename))

    if base.endswith('.bits'):
        base = os.path.splitext(base)[0]
    if args.output == 'file':
        sys.stdout = open(f'{base}.parsed', 'wt')

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


def do_input():
    if True:
        if args.do_stats:
            stats['files']=len(args.remainder)
            stats['fileno']=0
        for line in fileinput.input(args.remainder, openhook=openhook):
            if args.do_stats:
                if fileinput.isfirstline():
                    stats['fileno']+=1
                    stat=os.fstat(fileinput.fileno())
                    stats['size']=stat.st_size
                stats['in']+=1
                if poller is not None and len(poller.poll(0))>0:
                    zmq_xpub(poller, stats)
            if args.min_confidence is not None:
                q=bitsparser.Message(line.strip())
                try:
                    if q.confidence<args.min_confidence:
                        continue
                except AttributeError:
                    continue
                perline(q.upgrade())
            else:
                perline(bitsparser.Message(line.strip()).upgrade())
    else:
        print("Unknown input mode.", file=sys.stderr)
        exit(1)

def perline(q):
    if args.dosatclass is True:
        sat=satclass.classify(q.frequency,q.globaltime)
        q.satno=int(sat.name)
    if q.error:
        if isinstance(args.errorstats, collections.abc.Mapping):
            msg=q.error_msg[0]
            if msg in args.errorstats:
                args.errorstats[msg]+=1
            else:
                args.errorstats[msg]=1
        if args.errorfile is not None:
            print(q.line+" ERR:"+", ".join(q.error_msg), file=args.errorfile)
            return
    if args.perfect:
        if q.error or ("fixederrs" in q.__dict__ and q.fixederrs>0):
            return
        q.descramble_extra=""
    if args.errorfree:
        if q.error:
            return
        q.descramble_extra=""
#    if linefilter['type']!="All" and type(q).__name__ != linefilter['type']:
    if args.linefilter['type']!="All" and not issubclass(type(q),globals()['bitsparser'].__dict__[args.linefilter['type']]):
        return
    if args.linefilter['attr'] and args.linefilter['attr'] not in q.__dict__:
        return
    if args.linefilter['check'] and not eval(args.linefilter['check']):
        return
    if args.do_stats:
        stats["out"]+=1
    if args.output == "err":
        if q.error:
            selected.append(q)
    elif args.output == "sat":
        if not q.error:
            selected.append(q)
    elif args.output == "plot":
        selected.append(q)
    elif args.output == "line" or args.output == "file":
        if q.error:
            print(q.pretty()+" ERR:"+", ".join(q.error_msg))
        else:
            if not args.ofmt:
                print(q.pretty())
            else:
                print(" ".join([str(q.__dict__[x]) for x in args.ofmt]))
    elif args.output == "zmq":
        socket.send_string(q.pretty())
    elif args.output == "json":
        if q.error: return
        for attr in ["parse_error", "error_msg", "descrambled", "bitstream_bch", "bitstream_raw", "rs6c", "rs6m", "rs8c", "rs8m", "idata", "payload_f", "payload_r", "descramble_extra", "swapped", "da_ta", "vdata", "header", "freq_print"]:
            if attr in q.__dict__:
                del q.__dict__[attr]
        q.type = type(q).__name__
        try:
            print(json.dumps(q.__dict__))
        except Exception as e:
            print("Couldn't serialize: ", q.__dict__, file=sys.stderr)
            raise e
    elif args.output == "sigmf":
        if q.parse_error:
            return
        try:
            sr=sigmfjson['global']["core:sample_rate"]
            center=sigmfjson['captures'][0]["core:frequency"]
        except TypeError:
            print("Failed to get sample_rate or frequency from sigmf.", file=sys.stderr)
            sr=10e7
            center=1622000000
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
            "core:description": desc,
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

if args.do_stats:
    from threading import Thread, Event
    stats['start']=time.time()
    stats['in']=0
    stats['out']=0
    stats['stop']= Event()
    sthread = Thread(target = stats_thread, args = [stats], daemon= True, name= 'stats')
    sthread.start()

try:
    do_input()
except KeyboardInterrupt:
    pass
except BrokenPipeError as e:
    print(e, file=sys.stderr, end=eolnl if args.do_stats else None)

if args.do_stats:
    stats['stop'].set()
    sthread.join()

if args.output=='zmq':
    socket.close()
    context.term()

if args.sigmffile is not None:
    print("{}]}", file=sigmfout)
    sigmfout.close()
    if os.path.isfile(args.sigmffile):
        os.rename(args.sigmffile,        args.sigmffile+".bak")
    os.rename(args.sigmffile+".tmp", args.sigmffile)

if args.output == "sat":
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

if isinstance(args.errorstats, collections.abc.Mapping):
    total=0
    for (msg,count) in sorted(args.errorstats.items()):
        total+=count
        print("%7d: %s"%(count, msg), file=sys.stderr)
    print("%7d: %s"%(total, "Total"), file=sys.stderr)

if args.output == "err":
    print("### ")
    print("### Error listing:")
    print("### ")
    sort={}
    for m in selected:
        msg=m.error_msg[0]
        if msg in sort:
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

if args.output == "plot":
    name="%s over %s"%(args.plotargs[1],args.plotargs[0])
    if len(args.plotargs)>2:
        name+=" with %s"%args.plotargs[2]
    filter=""
    if len(args.linefilter)>0 and args.linefilter['type']!="All":
        filter+="type==%s"%args.linefilter['type']
        name=("%s "%args.linefilter['type'])+name
    if args.linefilter['attr']:
        filter+=" containing %s"%args.linefilter['attr']
        name+=" having %s"%args.linefilter['attr']
    if args.linefilter['check']:
        x=args.linefilter['check']
        if x.startswith("q."):
            x=x[2:]
        filter+=" and %s"%x
        name+=" where %s"%x
    plt.suptitle(filter)
    plt.xlabel(args.plotargs[0])
    plt.ylabel(args.plotargs[1])
    if args.plotargs[0]=="time":
        args.plotargs[0]="globalns"
        def format_date(x, _pos=None):
            return datetime.datetime.fromtimestamp(x/10**9).strftime('%Y-%m-%d %H:%M:%S')
        plt.gca().xaxis.set_major_formatter(ticker.FuncFormatter(format_date))
        plt.gcf().autofmt_xdate()

    if False:
        plotsats(plt,selected[0].globaltime,selected[-1].globaltime)

    for m in selected:
        xl.append(m.__dict__[args.plotargs[0]])
        yl.append(m.__dict__[args.plotargs[1]])
        if len(args.plotargs)>2:
            cl.append(m.__dict__[args.plotargs[2]])

    if len(args.plotargs)>2:
        plt.scatter(x = xl, y= yl, c= cl)
        plt.colorbar().set_label(args.plotargs[2])
    else:
        plt.scatter(x = xl, y= yl)

    mng = plt.get_current_fig_manager()
    mng.resize(*mng.window.maxsize())

    fname = re.sub(r'[/ ]', '_', name)

    c = plt.gcf().canvas
    c.get_default_filename = lambda: '%s.%s' % (fname, c.get_default_filetype())

    plt.savefig(fname+".png")
    plt.show()
