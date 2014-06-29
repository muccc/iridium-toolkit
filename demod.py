#!/usr/bin/python
# vim: set ts=4 sw=4 tw=0 et pm=:
import struct
import sys
import math
import numpy
import os.path
import cmath
import filters
import scipy.signal
import re
import sync_search
import iq
import matplotlib.pyplot as plt

def qpsk(angle):
    if angle<0: angle+=360
    sym=int(angle)/90
    off=abs(45-(angle % 90))

    if (off>20): print "Symbol offset >20"
    return sym

file_name = sys.argv[1]
basename= filename= re.sub('\.[^.]*$','',file_name)
schneider=0

if file_name == "-p":
    file_name=sys.argv[2]
    schneider=1

sample_rate = 2000000
symbols_per_second = 25000

samples_per_symbol= float(sample_rate)/float(symbols_per_second)

if int(samples_per_symbol)!=samples_per_symbol: raise Exception("Non-int sps")

samples_per_symbol=int(samples_per_symbol)

skip = 5*samples_per_symbol # beginning might be flakey

def normalize(v):
    m = max(v)

    return [x/m for x in v]

signal = iq.read(file_name)
signal_mag = [abs(x) for x in signal]

level=abs(numpy.mean(signal[skip:skip+samples_per_symbol]))
lmax=abs(numpy.max(signal[skip:skip+samples_per_symbol]))
print "level: ",level

if schneider==0:
    # Skip a few samples to have a clean signal
    print "skip: ",skip

    for i in xrange(skip,len(signal)):
        lvl= abs(signal[i])/level
        ang= cmath.phase(signal[i])/math.pi*180
        
        if lvl < 0.5:
            print "First transition is @",i
            transition=i
            break


    mag = [abs(x) for x in signal[transition:transition+samples_per_symbol]]
    peak=max(mag)
    peakidx=transition+mag.index(peak)
    print "peak is @",peakidx, " (",peak/level,")"
    start=peakidx-samples_per_symbol
else:
    start=sync_search.estimate_sync_word_start(signal, sample_rate, symbols_per_second)

i=start
bpskbits=12
symbols=[]

peaks=[complex(-lmax,0)]*len(signal)

mapping= [2,1,-2,-1]

print "len: ",len(signal)
while True:
    peaks[i]=complex(0,lmax/10.)

    sdiff=2

    try:
        cur=signal[i].real
        pre=signal[i-samples_per_symbol].real
        post=signal[i+samples_per_symbol].real
        curpre=signal[i-sdiff].real
        curpost=signal[i+sdiff].real

        if pre<0 and post<0 and cur>0:
            if curpre>cur and cur>curpost:
                print "Sampled late"
                i-=sdiff
            if curpre<cur and cur<curpost:
                print "Sampled early"
                i+=sdiff
        elif pre>0 and post>0 and cur<0:
            if curpre>cur and cur>curpost:
                print "Sampled early"
                i+=sdiff
            if curpre<cur and cur<curpost:
                print "Sampled late"
                i-=sdiff
        else:
            cur=signal[i].imag
            pre=signal[i-samples_per_symbol].imag
            post=signal[i+samples_per_symbol].imag
            post=cur
            curpre=signal[i-sdiff].imag
            curpost=signal[i+sdiff].imag

            if pre<0 and post<0 and cur>0:
                if curpre>cur and cur>curpost:
                    print "Sampled late"
                    i-=sdiff
                if curpre<cur and cur<curpost:
                    print "Sampled early"
                    i+=sdiff
            elif pre>0 and post>0 and cur<0:
                if curpre>cur and cur>curpost:
                    print "Sampled early"
                    i+=sdiff
                if curpre<cur and cur<curpost:
                    print "Sampled late"
                    i-=sdiff
    except IndexError:
        print "Last sample"

    lvl= abs(signal[i])/level
    ang= cmath.phase(signal[i])/math.pi*180
    symbol=qpsk(ang)
    symbols=symbols+[symbol]

    print "Symbol @ ",i,": ",symbol," (",ang,",",lvl,")"
    peaks[i]=complex(+lmax,mapping[symbol]*lmax/5.)
    i+=samples_per_symbol
    if i>=len(signal) : break

print "Done."

access=""
for s in symbols[:12]:
    access+=str(s)

data=""
for s in symbols[12:]:
    data+=str(s)

ok="not ok"
if access=="022220002002": ok="OK"

print "File:",basename," access: ",access," ",ok," data:",data

# Create r / phi file
#filename= re.sub('\.raw','.rphi',sys.argv[1])
#if filename == sys.argv[1]: raise Exception("filename replacement error")
#
#with open(filename, 'wb') as out:
#    signal = [item for sample
#        in signal for item
#        in [abs(sample), cmath.phase(sample)]]
#    s = "<" + len(signal) * 'f'
#    out.write(struct.Struct(s).pack(*signal))

iq.write("%s.peaks" % (os.path.basename(basename)), peaks)
