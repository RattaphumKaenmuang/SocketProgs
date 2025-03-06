from sys import argv
from socket import *
from classes import *
from config import *
import time
import hashlib
import os

server_ip = argv[1]
server_port = int(argv[2])
server_addr = (server_ip, server_port)
client_addr = None

sock = socket(AF_INET, SOCK_DGRAM)
sock.bind(server_addr)
sock.settimeout(SERVER_SOCK_TIMEOUT)

log(f"Waiting for connection at {server_addr}...")

def send_ack(expected_seq_num, payload=b''):
    """Helper to send an ACK segment with a given expected sequence number."""
    ack_seg = Segment(0, expected_seq_num, payload)
    sock.sendto(ack_seg.to_bytes(), client_addr)
    log(f"OUT: {ack_seg}")

# ============== Name exchange ==============

while True:
    try:
        data, client_addr = sock.recvfrom(BUFFER_SIZE)
        fname_seg = Segment.to_segment(data)
        log(f"IN: {fname_seg}")
        log(f"File name: {fname_seg.payload.decode()}")
        send_ack(fname_seg.seq_num + len(fname_seg.payload))
        break
    except KeyboardInterrupt:
        raise SystemExit
    except timeout:
        log("Waiting for filename...")

# =========== Content transmission ===========
log("Receiving content...")
transaction_start = time.time()
file_name = fname_seg.payload.decode()
file_path = os.path.join(OUTPUT_PATH, file_name)
output_file = open(file_path, 'wb')
received_segments = {}
expected_seq_num = 0
consecutive_timeouts = 0

while True:
    try:
        data, client_addr = sock.recvfrom(BUFFER_SIZE)
        consecutive_timeouts = 0
        seg = Segment.to_segment(data)
        log(f"Received segment: {seg}")
        
        # Check for FIN segment
        if seg.payload == b'FIN':
            log("Received FIN segment, preparing to end transfer")
            break
        
        # In-order segment
        if seg.seq_num == expected_seq_num:
            output_file.write(seg.payload)
            expected_seq_num += len(seg.payload)
            send_ack(expected_seq_num)
            
            # Process any buffered segments now in order
            while expected_seq_num in received_segments:
                next_seg = received_segments.pop(expected_seq_num)
                output_file.write(next_seg.payload)
                expected_seq_num += len(next_seg.payload)
                send_ack(expected_seq_num)
        
        # Out-of-order segment: buffer it
        elif seg.seq_num > expected_seq_num:
            received_segments[seg.seq_num] = seg
            log(f"Buffered out-of-order segment: seqNum = {seg.seq_num}")
    
    except timeout:
        consecutive_timeouts += 1
        log(f"Timeout {consecutive_timeouts}, last expected seqNum = {expected_seq_num}")
    
    except KeyboardInterrupt:
        raise SystemExit

# =========== Ending Transaction ===========

# Send FIN_ACK to acknowledge FIN segment
fin_ack_seg = Segment(0, 0, b'FIN_ACK')
sock.sendto(fin_ack_seg.to_bytes(), client_addr)
log(f"Sent FIN_ACK: {fin_ack_seg}")

output_file.close()
print(f"File transfer complete. Saved as {file_name}")
transaction_end = time.time()
print(f"Time elapsed: {transaction_end - transaction_start}s")

with open(file_path, 'rb') as f:
    file_content = f.read()
print(f"md5sum: {hashlib.md5(file_content).digest().hex()}")