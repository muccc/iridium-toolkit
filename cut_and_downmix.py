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

def normalize(v):
    m = max(v)
    return [x/m for x in v]

class CutAndDownmix(object):
    def __init__(self, center, sample_rate, search_depth=0.007,
                    symbols_per_second=25000, preamble_length=64,
                    verbose=False):

        self._center = center
        self._sample_rate = sample_rate
        self._search_depth = search_depth
        self._symbols_per_second = symbols_per_second
        self._preamble_length = preamble_length
        self._verbose = verbose

        self._fft_length = int(math.pow(2, int(math.log(self._sample_rate/self._symbols_per_second*self._preamble_length,2))))
        self._fft_step = self._fft_length / 50
        self._skip = 0

        if self._verbose:
            print 'sample_rate', self._sample_rate
            print 'fft_length', self._fft_length

    def _update_search_window(self, search_offset, search_window):
        self._fft_windows = {}
        if search_offset and search_window:
            # Compute the percentage of the signal in which we are
            # interested in. fft_lower_bound and fft_upper_bound will
            # varry between 0 and 1
            self._fft_lower_bound = (search_offset - search_window / 2.) / self._sample_rate + 0.5
            self._fft_upper_bound = (search_offset + search_window / 2.) / self._sample_rate + 0.5
            if self._fft_lower_bound < 0:
                self._fft_lower_bound = 0.
            if self._fft_upper_bound > 1:
                self._fft_upper_bound = 1.

            if self._fft_lower_bound > 1 or self._fft_upper_bound < 0:
                raise RuntimeError("Inconsistent window selected.")
        else:
            self._fft_lower_bound = None
            self._fft_upper_bound = None

    def _fft(self, slice, fft_len=None):
        if fft_len:
            fft_result = numpy.fft.fft(slice, fft_len)
        else:
            fft_result = numpy.fft.fft(slice)

        fft_freq = numpy.fft.fftfreq(len(fft_result))
        fft_result = numpy.fft.fftshift(fft_result)
        fft_freq = numpy.fft.fftshift(fft_freq)

        if self._fft_lower_bound and self._fft_upper_bound:
            # Build a window so we can mask out parts of the fft in which
            # we are not interested
            if len(fft_result) not in self._fft_windows:
                lower_stop_count = int(len(fft_result) * self._fft_lower_bound)
                upper_stop_count = int(len(fft_result) * (1 - self._fft_upper_bound))
                pass_count = len(fft_result) - lower_stop_count - upper_stop_count
                fft_window = [0] * lower_stop_count
                fft_window += [1] * pass_count
                fft_window += [0] * upper_stop_count
                self._fft_windows[len(fft_result)] = numpy.array(fft_window)

            # Mask parts of the signal which are not relevant
            fft_result *= self._fft_windows[len(fft_result)]
        return (fft_result, fft_freq)

    def _signal_start(self, signal):
        max_fft = []
        l = []
        stop = int(self._search_depth * self._sample_rate)
        if stop > len(signal):
            stop = len(signal)
        for i in range(0, stop, self._fft_step):
            slice = signal[i:i+self._fft_length]
            #fft_result = numpy.fft.fft(slice * numpy.blackman(len(slice)))
            fft_result, fft_freq = self._fft(slice)

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
        t = m * self._fft_step

        #plt.plot(t, 1, 'b*')

        return t

    def cut_and_downmix(self, signal, search_offset=None, search_window=None, frequency_offset=0):
        self._update_search_window(search_offset, search_window)

        #signal_mag = [abs(x) for x in signal]
        #plt.plot(normalize(signal_mag))
        begin = self._signal_start(signal)
        if self._verbose:
            print 'begin', begin

        # Skip a few samples to have a clean signal
        signal = signal[begin + self._skip:]
        preamble = signal[:self._fft_length]

        #plt.plot([begin+skip, begin+skip], [0, 1], 'r')
        #plt.plot([begin+skip+self._fft_length, begin+skip+self._fft_length], [0, 1], 'r')

        preamble = preamble * numpy.blackman(len(preamble))
        # Increase size of FFT to inrease resolution
        fft_result, fft_freq = self._fft(preamble, len(preamble) * 16)
        if self._verbose:
            print 'binsize', (fft_freq[101] - fft_freq[100]) * self._sample_rate

        # Use magnitude of FFT to detect maximum and correct the used bin
        mag = numpy.absolute(fft_result)
        max_index = numpy.argmax(mag)

        if self._verbose:
            print 'max_index', max_index
            print 'max_value', fft_result[max_index]
            print 'offset', fft_freq[max_index] * self._sample_rate

        #see http://www.dsprelated.com/dspbooks/sasp/Quadratic_Interpolation_Spectral_Peaks.html
        alpha = abs(fft_result[max_index-1])
        beta = abs(fft_result[max_index])
        gamma = abs(fft_result[max_index+1])
        correction = 0.5 * (alpha - gamma) / (alpha - 2*beta + gamma)
        real_index = max_index + correction

        offset_freq = (fft_freq[math.floor(real_index)] + (real_index - math.floor(real_index)) * (fft_freq[math.floor(real_index) + 1] - fft_freq[math.floor(real_index)])) * self._sample_rate
        offset_freq+=frequency_offset

        if self._verbose:
            print 'correction', correction
            print 'corrected max', max_index - correction
            print 'corrected offset', offset_freq

            #print 'File:',basename,"f=%10.2f"%offset_freq

        single_turn = self._sample_rate / offset_freq

        # Generate a complex signal at offset_freq Hz.
        shift_signal = numpy.exp(complex(0,-1)*numpy.arange(len(signal))*2*numpy.pi*offset_freq/float(self._sample_rate))

        # Multiply the two signals, effectively shifting signal by offset_freq
        signal = signal*shift_signal

        #plt.plot([cmath.phase(x) for x in signal[:self._fft_length]])
        sin_avg = numpy.average(numpy.sin(numpy.angle(signal[:self._fft_length])))
        cos_avg = numpy.average(numpy.cos(numpy.angle(signal[:self._fft_length])))
        preamble_phase = math.atan2(sin_avg, cos_avg)
        if self._verbose:
            print "Original preamble phase", math.degrees(preamble_phase)

        # Multiplying with a complex number on the unit circle
        # just changes the angle.
        # See http://www.mash.dept.shef.ac.uk/Resources/7_6multiplicationanddivisionpolarform.pdf
        signal = signal * cmath.rect(1,math.pi/4 - preamble_phase)

        #plt.plot([cmath.phase(x) for x in signal[:self._fft_length]])
        #sin_avg = numpy.average([math.sin(cmath.phase(x)) for x in signal[:self._fft_length]])
        #cos_avg = numpy.average([math.cos(cmath.phase(x)) for x in signal[:self._fft_length]])
        #preamble_phase = math.atan2(sin_avg, cos_avg)
        #print "Corrected preamble phase", math.degrees(preamble_phase)

        #print numpy.average([x.real for x in signal[:self._fft_length]])
        #print numpy.average([x.imag for x in signal[:self._fft_length]])

        #print max(([abs(x.real) for x in signal]))
        #print max(([abs(x.imag) for x in signal]))

        ntaps= 161 # 10001, 1001, 161, 41
        ntaps= 2*int(self._sample_rate/20000)+1
        rrc = filters.rrcosfilter(ntaps, 0.4, 1./self._symbols_per_second, self._sample_rate)[1]
        signal = numpy.convolve(signal, rrc, 'same')

        #plt.plot([x.real for x in signal])
        #plt.plot([x.imag for x in signal])
        if self._verbose:
            print "preamble I avg",numpy.average(signal[:self._fft_length].real)
            print "preamble Q avg",numpy.average(signal[:self._fft_length].imag)

        #print max(([abs(x.real) for x in signal]))
        #print max(([abs(x.imag) for x in signal]))

        #plt.plot(numpy.absolute(fft_result))
        #plt.plot(fft_freq, numpy.absolute(fft_result))
        #plt.plot([], [bins[bin]], 'rs')
        #plt.plot(mag)
        #plt.plot(preamble)
        #plt.show()

        return (signal, self._center+offset_freq)

