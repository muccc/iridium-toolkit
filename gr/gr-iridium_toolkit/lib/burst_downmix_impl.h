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

#ifndef INCLUDED_IRIDIUM_TOOLKIT_BURST_DOWNMIX_IMPL_H
#define INCLUDED_IRIDIUM_TOOLKIT_BURST_DOWNMIX_IMPL_H

#include <gnuradio/blocks/rotator.h>
#include <gnuradio/filter/fir_filter.h>

#include <iridium_toolkit/burst_downmix.h>

namespace gr {
  namespace iridium_toolkit {

    class burst_downmix_impl : public burst_downmix
    {
     private:
      size_t d_max_burst_size;

      int d_input_decimation;

      gr_complex * d_input;
      gr_complex * d_tmp_a;
      gr_complex * d_tmp_b;

      std::vector<float> d_input_taps;

      blocks::rotator d_r;
      filter::kernel::fir_filter_ccf d_input_fir;

      void handler(pmt::pmt_t msg);
      void update_buffer_sizes(size_t burst_size);

     public:
      burst_downmix_impl(int sample_rate, int search_depth, const std::vector<float> &input_taps);
      ~burst_downmix_impl();

      int work(int noutput_items,
         gr_vector_const_void_star &input_items,
         gr_vector_void_star &output_items);
    };

  } // namespace iridium_toolkit
} // namespace gr

#endif /* INCLUDED_IRIDIUM_TOOLKIT_BURST_DOWNMIX_IMPL_H */

