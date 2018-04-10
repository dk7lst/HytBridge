-- Kommunikation zwischen Hytera IP-Dispatch-Software und Repeater analysieren
-- Zur Installation nach C:\Users\USERNAME\AppData\Roaming\Wireshark\plugins kopieren. Ordner muss ggf. angelegt werden wenn er noch nicht exisitert.
-- (Defaultpfad, siehe Hilfe -> Über Wireshark -> Ordner -> Personal Plugins)
-- Anschließend Plugins neu laden: "Analyse" -> "Lua Plugins neu laden" (Shortcut: STRG+SHIFT+L)

-- URLs:
-- https://wiki.wireshark.org/LuaAPI
-- https://wiki.wireshark.org/Lua/Dissectors

-- Neue Protokolle anlegen:
HyteraRRS = Proto("HyteraRRS", "Hytera Radio Registration Service")
HyteraLP = Proto("HyteraLP", "Hytera Location Protocol")
HyteraTP = Proto("HyteraTP", "Hytera Telemetry Protocol")
HyteraTMP = Proto("HyteraTMP", "Hytera Text Message Protocol")
HyteraRCP = Proto("HyteraRCP", "Hytera Radio Control Protocol")
HyteraSDM = Proto("HyteraSDM", "Hytera Self-Defined Message")
HyteraRTP = Proto("HyteraRTP", "Hytera RTP Audio")

-- Felder von anderen Protokollschichten holen:
UDP_Port = Field.new("udp.dstport")
RTP_Payload = Field.new("rtp.payload")

-- Funktion zur Analyse der Daten
--function trivial_proto.dissector(buffer, pinfo, tree)
--    pinfo.cols.protocol = "TRIVIAL"
--    local subtree = tree:add(trivial_proto,buffer(),"Trivial Protocol Data")
--    subtree:add(buffer(0,2),"The first two bytes: " .. buffer(0,2):uint())
--    subtree = subtree:add(buffer(2,2),"The next two bytes")
--    subtree:add(buffer(2,1),"The 3rd byte: " .. buffer(2,1):uint())
--    subtree:add(buffer(3,1),"The 4th byte: " .. buffer(3,1):uint())
--end

-- Prüfen, ob das Paket mit einer Hytera-Signatur beginnt:
function hasHyteraMagicNumber(buffer)
  return tostring(buffer(0, 3)) == "324200"
end

-- "Rückwärts" kodierte IDs richtigrum drehen:
function reverseID(id)
  -- Lua 5.2 ist bei Logik-Operationen noch ein wenig umständlicher als 5.3.
  return bit32.bor(bit32.bor(bit32.lshift(bit32.extract(id, 0, 8), 16), bit32.lshift(bit32.extract(id, 8, 8), 8)), bit32.extract(id, 16, 8))
end

function decodeCallType(ct)
  if ct == 0 then
    return "Pvt"
  elseif ct == 1 then
    return "Grp"
  elseif ct == 2 then
    return "All"
  end
  return "Unknown" .. "(" .. ct .. ")"
end

-- Protokolle sind alle recht ähnlich, daher erstmal einen Dissector für alle probieren:
function HyteraDissector(protname, prot, buffer, pinfo, tree)
  -- Protokollnamen setzen:
  pinfo.cols.protocol = protname .. " [TS" .. (2 - UDP_Port().value % 2) .. "]"

  -- Baum aufbauen:
  local subtree = tree:add(prot, buffer(), pinfo.cols.protocol)
  subtree:add(buffer(0, 3), "Signature: " .. buffer(0, 3):uint() .. " (valid=" .. tostring(hasHyteraMagicNumber(buffer)) .. ")")

  local PacketType = buffer(3, 1):uint()
  local PacketTypeStr
  if PacketType == 0x20 then
    PacketTypeStr = "QSO-Data"
  elseif PacketType == 1 then
    PacketTypeStr = "ACK"
  elseif PacketType == 2 then
    PacketTypeStr = "Idle-Keep-Alive?"
  elseif PacketType == 5 then
    PacketTypeStr = "Connection Start-Up?"
  elseif PacketType == 0x24 then
    PacketTypeStr = "No PC connected?"
  else
    PacketTypeStr = "CMD" .. string.format("#%02X", PacketType)
  end
  subtree:add(buffer(3, 1), "Packet Type: " .. PacketTypeStr .. " (" .. string.format("0x%02X", PacketType) .. ")")

  --subtree:add(buffer(4, 1), "?: " .. buffer(4, 1):uint())
  subtree:add(buffer(5, 1), "Sequence-Counter: " .. buffer(5, 1):uint())
  if buffer:len() == 38 then
    local RptId = buffer(9, 3):uint()
    local CT = decodeCallType(buffer(26, 1):uint())
    local DstId = reverseID(buffer(28, 3):uint())
    local SrcId = reverseID(buffer(32, 3):uint())
    subtree:add(buffer(9, 3), "Repeater-ID: " .. RptId)
    subtree:add(buffer(26, 1), "Call-Type: " .. CT)
    subtree:add(buffer(28, 3), "Destination-ID: " .. DstId)
    subtree:add(buffer(32, 3), "Source-ID: " .. SrcId)
    PacketTypeStr = PacketTypeStr .. " (" .. CT .. "-call from " .. SrcId .. " via " .. RptId .. " to " .. DstId .. ")"
  end

  pinfo.cols.info = PacketTypeStr .. " Len: " .. tostring(buffer:len())  
