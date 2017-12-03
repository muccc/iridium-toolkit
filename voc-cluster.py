#!/usr/bin/python
# vim: set ts=4 sw=4 tw=0 et fenc=utf8 pm=:

import sys
import os

class Frame:
    def __init__(self, f, ts, line):
        self.f = f
        self.ts = ts
        self.line = line

calls = []

for line in open(sys.argv[1]):
    if 'VOC: ' in line:
        sl = line.split()
        ts = int(sl[2])/1000. # seconds
        f = int(sl[3])/1000. # kHz
        frame = Frame(f, ts, line)

        for call in calls:
            last_frame = call[-1]

            # If the last frame is not more than 20 kHz and 20 seconds "away"
            if abs(last_frame.f - frame.f) < 20 and abs(last_frame.ts - frame.ts) < 20:
                call.append(frame)
                # First call that matches wins
                break
        else:
            # If no matching call is available create a new one
            calls.insert(0,[frame])

call_id = 0
for call in calls:
    if abs(call[0].ts - call[-1].ts) < 1: 
        continue

    samples = [frame.line for frame in call]

    filename = "call-%d.parsed" % call_id
    open(filename, "w").writelines(samples)
    is_voice = os.system('check-sample ' + filename) == 0

    if not is_voice:
        os.system('mv ' + filename + ' fail-%d.parsed' % call_id)
    call_id += 1

