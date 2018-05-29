#!/usr/bin/env python

from datetime import datetime
import unittest


from .base_line import BaseLine, LineParseException, LinkDirection


class BaseLineTest(unittest.TestCase):
    TEST_VOC_LINE_1 = 'VOC: i-1443338945.6543-t1 033399141 1625872817  81% 0.027 179 L:no LCW(0,001111,100000000000000000000 E1) 01111001000100010010010011011011011001111    011000010000100001110101111011110010010111011001010001011101010001100000000110010100000110111110010101110101001111010100111001000110100110001110110    1010101010010010001000001110011000001001001010011110011100110100111110001101110010110101010110011101011100011101011000000000 descr_extra:'
    TEST_VOC_LINE_2 = 'VOC: i-1526039037-t1 000065686 1620359296 100%   0.003 179 DL LCW(0,T:maint,C:maint[2][lqi:3,power:0,f_dtoa:0,f_dfoa:127](3),786686 E0)                                       [df.ff.f3.fc.10.33.c3.1f.0c.83.c3.cc.cc.30.ff.f3.ef.00.bc.0c.b4.0f.dc.d0.1a.cc.9c.c5.0c.fc.28.01.cc.38.c2.33.e0.ff.4f]'
    TEST_RAW_LINE_1 = 'RAW: i-1526300857-t1 000001404 1619597184  79%   0.001 <001100000011000011110011> 0110000000100011 0000100000001011 0001100100000010 1010101010101010 1000111010101010 0011101010001011 0011101010100010 1010101011101000 1010101010101010 1010001110101010 1010101010101010 1010110010101010 1010101010101010 1010001110101000 1011101010101010 1010101010101010 1010101010101010 1011001010101010 1010101010101010 1010101010101010 1010101010101010 1010101010101010 101010 ERR:Message: unknown Iridium message type'
    TEST_IMS_LINE_1 = 'IMS: capture-s1 000003681 1626472922 100%   0.043 127 DL 00110011111100110011001111110011 odd:100001                     9:A:22 1 c=03829           00000000 00000000000000000000 00000000000000000000 00000000000000000000 descr_extra:011010110101111001110011001111'

    def test_empty_input(self):
        with self.assertRaises(LineParseException):
            BaseLine('')

    def test_old_format_datetime(self):
        base_line = BaseLine(BaseLineTest.TEST_VOC_LINE_1)
        self.assertEquals(base_line.datetime_unix, 1443372344)
        self.assertEquals(base_line.datetime, datetime.utcfromtimestamp(1443372344))

    def test_new_format_datetime(self):
        base_line = BaseLine(BaseLineTest.TEST_VOC_LINE_2)
        self.assertEquals(base_line.datetime_unix, 1526039102)
        self.assertEquals(base_line.datetime, datetime.utcfromtimestamp(1526039102))

    def test_filename_datetime(self):
        now = datetime.utcfromtimestamp(1526300857)
        base_line = BaseLine(BaseLineTest.TEST_IMS_LINE_1, now=now)
        self.assertEquals(base_line.datetime_unix, 1526297260)
        self.assertEquals(base_line.datetime, datetime.utcfromtimestamp(1526297260))

    def test_frequency(self):
        base_line = BaseLine(BaseLineTest.TEST_VOC_LINE_2)
        self.assertEquals(base_line.frequency, 1620359296)

    def test_frame_type(self):
        base_line = BaseLine(BaseLineTest.TEST_VOC_LINE_2)
        self.assertEquals(base_line.frame_type, 'VOC')

    def test_confidence(self):
        base_line = BaseLine(BaseLineTest.TEST_VOC_LINE_1)
        self.assertEquals(base_line.confidence, 81)
        base_line = BaseLine(BaseLineTest.TEST_VOC_LINE_2)
        self.assertEquals(base_line.confidence, 100)

    def test_level(self):
        base_line = BaseLine(BaseLineTest.TEST_VOC_LINE_1)
        self.assertEquals(base_line.level, 0.027)
        base_line = BaseLine(BaseLineTest.TEST_VOC_LINE_2)
        self.assertEquals(base_line.level, 0.003)

    def test_symbols(self):
        base_line = BaseLine(BaseLineTest.TEST_VOC_LINE_1)
        self.assertEquals(base_line.symbols, 179)
        base_line = BaseLine(BaseLineTest.TEST_RAW_LINE_1)
        self.assertEquals(base_line.symbols, None)

    def test_link_direction(self):
        base_line = BaseLine(BaseLineTest.TEST_VOC_LINE_1)
        self.assertEquals(base_line.link_direction, LinkDirection.NO_DIRECTION)
        self.assertEquals(base_line.is_downlink(), False)
        self.assertEquals(base_line.is_uplink(), False)

        base_line = BaseLine(BaseLineTest.TEST_VOC_LINE_2)
        self.assertEquals(base_line.link_direction, LinkDirection.DOWNLINK)
        self.assertEquals(base_line.is_downlink(), True)
        self.assertEquals(base_line.is_uplink(), False)

        base_line = BaseLine(BaseLineTest.TEST_RAW_LINE_1)
        self.assertEquals(base_line.link_direction,None)
        self.assertEquals(base_line.is_downlink(), False)
        self.assertEquals(base_line.is_uplink(), False)

    def test_raw_line(self):
        for line in [BaseLineTest.TEST_VOC_LINE_1, BaseLineTest.TEST_VOC_LINE_2]:
            base_line = BaseLine(line)
            self.assertEquals(base_line.raw_line, line)


def main():
    unittest.main()


if __name__ == "__main__":
    main()
