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
import scipy.signal
import complex_sync_search
import time

import matplotlib.pyplot as plt

def normalize(v):
    m = max(v)
    return [x/m for x in v]

class CutAndDownmix(object):
    def __init__(self, center, input_sample_rate, search_depth=0.007,
                    symbols_per_second=25000,
                    verbose=False):

        self._center = center
        self._input_sample_rate = int(input_sample_rate)

        if self._input_sample_rate > 1000000:
            self._output_sample_rate = 1000000
            #self._output_sample_rate = 500000
            if self._input_sample_rate % self._output_sample_rate > 0:
                raise RuntimeError("If the sample rate is > 1e6, it must be a multiple of 1000000")
            self._decimation = self._input_sample_rate / self._output_sample_rate
        else:
            self._decimation = 1
            self._output_sample_rate = self._input_sample_rate

        self._search_depth = search_depth
        self._symbols_per_second = symbols_per_second
        self._output_samples_per_symbol = self._output_sample_rate/self._symbols_per_second
        self._verbose = verbose
        #self._verbose = True

        self._skip = 0
        self._search_window = None

        self._input_low_pass = scipy.signal.firwin(401, 50e3/self._input_sample_rate)
        self._low_pass2= scipy.signal.firwin(401, 10e3/self._output_sample_rate)

        self._sync_search = complex_sync_search.ComplexSyncSearch(self._output_sample_rate)
        self._foo = 1

        if self._verbose:
            print 'input sample_rate', self._input_sample_rate
            print 'output sample_rate', self._output_sample_rate

    @property
    def output_sample_rate(self):
        return self._output_sample_rate

    def _update_search_window(self, search_window):
        self._fft_windows = {}
        if not search_window == self._search_window and search_window:
            # Compute the percentage of the signal in which we are
            # interested in. fft_lower_bound and fft_upper_bound will
            # varry between 0 and 1
            self._fft_lower_bound = (-search_window / 2.) / self._output_sample_rate + 0.5
            self._fft_upper_bound = (search_window / 2.) / self._output_sample_rate + 0.5
            if self._fft_lower_bound < 0:
                self._fft_lower_bound = 0.
            if self._fft_upper_bound > 1:
                self._fft_upper_bound = 1.

            if self._fft_lower_bound > 1 or self._fft_upper_bound < 0:
                raise RuntimeError("Inconsistent window selected.")
            self._search_window = search_window
        else:
            self._fft_lower_bound = None
            self._fft_upper_bound = None
            self._search_window = None

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

    def _signal_start(self, signal, frequency_offset):
        #print "offset", frequency_offset
        #shift_signal = numpy.exp(complex(0,-1)*numpy.arange(len(signal))*2*numpy.pi*frequency_offset/float(self._output_sample_rate))
        #signal_filtered = numpy.convolve(signal * shift_signal, self._input_low_pass, mode='same')

        #frequency_offset = -frequency_offset
        #shift_signal = numpy.exp(complex(0,-1)*numpy.arange(len(self._input_low_pass))*2*numpy.pi*frequency_offset/float(self._output_sample_rate))
        #signal_filtered = numpy.convolve(signal, self._input_low_pass * shift_signal, mode='same')

        #iq.write('/tmp/signal_filtered.cfile', signal_filtered)

        #iq.write('/tmp/foo-%d.raw' % self._foo, signal)
        #iq.write('/tmp/bar-%d.raw' % self._foo, signal_filtered)
        #self._foo += 1
        #return 0;

        signal_mag = numpy.abs(signal)
        signal_mag_lp = numpy.convolve(signal_mag, self._low_pass2, mode='same')
        #plt.plot(signal_mag)
        #plt.plot(signal_mag_lp)

        #avg = numpy.average(signal_mag)
        #signal_mag = [x if x > avg else 0 for x in signal_mag_lp]
        #start = next(i for i, j in enumerate(signal_mag) if j)

        threshold = numpy.max(signal_mag_lp) * 0.7
        #start = next(i for i, j in enumerate(signal_mag_lp) if j > threshold)
        start = numpy.where(signal_mag_lp>threshold)[0][0]

        #plt.plot(l, normalize(max_fft))
        #plt.plot(start, signal_mag_lp[start], 'b*')
        #return start + ((self._output_sample_rate / self._symbols_per_second) * self._preamble_length - self._fft_length) / 2 , signal_filtered[start:]
        #plt.show()
        return start

        stop = next(i for i, j in enumerate(max_fft[start:]) if not j) + start

        m = max_fft[start:stop].index(max(max_fft[start:stop])) + start
        t = m * self._fft_step

        #plt.plot(t, 1, 'b*')
        #plt.show()

        return t

    def cut_and_downmix(self, signal, search_offset=None, search_window=None, frequency_offset=0):
        #iq.write("/tmp/foo.cfile", signal)
        shift_signal = numpy.exp(complex(0,-1)*numpy.arange(len(signal))*2*numpy.pi*search_offset/float(self._input_sample_rate))
        signal_filtered = numpy.convolve(signal * shift_signal, self._input_low_pass, mode='same')
        #iq.write("/tmp/bar.cfile", signal_filtered)
        signal = signal_filtered[::self._decimation]
        #iq.write("/tmp/baz.cfile", signal)

        center = self._center + search_offset
        #print "new center:", center
        search_offset = 0

        if center + search_offset > 1626000000:
            preamble_length = 64
        else:
            preamble_length = 16

        self._fft_length = int(math.pow(2, int(math.log(self._output_samples_per_symbol*preamble_length,2))))
        self._fft_step = self._fft_length / 10
        if self._verbose:
            print 'fft_length', self._fft_length

        self._update_search_window(search_window)

        #signal_mag = [abs(x) for x in signal]
        #plt.plot(normalize(signal_mag))
        #begin, signal = self._signal_start(signal, search_offset)
        t0 = time.time()
        begin = self._signal_start(signal[:int(self._search_depth * self._output_sample_rate)], search_offset)
        #print "_signal_start:", time.time() - t0

        if self._verbose:
            print 'begin', begin

        t0 = time.time()
        # Skip a few samples to have a clean signal
        signal = signal[begin + self._skip:]
        preamble = signal[:self._fft_length]

        """
        preamble = signal[:self._fft_length]
        preamble_black = numpy.repeat(preamble * numpy.blackman(len(preamble)), 16)
        result = numpy.correlate(preamble_black, preamble_black, 'full')
        #result = numpy.correlate(signal, signal, 'full')
        result = numpy.angle(result[result.size/2:])
        print len(result)

        start_angle = result[0]
        count = 0
        if result[1] > 0:
            dir = 1
        else:
            dir = -1

 
        #for i in range(int(len(result) * 0.75)):
        for i in range(len(result)):
            if i == 0:
                continue

            if dir == 1:
                if result[i] > 0 and result[i-1] < 0:
                    count += 1
                    max_i = i
            else:
                if result[i] < 0 and result[i-1] > 0:
                    count += 1
                    max_i = i

        x0 = float(max_i - 1)
        x1 = float(max_i)
        y0 = result[max_i - 1]
        y1 = result[max_i]

        int_i = -y0 * (x1-x0)/(y1-y0) + x0

        guessed = dir * self._output_sample_rate / ((int_i)/float(count)) * 16
        print "guessed offset", guessed
        #plt.plot(result)
        #plt.show()
        """

        #signal = signal[:begin + self._fft_length/4]
        #preamble = signal[:self._fft_length]

        #plt.plot([begin+skip, begin+skip], [0, 1], 'r')
        #plt.plot([begin+skip+self._fft_length, begin+skip+self._fft_length], [0, 1], 'r')

        preamble = preamble * numpy.blackman(len(preamble))
        # Increase size of FFT to inrease resolution
        fft_result, fft_freq = self._fft(preamble, len(preamble) * 16)
        if self._verbose:
            print 'binsize', (fft_freq[101] - fft_freq[100]) * self._output_sample_rate

        # Use magnitude of FFT to detect maximum and correct the used bin
        mag = numpy.absolute(fft_result)
        max_index = numpy.argmax(mag)

        if self._verbose:
            print 'max_index', max_index
            print 'max_value', fft_result[max_index]
            print 'offset', fft_freq[max_index] * self._output_sample_rate

        #see http://www.dsprelated.com/dspbooks/sasp/Quadratic_Interpolation_Spectral_Peaks.html
        alpha = abs(fft_result[max_index-1])
        beta = abs(fft_result[max_index])
        gamma = abs(fft_result[max_index+1])
        correction = 0.5 * (alpha - gamma) / (alpha - 2*beta + gamma)
        real_index = max_index + correction

        #print "fft:", time.time() - t0

        t0 = time.time()
        offset_freq = (fft_freq[math.floor(real_index)] + (real_index - math.floor(real_index)) * (fft_freq[math.floor(real_index) + 1] - fft_freq[math.floor(real_index)])) * self._output_sample_rate
        offset_freq+=frequency_offset

        if self._verbose:
            print 'correction', correction
            print 'corrected max', max_index - correction
            print 'corrected offset', offset_freq

            #print 'File:',basename,"f=%10.2f"%offset_freq

        #single_turn = self._output_sample_rate / offset_freq
        #offset_freq = guessed
        # Generate a complex signal at offset_freq Hz.
        shift_signal = numpy.exp(complex(0,-1)*numpy.arange(len(signal))*2*numpy.pi*offset_freq/float(self._output_sample_rate))

        # Multiply the two signals, effectively shifting signal by offset_freq
        signal = signal*shift_signal
        #print "shift:", time.time() - t0
        t0 = time.time()

        #print "Sync word start after shift:", complex_sync_search.estimate_sync_word_start(signal, self._output_sample_rate)
        offset2, phase = self._sync_search.estimate_sync_word_freq(signal[:(preamble_length+16)*self._output_samples_per_symbol], preamble_length)
        offset2 = -offset2
        shift_signal = numpy.exp(complex(0,-1)*numpy.arange(len(signal))*2*numpy.pi*offset2/float(self._output_sample_rate))
        signal = signal*shift_signal
        #offset2 = complex_sync_search.estimate_sync_word_freq(signal[:32*self._output_samples_per_symbol], self._output_sample_rate)
        offset_freq += offset2
        #print "shift2:", time.time() - t0

        #plt.plot([cmath.phase(x) for x in signal[:self._fft_length]])
        sin_avg = numpy.average(numpy.sin(numpy.angle(signal[:self._fft_length])))
        cos_avg = numpy.average(numpy.cos(numpy.angle(signal[:self._fft_length])))
        preamble_phase = math.atan2(sin_avg, cos_avg)
        if self._verbose:
            print "Original preamble phase", math.degrees(preamble_phase)

        # Multiplying with a complex number on the unit circle
        # just changes the angle.
        # See http://www.mash.dept.shef.ac.uk/Resources/7_6multiplicationanddivisionpolarform.pdf
        #signal = signal * cmath.rect(1,math.pi/4 - preamble_phase)
        signal = signal * cmath.rect(1,-phase)

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
        ntaps= 2*int(self._output_sample_rate/20000)+1
        rrc = filters.rrcosfilter(ntaps, 0.4, 1./self._symbols_per_second, self._output_sample_rate)[1]
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

        #return (signal, self._center+offset_freq+search_offset)
        return (signal, center+offset_freq)

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

    cad = CutAndDownmix(center=center, input_sample_rate=sample_rate, symbols_per_second=symbols_per_second,
                            search_depth=search_depth, verbose=verbose)

    signal, freq = cad.cut_and_downmix(signal=signal, search_offset=search_offset, search_window=search_window, frequency_offset=frequency_offset)

    iq.write("%s-f%010d.cut" % (os.path.basename(basename), freq), signal)
    print "output=","%s-f%10d.cut" % (os.path.basename(basename), freq)
