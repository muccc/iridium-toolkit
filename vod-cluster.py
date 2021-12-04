#!/usr/bin/env python3
# vim: set ts=4 sw=4 tw=0 et fenc=utf8 pm=:

import sys
import os
from util import parse_channel

class Frame:
    def __init__(self, f, f_alt, ts, line):
        self.f = f
        self.ts = ts
        self.line = line
        self.f_alt = f_alt

calls = []

for line in open(sys.argv[1]):
    if 'VOD: ' in line:
        sl = line.split()
        ts = float(sl[2])/1000. # seconds
        f = parse_channel(sl[3]) / 1000.
        frame = Frame(f, 0, ts, line)

        for call in calls:
            last_frame = call[-1]

            # VOD calls span three adjacent channels. We need to be quite
            # generous with our frequency window to capture them while looking
            # at single frames

            # If the last frame is not more than 140 kHz and 20 seconds "away"
            if abs(last_frame.f - frame.f < 140) and abs(last_frame.ts - frame.ts) < 20:
                call.append(frame)
                # First call that matches wins
                break
        else:
            # If no matching call is available create a new one
            calls.insert(0,[frame])

call_id = 0
for call in calls[::-1]:
    if abs(call[0].ts - call[-1].ts) < 1:
        continue

    samples = [frame.line for frame in call]

    filename = "call-%04d.parsed" % call_id
    open(filename, "w").writelines(samples)

    is_voice = os.system('check-sample-vod ' + filename) == 0

    if not is_voice:
        os.system('mv ' + filename + ' fail-%d.parsed' % call_id)
    call_id += 1

