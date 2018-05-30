#!/usr/bin/env python

import unittest


from .base_line import LineParseException
from .msg_line import MsgLine


class MsgLineTest(unittest.TestCase):
    TEST_MSG_LINE_1 = 'MSG: i-1526039037-t1 001174920 1626447232 100%   0.006 432 DL 00110011111100110011001111110011 odd:01100000000000000000000001 1:0:03                                                                                             ric:3525696 fmt:05 seq:18 1101000111 0/0 AgAFACYCgTLIxITKA4x8qpLs5geb4SICAVgVzXq9gdkuxao79yKD7DG5XpZD      +1111'
    TEST_MSG_LINE_2 = 'MSG: i-1526039037-t1 002353427 1626432128  90%   0.002 432 DL 00110011111100110011001111110011 odd:01100000000000000000000001 1:3:05                                                                                             ric:3525696 fmt:05 seq:24 0010000101 0/0 AgAFAiZzt1VegmFKoMZzD/Bb.M![127][25][19]+/tuE3QMEXmzPe433ff0L2RchgTp2z +1111'
    TEST_MSG_LINE_3 = 'MSG: i-1526039037-t1 000083205 1626415820 100%   0.038 358 DL 00110011111100110011001111110011 odd:10000110000000000001       2:A:34 1 c=09297           00000000 01110000000000000000 00000100000000000000 00000000000000000000 ric:3221191 fmt:05 seq:07 0010101111 0/0 Estab comms 99 @ 2030 for sitrep                                  +       descr_extra:01101011010111100111001100111101101110000011'

    def test_empty_input(self):
        with self.assertRaises(LineParseException):
            MsgLine('')

    def test_simple(self):
        msg_line = MsgLine(MsgLineTest.TEST_MSG_LINE_1)

        self.assertEqual(msg_line.message_ric, 3525696)
        self.assertEqual(msg_line.format, 5)
        self.assertEqual(msg_line.message_sequence, 18)
        self.assertEqual(msg_line.message_ctr, 0)
        self.assertEqual(msg_line.message_ctr_max, 0)

        self.assertEqual(msg_line.message_data_escaped, 'AgAFACYCgTLIxITKA4x8qpLs5geb4SICAVgVzXq9gdkuxao79yKD7DG5XpZD')
        self.assertEqual(msg_line.message_data, b'AgAFACYCgTLIxITKA4x8qpLs5geb4SICAVgVzXq9gdkuxao79yKD7DG5XpZD')
        self.assertEqual(msg_line.message_rest, '1111')

    def test_escaped_message(self):
        msg_line = MsgLine(MsgLineTest.TEST_MSG_LINE_2)

        self.assertEqual(msg_line.message_data_escaped, 'AgAFAiZzt1VegmFKoMZzD/Bb.M![127][25][19]+/tuE3QMEXmzPe433ff0L2RchgTp2z')
        self.assertEqual(msg_line.message_data, b'AgAFAiZzt1VegmFKoMZzD/Bb.M!\x7f\x19\x13+/tuE3QMEXmzPe433ff0L2RchgTp2z')
        self.assertEqual(msg_line.message_rest, '1111')

    def test_no_msg_reset_chars(self):
        msg_line = MsgLine(MsgLineTest.TEST_MSG_LINE_3)

        self.assertEqual(msg_line.message_rest, '')


def main():
    unittest.main()


if __name__ == "__main__":
    main()
