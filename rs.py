#!/usr/bin/python
# vim: set ts=4 sw=4 tw=0 et pm=:

import reedsolo

generator=2
fcr=0
nsym=16
c_exp=8 # bits per symbol
prim=0x11d
reedsolo.init_tables(prim=prim,generator=generator,c_exp=c_exp)

# erasure length
elen=8

def rs_check(data):
	mlen=len(data)+elen-nsym
	msg=reedsolo.rs_encode_msg(data[:mlen],nsym,fcr=fcr)
	return bytearray(data[mlen:])==msg[mlen:len(data)]

def rs_fix(data):
#	data=data+bytearray([0]*elen)
	data=data+([0]*elen)
	r=range(len(data)-elen,len(data))
	try:
		(cmsg,crs)=reedsolo.rs_correct_msg(data,nsym,fcr,generator,r)
	except:
		return (False,None,None)
	return (True,cmsg,crs)
