#!/usr/bin/env python

import unittest
from io import BytesIO

from bits_to_dfs import chunks, bits_to_dfs


class ChunksTest(unittest.TestCase):
    def test_simple(self):
        result = list(chunks([1, 2, 3, 4, 5, 6], 2))
        self.assertEquals(result, [[1, 2], [3, 4], [5, 6]])


class BitsToDfsTest(unittest.TestCase):
    TEST_VOC_LINE = 'VOC: i-1443338945.6543-t1 033399141 1625872817  81% 0.027 179 L:no LCW(0,001111,100000000000000000000 E1) 01111001000100010010010011011011011001111    011000010000100001110101111011110010010111011001010001011101010001100000000110010100000110111110010101110101001111010100111001000110100110001110110    1010101010010010001000001110011000001001001010011110011100110100111110001101110010110101010110011101011100011101011000000000 descr_extra:'

    def test_empty_input(self):
        output = BytesIO()
        bits_to_dfs([], output)
        self.assertEquals(output.getvalue(), '')

    def test_single(self):
        output = BytesIO()
        bits_to_dfs([BitsToDfsTest.TEST_VOC_LINE], output)
        self.assertEquals(output.getvalue(), '\x9e\x88$\xdb\xe6\x01')

    def test_multiple(self):
        output = BytesIO()
        bits_to_dfs([BitsToDfsTest.TEST_VOC_LINE, BitsToDfsTest.TEST_VOC_LINE, BitsToDfsTest.TEST_VOC_LINE], output)
        self.assertEquals(output.getvalue(), '\x9e\x88$\xdb\xe6\x01' * 3)

    def test_filters_non_voc_lines(self):
        output = BytesIO()
        bits_to_dfs([BitsToDfsTest.TEST_VOC_LINE, 'NOT_VOC:', BitsToDfsTest.TEST_VOC_LINE], output)
        self.assertEquals(output.getvalue(), '\x9e\x88$\xdb\xe6\x01' * 2)


def main():
    unittest.main()


if __name__ == "__main__":
    main()
