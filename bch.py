#!/usr/bin/python
# vim: set ts=4 sw=4 tw=0 et pm=:
from fec import stringify, listify

def divide(a,b):
    aa=listify (a);
    bb=listify (b);

    while True:
        try:
            one=bb.index(1);
        except:
            return "0";

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
    return stringify(bb)

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
