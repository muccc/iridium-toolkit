/* -*- c++ -*- */
/* 
 * Copyright 2016 Free Software Foundation, Inc
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


#include <gnuradio/attributes.h>
#include <cppunit/TestAssert.h>
#include "qa_fft_burst_tagger.h"
#include <iridium_toolkit/fft_burst_tagger.h>

namespace gr {
  namespace iridium_toolkit {

    void
    qa_fft_burst_tagger::t1()
    {
      fft_burst_tagger::make(1024, 1000000, 1000, 1000, 100, 0, 7.0, 512, false);
    }

  } /* namespace iridium_toolkit */
} /* namespace gr */

