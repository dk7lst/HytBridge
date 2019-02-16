#!/usr/bin/python3

# Forward TCP/IP ports over DMR-data-links (for use with radios, not repeaters).

# Warning: This is a proof of concept and not yet fully functional!
# TODO:
# - Flow control and sequence numbers
# - Timeouts, resends
# - Implement non-blocking connect()
# - Much more error handling needed
# - Read DMR-ID from local radio and check whether radio is reachable

import socket
import select
import time
import signal
import sys
import random

# DMR subnet prefix. Radios will uses DMR_SUBNET_PREFIX.x.y.z IP addresses. Needs to match codeplug settings!
#DMR_SUBNET_PREFIX = 10

# Local IP address of network adapter connected to DMR radio. Needs to match codeplug settings!
LOCAL_RADIO_NET_IP = "0.0.0.0" #TEST - "192.168.10.2"

# UDP/IP port the radio is listening for data packets. Needs to match codeplug settings!
RADIO_UDP_PORT = 3007

# Client-Mode:
ALLOW_CLIENT_MODE = True
LOCAL_CLIENT_NET_IP = "0.0.0.0" # Local IP address of network adapter connected to bind for client connections. 0.0.0.0 for all interfaces.
LOCAL_TCP_PORT = 8000 # Local TCP-port to listen for connecting clients:

# Server-Mode:
ALLOW_SERVER_MODE = True
DESTINATION_HOST = "127.0.0.1" # Host to forward connections to
DESTINATION_PORT = 80  # Port of host to forward connections to

# Client -> LOCAL_CLIENT_NET_IP:LOCAL_TCP_PORT@PC1 -> DMR -> LOCAL_RADIO_NET_IP:RADIO_UDP_PORT@PC2 -> DESTINATION_HOST:DESTINATION_PORT

# Maximum UDP payload size to send to radio. Bigger values are more efficent
# (faster) but may crash the radio firmware. Decrease when radio reboots while sending.
RADIO_MAX_UDP_PAYLOAD_SIZE = 1024

# Minimum time inverval in seconds between packets send to radio:
RADIO_MIN_TIME_BETWEEN_PACKETS = 0.1

# Max number of unconfirmed packets flying around
# Has to be 1 for now!
TRANSMIT_WINDOW_SIZE = 1

# Time-out in seconds after a resend is triggered when packet is still not confirmed by other station:
PACKET_TIMEOUT = 10

# Max number of times a packet is resent after time-out:
MAX_RETRY_COUNT = 3

# Size of headers:
HEADER_SIZE = 3

# Class for data packets with header to be transmitted over the DMR link:
class DataPacket:
  def __init__(self, data = None):
    if data == None:
      self.header = bytearray(HEADER_SIZE)
      self.data = bytearray()
    else:
      assert len(data) >= HEADER_SIZE
      self.header = bytearray(data[:HEADER_SIZE])
      self.data = bytearray(data[HEADER_SIZE:])
    self.ScheduledTxTime = 0
    self.RetryCount = 0

  def send(self, OtherStationIP):
    return RadioSocket.sendto(self.header + self.data, (OtherStationIP, RADIO_UDP_PORT))

  def getVirtualCircuitId(self):
    assert len(self.header) == HEADER_SIZE
    return (self.header[0] << 8) | self.header[1]

  def setVirtualCircuitId(self, id):
    assert len(self.header) == HEADER_SIZE
    self.header[0] = id >> 8
    self.header[1] = id & 0xFF

  def getSeqNum(self):
    return self.header[2]

  def setSeqNum(self, n):
    self.header[2] = n

  def getData(self):
    return self.data

  def setData(self, data):
    self.data = bytearray(data)

