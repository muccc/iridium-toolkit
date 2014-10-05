# vim: set ts=4 sw=4 tw=0 et pm=:

import sys
import re

def listify(v):
    return [int(x) for x in re.findall(".",v)]

def stringify(v):
    return "".join([str(x) for x in v])


debug=0

#define POLYA   0x6d
#define POLYB   0x4f

p1= listify("{0:b}".format(0x6d))
p2= listify("{0:b}".format(0x4f))

def set_poly(pa,pb):
    global p1,p2
    p1= listify("{0:b}".format(pa))
    p2= listify("{0:b}".format(pb))
    if(len(p1)!=len(p2)):
        print "set_poly: Poly length not equal"
        exit(-1)


initbb= listify('0000000') # "bit buffer" :-)
def set_initbb(list):
    global initbb
    initbb=list
    if len(initbb)!=len(p1):
        print "intibb: Length needs to be ",len(p1)
        exit(-1)


def fec(bits):
    out=[]
    bb=initbb
    for bit in bits:
        if debug:
            print "bit=",bit,"bb: ",bb
        bb=bb[1:]+[bit]
        o1=0
        o2=0
        for i in xrange(len(bb)):
            o1^=p1[i]*bb[i]
            o2^=p2[i]*bb[i]
        if debug:
            print "o1=",o1,"o2=",o2
        out+=[o1]+[o2]
    return out

# depuncture 3/4
# wikipedia: [1,0,1,1,1,0],  auto-fec: [1,1,0,1,1,0] and [1,1,1,0,0,1]
d1a= [1,0,1,1,1,0]
d1b= [0,1,1,1,0,1]
d1c= [1,1,1,0,1,0]
d1d= [1,1,0,1,0,1]
d1e= [1,0,1,0,1,1]
d1f= [0,1,0,1,1,1]

d2a= [1,1,0,1,1,0]
d2b= [1,0,1,1,0,1]
d2c= [0,1,1,0,1,1]

d3a= [1,1,1,0,0,1]
d3b= [1,1,0,0,1,1]
d3c= [1,0,0,1,1,1]
d3d= [0,0,1,1,1,1]
d3e= [0,1,1,1,1,0]
d3f= [1,1,1,1,0,0]

def puncture(dp,bits):
    debug=0
    ostr=''
    for i in xrange(len(bits)):
        if(dp[i%len(dp)]):
            ostr+=str(bits[i])
        else:
            if debug:
                ostr+='.'
    return ostr
