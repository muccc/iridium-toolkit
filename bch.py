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
        if(len(bb)-one<=len(aa)):
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
