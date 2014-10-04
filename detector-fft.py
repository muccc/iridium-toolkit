#!/usr/bin/python
import struct
import sys
import math
import numpy
import os.path
from itertools import izip
import re
import matplotlib.pyplot as plt

def grouped(iterable, n):
    "s -> (s0,s1,s2,...sn-1), (sn,sn+1,sn+2,...s2n-1), (s2n,s2n+1,s2n+2,...s3n-1), ..."
    return izip(*[iter(iterable)]*n)

file_name = sys.argv[1]
basename= filename= re.sub('\.[^.]*$','',file_name)

# roughtly a 1ms window
sample_rate = 2000000
fft_size = 2048
bin_size = int(float(fft_size)/sample_rate * 1000) * 5
min_std = 1.7

struct_fmt = '<' +  fft_size * 5 * '2f'
struct_len = struct.calcsize(struct_fmt)
struct_unpack = struct.Struct(struct_fmt).unpack_from

window = numpy.blackman(fft_size)
bins = []

file_size = os.path.getsize(file_name)/8./fft_size/5
reported_percentage = -100

index = 0

with open(file_name, "rb") as f:
    #f.read(struct_len)
    #bins_avg.append(0)
    #bins.append(0)
    while True:
        data = f.read(struct_len)
        if not data: break
        if len(data) != struct_len: break
        s = struct_unpack(data)
        slice = []
        index += 1
        for i, q in grouped(s[:fft_size*2], 2):
            slice.append(complex(i, q))

        fft_result = numpy.fft.fft(slice * window)
        #fft_result = numpy.fft.fft(slice)
        bins.append(max([abs(x) for x in fft_result]))
        #bins.append(numpy.std(mag))
        #bins_avg.append(numpy.average(mag))
        #bins.append(numpy.average(mag))
        percentage = int((index/file_size)*100)
        if reported_percentage < percentage - 4:
            print percentage, '%'
            reported_percentage = percentage

print len(bins)

#plt.plot(range(0, fft_size * len(bins), fft_size), bins, 'b')
#plt.show()

#avg = numpy.average(bins_avg)
#std = numpy.std(bins_avg)

avg = numpy.average(bins)
std = numpy.std(bins)

print "avg:", avg
print "std:", std
active_bins = []

for i in range(len(bins)):
    if bins[i] > avg + min_std * std:
        if not active_bins or (
                (i-1) not in active_bins[-1]
                and (i-2) not in active_bins[-1]
                and (i-3) not in active_bins[-1]):
            print "%d ms: %f" % (i * bin_size, bins[i])#, bins_avg[i]
            active_bins.append([i])
        else:
            active_bins[-1].append(i)

with open(file_name, "rb") as f:
    for abins in active_bins:
        start_bin = abins[0]
        if start_bin > 3: start_bin -= 5
        f.seek(struct_len * start_bin)
        with open("%s-%07d.det" % (os.path.basename(basename), start_bin * bin_size), "wb") as wf:
            wf.write(f.read(struct_len * (len(abins) + 10)))

#plt.plot(range(0, bin_size * len(bins), bin_size), bins, 'b')
#plt.plot(range(0, bin_size * len(bins), bin_size), bins_avg, 'g')

#for abins in active_bins:
#    bin = abins[0]
#    plt.plot([bin * bin_size], [bins[bin]], 'rs')
#plt.show()

