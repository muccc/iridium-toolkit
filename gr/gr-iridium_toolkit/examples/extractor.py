#!/usr/bin/env python
# vim: set ts=4 sw=4 tw=0 et pm=:
import time
import getopt
import sys
import threading

import multiprocessing
#import iridium
import flow_graph

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


def print_stats(tb):
    global last_print, queue_len_max, out_count, in_count
    global drop_count, drop_count_total, ok_count
    global ok_count_total, out_count_total, in_count_total, t0
    while True:

        queue_len = 0

        in_count = tb.get_n_handled_bursts() - in_count_total
        ok_count = tb.get_n_access_ok_bursts() - ok_count_total
        out_count = in_count
        drop_count = 0

        if queue_len > queue_len_max:
            queue_len_max = queue_len

        dt = time.time() - last_print
        in_rate = in_count / dt
        in_count_total += in_count
        in_rate_avg = in_count_total / (time.time() - t0)
        out_rate = out_count/ dt
        drop_rate = drop_count / dt
        ok_ratio = ok_count / float(out_count)
        ok_rate = ok_count / dt
        drop_count_total += drop_count
        ok_count_total += ok_count
        out_count_total += out_count
        ok_ratio_total = ok_count_total / float(out_count_total)
        ok_rate_avg = ok_count_total / (time.time() - t0)

        stats = ""
        stats += "%d" % time.time()
        stats += " | i: %3d/s" % in_rate + " | i_avg: %3d/s" % in_rate_avg
        stats += " | q: %4d" % queue_len + " | q_max: %4d" % queue_len_max
        stats += " | o: %2d/s" % out_rate
        stats += " | ok: %3d%%" % (ok_ratio * 100)
        stats += " | ok: %2d/s" % ok_rate
        stats += " | ok_avg: %3d%%" % (ok_ratio_total * 100)
        stats += " | ok: %10d" % ok_count_total
        stats += " | ok_avg: %3d/s" % ok_rate_avg
        stats += " | d: %d" % drop_count_total
        print >> sys.stderr, stats

        queue_len_max = 0
        in_count = 0
        out_count = 0
        drop_count = 0
        ok_count = 0
        last_print = time.time()

        time.sleep(60)



if __name__ == "__main__":
    options, remainder = getopt.getopt(sys.argv[1:], 'w:c:r:vd:f:p:j:oq:b:D:', ['offset=',
                                                            'window=',
                                                            'center=',
                                                            'rate=',
                                                            'search-depth=',
                                                            'verbose',
                                                            'db=',
                                                            'format=',
                                                            'pipe=',
                                                            'jobs=',
                                                            'offline',
                                                            'queuelen=',
                                                            'burstsize=',
                                                            'uplink',
                                                            'downlink',
                                                            'decimation'
                                                            ])

    center = None # 1626270833
    search_window = 40000
    search_depth = 0.007
    verbose = False
    search_size=1 # Only calulate every (search_size)'th fft
    sample_rate = None
    threshold = 8.5 # about 8.5 dB over noise
    fmt = None
    pipe = None
    jobs = 4
    offline = False
    max_queue_len = 1000
    burst_size = 20
    direction = None
    decimation = 1

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
        elif opt in ('-p', '--pipe'):
            pipe = arg
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


    if len(remainder)==0 or pipe !=None:
        file_name = "/dev/stdin"
    else:
        file_name = remainder[0]

    tb = flow_graph.FlowGraph(center_frequency=center, sample_rate=sample_rate, decimation=decimation, 
            filename=file_name, sample_format=fmt,
            threshold=threshold, signal_width=search_window,
            verbose=verbose)

    statistics_thread = threading.Thread(target=print_stats, args=(tb,))
    statistics_thread.setDaemon(True)
    statistics_thread.start()

    tb.run()

    print >> sys.stderr, "Done."
