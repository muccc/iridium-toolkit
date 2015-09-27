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


class ComplexSyncSearch(object):
    def __init__(self, sample_rate, rrcos=True):
        self._sample_rate = sample_rate
        self._symbols_per_second = 25000
        self._samples_per_symbol = self._sample_rate / self._symbols_per_second

        self._sync_words = {}
        self._sync_words[0] = self.generate_padded_sync_words(-1000, 1000, 0, rrcos)
        self._sync_words[16] = self.generate_padded_sync_words(-1000, 1000, 16, rrcos)
        self._sync_words[64] = self.generate_padded_sync_words(-1000, 1000, 64, rrcos)

    def generate_padded_sync_words(self, f_min, f_max, preamble_length, rrcos=True):
        s1 = -1-1j
        s0 = -s1

        sync_word = [s0] * preamble_length + [s0, s1, s1, s1, s1, s0, s0, s0, s1, s0, s0, s1]
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


    def estimate_sync_word_start(self, signal, preamble_length, offset=0):
        #c = numpy.correlate(signal, sync_word_shifted[offset], 'same')
        c = scipy.signal.fftconvolve(signal, self._sync_words[preamble_length][offset], 'same')

        sync_middle = numpy.argmax(numpy.abs(c))
        sync_start = sync_middle - len(self._sync_words[preamble_length][offset]) / 2

        return sync_start, numpy.abs(c[sync_middle]), numpy.angle(c[sync_middle])


    def estimate_sync_word_freq(self, signal, preamble_length):
        if 0:
            offsets = range(-1000, 1000)
            cs = []
            phases = []

            #print 'signal len', len(signal)
            #print 'sync word led', len(sync_word_shifted[0])

            for offset in offsets:
                start, c, phase = self._estimate_sync_word_start(signal, offset)
                cs.append(c)
                phases.append(phase)

            plt.plot(cs)
            #plt.plot(phases)
            plt.show()

            print "best freq:", offsets[numpy.argmax(cs)]
            #print "phase:", math.degrees(phases[numpy.argmax(cs)])

            #print "current phase:", math.degrees(estimate(signal, 0)[1])
            #return offsets[numpy.argmax(cs)]
        

        def f_est(freq):
            #print freq
            #c = numpy.correlate(signal, sync_word_shifted[int(freq+0.5)], 'same')
            c = scipy.signal.fftconvolve(signal, self._sync_words[preamble_length][int(freq+0.5)], 'same')
            return -numpy.max(numpy.abs(c))

        freq = int(scipy.optimize.fminbound(f_est, -100, 100, xtol=1) + 0.5)
        _, _, phase = self.estimate_sync_word_start(signal, preamble_length, freq)

        #print "best freq:", freq
        #print "phase:", phase
        return freq, phase
