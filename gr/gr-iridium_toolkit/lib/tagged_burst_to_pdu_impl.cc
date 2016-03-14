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
#include "tagged_burst_to_pdu_impl.h"

namespace gr {
  namespace iridium_toolkit {

    tagged_burst_to_pdu::sptr
    tagged_burst_to_pdu::make(int max_burst_size, float relative_center_frequency, float relative_span)
    {
      return gnuradio::get_initial_sptr
        (new tagged_burst_to_pdu_impl(max_burst_size, relative_center_frequency, relative_span));
    }

    /*
     * The private constructor
     */
    tagged_burst_to_pdu_impl::tagged_burst_to_pdu_impl(int max_burst_size, float relative_center_frequency, float relative_span)
      : gr::sync_block("tagged_burst_to_pdu",
              gr::io_signature::make(1, 1, sizeof(gr_complex)),
              gr::io_signature::make(0, 0, 0)),
              d_max_burst_size(max_burst_size),
              d_relative_center_frequency(relative_center_frequency),
              d_relative_span(relative_span)
    {
      d_lower_border = relative_center_frequency - relative_span / 2;
      d_upper_border = relative_center_frequency + relative_span / 2;
      message_port_register_out(pmt::mp("cpdus"));
    }

    /*
     * Our virtual destructor.
     */
    tagged_burst_to_pdu_impl::~tagged_burst_to_pdu_impl()
    {
    }

    void
    tagged_burst_to_pdu_impl::append_to_burst(burst_data &burst, const gr_complex * data, size_t n)
    {
        // If the burst really gets longer than this, we can just throw away the data
      if(burst.len + n <= d_max_burst_size) {
        memcpy(burst.data + burst.len, data, n * sizeof(gr_complex));
        burst.len += n;
      }
    }

    void
    tagged_burst_to_pdu_impl::publish_burst(burst_data &burst)
    {
      pmt::pmt_t d_pdu_meta = pmt::make_dict();
      pmt::pmt_t d_pdu_vector = pmt::init_c32vector(burst.len, burst.data);

      d_pdu_meta = pmt::dict_add(d_pdu_meta, pmt::mp("id"), pmt::mp(burst.id));
      d_pdu_meta = pmt::dict_add(d_pdu_meta, pmt::mp("offset"), pmt::mp(burst.offset));
      d_pdu_meta = pmt::dict_add(d_pdu_meta, pmt::mp("magnitude"), pmt::mp(burst.magnitude));
      d_pdu_meta = pmt::dict_add(d_pdu_meta, pmt::mp("relative_frequency"), pmt::mp(burst.relative_frequency));
      d_pdu_meta = pmt::dict_add(d_pdu_meta, pmt::mp("center_frequency"), pmt::mp(burst.center_frequency));
      d_pdu_meta = pmt::dict_add(d_pdu_meta, pmt::mp("sample_rate"), pmt::mp(burst.sample_rate));

      pmt::pmt_t msg = pmt::cons(d_pdu_meta,
          d_pdu_vector);
      message_port_pub(pmt::mp("cpdus"), msg);
    }

    void
    tagged_burst_to_pdu_impl::create_new_bursts(int noutput_items,
            const gr_complex * in)
    {
      std::vector<tag_t> new_bursts;
      get_tags_in_window(new_bursts, 0, 0, noutput_items, pmt::mp("new_burst"));

      for(tag_t tag : new_bursts) {
        float relative_frequency = pmt::to_float(pmt::dict_ref(tag.value, pmt::mp("relative_frequency"), pmt::PMT_NIL));

        if(d_lower_border < relative_frequency && relative_frequency <= d_upper_border) {
          uint64_t id = pmt::to_uint64(pmt::dict_ref(tag.value, pmt::mp("id"), pmt::PMT_NIL));
          float magnitude = pmt::to_float(pmt::dict_ref(tag.value, pmt::mp("magnitude"), pmt::PMT_NIL));
          float center_frequency = pmt::to_float(pmt::dict_ref(tag.value, pmt::mp("center_frequency"), pmt::PMT_NIL));
          float sample_rate = pmt::to_float(pmt::dict_ref(tag.value, pmt::mp("sample_rate"), pmt::PMT_NIL));
          float relative_frequency = pmt::to_float(pmt::dict_ref(tag.value, pmt::mp("relative_frequency"), pmt::PMT_NIL));


          // Adjust the values based on our position behind a potential filter bank
          center_frequency += d_relative_center_frequency * sample_rate;
          sample_rate = sample_rate * d_relative_span;
          relative_frequency = relative_frequency - d_relative_center_frequency;

          burst_data burst = {id, tag.offset, magnitude, relative_frequency,
            center_frequency, sample_rate, 0};
          burst.data = (gr_complex *) malloc(sizeof(gr_complex) * d_max_burst_size);

          if(burst.data != NULL) {
            d_bursts[id] = burst;
            int relative_offset = burst.offset - nitems_read(0);
            int to_copy = noutput_items - relative_offset;
            append_to_burst(d_bursts[id], &in[relative_offset], to_copy);
            printf("New burst: %lu %lu %f %f\n", tag.offset, id, relative_frequency, magnitude);
          } else {
            printf("Error, malloc failed\n");
          }
        }
      }
    }

    void
    tagged_burst_to_pdu_impl::publish_and_remove_old_bursts(int noutput_items, const gr_complex * in)
    {
      std::vector<tag_t> gone_bursts;
      get_tags_in_window(gone_bursts, 0, 0, noutput_items, pmt::mp("gone_burst"));

      for(tag_t tag : gone_bursts) {
        uint64_t id = pmt::to_uint64(pmt::dict_ref(tag.value, pmt::mp("id"), pmt::PMT_NIL));

        if(d_bursts.count(id)) {
          burst_data &burst = d_bursts[id];
          int relative_offset = tag.offset - nitems_read(0);
          append_to_burst(burst, in, relative_offset);  
          printf("gone burst: %lu %ld\n", id, burst.len);
          publish_burst(burst);
          free(d_bursts[id].data);
          d_bursts.erase(id);
        }
      }
    }

    void
    tagged_burst_to_pdu_impl::update_current_bursts(int noutput_items, const gr_complex * in)
    {
      for(auto& kv : d_bursts) {
        append_to_burst(kv.second, in, noutput_items);  
      }
    }

    int
    tagged_burst_to_pdu_impl::work(int noutput_items,
        gr_vector_const_void_star &input_items,
        gr_vector_void_star &output_items)
    {
      const gr_complex *in = (const gr_complex *) input_items[0];

      publish_and_remove_old_bursts(noutput_items, in);
      update_current_bursts(noutput_items, in);
      create_new_bursts(noutput_items, in);

      // Not sure if this makes sense in a sink block
      return noutput_items;
    }

  } /* namespace iridium_toolkit */
} /* namespace gr */

