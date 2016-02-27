#!/usr/bin/env python
# vim: set ts=4 sw=4 tw=0 et pm=:
import sys
import math
import numpy
import os.path
import re
import getopt
import time
from functools import partial
from gnuradio import gr
from gnuradio import blocks
import iridium_toolkit
import osmosdr

class burst_sink_c(gr.sync_block):
    def __init__(self, callback):
        gr.sync_block.__init__(self,
            name="burst_sink_c",
            in_sig=[numpy.complex64],
            out_sig=[])

        self._bursts = {}
        self._callback = callback

    def work(self, input_items, output_items):
        input = input_items[0]
        n = len(input)
        tags = self.get_tags_in_window(0, 0, n)
        for tag in tags:
            if str(tag.key) == 'new_burst':
                id = gr.pmt.to_uint64(gr.pmt.vector_ref(tag.value, 0))
                rel_freq = gr.pmt.to_float(gr.pmt.vector_ref(tag.value, 1))
                mag = gr.pmt.to_float(gr.pmt.vector_ref(tag.value, 2))
                self._bursts[id] = [self.nitems_read(0), mag, rel_freq, numpy.array((), dtype=numpy.complex64)]
                #print "new burst:", id, rel_freq
            elif str(tag.key) == 'gone_burst':
                id = gr.pmt.to_uint64(tag.value)
                #print "gone burst", id
                self._callback(self._bursts[id])
                del self._bursts[id]

        for burst in self._bursts:
            self._bursts[burst][3] = numpy.append(self._bursts[burst][3], input)

        return n

    
class Detector(object):
    def __init__(self, sample_rate, threshold=7.0, verbose=False, signal_width=40e3):
        self._sample_rate = sample_rate
        self._verbose = verbose
        self._threshold = threshold

        self._fft_size=int(math.pow(2, 1+int(math.log(self._sample_rate/1000,2)))) # fft is approx 1ms long
        self._bin_size = float(self._fft_size)/self._sample_rate * 1000 # How many ms is one fft now?
        self._burst_pre_len = self._fft_size
        self._burst_post_len = 8 * self._fft_size
        self._burst_width= int(signal_width / (self._sample_rate / self._fft_size)) # Area to ignore around an already found signal in FFT bins
        
        if self._verbose:
            print "fft_size=%d (=> %f ms)" % (self._fft_size,self._bin_size)
            print "require %.1f dB" % self._threshold
            print "signal_width: %d (= %.1f Hz)" % (self._signal_width,self._signal_width*self._sample_rate/self._fft_size)

    def process(self, data_collector, filename=None, sample_format=None):
        self._data_collector = data_collector
        self._filename = filename

        if filename.endswith(".conf"):
            import ConfigParser
            config = ConfigParser.ConfigParser()
            config.read(filename)
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
            source = blocks.file_source(itemsize=itemsize, filename=filename, repeat=False)

        tb = gr.top_block()

        fft_burst_tagger = iridium_toolkit.fft_burst_tagger(fft_size=self._fft_size,
                                burst_pre_len=self._burst_pre_len, burst_post_len=self._burst_post_len,
                                burst_width=self._burst_width, debug=self._verbose)

        sink = burst_sink_c(self._new_burst)

        if converter:
            tb.connect(source, converter, fft_burst_tagger, sink)
        else:
            tb.connect(source, fft_burst_tagger, sink)

        tb.run()

    def _new_burst(self, burst):
        #print "new burst at", burst[0] / float(self._sample_rate)
        #print "len:", len(burst[3])
        self._data_collector(burst[0] / float(self._sample_rate), burst[1], burst[2] * self._sample_rate, burst[3])
        pass

def file_collector(basename, time_stamp, signal_strength, bin_index, freq, signal):
    filename = "/tmp/bursts/%s-%07d-o%+07d.det" % (os.path.basename(basename), time_stamp, freq)
    signal.tofile(filename)

if __name__ == "__main__":
    options, remainder = getopt.getopt(sys.argv[1:], 'r:d:vf:p:', [
                                                            'rate=', 
                                                            'db=', 
                                                            'verbose',
                                                            'format=',
                                                            'pipe',
                                                            ])
    sample_rate = None
    verbose = False
    threshold = 8.5 # 8.5 dB over noise
    fmt = None
    pipe = None
    online = False
    filename = None

    for opt, arg in options:
        if opt in ('-r', '--rate'):
            sample_rate = int(arg)
        elif opt in ('-d', '--db'):
            threshold = float(arg)
        elif opt in ('-v', '--verbose'):
            verbose = True
        elif opt in ('-f', '--format'):
            fmt = arg
        elif opt in ('-p', '--pipe'):
            pipe = arg
        elif opt in ('-o', '--online'):
            online = True

    if sample_rate == None:
        print >> sys.stderr, "Sample rate missing!"
        exit(1)

    if fmt == None and not online:
        print >> sys.stderr, "Need to specify the sample format (one of rtl, hackrf, sc16, float) in offline mode"
        exit(1)

    basename=None

    if len(remainder)==0 or pipe !=None:
        if pipe==None:
            print >> sys.stderr, "WARN: pipe mode not set"
            pipe="t"
        basename="i-%.4f-%s1"%(time.time(),pipe)
        print >> sys.stderr, basename
        if not online:
            filename = "/dev/stdin"
    else:
        filename = remainder[0]
        basename = re.sub('\.[^.]*$', '', filename)

    d = Detector(sample_rate, threshold=threshold, verbose=verbose)
    d.process(partial(file_collector, basename), filename, sample_format=fmt)

