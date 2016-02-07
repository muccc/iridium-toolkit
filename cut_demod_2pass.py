#!/usr/bin/env python
# vim: set ts=4 sw=4 tw=0 et pm=:
import struct
import sys
import math
import numpy
import os.path
import cmath
import filters
import re
import iq
import getopt
import demod
import cut_and_downmix

if __name__ == "__main__":

    options, remainder = getopt.getopt(sys.argv[1:], 'o:w:c:r:s:cv', ['offset=',
                                                            'window=',
                                                            'center=',
                                                            'rate=',
                                                            'search-depth=',
                                                            'use-correlation',
                                                            'verbose',
                                                            'downlink',
                                                            'uplink'
                                                            ])

    center = None
    sample_rate = None
    symbols_per_second = 25000
    preamble_length = 16
    search_offset = None
    search_window = 50000
    search_depth = 0.007
    use_correlation=False
    verbose = False
    direction = None

    for opt, arg in options:
        if opt in ('-o', '--search-offset'):
            search_offset = int(arg)
        if opt in ('-w', '--search-window'):
            search_window = int(arg)
        elif opt in ('-c', '--center'):
            center = int(arg)
        elif opt in ('-r', '--rate'):
            sample_rate = int(arg)
        elif opt in ('-s', '--search'):
            search_depth = float(arg)
        elif opt in ('-c', '--use-correlation'):
            use_correlation=True
        elif opt in ('-v', '--verbose'):
            verbose = True
        elif opt in ('-u', '--uplink'):
            direction = iridium.UPLINK
        elif opt in ('-d', '--downlink'):
            direction = iridium.DOWNLINK


    if sample_rate == None:
        print >> sys.stderr, "Sample rate missing!"
        exit(1)
    if center == None:
        print >> sys.stderr, "Need to specify center frequency!"
        exit(1)

    if len(remainder)==0:
        file_name = "/dev/stdin"
        basename="stdin"
    else:
        file_name = remainder[0]
        basename= filename= re.sub('\.[^.]*$','',file_name)

    signal = iq.read(file_name)

    cad = cut_and_downmix.CutAndDownmix(center=center, sample_rate=sample_rate, symbols_per_second=symbols_per_second, preamble_length=preamble_length,
                            search_depth=search_depth, verbose=verbose, search_window=search_window)
    d = demod.Demod(sample_rate=sample_rate, verbose=verbose)

    temp_signal, freq, _ = cad.cut_and_downmix(signal=signal, search_offset=search_offset, direction=direction)

    dataarray, data, access_ok, lead_out_ok, confidence, level, nsymbols, final_offset = d.demod(temp_signal,return_final_offset=True)

    print "RAW: %s %d %010d A:%s L:%s %3d%% %.3f %3d %s"%(basename,0,freq,("no","OK")[access_ok],("no","OK")[lead_out_ok],confidence,level,(nsymbols-12),data)
    signal, freq, _ = cad.cut_and_downmix(signal=signal, search_offset=search_offset, frequency_offset=-final_offset)
    print "F_off:",-final_offset
    dataarray, data, access_ok, lead_out_ok, confidence, level, nsymbols, final_offset = d.demod(signal,return_final_offset=True)
    print "RAW: %s %d %010d A:%s L:%s %3d%% %.3f %3d %s"%(basename,0,freq,("no","OK")[access_ok],("no","OK")[lead_out_ok],confidence,level,(nsymbols-12),data)

