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

namespace gr {
  namespace iridium_toolkit {

    burst_downmix::sptr
    burst_downmix::make(int sample_rate, int search_depth, int search_window)
    {
      return gnuradio::get_initial_sptr
        (new burst_downmix_impl(sample_rate, search_depth, search_window));
    }

    /*
     * The private constructor
     */
    burst_downmix_impl::burst_downmix_impl(int sample_rate, int search_depth, int search_window)
      : gr::sync_block("burst_downmix",
              gr::io_signature::make(0, 0, 0),
              gr::io_signature::make(0, 0, 0))
    {}

    /*
     * Our virtual destructor.
     */
    burst_downmix_impl::~burst_downmix_impl()
    {
    }

    int
    burst_downmix_impl::work(int noutput_items,
        gr_vector_const_void_star &input_items,
        gr_vector_void_star &output_items)
    {
    }

  } /* namespace iridium_toolkit */
} /* namespace gr */

