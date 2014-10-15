#!/usr/bin/env python
# vim: set ts=4 sw=4 tw=0 et pm=:
import sys
import re
from fec import stringify,listify
from bch import divide,add,poly,multiply
import getopt

options, remainder = getopt.getopt(sys.argv[1:], 'v', [
                                                         'verbose',
                                                         ])

# See: http://syagha.blogspot.de/2012/06/bch-code.html
# and: http://www.aqdi.com/bch.pdf

verbose = False

for opt, arg in options:
    if opt in ('-v', '--verbose'):
        verbose = True

genpolystr=remainder[0]
genpoly=int(genpolystr,2)
size=len(genpolystr)-1
max=1<<size
rest=genpoly-max

t=int(remainder[1])

print "BCH: m=",size,"t=",t
print "will have ",size*t,"or less check bits"

# Primitive polys from http://mathworld.wolfram.com/PrimitivePolynomial.html
#1	1+x
#2	1+x+x^2
#3	1+x+x^3, 1+x^2+x^3
#4	1+x+x^4, 1+x^3+x^4
#5	1+x^2+x^5, 1+x+x^2+x^3+x^5, 1+x^3+x^5, 1+x+x^3+x^4+x^5, 1+x^2+x^3+x^4+x^5, 1+x+x^2+x^4+x^5

#1: 11
#2: 111
#3: 1011 1101
#4: 10011 11001
#5: 100101 101001 101111 111101 111011 110111

print "Genrator poly is=",poly(genpoly)

#
# Generate Field
#
if(verbose):
	print "Using equivalence of x^%d = %s"%(size,poly(rest)),"to generate field"
ctr=1
p=1
field=[0]*(max+1)

while(ctr<=max):
	if (verbose):
		print "%3d (x^%d) = %s"%(ctr,ctr-1,poly(p))
	field[ctr]=p
	ctr+=1
	p<<=1
	if (p>=max):
	  p=p^genpoly # same as (p-max)^rest

if verbose:
	print


#
# Generate t minimal polys
#
def polysum(a,ary):
	r=0
	while a>0:
		if(a%2):
			r^=ary[0]
		a>>=1
		ary=ary[1:]
	return r

def linsolve(ary):
	# solve linear problem over GF(2^n)
	# bruetforce this :)
	for c in xrange(1,pow(2,len(ary))):
		ps=polysum(c,ary)
	#	print c,"=>",ps
		if(ps==0):
			return c
	

mplist=[]
for x in xrange(0,t): # generate first t minimal polys
	m=x*2+1
	if verbose:
		print "finding minmal poly ",m
	lgs=[]
	for grade in xrange(size+1): # gather all potentcies of x^m
		idx=1+m*grade
		idx%=max
		if (verbose):
			print "%2d"%(idx),("= {0:%db}"%size).format(field[idx])
		lgs.append(field[idx])

	mp=linsolve(lgs)
	print "mp(%d)="%m,poly(mp)
	mplist.append(mp)

if(verbose):
	print "bch poly is ", "*".join(["("+poly(x)+")" for x in mplist])," "

#multiply all minimal polys together
result=1
for mp in mplist:
	result=multiply(result,mp)

resultbin="{0:b}".format(result)
checkbits=len(resultbin)-1
print "BCH(%d,%d)="%(max-1,max-1-checkbits)
print poly(result)," (%d)"%result

