#!/usr/bin/env python3
#
# iridium-acars-to-airframes.py
#
# Send the ACARS JSON output from iridium-toolkit to Airframes.io. You may send to additional destinations
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
#  $ reassembler.py -i zmq: -m acars -a json --station YOUR_STATION_IDENT | iridium-acars-to-airframes.py
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
#     --verbose, -v         Verbose output. Currently logs every message to stdout.
#     --debug, -d           Enable debug output
#     --output OUTPUT, -o OUTPUT
#                           Send output via TCP to additional destination transport:host:port
#                           (where transport is "tcp" or "udp")
#     --no-airframes        Do not automatically add airframes.io to the list of outputs.

# For more information about Airframes, see https://app.airframes.io/about or contact kevin@airframes.io.
#

import argparse
import json
import logging
import select
import socket
import sys
import time

AIRFRAMES_INGEST_HOST = 'feed.airframes.io'
AIRFRAMES_INGEST_PORT = 5590
sockets = {}

logging.basicConfig(format='%(message)s', level=logging.WARNING)
log = logging.getLogger(__name__)

def send_message(message):
    global sockets
    for k, sock in sockets.items():
        if sock is not None:
            try:
                sock.sendall(("%s\n" % message).encode('utf-8'))
                log.info("Sent message to %s" % (k))
            except Exception as e:
                log.error('Error sending message to %s: %s' % (k, e))
                try:
                    sock.close()
                except:
                    pass
                # A None object instead of a socket will cause the script to attempt connecting in the send loop.
                sockets[k] = None
                sock = None

        if sock is None:
            transport, host, port = k.split(":")
            if transport == 'udp':
                try:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    sock.connect((host, int(port)))
                    sockets[k] = sock

                    sock.sendall(("%s\n" % message).encode('utf-8'))
                except Exception as e:
                    log.error("Exception creating socket to %s: %s" % (k, e))
                    sockets[k] = None
                    sock = None

            elif transport == 'tcp':
                # Assume TCP socket is dead. Close and reconnect.
                try:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.connect((host, int(port)))
                    sockets[k] = sock

                    sock.sendall(("%s\n" % message).encode('utf-8'))
                except Exception as e:
                    log.error("Error reconnecting to %s: %s" % (k, e))

                    # A None object instead of a socket will cause the script to attempt connecting in the send loop.
                    sockets[k] = None
                    sock = None

def main():
    args_parser = argparse.ArgumentParser(
        prog='iridium-acars-to-airframes.py',
        description='Feed Iridium ACARS to Airframes.io and additional remote destinations',
    )
    args_parser.add_argument(
        '--station', '-s', help='Override station ident', required=False)
    args_parser.add_argument(
        '--verbose', '-v', help='Verbose output. Currently logs every message to stdout.', action='store_true')
    args_parser.add_argument(
        '--debug', '-d', help='Enable debug output', action='store_true')
    args_parser.add_argument(
        '--output', '-o', help='Send output via TCP to additional destination transport:host:port (where transport is "tcp" or "udp")', default=[], action='append')
    args_parser.add_argument(
        '--no-airframes', help='Do not automatically add airframes.io to the list of outputs.', action='store_true')
    args = args_parser.parse_args()

    if args.debug:
        log.setLevel(logging.DEBUG)

    if args.station:
        logging.warn("Overriding station ident to %s" % (args.station,))

    if not args.no_airframes:
        args.output = ['tcp:%s:%d' %
                       (AIRFRAMES_INGEST_HOST, AIRFRAMES_INGEST_PORT)] + args.output

    for output in args.output:
        transport, host, port = output.split(':')
        try:
            if transport == 'tcp':
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.connect((host, int(port)))
                sockets[output] = sock
                log.info("Connected to %s:%s:%s" % (transport, host, port))
            elif transport == 'udp':
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.connect((host, int(port)))
                sockets[output] = sock
                log.info("Connected to %s:%s:%s" % (transport, host, port))
            else:
                log.error("Unknown transport %s" % (transport,))
                sys.exit(1)
        except TimeoutError as e:
            log.warning("Error connecting to output (%s:%s): %s. Will attempt connection later." % (host, port, e))
            # A None object instead of a socket will cause the script to attempt connecting in the send loop.
            sockets[output] = None
        except Exception as e:
            log.warning("Error connecting to output (%s:%s): %s. Will attempt connection later." % (host, port, e))
            # A None object instead of a socket will cause the script to attempt connecting in the send loop.
            sockets[output] = None

    if len(sockets) < 1:
        log.error("No valid outputs configured. Exiting.")
        sys.exit(0)

    for line in sys.stdin:
        line = line.strip()

        if args.verbose:
            print(line)

        if line is None or len(line) < 1:
            log.error("Received EOF. Exiting.")
            sys.exit(0)

        if args.station:
            try:
                message = json.loads(line)
            except Exception as e:
                log.warning("Error parsing JSON (%s): %s" % (e, repr(line),))
                continue

            if "source" not in message:
                message["source"] = {}

            message['source']['station_id'] = args.station

            line = json.dumps(message)

        send_message(line)

if __name__ == '__main__':
    main()
