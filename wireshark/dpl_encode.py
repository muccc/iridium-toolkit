#!/usr/bin/env python3
# Encode DPL frames and emit a pcap for dissector testing.
#
# Usage:
#   python3 dpl_encode.py           # regenerate tests/sample.pcap
#   python3 dpl_encode.py --hex 05 80   # print hex for a single frame
#
# No third-party deps. Frames are wrapped in UDP/IP over the BSD null
# loopback link type; Wireshark's heuristic dissector lookup handles the rest.

import argparse
import os
import struct
import sys
import time


def encode(ch: int, payload: bytes = b"") -> bytes:
    """Return a full DPL frame: ch, len, payload, xor, 0x03."""
    if not 0 <= ch <= 0xff:
        raise ValueError("channel out of range")
    if len(payload) > 0xff:
        raise ValueError("payload too long for 1-byte length field")
    header = bytes([ch, len(payload)])
    body = header + payload
    x = 0
    for b in body:
        x ^= b
    return body + bytes([x, 0x03])


def wrap_udp(dpl_frame: bytes, sport: int = 4000, dport: int = 4001) -> bytes:
    """Wrap a DPL frame as UDP/IPv4 over loopback (BSD null encap)."""
    udp_len = 8 + len(dpl_frame)
    udp = struct.pack("!HHHH", sport, dport, udp_len, 0) + dpl_frame

    ip_total = 20 + udp_len
    ip_hdr = struct.pack(
        "!BBHHHBBH4s4s",
        0x45, 0x00, ip_total,
        0x0000, 0x0000,
        64, 17, 0x0000,
        b"\x7f\x00\x00\x01",
        b"\x7f\x00\x00\x01",
    )
    ip_chk = _ip_checksum(ip_hdr)
    ip_hdr = ip_hdr[:10] + struct.pack("!H", ip_chk) + ip_hdr[12:]

    loopback_family = struct.pack("<I", 2)  # AF_INET little-endian
    return loopback_family + ip_hdr + udp


def _ip_checksum(hdr: bytes) -> int:
    s = 0
    for i in range(0, len(hdr), 2):
        s += (hdr[i] << 8) | hdr[i + 1]
    while s >> 16:
        s = (s & 0xffff) + (s >> 16)
    return (~s) & 0xffff


def write_pcap(path: str, frames: list[bytes]) -> None:
    """Write pcap file in LINKTYPE_NULL (BSD loopback) format."""
    with open(path, "wb") as f:
        f.write(struct.pack("=IHHIIII",
                            0xa1b2c3d4,
                            2, 4,
                            0, 0,
                            65535,
                            0))  # link_type 0 = LINKTYPE_NULL
        ts = int(time.time())
        for i, frame in enumerate(frames):
            pkt = wrap_udp(frame)
            f.write(struct.pack("=IIII", ts, i, len(pkt), len(pkt)))
            f.write(pkt)


def sample_frames() -> list[bytes]:
    frames = []
    # channel 0x05: firmware upgrade transport
    frames.append(encode(0x05, bytes([0x80])))                       # PING
    frames.append(encode(0x05, bytes([0x83])))                       # GETID
    frames.append(encode(0x05, bytes([0x86, 0x00, 0x00, 0x00])))     # READBUFF + addr
    frames.append(encode(0x05, bytes([0xc0, 0x12, 0x34])))           # READSECT
    frames.append(encode(0x05, bytes([0xc6])))                       # BOOT
    # channel 0x81: host-to-modem control link, opaque payloads
    frames.append(encode(0x81, b"AT\r"))
    frames.append(encode(0x81, b"hello"))
    # malformed: bad xor (swap last data byte)
    good = bytearray(encode(0x05, bytes([0x80, 0x11])))
    good[-2] ^= 0xff
    frames.append(bytes(good))
    return frames


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hex", nargs="+", metavar="BYTE",
                    help="print hex for one DPL frame: first byte is channel, "
                         "rest is payload. Example: --hex 05 80")
    ap.add_argument("-o", "--out", default=None,
                    help="output pcap path (default: tests/sample.pcap next to this script)")
    args = ap.parse_args()

    if args.hex:
        vals = [int(x, 16) for x in args.hex]
        frame = encode(vals[0], bytes(vals[1:]))
        print(frame.hex())
        return 0

    out = args.out
    if out is None:
        here = os.path.dirname(os.path.abspath(__file__))
        out = os.path.join(here, "tests", "sample.pcap")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    write_pcap(out, sample_frames())
    print("wrote", out, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
