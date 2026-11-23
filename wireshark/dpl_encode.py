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


def encode(stx: int, payload: bytes = b"") -> bytes:
    """Return a full DPL frame: STX, LEN, payload, XOR, ETX (0x03)."""
    if not 0 <= stx <= 0xff:
        raise ValueError("STX out of range")
    if len(payload) > 0xff:
        raise ValueError("payload too long for 1-byte length field")
    header = bytes([stx, len(payload)])
    body = header + payload
    x = 0
    for b in body:
        x ^= b
    return body + bytes([x, 0x03])


def pmh(
    addr: int,
    seq: int,
    iface: int,
    prim: int,
    dest: int = 0x00,
    src: int = 0x00,
    data: bytes = b"",
) -> bytes:
    """Build a Peripheral Message Header + Layer 3 data payload.

    Used as the payload of an STX[IPn] frame.

    addr: 4-bit destination address (0xE=ISU, 0x1..0x7=IP).
    seq:  4-bit sequence number.
    """
    if not 0 <= addr <= 0xf:
        raise ValueError("addr is a nybble")
    if not 0 <= seq <= 0xf:
        raise ValueError("seq is a nybble")
    for name, v in (("iface", iface), ("prim", prim), ("dest", dest), ("src", src)):
        if not 0 <= v <= 0xff:
            raise ValueError(f"{name} out of range")
    return bytes([(addr << 4) | seq, iface, prim, dest, src]) + data


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

    # STX=0x05: firmware upgrade transport
    frames.append(encode(0x05, bytes([0x80])))                       # PING
    frames.append(encode(0x05, bytes([0x83])))                       # GETID
    frames.append(encode(0x05, bytes([0x86, 0x00, 0x00, 0x00])))     # READBUFF
    frames.append(encode(0x05, bytes([0xc0, 0x12, 0x34])))           # READSECT
    frames.append(encode(0x05, bytes([0xc6])))                       # BOOT

    # STX=0x07: STDIO
    frames.append(encode(0x07, b"ready\r\n"))

    # STX=0x01: DLOG, opaque payload
    frames.append(encode(0x01, bytes([0xde, 0xad, 0xbe, 0xef])))

    # STX=0x81 (IP1) with PMH: INIT
    # ISU -> IP1, seq=0, iface=0xA7, prim=0x12, data=protocol version byte
    frames.append(encode(0x81, pmh(0x1, 0, 0xa7, 0x12, 0x00, 0x00, bytes([0x02]))))

    # STX=0x81 with PMH: RTI (Response To INIT) — 16 bytes
    # IP1 -> ISU, seq=0, iface=0xA7, prim=0x13
    # serial(6) + device_emulation_group(4 LE) + requested_events_group(4 LE) + rsvd(2)
    rti_data = (
        bytes([0x80, 0x32, 0xe0, 0x00, 0x00, 0x01])
        + b"\x80\x00\x00\x00"
        + b"\xc8\x00\x00\x00"
        + b"\x00\x00"
    )
    frames.append(encode(0x81, pmh(0xe, 0, 0xa7, 0x13, 0x00, 0x00, rti_data)))

    # STX=0x81 with PMH: ip_call_start_req (keypad dial)
    # IP1 -> ISU, seq=1, iface=0xA8, prim=0x05, dest=0x17, src=0x00
    call_start = (
        bytes([0x00, 0x00, 0x91, 0x00])
        + b"+14805551212\x00"
    )
    frames.append(encode(0x81, pmh(0xe, 1, 0xa8, 0x05, 0x17, 0x00, call_start)))

    # STX=0x81 with PMH: ip_call_status_ind
    # ISU -> IP1, seq=2, iface=0xA8, prim=0x27
    frames.append(encode(0x81, pmh(0x1, 2, 0xa8, 0x27, 0x00, 0x00, bytes([0x02, 0x01, 0x00]))))

    # STX=0x82 (IP2) with PMH: seem_status_cnf
    # ISU -> IP2, seq=0, iface=0x14, prim=0x0F
    frames.append(encode(0x82, pmh(0x2, 0, 0x14, 0x0f, 0x00, 0x00, bytes([0x06]))))

    # STX=0x81 with PMH: sim_instruction_req (GSM 11.11 passthrough)
    # IP1 -> ISU, seq=3, iface=0x98, prim=0x03
    # minimal GSM 11.11 header: CLA=A0 INS=C0 P1=00 P2=00 P3=16 + direction=0
    sim_instr = bytes([0xa0, 0xc0, 0x00, 0x00, 0x16, 0x00])
    frames.append(encode(0x81, pmh(0xe, 3, 0x98, 0x03, 0xfa, 0x00, sim_instr)))

    # STX=0x81 too short for PMH (should trigger expert info)
    frames.append(encode(0x81, b"AT\r"))

    # Malformed: bad XOR
    bad = bytearray(encode(0x05, bytes([0x80, 0x11])))
    bad[-2] ^= 0xff
    frames.append(bytes(bad))

    return frames


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hex", nargs="+", metavar="BYTE",
                    help="print hex for one DPL frame: first byte is STX, "
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
