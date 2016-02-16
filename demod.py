#!/usr/bin/env python
# coding: utf-8
# vim: set ts=4 sw=4 tw=0 et fenc=utf8 pm=:
import struct
import sys
import math
import numpy
import os.path
import cmath
import filters
import re
import complex_sync_search
import iq
import getopt
import iridium


UW_DOWNLINK = "022220002002"
UW_UPLINK = "220002002022"

def normalize(v):
    m = max([abs(x) for x in v])
    return [x/m for x in v]

def mynormalize(v):
    reals = normalize([x.real for x in v])
    imags = normalize([x.imag for x in v])
    zip=[]
    for i in xrange(len(reals)):
        zip.append(complex(reals[i],imags[i]))
    return zip

class Demod(object):
    def __init__(self, sample_rate, verbose=False, debug=False):
        self._sample_rate=sample_rate
        self._verbose=verbose
        self._debug = debug
        
        if self._verbose:
            print "sample rate:",self._sample_rate

        if self._sample_rate % iridium.SYMBOLS_PER_SECOND != 0:
            raise Exception("Non-int samples per symbol")

        self._samples_per_symbol= self._sample_rate / iridium.SYMBOLS_PER_SECOND

        if self._verbose:
            print "samples per symbol:",self._samples_per_symbol

        self._skip = 5*self._samples_per_symbol # beginning might be flaky

        self._sync_search = complex_sync_search.ComplexSyncSearch(self._sample_rate, verbose=self._verbose)

    def qpsk(self, phase):
        self._nsymbols+=1
        phase = phase % 360

        # In theory we should only see 0, 90, 180 and 270 here.
        sym=int(phase)/90
        #print "symbol", sym

        off=(45-(phase % 90))
        if (abs(off)>22):
            if self._verbose:
                print "Symbol offset >22"
            self._errors+=1

        return sym,off

    def _find_start(self, signal, direction): 
        if direction is not None:
            start, _ = self._sync_search.estimate_sync_word_start(signal, direction)
        else:
            start_dl, confidence_dl = self._sync_search.estimate_sync_word_start(signal, iridium.DOWNLINK)
            start_ul, confidence_ul = self._sync_search.estimate_sync_word_start(signal, iridium.UPLINK)
            
            if confidence_dl > confidence_ul:
                start = start_dl
            else:
                start = start_ul

        if self._verbose:
            print "correlated start of sync word", start
        return start

    def demod(self, signal, direction=None, return_final_offset=False):
        self._errors=0
        self._nsymbols=0

        #signal_mag = numpy.abs(signal)

        level=abs(numpy.mean(signal[self._skip:self._skip+16*self._samples_per_symbol]))
        lmax=abs(numpy.max(signal[self._skip:self._skip+16*self._samples_per_symbol]))

        if self._verbose:
            print "level:",level
            print 'lmax:', lmax

        i=self._find_start(signal, direction)
        symbols=[]
        if self._debug:
            self.samples=[]

        #Graphical debugging stuff (the *.peaks file)
        if self._debug:
            self.peaks=[complex(-lmax,0)]*len(signal)
            self.turned_signal=[0+0j] * len(signal)
            mapping= [2,1,-2,-1] # mapping: symbols->*.peaks output

        if self._verbose:
            print "len:",len(signal)

        phase=0 # Current phase offset
        alpha=2 # How many degrees is still fine.

        delay=0
        sdiff=2 # Timing check difference

        if(self._samples_per_symbol<20):
            sdiff=1

        while True:
            if self._debug:
                self.peaks[i]=complex(-lmax,lmax/10.)

            # Adjust our sample rate to reality
            try:
                cur=signal[i].real
                pre=signal[i-self._samples_per_symbol].real
                post=signal[i+self._samples_per_symbol].real
                curpre=signal[i-sdiff].real
                curpost=signal[i+sdiff].real

                if pre<0 and post<0 and cur>0:
                    if curpre>cur and cur>curpost:
                        if self._verbose:
                            print "Sampled late"
                        i-=sdiff
                        delay-=sdiff
                    if curpre<cur and cur<curpost:
                        if self._verbose:
                            print "Sampled early"
                        i+=sdiff
                        delay-=sdiff
                elif pre>0 and post>0 and cur<0:
                    if curpre>cur and cur>curpost:
                        if self._verbose:
                            print "Sampled early"
                        i+=sdiff
                        delay+=sdiff
                    if curpre<cur and cur<curpost:
                        if self._verbose:
                            print "Sampled late"
                        i-=sdiff
                        delay-=sdiff
                else:
                    cur=signal[i].imag
                    pre=signal[i-self._samples_per_symbol].imag
                    post=signal[i+self._samples_per_symbol].imag
                    curpre=signal[i-sdiff].imag
                    curpost=signal[i+sdiff].imag

                    if pre<0 and post<0 and cur>0:
                        if curpre>cur and cur>curpost:
                            if self._verbose:
                                print "Sampled late"
                            i-=sdiff
                            delay-=sdiff
                        if curpre<cur and cur<curpost:
                            if self._verbose:
                                print "Sampled early"
                            i+=sdiff
                            delay+=sdiff
                    elif pre>0 and post>0 and cur<0:
                        if curpre>cur and cur>curpost:
                            if self._verbose:
                                print "Sampled early"
                            i+=sdiff
                            delay+=sdiff
                        if curpre<cur and cur<curpost:
                            if self._verbose:
                                print "Sampled late"
                            i-=sdiff
                            delay-=sdiff
            except IndexError:
                if self._verbose:
                    print "Last sample"

            lvl= abs(signal[i])/level
            ang= cmath.phase(signal[i])/math.pi*180
            symbol,offset = self.qpsk(ang+phase)
            if(offset>alpha):
                if self._debug:
                    try:
                        self.peaks[i+self._samples_per_symbol/10]=complex(-lmax*0.8,0);
                    except IndexError:
                        if self._verbose:
                            print "Last sample"
                if self._verbose:
                    print "offset forward"
                phase+=sdiff
            if(offset<-alpha):
                if self._debug:
                    self.peaks[i-self._samples_per_symbol/10]=complex(-lmax*0.8,0);
                if self._verbose:
                    print "offset backward"
                phase-=sdiff

            symbols=symbols+[symbol]
            if self._debug:
                self.samples=self.samples+[signal[i]]

            if self._verbose:
                print "Symbol @%06d (%3d°,%3.0f%%)=%d delay=%d phase=%d"%(i,ang%360,lvl*100,symbol,delay,phase)
            if self._debug:
                self.peaks[i]=complex(+lmax,mapping[symbol]*lmax/5.)
                self.turned_signal[i:i+self._samples_per_symbol] = signal[i:i+self._samples_per_symbol] * cmath.rect(1,numpy.radians(phase))
            i+=self._samples_per_symbol
            if i>=len(signal) : break
            if abs(signal[i]) < lmax/8:
                break

        if self._verbose:
            print "Done."

        access=""
        for s in symbols[:iridium.UW_LENGTH]:
            access+=str(s)

        # Do gray code on symbols
        data=""
        oldsym=0
        dataarray=[]
        for s in symbols:
            bits=(s-oldsym)%4
            if bits==0:
                bits=0
            elif bits==1:
                bits=2
            elif bits==2:
                bits=3
            else:
                bits=1
            oldsym=s
            data+=str((bits&2)/2)+str(bits&1)
            dataarray+=[(bits&2)/2,bits&1]

        if access == UW_DOWNLINK or access == UW_UPLINK:
            access_ok = True
        else:
            access_ok = False

        lead_out = "100101111010110110110011001111"
        lead_out_ok = lead_out in data

        confidence = (1-float(self._errors)/self._nsymbols)*100

        self._real_freq_offset=phase/360.*iridium.SYMBOLS_PER_SECOND/self._nsymbols

        if self._verbose:
            print "access:",access_ok,"(%s)"%access
            print "leadout:",lead_out_ok
            print "len:",self._nsymbols
            print "confidence:",confidence
            print "data:",data
            print "final delay",delay
            print "final phase",phase
            print "frequency offset:", self._real_freq_offset

        if access_ok:
            data="<"+data[:iridium.UW_LENGTH*2]+"> "+data[iridium.UW_LENGTH*2:]

        if lead_out_ok:
            lead_out_index = data.find(lead_out)
            data=data[:lead_out_index]+"["+data[lead_out_index:lead_out_index+len(lead_out)]+"]"  +data[lead_out_index+len(lead_out):]

        data=re.sub(r'([01]{32})',r'\1 ',data)

        if return_final_offset:
            return (dataarray, data, access_ok, lead_out_ok, confidence, level, self._nsymbols,self._real_freq_offset)
        else:
            return (dataarray, data, access_ok, lead_out_ok, confidence, level, self._nsymbols)
        
