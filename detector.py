#!/usr/bin/env python
# vim: set ts=4 sw=4 tw=0 et pm=:
import sys
import math
import numpy
import os.path
import re
import getopt
import time
from functools import partial

class Detector(object):
    def __init__(self, sample_rate, fft_peak=7.0, sample_format=None, search_size=1, verbose=False, signal_width=40e3, burst_size=6):
        self._sample_rate = sample_rate
        self._fft_size=int(math.pow(2, 1+int(math.log(self._sample_rate/1000,2)))) # fft is approx 1ms long
        self._bin_size = float(self._fft_size)/self._sample_rate * 1000 # How many ms is one fft now?
        self._verbose = verbose
        self._search_size = search_size
        self._fft_peak = fft_peak
        self._burst_size = burst_size

        if sample_format == "rtl":
            self._struct_elem = numpy.uint8
            self._struct_len = numpy.dtype(self._struct_elem).itemsize * self._fft_size *2
        elif sample_format == "hackrf":
            self._struct_elem = numpy.int8
            self._struct_len = numpy.dtype(self._struct_elem).itemsize * self._fft_size *2
        elif sample_format == "sc16":
            self._struct_elem = numpy.int16
            self._struct_len = numpy.dtype(self._struct_elem).itemsize * self._fft_size *2
        elif sample_format == "float":
            self._struct_elem = numpy.complex64
            self._struct_len = numpy.dtype(self._struct_elem).itemsize * self._fft_size
        else:
            raise Exception("No sample format given")

        self._window = numpy.blackman(self._fft_size)
        self._fft_histlen=500 # How many items to keep for moving average. 5 times our signal length
        self._data_histlen=self._search_size
        self._data_postlen=8
        self._signal_maxlen=1+int(30/self._bin_size) # ~ 30 ms
        self._fft_freq = numpy.fft.fftshift(numpy.fft.fftfreq(self._fft_size))
        self._signal_width=signal_width/(self._sample_rate/self._fft_size) # Area to ignore around an already found signal in Hz
        
        if self._verbose:
            print "fft_size=%d (=> %f ms)"%(self._fft_size,self._bin_size)
            print "calculate fft once every %d block(s)"%(self._search_size)
            print "require %.1f dB"%(10*math.log(self._fft_peak,10))
            print "signal_width: %d (= %.1f Hz)"%(self._signal_width,self._signal_width*self._sample_rate/self._fft_size)

    def process_file(self, file_name, data_collector):
        data_hist = []
        fft_avg = [0.0]*self._fft_size
        fft_hist = []

        index = -1
        wf=None
        writepost=0
        signals=0

        peaks=[] # idx, postlen, file

        def remove_signal(peaks,idx): # clear "area" around a peak
            w=int(self._signal_width-1)/2
            p0=idx-w
            if p0<0:
                p0=0
            p1=idx+w
            if p1>=self._fft_size:
                p1=self._fft_size-1
            peaks[p0:p1+1]=[0]*(p1-p0+1)

        with open(file_name, "rb") as f:
            burst_signals=0
            burst_mute=0
            while True:
                data = f.read(self._struct_len)
                if burst_signals>0:
                    burst_signals-=1
                if burst_mute>0:
                    burst_mute-=1
                if not data: break
                if len(data) != self._struct_len: break

                index+=1
                if index%self._search_size==0:
                    slice = numpy.frombuffer(data, dtype=self._struct_elem)
                    if self._struct_elem == numpy.uint8:
                        slice = slice.astype(numpy.float32) # convert to float
                        slice = (slice-127.4)/128.          # Normalize
                        slice = slice.view(numpy.complex64) # reinterpret as complex
                    if self._struct_elem == numpy.int8:
                        slice = slice.astype(numpy.float32) # convert to float
                        slice = slice/128.                  # Normalize
                        slice = slice.view(numpy.complex64) # reinterpret as complex
                    if self._struct_elem == numpy.int16:
                        slice = slice.astype(numpy.float32) # convert to float
                        slice = slice/32768.                # Normalize
                        slice = slice.view(numpy.complex64) # reinterpret as complex
                    fft_result = numpy.absolute(numpy.fft.fftshift(numpy.fft.fft(slice * self._window)))

                    if len(fft_hist)>25: # grace period after start of file
                        peakl= (fft_result / fft_avg)*len(fft_hist)

                        if self._verbose:
                            for p in peaks:
                                print "[%4d,%2d,%2d]"%(p[0],p[1],index-p[2]),
                        for p in peaks:
                            pi=p[0]
                            if self._verbose:
                                print "Peak B%4d: %4.1f dB"%(pi,10*math.log(peakl[pi],10)),
                                pa=numpy.average(peakl[pi-10:pi+10])
                                print "(avg: %4.1f dB)"%(10*math.log(pa,10)),
                            if peakl[p[0]]>self._fft_peak:
                                if self._verbose:
                                    print "still peak",
                                p[1]=self._search_size+self._data_postlen
                            p[1]-=1
                            p[4] = numpy.append(p[4], slice)
                            if self._verbose:
                                print
                                if (index-p[2])==self._signal_maxlen:
                                    print "Peak B%d @ %d too long"%(p[0],p[2])
                            if (index-p[2])<self._signal_maxlen:
                                remove_signal(peakl,pi)
                        peakidx=numpy.argmax(peakl)
                        peak=peakl[peakidx]
                        while(peak>self._fft_peak and burst_mute==0):
                            signals+=1
                            burst_signals+=1
                            if burst_signals==self._burst_size:
                                break

                            time_stamp = index*self._bin_size
                            signal_strength = 10*math.log(peak,10)
                            bin_index = peakidx
                            freq = self._fft_freq[peakidx]*self._sample_rate
                            info = (time_stamp, signal_strength, bin_index, freq)
                            signal = numpy.append(numpy.concatenate(data_hist), slice)
                            if self._verbose:
                                print "New peak:",
                                print "Peak t=%5d (%4.1f dB) B:%3d @ %.0f Hz"%info

                            writepost=self._search_size+self._data_postlen
                            peaks.append([peakidx,writepost,index,info, signal])

                            remove_signal(peakl,peakidx)
                            peakidx=numpy.argmax(peakl)
                            peak=peakl[peakidx]
                    if burst_signals==self._burst_size:
                        burst_mute=10
                        burst_signals=0
                        time_stamp = index*self._bin_size
                        print >> sys.stderr, "Ran into burst squelch at", time_stamp

                    peaks_to_collect = filter(lambda e: e[1]<=0, peaks)
                    for peak in peaks_to_collect:
                        data_collector(peak[3][0], peak[3][1], peak[3][2], peak[3][3], peak[4])
                    peaks = filter(lambda e: e[1]>0, peaks)

                    # keep fft in history buffer and update average
                    if len(peaks)==0: # No output in progress
                        fft_hist.append(fft_result)
                        fft_avg+=fft_result
                        if len(fft_hist)>self._fft_histlen:
                            fft_avg-=fft_hist[0]
                            fft_hist.pop(0)

                # keep slice in history buffer
                data_hist.append(slice)
                if len(data_hist)>self._data_histlen:
                    data_hist.pop(0)

        if self._verbose:
            print "%d signals found"%(signals)

