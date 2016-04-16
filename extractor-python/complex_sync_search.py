import struct
import sys
import math
import numpy
import os.path
import cmath
import filters
#import matplotlib.pyplot as plt
import scipy.optimize
import scipy.signal
import iridium

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
        
        filter = filters.rrcosfilter(161, 0.4, 1./iridium.SYMBOLS_PER_SECOND, self._sample_rate)[1]
        sync_word_padded_filtered = numpy.convolve(sync_word_padded, filter, 'full')

        sync_words_shifted = {}

        for offset in range(f_min, f_max):
            shift_signal = numpy.exp(complex(0,-1)*numpy.arange(len(sync_word_padded_filtered))*2*numpy.pi*offset/float(self._sample_rate))
            sync_words_shifted[offset] = sync_word_padded_filtered * shift_signal
            sync_words_shifted[offset] = numpy.conjugate(sync_words_shifted[offset][::-1])
        
        return sync_words_shifted


    def estimate_sync_word_start(self, signal, direction):
        
        sync_middle, confidence, _ = self.estimate_sync_word(signal, self._sync_words[direction][16][0])
        
        # Compensate for the 16 symbols of preamble
        sync_start = sync_middle + 2 * self._samples_per_symbol 

        return sync_start, confidence

    def estimate_sync_word(self, signal, preamble):
        c = scipy.signal.fftconvolve(signal, preamble, 'same')
        sync_middle = numpy.argmax(numpy.abs(c))

        return sync_middle, numpy.abs(c[sync_middle]), numpy.angle(c[sync_middle])


    def estimate_sync_word_freq(self, signal, preamble_length, direction):

        if preamble_length not in self._sync_words[direction]:
            return None, None, None

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
                _, c, phase = self.estimate_sync_word(signal, sync_words[offset])
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

        freq = int(scipy.optimize.fminbound(f_est, -(F_SEARCH - 1), (F_SEARCH - 1), args = (sync_words,), xtol=1) + 0.5)
        if self._verbose:
            print "best freq (optimize):", freq

        if self._verbose:
            freq = numpy.argmax(cs) - F_SEARCH

        if abs(freq) == F_SEARCH - 1:
            return None, None, None

        _, confidence, phase = self.estimate_sync_word(signal, sync_words[freq])

        if self._verbose:
            print "phase:", phase
        return freq, phase, confidence
