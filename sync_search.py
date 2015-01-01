import struct
import sys
import math
import numpy
import os.path
import cmath
import scipy.signal
import filters

def estimate_sync_word_start(signal, sample_rate, symbols_per_second):
    samples_per_symbol = sample_rate / symbols_per_second
    sync_word = [-1, 1, 1, 1, 1, -1, -1, -1, 1, -1, -1, 1]
    sync_word_padded = []
    for bit in sync_word:
        sync_word_padded += [bit]
        sync_word_padded += [0] * (samples_per_symbol - 1)
    
    rcos = filters.rcosfilter(1001, 0.4, 1./25000., 2e6)[1]
    #sync_word_padded = scipy.signal.convolve(sync_word_padded, rcos, 'same')

    bpsk_signal = [c.real + c.imag for c in signal]
    sync_correlation = scipy.signal.correlate(numpy.array([c.real + c.imag for c in signal]), numpy.array(sync_word_padded), 'same')
    sync_correlation = [x for x in numpy.abs(sync_correlation)]
    sync_middle = sync_correlation.index(max(sync_correlation))
    sync_start = sync_middle - samples_per_symbol * (len(sync_word) - 1) / 2
    sync_start = sync_middle - len(sync_word_padded) / 2
    print "correlated start of sync word", sync_start
    return sync_start
