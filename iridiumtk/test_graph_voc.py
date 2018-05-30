#!/usr/bin/env python

import os
import tempfile
import unittest


from .graph_voc import read_lines


class MainTest(unittest.TestCase):
    TEST_VOC_LINE_1 = 'VOC: i-1443338945.6543-t1 033399141 1625872817  81% 0.027 179 L:no LCW(0,001111,100000000000000000000 E1) 01111001000100010010010011011011011001111    011000010000100001110101111011110010010111011001010001011101010001100000000110010100000110111110010101110101001111010100111001000110100110001110110    1010101010010010001000001110011000001001001010011110011100110100111110001101110010110101010110011101011100011101011000000000 descr_extra:'
    TEST_VOC_LINE_2 = 'VOC: i-1526039037-t1 000065686 1620359296 100%   0.003 179 DL LCW(0,T:maint,C:maint[2][lqi:3,power:0,f_dtoa:0,f_dfoa:127](3),786686 E0)                                       [df.ff.f3.fc.10.33.c3.1f.0c.83.c3.cc.cc.30.ff.f3.ef.00.bc.0c.b4.0f.dc.d0.1a.cc.9c.c5.0c.fc.28.01.cc.38.c2.33.e0.ff.4f]'
    TEST_VOC_LINE_3 = 'VOC: i-1526039037-t1 000065686 1620359296 100%   0.003 178 DL LCW(0,T:maint,C:maint[2][lqi:3,power:0,f_dtoa:0,f_dfoa:127](3),786686 E0)                                       [df.ff.f3.fc.10.33.c3.1f.0c.83.c3.cc.cc.30.ff.f3.ef.00.bc.0c.b4.0f.dc.d0.1a.cc.9c.c5.0c.fc.28.01.cc.38.c2.33.e0.ff]'

    def setUp(self):
        self.tempfiles = []

    def get_temp_file(self):
        _, file_path = tempfile.mkstemp()
        self.tempfiles.append(file_path)
        return file_path

    def test_read_lines(self):
        input_file_path = self.get_temp_file()
        with open(input_file_path, 'w') as input_file:
            input_file.write(MainTest.TEST_VOC_LINE_1 + '\n')
            input_file.write(MainTest.TEST_VOC_LINE_2 + '\n')
            input_file.write(MainTest.TEST_VOC_LINE_3 + '\n')

        voc_lines = list(read_lines(input_file_path, None, None))
        self.assertEqual(len(voc_lines), 2)

    def test_test_read_lines_with_raw_data(self):
        input_file_path = self.get_temp_file()
        with open(input_file_path, 'w') as input_file:
            input_file.write('RAW: i-1525892321-t1 0001338 1623702528 A:OK I:00000000027  79% 0.001 1 00\n')
        with self.assertRaises(RuntimeError):
            list(read_lines(input_file_path, None, None))

    def test_test_read_lines_with_parsed_errors(self):
        input_file_path = self.get_temp_file()
        with open(input_file_path, 'w') as input_file:
            input_file.write('RAW: i-1525892321-t1 000045987 1626110208  83%   0.001 <001100000011000011110011> 1100000000000000 .... 00011001 ERR:Message: unknown Iridium message type\n')
        voc_lines = list(read_lines(input_file_path, None, None))
        self.assertEqual(voc_lines, [])

    def tearDown(self):
        for path in self.tempfiles:
            os.remove(path)


def main():
    unittest.main()


if __name__ == "__main__":
    main()
