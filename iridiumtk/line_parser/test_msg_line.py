#!/usr/bin/env python

import unittest


from .base_line import LineParseException
from .msg_line import MsgLine


class MsgLineTest(unittest.TestCase):
    TEST_MSG_LINE_1 = 'MSG: i-1526039037-t1 001174920 1626447232 100%   0.006 432 DL 00110011111100110011001111110011 odd:01100000000000000000000001 1:0:03                                                                                             ric:3525696 fmt:05 seq:18 1101000111 0/0 AgAFACYCgTLIxITKA4x8qpLs5geb4SICAVgVzXq9gdkuxao79yKD7DG5XpZD      +1111'

    def test_empty_input(self):
        with self.assertRaises(LineParseException):
            MsgLine('')

    def test_simple(self):
        msg_line = MsgLine(MsgLineTest.TEST_MSG_LINE_1)

        self.assertEquals(msg_line.message_ric, 3525696)
        self.assertEquals(msg_line.format, 5)
        self.assertEquals(msg_line.message_sequence, 18)
        self.assertEquals(msg_line.message_ctr, 0)
        self.assertEquals(msg_line.message_ctr_max, 0)

        self.assertEquals(msg_line.message_checksum, None)
        self.assertEquals(msg_line.message_hex, None)
        self.assertEquals(msg_line.message_brest, None)
        self.assertEquals(msg_line.message_ascii, None)
        self.assertEquals(msg_line.message_rest, None)


def main():
    unittest.main()


if __name__ == "__main__":
    main()
