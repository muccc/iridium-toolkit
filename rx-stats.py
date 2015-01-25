#!/usr/bin/env python
# vim: set ts=4 sw=4 tw=0 et pm=:

# Parses .bits files and displays how many messages have
# been received over time. Usefull to tune a receiving setup

import sys
import matplotlib.pyplot as plt
import getopt

import bitutils

options, remainder = getopt.getopt(sys.argv[1:], 's:l:o', [
                                                         'span=',
                                                         'minimum_length=',
                                                         'lead_out_required'
                                                         ])
span = 3600
minimum_length = 0
lead_out_required = False

for opt, arg in options:
    if opt in ('-s', '--span'):
        span = int(arg)
    elif opt in ('-l', '--minimum_length'):
        minimum_length = int(arg)
    elif opt in ('-o', '--lead_out_required'):
        lead_out_required = True
    else:
        print opt
        raise Exception("unknown argument?")
filename= remainder[0]

messages = bitutils.read_file(filename)

timestamps = [s['timestamp'] for s in messages if s['length'] > minimum_length and (not lead_out_required or s['lead_out'])]

t0 = min(timestamps)
t = max(timestamps)

bins = (t - t0)/span

title = "File: %s : Messages per %d seconds, longer than %d symbols" % (filename, span, minimum_length)
if lead_out_required:
    title += ', lead out needs to be present'
else:
    title += ', lead out does not need to be present'

plt.title(title)
plt.hist(timestamps, bins)
plt.show()
