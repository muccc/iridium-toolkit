#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import print_function
import sys
import glob
import parser
import pytest
from mock import patch

TESTS={
    # Test header format
    'hdr': [('p-1598047209-e000 000000841.3554 1625695104 100%   0.044', '')],

    # Test LCW parsing
    'lcw': [],

    # Test Frame parsing
    'frame': [
        ('ISY: - Sync=OK', '0001000110111111000000100000001000100011000100 010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101')
    ]
}

def add_tests():
    """Add tests from filesystem"""
    for typ in ['frame']:
        for file in glob.glob("testdata.%s*"%typ):
            f=open(file)
            for line in f:
                expected=line.strip()
                while expected[0]=='#':
                    expected=next(f).strip()
                bits=next(f).strip()
                TESTS[typ].append((expected, bits))

@pytest.mark.parametrize("expected,bits", TESTS['hdr'])
def test_bits_header(expected, bits):
    line=frame_to_line(bits)
    with patch('fileinput.lineno', return_value='0'):
        p=parser.Message(line).upgrade()
        assert p._pretty_header() == expected

@pytest.mark.parametrize("expected,bits", TESTS['frame'])
def test_bits_without_header(expected, bits):
    line=frame_to_line(bits)
    with patch('fileinput.lineno', return_value = '0'):
        with patch('parser.IridiumMessage._pretty_header', return_value = '-'):
            parser.freqclass=False
            p=parser.Message(line).upgrade()
            assert p.pretty().strip() == expected

def do_test_frame(bits):
    line=frame_to_line(bits)
    with patch('fileinput.lineno', return_value = '0'):
        with patch('parser.IridiumMessage._pretty_header', return_value = '-'):
            p=parser.Message(line).upgrade()
            if p.error:
                return "ERR:"+", ".join(p.error_msg)
            else:
                return p.pretty()

def bits_to_line(bits):
    bits=bits.replace(" ","")
    syms=(len(bits)-len(parser.iridium_access))/2
    hdr='%s: %s %012.4f %10d A:%s I:%011d %3d%% %7.5f %3d'%('RAW', 'i-1598047209-t1', 841.3554, 1625695104, 'OK', 20, 100, 0.04370, syms)
    return hdr+' '+bits

def frame_to_line(bits):
    return bits_to_line(parser.iridium_access+bits)

def summarize_tests():
    """Print quick summary of tests to verify what was loaded from the filesystem"""
    print("Test dictionary:")
    for key in sorted(TESTS):
        print("  %-7s: %2d"%(key, len(TESTS[key])))
        if key=="frame":
            types={}
            for expected,_ in TESTS[key]:
                typ=expected[0:3]
                if not typ in types:
                    types[typ]=0
                types[typ]+=1
            for typ in sorted(types):
                print("  - %3s: %2d"%(typ, types[typ]))

add_tests()

if __name__ == "__main__":
    summarize_tests()
    pytest.main([sys.argv[0]])
