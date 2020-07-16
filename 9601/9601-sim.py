import serial
import time


class ATInterface:
    def __init__(self, port, speed=19200):
        self.s = serial.Serial(port, speed)
        self._echo_enabled = True

    def reader(self):
        line = ''
        while True:
            c = self.s.read(1)
            #print "Got", list(c)
            if len(c) != 1:
                continue

            if self._echo_enabled:
                #print "Write", list(c)
                self.s.write(c)

            if c != '\r':
                line += c
            else:
                if line != '':
                    self.read(line)
                line = ''

    def read(self, line):
        print "Read", line

        if (line == 'AT+GSN&F&K&D+SBDMTA=1+SBDAREG=2+CIER=1,1,1,1;*R1' or
            line == 'AT+GSN&F&K&D+SBDMTA=0+SBDAREG=0+CIER=1,1,1,1;*R1'):
            self.s.write("\r\n300034013613490\r\n")
            self.s.write("\r\nOK\r\n")
            self.s.write("\r\n+CIEV:0,3\r\n")
            self.s.write("\r\n+CIEV:1,1\r\n")
            self.s.write("\r\n+CIEV:2,0\r\n")

        if line == 'AT+SBDD2':
            self.s.write("\r\nOK\r\n")

        if line.startswith('AT+SBDWB='):
            l = int(line[9:])
            self.s.write("\r\nREADY\r\n")
            data = self.s.read(l + 2)
            print "Data:", data[:-2].encode('hex')
            self.s.write("\r\n0\r\n")
            self.s.write("\r\nOK\r\n")
        if line.startswith("AT+SBDIX"):
            self.s.write("\r\n+SBDIX:0,23,0,0,0,0\r\n")
            self.s.write("\r\nOK\r\n")

iface = ATInterface('/dev/ttyUSB0')
iface.reader()
