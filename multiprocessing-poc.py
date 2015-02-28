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
from functools import partial
import multiprocessing

work_queue = multiprocessing.JoinableQueue()
out_queue = multiprocessing.JoinableQueue()

class Worker(object):
    def __init__(self, work_queue, out_queue, center, sample_rate, search_depth, search_window, verbose):
        self._work_queue = work_queue
        self._cad = cut_and_downmix.CutAndDownmix(center=center, sample_rate=sample_rate,
                                            search_depth=search_depth, verbose=verbose)
        self._dem = demod.Demod(sample_rate=sample_rate, use_correlation=True, verbose=verbose)
        self._out_queue = out_queue
        self._search_window=search_window
        self._verbose = verbose

    def run(self):
        while True:
            basename, time_stamp, signal_strength, bin_index, freq, signal = self._work_queue.get()
            try:
                signal, freq = self._cad.cut_and_downmix(signal=signal, search_offset=freq, search_window=self._search_window)
                dataarray, data, access_ok, lead_out_ok, confidence, level, nsymbols = self._dem.demod(signal)
                msg = "RAW: %s %07d %010d A:%s L:%s %3d%% %.3f %3d %s"%(basename,time_stamp,freq,("no","OK")[access_ok],("no","OK")[lead_out_ok],confidence,level,(nsymbols-12),data)
                self._out_queue.put(msg)
            except:
                sys.stderr.write("something went wrong :/\n")
            self._work_queue.task_done()

def collector(basename, time_stamp, signal_strength, bin_index, freq, signal):
    work_queue.put((basename, time_stamp, signal_strength, bin_index, freq, signal))

def printer(out_queue):
    while True:
        msg = out_queue.get()
        print msg

def main():
    options, remainder = getopt.getopt(sys.argv[1:],
        'o:w:c:r:S:vd:8p:', ['offset=',
                             'window=',
                             'center=',
                             'rate=',
                             'search-depth=',
                             'verbose',
                             'speed=',
                             'db=',
                             'rtl',
                             'pipe',
                             ])

    center= 1626270833
    search_window = 60000
    search_depth = 0.007
    verbose = False
    search_size=1 # Only calulate every (search_size)'th fft
    sample_rate = 0
    fft_peak = 7.0 # about 8.5 dB over noise
    rtl = False
    pipe = None

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
        elif opt in ('-8', '--rtl'):
            rtl = True
        elif opt in ('-p', '--pipe'):
            pipe = arg

    if sample_rate == 0:
        print "Sample rate missing!"
        exit(1)

    basename=None

    if len(remainder)==0 or pipe !=None:
        if pipe==None:
            pipe="t"
        basename="i-%.4f-%s1"%(time.time(),pipe)
        file_name = "/dev/stdin"
    else:
        file_name = remainder[0]

    det = detector.Detector(sample_rate=sample_rate, fft_peak=fft_peak,
            use_8bit = rtl, search_size=search_size, verbose=verbose)

    workers = []
    for i in range(4):
        w = Worker(work_queue, out_queue, center=center,
                sample_rate=sample_rate, search_depth=search_depth,
                search_window=search_window, verbose=verbose)
        p = multiprocessing.Process(target=w.run)
        p.daemon = True
        p.start()
        workers.append((w, p))

    out_thread = threading.Thread(target=printer, args = (out_queue,))
    out_thread.daemon = True
    out_thread.start()

    det.process_file(file_name, partial(collector, basename))
    work_queue.join()

if __name__ == "__main__":
    main()

