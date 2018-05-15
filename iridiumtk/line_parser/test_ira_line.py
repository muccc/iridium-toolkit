#!/usr/bin/env python

import unittest


from .base_line import LineParseException
from .ira_line import IraLine, Page


class IraLineTest(unittest.TestCase):
    TEST_IRA_LINE_1 = 'IRA: i-1526300857-t1 000159537 1626299264 100%   0.003 130 DL sat:80 beam:30 pos=(+54.57/-001.24) alt=001 RAI:48 ?00 bc_sb:07 PAGE(tmsi:0cf155ab msc_id:03) PAGE(NONE) descr_extra:011010110101111001110011001111100110'

    def test_empty_input(self):
        with self.assertRaises(LineParseException):
            IraLine('')

    def test_simple(self):
        ira_line = IraLine(IraLineTest.TEST_IRA_LINE_1)

        self.assertEquals(ira_line.satellite, 80)
        self.assertEquals(ira_line.beam, 30)
        self.assertEquals(ira_line.position, (54.57, -1.24))
        self.assertEquals(ira_line.altitude, 1)
        self.assertEquals(ira_line.pages, [Page(tmsi='0cf155ab', msc_id=3)])


def main():
    unittest.main()


if __name__ == "__main__":
    main()
