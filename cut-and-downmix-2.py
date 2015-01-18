#!/usr/bin/env python
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
import iq
import getopt

#import matplotlib.pyplot as plt

options, remainder = getopt.getopt(sys.argv[1:], 'o:c:r:v', ['offset=', 
                                                         'center=',
                                                         'rate=',
                                                         'verbose',
                                                         ])
file_name = remainder[0]
basename= filename= re.sub('\.[^.]*$','',file_name)

f_off=0

center= 1626270833
sample_rate = 2000000
symbols_per_second = 25000
preamble_length = 64

for opt, arg in options:
    if opt in ('-o', '--offset'):
        f_off = int(arg)
    elif opt in ('-c', '--center'):
        center = int(arg)
    elif opt in ('-r', '--rate'):
        sample_rate = int(arg)
    elif opt == '-v':
        verbose = True

fft_length = int(math.pow(2, int(math.log(sample_rate/symbols_per_second*preamble_length,2))))
#fft_length = int(sample_rate/symbols_per_second*preamble_length*0.85)
#fft_length = int(sample_rate/symbols_per_second*preamble_length*1)
fft_step = fft_length / 50
skip = fft_length / 20
skip = 0

print 'fft_length', fft_length
struct_len = 8

def normalize(v):
    m = max(v)

    return [x/m for x in v]

def fft(slice, fft_len=None):
    if fft_len:
        fft_result = numpy.fft.fft(slice, fft_len)
    else:
        fft_result = numpy.fft.fft(slice)

    fft_freq = numpy.fft.fftfreq(len(fft_result))
    fft_result = numpy.fft.fftshift(fft_result)
    fft_freq = numpy.fft.fftshift(fft_freq)

    return (fft_result, fft_freq)


def signal_start(signal):
    max_fft = []
    l = []
    for i in range(0, len(signal), fft_step):
        slice = signal[i:i+fft_length]
        #fft_result = numpy.fft.fft(slice * numpy.blackman(len(slice)))
        fft_result, fft_freq = fft(slice)

        max_mag = numpy.amax(numpy.absolute(fft_result))
        max_fft.append(max_mag)
        l.append(i)
    #plt.plot(l, normalize(max_fft))

    avg = numpy.average(max_fft)
    max_fft = [x if x > avg else 0 for x in max_fft]
    #plt.plot(l, normalize(max_fft))

    start = next(i for i, j in enumerate(max_fft) if j)
    stop = next(i for i, j in enumerate(max_fft[start:]) if not j) + start

    m = max_fft[start:stop].index(max(max_fft[start:stop])) + start
    t = m * fft_step

    #plt.plot(t, 1, 'b*')

    return t

signal = iq.read(file_name)
#signal_mag = [abs(x) for x in signal]
#plt.plot(normalize(signal_mag))
begin = signal_start(signal)
print 'begin', begin

# Skip a few samples to have a clean signal
signal = signal[begin + skip:]
#signal = signal[begin:]
preamble = signal[:fft_length]

#plt.plot([begin+skip, begin+skip], [0, 1], 'r')
#plt.plot([begin+skip+fft_length, begin+skip+fft_length], [0, 1], 'r')

preamble = preamble * numpy.blackman(len(preamble))
# Increase size of FFT to inrease resolution
fft_result, fft_freq = fft(preamble, len(preamble) * 16)
print 'binsize', (fft_freq[100] - fft_freq[101]) * sample_rate

# Use magnitude of FFT to detect maximum and correct the used bin
mag = numpy.absolute(fft_result)
max_index = numpy.argmax(mag)

print 'max_index', max_index
print 'max_value', fft_result[max_index]

print 'offset', fft_freq[max_index] * sample_rate

# see http://www.embedded.com/design/configurable-systems/4007643/DSP-Tricks-Spectral-peak-location-algorithm
#Xmk = fft_result[max_index]
#Xmkp1 = fft_result[max_index+1]
#Xmkm1 = fft_result[max_index-1]
#correction = ((Xmkp1 - Xmkm1) / (2*Xmk - Xmkm1 - Xmkp1)).real
#real_index = max_index - correction

#see http://www.dsprelated.com/dspbooks/sasp/Quadratic_Interpolation_Spectral_Peaks.html
alpha = abs(fft_result[max_index-1])
beta = abs(fft_result[max_index])
gamma = abs(fft_result[max_index+1])
correction = 0.5 * (alpha - gamma) / (alpha - 2*beta + gamma)
real_index = max_index + correction

offset_freq = (fft_freq[math.floor(real_index)] + (real_index - math.floor(real_index)) * (fft_freq[math.floor(real_index) + 1] - fft_freq[math.floor(real_index)])) * sample_rate

print 'correction', correction
print 'corrected max', max_index - correction
print 'corrected offset', offset_freq

print 'File:',basename,"f=%10.2f"%offset_freq

offset_freq+=f_off
single_turn = sample_rate / offset_freq

shift_signal = numpy.exp(complex(0,-1)*numpy.arange(len(signal))*2*numpy.pi*offset_freq/float(sample_rate))

signal = signal*shift_signal

#plt.plot([cmath.phase(x) for x in signal[:fft_length]])
sin_avg = numpy.average(numpy.sin(numpy.angle(signal[:fft_length])))
cos_avg = numpy.average(numpy.cos(numpy.angle(signal[:fft_length])))
preamble_phase = math.atan2(sin_avg, cos_avg)
print "Original preamble phase", math.degrees(preamble_phase)

signal = signal * cmath.rect(1,math.pi/4 - preamble_phase)
#plt.plot([cmath.phase(x) for x in signal[:fft_length]])
#sin_avg = numpy.average([math.sin(cmath.phase(x)) for x in signal[:fft_length]])
#cos_avg = numpy.average([math.cos(cmath.phase(x)) for x in signal[:fft_length]])
#preamble_phase = math.atan2(sin_avg, cos_avg)
#print "Corrected preamble phase", math.degrees(preamble_phase)

#print numpy.average([x.real for x in signal[:fft_length]])
#print numpy.average([x.imag for x in signal[:fft_length]])

#print max(([abs(x.real) for x in signal]))
#print max(([abs(x.imag) for x in signal]))

ntaps= 161 # 10001, 1001, 161, 41
rrc = filters.rrcosfilter(ntaps, 0.4, 1./symbols_per_second, sample_rate)[1]
signal = scipy.signal.convolve(signal, rrc, 'same')

#plt.plot([x.real for x in signal])
#plt.plot([x.imag for x in signal])
print "preamble I avg",numpy.average(signal[:fft_length].real)
print "preamble Q avg",numpy.average(signal[:fft_length].imag)

#print max(([abs(x.real) for x in signal]))
#print max(([abs(x.imag) for x in signal]))

iq.write("%s-f%10d.cut" % (os.path.basename(basename), center+offset_freq), signal)
print "output=","%s-f%10d.cut" % (os.path.basename(basename), center+offset_freq)
#plt.plot(numpy.absolute(fft_result))
#plt.plot(fft_freq, numpy.absolute(fft_result))
#plt.plot([], [bins[bin]], 'rs')
#plt.plot(mag)
#plt.plot(preamble)
#plt.show()
