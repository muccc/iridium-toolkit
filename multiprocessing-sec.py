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

def printer(out_queue):
    while True:
        msg = out_queue.get()
        print msg
        out_queue.task_done()

if __name__ == "__main__":
    options, remainder = getopt.getopt(sys.argv[1:], 'o:w:c:r:S:vd:f:p:j:', ['offset=',
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

    if sample_rate == None:
        print >> sys.stderr, "Sample rate missing!"
        exit(1)
    if center == None:
        print >> sys.stderr, "Need to specify center frequency!"
        exit(1)
    if fmt == None:
        print >> sys.stderr, "Need to specify sample format (one of rtl, hackrf, sc16, float)!"
        exit(1)


    basename=None

    if len(remainder)==0 or pipe !=None:
        if pipe==None:
            pipe="t"
        basename="i-%.4f-%s1"%(time.time(),pipe)
        file_name = "/dev/stdin"
    else:
        file_name = remainder[0]
        basename= filename= re.sub('\.[^.]*$','',file_name)

    det = detector.Detector(sample_rate=sample_rate, fft_peak=fft_peak, sample_format=fmt, search_size=search_size, verbose=verbose, signal_width=search_window)
    cad = cut_and_downmix.CutAndDownmix(center=center, input_sample_rate=sample_rate, search_depth=search_depth, verbose=verbose)
    dem = demod.Demod(sample_rate=cad.output_sample_rate, use_correlation=True, verbose=verbose)

    def process_one(basename, time_stamp, signal_strength, bin_index, freq, signal):
        mix_signal, mix_freq = cad.cut_and_downmix(signal=signal, search_offset=freq, search_window=search_window)
        dataarray, data, access_ok, lead_out_ok, confidence, level, nsymbols = dem.demod(mix_signal)
        msg = "RAW: %s %09d %010d A:%s L:%s %3d%% %.3f %3d %s"%(basename,time_stamp,mix_freq,("no","OK")[access_ok],("no","OK")[lead_out_ok],confidence,level,(nsymbols-12),data)
        out_queue.put(msg)
        if mix_freq < 1626e6 and confidence>95 and nsymbols>40 and access_ok==1:
            iq.write("keep.%010d-f%010d.raw"%(time_stamp,freq),signal)

    def wrap_process(time_stamp, signal_strength, bin_index, freq, signal):
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
