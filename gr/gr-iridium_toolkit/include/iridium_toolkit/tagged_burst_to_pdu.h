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


#ifndef INCLUDED_IRIDIUM_TOOLKIT_TAGGED_BURST_TO_PDU_H
#define INCLUDED_IRIDIUM_TOOLKIT_TAGGED_BURST_TO_PDU_H

#include <iridium_toolkit/api.h>
#include <gnuradio/sync_block.h>

namespace gr {
  namespace iridium_toolkit {

    /*!
     * \brief <+description of block+>
     * \ingroup iridium_toolkit
     *
     */
    class IRIDIUM_TOOLKIT_API tagged_burst_to_pdu : virtual public gr::sync_block
    {
     public:
      typedef boost::shared_ptr<tagged_burst_to_pdu> sptr;

      /*!
       * \brief Return a shared_ptr to a new instance of iridium_toolkit::tagged_burst_to_pdu.
       *
       * To avoid accidental use of raw pointers, iridium_toolkit::tagged_burst_to_pdu's
       * constructor is in a private implementation
       * class. iridium_toolkit::tagged_burst_to_pdu::make is the public interface for
       * creating new instances.
       */
      static sptr make(int max_burst_size, float relative_center_frequency, float relative_span,
                        int max_outstanding, bool drop_overflow);
    };

  } // namespace iridium_toolkit
} // namespace gr

#endif /* INCLUDED_IRIDIUM_TOOLKIT_TAGGED_BURST_TO_PDU_H */

