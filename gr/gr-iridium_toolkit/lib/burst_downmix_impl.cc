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

#include <gnuradio/io_signature.h>
#include "burst_downmix_impl.h"

#include <gnuradio/filter/firdes.h>
#include <volk/volk.h>

namespace gr {
  namespace iridium_toolkit {

    burst_downmix::sptr
    burst_downmix::make(int sample_rate, int search_depth, const std::vector<float> &input_taps)
    {
      return gnuradio::get_initial_sptr
        (new burst_downmix_impl(sample_rate, search_depth, input_taps));
    }

    /*
     * The private constructor
     */
    burst_downmix_impl::burst_downmix_impl(int sample_rate, int search_depth, const std::vector<float> &input_taps)
      : gr::sync_block("burst_downmix",
              gr::io_signature::make(0, 0, 0),
              gr::io_signature::make(0, 0, 0)),
              d_max_burst_size(0), d_input(NULL),
              d_tmp_a(NULL), d_tmp_b(NULL),
              d_input_decimation(sample_rate / 250000),
              d_input_fir(0, input_taps)
    {
      message_port_register_in(pmt::mp("cpdus"));
      message_port_register_out(pmt::mp("cpdus"));
      set_msg_handler(pmt::mp("cpdus"), boost::bind(&burst_downmix_impl::handler, this, _1));
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
    }

    void burst_downmix_impl::update_buffer_sizes(size_t burst_size)
    {
      if(burst_size > d_max_burst_size) {
        d_max_burst_size = burst_size;
        if(d_input) {
          volk_free(d_input);
        }
        d_input = (gr_complex *)volk_malloc(burst_size * sizeof(gr_complex), volk_get_alignment());

        if(d_tmp_a) {
          volk_free(d_tmp_a);
        }
        d_tmp_a = (gr_complex *)volk_malloc(burst_size * sizeof(gr_complex), volk_get_alignment());

        if(d_tmp_b) {
          volk_free(d_tmp_b);
        }
        d_tmp_b = (gr_complex *)volk_malloc(burst_size * sizeof(gr_complex), volk_get_alignment());
      }
    }

    void burst_downmix_impl::handler(pmt::pmt_t msg)
	{
      pmt::pmt_t samples = pmt::cdr(msg);
      size_t burst_size = pmt::length(samples);
      const gr_complex * burst = (const gr_complex*)pmt::c32vector_elements(samples, burst_size);

      update_buffer_sizes(burst_size);

      pmt::pmt_t meta = pmt::car(msg);
      float relative_frequency = pmt::to_float(pmt::dict_ref(meta, pmt::mp("relative_frequency"), pmt::PMT_NIL));
      float absolute_frequency = pmt::to_float(pmt::dict_ref(meta, pmt::mp("absolute_frequency"), pmt::PMT_NIL));
      printf("relative_frequency=%f\n", relative_frequency);

      float phase_inc = 2 * M_PI * -relative_frequency;
      d_r.set_phase_incr(exp(gr_complex(0, phase_inc)));
      d_r.rotateN(d_tmp_a, burst, burst_size);

      int output_samples = (burst_size - d_input_fir.ntaps() + 1) / d_input_decimation;
      d_input_fir.filterNdec(d_tmp_b, d_tmp_a, output_samples, d_input_decimation);

      pmt::pmt_t pdu_meta = pmt::make_dict();
      pmt::pmt_t pdu_vector = pmt::init_c32vector(output_samples, d_tmp_b);

      pdu_meta = pmt::dict_add(pdu_meta, pmt::mp("sample_rate"), pmt::mp(250000));

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

