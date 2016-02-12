import struct
import sys
import math
import numpy
import os.path
import cmath
import filters
import matplotlib.pyplot as plt
import scipy.optimize
import scipy.signal
import iridium
import scipy.interpolate
import time

F_SEARCH = 100

def normalize(v):
    m = max(v)
    return [x/m for x in v]

class ComplexSyncSearch(object):

    def __init__(self, sample_rate, verbose=False):
        self._sample_rate = sample_rate
        self._samples_per_symbol = self._sample_rate / iridium.SYMBOLS_PER_SECOND

        self._sync_words = [{},{}]
        self._sync_words[iridium.DOWNLINK][0] = self.generate_padded_sync_words(-F_SEARCH, F_SEARCH, 0, iridium.DOWNLINK)
        self._sync_words[iridium.DOWNLINK][16] = self.generate_padded_sync_words(-F_SEARCH, F_SEARCH, 16, iridium.DOWNLINK)
        self._sync_words[iridium.DOWNLINK][64] = self.generate_padded_sync_words(-F_SEARCH, F_SEARCH, 64, iridium.DOWNLINK)

        self._sync_words[iridium.UPLINK][16] = self.generate_padded_sync_words(-F_SEARCH, F_SEARCH, 16, iridium.UPLINK)

        self._verbose = verbose

    def generate_padded_sync_words(self, f_min, f_max, preamble_length, direction):
        s1 = -1-1j
        s0 = -s1

        if direction == iridium.DOWNLINK:
            sync_word = [s0] * preamble_length + [s0, s1, s1, s1, s1, s0, s0, s0, s1, s0, s0, s1]
        elif direction == iridium.UPLINK:
            sync_word = [s1, s0] * (preamble_length / 2) + [s1, s1, s0, s0, s0, s1, s0, s0, s1, s0, s1, s1]

        sync_word_padded = []

        for bit in sync_word:
            sync_word_padded += [bit]
            sync_word_padded += [0] * (self._samples_per_symbol - 1)

        # Remove the padding after the last symbol...
        sync_word_padded = sync_word_padded[:-(self._samples_per_symbol - 1)]
        
        filter = filters.rrcosfilter(161, 0.4, 1./iridium.SYMBOLS_PER_SECOND, self._sample_rate)[1]
        sync_word_padded_filtered = numpy.convolve(sync_word_padded, filter, 'full')

        sync_words_shifted = {}

        for offset in range(f_min, f_max + 1):
            shift_signal = numpy.exp(complex(0,-1)*numpy.arange(len(sync_word_padded_filtered))*2*numpy.pi*offset/float(self._sample_rate))
            sync_words_shifted[offset] = sync_word_padded_filtered * shift_signal
            sync_words_shifted[offset] = numpy.conjugate(sync_words_shifted[offset][::-1])
        
        return sync_words_shifted


        return sync_middle - len(sync_word_mag) / 2

    def estimate_sync_word_start(self, signal, direction, preamble_length=16):
        uw_start, confidence, phase = self.estimate_sync_word(signal, self._sync_words[direction][preamble_length][0], preamble_length)
        return uw_start, confidence, phase

    def estimate_sync_word(self, signal, preamble, preamble_length):
        c = scipy.signal.fftconvolve(signal, preamble, 'same')

        sync_middle = numpy.argmax(numpy.abs(c))
        confidence = numpy.abs(c[sync_middle])
        phase = numpy.angle(c[sync_middle])

        # Compensate for the symbols of the preamble
        uw_start = sync_middle + ((preamble_length - (preamble_length + iridium.UW_LENGTH) / 2)
                                    * self._samples_per_symbol + self._samples_per_symbol / 2)

        return uw_start, confidence, phase


    def estimate_sync_word_freq(self, signal, preamble_length, direction):

        if preamble_length not in self._sync_words[direction]:
            return None, None, None, None

        sync_words = self._sync_words[direction][preamble_length]

        if self._verbose:

            #plt.plot([x.real for x in signal])
            #plt.plot([x.imag for x in signal])
            #plt.show()

            offsets = range(-F_SEARCH, F_SEARCH)
            cs = []
            phases = []

            #print 'signal len', len(signal)
            #print 'sync word led', len(sync_word_shifted[0])

            for offset in offsets:
                uw_start, c, phase = self.estimate_sync_word(signal, sync_words[offset], preamble_length)
                cs.append(c)
                phases.append(phase)

            #plt.plot(normalize(cs))
            #plt.plot(phases)
            #plt.show()

            print "best freq (brute force):", offsets[numpy.argmax(cs)]
            #print "phase:", math.degrees(phases[numpy.argmax(cs)])

            #print "current phase:", math.degrees(estimate(signal, 0)[1])
            #return offsets[numpy.argmax(cs)]
        

        def f_est(freq, preambles):
            #print freq
            #c = numpy.correlate(signal, preambles[int(freq+0.5)], 'same')
            f_index = int(freq+0.5)
            c = scipy.signal.fftconvolve(signal, preambles[int(freq+0.5)], 'same')

            return -numpy.max(numpy.abs(c))

        x = numpy.linspace(-F_SEARCH, F_SEARCH, 4)
        y = [f_est(f, sync_words) for f in x]
        f = scipy.interpolate.UnivariateSpline(x, y)

        #t0 = time.time()
        #for i in range(1000):
        #    f(i%50)
        #print time.time() - t0

        freq = int(scipy.optimize.fminbound(f, -(F_SEARCH - 1), (F_SEARCH - 1), xtol=2) + 0.5)
        if self._verbose:
            print "best freq (interpolate, optimize):", freq

        if self._verbose:
            freq = numpy.argmax(cs) - F_SEARCH

        if abs(freq) > F_SEARCH * 0.9:
            return None, None, None, None

        uw_start, confidence, phase = self.estimate_sync_word(signal, sync_words[freq], preamble_length)

        if self._verbose:
            print "phase:", phase

        return freq, phase, confidence, uw_start
