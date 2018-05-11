#!/usr/bin/env python

import unittest

from .stats_voc import VocLine


class VocLineTest(unittest.TestCase):

    def test_empty_input(self):
        with self.assertRaises(Exception):
            VocLine('')

def main():
    unittest.main()


if __name__ == "__main__":
    main()
