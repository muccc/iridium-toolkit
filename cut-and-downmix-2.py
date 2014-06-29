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

from itertools import izip
import matplotlib.pyplot as plt

def grouped(iterable, n):
    "s -> (s0,s1,s2,...sn-1), (sn,sn+1,sn+2,...s2n-1), (s2n,s2n+1,s2n+2,...s3n-1), ..."
    return izip(*[iter(iterable)]*n)

file_name = sys.argv[1]
basename= filename= re.sub('\.[^.]*$','',file_name)

sample_rate = 2000000
symbols_per_second = 25000
preamble_length = 64
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

def signal_start(signal):
    max_fft = []
    l = []
    for i in range(0, len(signal), fft_step):
        slice = signal[i:i+fft_length]
        #fft_result = numpy.fft.fft(slice * numpy.blackman(len(slice)))
        fft_result = numpy.fft.fft(slice)
        max_mag = max([abs(x) for x in fft_result])
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

with open(file_name, "rb") as f:
    data = f.read()
    if len(data) % 8 != 0: raise Exception("Bad file len")

    struct_fmt = '<' +  len(data)/8 * '2f'
    struct_unpack = struct.Struct(struct_fmt).unpack_from
    s = struct_unpack(data)
    signal = []
    for i, q in grouped(s, 2):
        signal.append(complex(i, q))

    signal_mag = [abs(x) for x in signal]
    #plt.plot(normalize(signal_mag))
    begin = signal_start(signal)
    print 'begin', begin

    # Skip a few samples to have a clean signal
    signal = signal[begin + skip:]
    #signal = signal[begin:]
    preamble = signal[:fft_length]

    #plt.plot([begin+skip, begin+skip], [0, 1], 'r')
    #plt.plot([begin+skip+fft_length, begin+skip+fft_length], [0, 1], 'r')
    #preamble = preamble * numpy.blackman(len(preamble))

    # Increase size of FFT to inrease resolution
    preamble = preamble + [complex(0, 0)] * fft_length * 15
    #fft_length = fft_length * 16
    preamble = preamble * numpy.blackman(len(preamble))
    fft_result = numpy.fft.fft(preamble)

    # Use magnitude of FFT to detect maximum and correct the used bin
    mag = [abs(x) for x in fft_result]
    #max_index = list(fft_result.flat).index(numpy.amax(fft_result))
    max_index = mag.index(max(mag))

    print 'max_index', max_index
    print 'max_value', fft_result[max_index]

    print 'offset', float(sample_rate)/(fft_length*16)*max_index

    # see http://www.embedded.com/design/configurable-systems/4007643/DSP-Tricks-Spectral-peak-location-algorithm
    Xmk = fft_result[max_index]
    Xmkp1 = fft_result[max_index+1]
    Xmkm1 = fft_result[max_index-1]
    correction = ((Xmkp1 - Xmkm1) / (2*Xmk - Xmkm1 - Xmkp1)).real
    offset_freq = float(sample_rate)/float(fft_length * 16)*(max_index - correction)

    print 'correction', correction
    print 'corrected max', max_index - correction
    print 'corrected offset', offset_freq

    single_turn = sample_rate / offset_freq

    shift_signal = [cmath.rect(1, -float(x)/(float(sample_rate)/offset_freq) * 2 * math.pi) for x in range(len(signal))]

    signal = [x*y for x,y in zip(signal, shift_signal)]

    #plt.plot([cmath.phase(x) for x in signal[:fft_length]])
    sin_avg = numpy.average([math.sin(cmath.phase(x)) for x in signal[:fft_length]])
    cos_avg = numpy.average([math.cos(cmath.phase(x)) for x in signal[:fft_length]])
    preamble_phase = math.atan2(sin_avg, cos_avg)
    print "Original preamble phase", math.degrees(preamble_phase)

    signal = [cmath.rect(abs(x), cmath.phase(x) - preamble_phase + math.pi/4) for x in signal]
    #plt.plot([cmath.phase(x) for x in signal[:fft_length]])
    sin_avg = numpy.average([math.sin(cmath.phase(x)) for x in signal[:fft_length]])
    cos_avg = numpy.average([math.cos(cmath.phase(x)) for x in signal[:fft_length]])
    preamble_phase = math.atan2(sin_avg, cos_avg)
    print "Corrected preamble phase", math.degrees(preamble_phase)

    #print numpy.average([x.real for x in signal[:fft_length]])
    #print numpy.average([x.imag for x in signal[:fft_length]])

    #print max(([abs(x.real) for x in signal]))
    #print max(([abs(x.imag) for x in signal]))

    #rrc = filters.rrcosfilter(10001, 0.4, 1./25000., 2e6)[1]
    rrc = filters.rrcosfilter(1001, 0.4, 1./25000., 2e6)[1]
    #rrc = filters.rrcosfilter(161, 0.4, 1./25000., 2e6)[1]
    #rrc = filters.rrcosfilter(41, 0.4, 1./25000., 2e6)[1]
    signal = scipy.signal.convolve(signal, rrc)

    #plt.plot([x.real for x in signal])
    #plt.plot([x.imag for x in signal])
    print "preamble I avg",numpy.average([x.real for x in signal[:fft_length]])
    print "preamble Q avg", numpy.average([x.imag for x in signal[:fft_length]])

    #print max(([abs(x.real) for x in signal]))
    #print max(([abs(x.imag) for x in signal]))

    with open("%s-f%10d.raw" % (os.path.basename(basename), 1626270833-offset_freq), 'wb') as out:
        signal = [item for sample
                    in signal for item
                    in [sample.real, sample.imag]]
        s = "<" + len(signal) * 'f'
        out.write(struct.Struct(s).pack(*signal))
    #plt.plot(fft_result)
    #plt.plot(mag)
    #plt.plot(preamble)
    #plt.show()