if __name__ == "__main__":
    options, remainder = getopt.getopt(sys.argv[1:], 'r:dv', [
                                                            'rate=',
                                                            'debug',
                                                            'verbose',
                                                            'uplink',
                                                            'downlink'
                                                            ])

    sample_rate = None
    debug = False
    verbose = False
    direction = None

    for opt, arg in options:
        if opt in ('-r', '--rate'):
            sample_rate=int(arg)
        elif opt in ('-v', '--verbose'):
            verbose = True
        elif opt in ('-d', '--debug'):
            debug = True
        elif opt == '--downlink':
            direction = iridium.DOWNLINK
        elif opt == '--uplink':
            direction = iridium.UPLINK

    if sample_rate == None:
        print >> sys.stderr, "Sample rate missing!"
        exit(1)

    file_name = remainder[0]
    basename= filename= re.sub('\.[^.]*$','',file_name)

    if verbose:
        print "File:",basename

    signal = iq.read(file_name)

    # Nice output format
    p=re.compile('(.*?)-(\d+)(?:-o[-+]\d+)?-f(\d+)')
    m=p.match(basename)
    if(m):
        rawfile=m.group(1)
        timestamp=int(m.group(2))
        freq=int(m.group(3))
    else:
        rawfile=basename
        timestamp=0
        freq=0

    if verbose:
        print "raw filename:",rawfile
        print "base freq:",freq

    d = Demod(sample_rate=sample_rate, verbose=verbose, debug=debug)

    dataarray, data, access_ok, lead_out_ok, confidence, level, nsymbols = d.demod(signal, direction)

    print "RAW: %s %07d %010d A:%s L:%s %3d%% %.3f %3d %s"%(rawfile,timestamp,freq,("no","OK")[access_ok],("no","OK")[lead_out_ok],confidence,level,(nsymbols-iridium.UW_LENGTH),data)

    if 0: # Create r / phi file
        with open("%s.rphi" % (os.path.basename(basename)), 'wb') as out:
            signal = [item for sample
                in signal for item
                in [abs(sample), cmath.phase(sample)]]
            s = "<" + len(signal) * 'f'
            out.write(struct.Struct(s).pack(*signal))

    if debug: # The graphical debugging file
        iq.write("%s.peaks" % (os.path.basename(basename)), d.peaks)
        iq.write("%s.turned" % (os.path.basename(basename)), d.turned_signal)

    if 0: # The actual samples we used
        iq.write("%s.samples" % (os.path.basename(basename)), mynormalize(d.samples))

    if 0: # The data bitstream
        with open("%s.data" % (os.path.basename(basename)), 'wb') as out:
            for c in dataarray:
                out.write(chr(c))

