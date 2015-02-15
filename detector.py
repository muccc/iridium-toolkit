#!/usr/bin/env python
# vim: set ts=4 sw=4 tw=0 et pm=:
import struct
import sys
import math
import numpy
import os.path
from itertools import izip
import re
#import matplotlib.pyplot as plt
import getopt
import time

def grouped(iterable, n):
    "s -> (s0,s1,s2,...sn-1), (sn,sn+1,sn+2,...s2n-1), (s2n,s2n+1,s2n+2,...s3n-1), ..."
    return izip(*[iter(iterable)]*n)

options, remainder = getopt.getopt(sys.argv[1:], 'r:s:d:v8p:', [
                                                        'rate=', 
                                                        'speed=', 
                                                        'db=', 
                                                        'verbose',
                                                        'rtl',
                                                        'pipe',
                                                         ])
sample_rate = 0
verbose = False
search_size=1 # Only calulate every (search_size)'th fft
fft_peak = 7.0 # about 8.5 dB over noise
rtl = False
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
        print "WARN: pipe mode not set"
        pipe="t"
    basename="i-%.4f-%s1"%(time.time(),pipe)
    print basename
    file_name = "/dev/stdin"
else:
    file_name = remainder[0]
    basename= filename= re.sub('\.[^.]*$','',file_name)

fft_size=int(math.pow(2, 1+int(math.log(sample_rate/1000,2)))) # fft is approx 1ms long
bin_size = float(fft_size)/sample_rate * 1000 # How many ms is one fft now?

if rtl:
    struct_elem = numpy.uint8
    struct_len = numpy.dtype(struct_elem).itemsize * fft_size *2
else:
    struct_elem = numpy.complex64
    struct_len = numpy.dtype(struct_elem).itemsize * fft_size

window = numpy.blackman(fft_size)

data_hist = []
data_histlen=search_size
data_postlen=5
signal_maxlen=1+int(30/bin_size) # ~ 30 ms

fft_avg = [0.0]*fft_size
fft_hist = []
fft_histlen=500 # How many items to keep for moving average. 5 times our signal length

fft_freq = numpy.fft.fftfreq(fft_size)

print "fft_size=%d (=> %f ms)"%(fft_size,bin_size)
print "calculate fft once every %d block(s)"%(search_size)
print "require %.1f dB"%(10*math.log(fft_peak,10))

index = -1
wf=None
writepost=0
signals=0

peaks=[] # idx, postlen, file

with open(file_name, "rb") as f:
    while True:
        data = f.read(struct_len)
        if not data: break
        if len(data) != struct_len: break

        index+=1
        if index%search_size==0:
            slice = numpy.frombuffer(data, dtype=struct_elem)
            if rtl:
                slice = slice.astype(numpy.float32) # convert to float
                slice = (slice-127)/128             # Normalize
                slice = slice.view(numpy.complex64) # reinterpret as complex
                data = numpy.getbuffer(slice) # So all output formats are complex float again
            fft_result = numpy.absolute(numpy.fft.fft(slice * window))

            if len(fft_hist)>25: # grace period after start of file
                peakl= (fft_result / fft_avg)*len(fft_hist)

                for p in peaks:
                    print "[%4d,%2d,%2d]"%(p[0],p[1],index-p[2]),
                for p in peaks:
                    pi=p[0]
                    print "Peak B%4d: %4.1f dB"%(pi,10*math.log(peakl[pi],10)),
                    pa=numpy.average(peakl[pi-10:pi+10])
                    print "(avg: %4.1f dB)"%(10*math.log(pa,10)),
                    if peakl[p[0]]>fft_peak:
                        print "still peak",
                        p[1]=search_size+data_postlen
                    print
                    p[1]-=1
                    p[3].write(data)
                    if (index-p[2])==signal_maxlen:
                        print "Peak B%d @ %d too long"%(p[0],p[2])
                    if (index-p[2])<signal_maxlen:
                        # XXX: clear "area" around peak
                        w=25
                        p0=pi-w
                        if p0<0:
                            p0=0
                        p1=pi+w
                        if p1>=fft_size:
                            p1=fft_size-1
                        peakl[p0:p1]=[0]*(p1-p0)
                peakidx=numpy.argmax(peakl)
                peak=peakl[peakidx]
                if(peak>fft_peak):
                    print "New peak:",
                    signals+=1
                    print "Peak t=%5d (%4.1f dB) B:%3d @ %.0f Hz"%(index*bin_size,10*math.log(peak,10),peakidx,fft_freq[peakidx]*sample_rate)
                    wf=open("%s-%07d-o%+07d.det" % (os.path.basename(basename), int(index*bin_size), fft_freq[peakidx]*sample_rate), "wb")
                    for d in data_hist:
                        wf.write(d)
                    wf.write(data)
                    writepost=search_size+data_postlen
                    peaks.append([peakidx,writepost,index,wf])

            peaks = filter(lambda e: e[1]>0, peaks)

            # keep fft in history buffer and update average
            if len(peaks)==0: # No output in progress
                fft_hist.append(fft_result)
                fft_avg+=fft_result
                if len(fft_hist)>fft_histlen:
                    fft_avg-=fft_hist[0]
                    fft_hist.pop(0)

        # keep data in history buffer
        data_hist.append(data)
        if len(data_hist)>data_histlen:
            data_hist.pop(0)

if verbose:
    print "%d signals found"%(signals)

