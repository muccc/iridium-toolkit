#!/usr/bin/env python
# vim: set ts=4 sw=4 tw=0 et pm=:
import time
import getopt
import sys
import threading

import multiprocessing
#import iridium
import flow_graph
import requests

queue_len_max = 0

out_count = 0
in_count = 0
drop_count = 0
ok_count = 0

in_count_total = 0
out_count_total = 0
drop_count_total = 0
ok_count_total = 0

last_print = 0
t0 = time.time()

def sendData(timestamp, in_rate, in_rate_avg, queue_len, queue_len_max, out_rate, ok_ratio, ok_rate, ok_ratio_total, ok_count_total, ok_rate_avg, drop_count_total):
    payload = {'timestamp': timestamp, 'in_rate': in_rate, 'in_rate_avg': in_rate_avg, 'queue_len': queue_len, 'queue_len_max': queue_len_max, 'out_rate': out_rate, 'ok_ratio': ok_ratio, 'ok_rate': ok_rate, 'ok_ratio_total': ok_ratio_total, 'ok_count_total': ok_count_total, 'ok_rate_avg': ok_rate_avg, 'drop_count_total': drop_count_total }
    global host, port
    
    try:
        r = requests.get('http://' + host + ':' + str(port) + '/post', params=payload)
        print >> sys.stderr, "Dashboard Response: " + str(r.status_code)
    except requests.exceptions.Timeout as e:
        print >> sys.stderr, "Dashboard: Request Timeout"
    except requests.exceptions.TooManyRedirects as e:
        print >> sys.stderr, "Dashboard: Too many redirects"
    except requests.exceptions.RequestException as e:
        print >> sys.stderr, "Dashboard: Request exception"
    except requests.exceptions.ConnectionError as e:
        print >> sys.stderr, "Dashboard: Connection error"

def print_stats(tb):
    global last_print, queue_len_max, out_count, in_count
    global drop_count, drop_count_total, ok_count
    global ok_count_total, out_count_total, in_count_total, t0
    global dashboard
    
    while True:

        queue_len = tb.get_queue_size()
        queue_len_max = tb.get_max_queue_size()

        in_count = tb.get_n_detected_bursts() - in_count_total
        out_count = tb.get_n_handled_bursts() - out_count_total
        ok_count = tb.get_n_access_ok_bursts() - ok_count_total
        drop_count = 0

        dt = time.time() - last_print
        in_rate = in_count / dt
        in_count_total += in_count
        in_rate_avg = in_count_total / (time.time() - t0)
        out_rate = out_count/ dt
        drop_rate = drop_count / dt

        if out_count != 0:
            ok_ratio = ok_count / float(out_count)
        else:
            ok_ratio = 0

        ok_rate = ok_count / dt
        drop_count_total += drop_count
        ok_count_total += ok_count
        out_count_total += out_count

        if out_count_total != 0:
            ok_ratio_total = ok_count_total / float(out_count_total)
        else:
            ok_ratio_total = 0

        ok_rate_avg = ok_count_total / (time.time() - t0)

        timestamp = time.time()
        
        stats = ""
        stats += "%d" % timestamp
        stats += " | i: %3d/s" % in_rate + " | i_avg: %3d/s" % in_rate_avg
        stats += " | q: %4d" % queue_len + " | q_max: %4d" % queue_len_max
        stats += " | o: %3d/s" % out_rate
        stats += " | ok: %3d%%" % (ok_ratio * 100)
        stats += " | ok: %3d/s" % ok_rate
        stats += " | ok_avg: %3d%%" % (ok_ratio_total * 100)
        stats += " | ok: %10d" % ok_count_total
        stats += " | ok_avg: %3d/s" % ok_rate_avg
        stats += " | d: %d" % drop_count_total
        print >> sys.stderr, stats

        if dashboard == True:
            sendData(timestamp, in_rate, in_rate_avg, queue_len, queue_len_max, out_rate, (ok_ratio * 100), ok_rate, (ok_ratio_total * 100), ok_count_total, ok_rate_avg, drop_count_total)

        queue_len_max = 0
        in_count = 0
        out_count = 0
        drop_count = 0
        ok_count = 0
        last_print = time.time()

        time.sleep(60)



