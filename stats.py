#!/usr/bin/python
# vim: set ts=4 sw=4 tw=0 et fenc=utf8 pm=:
import sys
import matplotlib.pyplot as plt
f = open(sys.argv[1])
#IRA: i-1424627833.3321-t1 0095916 1626242718  98% 0.317 101 L:OK ts:329774983 sat:11 cell:15 0 01111100,111[0999] 00 0011000000[0192] 01001,1000110[1222] 0110000 00 11010{26} 111111111111111111111 111111111111111111111 descr_extra:[100101111010110110110011001111]100111010000
#IMS: i-1424627833.3321-t1 0465557 1626388717  87% 0.167 133 L:OK 00110011111100110011001111110011 odd:110001                     8:A:20 1 c=06559           10000000 00000000000000000 00000000000000000000 descr_extra:[100101111010110110110011001111]111000000010
#0    1                    2         3           4   5     6   7    8
#IDA: i-1443376286.1279-t1 000000026 1625062691  84% 0.016 180 L:no LCW(2,000011,000000011111101111110 E0) 1010101011010110 0000110001010011 0110100001100110 1010101111000000 0000000000000000 0000011011111100 0000000011100000 0110001110000011 0110111011001000 0011111100100011 1000000100000000 0000000000000001 1111111100000000 00 descr_extra:01

tsl = []
fl = []
lenl = []
confl = []
sigl = []
secl = []
strengthl = []
f.readline()
for line in f:
    line = line.strip().split()
    #print line
    ts_base = int(line[1].split('-')[1].split('.')[0])
    ts = ts_base + float(line[2])/1000.
    f = int(line[3])/1000.
    #len = int(line[6])
    strength = float(line[5])
    tsl.append(ts)
    fl.append(f)
    #lenl.append(len)
    strengthl.append(strength)

#plt.scatter(x = tsl, y = fl, s = lenl, c = strengthl, alpha=.5)
plt.scatter(x = tsl, y = fl, c = strengthl, alpha=.5)
plt.colorbar()
plt.show()