end

function HyteraRRS.dissector(buffer, pinfo, tree)
  HyteraDissector("Hytera Radio Registration", HyteraRRS, buffer, pinfo, tree)
end

function HyteraLP.dissector(buffer, pinfo, tree)
  HyteraDissector("Hytera Location", HyteraLP, buffer, pinfo, tree)
end

function HyteraTP.dissector(buffer, pinfo, tree)
  HyteraDissector("Hytera Telemetry", HyteraTP, buffer, pinfo, tree)
end

function HyteraTMP.dissector(buffer, pinfo, tree)
  HyteraDissector("Hytera Text-Message", HyteraTMP, buffer, pinfo, tree)
end

function HyteraRCP.dissector(buffer, pinfo, tree)
  HyteraDissector("Hytera Radio Control", HyteraRCP, buffer, pinfo, tree)
end

function HyteraSDM.dissector(buffer, pinfo, tree)
  HyteraDissector("Hytera Self-Defined Message", HyteraSDM, buffer, pinfo, tree)
end

function HyteraRTP.dissector(buffer, pinfo, tree)
  if hasHyteraMagicNumber(buffer) then
    -- Hytera-Signatur gefunden, also selber interpretieren:
    HyteraDissector("", HyteraRCP, buffer, pinfo, tree)
    pinfo.cols.protocol = "Hytera Audio (Control)"
  else
    -- Ist wohl echtes RTP, daher bei Wireshark mitgelieferten RTP-Dissector aufrufen:
    Dissector.get("rtp"):call(buffer, pinfo, tree)
    pinfo.cols.protocol = "Hytera Audio (RTP)"
    if string.find(tostring(RTP_Payload().value), "[^F]") == nil then -- Enthält RTP-Payload was anderes als 0xFF ?
      pinfo.cols.info = "Empty RTP"
    else
      pinfo.cols.info = "Audio RTP: " .. tostring(pinfo.cols.info)
    end
  end

  -- TS anhängen:
  if UDP_Port().value == 30012 then
    pinfo.cols.protocol = tostring(pinfo.cols.protocol) .. " [TS1]"
  elseif UDP_Port().value == 30014 then
    pinfo.cols.protocol = tostring(pinfo.cols.protocol) .. " [TS2]"
  end
end

-- Protokolle für die entsprechenden UDP-Ports eintragen.
-- Der erste Port ist vermutlich für TS1, der zweite für TS2.
udp_table = DissectorTable.get("udp.port")
udp_table:add(30001, HyteraRRS)
udp_table:add(30002, HyteraRRS)
udp_table:add(30003, HyteraLP)
udp_table:add(30004, HyteraLP)
udp_table:add(30005, HyteraTP)
udp_table:add(30006, HyteraTP)
udp_table:add(30007, HyteraTMP)
udp_table:add(30008, HyteraTMP)
udp_table:add(30009, HyteraRCP)
udp_table:add(30010, HyteraRCP)
udp_table:add(3017, HyteraSDM)
udp_table:add(3018, HyteraSDM)
udp_table:add(30012, HyteraRTP)
udp_table:add(30014, HyteraRTP)
