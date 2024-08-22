#!/usr/bin/env python3

from ctypes import c_void_p, c_char_p, c_char, c_int, c_size_t, c_bool, c_long
from ctypes import Structure, POINTER, CDLL, cast
from enum import IntEnum, auto


class CtypesEnum(IntEnum):
    """A ctypes-compatible IntEnum superclass."""
    @classmethod
    def from_param(cls, obj):
        return int(obj)


class la_msg_dir(CtypesEnum):
    LA_MSG_DIR_UNKNOWN = 0
    LA_MSG_DIR_GND2AIR = auto()
    LA_MSG_DIR_AIR2GND = auto()


class la_reasm_status(CtypesEnum):
    LA_REASM_UNKNOWN = 0
    LA_REASM_COMPLETE = auto()
    LA_REASM_IN_PROGRESS = auto()
    LA_REASM_SKIPPED = auto()
    LA_REASM_DUPLICATE = auto()
    LA_REASM_FRAG_OUT_OF_SEQUENCE = auto()
    LA_REASM_ARGS_INVALID = auto()


class timeval(Structure):
    _fields_ = [
        ("tv_sec", c_long),
        ("tv_usec", c_long)
    ]


class la_type_descriptor(Structure):
    _fields_ = [
        ("format_text", c_void_p),
        ("destroy", c_void_p),
        ("format_json", c_void_p),
        ("json_key", c_char_p),
    ]


class la_acars_msg(Structure):
    _fields_ = [
        ("crc_ok", c_bool),
        ("err", c_bool),
        ("final_block", c_bool),
        ("mode", c_char),
        ("reg", c_char * 8),
        ("ack", c_char),
        ("label", c_char * 3),
        ("sublabel", c_char * 3),
        ("mfi", c_char * 3),
        ("block_id", c_char),
        ("msg_num", c_char * 4),
        ("msg_num_seq", c_char),
        ("flight_id", c_char * 7),
        ("reasm_status", c_int),
        # ...
    ]


class la_proto_node(Structure):
    pass


la_proto_node._fields_ = [
    ("td", POINTER(la_type_descriptor)),
    ("data", c_void_p),
    ("next", POINTER(la_proto_node)),
    # ...
]


class la_vstr(Structure):
    _fields_ = [
        ("str", c_char_p),
        ("len", c_size_t),
        ("allocated_size", c_size_t),
    ]


class libacars:
    lib = CDLL("libacars-2.so")

    version = cast(lib.LA_VERSION, POINTER(c_char_p)).contents.value.decode("ascii")

    lib.la_acars_parse.restype = POINTER(la_proto_node)
    lib.la_acars_parse.argtypes = [c_char_p, c_size_t, la_msg_dir]

    lib.la_acars_parse_and_reassemble.restype = POINTER(la_proto_node)
    lib.la_acars_parse_and_reassemble.argtypes = [c_char_p, c_size_t, la_msg_dir, c_void_p, timeval]

    lib.la_proto_tree_format_text.restype = POINTER(la_vstr)
    lib.la_proto_tree_format_text.argtypes = [c_void_p, POINTER(la_proto_node)]

    lib.la_proto_tree_format_json.restype = POINTER(la_vstr)
    lib.la_proto_tree_format_json.argtypes = [c_void_p, POINTER(la_proto_node)]

    lib.la_vstring_destroy.restype = None
    lib.la_vstring_destroy.argtypes = [POINTER(la_vstr), c_bool]

    lib.la_proto_tree_destroy.restype = None
    lib.la_proto_tree_destroy.argtypes = [POINTER(la_proto_node)]

    lib.la_reasm_ctx_new.restype = c_void_p
    lib.la_reasm_ctx_new.argtypes = []

    ctx = lib.la_reasm_ctx_new()

    def __init__(self, data, direction=la_msg_dir.LA_MSG_DIR_UNKNOWN, time=None):
        x = data[1:]
        if x[0] == 3: # Cut (unknown) iridium header
            x = x[8:]
        if time is None:
            self.p = libacars.lib.la_acars_parse(x, len(x), direction)
        else:
            self.p = libacars.lib.la_acars_parse_and_reassemble(x, len(x), direction, libacars.ctx, timeval(int(time), int(time-int(time))*1000000))

    def json(self):
        vstr = libacars.lib.la_proto_tree_format_json(None, self.p)
        rv = vstr.contents.str.decode("ascii")
        libacars.lib.la_vstring_destroy(vstr, True)
        return rv

    def is_err(self):
        if self.p.contents.td.contents.json_key != b"acars":
            return False
        return cast(self.p.contents.data, POINTER(la_acars_msg)).contents.err

    def is_ping(self):
        if self.p.contents.td.contents.json_key != b"acars":
            return False
        if cast(self.p.contents.data, POINTER(la_acars_msg)).contents.err:
            return False
        return cast(self.p.contents.data, POINTER(la_acars_msg)).contents.label in (b'_d', b'Q0')

    def is_reasm(self):
        if self.p.contents.td.contents.json_key != b"acars":
            return False
        if cast(self.p.contents.data, POINTER(la_acars_msg)).contents.err:
            return False
        return cast(self.p.contents.data, POINTER(la_acars_msg)).contents.reasm_status == la_reasm_status.LA_REASM_IN_PROGRESS

    def is_interesting(self):
        if self.p.contents.td.contents.json_key != b"acars":
            return True
        if self.p.contents.next:
            return True
        else:
            return False

    def debug(self):
        print(self.p.contents.td, ":", self.p.contents.td.contents.json_key)
        print("err:", cast(self.p.contents.data, POINTER(la_acars_msg)).contents.err)
        if self.p.contents.next:
            print("More contents")
            print(self.p.contents.next.contents)
        else:
            print("No more contents")

    def __str__(self):
        vstr = libacars.lib.la_proto_tree_format_text(None, self.p)
        rv = vstr.contents.str.decode("ascii")
        libacars.lib.la_vstring_destroy(vstr, True)
        return rv

    def __del__(self):
        libacars.lib.la_proto_tree_destroy(self.p)


if __name__ == '__main__':
    import sys
    print(f"LibACARS version {libacars.version}\n")

    if len(sys.argv) <= 1:
        print("No arguments.", file=sys.stderr)
        exit(1)

    if len(sys.argv) == 2:
        data = bytes.fromhex(sys.argv[1])
        o = libacars(data, la_msg_dir.LA_MSG_DIR_UNKNOWN)
        print(o)
        print("JSON:")
        print(o.json())

    else:
        print("With reassembly:")

        for i, d in enumerate(sys.argv[1:]):
            data = bytes.fromhex(d)
            o = libacars(data, la_msg_dir.LA_MSG_DIR_UNKNOWN, i)
            if o.is_err():
                print(f"Couldn't parse #{1+i}")
                continue

            if o.is_reasm():
                continue

            print(f"#{1+i}", o)

    print("All done")
