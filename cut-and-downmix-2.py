#!/usr/bin/env python
# vim: set ts=4 sw=4 tw=0 et pm=:
import struct
import sys
import math
import numpy
import os.path
import cmath
import filters
import re
import iq
import getopt
#import matplotlib.pyplot as plt

options, remainder = getopt.getopt(sys.argv[1:], 'o:w:c:r:s:v', ['offset=',
                                                         'window=',
                                                         'center=',
                                                         'rate=',
                                                         'search-depth=',
                                                         'verbose',
                                                         ])
file_name = remainder[0]
basename= filename= re.sub('\.[^.]*$','',file_name)

center= 1626270833
sample_rate = 2000000
symbols_per_second = 25000
preamble_length = 64
search_offset = None
search_window = None
search_depth = 0.007

for opt, arg in options:
    if opt in ('-o', '--search-offset'):
        search_offset = int(arg)
    if opt in ('-w', '--search-window'):
        search_window = int(arg)
    elif opt in ('-c', '--center'):
        center = int(arg)
    elif opt in ('-r', '--rate'):
        sample_rate = int(arg)
    elif opt in ('-s', '--search'):
        search_depth = float(arg)
    elif opt == '-v':
        verbose = True

if search_offset and search_window:
    # Compute the percentage of the signal in which we are
    # interested in. fft_lower_bound and fft_upper_bound will
    # varry between 0 and 1
    fft_lower_bound = (search_offset - search_window / 2.) / sample_rate + 0.5
    fft_upper_bound = (search_offset + search_window / 2.) / sample_rate + 0.5
    if fft_lower_bound < 0:
        fft_lower_bound = 0.
    if fft_upper_bound > 1:
        fft_upper_bound = 1.

    if fft_lower_bound > 1 or fft_upper_bound < 0:
        sys.stderr.write("Inconsistent window selected.\n")
        sys.exit(1)
else:
    fft_lower_bound = None
    fft_upper_bound = None

fft_length = int(math.pow(2, int(math.log(sample_rate/symbols_per_second*preamble_length,2))))
fft_step = fft_length / 50
skip = 0

print 'sample_rate', sample_rate
print 'fft_length', fft_length
struct_len = 8

def normalize(v):
    m = max(v)

    return [x/m for x in v]

fft_windows = {}

def fft(slice, fft_len=None):
    if fft_len:
        fft_result = numpy.fft.fft(slice, fft_len)
    else:
        fft_result = numpy.fft.fft(slice)

    fft_freq = numpy.fft.fftfreq(len(fft_result))
    fft_result = numpy.fft.fftshift(fft_result)
    fft_freq = numpy.fft.fftshift(fft_freq)

    if fft_lower_bound and fft_upper_bound:
        # Build a window so we can mask out parts of the fft in which
        # we are not interested
        if len(fft_result) not in fft_windows:
            lower_stop_count = int(len(fft_result) * fft_lower_bound)
            upper_stop_count = int(len(fft_result) * (1 - fft_upper_bound))
            pass_count = len(fft_result) - lower_stop_count - upper_stop_count
            fft_window = [0] * lower_stop_count
            fft_window += [1] * pass_count
            fft_window += [0] * upper_stop_count
            fft_windows[len(fft_result)] = numpy.array(fft_window)

        # Mask parts of the signal which are not relevant
        fft_result *= fft_windows[len(fft_result)]
    return (fft_result, fft_freq)

def signal_start(signal):
    max_fft = []
    l = []
    stop = int(search_depth * sample_rate)
    if stop > len(signal):
        stop = len(signal)
    for i in range(0, stop, fft_step):
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

def cut_and_downmix():
    signal = iq.read(file_name)
    #signal_mag = [abs(x) for x in signal]
    #plt.plot(normalize(signal_mag))
    begin = signal_start(signal)
    print 'begin', begin

    # Skip a few samples to have a clean signal
    signal = signal[begin + skip:]
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

    single_turn = sample_rate / offset_freq

    shift_signal = numpy.exp(complex(0,-1)*numpy.arange(len(signal))*2*numpy.pi*offset_freq/float(sample_rate))

    signal = signal*shift_signal

    #plt.plot([cmath.phase(x) for x in signal[:fft_length]])
    sin_avg = numpy.average(numpy.sin(numpy.angle(signal[:fft_length])))
    cos_avg = numpy.average(numpy.cos(numpy.angle(signal[:fft_length])))
    preamble_phase = math.atan2(sin_avg, cos_avg)
    print "Original preamble phase", math.degrees(preamble_phase)

    # Multiplying with a complex number on the unit circle
    # just changes the angle.
    # See http://www.mash.dept.shef.ac.uk/Resources/7_6multiplicationanddivisionpolarform.pdf
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
    signal = numpy.convolve(signal, rrc, 'same')

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

if __name__ == "__main__":
    cut_and_downmix()
