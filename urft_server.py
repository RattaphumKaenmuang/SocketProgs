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
        sock.close()
        raise SystemExit
    
    except timeout:
        log("Waiting for filename...")

    except ConnectionResetError:
        log("Client closed its socket for some reasons, terminating...")
        sock.close()
        raise SystemExit

# =========== Content transmission ===========
log("Receiving content...")
transaction_start = time.time()
file_name = fname_seg.payload.decode()
file_path = os.path.join(OUTPUT_PATH, file_name)
output_file = open(file_path, 'wb')
received_segments = {}
seq_freq = {}

# Continue sequence numbering from filename exchange
expected_seq_num = fname_seg.seq_num + len(fname_seg.payload)
consecutive_timeouts = 0
server_seq_num = 0  # For server-initiated segments

while True:
    try:
        data, client_addr = sock.recvfrom(BUFFER_SIZE)
        consecutive_timeouts = 0
        seg = Segment.to_segment(data)
        log(f"Received segment: {seg}")
        
        if seg.seq_num in seq_freq:
            seq_freq[seg.seq_num] += 1
        else:
            seq_freq[seg.seq_num] = 1

        # Check for FIN segment
        if seg.payload == b'FIN':
            log("Received FIN segment, preparing to end transfer")
            # Store the received FIN segment for later use
            client_fin_seg = seg
            break
        
        # In-order segment
        if seg.seq_num == expected_seq_num:
            output_file.write(seg.payload)
            expected_seq_num += len(seg.payload)
            send_ack(expected_seq_num)
            
            # Something buffered might be in-order now
            while expected_seq_num in received_segments:
                next_seg = received_segments.pop(expected_seq_num)
                output_file.write(next_seg.payload)
                expected_seq_num += len(next_seg.payload)
                send_ack(expected_seq_num)
        
        # Out of order (Later packets arriving before it should)
        elif seg.seq_num > expected_seq_num:
            received_segments[seg.seq_num] = seg
            log(f"Buffered out-of-order segment: seqNum = {seg.seq_num}")
            send_ack(expected_seq_num)  # Send ACK for what we expect next

        # Possible ACK loss
        elif seg.seq_num in seq_freq and seq_freq[seg.seq_num] >= MAX_ACK_RETRIES:
            log("Outdated segment detected, possible ACK loss, retransmitting...")
            send_ack(expected_seq_num)
            del seq_freq[seg.seq_num]
        else:
            # Possible duplicate
            send_ack(expected_seq_num)
    
    except timeout:
        consecutive_timeouts += 1
        log(f"Timeout {consecutive_timeouts}, last expected seqNum = {expected_seq_num}")
    
    except KeyboardInterrupt:
        sock.close()
        raise SystemExit
    
    except ConnectionResetError:
        log("Client closed its socket for some reasons, terminating...")
        sock.close()
        raise SystemExit

# =========== Ending Transaction - Two-sided FIN exchange ===========

# First, acknowledge client's FIN
output_file.close()
log("File reception complete, closing file")

fin_ack_seq_num = server_seq_num
fin_ack = Segment(fin_ack_seq_num, client_fin_seg.seq_num + len(client_fin_seg.payload), b'')
sock.sendto(fin_ack.to_bytes(), client_addr)
log(f"Sent ACK for client FIN: {fin_ack}")

# Now send server's FIN
server_fin = Segment(fin_ack_seq_num + len(fin_ack.payload), client_fin_seg.seq_num + len(client_fin_seg.payload), b'FIN')
server_fin_acked = False
max_retries = 5
retry_count = 0

while not server_fin_acked and retry_count < max_retries:
    try:
        # Send server's FIN
        sock.sendto(server_fin.to_bytes(), client_addr)
        log(f"Sent server FIN: {server_fin}")
        
        # Wait for ACK
        data, _ = sock.recvfrom(BUFFER_SIZE)
        client_seg = Segment.to_segment(data)
        log(f"Received from client: {client_seg}")
        
        # Check if it's an ACK for our FIN
        expected_ack = server_fin.seq_num + len(server_fin.payload)
        if client_seg.ack_num == expected_ack and client_seg.payload == b'ACK':
            server_fin_acked = True
            log("Server FIN has been acknowledged, closing connection")
            break
        elif client_seg.payload == b'FIN':
            # Client retransmitted its FIN, acknowledge it again
            sock.sendto(fin_ack.to_bytes(), client_addr)
            log(f"Re-sent ACK for client FIN: {fin_ack}")
        
        retry_count += 1
        
    except timeout:
        log(f"Timeout waiting for FIN ACK (attempt {retry_count+1}/{max_retries})")
        retry_count += 1
    
    except KeyboardInterrupt:
        raise SystemExit
    
    except ConnectionResetError:
        log("Client closed its socket for some reasons, terminating...")
        raise SystemExit

print(f"File transfer complete. Saved as {file_name}")
transaction_end = time.time()
print(f"Time elapsed: {transaction_end - transaction_start}s")

with open(file_path, 'rb') as f:
    file_content = f.read()
print(f"md5sum: {hashlib.md5(file_content).digest().hex()}")