from sys import argv
from socket import *
from classes import *
from config import *
import os
import time

file_path = argv[1]
server_ip = argv[2]
server_port = int(argv[3])
server_addr = (server_ip, server_port)

sock = socket(AF_INET, SOCK_DGRAM)
sock.settimeout(1)

file_name = os.path.basename(file_path)
file_content = open(file_path, 'rb').read()

seqNum = 0
ackNum = 0

fname_seg = Segment(seqNum, ackNum, file_name)
fname_bytes = fname_seg.to_bytes()

while True:
    try:
        sock.sendto(fname_bytes, server_addr)
        log(f"OUT: {fname_seg}")
        data, addr = sock.recvfrom(BUFFER_SIZE)
        ack_seg = Segment.to_segment(data)
        log(f"IN: {ack_seg}")
        break
    except KeyboardInterrupt:
        raise SystemExit
    except timeout:
        log("Fname ACK not received in time, resending...")