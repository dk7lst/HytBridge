#!/usr/bin/python3

# Konvertierung nach Wave: $ sox -r 8000 -t raw -e u-law -c 1 HytBridge.TS1.raw out.wav

import socket
import _thread
import time
import signal
import sys
import audioop
import wave

# IP-Adresse vom Repeater:
#LOCAL_IP = "127.0.0.1"
#RPT_IP = "127.0.0.1"
LOCAL_IP = "192.168.0.115"
RPT_IP = "192.168.0.201"

# UDP-Ports für die Steuerung:
RCP_PORT_TS1 = 30009
RCP_PORT_TS2 = 30010

# UDP-Ports für die Audio-Daten:
RTP_PORT_TS1 = 30012
RTP_PORT_TS2 = 30014

# Bei STRG+C beenden:
def signal_handler(signal, frame):
  print("Abort!")
  sys.exit(0)

  # Klasse, die sich um das Audio (RCP+RTP) für einen Timeslot kümmert.
class AudioSlot:
  def __init__(self, name, RptIP, RCP_Port, RTP_Port):
    # Portnummern merken:
    self.name = name
    self.RptIP = RptIP
    self.RCP_Port = RCP_Port
    self.RTP_Port = RTP_Port

    # Sockets anlegen:
    self.RCP_Sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    self.RTP_Sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    # Sockets an Ports binden:
    self.RCP_Sock.bind((LOCAL_IP, RCP_Port))
    self.RTP_Sock.bind((LOCAL_IP, RTP_Port))
#    try:
    _thread.start_new_thread(self.RCP_Rx_Thread, (name,))
    _thread.start_new_thread(self.RTP_Rx_Thread, (name,))
    _thread.start_new_thread(self.RCP_Tx_Thread, (name,))
    _thread.start_new_thread(self.RTP_Tx_Thread, (name,))
#    except:
#      print("ERROR: Unable to start threads!", name)

  def RCP_Rx_Thread(self, threadName):
    print(threadName, "RCP_Rx_Thread started")
    while True:
      data, addr = self.RCP_Sock.recvfrom(1024)
      print(threadName, "RCP_Rx_Thread: received message:", data)

  def RTP_Rx_Thread(self, threadName):
    print(threadName, "RTP_Rx_Thread started")
    wavefile = wave.open("HytAudioBridge." + threadName + ".wav", 'wb')
    wavefile.setparams((1, 2, 8000, 0, 'NONE', 'not compressed'))
    while True:
      data, addr = self.RTP_Sock.recvfrom(1024)
      #print(threadName, "RTP_Rx_Thread: received message:", data)
      if data[0:2] == bytes.fromhex('9000'):
        wavefile.writeframes(audioop.ulaw2lin(data[28:], 2))

  def RCP_Tx_Thread(self, threadName):
    print(threadName, "RCP_Tx_Thread started")
    WakeCall = bytes.fromhex('324200050000')
    self.RCP_Sock.sendto(WakeCall, (self.RptIP, self.RCP_Port))
    IdleKeepAlive = bytes.fromhex('324200020000')
    while True:
      self.RCP_Sock.sendto(IdleKeepAlive, (self.RptIP, self.RCP_Port))
      time.sleep(2)

  def RTP_Tx_Thread(self, threadName):
    print(threadName, "RTP_Tx_Thread started")
    WakeCall = bytes.fromhex('324200050000')
    self.RTP_Sock.sendto(WakeCall, (self.RptIP, self.RTP_Port))
    IdleKeepAlive = bytes.fromhex('324200020000')
    while True:
      self.RTP_Sock.sendto(IdleKeepAlive, (self.RptIP, self.RTP_Port))
      time.sleep(2)
    
print("HytAudioBridge 0.01")
signal.signal(signal.SIGINT, signal_handler)

AudioSlot1 = AudioSlot("TS1", RPT_IP, RCP_PORT_TS1, RTP_PORT_TS1)
AudioSlot2 = AudioSlot("TS2", RPT_IP, RCP_PORT_TS2, RTP_PORT_TS2)

time.sleep(60)
print("Exit!")
sys.exit(0)
