/* -*- c++ -*- */
/*
 * Copyright 2016 <+YOU OR YOUR COMPANY+>.
 *
 * This is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 3, or (at your option)
 * any later version.
 *
 * This software is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this software; see the file COPYING.  If not, write to
 * the Free Software Foundation, Inc., 51 Franklin Street,
 * Boston, MA 02110-1301, USA.
 */

#ifdef HAVE_CONFIG_H
#include "config.h"
#endif

#include "iridium.h"

#include <gnuradio/io_signature.h>
#include <gnuradio/fft/fft.h>
#include <gnuradio/fft/window.h>
#include <gnuradio/math.h>

#include "burst_downmix_impl.h"

#include <gnuradio/filter/firdes.h>
#include <volk/volk.h>

namespace gr {
  namespace iridium_toolkit {


    void write_data_c(const gr_complex * data, size_t len, int num)
    {
        char filename[256];
        sprintf(filename, "/tmp/signals/signal-%d.cfile", num);
        FILE * fp = fopen(filename, "wb");
        fwrite(data, sizeof(gr_complex), len, fp);
        fclose(fp);

        //fp = fopen("/tmp/last.cfile", "wb");
        //fwrite(data, sizeof(gr_complex), len, fp);
        //fclose(fp);

    }

    burst_downmix::sptr
    burst_downmix::make(int sample_rate, int search_depth,
            const std::vector<float> &input_taps,  const std::vector<float> &start_finder_taps)
    {
      return gnuradio::get_initial_sptr
        (new burst_downmix_impl(sample_rate, search_depth, input_taps, start_finder_taps));
    }

    /*
     * The private constructor
     */
    burst_downmix_impl::burst_downmix_impl(int sample_rate, int search_depth,
            const std::vector<float> &input_taps, const std::vector<float> &start_finder_taps)
      : gr::sync_block("burst_downmix",
              gr::io_signature::make(0, 0, 0),
              gr::io_signature::make(0, 0, 0)),
              d_output_sample_rate(250000),
              d_output_samples_per_symbol(d_output_sample_rate / iridium::SYMBOLS_PER_SECOND),
              d_max_burst_size(0),
              d_search_depth(search_depth),
              d_pre_start_samples(int(0.1e-3 * d_output_sample_rate)),

              // Take the FFT over the (short) preamble + 10 symbols from the unique word (UW)
              // (Frames with a 64 symbol preamble will use 26 symbols of the preamble)
              d_cfo_est_fft_size(pow(2, int(log(d_output_samples_per_symbol * (iridium::PREAMBLE_LENGTH_SHORT + 10)) / log(2)))),

              d_fft_over_size_facor(16),
              d_sync_search_len((iridium::PREAMBLE_LENGTH_LONG + iridium::UW_LENGTH + 2) * d_output_samples_per_symbol),
              d_debug(false),

              d_input(NULL),
              d_tmp_a(NULL),
              d_tmp_b(NULL),
              d_dl_preamble_reversed_conj_fft(NULL),
              d_ul_preamble_reversed_conj_fft(NULL),

              d_magnitude_f(NULL),
              d_magnitude_filtered_f(NULL),
              d_cfo_est_window_f(NULL),

              d_corr_fft(NULL),
              d_corr_ifft(NULL),

              d_input_fir(0, input_taps),
              d_start_finder_fir(0, start_finder_taps),
              d_rrc_fir(0, gr::filter::firdes::root_raised_cosine(1.0, d_output_sample_rate, iridium::SYMBOLS_PER_SECOND, .4, 51)),

              d_dl_preamble_reversed_conj(generate_sync_word(iridium::direction::DOWNLINK)),
              d_ul_preamble_reversed_conj(generate_sync_word(iridium::direction::UPLINK)),

              d_cfo_est_fft(fft::fft_complex(d_cfo_est_fft_size * d_fft_over_size_facor, true, 1))
    {
      initialize_cfo_est_fft();

      initialize_correlation_filter();

      message_port_register_in(pmt::mp("cpdus"));
      message_port_register_out(pmt::mp("cpdus"));
      set_msg_handler(pmt::mp("cpdus"), boost::bind(&burst_downmix_impl::handler, this, _1));

      if(d_debug) {
        std::cout << "Start filter size:" << d_start_finder_fir.ntaps() << " Search depth:" << d_search_depth << "\n";
      }
    }

