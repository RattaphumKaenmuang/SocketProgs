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
    # Calculate the next expected byte based on the payload length
    payload_len = len(segment.payload)
    ack_seg = Segment(0, segment.seq_num + payload_len)
    ack_bytes = ack_seg.to_bytes()

    sock.sendto(ack_bytes, client_addr)
    log(f"OUT: {ack_seg}")

# ============== Name exchange ==============

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
        log("Waiting for filename...")

# =========== Content transmission ===========

filename = fname_seg.payload.decode()
output_file = open(filename, 'wb')
received_segments = {}
expected_seq_num = 0
transfer_complete = False
consecutive_timeouts = 0
max_consecutive_timeouts = 10  # Adjust as needed

while not transfer_complete:
    try:
        # Reset consecutive timeouts when we receive data
        data, client_addr = sock.recvfrom(BUFFER_SIZE)
        consecutive_timeouts = 0
        
        seg = Segment.to_segment(data)
        log(f"Received segment: {seg}")
        
        # Check if segment is a FIN segment
        if seg.payload == b'FIN':
            log("Received FIN segment, preparing to end transfer")
            transfer_complete = True
            break
        
        # Check if segment is the next expected segment
        if seg.seq_num == expected_seq_num:
            # Write segment to file
            output_file.write(seg.payload)
            
            # Update expected sequence number
            expected_seq_num += len(seg.payload)
            
            # Send acknowledgment for next expected byte
            ack_seg = Segment(0, expected_seq_num, b'')
            sock.sendto(ack_seg.to_bytes(), client_addr)
            log(f"Sent ACK: {ack_seg}")
            
            # Check if we have any buffered segments that can now be processed
            while expected_seq_num in received_segments:
                next_seg = received_segments.pop(expected_seq_num)
                output_file.write(next_seg.payload)
                expected_seq_num += len(next_seg.payload)
                
                # Send updated acknowledgment
                ack_seg = Segment(0, expected_seq_num, b'')
                sock.sendto(ack_seg.to_bytes(), client_addr)
                log(f"Sent ACK for buffered segment: {ack_seg}")
        
        elif seg.seq_num > expected_seq_num:
            # Out of order segment, buffer it
            received_segments[seg.seq_num] = seg
            log(f"Buffered out-of-order segment: seqNum = {seg.seq_num}")
        
        # Send acknowledgment for any out-of-order segments
        ack_seg = Segment(0, expected_seq_num, b'')
        sock.sendto(ack_seg.to_bytes(), client_addr)
    
    except timeout:
        consecutive_timeouts += 1
        log(f"Timeout {consecutive_timeouts}, last expected seqNum = {expected_seq_num}")
        
        # If we've had multiple consecutive timeouts, we assume transfer is complete
        if consecutive_timeouts >= max_consecutive_timeouts:
            transfer_complete = True
    
    except KeyboardInterrupt:
        raise SystemExit

# =========== Ending Transaction ===========

# Send FIN_ACK to acknowledge the FIN segment
fin_ack_seg = Segment(0, 0, b'FIN_ACK')
sock.sendto(fin_ack_seg.to_bytes(), client_addr)
log(f"Sent FIN_ACK: {fin_ack_seg}")

# Write any remaining buffered segments to the file
for seq_num in sorted(received_segments):
    seg = received_segments[seq_num]
    output_file.write(seg.payload)
    log(f"Wrote buffered segment to file: seqNum = {seq_num}")
output_file.close()
log(f"File transfer complete. Saved as {filename}")