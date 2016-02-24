/* -*- c++ -*- */

#define IRIDIUM_TOOLKIT_API

%include "gnuradio.i"			// the common stuff

//load generated python docstrings
%include "iridium_toolkit_swig_doc.i"

%{
#include "iridium_toolkit/fft_burst_tagger.h"
%}

%include "iridium_toolkit/fft_burst_tagger.h"
GR_SWIG_BLOCK_MAGIC2(iridium_toolkit, fft_burst_tagger);