    /*
     * Our virtual destructor.
     */
    burst_downmix_impl::~burst_downmix_impl()
    {
        if(d_input) {
          volk_free(d_input);
        }
        if(d_tmp_a) {
          volk_free(d_tmp_a);
        }
        if(d_tmp_b) {
          volk_free(d_tmp_b);
        }
        if(d_magnitude_f) {
          volk_free(d_magnitude_f);
        }
        if(d_magnitude_filtered_f) {
          volk_free(d_magnitude_filtered_f);
        }
        if(d_cfo_est_window_f) {
          free(d_cfo_est_window_f);
        }
        if(d_dl_preamble_reversed_conj_fft) {
          volk_free(d_dl_preamble_reversed_conj_fft);
        }
        if(d_ul_preamble_reversed_conj_fft) {
          volk_free(d_ul_preamble_reversed_conj_fft);
        }
        if(d_corr_fft) {
          delete d_corr_fft;
        }
        if(d_corr_ifft) {
          delete d_corr_ifft;
        }
    }

    std::vector<gr_complex> burst_downmix_impl::generate_sync_word(iridium::direction direction)
    {
      gr_complex s1 = gr_complex(-1, -1);
      gr_complex s0 = -s1;
      std::vector<gr_complex> sync_word;
      std::vector<gr_complex> uw_dl = {s0, s1, s1, s1, s1, s0, s0, s0, s1, s0, s0, s1};
      std::vector<gr_complex> uw_ul = {s1, s1, s0, s0, s0, s1, s0, s0, s1, s0, s1, s1};
      int i;

      if(direction == iridium::direction::DOWNLINK) {
        for(i = 0; i < iridium::PREAMBLE_LENGTH_SHORT; i++) {
          sync_word.push_back(s0);
        }
        sync_word.insert(std::end(sync_word), std::begin(uw_dl), std::end(uw_dl));
      } else if(direction == iridium::direction::UPLINK) {
        for(i = 0; i < iridium::PREAMBLE_LENGTH_SHORT / 2; i+=2) {
          sync_word.push_back(s1);
          sync_word.push_back(s0);
        }
        sync_word.insert(std::end(sync_word), std::begin(uw_ul), std::end(uw_ul));
      }

      std::vector<gr_complex> sync_word_padded;
      std::vector<gr_complex> padding;
      for(i = 0; i < d_output_samples_per_symbol - 1; i++) {
        padding.push_back(0);
      }

      for(gr_complex s : sync_word) {
        sync_word_padded.push_back(s);
        sync_word_padded.insert(std::end(sync_word_padded), std::begin(padding), std::end(padding));
      }

      // Remove the padding after the last symbol
      sync_word_padded.erase(std::end(sync_word_padded) - d_output_samples_per_symbol + 1, std::end(sync_word_padded));


      int half_fir_size = (d_rrc_fir.ntaps() - 1) / 2;
      std::vector<gr_complex> tmp(sync_word_padded);

      for(i = 0; i < half_fir_size; i++) {
        tmp.push_back(0);
        tmp.insert(tmp.begin(), 0);
      }

      // TODO: Maybe do a 'full' convolution including the borders
      d_rrc_fir.filterN(&sync_word_padded[0], &tmp[0], sync_word_padded.size());

      if(d_debug) {
        std::cout << "Sync Word Unpadded: ";
        for(gr_complex s : sync_word) {
          std::cout << s << ", ";
        }
        std::cout << std::endl;

        std::cout << "Sync Word Padded: ";
        for(gr_complex s : sync_word_padded) {
          std::cout << s << ", ";
        }
        std::cout << std::endl;
      }

      std::reverse(sync_word_padded.begin(), sync_word_padded.end());
      volk_32fc_conjugate_32fc(&sync_word_padded[0], &sync_word_padded[0], sync_word_padded.size());
      return sync_word_padded;
    }

