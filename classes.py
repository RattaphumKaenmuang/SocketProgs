import struct
from config import *

def log(txt):
    if DEBUG:
        print(txt)

class Segment:
    segment_header = '!II'
    def __init__(self, seq_num, ack_num, payload=b''):
        self.seq_num = seq_num  # Starting byte of this segment
        self.ack_num = ack_num  # Next expected byte
        
        if not isinstance(payload, bytes):
            payload = payload.encode()
        
        self.payload = payload
    
    def to_bytes(self):
        return struct.pack(Segment.segment_header, self.seq_num, self.ack_num) + self.payload
    
    @staticmethod
    def to_segment(data):
        seq_num, ack_num = struct.unpack(Segment.segment_header, data[:8])
        payload = data[8:]
        return Segment(seq_num, ack_num, payload)
    
    def __str__(self):
        return f"seqNum = {self.seq_num}, ackNum = {self.ack_num}, payload_len = {len(self.payload)}"