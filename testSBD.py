#!/usr/bin/env python
import sys, hexdump, binascii, re

#sbd_file = "SBD_sample.parsed"
sbd_file = sys.argv[1]
hexfile = open(str(sys.argv[1]) + ".SBD.hex", "w")
binfile = open(str(sys.argv[1]) + ".SBD.bin", "w")
stringfile = open(str(sys.argv[1]) + ".SBD.string", "w")
# Read parsed data

regex_SBD = re.compile('CRC:OK 0000 SBD:')
regex_hex = re.compile('0:0000 \[[0-9a-f\.]*\]')

SBD_hex = []
SBD_strings = []

with open(sbd_file) as data:
    for line in data:
#        print(line)
        # regex to match on "CRC:OK 0000 SBD:" "0:0000 \[.*\]"
#        match_SBD = re.compile('CRC:OK 0000 SBD:')
#        match_hex = re.compile('0:0000 \[.*\]')
        m_val = regex_SBD.search(line)
#        h_val = regex_hex.search(line)
#        print(m_val.group(0))
#        print(h_val.group(0))
        try:
            m_val_string = str(m_val.group(0)) 
            if "CRC:OK 0000 SBD" in m_val_string:
                r = regex_hex.search(line)
                m_raw = r.group(0).replace(".", " ")
                m = m_raw.replace(" ", "")
#                print(m)
                m_len = len(m)
                ascii_hex_string = m[7:m_len-1]
#                print("0x" + ascii_hex_string)
                hex_val = binascii.a2b_hex(ascii_hex_string)
                SBD_hex.append(hex_val)
                for m in re.finditer("([\x20-\x7f]{1,})", hex_val):
#            print(m.start(), repr(m.group(1)))
#                    print(repr(m.group(1)))
                    SBD_strings.append(repr(m.group(1)))
#        else:
#            print("error")
        except AttributeError:
#            print("Not SBD")
            m_val = ""
for b in SBD_hex:
    binfile.write(b)
binfile.close()

for h in SBD_hex:
    hexfile.write(str(hexdump.hexdump(h, result='return')) + "\n")
hexfile.close()

for s in SBD_strings:
    stringfile.write(s[1:-1] + "\n")
stringfile.close()
'''
#d = open("testSBD.parsed", "rb")
#data = d.read()
#d.close()
with open(sbd_file) as data:
    for data_line in data:
#        print(data_line)
        line = data_line.strip()
#        print(line)
        hex_line = binascii.a2b_hex(line)
        for m in re.finditer("([\x20-\x7f]{4,})", hex_line):
#            print(m.start(), repr(m.group(1)))
            print(repr(m.group(1)))
#        print("\n" + line + "\n")
#        hex_line = line.decode('hex')
#        print(binascii.hexlify(hex_line))
#        hexdump.dehex(hex_line)
'''