    void burst_downmix_impl::initialize_cfo_est_fft(void)
    {
      // Only the first d_cfo_est_fft_size samples will be filled with data.
      // Zero out everyting first.
      memset(d_cfo_est_fft.get_inbuf(), 0, d_cfo_est_fft_size * d_fft_over_size_facor * sizeof(gr_complex));

      // Compute window and move it into aligned buffer
      std::vector<float> window = fft::window::build(fft::window::WIN_BLACKMAN, d_cfo_est_fft_size, 0);
      d_cfo_est_window_f = (float *)volk_malloc(sizeof(float) * d_cfo_est_fft_size, volk_get_alignment());
      memcpy(d_cfo_est_window_f, &window[0], sizeof(float) * d_cfo_est_fft_size);

      if(d_debug) {
        printf("fft_length=%d (%d)\n", d_cfo_est_fft_size, d_output_samples_per_symbol * (iridium::PREAMBLE_LENGTH_SHORT + 10));
      }
    }

    void burst_downmix_impl::initialize_correlation_filter(void)
    {
      // Based on code from synchronizer_v4_impl.cc in gr-burst

      // Make the FFT size a power of two
      int corr_fft_size_target = d_sync_search_len + d_dl_preamble_reversed_conj.size() - 1;
      d_corr_fft_size = pow(2, (int)(std::ceil(log(corr_fft_size_target) / log(2))));

      // TODO: We could increase the search size for free
      //d_sync_search_len = d_corr_fft_size - d_dl_preamble_reversed_conj.size() + 1;

      if(d_debug) {
        std::cout << "Conv FFT size:" << d_corr_fft_size << std::endl;
      }

      // Allocate space for the pre transformed filters
      d_dl_preamble_reversed_conj_fft = (gr_complex *)volk_malloc(d_corr_fft_size * sizeof(gr_complex), volk_get_alignment());
      d_ul_preamble_reversed_conj_fft = (gr_complex *)volk_malloc(d_corr_fft_size * sizeof(gr_complex), volk_get_alignment());

      // Temporary FFT to pre transform the filters
      fft::fft_complex fft_engine = fft::fft_complex(d_corr_fft_size);
      memset(fft_engine.get_inbuf(), 0, sizeof(gr_complex) * d_corr_fft_size);

      int sync_word_len = d_dl_preamble_reversed_conj.size();

      // Transform the filters
      memcpy(fft_engine.get_inbuf(), &d_dl_preamble_reversed_conj[0], sizeof(gr_complex) * sync_word_len);
      fft_engine.execute();
      memcpy(d_dl_preamble_reversed_conj_fft, fft_engine.get_outbuf(), sizeof(gr_complex) * d_corr_fft_size);

      memcpy(fft_engine.get_inbuf(), &d_ul_preamble_reversed_conj[0], sizeof(gr_complex) * sync_word_len);
      fft_engine.execute();
      memcpy(d_ul_preamble_reversed_conj_fft, fft_engine.get_outbuf(), sizeof(gr_complex) * d_corr_fft_size);

      // Update the size of the work FFTs
      // TODO: This could be moved to the initialization list
      d_corr_fft = new fft::fft_complex(d_corr_fft_size, true, 1);
      d_corr_ifft = new fft::fft_complex(d_corr_fft_size, false, 1);

      // The inputs need to zero, as we might not use it completely
      memset(d_corr_fft->get_inbuf(), 0, sizeof(gr_complex) * d_corr_fft_size);
    }

    void burst_downmix_impl::update_buffer_sizes(size_t burst_size)
    {
      if(burst_size > d_max_burst_size) {
        d_max_burst_size = burst_size;
        if(d_input) {
          volk_free(d_input);
        }
        d_input = (gr_complex *)volk_malloc(d_max_burst_size * sizeof(gr_complex), volk_get_alignment());

        if(d_tmp_a) {
          volk_free(d_tmp_a);
        }
        d_tmp_a = (gr_complex *)volk_malloc(d_max_burst_size * sizeof(gr_complex), volk_get_alignment());

        if(d_tmp_b) {
          volk_free(d_tmp_b);
        }
        d_tmp_b = (gr_complex *)volk_malloc(d_max_burst_size * sizeof(gr_complex), volk_get_alignment());

        if(d_magnitude_f) {
          volk_free(d_magnitude_f);
        }
        d_magnitude_f = (float *)volk_malloc(d_max_burst_size * sizeof(float), volk_get_alignment());

        if(d_magnitude_filtered_f) {
          volk_free(d_magnitude_filtered_f);
        }
        d_magnitude_filtered_f = (float *)volk_malloc(d_max_burst_size * sizeof(float), volk_get_alignment());
      }
    }

