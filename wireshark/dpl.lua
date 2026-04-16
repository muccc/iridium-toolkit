-- DPL dissector for Wireshark
--
-- Usage:
--   1. Drop this file into your Wireshark personal Lua plugins directory
--      (Help -> About Wireshark -> Folders -> Personal Lua Plugins).
--   2. Reload Lua plugins (Analyze -> Reload Lua Plugins) or restart Wireshark.
--   3. Right-click a packet -> "Decode As..." -> pick "DPL".
--
-- Heuristic activation is also registered on a few common transports.
-- Accepts a single DPL frame per dissected PDU.

local dpl = Proto("dpl", "DPL")

local channel_names = {
    [0x05] = "firmware upgrade transport",
    [0x81] = "host-to-modem control link",
}

local ch05_opcode_names = {
    [0x80] = "PING",
    [0x83] = "GETID",
    [0x85] = "WRITEBUFF",
    [0x86] = "READBUFF",
    [0x89] = "CLEARBUFF",
    [0x8a] = "ERASECHIP",
    [0x8c] = "ERASESECT",
    [0x8f] = "WRITESECT",
    [0xc0] = "READSECT",
    [0xc6] = "BOOT",
}

local f_ch      = ProtoField.uint8 ("dpl.ch",      "Channel",       base.HEX, channel_names)
local f_len     = ProtoField.uint8 ("dpl.len",     "Length",        base.DEC)
local f_payload = ProtoField.bytes ("dpl.payload", "Payload")
local f_opcode  = ProtoField.uint8 ("dpl.opcode",  "Opcode",        base.HEX, ch05_opcode_names)
local f_xor     = ProtoField.uint8 ("dpl.xor",     "XOR",           base.HEX)
local f_xor_ok  = ProtoField.bool  ("dpl.xor_ok",  "XOR valid")
local f_eom     = ProtoField.uint8 ("dpl.eom",     "End-of-message",base.HEX)

dpl.fields = { f_ch, f_len, f_payload, f_opcode, f_xor, f_xor_ok, f_eom }

local ef_bad_xor = ProtoExpert.new("dpl.bad_xor.expert", "DPL XOR mismatch",
                                   expert.group.CHECKSUM, expert.severity.WARN)
local ef_bad_eom = ProtoExpert.new("dpl.bad_eom.expert", "DPL terminator is not 0x03",
                                   expert.group.MALFORMED, expert.severity.WARN)
dpl.experts = { ef_bad_xor, ef_bad_eom }

local function compute_xor(tvb, first, last)
    local x = 0
    for i = first, last do
        x = bit.bxor(x, tvb(i, 1):uint())
    end
    return x
end

-- Validate framing without asserting on errors. Returns:
--   ok, len, expected_xor, actual_xor, eom_byte
-- ok is false if the buffer cannot be a DPL frame at all.
local function validate(tvb)
    if tvb:len() < 4 then return false end
    local plen = tvb(1, 1):uint()
    local expected_size = 1 + 1 + plen + 1 + 1
    if tvb:len() ~= expected_size then return false end
    local eom = tvb(tvb:len() - 1, 1):uint()
    local expected_xor = compute_xor(tvb, 0, 1 + plen)
    local actual_xor = tvb(2 + plen, 1):uint()
    return true, plen, expected_xor, actual_xor, eom
end

function dpl.dissector(tvb, pinfo, tree)
    local ok, plen, expected_xor, actual_xor, eom = validate(tvb)
    if not ok then return 0 end

    pinfo.cols.protocol = "DPL"

    local subtree = tree:add(dpl, tvb(), "DPL")
    subtree:add(f_ch,  tvb(0, 1))
    subtree:add(f_len, tvb(1, 1))

    local ch = tvb(0, 1):uint()

    if plen > 0 then
        local payload_tvb = tvb(2, plen)
        subtree:add(f_payload, payload_tvb)
        if ch == 0x05 then
            subtree:add(f_opcode, tvb(2, 1))
        end
    end

    local xor_item = subtree:add(f_xor, tvb(2 + plen, 1))
    subtree:add(f_xor_ok, expected_xor == actual_xor)
        :set_generated()
    if expected_xor ~= actual_xor then
        xor_item:add_proto_expert_info(ef_bad_xor,
            string.format("expected 0x%02x, got 0x%02x", expected_xor, actual_xor))
    end

    local eom_item = subtree:add(f_eom, tvb(tvb:len() - 1, 1))
    if eom ~= 0x03 then
        eom_item:add_proto_expert_info(ef_bad_eom)
    end

    local info
    if ch == 0x05 and plen > 0 then
        local op = tvb(2, 1):uint()
        info = string.format("ch=0x%02x op=%s len=%d", ch,
                             ch05_opcode_names[op] or string.format("0x%02x", op),
                             plen)
    else
        info = string.format("ch=0x%02x len=%d", ch, plen)
    end
    pinfo.cols.info = info

    return tvb:len()
end

local function dpl_heur(tvb, pinfo, tree)
    local ok, _, expected_xor, actual_xor, eom = validate(tvb)
    if not ok then return false end
    if eom ~= 0x03 then return false end
    if expected_xor ~= actual_xor then return false end
    local ch = tvb(0, 1):uint()
    if channel_names[ch] == nil then return false end
    dpl.dissector(tvb, pinfo, tree)
    return true
end

dpl:register_heuristic("tcp", dpl_heur)
dpl:register_heuristic("udp", dpl_heur)
dpl:register_heuristic("usb.bulk", dpl_heur)
dpl:register_heuristic("usb.interrupt", dpl_heur)
