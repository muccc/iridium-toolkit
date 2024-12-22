#!/usr/bin/env python3
# vim: set ts=4 sw=4 tw=0 et pm=:

import sys
import fileinput
import argparse
import os
from os.path import splitext, basename
import importlib
import pkgutil

import iridiumtk.config
import iridiumtk.reassembler

parser = argparse.ArgumentParser()

def parse_comma(arg):
    return arg.split(',')

parser.add_argument("-v", "--verbose",     action="store_true",
        help="increase output verbosity")
parser.add_argument("-i", "--input",       default=None,
        help="input filename")
parser.add_argument("-o", "--output",      default=None,
        help="output filename")
parser.add_argument("-m", "--mode",        default=None, required=True,
        help="processing mode")
parser.add_argument("-a", "--args",        default=[], type=parse_comma,
        help="comma separated additional arguments")
parser.add_argument("-s", "--stats",       action="store_true",
        help="enable statistics")
parser.add_argument("-d", "--debug",       action="store_true",
        help=argparse.SUPPRESS)

parser.add_argument("--station",           default=None,
        help="optional station ID for acars")

parser.add_argument("remainder", nargs='*',
        help=argparse.SUPPRESS)

config, remaining = parser.parse_known_args()

if config.stats:
    import curses
    curses.setupterm(fd=sys.stderr.fileno())
    eol=(curses.tigetstr('el')+curses.tigetstr('cr')).decode("ascii")


state=None
if 'state' in config.args:
    import pickle
    statefile="%s.state" % (config.mode)
    try:
        with open(statefile) as f:
            state=pickle.load(f)
    except (IOError, EOFError):
        pass
    config.state=state

validargs=()
zx=None

iridiumtk.config.config=config

plugins = iridiumtk.reassembler.get_plugins(iridiumtk.reassembler)

modes={}
for s, v in plugins.items():
    for mode in v.modes:
        modes[mode[0]]=[v]+mode[1:]

if config.debug or config.mode == 'help':
    cwd = os.getcwd()+'/'
    for mode, info in sorted(modes.items()):
        path=info[0].__spec__.origin
        if path.startswith(cwd):
            path=path[len(cwd):]
        print("Mode %-10s class %-22s source %-37s"%(mode, info[1].__name__, path), end='')
        if len(info)>2:
            print(" - Options: ",info[2])
        else:
            print()
    print()

if config.mode not in modes:
    raise SystemExit("No plugin found for mode: "+config.mode)

zx=modes[config.mode][1]()

if len(modes[config.mode])>2:
    validargs=modes[config.mode][2]

for x in config.args:
    if x not in validargs:
        raise Exception("unknown -a option: "+x)

if getattr(zx, "args", None) is not None:
    config = zx.args(parser)
else:
    config = parser.parse_args()

if config.input is None:
    if not config.remainder:
        config.input = "/dev/stdin"
    else:
        config.input = config.remainder[0]

config.outbase, _= splitext(config.input)
if config.outbase.startswith('/dev'):
    config.outbase=basename(config.outbase)

if config.output is None:
    outfile=sys.stdout
elif config.output == "" or config.output == "=":
    config.output="%s.%s" % (config.outbase, config.mode)
    outfile=open(config.output,"w")
else:
    outfile=open(config.output,"w")

config.outfile = outfile

if getattr(zx, "outfile", None) is not None:
    zx.outfile=config.outfile
if getattr(zx, "config", None) is not None:
    zx.config=config

if config.input.startswith("zmq:"):
    try:
        topics=zx.topic
        if not isinstance(topics,list):
            topics=[topics]
    except AttributeError:
        print("mode '%s' does not support streaming"%mode, file=sys.stderr)
        sys.exit(1)
    import zmq
    context = zmq.Context()
    socket = context.socket(zmq.SUB)
    socket.connect ("tcp://localhost:4223")
    for topic in topics:
        socket.setsockopt(zmq.SUBSCRIBE, bytes(topic,"ascii"))
    config.iobj=iter(socket.recv_string,"")
else:
    config.iobj=fileinput.input(config.input)

try:
    zx.run(config.iobj)
except BrokenPipeError as e:
    raise SystemExit(e)
except KeyboardInterrupt:
    print("")
