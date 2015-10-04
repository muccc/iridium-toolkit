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

def normalize(v):
    m = max(v)
    return [x/m for x in v]

class PeakHold(object):
    def __init__(self, fft_size, use_8bit=False, verbose=False):
        self._slice_size=fft_size
        self._fft_size=self._slice_size

        if use_8bit:
            self._struct_elem = numpy.uint8
            self._struct_len = numpy.dtype(self._struct_elem).itemsize * self._slice_size *2
        else:
            self._struct_elem = numpy.complex64
            self._struct_len = numpy.dtype(self._struct_elem).itemsize * self._slice_size

        self._window = numpy.blackman(self._fft_size)
        self.peaks = numpy.array([-100000000]*self._fft_size)

    def _fft(self, slice, fft_len=None):
        if fft_len:
            fft_result = numpy.fft.fft(slice, fft_len)
        else:
            fft_result = numpy.fft.fft(slice)

        fft_result = numpy.fft.fftshift(fft_result)
        return fft_result/len(slice)


    def process_file(self, file_name):
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
                
                spectrum = self._fft(slice, self._fft_size)
                mag = spectrum
                mag = numpy.abs(spectrum)**2
                #print max(numpy.abs(slice)), max(mag)
                mag = 10*numpy.log10(mag)
                self.peaks = numpy.maximum(self.peaks, mag)

def plot_peaks(data):
    plt.ion()
    fig = plt.figure()
    ax = fig.add_subplot(111)
    ax.set_ylim([-80,-20])
    time.sleep(1)
    l, = ax.plot(data.peaks, )
    while 1:
        l.set_ydata(data.peaks)
        fig.canvas.draw()
        time.sleep(1)
       
if __name__ == "__main__":
    fft_size = int(sys.argv[1])
    verbose = False
    file_name = "/dev/stdin"
    d = PeakHold(fft_size=fft_size, use_8bit=False, verbose=verbose)
    drawer = threading.Thread(target=plot_peaks, args=[d])
    drawer.setDaemon(True)
    drawer.start()

    d.process_file(file_name)
    while True:
        time.sleep(1)

