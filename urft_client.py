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
sock.settimeout(CLIENT_SOCK_TIMEOUT)

file_name = os.path.basename(file_path)
with open(file_path, 'rb') as f:
    file_content = f.read()

seq_num = 0
ack_num = 0

def fragment(content, fragment_size=FRAGMENT_SIZE):
    return [content[i:i+fragment_size] for i in range(0, len(content), fragment_size)]

def check_ack(payload_seg, ack_seg):
    expected_ack = payload_seg.seq_num + len(payload_seg.payload)
    res = (ack_seg.ack_num == expected_ack)
    log(f"ACK matching: expected {expected_ack}, received {ack_seg.ack_num}, result: {res}")
    return res

def send_and_wait(segment, expect_check_func, expect_msg):
    seg_bytes = segment.to_bytes()
    while True:
        try:
            sock.sendto(seg_bytes, server_addr)
            log(f"OUT: {segment}")
            data, _ = sock.recvfrom(BUFFER_SIZE)
            ack_seg = Segment.to_segment(data)
            log(f"IN: {ack_seg}")
            if expect_check_func(segment, ack_seg):
                return ack_seg
        except timeout:
            log(f"{expect_msg} not received in time, resending...")

# ============== Name exchange ==============

fname_seg = Segment(seq_num, ack_num, file_name)
fname_ack = send_and_wait(fname_seg, check_ack, "Fname ACK")

current_seq_num = fname_seg.seq_num + len(fname_seg.payload)
expected_ack = fname_ack.ack_num

# =========== Content transmission ===========

file_chunks = fragment(file_content)
window_size = SENDING_WINDOW_SIZE
base = 0             # Index of the first chunk in the window
next_chunk_idx = 0   # Next chunk index to send
pending = {}         # Map of seq_num to (segment, send_time)
ack_freq = {}
total_chunks = len(file_chunks)
filename_size = len(file_name)
initial_seq = current_seq_num  # Remember the starting sequence number

log(f"Initial seq_num after filename: {current_seq_num}, expected_ack: {expected_ack}")
log(f"Total chunks to send: {total_chunks}")

while base < total_chunks:
    # Send segments while window is not full and there are chunks unsent
    while next_chunk_idx < base + window_size and next_chunk_idx < total_chunks:
        payload = file_chunks[next_chunk_idx]
        seg = Segment(current_seq_num, expected_ack, payload)
        sock.sendto(seg.to_bytes(), server_addr)
        log(f"Sending segment: {seg}")
        pending[current_seq_num] = (seg, time.time())
        current_seq_num += len(payload)
        next_chunk_idx += 1
    
    # Wait for acknowledgments with timeout handling
    try:
        ack_bytes, _ = sock.recvfrom(BUFFER_SIZE)
        ack_seg = Segment.to_segment(ack_bytes)
        log(f"Received ACK: {ack_seg}")
        
        if ack_seg.ack_num in ack_freq:
            ack_freq[ack_seg.ack_num] += 1
        else:
            ack_freq[ack_seg.ack_num] = 1

        for a in ack_freq:
            if ack_freq[a] > MAX_ACK_RETRIES:
                log(f"{a}:{ack_freq[a]}")
        
        if ack_seg.ack_num > expected_ack:
            # Remove acknowledged segments from pending
            acked_seqs = [seq for seq in pending.keys() if seq < ack_seg.ack_num]
            for seq in acked_seqs:
                del pending[seq]
            
            # Update expected_ack
            expected_ack = ack_seg.ack_num
            
            # Calculate how many bytes have been acknowledged since the initial sequence
            bytes_acked = expected_ack - initial_seq
            
            # Calculate new base (first unacknowledged chunk)
            bytes_per_chunk = 0
            new_base = 0
            
            for i, chunk in enumerate(file_chunks):
                if bytes_per_chunk + len(chunk) <= bytes_acked:
                    bytes_per_chunk += len(chunk)
                    new_base = i + 1  # This chunk is fully acknowledged
                else:
                    break
                    
            log(f"Bytes acked: {bytes_acked}, New base calculated: {new_base}")
            if new_base > base:
                base = new_base
                log(f"Window slides to base={base}, next_chunk_idx={next_chunk_idx}")
            
        elif ack_seg.ack_num in ack_freq and ack_freq[ack_seg.ack_num] >= MAX_ACK_RETRIES:
            # Resend the segment corresponding to the outdated ack
            outdated_seq = ack_seg.ack_num
            if outdated_seq in pending:
                outdated_seg, _ = pending[outdated_seq]
                log(f"Outdated ACK received too many times, resending segment with seq={outdated_seq}")
                sock.sendto(outdated_seg.to_bytes(), server_addr)
                pending[outdated_seq] = (outdated_seg, time.time())
                del ack_freq[ack_seg.ack_num]

    except timeout:
        # Check for timed-out segments and retransmit
        current_time = time.time()
        retransmitted = False
        
        for seq, (seg, send_time) in list(pending.items()):
            if current_time - send_time > CLIENT_SEG_TIMEOUT:
                log(f"Timeout detected for segment with seq={seq}, retransmitting")
                sock.sendto(seg.to_bytes(), server_addr)
                # Update send time for the retransmitted segment
                pending[seq] = (seg, time.time())
                retransmitted = True
    
    except KeyboardInterrupt:
        sock.close()
        raise SystemExit

    except ConnectionResetError:
        sock.close()
        log("Server closed its socket for some reasons, terminating...")
        raise SystemExit

# =========== Ending Transaction ===========

# Client initiates FIN
client_fin_seq = current_seq_num
client_fin = Segment(client_fin_seq, expected_ack, b'FIN')
fin_acked = False
server_fin_received = False

while not (fin_acked and server_fin_received):
    try:
        # Send FIN if haven't FIN_ACKED
        if not fin_acked:
            sock.sendto(client_fin.to_bytes(), server_addr)
            log(f"Sending client FIN: {client_fin}")
        
        data, _ = sock.recvfrom(BUFFER_SIZE)
        server_seg = Segment.to_segment(data)
        log(f"Received from server: {server_seg}")
        
        # If received FIN_ACK
        if server_seg.ack_num == client_fin_seq + len(client_fin.payload):
            fin_acked = True
            log("Client FIN has been acknowledged")
        
        # If received FIN
        if server_seg.payload == b'FIN':
            server_fin_received = True
            log("Server FIN received")
            
            # Send ACK for server's FIN
            server_fin_ack = Segment(client_fin_seq + len(client_fin.payload), 
                                     server_seg.seq_num + len(server_seg.payload), 
                                     b'ACK')
            sock.sendto(server_fin_ack.to_bytes(), server_addr)
            log(f"Sent ACK for server FIN: {server_fin_ack}")
            
            if fin_acked:
                log("Two-sided FIN exchange completed.")
                break
                
    except timeout:
        log("Timeout during termination, retrying...")
        
    except KeyboardInterrupt:
        sock.close()
        raise SystemExit

log("File transfer Completed.")
print(f"md5sum: {hashlib.md5(file_content).digest().hex()}")