# Class for scheduling when to transmit which packet.
class TxSchedule:
  def __init__(self, OtherStationIP):
    # The list of packets (data with header) to be send over the DMR link which are not yet confirmed by the other station
    # and therefore may needed to be resend:
    self.UnconfirmedPackets = []
    self.OtherStationIP = OtherStationIP

  # Anything in the output queue that is due to be transmitted?
  def hasPacketToSend(self):
    return len(self.UnconfirmedPackets) > 0 and time.time() >= self.UnconfirmedPackets[0].ScheduledTxTime

  # Put a packet in the queue to be send to the radio:
  def queuePacket(self, p):
    self.UnconfirmedPackets.append(p)

  # Send next packet and reschedule:
  def sendNextPacket(self):
    if not self.hasPacketToSend(): return False
    p = self.UnconfirmedPackets[0]
    p.send(self.OtherStationIP)

    p.RetryCount += 1

    # Move packet to end of queue.
    # Packets get rescheduled and resend until reception is confirmed by other station or final timeout.
    self.UnconfirmedPackets = self.UnconfirmedPackets[1:]
    if p.RetryCount <= MAX_RETRY_COUNT:
      p.ScheduledTxTime = time.time() + PACKET_TIMEOUT
      self.UnconfirmedPackets.append(p)
    else:
      print("Packet for virtual circuit", p.getVirtualCircuitId(), "discarded because MAX_RETRY_COUNT reached.")
      disconnectClient(ConList[p.getVirtualCircuitId()].Socket)
    return True

  def countPacketsForVirtualCircuit(self, id):
    n = 0
    for p in self.UnconfirmedPackets:
      if p.getVirtualCircuitId() == id: n += 1
    return n

  def deleteAllPacketsForVirtualCircuit(self, id):
    for p in self.UnconfirmedPackets:
      if p.getVirtualCircuitId() == id: self.UnconfirmedPackets.remove(p)

# Class for handling connections:
class Connection:
  def __init__(self, socket):
    # The socket connected to the other TCP party:
    self.Socket = socket

    # A virtual circuit id to multiplex different TCP data streams over a single DMR radio link.
    # Use random non-zero 16 bit number.
    self.VirtualCircuitId = random.randrange(1, 2**16)

    # The next sequence number to assign for the next packet in this virtual circuit:
    self.NextLocalSeqNum = random.randrange(1, 2**8)

    # The last sequence number of the other party that we received and confirmed:
    self.LastConfirmedRemoteSeqNum = -1

    # The last time we send to the other station concerning this virtual circuit:
    self.LastTxTime = 0

    # The last time we heard from the other station concerning this virtual circuit:
    self.LastRxTime = 0

    # Unsend data bytes (no header required) to the client because the client is busy:
    self.UnsentClientBytes = bytearray()

  # Can this connection accept more client data?
  # We don't accept new data when there already is too much unconfirmed data flying around.
  def canAcceptMoreData(self):
    return Schedule.countPacketsForVirtualCircuit(self.VirtualCircuitId) < TRANSMIT_WINDOW_SIZE

  # Put a packet in the queue to be send to the radio:
  def queueRadioPacket(self, p):
    p.setSeqNum(self.NextLocalSeqNum)
    self.NextLocalSeqNum = (self.NextLocalSeqNum + 1) & 0xFF
    Schedule.queuePacket(p)

  def hasBytesToSendToClient(self):
    return len(self.UnsentClientBytes) > 0

  # Put a packet in the queue to be send to the client:
  def queueClientBytes(self, data):
    self.UnsentClientBytes += data

  # Send bytes to client via given socket and remove from queue:
  def sendBytesToClient(self, s):
    if not self.hasBytesToSendToClient(): return False
    bytes = s.send(self.UnsentClientBytes)
    self.UnsentClientBytes = self.UnsentClientBytes[bytes:]
    return True

  # Add this connection to the connection list:
  def save(self):
    global ConList
    ConList[self.VirtualCircuitId] = self

# Exit on CTRL+C:
def signal_handler(signal, frame):
  global AbortRequest
  if AbortRequest: # Hard exit on second key-press
    print("Killing!")
    sys.exit(1)
  print("Aborting...")
  AbortRequest = True

# Find virtual circuit id by socket:
def getVirtualCircuitIdBySocket(socket):
  global ConList
  for c in ConList:
    o = ConList[c]
    if o.Socket is socket: return o.VirtualCircuitId
  return 0

# Disconnect a client:
def disconnectClient(s):
  global ConList
  c = getVirtualCircuitIdBySocket(s)
  assert c > 0
  print("Closing virtual circuit", c, ".")
  Schedule.deleteAllPacketsForVirtualCircuit(c)
  del ConList[c]
  s.close()

# Process packet from client socket and send with proper header to radio:
def processClientToRadio(s):
  global ConList, RadioSocket
  #try:
  data = s.recv(RADIO_MAX_UDP_PAYLOAD_SIZE - HEADER_SIZE)
  if len(data) == 0:
    # Connection problem - disconnect lost client:
    disconnectClient(s)
    return
  c = getVirtualCircuitIdBySocket(s)
  print("processClientToRadio(): Sending", len(data), "bytes from virtual circuit", c, "to radio")
  p = DataPacket()
  p.setVirtualCircuitId(c)
  p.setData(data)
  ConList[c].queueRadioPacket(p)
  #except: print("Error in ClientToRadio()!")

