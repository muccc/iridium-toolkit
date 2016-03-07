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
    tagged_burst_to_pdu::make(float relative_center_frequency, float relative_span)
    {
      return gnuradio::get_initial_sptr
        (new tagged_burst_to_pdu_impl(relative_center_frequency, relative_span));
    }

    /*
     * The private constructor
     */
    tagged_burst_to_pdu_impl::tagged_burst_to_pdu_impl(float relative_center_frequency, float relative_span)
      : gr::sync_block("tagged_burst_to_pdu",
              gr::io_signature::make(1, 1, sizeof(gr_complex)),
              gr::io_signature::make(0, 0, 0))
    {}

    /*
     * Our virtual destructor.
     */
    tagged_burst_to_pdu_impl::~tagged_burst_to_pdu_impl()
    {
    }

    int
    tagged_burst_to_pdu_impl::work(int noutput_items,
        gr_vector_const_void_star &input_items,
        gr_vector_void_star &output_items)
    {
      const gr_complex *in = (const gr_complex *) input_items[0];


      // Tell runtime system how many output items we produced.
      return noutput_items;
    }

  } /* namespace iridium_toolkit */
} /* namespace gr */

