#!/usr/bin/env python
# coding: utf-8
# vim: set ts=4 sw=4 tw=0 et fenc=utf8 pm=:
import struct
import sys
import math
import numpy
import os.path
import cmath
import filters
import re
import sync_search
import iq
import getopt

errors=0
nsymbols=0

def qpsk(phase):
    global errors
    global nsymbols
    nsymbols+=1
    phase = phase % 360

    # In theory we should only see 0, 90, 180 and 270 here.
    sym=int(phase)/90
    #print "symbol", sym

    off=(45-(phase % 90))
    if (abs(off)>22):
        print "Symbol offset >22"
        errors+=1

    return sym,off

options, remainder = getopt.getopt(sys.argv[1:], 'r:cv', [
                                                         'rate=',
                                                         'use-correlation',
                                                         'verbose',
                                                         ])

use_correlation=False
sample_rate = 2000000
symbols_per_second = 25000

for opt, arg in options:
    if opt in ('-r', '--rate'):
        sample_rate=int(arg)
    elif opt in ('-v', '--verbose'):
        verbose = True
    elif opt in ('-c', '--use-correlation'):
        use_correlation=True

file_name = remainder[0]
basename= filename= re.sub('\.[^.]*$','',file_name)

print "File:",basename
print "rate:",sample_rate
print "symbol rate:",symbols_per_second

samples_per_symbol= float(sample_rate)/float(symbols_per_second)

if int(samples_per_symbol)!=samples_per_symbol: raise Exception("Non-int sps")

samples_per_symbol=int(samples_per_symbol)

print "samples per symbol:",samples_per_symbol

skip = 5*samples_per_symbol # beginning might be flaky

def normalize(v):
    m = max([abs(x) for x in v])
    return [x/m for x in v]

def mynormalize(v):
    reals = normalize([x.real for x in v])
    imags = normalize([x.imag for x in v])
    zip=[]
    for i in xrange(len(reals)):
        zip.append(complex(reals[i],imags[i]))
    return zip

signal = iq.read(file_name)
signal_mag = [abs(x) for x in signal]

level=abs(numpy.mean(signal[skip:skip+samples_per_symbol]))
lmax=abs(numpy.max(signal[skip:skip+samples_per_symbol]))
print "level:",level
print 'lmax:', lmax

if use_correlation:
    start=sync_search.estimate_sync_word_start(signal, sample_rate, symbols_per_second)
    print "correlated start of sync word", start
else:
    # Skip a few samples to have a clean signal
    print "skip:",skip

    for i in xrange(skip,len(signal)):
        lvl= abs(signal[i])/level
        ang= cmath.phase(signal[i])/math.pi*180
        
        if lvl < 0.5:
            print "First transition is @",i
            transition=i
            break

    if 1:
        mag = [abs(x) for x in signal[transition:transition+samples_per_symbol]]
        peak=max(mag)
        peakidx=transition+mag.index(peak) - 6 # -6 is "magic best feeling"
        print "peak is @",peakidx, " (",peak/level,")"
    else:
        peakidx=transition-samples_per_symbol/2

    start=peakidx-samples_per_symbol

i=start
symbols=[]
samples=[]

#Graphical debugging stuff (the *.peaks file)
peaks=[complex(-lmax,0)]*len(signal)
mapping= [2,1,-2,-1] # mapping: symbols->*.peaks output

print "len:",len(signal)
phase=0 # Current phase offset
alpha=2 # How many degrees is still fine.

delay=0
sdiff=2 # Timing check difference

if(samples_per_symbol<20):
    sdiff=1

