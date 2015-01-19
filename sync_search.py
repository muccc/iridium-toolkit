import struct
import sys
import math
import numpy
import os.path
import cmath
import filters

def estimate_sync_word_start(signal, sample_rate, symbols_per_second):
    samples_per_symbol = sample_rate / symbols_per_second
    sync_word = [-1, 1, 1, 1, 1, -1, -1, -1, 1, -1, -1, 1]
    sync_word_padded = []
    for bit in sync_word:
        sync_word_padded += [bit]
        sync_word_padded += [0] * (samples_per_symbol - 1)
    # TODO: Convolve the sync word with a sinusoidal base function
    
    bpsk_signal = signal.real + signal.imag
    sync_correlation = numpy.correlate(bpsk_signal, sync_word_padded, 'same')
    sync_correlation = numpy.abs(sync_correlation)
    sync_middle = numpy.argmax(sync_correlation)
    sync_start = sync_middle - samples_per_symbol * (len(sync_word) - 1) / 2
    sync_start = sync_middle - len(sync_word_padded) / 2
    return sync_start
