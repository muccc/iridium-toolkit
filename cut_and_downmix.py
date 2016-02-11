#!/usr/bin/env python
# vim: set ts=4 sw=4 tw=0 et pm=:
import struct
import sys
import math
import numpy
import os.path
import cmath
import filters
import re
import iq
import getopt
import scipy.signal
import complex_sync_search
import time
import iridium
import gnuradio.gr
import gnuradio.blocks
import gnuradio.filter
import collections

import matplotlib.pyplot as plt

def normalize(v):
    m = max(v)
    return [x/m for x in v]

class DownmixError(Exception):
    pass

class source_c(gnuradio.gr.sync_block):
    def __init__(self):
        gnuradio.gr.sync_block.__init__(self,
            name="source_c",
            in_sig=[],
            out_sig=[numpy.complex64])

    def set_data(self, data):
        self._data = data
        self._data_index = 0
        self._data_left = len(self._data)

    def work(self, input_items, output_items):
        out = output_items[0]
        n = len(out)

        if self._data_left >= n:
            out[:] = self._data[self._data_index:self._data_index+n]
        elif self._data_left > 0:
            n = self._data_left
            out = self._data[self._data_index:self._data_index+n]
        else:
            return -1

        self._data_index += n
        self._data_left -= n
        return n

class CutAndDownmix(object):
    def __init__(self, center, input_sample_rate, search_depth=7e-3, search_window=50e3,
                    symbols_per_second=25000, verbose=False):

        self._center = center
        self._input_sample_rate = int(input_sample_rate)
        self._output_sample_rate = 500000
        #self._output_sample_rate = 250000

        if self._input_sample_rate % self._output_sample_rate:
            raise RuntimeError("Input sample rate must be a multiple of %d" % self._output_sample_rate)
            
        self._decimation = self._input_sample_rate / self._output_sample_rate

        self._search_depth = search_depth
        self._symbols_per_second = symbols_per_second
        self._output_samples_per_symbol = self._output_sample_rate/self._symbols_per_second
        self._verbose = verbose
        #self._verbose = True

        self._input_low_pass = scipy.signal.firwin(401, float(search_window)/self._input_sample_rate)
        self._low_pass2 = scipy.signal.firwin(401, 10e3/self._output_sample_rate)
        self._rrc = filters.rrcosfilter(51, 0.4, 1./self._symbols_per_second, self._output_sample_rate)[1]

        self._sync_search = complex_sync_search.ComplexSyncSearch(self._output_sample_rate, verbose=self._verbose)

        self._pre_start_samples = int(0.1e-3 * self._output_sample_rate)

        self._tb = gnuradio.gr.top_block()

        self._src = source_c()

        self._dst = gnuradio.blocks.vector_sink_c()

        #self._xlating_filter = gnuradio.filter.freq_xlating_fir_filter_ccf(self._decimation,
        #        taps=self._input_low_pass, center_freq=0, sampling_freq=self._input_sample_rate)

        self._xlating_filter = gnuradio.filter.freq_xlating_fft_filter_ccc(decim=self._decimation,
                taps=(self._input_low_pass * 1+0j), center_freq=0, samp_rate=self._input_sample_rate)

        # Precompute a few filters to swap in. It takes some time to change the center frequency on the fly.
        #self._xlating_filters = {}
        #for center_freq in range(-int(self._input_sample_rate)/2, int(self._input_sample_rate)/2, 5000):
        #    self._xlating_filters[center_freq] = gnuradio.filter.freq_xlating_fft_filter_ccc(decim=self._decimation,
        #        taps=(self._input_low_pass * 1+0j), center_freq=center_freq, samp_rate=self._input_sample_rate)

        self._tb.connect(self._src, self._xlating_filter)
        self._tb.connect(self._xlating_filter, self._dst)

        self._timing_debug = False

        self._timing_signals = 0
        self._timing_accounts_sum = {}
        self._input_lengths = 0

        if self._verbose:
            print 'input sample_rate', self._input_sample_rate
            print 'output sample_rate', self._output_sample_rate

    def _timing_start(self):
        if not self._timing_debug: return
        self._timing_accounts = collections.OrderedDict()
        self._timing_real_start = time.time()
         
    def _timing_start_step(self):
        if not self._timing_debug: return
        self._timing_step_start = time.time()

    def _timing_finish_step(self, account_name):
        if not self._timing_debug: return
        t = time.time() - self._timing_step_start
        self._timing_accounts[account_name] = t
        
    def _timing_finish(self, length):
        if not self._timing_debug: return

        self._timing_signals += 1
        self._input_lengths += length

        total = sum(self._timing_accounts.values())
        self._timing_accounts['total'] = total
        
        real = time.time() - self._timing_real_start
        self._timing_accounts['real'] = real

        for account_name in self._timing_accounts: 
            if account_name not in self._timing_accounts_sum:
                self._timing_accounts_sum[account_name] = 0.0
            self._timing_accounts_sum[account_name] += self._timing_accounts[account_name]

        if self._timing_signals == 100:
            avg_len = float(self._input_lengths) / self._timing_signals
            print >> sys.stderr, "Input Samplerate: %d, Output Samplerate: %d, Signals: %d, Signal len: %d" % (self._input_sample_rate, self._output_sample_rate, self._timing_signals, avg_len)
            for account in self._timing_accounts: 
                t = self._timing_accounts[account]
                t_sum = self._timing_accounts_sum[account]
                t_avg = t_sum / self._timing_signals

                print >> sys.stderr, "%030s: %5.02f" % (account, t_avg * 1000)

            print >> sys.stderr, "--------------------------------"

            self._timing_signals = 0
            self._timing_accounts_sum = {}
            self._input_lengths = 0


    @property
    def output_sample_rate(self):
        return self._output_sample_rate

    def _fft(self, slice, fft_len=None):
        if fft_len:
            fft_result = numpy.fft.fft(slice, fft_len)
        else:
            fft_result = numpy.fft.fft(slice)

        fft_freq = numpy.fft.fftfreq(len(fft_result))
        fft_result = numpy.fft.fftshift(fft_result)
        fft_freq = numpy.fft.fftshift(fft_freq)

        return (fft_result, fft_freq)

    def _signal_start(self, signal):
        signal_mag = numpy.abs(signal)
        signal_mag_lp = scipy.signal.fftconvolve(signal_mag, self._low_pass2, mode='same')

        threshold = numpy.max(signal_mag_lp) * 0.5
        start = max(numpy.where(signal_mag_lp>threshold)[0][0] - self._pre_start_samples, 0)
        
        #plt.plot(signal_mag)
        #plt.plot(signal_mag_lp)
        #plt.plot(start, signal_mag_lp[start], 'b*')
        #plt.show()
        return start

    def cut_and_downmix(self, signal, search_offset, direction=None, frequency_offset=0, phase_offset=0):
        if self._verbose:
            iq.write("/tmp/signal.cfile", signal)

        input_length = len(signal)
        self._timing_start()

        self._timing_start_step()
        self._src.set_data(signal)
        self._timing_finish_step("set_data")

        self._timing_start_step()
        self._xlating_filter.set_center_freq(search_offset)
        #search_offset = int(search_offset) / 5000 * 5000
        #self._tb.connect(self._src, self._xlating_filters[search_offset])
        #self._tb.connect(self._xlating_filters[search_offset], self._dst)
        self._timing_finish_step("set_center_freq")

        self._timing_start_step()
        self._dst.reset()
        self._timing_finish_step("dst.reset")

        self._timing_start_step()
        self._tb.run()
        #self._tb.disconnect_all()
        self._timing_finish_step("xlating_filter")

        self._timing_start_step()
        signal = numpy.array(self._dst.data())
        self._timing_finish_step("get_data")

        self._timing_start_step()
        signal_center = self._center + search_offset
        if self._verbose:
            iq.write("/tmp/signal-filtered-deci.cfile", signal)

        # Ring Alert and Pager Channels have a 64 symbol preamble
        if signal_center > 1626000000:
            preamble_length = 64
            direction = iridium.DOWNLINK
        else:
            preamble_length = 16

        # Take the FFT over the preamble + 10 symbols from the unique word (UW)
        fft_length = 2 ** int(math.log(self._output_samples_per_symbol * (preamble_length + 10), 2))
        if self._verbose:
            print 'fft_length', fft_length

        #signal_mag = [abs(x) for x in signal]
        #plt.plot(normalize(signal_mag))
        self._timing_finish_step("misc")

        self._timing_start_step()
        begin = self._signal_start(signal[:int(self._search_depth * self._output_sample_rate)])
        signal = signal[begin:]
        self._timing_finish_step("signal_start")

        if self._verbose:
            print 'begin', begin
            iq.write("/tmp/signal-filtered-deci-cut-start.cfile", signal)
            iq.write("/tmp/signal-filtered-deci-cut-start-x2.cfile", signal ** 2)

        self._timing_start_step()
        signal_preamble = signal[:fft_length] ** 2

        #plt.plot([begin+skip, begin+skip], [0, 1], 'r')
        #plt.plot([begin+skip+fft_length, begin+skip+fft_length], [0, 1], 'r')

        if self._verbose:
            iq.write("/tmp/preamble-x2.cfile", signal_preamble)

        #plt.plot([x.real for x in signal_preamble])
        #plt.plot([x.imag for x in signal_preamble])
        #plt.show()

        signal_preamble = signal_preamble * numpy.blackman(len(signal_preamble))
        # Increase size of FFT to inrease resolution
        fft_result, fft_freq = self._fft(signal_preamble, len(signal_preamble) * 16)
        fft_bin_size = fft_freq[101] - fft_freq[100]

        if self._verbose:
            print 'FFT bin size (Hz)', fft_bin_size * self._output_sample_rate

        # Use magnitude of FFT to detect maximum and correct the used bin
        mag = numpy.absolute(fft_result)
        max_index = numpy.argmax(mag)

        if self._verbose:
            print 'FFT peak bin:', max_index
            print 'FFT peak bin (Hz)', (fft_freq[max_index] * self._output_sample_rate) / 2

        #see http://www.dsprelated.com/dspbooks/sasp/Quadratic_Interpolation_Spectral_Peaks.html
        alpha = abs(fft_result[max_index-1])
        beta = abs(fft_result[max_index])
        gamma = abs(fft_result[max_index+1])
        correction = 0.5 * (alpha - gamma) / (alpha - 2*beta + gamma)
        real_index = max_index + correction

        a = math.floor(real_index)
        corrected_index = fft_freq[a] + (real_index - a) * fft_bin_size
        offset_freq = corrected_index * self._output_sample_rate / 2.

        if self._verbose:
            print 'FFT bin correction', correction
            print 'FFT interpolated peak:', max_index - correction
            print 'FFT interpolated peak (Hz):', offset_freq

        self._timing_finish_step("fft")

        self._timing_start_step()
        # Generate a complex signal at offset_freq Hz.
        shift_signal = numpy.exp(complex(0,-1)*numpy.arange(len(signal))*2*numpy.pi*offset_freq/float(self._output_sample_rate))

        # Multiply the two signals, effectively shifting signal by offset_freq
        signal = signal*shift_signal
        self._timing_finish_step("shift_fft")

        if self._verbose:
            iq.write("/tmp/signal-filtered-deci-cut-start-shift.cfile", signal)

        self._timing_start_step()
        preamble_uw = signal[:(preamble_length + 16) * self._output_samples_per_symbol]

        if direction is not None:
            offset, phase, _ = self._sync_search.estimate_sync_word_freq(preamble_uw, preamble_length, direction)
        else:
            offset_dl, phase_dl, confidence_dl = self._sync_search.estimate_sync_word_freq(preamble_uw, preamble_length, iridium.DOWNLINK)
            offset_ul, phase_ul, confidence_ul = self._sync_search.estimate_sync_word_freq(preamble_uw, preamble_length, iridium.UPLINK)

            if confidence_dl > confidence_ul:
                direction = iridium.DOWNLINK
                offset = offset_dl
                phase = phase_dl
            else:
                direction = iridium.UPLINK
                offset = offset_ul
                phase = phase_ul

        if offset == None:
            raise DownmixError("No valid freq offset for sync word found")

        offset = -offset

        phase += phase_offset
        offset += frequency_offset
        self._timing_finish_step("complex_sync_search")


        self._timing_start_step()
        shift_signal = numpy.exp(complex(0,-1)*numpy.arange(len(signal))*2*numpy.pi*offset/float(self._output_sample_rate))
        signal = signal*shift_signal
        offset_freq += offset
        self._timing_finish_step("shift_css")

        if self._verbose:
            iq.write("/tmp/signal-filtered-deci-cut-start-shift-shift.cfile", signal)

        self._timing_start_step()
        #plt.plot([cmath.phase(x) for x in signal[:fft_length]])
        # Multiplying with a complex number on the unit circle
        # just changes the angle.
        # See http://www.mash.dept.shef.ac.uk/Resources/7_6multiplicationanddivisionpolarform.pdf
        signal = signal * cmath.rect(1,-phase)
        self._timing_finish_step("shift_phase")

        if self._verbose:
            iq.write("/tmp/signal-filtered-deci-cut-start-shift-shift-rotate.cfile", signal)

        self._timing_start_step()
        signal = numpy.convolve(signal, self._rrc, 'same')
        self._timing_finish_step("filter_rrc")

        #plt.plot([x.real for x in signal])
        #plt.plot([x.imag for x in signal])

        #print max(([abs(x.real) for x in signal]))
        #print max(([abs(x.imag) for x in signal]))

        #plt.plot(numpy.absolute(fft_result))
        #plt.plot(fft_freq, numpy.absolute(fft_result))
        #plt.plot([], [bins[bin]], 'rs')
        #plt.plot(mag)
        #plt.plot(signal_preamble)
        #plt.show()

        self._timing_finish(input_length)
        return (signal, signal_center+offset_freq, direction)

