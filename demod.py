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

errors=0
nsymbols=0
def qpsk(angle):
    global errors
    global nsymbols
    nsymbols+=1
    if angle<0: angle+=360
    sym=int(angle)/90
    off=abs(45-(angle % 90))

    if (off>22):
        print "Symbol offset >22"
        errors+=1
    return sym

file_name = sys.argv[1]
schneider=0

if file_name == "-p":
    file_name=sys.argv[2]
    schneider=1

basename= filename= re.sub('\.[^.]*$','',file_name)
sample_rate = 2000000
symbols_per_second = 25000

samples_per_symbol= float(sample_rate)/float(symbols_per_second)

if int(samples_per_symbol)!=samples_per_symbol: raise Exception("Non-int sps")

samples_per_symbol=int(samples_per_symbol)

skip = 5*samples_per_symbol # beginning might be flakey

def normalize(v):
    m = max([abs(x) for x in v])
    return [x/m for x in v]

def mynormalize(v):
    reals = normalize([x.real for x in samples])
    imags = normalize([x.imag for x in samples])
    zip=[]
    for i in xrange(len(reals)):
        zip.append(complex(reals[i],imags[i]))
    return zip

signal = iq.read(file_name)
signal_mag = [abs(x) for x in signal]

level=abs(numpy.mean(signal[skip:skip+samples_per_symbol]))
lmax=abs(numpy.max(signal[skip:skip+samples_per_symbol]))
print "level: ",level
print 'lmax: ', lmax

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

    if 1:
        mag = [abs(x) for x in signal[transition:transition+samples_per_symbol]]
        peak=max(mag)
        peakidx=transition+mag.index(peak) - 6 # -6 is "magic best feeling"
        print "peak is @",peakidx, " (",peak/level,")"
    else:
        peakidx=transition-samples_per_symbol/2

    start=peakidx-samples_per_symbol
else:
    start=sync_search.estimate_sync_word_start(signal, sample_rate, symbols_per_second)

i=start
symbols=[]
samples=[]

peaks=[complex(-lmax,0)]*len(signal)

mapping= [2,1,-2,-1]

print "len: ",len(signal)
while True:
    peaks[i]=complex(-lmax,lmax/10.)

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
    samples=samples+[signal[i]]

    print "Symbol @ ",i,": ",symbol," (",ang,",",lvl,")"
    peaks[i]=complex(+lmax,mapping[symbol]*lmax/5.)
    i+=samples_per_symbol
    if i>=len(signal) : break
    if abs(signal[i]) < lmax/5:
        break

print "Done."

access=""
for s in symbols[:12]:
    access+=str(s)

data=""
oldsym=0
dataarray=[]
for s in symbols:
    bits=(s-oldsym)%4
    if bits==0:
        bits=0
    elif bits==1:
        bits=1
    elif bits==2:
        bits=3
    else:
        bits=2
    oldsym=s
    data+=str((bits&2)/2)+str(bits&1)
    dataarray+=[(bits&2)/2,bits&1]

ok=False
if access=="022220002002": ok=True
#lead_out = "0110101101111100111100010001010" # old differential decoding
lead_out = "011010110101111001110011001111"
lead_out_ok = lead_out in data
confidence = (1-float(errors)/nsymbols)*100

oks="not ok"
if ok: oks="OK"

print "File:",basename,"access: ",oks,"(",access,"), lo=", lead_out_ok, "len=",nsymbols,"confidence=%3d%%"%(confidence)
print "File:",basename,"data: ",data
if(ok and lead_out_ok and confidence >80):
    p=re.compile('.*-(\d+)-f(\d+)')
    m=p.match(basename)
    lead_out_index = data.find(lead_out)
    padding = ' ' * (289 - lead_out_index)

p=re.compile('(.*)-(\d+)-f(\d+)')
m=p.match(basename)
oks="A:no"
if ok: oks="A:OK"
los="L:no"
if lead_out_ok: los="L:OK"
if ok:
    data=data[:24]+"."+data[24:]
if lead_out_ok:
    lead_out_index = data.find(lead_out)
    data=data[:lead_out_index]+"."+data[lead_out_index:]
print "RAW:",m.group(1),m.group(2),m.group(3),oks,los,"%3d%%"%(confidence),"%3d"%(nsymbols),data

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
iq.write("%s.samples" % (os.path.basename(basename)), mynormalize(samples))
with open("%s.dsamples" % (os.path.basename(basename)), 'wb') as out:
    for c in dataarray:
        out.write(chr(c))

#if ok == 'OK' and confidence > 90 and lead_out_ok: 
#    lead_out_index = data.find(lead_out)
#    padding = ' ' * (289 - lead_out_index)
#    print "OK File:",basename,"data: ", padding + data
