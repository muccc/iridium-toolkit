#!/usr/bin/env python
# vim: set ts=4 sw=4 tw=0 et pm=:

import iridium_toolkit

import osmosdr
import gnuradio.filter

from gnuradio import gr
from gnuradio import blocks

import sys
import math


class FlowGraph(gr.top_block):
    def __init__(self, center_frequency, sample_rate, decimation, filename, sample_format=None, threshold=7.0, signal_width=40e3, verbose=False):
        gr.top_block.__init__(self, "Top Block")
        self._center_frequency = center_frequency
        self._signal_width = 40e3
        self._input_sample_rate = sample_rate
        self._verbose = verbose
        self._threshold = threshold
        self._filename = filename

        self._fft_size = int(math.pow(2, 1 + int(math.log(self._input_sample_rate / 1000, 2)))) # fft is approx 1ms long
        self._burst_pre_len = self._fft_size
        self._burst_post_len = 8 * self._fft_size
        self._burst_width= int(self._signal_width / (self._input_sample_rate / self._fft_size)) # Area to ignore around an already found signal in FFT bins
        if decimation > 1:
            self._use_pfb = True

            # We will set up a filter bank with an odd number of outputs and
            # and an over sampling ratio to still get the desired decimation.

            # The goal is to still catch signal which (due to doppler shift) end up
            # on the border of two channels.

            # For this to work the desired decimation must be even.
            if decimation % 2:
                raise RuntimeError("The desired decimation must be 1 or an even number")

            self._channels = decimation + 1
            self._pfb_over_sample_ratio = self._channels / (self._channels - 1.)
            pfb_output_sample_rate = int(round(float(self._input_sample_rate) / self._channels * self._pfb_over_sample_ratio))
            assert pfb_output_sample_rate == self._input_sample_rate / decimation


            # The over sampled region of the FIR filter contains half of the signal width and
            # the transition region of the FIR filter.
            # The bandwidth is simply increased by the signal width.
            # A signal which has its center frequency directly on the border of
            # two channels will reconstruct correclty on both channels.
            self._fir_bw = (self._input_sample_rate / self._channels + self._signal_width) / 2

            # The remaining bandwidth inside the over samples region is used to
            # contain the transistion region of the filter.
            # It can be multiplied by two as it is allowed to continue into the
            # transition region of the neighboring channel.
            # TODO: Draw a nice graphic how this works.
            self._fir_tw = (pfb_output_sample_rate / 2 - self._fir_bw) * 2

            # If the over sampling ratio is not large enough, there is not
            # enough room to construct a transition region.
            if self._fir_tw < 0:
                raise RuntimeError("PFB over sampling ratio not enough to create a working FIR filter")

            self._pfb_fir_filter = gnuradio.filter.firdes.low_pass_2(1, self._input_sample_rate, self._fir_bw, self._fir_tw, 60)
            
            # If the transition width approaches 0, the filter size goes up significantly.
            if self._pfb_fir_filter.ntaps() > 200:
                print >> sys.stderr, "Warning: The PFB FIR filter has an abnormal large number of taps."
                print >> sys.stderr, "Consider reducing the decimation factor or increase the over sampling ratio"

            
            self._burst_sample_rate = pfb_output_sample_rate
            if self._verbose:
                print >> sys.stderr, "self._channels", self._channels
                print >> sys.stderr, "self._pfb_over_sample_ratio", self._pfb_over_sample_ratio
                print >> sys.stderr, "self._fir_bw", self._fir_bw
                print >> sys.stderr, "self._fir_tw", self._fir_tw
        else:
            self._use_pfb = False
            self._burst_sample_rate = self._input_sample_rate

        if self._verbose:
            print >> sys.stderr, "require %.1f dB" % self._threshold
            print >> sys.stderr, "burst_width: %d (= %.1f Hz)" % (self._burst_width, self._burst_width*self._input_sample_rate/self._fft_size)


        if self._filename.endswith(".conf"):
            import ConfigParser
            config = ConfigParser.ConfigParser()
            config.read(self._filename)
            items = config.items("osmosdr-source")
            d = {key: value for key, value in items}

            if 'device_args' in d:
                source = osmosdr.source(args=d['device_args'])
            else:
                source = osmosdr.source()

            source.set_sample_rate(int(d['sample_rate']))
            source.set_center_freq(int(d['center_freq']), 0)
            if 'gain' in d:
                source.set_gain(int(d['gain']), 0)
            if 'if_gain' in d:
                source.set_if_gain(int(d['if_gain']), 0)
            if 'bb_gain' in d:
                source.set_bb_gain(int(d['bb_gain']), 0)
            if 'bandwidth' in d:
                source.set_bandwidth(int(d['bandwidth']), 0)
            #source.set_freq_corr($corr0, 0)
            #source.set_dc_offset_mode($dc_offset_mode0, 0)
            #source.set_iq_balance_mode($iq_balance_mode0, 0)
            #source.set_gain_mode($gain_mode0, 0)
            #source.set_antenna($ant0, 0)

            converter = None
        else:
            if sample_format == "rtl":
                converter = iridium_toolkit.iuchar_to_complex()
                itemsize = gr.sizeof_char
            elif sample_format == "hackrf":
                converter = blocks.interleaved_char_to_complex()
                itemsize = gr.sizeof_char
            elif sample_format == "sc16":
                converter = blocks.interleaved_short_to_complex()
                itemsize = gr.sizeof_short
            elif sample_format == "float":
                converter = None
                itemsize = gr.sizeof_gr_complex
            else:
                raise RuntimeError("Unknown sample format for offline mode given")
            source = blocks.file_source(itemsize=itemsize, filename=self._filename, repeat=False)

        # Just to keep the code below a bit more portable
        tb = self

        #fft_burst_tagger::make(float center_frequency, int fft_size, int sample_rate,
        #                    int burst_pre_len, int burst_post_len, int burst_width,
        #                    int max_bursts, float threshold, int history_size, bool debug)
 
        fft_burst_tagger = iridium_toolkit.fft_burst_tagger(center_frequency=self._center_frequency,
                                fft_size=self._fft_size,
                                sample_rate=self._input_sample_rate,
                                burst_pre_len=self._burst_pre_len, burst_post_len=self._burst_post_len,
                                burst_width=self._burst_width,
                                max_bursts=100,
                                threshold=self._threshold,
                                history_size=512,
                                debug=self._verbose)

        # Initial filter to filter the detected bursts. Runs at burst_sample_rate. Used to decimate the signal.
        # TODO: Should probably be set to self._signal_width
        input_filter = gnuradio.filter.firdes.low_pass_2(1, self._burst_sample_rate, 50e3/2, 50e3/2/2, 60)

        # Filter to find the start of the signal. Should be fairly narrow.
        # TODO: 250000 appears as magic number here
        start_finder_filter = gnuradio.filter.firdes.low_pass_2(1, 250000, 10e3, 10e3, 60)

        burst_downmix = iridium_toolkit.burst_downmix(self._burst_sample_rate, int(0.007 * 250000), 1000, (input_filter), (start_finder_filter))

        if self._use_pfb:
            pdu_converters = []
            sinks = []

            for channel in range(self._channels):
                center = channel if channel <= self._channels / 2 else (channel - self._channels)

                # TODO: First paramter is max burst size. Make it dynamic (about 100 ms).
                # Second and third parameters tell the block where after the PFB it sits.
                pdu_converters.append(iridium_toolkit.tagged_burst_to_pdu(100000, center / float(self._channels), 1. / self._channels))

            #pfb_debug_sinks = [blocks.file_sink(itemsize=gr.sizeof_gr_complex, filename="/tmp/channel-%d.f32"%i) for i in range(self._channels)]
            pfb_debug_sinks = None

            pfb = gnuradio.filter.pfb.channelizer_ccf(numchans=self._channels, taps=self._pfb_fir_filter, oversample_rate=self._pfb_over_sample_ratio)

            if converter:
                tb.connect(source, converter, fft_burst_tagger, pfb)
            else:
                tb.connect(source, fft_burst_tagger, pfb)

            for i in range(self._channels):
                tb.connect((pfb, i), pdu_converters[i])
                if pfb_debug_sinks:
                    tb.connect((pfb, i), pfb_debug_sinks[i])

                tb.msg_connect((pdu_converters[i], 'cpdus'), (burst_downmix, 'cpdus'))    
        else:
            burst_to_pdu = iridium_toolkit.tagged_burst_to_pdu(100000, 0.0, 1.0)

            if converter:
                tb.connect(source, converter, fft_burst_tagger, burst_to_pdu)
            else:
                tb.connect(source, fft_burst_tagger, burst_to_pdu)


            tb.msg_connect((burst_to_pdu, 'cpdus'), (burst_downmix, 'cpdus'))    

        iridium_qpsk_demod_cpp = iridium_toolkit.iridium_qpsk_demod_cpp()   

        # Final connection to the demodulator. It prints the output to stdout
        tb.msg_connect((burst_downmix, 'cpdus'), (iridium_qpsk_demod_cpp, 'cpdus'))    

