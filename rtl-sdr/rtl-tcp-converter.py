#!/usr/bin/env python
# vim: set ts=4 sw=4 tw=0 et pm=:
import sys
import numpy

class Converter(object):
    def __init__(self, verbose=False):
        self._struct_elem = numpy.uint8

    def process_file(self, file_name):
        with open(file_name, "rb") as f:
            while True:
                data = f.read(1024)
                if not data: break

                slice = numpy.frombuffer(data, dtype=self._struct_elem)
                slice = slice.astype(numpy.float32) # convert to float
                slice = (slice-127.35)/128.*10000             # Normalize
                #slice = slice.view(numpy.complex64) # reinterpret as complex
                slice.tofile(sys.stdout)

if __name__ == "__main__":
    verbose = False
    file_name = "/dev/stdin"
    d = Converter(verbose=verbose)
    d.process_file(file_name)

