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

seq_num = 0
ack_num = 0

def fragment(file_content, fragment_size=FRAGMENT_SIZE):
    frags = []
    content_size = len(file_content)
    for i in range(0, content_size, fragment_size):
        frags.append(file_content[i:i+fragment_size])
    return frags

def check_ack(payload_seg, ack_seg):
    res = (payload_seg.seq_num + 1 == ack_seg.ack_num)
    log(f"ACK matching result: {res}")
    return res

# ============== Name exchange ==============

fname_seg = Segment(seq_num, ack_num, file_name)
fname_bytes = fname_seg.to_bytes()

while True:
    try:
        sock.sendto(fname_bytes, server_addr)
        log(f"OUT: {fname_seg}")
        data, addr = sock.recvfrom(BUFFER_SIZE)
        ack_seg = Segment.to_segment(data)
        log(f"IN: {ack_seg}")
        check_ack(fname_seg, ack_seg)
        break
    except KeyboardInterrupt:
        raise SystemExit
    except timeout:
        log("Fname ACK not received in time, resending...")

# =========== Content transmission ===========

file_chunks = fragment(file_content)
window_size = 5
base = 0  # Base of the sending window
next_seq_num = 0  # Next sequence number to send
pending = {}  # Track sent but unacknowledged segments


while base < len(file_chunks):
    # Send segments while window is not full
    while next_seq_num < base + window_size and next_seq_num < len(file_chunks):
        # Create segment
        seg = Segment(next_seq_num, 0, file_chunks[next_seq_num])
        seg_bytes = seg.to_bytes()
        
        # Send segment
        sock.sendto(seg_bytes, server_addr)
        log(f"Sending segment: {seg}")
        
        # Track pending segments
        pending[next_seq_num] = (seg, time.time())
        next_seq_num += 1
    
    # Wait for acknowledgments
    try:
        ack_bytes, _ = sock.recvfrom(BUFFER_SIZE)
        ack_seg = Segment.to_segment(ack_bytes)
        log(f"Received ACK: {ack_seg}")
        
        # Slide window forward
        if ack_seg.ack_num in pending:
            del pending[ack_seg.ack_num - 1]
            base = ack_seg.ack_num
    
    except timeout:
        # Retransmit unacknowledged segments
        current_time = time.time()
        for seq_num, (seg, send_time) in list(pending.items()):
            if current_time - send_time > 1.0:  # 1-second timeout
                log(f"Retransmitting segment: {seg}")
                sock.sendto(seg.to_bytes(), server_addr)
                pending[seq_num] = (seg, time.time())
    
    except KeyboardInterrupt:
        raise SystemExit