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

def grouped(iterable, n):
    "s -> (s0,s1,s2,...sn-1), (sn,sn+1,sn+2,...s2n-1), (s2n,s2n+1,s2n+2,...s3n-1), ..."
    return izip(*[iter(iterable)]*n)

options, remainder = getopt.getopt(sys.argv[1:], 'r:s:d:v8', [
                                                        'rate=', 
                                                        'speed=', 
                                                        'db=', 
                                                        'verbose',
                                                        'rtl',
                                                         ])
sample_rate = 0
verbose = False
search_size=1 # Only calulate every (search_size)'th fft
fft_peak = 7.0 # about 8.5 dB over noise
rtl = False

for opt, arg in options:
    if opt in ('-r', '--rate'):
        sample_rate = int(arg)
    if opt in ('-s', '--speed'):
        search_size = int(arg)
    if opt in ('-d', '--db'):
        fft_peak = pow(10,float(arg)/10)
    elif opt in ('-v', '--verbose'):
        verbose = True
    elif opt in ('-8', '--rtl'):
        rtl = True

if sample_rate == 0:
    print "Sample rate missing!"
    exit(1)

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
data_histlen=1
data_postlen=5
signal_maxlen=30

fft_avg = [0.0]*fft_size
fft_hist = []
fft_histlen=100 # How many items to keep for moving average. 5 times our signal length

fft_freq = numpy.fft.fftfreq(fft_size)

print "fft_size=%d (=> %f ms)"%(fft_size,bin_size)
print "calculate fft once every %d block(s)"%(search_size)
print "require %.1f dB"%(10*math.log(fft_peak,10))

index = -1
wf=None
writepost=0
signals=0
sig_len=0

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
                slice = slice-127                   # Normalize
                slice = slice.view(numpy.complex64) # reinterpret as complex
                data = numpy.getbuffer(slice) # So all output formats are complex float again
            fft_result = numpy.absolute(numpy.fft.fft(slice * window))

            if len(fft_hist)>2: # grace period after start of file
                peakl= (fft_result / fft_avg)*len(fft_hist)
                peakidx=numpy.argmax(peakl)
                peak=peakl[peakidx]
                if(peak>fft_peak):
                    if wf == None:
                        signals+=1
                        print "Peak t=%5d (%4.1f dB) B:%3d @ %.0f Hz"%(index*bin_size,10*math.log(peak,10),peakidx,fft_freq[peakidx]*sample_rate)
                        wf=open("%s-%07d.det" % (os.path.basename(basename), int(index*bin_size)), "wb")
#                        wf=open("%s-%07d-P%06d.d2" % (os.path.basename(basename), int((index-len(data_hist))*bin_size), fft_freq[peakidx]*sample_rate), "wb")
                        for d in data_hist:
                            wf.write(d)
                        writepost=search_size+data_postlen
                    else:
                        if verbose:
                            print "     t=%5d (%4.1f dB) B:%3d @ %.0f Hz"%(index*bin_size,10*math.log(peak,10),peakidx,fft_freq[peakidx]*sample_rate)
                        writepost=search_size+data_postlen

            # keep fft in history buffer and update average
            if wf==None or sig_len>signal_maxlen:
                if sig_len>signal_maxlen:
                    print "Signal too long!"
                fft_hist.append(fft_result)
                fft_avg+=fft_result
                if len(fft_hist)>fft_histlen:
                    fft_avg-=fft_hist[0]
                    fft_hist.pop(0)

        if writepost>0:
            wf.write(data)
            sig_len+=1
            writepost-=1
            if writepost==0:
                if verbose:
                    print
                wf.close()
                sys.stdout.flush()
                wf=None
                sig_len=0
        # keep data in history buffer
        data_hist.append(data)
        if len(data_hist)>data_histlen:
            data_hist.pop(0)

if verbose:
    print "%d signals found"%(signals)

