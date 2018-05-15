#!/usr/bin/env python

import logging
import re


import six


from .base_line import BaseLine, LineParseException


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# eg .... ric:3525696 fmt:05 seq:18 1101000111 0/0 AgAFACYCgTLIxITKA4x8qpLs5geb4SICAVgVzXq9gdkuxao79yKD7DG5XpZD      +1111
MSG_META_REGEX = re.compile(r'.* ric:(\d+) fmt:(\d+) seq:(\d+) [01]+ (\d)/(\d) ')
MSG_TEXT_REGEX = re.compile(r'.* csum:([0-9a-f][0-9a-f]) msg:([0-9a-f]+)\.([01]*) ')


# Example lines
# MSG: i-1526039037-t1 001174920 1626447232 100%   0.006 432 DL 00110011111100110011001111110011 odd:01100000000000000000000001 1:0:03                                                                                             ric:3525696 fmt:05 seq:18 1101000111 0/0 AgAFACYCgTLIxITKA4x8qpLs5geb4SICAVgVzXq9gdkuxao79yKD7DG5XpZD      +1111
class MsgLine(BaseLine):
    def __init__(self, line):
        super(MsgLine, self).__init__(line)
        try:
            line_split = line.split()
            assert line_split[0] == 'MSG:', 'Non MSG line passed to MsgLine'

            data = line.split(None, 8)[8]
            matches = MSG_META_REGEX.match(data)
            if not matches:
                raise ValueError('Failed to parse MSG data section: {}'.format(data))

            self._msg_ric = int(matches.group(1))
            self._format = int(matches.group(2))
            self._msg_seq = int(matches.group(3))
            self._msg_ctr = int(matches.group(4))
            self._msg_ctr_max = int(matches.group(5))

            matches = MSG_TEXT_REGEX.match(data)
            if matches:
                self._msg_checksum = int(matches.group(6), 16)
                self._msg_hex = matches.group(7)
                self._msg_brest = matches.group(8)

                msg_msgdata = ''.join(["{0:08b}".format(int(self._msg_hex[i:i + 2], 16)) for i in range(0, len(self._msg_hex), 2)])
                msg_msgdata += self._msg_brest
                matches = re.compile(r'(\d{7})').findall(msg_msgdata)
                msg_ascii = ''
                for (group) in matches:
                    character = int(group, 2)
                    if (character < 32 or character == 127):
                        msg_ascii += '[%d]' % character
                    else:
                        msg_ascii += chr(character)
                self._msg_ascii = msg_ascii

                if len(msg_msgdata) % 7:
                    self._msg_rest = msg_msgdata[-(len(msg_msgdata) % 7):]
                else:
                    self._msg_rest = ''
            else:
                self._msg_checksum = None
                self._msg_hex = None
                self._msg_brest = None
                self._msg_ascii = None
                self._msg_rest = None
        except (IndexError, ValueError) as e:
            logger.error('Failed to parse line "%s"', line)
            six.raise_from(LineParseException('Failed to parse line "{}"'.format(line), e), e)

    @property
    def message_ric(self):
        return self._msg_ric

    @property
    def format(self):
        return self._format

    @property
    def message_sequence(self):
        return self._msg_seq

    @property
    def message_ctr(self):
        return self._msg_ctr

    @property
    def message_ctr_max(self):
        return self._msg_ctr_max

    @property
    def message_checksum(self):
        return self._msg_checksum

    @property
    def message_hex(self):
        return self._msg_hex

    @property
    def message_brest(self):
        return self._msg_brest

    @property
    def message_ascii(self):
        return self._msg_ascii

    @property
    def message_rest(self):
        return self._msg_rest
