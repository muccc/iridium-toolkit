#!/usr/bin/env python
##################################################
# Gnuradio Python Flow Graph
# Title: Top Block
# Generated: Sun Mar  8 04:59:10 2015
##################################################

from gnuradio import blocks
from gnuradio import eng_notation
from gnuradio import filter
from gnuradio import gr
from gnuradio.eng_option import eng_option
from gnuradio.filter import firdes
from optparse import OptionParser
import osmosdr

class top_block(gr.top_block):

    def __init__(self):
        gr.top_block.__init__(self)
        ##################################################
        # Variables
        ##################################################
        self.samp_rate = samp_rate = 1e6

        ##################################################
        # Blocks
        ##################################################
        self.rtlsdr_source_0 = osmosdr.source( args="numchan=" + str(1) + " " + "" )
        self.rtlsdr_source_0.set_sample_rate(samp_rate)
        self.rtlsdr_source_0.set_center_freq(1.626e9 + 150e3, 0)
        self.rtlsdr_source_0.set_freq_corr(0, 0)
        self.rtlsdr_source_0.set_dc_offset_mode(0, 0)
        self.rtlsdr_source_0.set_iq_balance_mode(0, 0)
        self.rtlsdr_source_0.set_gain_mode(False, 0)
        self.rtlsdr_source_0.set_gain(25, 0)
        self.rtlsdr_source_0.set_if_gain(25, 0)
        self.rtlsdr_source_0.set_bb_gain(20, 0)
        self.rtlsdr_source_0.set_antenna("", 0)
        self.rtlsdr_source_0.set_bandwidth(0, 0)
          
        self.freq_xlating_fir_filter_xxx_0 = filter.freq_xlating_fir_filter_ccc(4, (filter.firdes.low_pass(1, samp_rate, 100e3, 25e3)), 250e3, samp_rate)
        #self.blocks_file_sink_0 = blocks.file_sink(gr.sizeof_gr_complex*1, "/tmp/fifo", False)
        self.blocks_file_sink_0 = blocks.file_sink(gr.sizeof_gr_complex*1, "/dev/fd/3", False)
        self.blocks_file_sink_0.set_unbuffered(False)

        ##################################################
        # Connections
        ##################################################
        self.connect((self.freq_xlating_fir_filter_xxx_0, 0), (self.blocks_file_sink_0, 0))
        self.connect((self.rtlsdr_source_0, 0), (self.freq_xlating_fir_filter_xxx_0, 0))


# QT sink close method reimplementation

    def get_samp_rate(self):
        return self.samp_rate

    def set_samp_rate(self, samp_rate):
        self.samp_rate = samp_rate
        self.freq_xlating_fir_filter_xxx_0.set_taps((filter.firdes.low_pass(1, self.samp_rate, 100e3, 25e3)))
        self.rtlsdr_source_0.set_sample_rate(self.samp_rate)

if __name__ == '__main__':
    import ctypes
    import sys
    parser = OptionParser(option_class=eng_option, usage="%prog: [options]")
    (options, args) = parser.parse_args()
    tb = top_block()
    tb.run()

