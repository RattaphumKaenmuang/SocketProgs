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
    payload_len = len(segment.payload.decode())
    seq_num += payload_len
    ack_seg = Segment(seq_num, segment.seq_num+1)
    ack_bytes = ack_seg.to_bytes()

    sock.sendto(ack_bytes, client_addr)
    log(f"OUT: {ack_seg}")

while True:
    try:
        data, client_addr = sock.recvfrom(BUFFER_SIZE)
        fname_seg = Segment.to_segment(data)
        log(f"IN: {fname_seg}")
        log(f"File name: {fname_seg.payload.decode()}")
        ack_segment(fname_seg)
        break
    except KeyboardInterrupt:
        raise SystemExit
    except timeout:
        log("BRO WHEN ARE YOU GONNA TALK")

received_segments = {}
expected_seq_num = 0
output_file = open(fname_seg.payload.decode(), 'wb')

while True:
    try:
        data, client_addr = sock.recvfrom(BUFFER_SIZE)
        seg = Segment.to_segment(data)
        log(f"Received segment: {seg}")
        
        # Check if segment is the next expected segment
        if seg.seq_num == expected_seq_num:
            # Write segment to file
            output_file.write(seg.payload)
            
            # Send acknowledgment
            ack_seg = Segment(0, seg.seq_num + len(seg.payload))
            sock.sendto(ack_seg.to_bytes(), client_addr)
            
            # Update expected sequence number
            expected_seq_num += len(seg.payload)
        
        elif seg.seq_num > expected_seq_num:
            # Out of order segment, buffer it
            received_segments[seg.seq_num] = seg
        
    except timeout:
        # Handle timeout or completion
        if len(received_segments) == 0:
            break
    
    except KeyboardInterrupt:
        raise SystemExit