while True:
    peaks[i]=complex(-lmax,lmax/10.)

    # Adjust our sample rate to reality
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
                delay-=sdiff
            if curpre<cur and cur<curpost:
                print "Sampled early"
                i+=sdiff
                delay-=sdiff
        elif pre>0 and post>0 and cur<0:
            if curpre>cur and cur>curpost:
                print "Sampled early"
                i+=sdiff
                delay+=sdiff
            if curpre<cur and cur<curpost:
                print "Sampled late"
                i-=sdiff
                delay-=sdiff
        else:
            cur=signal[i].imag
            pre=signal[i-samples_per_symbol].imag
            post=signal[i+samples_per_symbol].imag
            curpre=signal[i-sdiff].imag
            curpost=signal[i+sdiff].imag

            if pre<0 and post<0 and cur>0:
                if curpre>cur and cur>curpost:
                    print "Sampled late"
                    i-=sdiff
                    delay-=sdiff
                if curpre<cur and cur<curpost:
                    print "Sampled early"
                    i+=sdiff
                    delay+=sdiff
            elif pre>0 and post>0 and cur<0:
                if curpre>cur and cur>curpost:
                    print "Sampled early"
                    i+=sdiff
                    delay+=sdiff
                if curpre<cur and cur<curpost:
                    print "Sampled late"
                    i-=sdiff
                    delay-=sdiff
    except IndexError:
        print "Last sample"

    lvl= abs(signal[i])/level
    ang= cmath.phase(signal[i])/math.pi*180
    symbol,offset =qpsk(ang+phase)
    if(offset>alpha):
        try:
            peaks[i+samples_per_symbol/10]=complex(-lmax*0.8,0);
        except IndexError:
            print "Last sample"
        print "offset forward"
        phase+=1
    if(offset<-alpha):
        peaks[i-samples_per_symbol/10]=complex(-lmax*0.8,0);
        print "offset backward"
        phase-=1

    symbols=symbols+[symbol]
    samples=samples+[signal[i]]

    print "Symbol @%06d (%3d°,%3.0f%%)=%d delay=%d phase=%d"%(i,ang%360,lvl*100,symbol,delay,phase)
    peaks[i]=complex(+lmax,mapping[symbol]*lmax/5.)
    i+=samples_per_symbol
    if i>=len(signal) : break
    if abs(signal[i]) < lmax/5:
        break

print "Done."

access=""
for s in symbols[:12]:
    access+=str(s)

# Do gray code on symbols
data=""
oldsym=0
dataarray=[]
for s in symbols:
    bits=(s-oldsym)%4
    if bits==0:
        bits=0
    elif bits==1:
        bits=2
    elif bits==2:
        bits=3
    else:
        bits=1
    oldsym=s
    data+=str((bits&2)/2)+str(bits&1)
    dataarray+=[(bits&2)/2,bits&1]

access_ok=False
if access=="022220002002": access_ok=True

lead_out = "011010110101111001110011001111"
lead_out = "100101111010110110110011001111"
lead_out_ok = lead_out in data

confidence = (1-float(errors)/nsymbols)*100

print "access:",access_ok,"(%s)"%access
print "leadout:",lead_out_ok
print "len:",nsymbols
print "confidence:",confidence
print "data:",data
print "final delay",delay
print "final phase",phase

# Nice output format
p=re.compile('(.*?)-(\d+)(?:-o[-+]\d+)?-f(\d+)')
m=p.match(basename)
if(m):
    rawfile=m.group(1)
    timestamp=int(m.group(2))
    freq=int(m.group(3))
else:
    rawfile=basename
    timestamp=0
    freq=0
print "raw filename:",rawfile
print "base freq:",freq

if access_ok:
    data="<"+data[:24]+"> "+data[24:]

if lead_out_ok:
    lead_out_index = data.find(lead_out)
    data=data[:lead_out_index]+"["+data[lead_out_index:lead_out_index+len(lead_out)]+"]"  +data[lead_out_index+len(lead_out):]

data=re.sub(r'([01]{32})',r'\1 ',data)
print "RAW: %s %07d %010d A:%s L:%s %3d%% %.3f %3d %s"%(rawfile,timestamp,freq,("no","OK")[access_ok],("no","OK")[lead_out_ok],confidence,level,(nsymbols-12),data)

if 0: # Create r / phi file
    with open("%s.rphi" % (os.path.basename(basename)), 'wb') as out:
        signal = [item for sample
            in signal for item
            in [abs(sample), cmath.phase(sample)]]
        s = "<" + len(signal) * 'f'
        out.write(struct.Struct(s).pack(*signal))

if 1: # The graphical debugging file
    iq.write("%s.peaks" % (os.path.basename(basename)), peaks)

if 0: # The actual samples we used
    iq.write("%s.samples" % (os.path.basename(basename)), mynormalize(samples))

if 1: # The data bitstream
    with open("%s.data" % (os.path.basename(basename)), 'wb') as out:
        for c in dataarray:
            out.write(chr(c))
