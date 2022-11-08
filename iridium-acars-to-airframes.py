#!/usr/bin/env python3
#
# iridium-acars-to-airframes.py
#
# Send the ACARS JSON output from iridium-toolkit to Airframes.io. You may send to additional TCP destinations
# by specifying the --output option multiple times.
#
# INSTRUCTIONS:
#
# 1. Ensure that your iridium-toolkit setup is properly decoding acars first.
# 2. Pipe the output of the "-m acars -a json" to this script. Make sure you set your station ident!
# 3. Optionally, specify additional outputs with the --output option.
#
# EXAMPLE:
#
#  $ export PYTHONUNBUFFERED=x
#  $ reassembler.py -i zmq: -m acars -a json --station YOUR_STATION_IDENT | acars-to-airframes.py
#
# USAGE:
#
#   iridium-acars-to-airframes.py [-h] [--station STATION] [--debug] [--output OUTPUT]
#
#   Feed Iridium ACARS to Airframes.io
#
#   options:
#     -h, --help            show this help message and exit
#     --station STATION, -s STATION
#                           Override station ident
#     --debug, -d           Enable debug output
#     --output OUTPUT, -o OUTPUT
#                           Send output via TCP to additional destination transport:host:port (where transport is "tcp" or "udp")
#
# For more information about Airframes, see https://app.airframes.io/about or contact kevin@airframes.io.
#

import argparse
import json
import sys
import select
import time
import socket

airframes_ingest_host = 'feed.airframes.io'
airframes_ingest_port = 5590
debug = True
sock = None
sockets = {}

def reconnect():
  s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
  s.connect((ingest_host, ingest_port))
  if debug:
    print("Reconnected to Airframes Iridium ACARS ingest (%s:%d)" % (ingest_host, ingest_port))
  return s

def send_message(message):
  global sockets
  for k, sock in sockets.items():
    try:
      sock.sendall(("%s\n" % message).encode())
      if debug:
        print("Sent message to %s" % (k))
    except Exception as e:
      print('Error sending message: %s' % e)
      sock.connect(sock.getpeername())
      sockets[k] = sock
      print("Reconnected to %s:%d" % (sock.getpeername()))
      sockets[k].sendall(message.encode('utf-8'))


if __name__ == '__main__':
  args_parser = argparse.ArgumentParser(
    prog = 'iridium-acars-to-airframes.py',
    description='Feed Iridium ACARS to Airframes.io and additional remote destinations',
  )
  args_parser.add_argument('--station', '-s', help='Override station ident', required=False)
  args_parser.add_argument('--debug', '-d', help='Enable debug output', action='store_true')
  args_parser.add_argument('--output', '-o', help='Send output via TCP to additional destination transport:host:port (where transport is "tcp" or "udp")', default=['tcp:%s:%s' % (airframes_ingest_host, airframes_ingest_port)], action='append')
  args = args_parser.parse_args()

  debug = args.debug
  if args.station and debug:
    print("Overriding station ident to %s" % (args.station,))

  for output in args.output:
    transport, host, port = output.split(':')
    try:
      if transport == 'tcp':
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((host, int(port)))
        sockets[output] = sock
        if debug:
          print("Connected to %s:%s:%s" % (transport, host, port))
      elif transport == 'udp':
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect((host, int(port)))
        sockets[output] = sock
        if debug:
          print("Connected to %s:%s:%s" % (transport, host, port))
      else:
        print("Unknown transport %s" % (transport,))
    except TimeoutError as e:
      print("Error connecting to output (%s:%s): %s" % (host, port, e))
      sys.exit(1)
    except Exception as e:
      print("Error connecting to output (%s:%s): %s" % (host, port, e))
      print("Not adding output to (%s:%s)" % (host, port))

  while True:
    line = sys.stdin.readline().strip()
    if debug:
      print("Received: %s" % (line,))

    try:
      message = json.loads(line)
    except Exception as e:
      print("Error parsing JSON (%s): %s" % (e, line,))
      continue

    if args.station:
      if message['source'] is None:
        message['source'] = {}
      message['source']['station'] = args.station

    send_message(json.dumps(message))
