#!/usr/bin/env python3
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

        for i in range(len(a)):
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
    for i in range(len(aa)):
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
    for i in range(len(a)):
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
    for b1 in range(len(b)):
        bnum1=bnum^(1<<b1)
        bnum1str=("{0:0%db}"%blen).format(bnum1)
        r=divide(a,bnum1str)
        if(r==0):
            return (1,bnum1str)
        for b2 in range(b1+1,len(b)):
            bnum2=bnum1^(1<<b2)
            bnum2str=("{0:0%db}"%blen).format(bnum2)
            r=divide(a,bnum2str)
            if(r==0):
                return (2,bnum2str)
    return(-1,b)

def nrepair1(a,b): # "repair" one bit error by brute force.
    r=ndivide(a,b)
    if(r==0):
        return (0,b)
    blen=len(b)
    bnum=int(b,2)
    for b1 in range(len(b)):
        bnum1=bnum^(1<<b1)
        r=nndivide(a,bnum1)
        if(r==0):
            bnum1str=("{0:0%db}"%blen).format(bnum1)
            return (1,bnum1str)
    return(-1,b)

def nrepair2(a,b): # "repair" two bit errors by brute force.
    r=ndivide(a,b)
    if(r==0):
        return (0,b)
    blen=len(b)
    bnum=int(b,2)
    for b1 in range(len(b)):
        bnum1=bnum^(1<<b1)
        r=nndivide(a,bnum1)
        if(r==0):
            bnum1str=("{0:0%db}"%blen).format(bnum1)
            return (1,bnum1str)
    for b1 in range(len(b)):
        bnum1=bnum^(1<<b1)
        for b2 in range(b1+1,len(b)):
            bnum2=bnum1^(1<<b2)
            r=nndivide(a,bnum2)
            if(r==0):
                bnum2str=("{0:0%db}"%blen).format(bnum2)
                return (2,bnum2str)
    return(-1,b)

def nrepair(poly, b): # "repair" any bit errors by syndromes
    r=nndivide(poly, int(b,2))
    if(r==0):
        return (0,b)
    if syndromes[poly][r] is None: # uncorrectable
        return(-1,b)

    ecnt, eloc = syndromes[poly][r]
    bnum=eloc ^ int(b,2)

    fstr="{0:0%db}"%len(b)
    return (ecnt,fstr.format(bnum))

def bch_repair1(poly,bits):
    (errs,repaired)=nrepair1(poly,bits)
    return (errs,repaired[:-poly.bit_length()+1],repaired[-poly.bit_length()+1:])

def bch_repair2(poly,bits):
    (errs,repaired)=nrepair2(poly,bits)
    return (errs,repaired[:-poly.bit_length()+1],repaired[-poly.bit_length()+1:])

def bch_repair(poly,bits):
    (errs,repaired)=nrepair(poly,bits)
    return (errs,repaired[:-poly.bit_length()+1],repaired[-poly.bit_length()+1:])

def mk_syn(poly, bits, synbits, errors=1, debug=False):
    assert errors in (1,2,3)
    syndromes[poly]=[None]*(2**(synbits))

    if debug:
        print("Creating syndromes for poly=%d with %d bits and max %d bit-errors"%(poly, bits, errors))
        print("Max syndrome value is: 2^%d = %d"%(synbits, 2**synbits))

    for n1 in range(0,bits):
        val=(1<<n1)
        r=nndivide(poly,val)
        if debug:
            print(("1 {:0%db} -> {:4d} / {:0%db}"%(bits,synbits)).format(val,r,r))
        syndromes[poly][r]=(1, val)

    if errors >= 2:
        for n1 in range(0,bits):
            for n2 in range(n1+1,bits):
                val=(1<<n1)|(1<<n2)
                r=nndivide(poly,val)
                if debug:
                    print(("2 {:0%db} -> {:4d} / {:0%db}"%(bits,synbits)).format(val,r,r))
                if syndromes[poly][r] is None:
                    syndromes[poly][r]=(2, val)
                else:
                    raise AssertionError("Poly(%d) collision on syndrome %d (error locators %s / %s)"%(poly, r, bin(val), bin(syndromes[poly][r][1])))

    if errors == 3:
        for n1 in range(0,bits):
            for n2 in range(n1+1,bits):
                for n3 in range(n2+1,bits):
                    val=(1<<n1)|(1<<n2)|(1<<n3)
                    r=nndivide(poly,val)
                    if debug:
                        print(("3 {:0%db} -> {:4d} / {:0%db}"%(bits,synbits)).format(val,r,r))
                    if syndromes[poly][r] is None:
                        syndromes[poly][r]=(3, val)
                    else:
                        raise AssertionError("Poly(%d) collision on syndrome %d (error locators %s / %s)"%(poly, r, bin(val), bin(syndromes[poly][r][1])))

    if debug:
        elems=sum(x is not None for x in syndromes[poly])
        elems+=1 # 0 element
        print("BCH efficiency: %d/%d %02d%%"%(elems,2**synbits,(2*elems/2**synbits)*100))

def print_syn(syndromes, bits=31, synbits=10):
    for r, v in enumerate(syndromes):
        if v is None:
            print(("> {:%ds} -> {:4d} / {:0%db}"%(bits,synbits)).format("",r,r))
        else:
            eb, val = v
            if val == -1:
                print(("c {:%ds} -> {:4d} / {:0%db}"%(bits,synbits)).format("",r,r))
            else:
                print(("%d {:0%db} -> {:4d} / {:0%db}"%(eb, bits,synbits)).format(val,r,r))


syndromes={}

def init(debug=False):
    mk_syn(poly=29,   bits=7,  synbits=4,            debug=debug)
    mk_syn(poly=465,  bits=14, synbits=8,  errors=2, debug=debug)
    mk_syn(poly=41,   bits=26, synbits=5,            debug=debug)
    mk_syn(poly=1897, bits=31, synbits=10, errors=2, debug=debug)
    mk_syn(poly=1207, bits=31, synbits=10, errors=2, debug=debug)
    mk_syn(poly=3545, bits=31, synbits=11, errors=2, debug=debug)

if __name__ == "__main__":
    init(True)
else:
    init()