    void burst_downmix_impl::handler(pmt::pmt_t msg)
	{
      /*
       * Extract the burst and meta data from the cpdu
       */
      pmt::pmt_t samples = pmt::cdr(msg);
      size_t burst_size = pmt::length(samples);
      const gr_complex * burst = (const gr_complex*)pmt::c32vector_elements(samples, burst_size);

      pmt::pmt_t meta = pmt::car(msg);
      float relative_frequency = pmt::to_float(pmt::dict_ref(meta, pmt::mp("relative_frequency"), pmt::PMT_NIL));
      float center_frequency = pmt::to_float(pmt::dict_ref(meta, pmt::mp("center_frequency"), pmt::PMT_NIL));
      float sample_rate = pmt::to_float(pmt::dict_ref(meta, pmt::mp("sample_rate"), pmt::PMT_NIL));
      uint64_t id = pmt::to_uint64(pmt::dict_ref(meta, pmt::mp("id"), pmt::PMT_NIL));
      uint64_t offset = pmt::to_uint64(pmt::dict_ref(meta, pmt::mp("offset"), pmt::PMT_NIL));

      if(d_debug) {
        printf("---------------> id:%lu len:%ld\n", id, burst_size);
        float absolute_frequency = center_frequency + relative_frequency * sample_rate;
        printf("relative_frequency=%f, absolute_frequency=%f\n", relative_frequency, absolute_frequency);
      }

      // This burst might be larger than the one before.
      // Update he buffer sizes if needed.
      update_buffer_sizes(burst_size);


      /*
       * Shift the center frequency of the burst to the provided rough CFO estimate.
       */
      float phase_inc = 2 * M_PI * -relative_frequency;
      d_r.set_phase_incr(exp(gr_complex(0, phase_inc)));
      d_r.set_phase(gr_complex(1, 0));
      d_r.rotateN(d_tmp_a, burst, burst_size);
      center_frequency += relative_frequency * sample_rate;


      /*
       * Apply the initial low pass filter and decimate the burst.
       */
      int decimation = std::lround(sample_rate) / d_output_sample_rate;
      int output_samples = (burst_size - d_input_fir.ntaps() + 1) / decimation;
      d_input_fir.filterNdec(d_tmp_b, d_tmp_a, output_samples, decimation);
      sample_rate /= decimation;
      offset /= decimation;

      if(d_debug) {
        //write_data_c(d_tmp_b, output_samples, id + 1000);
      }


      /*
       * Use the center frequency to make some assumptions about the burst.
       */
      iridium::direction direction = iridium::direction::UNDEF;
      int max_frame_length = 0;

      // Simplex transmissions and broadcast frames might have a 64 symbol preamble.
      // We ignore that and cut away the extra 48 symbols.
      if(center_frequency > iridium::SIMPLEX_FREQUENCY_MIN) {
        // Frames above this frequency must be downlink and simplex framse
        // XXX: If the SDR is not configured well, there might be aliasing from low
        // frequencies in this region.
        direction = iridium::direction::DOWNLINK;
        max_frame_length = (iridium::PREAMBLE_LENGTH_SHORT + iridium::MAX_FRAME_LENGTH_SIMPLEX) * d_output_samples_per_symbol;
      } else {
        max_frame_length = (iridium::PREAMBLE_LENGTH_SHORT + iridium::MAX_FRAME_LENGTH_NORMAL) * d_output_samples_per_symbol;
      }


      /*
       * Search for the start of the burst by looking at the magnitude.
       * Look at most d_search_depth far.
       */

      // The burst might be shorter than d_search_depth.
      volk_32fc_magnitude_32f(d_magnitude_f, d_tmp_b, std::min(d_search_depth, output_samples));

      if(output_samples < d_search_depth) {
        memset(d_magnitude_f + output_samples, 0, sizeof(float) * (d_search_depth - output_samples));
      }

      int N = d_search_depth - d_start_finder_fir.ntaps() + 1;
      d_start_finder_fir.filterN(d_magnitude_filtered_f, d_magnitude_f, N);

      float * max = std::max_element(d_magnitude_filtered_f, d_magnitude_filtered_f + N);
      float threshold = *max * 0.5;
      if(d_debug) {
        std::cout << "Threshold:" << threshold << " Max:" << *max << "(" << (max - d_magnitude_filtered_f) << ")\n";
      }

      int start;
      for(start = 0; start < N; start++) {
        if(d_magnitude_filtered_f[start] >= threshold) {
            break;
        }
      }
      start = std::max(start - d_pre_start_samples, 0);
      if(d_debug) {
        std::cout << "Start:" << start << "\n";
      }


      /*
       * Find the fine CFO estimate using an FFT over the preamble and the first symbols
       * of the unique word.
       * The signal gets squared to remove the BPSK from the uniqe word.
       */
      gr_complex * tmp = d_tmp_b + start;
      if(output_samples - start < d_cfo_est_fft_size) {
        // There are not enough samples available to run the FFT.
        // TODO: Log error.
        return;
      }

      // TODO: Not sure which way to square is faster.
      //volk_32fc_x2_multiply_32fc(d_tmp_a, tmp, tmp, d_cfo_est_fft_size);
      volk_32fc_s32f_power_32fc(d_tmp_a, tmp, 2, d_cfo_est_fft_size);
      volk_32fc_32f_multiply_32fc(d_cfo_est_fft.get_inbuf(), d_tmp_a, d_cfo_est_window_f, d_cfo_est_fft_size);
      d_cfo_est_fft.execute();
      volk_32fc_magnitude_32f(d_magnitude_f, d_cfo_est_fft.get_outbuf(), d_cfo_est_fft_size * d_fft_over_size_facor);
      float * x = std::max_element(d_magnitude_f, d_magnitude_f + d_cfo_est_fft_size * d_fft_over_size_facor);
      int max_index = x - d_magnitude_f;
      if(d_debug) {
        printf("max_index=%d\n", max_index);
      }

      // Interpolate the result of the FFT to get a finer resolution.
      // see http://www.dsprelated.com/dspbooks/sasp/Quadratic_Interpolation_Spectral_Peaks.html
      float alpha = d_magnitude_f[(max_index - 1) % (d_cfo_est_fft_size * d_fft_over_size_facor)];
      float beta = d_magnitude_f[max_index];
      float gamma = d_magnitude_f[(max_index + 1) % (d_cfo_est_fft_size * d_fft_over_size_facor)];
      float correction = 0.5 * (alpha - gamma) / (alpha - 2*beta + gamma);
      float interpolated_index = max_index + correction;

      // Prevent underflows
      if(interpolated_index < 0) {
        interpolated_index += d_cfo_est_fft_size * d_fft_over_size_facor;
      }

      // Remove FFT shift.
      // interpolated_index will now be between -(d_cfo_est_fft_size * d_fft_over_size_facor) / 2
      //                                     and (d_cfo_est_fft_size * d_fft_over_size_facor) / 2
      if(interpolated_index > d_cfo_est_fft_size * d_fft_over_size_facor / 2) {
        interpolated_index -= d_cfo_est_fft_size * d_fft_over_size_facor;
      }

      // Normalize the result.
      // Divide by two to remove the effect of the squaring operation before.
      float center_offset = interpolated_index / (d_cfo_est_fft_size * d_fft_over_size_facor) / 2;

      if(d_debug) {
        printf("interpolated_index=%f center_offset=%f (%f)\n", interpolated_index, center_offset, center_offset * d_output_sample_rate);
      }


      /*
       * Shift the burst again using the result of the FFT.
       */
      phase_inc = 2 * M_PI * -center_offset;
      d_r.set_phase_incr(exp(gr_complex(0, phase_inc)));
      d_r.set_phase(gr_complex(1, 0));
      d_r.rotateN(d_tmp_a, d_tmp_b + start, output_samples);
      center_frequency += center_offset * sample_rate;


      /*
       * Use a correlation to find the start of the sync word.
       * Uses an FFT to perform the correlation.
       */
      memcpy(d_corr_fft->get_inbuf(), d_tmp_a, sizeof(gr_complex) * d_sync_search_len);
      d_corr_fft->execute();
      volk_32fc_x2_multiply_32fc(d_corr_ifft->get_inbuf(), d_corr_fft->get_outbuf(), &d_dl_preamble_reversed_conj_fft[0], d_corr_fft_size);
      d_corr_ifft->execute();

      // Find the peak of the correlation
      volk_32fc_magnitude_32f(d_magnitude_f, d_corr_ifft->get_outbuf(), d_corr_fft_size);
      max = std::max_element(d_magnitude_f, d_magnitude_f + d_corr_fft_size);

      int corr_offset = max - d_magnitude_f;
      gr_complex corr_result = d_corr_ifft->get_outbuf()[corr_offset];
      corr_result /= abs(corr_result);

      if(d_debug) {
        printf("Conv max index = %d\n", corr_offset);
      }

      // Careful: The correlation might have found the start of the sync word
      // before the first sample => preamble_offset might be negative
      int preamble_offset = corr_offset - d_dl_preamble_reversed_conj.size() + 1;
      int uw_offset = preamble_offset + iridium::PREAMBLE_LENGTH_SHORT * d_output_samples_per_symbol;

      // If ther UW center_offset is < 0, we will not be able to demodulate the signal
      if(uw_offset < 0) {
        // TODO: Log an error?
        return;
      }

      // Clamp preamble_offset to >= 0
      preamble_offset = std::max(0, preamble_offset);


      /*
       * Align the burst so the first sample of the burst is the first symbol
       * of the 16 symbol preamble after the RRC filter.
       *
       */
      output_samples -= preamble_offset;
      output_samples = std::min(output_samples, max_frame_length);

      // Make some room at the start and the end, so the RRC can run
      int half_fir_size = (d_rrc_fir.ntaps() - 1) / 2;
      memmove(d_tmp_a + half_fir_size, d_tmp_a + preamble_offset, output_samples * sizeof(gr_complex));
      memset(d_tmp_a, 0, half_fir_size * sizeof(gr_complex));
      memset(d_tmp_a + half_fir_size + output_samples, 0, half_fir_size * sizeof(gr_complex));
      uw_offset -= preamble_offset;
      preamble_offset = 0;


      /*
       * Rotate the phase so the demodulation has a starting point.
       */
      d_r.set_phase_incr(exp(gr_complex(0, 0)));
      d_r.set_phase(std::conj(corr_result));
      d_r.rotateN(d_tmp_b, d_tmp_a, output_samples + half_fir_size * 2);


      /*
       * Apply the RRC filter.
       */
      d_rrc_fir.filterN(d_tmp_a, d_tmp_b, output_samples);


      /*
       * Done :)
       */
      pmt::pmt_t pdu_meta = pmt::make_dict();
      pmt::pmt_t pdu_vector = pmt::init_c32vector(output_samples, d_tmp_a);

      pdu_meta = pmt::dict_add(pdu_meta, pmt::mp("sample_rate"), pmt::mp(sample_rate));
      pdu_meta = pmt::dict_add(pdu_meta, pmt::mp("center_frequency"), pmt::mp(center_frequency));
      pdu_meta = pmt::dict_add(pdu_meta, pmt::mp("direction"), pmt::mp((int)direction));
      pdu_meta = pmt::dict_add(pdu_meta, pmt::mp("uw_start"), pmt::mp(uw_offset));
      pdu_meta = pmt::dict_add(pdu_meta, pmt::mp("offset"), pmt::mp(offset));
      pdu_meta = pmt::dict_add(pdu_meta, pmt::mp("id"), pmt::mp(id));

      if(d_debug) {
        printf("center_frequency=%f, uw_start=%u\n", center_frequency, uw_offset);
        write_data_c(d_tmp_a, output_samples, id);
      }

      pmt::pmt_t out_msg = pmt::cons(pdu_meta,
          pdu_vector);
      message_port_pub(pmt::mp("cpdus"), out_msg);
    }

    int
    burst_downmix_impl::work(int noutput_items,
        gr_vector_const_void_star &input_items,
        gr_vector_void_star &output_items)
    {
    }

  } /* namespace iridium_toolkit */
} /* namespace gr */