if __name__ == "__main__":
    options, remainder = getopt.getopt(sys.argv[1:], 'w:c:r:vd:f:j:oq:b:D:x:y:z:', ['offset=',
                                                            'window=',
                                                            'center=',
                                                            'rate=',
                                                            'search-depth=',
                                                            'verbose',
                                                            'db=',
                                                            'format=',
                                                            'jobs=',
                                                            'offline',
                                                            'queuelen=',
                                                            'burstsize=',
                                                            'uplink',
                                                            'downlink',
                                                            'decimation',
                                                            'dashboard',
                                                            'host',
                                                            'port'
                                                            ])

    center = None
    search_window = 40000
    search_depth = 0.007
    verbose = False
    sample_rate = None
    threshold = 8.5 # about 8.5 dB over noise
    fmt = None
    jobs = 4
    offline = False
    max_queue_len = 1000
    burst_size = 20
    direction = None
    decimation = 1
    dashboard = False
    host = "localhost"
    port = 5000

    if len(remainder) == 0 or remainder[0] == '-':
        filename = "/dev/stdin"
    else:
        filename = remainder[0]

    if filename.endswith(".conf"):
        import ConfigParser
        config = ConfigParser.ConfigParser()
        config.read(filename)
        items = config.items("osmosdr-source")
        d = {key: value for key, value in items}

        sample_rate = int(d['sample_rate'])
        center = int(d['center_freq'])

        fmt = 'float'

    for opt, arg in options:
        if opt in ('-w', '--search-window'):
            search_window = int(arg)
        elif opt in ('-c', '--center'):
            center = int(arg)
        elif opt in ('-r', '--rate'):
            sample_rate = int(arg)
        elif opt in ('-s', '--search'):
            search_depth = float(arg)
        elif opt in ('-d', '--db'):
            threshold = float(arg)
        elif opt in ('-v', '--verbose'):
            verbose = True
        elif opt in ('-f', '--format'):
            fmt = arg
        elif opt in ('-j', '--jobs'):
            jobs = int(arg)
        elif opt in ('-o', '--offline'):
            offline = True
        elif opt in ('-q', '--queuelen'):
            max_queue_len = int(arg)
        elif opt in ('-b', '--burstsize'):
            burst_size = int(arg)
        #elif opt == '--uplink':
        #    direction = iridium.UPLINK
        #elif opt == '--downlink':
        #    direction = iridium.DOWNLINK
        elif opt in ('-D', '--decimation'):
            decimation = int(arg)
        elif opt in ('-x', '--dashboard'):
            dashboard = True
        elif opt in ('-y', '--host'):
            host = arg
        elif opt in ('-z', '--port'):
            port = int(arg)

    if sample_rate == None:
        print >> sys.stderr, "Sample rate missing!"
        exit(1)
    if center == None:
        print >> sys.stderr, "Need to specify center frequency!"
        exit(1)
    if fmt == None:
        print >> sys.stderr, "Need to specify sample format (one of rtl, hackrf, sc16, float)!"
        exit(1)
    if decimation < 1:
        print >> sys.stderr, "Decimation must be > 0"
        exit(1)
    if decimation > 1 and decimation % 2:
        print >> sys.stderr, "Decimations > 1 must be even"
        exit(1)


    tb = flow_graph.FlowGraph(center_frequency=center, sample_rate=sample_rate, decimation=decimation, 
            filename=filename, sample_format=fmt,
            threshold=threshold, signal_width=search_window,
            offline=offline,
            verbose=verbose)

    statistics_thread = threading.Thread(target=print_stats, args=(tb,))
    statistics_thread.setDaemon(True)
    statistics_thread.start()

    tb.run()

    print >> sys.stderr, "Done."