if __name__ == "__main__":

    options, remainder = getopt.getopt(sys.argv[1:], 'o:w:c:r:s:f:v:p:', ['search-offset=',
                                                            'window=',
                                                            'center=',
                                                            'rate=',
                                                            'search-depth=',
                                                            'verbose',
                                                            'frequency-offset=',
                                                            'phase-offset=',
                                                            'uplink',
                                                            'downlink'
                                                            ])
    center = None
    sample_rate = None
    symbols_per_second = 25000
    search_offset = None
    search_window = 50e3
    search_depth = 0.007
    verbose = False
    frequency_offset = 0
    phase_offset = 0
    direction = None

    for opt, arg in options:
        if opt in ('-o', '--search-offset'):
            search_offset = int(arg)
        if opt in ('-w', '--search-window'):
            search_window = int(arg)
        elif opt in ('-c', '--center'):
            center = int(arg)
        elif opt in ('-r', '--rate'):
            sample_rate = int(arg)
        elif opt in ('-s', '--search'):
            search_depth = float(arg)
        elif opt in ('-f', '--frequency-offset'):
            frequency_offset = float(arg)
        elif opt in ('-p', '--phase-offset'):
            phase_offset = float(arg)/180. * numpy.pi;
        elif opt in ('-v', '--verbose'):
            verbose = True
        elif opt == '--uplink':
            direction = iridium.UPLINK
        elif opt == '--downlink':
            direction = iridium.DOWNLINK

    if sample_rate == None:
        print >> sys.stderr, "Sample rate missing!"
        exit(1)
    if center == None:
        print >> sys.stderr, "Need to specify center frequency!"
        exit(1)

    if len(remainder)==0:
        file_name = "/dev/stdin"
        basename="stdin"
    else:
        file_name = remainder[0]
        basename= filename= re.sub('\.[^.]*$','',file_name)

    signal = iq.read(file_name)

    cad = CutAndDownmix(center=center, input_sample_rate=sample_rate, symbols_per_second=symbols_per_second,
                            search_depth=search_depth, verbose=verbose, search_window=search_window)
    #for i in range(100):
    #    cad.cut_and_downmix(signal=signal[:], search_offset=search_offset, direction=direction, frequency_offset=frequency_offset, phase_offset=phase_offset)

    signal, freq, _ = cad.cut_and_downmix(signal=signal, search_offset=search_offset, direction=direction, frequency_offset=frequency_offset, phase_offset=phase_offset)

    iq.write("%s-f%010d.cut" % (os.path.basename(basename), freq), signal)
    print "output=","%s-f%10d.cut" % (os.path.basename(basename), freq)
