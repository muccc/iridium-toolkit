#!/usr/bin/env python
# vim: set ts=4 sw=4 tw=0 et pm=:
import sys
import math
import numpy
import os.path
import re
import getopt
import time
from functools import partial
import matplotlib.pyplot as plt
import threading
import time
import iq
import scipy.signal

def normalize(v):
    m = max(v)
    return [x/m for x in v]

class Mixer(object):
    def __init__(self, sample_rate, offset_freq, decimation, use_8bit, verbose):
        self._sample_rate=sample_rate
        self._offset_freq=offset_freq
        self._decimation=decimation

        if self._sample_rate % self._offset_freq != 0:
            raise Exception("sample_rate needs to be n*offset_freq")

        self._slice_size = int(self._sample_rate/abs(self._offset_freq)) * 100000
        sys.stderr.write("slice size: %d\n"%self._slice_size)
        # Generate a complex signal at offset_freq Hz.
        self._shift_signal = numpy.exp(complex(0,1)*numpy.arange(self._slice_size)*2*numpy.pi*self._offset_freq/float(self._sample_rate))

        if use_8bit:
            self._struct_elem = numpy.uint8
            self._struct_len = numpy.dtype(self._struct_elem).itemsize * self._slice_size *2
        else:
            self._struct_elem = numpy.complex64
            self._struct_len = numpy.dtype(self._struct_elem).itemsize * self._slice_size

    
    def butter_lowpass(self, cutoff, fs, order=5):
        nyq = 0.5 * fs
        normal_cutoff = cutoff / nyq
        b, a = scipy.signal.butter(order, normal_cutoff, btype='low', analog=False)
        return b, a

    def process_file(self, file_name):
        b, a = self.butter_lowpass(100e3, 1e6)

        with open(file_name, "rb") as f:
            f.read(self._struct_len)
            while True:
                data = f.read(self._struct_len)
                if not data: break
                if len(data) != self._struct_len: break

                slice = numpy.frombuffer(data, dtype=self._struct_elem)
                if self._struct_elem == numpy.uint8:
                    slice = slice.astype(numpy.float32) # convert to float
                    slice = (slice-127.35)/128.             # Normalize
                    slice = slice.view(numpy.complex64) # reinterpret as complex
 
                # Multiply the two signals, effectively shifting signal by offset_freq
                slice = slice*self._shift_signal
                #slice = self._shift_signal
                slice = scipy.signal.lfilter(b, a, slice)
                slice = scipy.signal.decimate(slice, 4)
                #slice = slice[::4]
                
                #slice = self._shift_signal
                iq.write(sys.stdout, slice)
                #iq.write('/tmp/foo', slice)

               
if __name__ == "__main__":
    verbose = False
    file_name = "/dev/stdin"
    m = Mixer(sample_rate=1e6, offset_freq=-250e3, decimation=4, use_8bit=True, verbose=verbose)
    m.process_file(file_name)

