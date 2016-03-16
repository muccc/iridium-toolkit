/* -*- c++ -*- */

#define IRIDIUM_TOOLKIT_API

%include "gnuradio.i"			// the common stuff

//load generated python docstrings
%include "iridium_toolkit_swig_doc.i"

%{
#include "iridium_toolkit/fft_burst_tagger.h"
#include "iridium_toolkit/iuchar_to_complex.h"
#include "iridium_toolkit/tagged_burst_to_pdu.h"
#include "iridium_toolkit/burst_downmix.h"
#include "iridium_toolkit/pdu_null_sink.h"
%}

%include "iridium_toolkit/fft_burst_tagger.h"
GR_SWIG_BLOCK_MAGIC2(iridium_toolkit, fft_burst_tagger);
%include "iridium_toolkit/iuchar_to_complex.h"
GR_SWIG_BLOCK_MAGIC2(iridium_toolkit, iuchar_to_complex);
%include "iridium_toolkit/tagged_burst_to_pdu.h"
GR_SWIG_BLOCK_MAGIC2(iridium_toolkit, tagged_burst_to_pdu);
%include "iridium_toolkit/burst_downmix.h"
GR_SWIG_BLOCK_MAGIC2(iridium_toolkit, burst_downmix);
%include "iridium_toolkit/pdu_null_sink.h"
GR_SWIG_BLOCK_MAGIC2(iridium_toolkit, pdu_null_sink);
