#!/usr/bin/env python

import logging
import re


from .base_line import BaseLine, LineParseException


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# eg .... ric:3525696 fmt:05 seq:18 1101000111 0/0 AgAFACYCgTLIxITKA4x8qpLs5geb4SICAVgVzXq9gdkuxao79yKD7DG5XpZD      +1111
MSG_META_REGEX = re.compile(r'.* ric:(\d+) fmt:(\d+) seq:(\d+) [01]+ (\d)/(\d) (.{65,}) \+([01]{0,6})')


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

            self._msg_data_escaped = matches.group(6).strip()
            self._msg_rest = matches.group(7)
        except (IndexError, ValueError) as e:
            logger.error('Failed to parse line "%s"', line)
            raise LineParseException(f'Failed to parse line "{line}"') from e

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
    def message_data_escaped(self):
        return self._msg_data_escaped

    @property
    def message_data(self):
        return bytearray(re.sub(r'\[[0-9]{1,3}\]', lambda matchobj: chr(int(matchobj.group(0)[1:-1])), self._msg_data_escaped), 'ascii')

    @property
    def message_rest(self):
        return self._msg_rest
