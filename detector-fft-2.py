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

options, remainder = getopt.getopt(sys.argv[1:], 'r:s:d:v', [
                                                        'rate=', 
                                                        'speed=', 
                                                        'db=', 
                                                        'verbose',
                                                         ])
sample_rate = 0
verbose = False
search_size=1 # Only calulate every (search_size)'th fft
fft_peak = 7.0 # about 8.5 dB over noise

for opt, arg in options:
    if opt in ('-r', '--rate'):
        sample_rate = int(arg)
    if opt in ('-s', '--speed'):
        search_size = int(arg)
    if opt in ('-d', '--db'):
        fft_peak = pow(10,float(arg)/10)
    elif opt in ('-v', '--verbose'):
        verbose = True

if sample_rate == 0:
    print "Sample rate missing!"
    exit(1)

file_name = remainder[0]
basename= filename= re.sub('\.[^.]*$','',file_name)

fft_size=int(math.pow(2, 1+int(math.log(sample_rate/1000,2)))) # fft is approx 1ms long
bin_size = float(fft_size)/sample_rate * 1000 # How many ms is one fft now?

struct_fmt = '<' + fft_size * '2f'
struct_len = struct.calcsize(struct_fmt)
struct_unpack = struct.Struct(struct_fmt).unpack_from

window = numpy.blackman(fft_size)

data_hist = []
data_histlen=4
data_postlen=4

fft_avg = [0.0]*fft_size
fft_hist = []
fft_histlen=50 # How many items to keep for moving average

fft_freq = numpy.fft.fftfreq(fft_size)

print "fft_size=%d (=> %f ms)"%(fft_size,bin_size)
print "calculate fft once every %d block(s)"%(search_size)
print "require %.1f dB"%(10*math.log(fft_peak,10))

index = -1
wf=None
writepost=0
signals=0

with open(file_name, "rb") as f:
    while True:
        data = f.read(struct_len)
        if not data: break
        if len(data) != struct_len: break

        index+=1
        if index%search_size==0:
            s = struct_unpack(data)
            slice = [ complex(i,q) for (i,q) in grouped(s[:fft_size*2], 2) ]
            fft_result = numpy.absolute(numpy.fft.fft(slice * window))

            if len(fft_hist)>2: # grace period after start of file
                peakl= (fft_result / fft_avg)*len(fft_hist)
                peakidx=numpy.argmax(peakl)
                peak=peakl[peakidx]
                if(peak>fft_peak):
                    if wf == None:
                        signals+=1
                        print "Peak t=%5d (%4.1f dB) @ %.0f Hz"%(index*bin_size,10*math.log(peak,10),fft_freq[peakidx]*sample_rate)
                        wf=open("%s-%07d.d2" % (os.path.basename(basename), int((index-len(data_hist))*bin_size)), "wb")
                        for d in data_hist:
                            wf.write(d)
                        writepost=search_size+data_postlen
                    else:
                        if verbose:
                            print "             (%4.1f dB) @ %.0f Hz"%(10*math.log(peak,10),fft_freq[peakidx]*sample_rate)
                        writepost+=search_size

            # keep fft in history buffer and update average
            fft_hist.append(fft_result)
            fft_avg+=fft_result
            if len(fft_hist)>fft_histlen:
                fft_avg-=fft_hist[0]
                fft_hist.pop(0)

        if writepost>0:
            wf.write(data)
            writepost-=1
            if writepost==0:
                if verbose:
                    print
                wf.close()
                wf=None
        # keep data in history buffer
        data_hist.append(data)
        if len(data_hist)>data_histlen:
            data_hist.pop(0)

if verbose:
    print "%d signals found"%(signals)

