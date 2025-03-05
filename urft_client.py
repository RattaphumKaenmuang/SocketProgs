from sys import argv
from socket import *
from classes import *
from config import *
import os
import time
import hashlib

file_path = argv[1]
server_ip = argv[2]
server_port = int(argv[3])
server_addr = (server_ip, server_port)

sock = socket(AF_INET, SOCK_DGRAM)
sock.settimeout(0.75)

file_name = os.path.basename(file_path)
with open(file_path, 'rb') as f:
    file_content = f.read()

seq_num = 0
ack_num = 0

def fragment(content, fragment_size=FRAGMENT_SIZE):
    """Break the file content into a list of chunks."""
    return [content[i:i+fragment_size] for i in range(0, len(content), fragment_size)]

def check_ack(payload_seg, ack_seg):
    """Check if the ack number matches the expected next byte."""
    expected_ack = payload_seg.seq_num + len(payload_seg.payload)
    res = (ack_seg.ack_num == expected_ack)
    log(f"ACK matching: expected {expected_ack}, received {ack_seg.ack_num}, result: {res}")
    return res

def send_and_wait(segment, expect_check_func, expect_msg):
    """Send a segment repeatedly until the expected ACK is received."""
    seg_bytes = segment.to_bytes()
    while True:
        try:
            sock.sendto(seg_bytes, server_addr)
            log(f"OUT: {segment}")
            data, _ = sock.recvfrom(BUFFER_SIZE)
            ack_seg = Segment.to_segment(data)
            log(f"IN: {ack_seg}")
            if expect_check_func(segment, ack_seg):
                return
        except timeout:
            log(f"{expect_msg} not received in time, resending...")

# ============== Name exchange ==============

fname_seg = Segment(seq_num, ack_num, file_name)
send_and_wait(fname_seg, check_ack, "Fname ACK")

# =========== Content transmission ===========

file_chunks = fragment(file_content)
window_size = 35
base = 0             # Index of the first chunk in the window
next_chunk_idx = 0   # Next chunk index to send
current_seq_num = 0  # Byte offset for segments
expected_ack = 0     # Latest ack value
pending = {}         # Map of seq_num to (segment, send_time)
total_chunks = len(file_chunks)

while base < total_chunks:
    # Send segments while window is not full
    while next_chunk_idx < base + window_size and next_chunk_idx < total_chunks:
        payload = file_chunks[next_chunk_idx]
        seg = Segment(current_seq_num, expected_ack, payload)
        sock.sendto(seg.to_bytes(), server_addr)
        log(f"Sending segment: {seg}")
        pending[current_seq_num] = (seg, time.time())
        current_seq_num += len(payload)
        next_chunk_idx += 1
    
    # Wait for acknowledgments and slide window if applicable
    try:
        ack_bytes, _ = sock.recvfrom(BUFFER_SIZE)
        ack_seg = Segment.to_segment(ack_bytes)
        log(f"Received ACK: {ack_seg}")
        if ack_seg.ack_num > expected_ack:
            # Remove acknowledged segments from pending
            for seq in list(pending.keys()):
                if seq < ack_seg.ack_num:
                    del pending[seq]
            # Slide window: determine new base index
            base = next((i for i, chunk in enumerate(file_chunks)
                         if sum(len(c) for c in file_chunks[:i]) >= ack_seg.ack_num),
                        total_chunks)
            expected_ack = ack_seg.ack_num
    except timeout:
        # Retransmit segments that timed out
        current_time = time.time()
        for seq, (seg, send_time) in list(pending.items()):
            if current_time - send_time > 1.0:
                log(f"Retransmitting segment: {seg}")
                sock.sendto(seg.to_bytes(), server_addr)
                pending[seq] = (seg, time.time())
    except KeyboardInterrupt:
        raise SystemExit

# =========== Ending Transaction ===========

fin_seg = Segment(current_seq_num, expected_ack, b'FIN')
fin_bytes = fin_seg.to_bytes()
while True:
    try:
        sock.sendto(fin_bytes, server_addr)
        log(f"Sending FIN: {fin_seg}")
        data, _ = sock.recvfrom(BUFFER_SIZE)
        fin_ack_seg = Segment.to_segment(data)
        log(f"Received FIN_ACK: {fin_ack_seg}")
        if fin_ack_seg.payload == b'FIN_ACK':
            log("Correct FIN_ACK, terminating...")
            break
    except timeout:
        log("FIN_ACK not received in time, resending...")
    except KeyboardInterrupt:
        raise SystemExit

log("File transfer Completed.")
print(f"md5sum: {hashlib.md5(file_content).digest().hex()}")