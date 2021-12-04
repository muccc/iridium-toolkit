#!/usr/bin/env python3
# vim: set ts=4 sw=4 tw=0 et pm=:

import reedsolo6

# VO6/LCW3: Message: 42*6b=31.5B, checksum: 10*6b=7.5B - RS_6(52,10) [total: 312b]

generator=2
fcr=54
nsym=10 # number of ecc symbols (n-k)
elen=0  # erasure length (how many bytes erased at end)
c_exp=6 # bits per symbol
prim=0x43
reedsolo6.init_tables(prim=prim,generator=generator,c_exp=c_exp)


def rs_check(data):
	mlen=len(data)-nsym
	msg=reedsolo6.rs_encode_msg(data[:mlen],nsym+elen,fcr=fcr)
	return bytearray(data[mlen:])==msg[mlen:len(data)]

def rs_fix(data):
#	data=data+bytearray([0]*elen)
	data=data+([0]*elen)
	r=list(range(len(data)-elen,len(data)))
	try:
		(cmsg,crs)=reedsolo6.rs_correct_msg(data,nsym+elen,fcr,generator,r)
	except reedsolo6.ReedSolomonError:
		return (False,None,None)
	except ZeroDivisionError:
		return (False,None,None)
	return (True,cmsg,crs[:nsym])
