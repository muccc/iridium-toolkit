# vim: set ts=4 sw=4 tw=0 et pm=:
import struct
from itertools import izip

def grouped(iterable, n):
    "s -> (s0,s1,s2,...sn-1), (sn,sn+1,sn+2,...s2n-1), (s2n,s2n+1,s2n+2,...s3n-1), ..."
    return izip(*[iter(iterable)]*n)

def write(file_name, signal):
    with open(file_name, 'wb') as out:
        signal = [item for sample
            in signal for item
            in [sample.real, sample.imag]]
        s = "<" + len(signal) * 'f'
        out.write(struct.Struct(s).pack(*signal))

def read(file_name):
    with open(file_name, "rb") as f:
        data = f.read()
        if len(data) % 8 != 0: raise Exception("Bad file len")

        struct_fmt = '<' +  len(data)/8 * '2f'
        struct_unpack = struct.Struct(struct_fmt).unpack_from
        s = struct_unpack(data)
        signal = []
        for i, q in grouped(s, 2):
            signal.append(complex(i, q))
    return signal
