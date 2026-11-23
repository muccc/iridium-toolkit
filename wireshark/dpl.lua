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

-- Layer 2 start characters.
local stx_names = {
    [0x01] = "DLOG",
    [0x02] = "TPI",
    [0x04] = "reserved",
    [0x05] = "firmware upgrade transport",
    [0x07] = "STDIO",
    [0x81] = "IP1",
    [0x82] = "IP2",
    [0x83] = "IP3",
    [0x84] = "IP4",
    [0x85] = "IP5",
    [0x86] = "IP6",
    [0x87] = "IP7",
}

local function is_ip_stx(b) return b >= 0x81 and b <= 0x87 end

-- Firmware upgrade opcodes (STX=0x05).
local fw_opcode_names = {
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

-- Layer 3 Interface IDs.
local iface_names = {
    [0x14] = "SEEM",    -- SIM External Module
    [0x94] = "Audio",
    [0x98] = "SIM",
    [0xa7] = "DPL/MMI/TEST",
    [0xa8] = "MMI/CC/Audio",
}

-- Primitive tables, keyed by (Interface ID, Prim ID) → name.
local prim_names = {
    [0xa7] = {
        [0x00] = "ip_dtmf_rec_ind",
        [0x01] = "ip_mute_dtmf_fbk_req",
        [0x02] = "ip_change_pin_req",
        [0x03] = "ip_change_pin_cnf",
        [0x04] = "ip_change_pin_state_req",
        [0x05] = "ip_change_pin_state_cnf",
        [0x06] = "ip_man_reg_req",
        [0x07] = "ip_man_reg_cnf",
        [0x0c] = "ip_ss_status_ind",
        [0x12] = "INIT",
        [0x13] = "RTI",
        [0x14] = "ECHO",
        [0x15] = "HSCTRL",
        [0x16] = "HSLCD",
        [0x17] = "HSKPD",
        [0xff] = "DEBUG",
    },
    [0xa8] = {
        [0x03] = "ip_time_charge_req",
        [0x04] = "ip_signal_level_req",
        [0x05] = "ip_call_start_req",
        [0x06] = "ip_get_info_element_req",
        [0x08] = "ip_mute_ind",
        [0x20] = "ip_call_accept_req",
        [0x21] = "ip_call_release_req",
        [0x22] = "ip_mute_req",
        [0x23] = "ip_step_volume_level_req",
        [0x25] = "ip_indr_ctrl_state_ind",
        [0x26] = "ip_pd_usage_ind",
        [0x27] = "ip_call_status_ind",
        [0x28] = "ip_audio_status_ind",
        [0x29] = "ip_class_ind",
        [0x2c] = "ip_time_charge_cnf",
        [0x2d] = "ip_signal_level_cnf",
        [0x2e] = "ip_call_start_cnf",
        [0x2f] = "ip_stop_req",
        [0x30] = "ip_stop_cnf",
        [0x31] = "ip_abbr_dial_tbl_ind",
        [0x32] = "ip_step_volume_level_cnf",
        [0x33] = "ip_mmi_display_update_ind",
        [0x35] = "ip_call_dtmf_req",
        [0x36] = "ip_gen_imei_req",
        [0x37] = "ip_gen_imei_cnf",
        [0x38] = "ip_gen_pin_stat_req",
        [0x39] = "ip_gen_pin_stat_cnf",
        [0x3a] = "ip_gen_pin_set_req",
        [0x3b] = "ip_gen_pin_set_cnf",
        [0x40] = "ip_audio_routing_req",
        [0x41] = "ip_sidetone_req",
        [0x42] = "ip_sidetone_cnf",
    },
    [0x14] = {
        [0x02] = "seem_activate_cnf",
        [0x03] = "seem_activate_ind",
        [0x06] = "seem_deactivate_ind",
        [0x0c] = "ip_get_info_element_cnf",
        [0x0f] = "seem_status_cnf",
        [0x11] = "seem_pin_change_cnf",
        [0x13] = "seem_pin_disable_cnf",
        [0x15] = "seem_pin_enable_cnf",
        [0x17] = "seem_pin_verify_cnf",
        [0x19] = "seem_unblocking_cnf",
    },
    [0x94] = {
        [0x0e] = "ip_key_feedback_ind",
    },
    [0x98] = {
        [0x00] = "sim_activate_req",
        [0x01] = "sim_switch_act_volt_req",
        [0x03] = "sim_instruction_req",
        [0x06] = "sim_deactivate_req",
        [0x20] = "sim_activate_cnf",
        [0x21] = "sim_deactivate_cnf",
        [0x23] = "sim_instruction_cnf",
        [0x40] = "sim_card_detect_ind",
    },
}

local function prim_name(iface, prim)
    local t = prim_names[iface]
    if t == nil then return nil end
    return t[prim]
end

local function addr_name(a)
    if a == 0xe then return "ISU" end
    if a >= 0x1 and a <= 0x7 then return "IP" .. a end
    return string.format("0x%x", a)
end

-- Protocol fields
local f_stx       = ProtoField.uint8 ("dpl.stx",       "STX",            base.HEX, stx_names)
local f_len       = ProtoField.uint8 ("dpl.len",       "Length",         base.DEC)
local f_payload   = ProtoField.bytes ("dpl.payload",   "Payload")
local f_fw_opcode = ProtoField.uint8 ("dpl.fw.opcode", "Firmware opcode",base.HEX, fw_opcode_names)
local f_xor       = ProtoField.uint8 ("dpl.xor",       "XOR",            base.HEX)
local f_xor_ok    = ProtoField.bool  ("dpl.xor_ok",    "XOR valid")
local f_eom       = ProtoField.uint8 ("dpl.eom",       "End-of-message", base.HEX)

-- PMH (Peripheral Message Header) — only present for STX[IPn]
local f_pmh_addr  = ProtoField.uint8 ("dpl.pmh.addr",  "Address",        base.HEX, nil, 0xf0)
local f_pmh_seq   = ProtoField.uint8 ("dpl.pmh.seq",   "Sequence",       base.DEC, nil, 0x0f)
local f_pmh_iface = ProtoField.uint8 ("dpl.pmh.iface", "Interface ID",   base.HEX, iface_names)
local f_pmh_prim  = ProtoField.uint8 ("dpl.pmh.prim",  "Primitive ID",   base.HEX)
local f_pmh_dest  = ProtoField.uint8 ("dpl.pmh.dest",  "Dest sub-addr",  base.HEX)
local f_pmh_src   = ProtoField.uint8 ("dpl.pmh.src",   "Src sub-addr",   base.HEX)
local f_pmh_data  = ProtoField.bytes ("dpl.pmh.data",  "L3 Data")

-- Generated / resolved fields
local f_pmh_prim_name = ProtoField.string("dpl.pmh.prim_name", "Primitive name")

dpl.fields = {
    f_stx, f_len, f_payload, f_fw_opcode, f_xor, f_xor_ok, f_eom,
    f_pmh_addr, f_pmh_seq, f_pmh_iface, f_pmh_prim,
    f_pmh_dest, f_pmh_src, f_pmh_data, f_pmh_prim_name,
}

local ef_bad_xor = ProtoExpert.new("dpl.bad_xor.expert", "DPL XOR mismatch",
                                   expert.group.CHECKSUM, expert.severity.WARN)
local ef_bad_eom = ProtoExpert.new("dpl.bad_eom.expert", "DPL terminator is not 0x03",
                                   expert.group.MALFORMED, expert.severity.WARN)
local ef_short_ip = ProtoExpert.new("dpl.short_ip.expert",
                                    "STX[IPn] payload too short for PMH (<5 bytes)",
                                    expert.group.MALFORMED, expert.severity.WARN)
dpl.experts = { ef_bad_xor, ef_bad_eom, ef_short_ip }

local function compute_xor(tvb, first, last)
    local x = 0
    for i = first, last do
        x = bit.bxor(x, tvb(i, 1):uint())
    end
    return x
end

-- Returns: ok, len, expected_xor, actual_xor, eom_byte
-- ok=false means the buffer cannot be a DPL frame at all.
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

-- Dissect the 5-byte PMH + optional L3 data, starting at offset `off`.
-- Returns an info string describing the primitive for the column display.
local function dissect_pmh(tvb, off, plen, subtree)
    local pmh = subtree:add(dpl, tvb(off, plen), "Peripheral Message Header")

    local addr_byte = tvb(off, 1):uint()
    local addr = bit.rshift(addr_byte, 4)
    local seq  = bit.band(addr_byte, 0x0f)
    pmh:add(f_pmh_addr,  tvb(off, 1)):append_text(string.format(" (%s)", addr_name(addr)))
    pmh:add(f_pmh_seq,   tvb(off, 1))

    local iface = tvb(off + 1, 1):uint()
    local prim  = tvb(off + 2, 1):uint()
    pmh:add(f_pmh_iface, tvb(off + 1, 1))
    local prim_item = pmh:add(f_pmh_prim, tvb(off + 2, 1))
    local pname = prim_name(iface, prim)
    if pname then
        prim_item:append_text(string.format(" (%s)", pname))
        pmh:add(f_pmh_prim_name, tvb(off + 2, 1), pname):set_generated()
    end

    pmh:add(f_pmh_dest,  tvb(off + 3, 1))
    pmh:add(f_pmh_src,   tvb(off + 4, 1))

    if plen > 5 then
        subtree:add(f_pmh_data, tvb(off + 5, plen - 5))
    end

    local iface_label = iface_names[iface] or string.format("iface=0x%02x", iface)
    local prim_label  = pname or string.format("prim=0x%02x", prim)
    return string.format("%s %s seq=%d", iface_label, prim_label, seq)
end

function dpl.dissector(tvb, pinfo, tree)
    local ok, plen, expected_xor, actual_xor, eom = validate(tvb)
    if not ok then return 0 end

    pinfo.cols.protocol = "DPL"

    local subtree = tree:add(dpl, tvb(), "DPL")
    subtree:add(f_stx, tvb(0, 1))
    subtree:add(f_len, tvb(1, 1))

    local stx = tvb(0, 1):uint()
    local info = string.format("stx=0x%02x len=%d", stx, plen)

    if plen > 0 then
        local payload_tvb = tvb(2, plen)
        subtree:add(f_payload, payload_tvb)

        if stx == 0x05 then
            local op = tvb(2, 1):uint()
            subtree:add(f_fw_opcode, tvb(2, 1))
            info = string.format("stx=0x%02x fw_op=%s len=%d",
                stx, fw_opcode_names[op] or string.format("0x%02x", op), plen)
        elseif is_ip_stx(stx) then
            if plen >= 5 then
                local pmh_info = dissect_pmh(tvb, 2, plen, subtree)
                info = string.format("%s %s", stx_names[stx] or string.format("0x%02x", stx), pmh_info)
            else
                subtree:add_proto_expert_info(ef_short_ip)
            end
        end
    end

    local xor_item = subtree:add(f_xor, tvb(2 + plen, 1))
    subtree:add(f_xor_ok, expected_xor == actual_xor):set_generated()
    if expected_xor ~= actual_xor then
        xor_item:add_proto_expert_info(ef_bad_xor,
            string.format("expected 0x%02x, got 0x%02x", expected_xor, actual_xor))
    end

    local eom_item = subtree:add(f_eom, tvb(tvb:len() - 1, 1))
    if eom ~= 0x03 then
        eom_item:add_proto_expert_info(ef_bad_eom)
    end

    pinfo.cols.info = info
    return tvb:len()
end

local function dpl_heur(tvb, pinfo, tree)
    local ok, _, expected_xor, actual_xor, eom = validate(tvb)
    if not ok then return false end
    if eom ~= 0x03 then return false end
    if expected_xor ~= actual_xor then return false end
    local stx = tvb(0, 1):uint()
    if stx_names[stx] == nil then return false end
    dpl.dissector(tvb, pinfo, tree)
    return true
end

dpl:register_heuristic("tcp", dpl_heur)
dpl:register_heuristic("udp", dpl_heur)
dpl:register_heuristic("usb.bulk", dpl_heur)
dpl:register_heuristic("usb.interrupt", dpl_heur)
