#!/usr/bin/python3

# Repeater Firmware: A8.05.07.001

import socket
import _thread
import time
import signal
import sys

# IP-Adresse vom Repeater:
#LOCAL_IP = "127.0.0.1"
#RPT_IP = "127.0.0.1"
LOCAL_IP = "192.168.0.115"
RPT_IP = "192.168.0.201"

# UDP ports:
SMS_PORT_TS1 = 30007
SMS_PORT_TS2 = 30008

# Bei STRG+C beenden:
def signal_handler(signal, frame):
  print("Abort!")
  sys.exit(0)

class TextSlot:
  def __init__(self, name, RptIP, SMS_Port):
    # Portnummern merken:
    self.name = name
    self.RptIP = RptIP
    self.SMS_Port = SMS_Port

    # Constants:
    self.WakeCallPacket = bytes.fromhex('324200050000')
    self.IdleKeepAlivePacket = bytes.fromhex('324200020000')

    self.SMS_Seq = 0

    # Socket anlegen:
    self.SMS_Sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    # Socket an Ports binden:
    self.SMS_Sock.bind((LOCAL_IP, SMS_Port))
    _thread.start_new_thread(self.SMS_Rx_Thread, (name,))
    _thread.start_new_thread(self.TxIdleMsgThread, (name,))

  def getNextSMSSeq(self):
    self.SMS_Seq = (self.SMS_Seq + 1) & 0xFF
    return self.SMS_Seq

  def sendACK(self, seq):
    AckPacket = bytearray.fromhex('324200010100')
    AckPacket[5] = seq;
    self.SMS_Sock.sendto(AckPacket, (self.RptIP, self.SMS_Port))

  def SMS_Rx_Thread(self, threadName):
    #print(threadName, "SMS_Rx_Thread started")
    while True:
      data, addr = self.SMS_Sock.recvfrom(1024)
      #print(threadName, "SMS_Rx_Thread: received message:", data)

  def TxIdleMsgThread(self, threadName):
    #print(threadName, "TxIdleMsgThread started")
    self.SMS_Sock.sendto(self.WakeCallPacket, (self.RptIP, self.SMS_Port))
    while True:
      self.SMS_Sock.sendto(self.IdleKeepAlivePacket, (self.RptIP, self.SMS_Port))
      time.sleep(2)

  def sendText(self, SrcId, DstId, text):
    packet = bytearray.fromhex('3242000000040900a1000e300000040a0000000a000000')
    packet[5] = packet[14] = self.getNextSMSSeq()
    packet[10] = 12 + len(text) * 2
    packet[16] = (DstId >> 16) & 0xFF
    packet[17] = (DstId >> 8) & 0xFF
    packet[18] = DstId & 0xFF
    packet[20] = (SrcId >> 16) & 0xFF
    packet[21] = (SrcId >> 8) & 0xFF
    packet[22] = SrcId & 0xFF
    packet += bytes(text, "utf-16le")
    packet.append(0) #ChkSum
    packet.append(3)
    for i in range(0, 256):
      packet[len(packet) - 2] = i
      self.SMS_Sock.sendto(packet, (self.RptIP, self.SMS_Port))
      time.sleep(0.1)

print("HytTextBridge 0.01")
signal.signal(signal.SIGINT, signal_handler)

TextSlot1 = TextSlot("TS1", RPT_IP, SMS_PORT_TS1)
TextSlot2 = TextSlot("TS2", RPT_IP, SMS_PORT_TS2)

print("Waiting...")
time.sleep(5)
print("Sending...")
TextSlot1.sendText(2623305, 2623305, "Dies ist ein wirklich richtig langer Test mit satzzeichen!")
time.sleep(10)
TextSlot1.sendText(123456, 2623266, "Dies ist ein langer Test")

time.sleep(40)

print("Exit!")
sys.exit(0)
