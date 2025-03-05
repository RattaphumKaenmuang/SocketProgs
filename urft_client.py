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
    # Expect the ACK number to be the next byte after the payload
    expected_ack = payload_seg.seq_num + len(payload_seg.payload)
    res = (ack_seg.ack_num == expected_ack)
    log(f"ACK matching: expected {expected_ack}, received {ack_seg.ack_num}, result: {res}")
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
        if check_ack(fname_seg, ack_seg):
            break
    except KeyboardInterrupt:
        raise SystemExit
    except timeout:
        log("Fname ACK not received in time, resending...")

# =========== Content transmission ===========

file_chunks = fragment(file_content)
window_size = 35
base = 0  # Base of the sending window
next_seq_num = 0  # Next sequence number to send
current_seq_num = 0  # Current byte offset
expected_ack = 0  # Next expected acknowledgment
pending = {}  # Track sent but unacknowledged segments
total_chunks = len(file_chunks)

while base < total_chunks:
    # Send segments while window is not full
    while next_seq_num < base + window_size and next_seq_num < total_chunks:
        # Create segment with current sequence number
        payload = file_chunks[next_seq_num]
        seg = Segment(current_seq_num, expected_ack, payload)
        seg_bytes = seg.to_bytes()
        
        # Send segment
        sock.sendto(seg_bytes, server_addr)
        log(f"Sending segment: {seg}")
        
        # Track pending segments
        pending[current_seq_num] = (seg, time.time())
        
        # Update sequence numbers
        current_seq_num += len(payload)
        next_seq_num += 1
    
    # Wait for acknowledgments
    try:
        ack_bytes, _ = sock.recvfrom(BUFFER_SIZE)
        ack_seg = Segment.to_segment(ack_bytes)
        log(f"Received ACK: {ack_seg}")
        
        # Slide window forward if we receive a new acknowledgment
        if ack_seg.ack_num > expected_ack:
            # Remove acknowledged segments from pending
            for seq_num in list(pending.keys()):
                if seq_num < ack_seg.ack_num:
                    del pending[seq_num]
            
            # Update base and expected acknowledgment
            base = next((i for i, chunk in enumerate(file_chunks) 
                         if sum(len(c) for c in file_chunks[:i]) >= ack_seg.ack_num), 
                        total_chunks)
            expected_ack = ack_seg.ack_num
    
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

# =========== Ending Transaction ===========

fin_seg = Segment(current_seq_num, expected_ack, b'FIN')
fin_bytes = fin_seg.to_bytes()

while True:
    try:
        sock.sendto(fin_bytes, server_addr)
        log(f"Sending FIN: {fin_seg}")
        data, addr = sock.recvfrom(BUFFER_SIZE)
        fin_ack_seg = Segment.to_segment(data)
        log(f"Received FIN_ACK: {fin_ack_seg}")
        if fin_ack_seg.payload == b'FIN_ACK':
            log(f"Correct FIN_ACK, terminating...")
            break
    except timeout:
        log("FIN_ACK not received in time, resending...")
    except KeyboardInterrupt:
        raise SystemExit

log("File transfer Completed.")