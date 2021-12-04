#!/usr/bin/env python3
# vim: set ts=4 sw=4 tw=0 et pm=:

import reedsolo

# IIQ/LCW3:  Message: 31B, checksum: 8B, erasure: 8B - RS(47,31) [total: 312b]

generator=2
fcr=0   # first consecutive root
nsym=8  # number of ecc symbols (n-k)
elen=8  # erasure length (how many bytes erased at end)
c_exp=8 # bits per symbol
prim=0x11d
reedsolo.init_tables(prim=prim,generator=generator,c_exp=c_exp)


def rs_check(data):
	mlen=len(data)-nsym
	msg=reedsolo.rs_encode_msg(data[:mlen],nsym+elen,fcr=fcr)
	return bytearray(data[mlen:])==msg[mlen:len(data)]

def rs_fix(data):
#	data=data+bytearray([0]*elen)
	data=data+([0]*elen)
	r=list(range(len(data)-elen,len(data)))
	try:
		(cmsg,crs)=reedsolo.rs_correct_msg(data,nsym+elen,fcr,generator,erase_pos=r)
	except reedsolo.ReedSolomonError:
		return (False,None,None)
	except ZeroDivisionError:
		return (False,None,None)
	return (True,cmsg,crs[:nsym])
