# dpl wireshark dissector

lua dissector for DPL (Digital Peripheral Link), the byte-level protocol on the UART link between an Iridium ISU and attached peripherals (handsets, SIM readers, controllers), plus the firmware-upgrade transport.

## framing (Layer 2)

```
+--------+--------+---------------------+---------+------+
| STX(1) | LEN(1) | PAYLOAD (LEN bytes) | XOR(1)  | ETX  |
+--------+--------+---------------------+---------+------+

XOR = STX ^ LEN ^ payload[0] ^ ... ^ payload[LEN-1]
ETX = 0x03 (always)
```

no sync word, no CRC. integrity is the one-byte xor. terminator is always `0x03`.

## STX values

`STX` is the Start-of-I-Frame character. besides being the frame delimiter it also selects which logical device / protocol family the frame is addressed to.

| STX | Name | Direction | Purpose |
|---|---|---|---|
| 0x01 | DLOG | ISU ↔ host | Data Logger |
| 0x02 | TPI  | ISU ↔ host | Test/Production Interface |
| 0x04 | reserved | — | special use |
| 0x05 | firmware upgrade transport | ISU ↔ host | |
| 0x07 | STDIO | ISU → host | text |
| 0x81 … 0x87 | IP1 … IP7 | ISU ↔ peripheral | Intelligent Peripheral addresses |

ACK (0x06) and NAK (0x15) are single-byte control characters outside the I-frame; they don't carry a length byte and are not dissected as separate frames.

only frames with STX in this table are accepted by the heuristic.

## firmware upgrade opcodes (STX=0x05)

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

## Layer 3 — PMH (for STX=0x81 … 0x87)

for frames addressed to an Intelligent Peripheral the payload starts with a 5-byte **Peripheral Message Header** followed by primitive-specific Layer 3 data:

```
byte 0 : addr(hi nybble) | sequence(lo nybble)    ; 0xE=ISU, 0x1..0x7=IP
byte 1 : Interface ID                              ; protocol family
byte 2 : Primitive ID                              ; command / indication
byte 3 : Destination sub-address
byte 4 : Source sub-address
byte 5…: Layer 3 data
```

the dissector decodes the header and names the primitive where possible.

### Interface IDs

| id   | family |
|---|---|
| 0x14 | SEEM (SIM External Module) |
| 0x94 | Audio |
| 0x98 | SIM (external card reader) |
| 0xA7 | DPL control / MMI / TEST (includes INIT/RTI) |
| 0xA8 | MMI / Call Control / Audio |

### Recognised primitives

the dissector names every (iface, prim) combination it knows. it does **not** currently decode primitive payload fields — only the header. Layer 3 data is shown as raw bytes with a label; extend per-primitive decoders as captures require them.

representative primitives:

- **0xA7 (discovery / MMI / TEST):** `INIT` (0x12), `RTI` (0x13), `ECHO` (0x14), `DEBUG` (0xFF), `HSCTRL`/`HSLCD`/`HSKPD` (0x15/0x16/0x17), `ip_change_pin_req` (0x02), `ip_man_reg_req` (0x06), `ip_ss_status_ind` (0x0C), and related `_cnf`s.
- **0xA8 (MMI/CC/Audio):** `ip_call_start_req` (0x05), `ip_call_accept_req` (0x20), `ip_call_release_req` (0x21), `ip_call_status_ind` (0x27), `ip_class_ind` (0x29), `ip_call_dtmf_req` (0x35), `ip_gen_imei_req/_cnf` (0x36/0x37), `ip_gen_pin_stat_req/_cnf` (0x38/0x39), `ip_gen_pin_set_req/_cnf` (0x3A/0x3B), `ip_signal_level_req/_cnf` (0x04/0x2D), `ip_mute_req/_ind` (0x22/0x08), `ip_sidetone_req/_cnf` (0x41/0x42), `ip_audio_routing_req` (0x40), and more.
- **0x14 (SEEM):** `seem_activate_ind`/`_cnf` (0x03/0x02), `seem_status_cnf` (0x0F), the PIN `_cnf` family (0x11, 0x13, 0x15, 0x17), `seem_unblocking_cnf` (0x19), `ip_get_info_element_cnf` (0x0C).
- **0x94 (Audio):** `ip_key_feedback_ind` (0x0E).
- **0x98 (SIM):** `sim_activate_req`/`_cnf` (0x00/0x20), `sim_deactivate_req/_cnf` (0x06/0x21), `sim_instruction_req/_cnf` (0x03/0x23) (GSM 11.11 passthrough), `sim_card_detect_ind` (0x40), `sim_switch_act_volt_req` (0x01).

see `dpl.lua` for the full table.

## install

drop `dpl.lua` into your Wireshark personal Lua plugins dir. on linux/macOS that's usually `~/.local/lib/wireshark/plugins/` or `~/.config/wireshark/plugins/`. check `Help -> About Wireshark -> Folders` if unsure. reload plugins (`Analyze -> Reload Lua Plugins`) or restart.

the dissector registers a heuristic on `tcp`, `udp`, `usb.bulk`, `usb.interrupt` that only fires when length + xor + terminator all match and STX is one we know. anything marginal stays as plain `Data` so you can still use `Decode As -> DPL` manually if you want to force it.

## generating test frames

`dpl_encode.py` builds DPL frames and wraps them in UDP over the BSD null link-type so Wireshark can pick them up.

```
python3 dpl_encode.py                   # regenerate tests/sample.pcap
python3 dpl_encode.py --hex 05 80       # print hex for one frame
```

the module exports two helpers: `encode(stx, payload)` wraps a full DPL frame, and `pmh(addr, seq, iface, prim, dest, src, data)` builds a Peripheral Message Header + L3 data (use as the `payload` argument to `encode` for STX[IPn] frames).

verify:

```
tshark -r tests/sample.pcap -X lua_script:dpl.lua -O dpl
```

`tests/sample.pcap` covers every known firmware-upgrade opcode on STX=0x05, an STDIO (STX=0x07) and a DLOG (STX=0x01) opaque payload, PMH-bearing STX=0x81 frames (`INIT`, `RTI`, `ip_call_start_req`, `ip_call_status_ind`, `sim_instruction_req`), a STX=0x82 (IP2) frame carrying a SEEM primitive, a STX=0x81 frame with a too-short payload (triggers the "payload too short for PMH" expert hint), and one deliberately-corrupted xor to confirm the heuristic doesn't accept bad frames.
