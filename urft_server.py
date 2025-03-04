from sys import argv
from socket import *
from classes import *
from config import *
import os
import time

server_ip = argv[1]
server_port = int(argv[2])
server_addr = (server_ip, server_port)
client_addr = None

sock = socket(AF_INET, SOCK_DGRAM)
sock.settimeout(1)
sock.bind(server_addr)

seq_num = 0
ack_num = 0

log(f"Waiting for connection at {server_addr}...")

def ack_segment(segment):
    global seq_num
    seq_num += 1
    ack_seg = Segment(seq_num, segment.seq_num+1)
    log(f"OUT: {ack_seg}")
    ack_bytes = ack_seg.to_bytes()
    sock.sendto(ack_bytes, client_addr)

while True:
    try:
        data, client_addr = sock.recvfrom(BUFFER_SIZE)
        fname_seg = Segment.to_segment(data)
        log(f"IN: {fname_seg}")
        log(f"File name: {fname_seg.payload.decode()}")
        ack_segment(fname_seg)
    except KeyboardInterrupt:
        raise SystemExit
    except timeout:
        log("BRO WHEN ARE YOU GONNA TALK")