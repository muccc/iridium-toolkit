#!/usr/bin/env python
# vim: set ts=4 sw=4 tw=0 et pm=:

# Parses .bits files and displays the distribution
# of the length of received frames

import sys
import matplotlib.pyplot as plt
import getopt

import bitutils

options, remainder = getopt.getopt(sys.argv[1:], 'b:c:eo', [
                                                         'bin=',
                                                         'minimum_confidence=',
                                                         'errors',
                                                         'lead_out_required'
                                                         ])
bin_size = 1
minimum_confidence = 0
lead_out_required = False
show_errors = False

for opt, arg in options:
    if opt in ('-b', '--bin'):
        bin_size = int(arg)
    elif opt in ('-c', '--minimum_confidence'):
        minimum_confidence = int(arg)
    elif opt in ('-o', '--lead_out_required'):
        lead_out_required = True
    elif opt in ('-e', '--errors'):
        show_errors = True
    else:
        print opt
        raise Exception("unknown argument?")

messages = bitutils.read_file(remainder)

lens = [s['length'] for s in messages if s['length'] > 100 and s['confidence'] > minimum_confidence and (s['lead_out'] or not lead_out_required) and (s['error'] == show_errors) and s['freq'] < 1.626e9]

bins = (max(lens) - min(lens))/bin_size

filename=["<stdin>",",".join(remainder)][remainder is None]
title = "File: %s : Distribution of message length. Bin Size: %d, Minimum Confidence: %d" % (filename, bin_size, minimum_confidence)
if lead_out_required:
    title += ', lead out needs to be present'
else:
    title += ', lead out does not need to be present'
if show_errors:
    title += " and having decoding errors"

plt.title(title)
plt.hist(lens, bins)
plt.show()