if __name__ == "__main__":

    options, remainder = getopt.getopt(sys.argv[1:], 'o:w:c:r:s:f:v', ['search-offset=',
                                                            'window=',
                                                            'center=',
                                                            'rate=',
                                                            'search-depth=',
                                                            'verbose',
                                                            'frequency-offset=',
                                                            ])
    center = None
    sample_rate = None
    symbols_per_second = 25000
    preamble_length = 64
    search_offset = None
    search_window = None
    search_depth = 0.007
    verbose = False
    frequency_offset = 0

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
        elif opt in ('-f', '--frequency-offset'):
            frequency_offset = float(arg)
        elif opt in ('-v', '--verbose'):
            verbose = True

    if sample_rate == None:
        print >> sys.stderr, "Sample rate missing!"
        exit(1)
    if center == None:
        print >> sys.stderr, "Need to specify center frequency!"
        exit(1)

    if len(remainder)==0:
        file_name = "/dev/stdin"
        basename="stdin"
    else:
        file_name = remainder[0]
        basename= filename= re.sub('\.[^.]*$','',file_name)

    signal = iq.read(file_name)

    cad = CutAndDownmix(center=center, sample_rate=sample_rate, symbols_per_second=symbols_per_second, preamble_length=preamble_length,
                            search_depth=search_depth, verbose=verbose)

    signal, freq = cad.cut_and_downmix(signal=signal, search_offset=search_offset, search_window=search_window, frequency_offset=frequency_offset)

    iq.write("%s-f%010d.cut" % (os.path.basename(basename), freq), signal)
    print "output=","%s-f%10d.cut" % (os.path.basename(basename), freq)
