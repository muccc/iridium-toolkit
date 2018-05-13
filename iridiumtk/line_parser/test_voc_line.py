#!/usr/bin/env python

import unittest


from .voc_line import chunks, VocLine


class ChunksTest(unittest.TestCase):
    def test_simple(self):
        result = list(chunks([1, 2, 3, 4, 5, 6], 2))
        self.assertEquals(result, [[1, 2], [3, 4], [5, 6]])


class VocLineTest(unittest.TestCase):
    TEST_VOC_LINE_1 = 'VOC: i-1443338945.6543-t1 033399141 1625872817  81% 0.027 179 L:no LCW(0,001111,100000000000000000000 E1) 01111001000100010010010011011011011001111    011000010000100001110101111011110010010111011001010001011101010001100000000110010100000110111110010101110101001111010100111001000110100110001110110    1010101010010010001000001110011000001001001010011110011100110100111110001101110010110101010110011101011100011101011000000000 descr_extra:'
    TEST_VOC_LINE_2 = 'VOC: i-1526039037-t1 000065686 1620359296 100%   0.003 179 DL LCW(0,T:maint,C:maint[2][lqi:3,power:0,f_dtoa:0,f_dfoa:127](3),786686 E0)                                       [df.ff.f3.fc.10.33.c3.1f.0c.83.c3.cc.cc.30.ff.f3.ef.00.bc.0c.b4.0f.dc.d0.1a.cc.9c.c5.0c.fc.28.01.cc.38.c2.33.e0.ff.4f]'
    TEST_VOC_LINE_3 = 'VOC: i-1526039037-t1 000065686 1620359296 100%   0.003 178 DL LCW(0,T:maint,C:maint[2][lqi:3,power:0,f_dtoa:0,f_dfoa:127](3),786686 E0)                                       [df.ff.f3.fc.10.33.c3.1f.0c.83.c3.cc.cc.30.ff.f3.ef.00.bc.0c.b4.0f.dc.d0.1a.cc.9c.c5.0c.fc.28.01.cc.38.c2.33.e0.ff]'

    def test_empty_input(self):
        with self.assertRaises(Exception):
            VocLine('')

    def test_old_format(self):
        voc_line = VocLine(VocLineTest.TEST_VOC_LINE_1)
        self.assertEquals(voc_line.voice_bits, '\x9e\x88$\xdb\xe6\x01')

    def test_new_format(self):
        voc_line = VocLine(VocLineTest.TEST_VOC_LINE_2)
        self.assertEquals(voc_line.voice_bits, '\xfb\xff\xcf?\x08\xcc\xc3\xf80\xc1\xc333\x0c\xff\xcf\xf7\x00=0-\xf0;\x0bX39\xa30?\x14\x803\x1cC\xcc\x07\xff\xf2')

    def test_voice_bits_small_packet(self):
        voc_line = VocLine(VocLineTest.TEST_VOC_LINE_3)
        self.assertEquals(voc_line.voice_bits, None)


def main():
    unittest.main()


if __name__ == "__main__":
    main()
