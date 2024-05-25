#!/usr/bin/env python3
# vim: set ts=4 sw=4 tw=0 et fenc=utf8 pm=:

import sys
import os
from util import parse_channel, parse_handoff, get_channel

class Frame:
    def __init__(self, f, f_alt, ts, line):
        self.f = f
        self.ts = ts
        self.line = line
        self.f_alt = f_alt

calls = []

for line in open(sys.argv[1]):
    if 'VOC: ' in line:
        sl = line.split()
        ts = float(sl[2])/1000. # seconds
        f = parse_channel(sl[3]) / 1000.
        frame = Frame(f, 0, ts, line)

        for call in calls:
            last_frame = call[-1]

            # If the last frame is not more than 20 kHz and 20 seconds "away"
            if (last_frame.f_alt and abs(last_frame.f_alt - frame.f) < 40 or abs(last_frame.f - frame.f) < 20) and abs(last_frame.ts - frame.ts) < 20:
                if "handoff_resp" in sl[8]:
                    ho = parse_handoff(sl[8])
                    frame.f_alt = get_channel(ho['sband_dn'], ho['access']) / 1000 + 52

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
    rv = os.system('check-sample ' + filename) >> 8
    if rv not in (0, 1):
        print(f"Problem running check-sample: {rv}", file=sys.stderr)
        break
    is_voice = rv == 0

    if not is_voice:
        os.system('mv ' + filename + ' fail-%04d.parsed' % call_id)
    call_id += 1