def file_collector(basename, time_stamp, signal_strength, bin_index, freq, signal):
    file_name = "%s-%07d-o%+07d.det" % (os.path.basename(basename), time_stamp, freq)
    signal.tofile(file_name)

if __name__ == "__main__":
    options, remainder = getopt.getopt(sys.argv[1:], 'r:s:d:vf:p:', [
                                                            'rate=', 
                                                            'speed=', 
                                                            'db=', 
                                                            'verbose',
                                                            'format=',
                                                            'pipe',
                                                            ])
    sample_rate = None
    verbose = False
    search_size=1 # Only calulate every (search_size)'th fft
    fft_peak = 7.0 # about 8.5 dB over noise
    fmt = None
    pipe = None

    for opt, arg in options:
        if opt in ('-r', '--rate'):
            sample_rate = int(arg)
        elif opt in ('-s', '--speed'):
            search_size = int(arg)
        elif opt in ('-d', '--db'):
            fft_peak = pow(10,float(arg)/10)
        elif opt in ('-v', '--verbose'):
            verbose = True
        elif opt in ('-f', '--format'):
            fmt = arg
        elif opt in ('-p', '--pipe'):
            pipe = arg

    if sample_rate == None:
        print >> sys.stderr, "Sample rate missing!"
        exit(1)
    if fmt == None:
        print >> sys.stderr, "Need to specify sample format (one of rtl, hackrf, sc16, float)!"
        exit(1)

    basename=None

    if len(remainder)==0 or pipe !=None:
        if pipe==None:
            print "WARN: pipe mode not set"
            pipe="t"
        basename="i-%.4f-%s1"%(time.time(),pipe)
        print basename
        file_name = "/dev/stdin"
    else:
        file_name = remainder[0]
        basename= filename= re.sub('\.[^.]*$','',file_name)

    d = Detector(sample_rate, fft_peak=fft_peak, sample_format=fmt, search_size=search_size, verbose=verbose)
    d.process_file(file_name, partial(file_collector, basename))

