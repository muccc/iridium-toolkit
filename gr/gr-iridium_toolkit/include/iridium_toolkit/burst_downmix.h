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


#ifndef INCLUDED_IRIDIUM_TOOLKIT_BURST_DOWNMIX_H
#define INCLUDED_IRIDIUM_TOOLKIT_BURST_DOWNMIX_H

#include <iridium_toolkit/api.h>
#include <gnuradio/sync_block.h>

namespace gr {
  namespace iridium_toolkit {

    /*!
     * \brief <+description of block+>
     * \ingroup iridium_toolkit
     *
     */
    class IRIDIUM_TOOLKIT_API burst_downmix : virtual public gr::sync_block
    {
     public:
      typedef boost::shared_ptr<burst_downmix> sptr;

      /*!
       * \brief Return a shared_ptr to a new instance of iridium_toolkit::burst_downmix.
       *
       * To avoid accidental use of raw pointers, iridium_toolkit::burst_downmix's
       * constructor is in a private implementation
       * class. iridium_toolkit::burst_downmix::make is the public interface for
       * creating new instances.
       */
      static sptr make(int sample_rate, int search_depth, int search_window);
    };

  } // namespace iridium_toolkit
} // namespace gr

#endif /* INCLUDED_IRIDIUM_TOOLKIT_BURST_DOWNMIX_H */

