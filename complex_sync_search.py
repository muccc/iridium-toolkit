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

DOWNLINK = 0
UPLINK = 1

class ComplexSyncSearch(object):
    def __init__(self, sample_rate, rrcos=True):
        self._sample_rate = sample_rate
        self._symbols_per_second = 25000
        self._samples_per_symbol = self._sample_rate / self._symbols_per_second

        self._sync_words = [{},{}]
        self._sync_words[DOWNLINK][0] = self.generate_padded_sync_words(-20000, 20000, 0, rrcos, True)
        self._sync_words[DOWNLINK][16] = self.generate_padded_sync_words(-20000, 20000, 16, rrcos, True)
        self._sync_words[DOWNLINK][64] = self.generate_padded_sync_words(-20000, 20000, 64, rrcos, True)

        self._sync_words[UPLINK][16] = self.generate_padded_sync_words(-20000, 20000, 16, rrcos, False)

    def generate_padded_sync_words(self, f_min, f_max, preamble_length, rrcos=True, downlink=True):
        s1 = -1-1j
        s0 = -s1

        if downlink:
            sync_word = [s0] * preamble_length + [s0, s1, s1, s1, s1, s0, s0, s0, s1, s0, s0, s1]
        else:
            sync_word = [s0, s1] * (preamble_length / 2) + [s1, s0, s0, s0, s1, s0, s0, s1, s0, s1, s1, s1]
        sync_word_padded = []

        for bit in sync_word:
            sync_word_padded += [bit]
            sync_word_padded += [0] * (self._samples_per_symbol - 1)
        
        #rrcos = True
        if rrcos:
            filter = filters.rrcosfilter(161, 0.4, 1./self._symbols_per_second, self._sample_rate)[1]
            sync_word_padded_filtered = numpy.convolve(sync_word_padded, filter, 'full')
        else:
            filter = filters.rcosfilter(161, 0.4, 1./self._symbols_per_second, self._sample_rate)[1]
            sync_word_padded_filtered = sync_word_padded

        sync_words_shifted = {}

        for offset in range(f_min, f_max):
            shift_signal = numpy.exp(complex(0,-1)*numpy.arange(len(sync_word_padded_filtered))*2*numpy.pi*offset/float(self._sample_rate))
            sync_words_shifted[offset] = sync_word_padded_filtered * shift_signal
            sync_words_shifted[offset] = numpy.conjugate(sync_words_shifted[offset][::-1])
        
        return sync_words_shifted


    def estimate_sync_word_start(self, signal, preamble):
        #c = numpy.correlate(signal, preamble, 'same')
        c = scipy.signal.fftconvolve(signal, preamble, 'same')

        sync_middle = numpy.argmax(numpy.abs(c))
        sync_start = sync_middle - len(preamble) / 2

        return sync_start, numpy.abs(c[sync_middle]), numpy.angle(c[sync_middle])


    def estimate_sync_word_freq(self, signal, preamble_length, direction=DOWNLINK):
        sync_words = self._sync_words[direction][preamble_length]
        if 0:

            #plt.plot([x.real for x in signal])
            #plt.plot([x.imag for x in signal])
            #plt.show()

            offsets = range(-20000, 20000)
            cs = []
            phases = []

            #print 'signal len', len(signal)
            #print 'sync word led', len(sync_word_shifted[0])

            for offset in offsets:
                start, c, phase = self.estimate_sync_word_start(signal, sync_words[offset])
                cs.append(c)
                phases.append(phase)

            plt.plot(cs)
            #plt.plot(phases)
            plt.show()

            print "best freq (brute force):", offsets[numpy.argmax(cs)]
            #print "phase:", math.degrees(phases[numpy.argmax(cs)])

            #print "current phase:", math.degrees(estimate(signal, 0)[1])
            #return offsets[numpy.argmax(cs)]
        

        def f_est(freq, preambles):
            #print freq
            #c = numpy.correlate(signal, preambles[int(freq+0.5)], 'same')
            c = scipy.signal.fftconvolve(signal, preambles[int(freq+0.5)], 'same')
            return -numpy.max(numpy.abs(c))

        freq = int(scipy.optimize.fminbound(f_est, -20000, 20000, args = (sync_words,), xtol=1) + 0.5)
        print "best freq (optimize):", freq
        _, _, phase = self.estimate_sync_word_start(signal, sync_words[freq])

        #print "phase:", phase
        return freq, phase