# Process packet from radio and send to client socket:
def processRadioToClient():
  global ConList, RadioSocket
  #try:
  data = RadioSocket.recv(RADIO_MAX_UDP_PAYLOAD_SIZE)
  if len(data) < HEADER_SIZE: return # Packets without complete header are invalid
  p = DataPacket(data)
  c = p.getVirtualCircuitId()
  if c not in ConList:
    if not ALLOW_SERVER_MODE: return # Connection is unknown but we're not allowed to create it
    print("Forwarding new virtual circuit", c, "to", DESTINATION_HOST, "port", DESTINATION_PORT, "...")
    newsocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    newsocket.connect((DESTINATION_HOST, DESTINATION_PORT))
    newsocket.setblocking(0)
    newcon = Connection(newsocket)
    newcon.VirtualCircuitId = c
    newcon.save()
  print("processRadioToClient(): Sending", len(data) - HEADER_SIZE, "bytes to virtual circuit", c)
  ConList[c].queueClientBytes(p.getData())
  #Schedule.queueAckForPacket(p) !TODO!
  #except: print("Error in RadioToClient()!")

print("HytDataBridge 0.01")
AbortRequest = False
signal.signal(signal.SIGINT, signal_handler)

# Shake it!
random.seed()

# Create and bind radio socket:
RadioSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
RadioSocket.bind((LOCAL_RADIO_NET_IP, RADIO_UDP_PORT))
RadioSocket.setblocking(0)

# Create transmit schedule:
Schedule = TxSchedule("127.0.0.1") # TODO: Compute IP from DMR-ID!

# Create empty dict of open connections indexed by virtual circuit id:
ConList = {}

# Timestamp of last radio tx:
LastRadioTxTime = 0

# Create and bind client socket for connections from clients which like to be forwarded:
if ALLOW_CLIENT_MODE:
  ClientSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
  ClientSocket.bind((LOCAL_CLIENT_NET_IP, LOCAL_TCP_PORT))
  ClientSocket.listen()
  print("Waiting for incoming TCP client connections on port", LOCAL_TCP_PORT,"of interface", LOCAL_CLIENT_NET_IP, "...")

# Main Loop
while not AbortRequest:
  #print("main loop is alive")

  # Create lists of sockets to watch:
  InList = [RadioSocket]
  OutList = []
  if ALLOW_CLIENT_MODE: InList.append(ClientSocket)
  for c in ConList:
    o = ConList[c]
    if o.hasBytesToSendToClient(): OutList.append(o.Socket)
    if o.canAcceptMoreData(): InList.append(o.Socket)

  # When rate limit allows to send new packets to the radio and someone has packets to send:
  if time.time() - LastRadioTxTime >= RADIO_MIN_TIME_BETWEEN_PACKETS and Schedule.hasPacketToSend(): OutList.append(RadioSocket)

  # Wait for activity on sockets or timeout:
  readable, writable, exceptional = select.select(InList, OutList, InList, RADIO_MIN_TIME_BETWEEN_PACKETS)
  if AbortRequest: break

  # Check all sockets ready to be read:
  for s in readable:
    if s is RadioSocket:
      # New data from radio received:
      processRadioToClient()
    elif ALLOW_CLIENT_MODE and s is ClientSocket:
      # New connection request:
      newsocket, addr = s.accept()
      newsocket.setblocking(0)
      newcon = Connection(newsocket)
      print("New client connection from", addr, "creating new virtual circuit", newcon.VirtualCircuitId, "...")
      newcon.save()
    else:
      # Data from TCP client connection received:
      processClientToRadio(s)

  # Check all sockets ready for write:
  for s in writable:
    if s is RadioSocket:
      Schedule.sendNextPacket()
      LastRadioTxTime = time.time()
    else:
      c = getVirtualCircuitIdBySocket(s)
      assert c > 0
      try:
        ConList[c].sendBytesToClient(s)
      except BrokenPipeError:
        print("TCP-connection for virtual circuit", c, "closed by client!")
        disconnectClient(s)

  # Clean up defective sockets:
  for s in exceptional:
    if s is RadioSocket:
      print("FATAL ERROR: radio UDP socket failed!")
      AbortRequest = True
      break
    if ALLOW_CLIENT_MODE and s is ClientSocket:
      print("FATAL ERROR: client listener socket failed!")
      AbortRequest = True
      break
    disconnectClient(s)

print("Exit!")
if ALLOW_CLIENT_MODE: ClientSocket.close()
RadioSocket.close()
sys.exit(0)
