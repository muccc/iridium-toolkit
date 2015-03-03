# vim: set ts=4 sw=4 tw=0 et pm=:
import struct
import numpy
from itertools import izip

def write(file_name, signal):
    if type(signal)!=numpy.complex64:
        signal=numpy.asarray(signal,dtype=numpy.complex64)
    signal.tofile(file_name)

def read(file_name):
    signal = numpy.fromfile(file_name, dtype=numpy.complex64)
    return signal
