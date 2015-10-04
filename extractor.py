#!/usr/bin/env python
# vim: set ts=4 sw=4 tw=0 et pm=:
import iq
import demod
import time
import cut_and_downmix
import detector
import getopt
import sys
import re
import threading
import multiprocessing
import signal
import os

out_queue = multiprocessing.JoinableQueue()

queue_len = 0
queue_len_max = 0

out_count = 0
in_count = 0
drop_count = 0
drop_count_total = 0

last_print = 0

queue_blocked = False

def printer(out_queue):
    global queue_len, last_print, queue_len_max, out_count, in_count, drop_count, drop_count_total
    while True:
        msg = out_queue.get()
        queue_len -= 1
        out_count += 1
        if queue_len > queue_len_max:
            queue_len_max = queue_len

        if time.time() - last_print > 60:
            dt = time.time() - last_print
            in_rate = in_count / dt
            out_rate = out_count/ dt
            drop_rate = drop_count / dt
            drop_count_total += drop_rate

            print >> sys.stderr, "%d" % time.time(), "i_rate: %3d" % in_rate, "q: %4d" % queue_len, "q_max: %4d" % queue_len_max, "o_rate: %2d" % out_rate, "d_rate: %3d" % drop_rate, "d: %d" % drop_count_total

            queue_len_max = 0
            in_count = 0
            out_count = 0
            drop_count = 0
            last_print = time.time()

        print msg
        out_queue.task_done()

if __name__ == "__main__":
    options, remainder = getopt.getopt(sys.argv[1:], 'w:c:r:S:vd:f:p:j:oq:b:', ['offset=',
                                                            'window=',
                                                            'center=',
                                                            'rate=',
                                                            'search-depth=',
                                                            'verbose',
                                                            'speed=',
                                                            'db=',
                                                            'format=',
                                                            'pipe=',
                                                            'jobs=',
                                                            'offline',
                                                            'queuelen='
                                                            'burstsize='
                                                            'decimate='
                                                            ])

    center = None # 1626270833
    search_window = 40000
    search_depth = 0.007
    verbose = False
    search_size=1 # Only calulate every (search_size)'th fft
    sample_rate = None
    fft_peak = 7.0 # about 8.5 dB over noise
    fmt = None
    pipe = None
    jobs = 4
    offline = False
    max_queue_len = 1000
    burst_size = 10
    decimate = 0

    for opt, arg in options:
        if opt in ('-w', '--search-window'):
            search_window = int(arg)
        elif opt in ('-c', '--center'):
            center = int(arg)
        elif opt in ('-r', '--rate'):
            sample_rate = int(arg)
        elif opt in ('-s', '--search'):
            search_depth = float(arg)
        elif opt in ('-S', '--speed'):
            search_size = int(arg)
        elif opt in ('-d', '--db'):
            fft_peak = pow(10,float(arg)/10)
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
        elif opt in ('--decimate'):
            decimate = int(arg)

    if sample_rate == None:
        print >> sys.stderr, "Sample rate missing!"
        exit(1)
    if center == None:
        print >> sys.stderr, "Need to specify center frequency!"
        exit(1)
    if fmt == None:
        print >> sys.stderr, "Need to specify sample format (one of rtl, hackrf, sc16, float)!"
        exit(1)

    if decimate == 0:
       if sample_rate > 1000000:
           osr = 500000
           if sample_rate % osr > 0:
               raise RuntimeError("If the sample rate is > 1e6, it must be a multiple of 1000000")
           decimate = sample_rate / osr
       else:
           decimation = 1

    basename=None

    if len(remainder)==0 or pipe !=None:
        if pipe==None:
            pipe="t"
        basename="i-%.4f-%s1"%(time.time(),pipe)
        file_name = "/dev/stdin"
    else:
        file_name = remainder[0]
        basename= filename= re.sub('\.[^.]*$','',file_name)

    det = detector.Detector(sample_rate=sample_rate, fft_peak=fft_peak, sample_format=fmt, search_size=search_size, verbose=verbose, signal_width=search_window, burst_size=burst_size)
    cad = cut_and_downmix.CutAndDownmix(center=center, input_sample_rate=sample_rate, search_depth=search_depth, verbose=verbose, decimation=decimate)
    dem = demod.Demod(sample_rate=cad.output_sample_rate, use_correlation=True, verbose=verbose)

    def process_one(basename, time_stamp, signal_strength, bin_index, freq, signal):
        mix_signal, mix_freq = cad.cut_and_downmix(signal=signal, search_offset=freq, search_window=search_window)
        dataarray, data, access_ok, lead_out_ok, confidence, level, nsymbols = dem.demod(mix_signal)
        msg = "RAW: %s %09d %010d A:%s L:%s %3d%% %.3f %3d %s"%(basename,time_stamp,mix_freq,("no","OK")[access_ok],("no","OK")[lead_out_ok],confidence,level,(nsymbols-12),data)
        out_queue.put(msg)

    def wrap_process(time_stamp, signal_strength, bin_index, freq, signal):
        global queue_len, queue_blocked, in_count, drop_count
        if offline:
            if queue_len > max_queue_len:
                while queue_len > 0:
                    time.sleep(1)
        else:
            if queue_len > max_queue_len:
                queue_blocked = True
            if queue_blocked and queue_len < (max_queue_len / 10):
                queue_blocked = False
            if queue_blocked:
                drop_count += 1
                return
        queue_len += 1
        in_count += 1
        workers.apply_async(process_one,(basename, time_stamp, signal_strength, bin_index, freq, signal))

    def init_worker():
        signal.signal(signal.SIGINT, signal.SIG_IGN)

    out_thread = threading.Thread(target=printer, args = (out_queue,))
    out_thread.daemon = True
    out_thread.start()

    workers = multiprocessing.Pool(processes=jobs, initializer=init_worker)
    try:
        det.process_file(file_name, wrap_process)
    except KeyboardInterrupt:
        print "Going to DIE"
        out_queue.join()
        raise

    workers.close()
    workers.join()
    out_queue.join()
    print "Done."
