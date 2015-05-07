#!/usr/bin/python
# vim: set ts=4 sw=4 tw=0 et pm=:
from fec import stringify, listify

def nndivide(poly,num): # both args as int
    if(num==0):
        return 0
    bits=num.bit_length()-poly.bit_length()
    pow=1<<(num.bit_length()-1)

    while bits>=0:
        if (num>=pow):
            num^=(poly<<bits)
        pow>>=1
        bits-=1
    return num

def ndivide(poly,bits):
    num=int(bits,2)
    return nndivide(poly,num)

def divide(a,b): # returns b%a in GF(2) fast/binary version
    return nndivide(int(a,2),int(b,2))

def sdivide(a,b): # returns b%a in GF(2) slow/ascii version
    aa=listify (a);
    bb=listify (b);

    while True:
        try:
            one=bb.index(1);
        except:
            return 0;

    #    print "lb-o: ",len(bb)-one,"la",len(aa)
        if(len(bb)-one<len(aa)):
          break

#        print "b:   ",stringify(bb),one
#        print "a:   ",(" "*(one-1)),stringify(aa)

        for i in xrange(len(a)):
          if aa[i]==1:
            bb[one+i]=1-bb[one+i]
    #      print "i: %2d"%i,stringify(bb),"a=",aa[i]

    #    print "b:   ",stringify(bb),one

#    print "Result: ",stringify(bb)
    return int(stringify(bb),2)

def add(a,b): # unneccessary, as actually add(a,b) == a^b
    aa=listify(a)
    bb=listify(b)

    result=[]
    if (len(bb)>len(aa)):
        (aa,bb)=(bb,aa)
    for i in xrange(len(aa)):
        result[i]=(aa[i]+bb[i])%2

    return stringify(result)

def multiply(a,b):
    result=0
    idx=0
    while (b>0):
        if (b%2):
            result=result^(a<<idx)
        b>>=1
        idx+=1
    return result

def polystr(a):
    poly=[]
    for i in xrange(len(a)):
        if (a[i]=="1"):
            poly.append("x^%d"%(len(a)-1-i))

    return "+".join(poly)

def poly(a):
    return polystr("{0:b}".format(a))

def repair(a,b): # "repair" two bit errors by brute force.
    r=divide(a,b)
    if(r==0):
        return (0,b)
    blen=len(b)
    bnum=int(b,2)
    for b1 in xrange(len(b)):
        bnum1=bnum^(1<<b1)
        bnum1str=("{0:0%db}"%blen).format(bnum1)
        r=divide(a,bnum1str)
        if(r==0):
            return (1,bnum1str)
        for b2 in xrange(b1+1,len(b)):
            bnum2=bnum1^(1<<b2)
            bnum2str=("{0:0%db}"%blen).format(bnum2)
            r=divide(a,bnum2str)
            if(r==0):
                return (2,bnum2str)
    return(-1,b)

def nrepair(a,b): # "repair" two bit errors by brute force.
    r=ndivide(a,b)
    if(r==0):
        return (0,b)
    blen=len(b)
    bnum=int(b,2)
    for b1 in xrange(len(b)):
        bnum1=bnum^(1<<b1)
        r=nndivide(a,bnum1)
        if(r==0):
            bnum1str=("{0:0%db}"%blen).format(bnum1)
            return (1,bnum1str)
    for b1 in xrange(len(b)):
        bnum1=bnum^(1<<b1)
        for b2 in xrange(b1+1,len(b)):
            bnum2=bnum1^(1<<b2)
            r=nndivide(a,bnum2)
            if(r==0):
                bnum2str=("{0:0%db}"%blen).format(bnum2)
                return (2,bnum2str)
    return(-1,b)

def bch_repair(poly,bits):
    (errs,repaired)=nrepair(poly,bits)
    return (errs,repaired[:-poly.bit_length()+1],repaired[-poly.bit_length()+1:])
