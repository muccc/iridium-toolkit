# dpl wireshark dissector

small lua dissector for DPL, the byte-level framing used on `ch=0x05` (firmware upgrade transport) and `ch=0x81` (host-to-modem control link).

## framing

```
+--------+--------+---------------------+---------+------+
| ch (1) | len(1) | payload (len bytes) | xor (1) | 0x03 |
+--------+--------+---------------------+---------+------+

xor = ch ^ len ^ payload[0] ^ ... ^ payload[len-1]
```

no sync word, no CRC. integrity is the one-byte xor. terminator is always `0x03`.

## channels

| ch | purpose |
|---|---|
| 0x05 | firmware upgrade transport |
| 0x81 | host-to-modem control link |

## ch=0x05 opcodes

the first payload byte is the opcode. known values:

| opcode | name |
|---|---|
| 0x80 | PING |
| 0x83 | GETID |
| 0x85 | WRITEBUFF |
| 0x86 | READBUFF |
| 0x89 | CLEARBUFF |
| 0x8a | ERASECHIP |
| 0x8c | ERASESECT |
| 0x8f | WRITESECT |
| 0xc0 | READSECT |
| 0xc6 | BOOT |

arg layout after the opcode byte is opcode-specific and not tabulated here.

## install

drop `dpl.lua` into your Wireshark personal Lua plugins dir. on linux/macOS that's usually `~/.local/lib/wireshark/plugins/` or `~/.config/wireshark/plugins/`. check `Help -> About Wireshark -> Folders` if unsure. reload plugins (`Analyze -> Reload Lua Plugins`) or restart.

the dissector registers a heuristic on `tcp`, `udp`, `usb.bulk`, `usb.interrupt` that only fires when length + xor + terminator all match and the channel byte is one we know. anything marginal stays as plain `Data` so you can still use `Decode As -> DPL` manually if you want to force it.

## generating test frames

`dpl_encode.py` builds DPL frames and wraps them in UDP over the BSD null link-type so Wireshark can pick them up.

```
python3 dpl_encode.py                   # regenerate tests/sample.pcap
python3 dpl_encode.py --hex 05 80       # print hex for one frame
```

verify:

```
tshark -r tests/sample.pcap -X lua_script:dpl.lua -O dpl
```

`tests/sample.pcap` covers one frame per known opcode on `ch=0x05`, a couple of opaque `ch=0x81` payloads, and one deliberately-corrupted xor to confirm the heuristic doesn't accept bad frames.
