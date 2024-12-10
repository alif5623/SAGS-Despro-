import serial
import binascii
import time
from dataclasses import dataclass
from typing import Optional, List, Any

class ExpiringDict(dict):
    def __init__(self, default_expiry: int = 3600, *args, **kwargs):
        self.default_expiry = default_expiry
        self._expiry = {}
        super().__init__(*args, **kwargs)
    
    def __setitem__(self, key: str, value: Any, expiry: Optional[int] = None) -> None:
        super().__setitem__(key, value)
        self._expiry[key] = time.time() + (expiry or self.default_expiry)
        self.cleanup() # Auto cleanup expired items
    
    def __getitem__(self, key: str) -> Any:
        expiry = self._expiry.get(key, 0)
        if expiry < time.time():
            del self[key]
            return None
        return super().__getitem__(key)
    
    def __delitem__(self, key: str) -> None:
        super().__delitem__(key)
        self._expiry.pop(key, None)
    
    def set(self, key: str, value: Any, expiry: Optional[int] = None) -> None:
        self.__setitem__(key, value, expiry)
        
    def cleanup(self) -> None:
        now = time.time()
        expired = [k for k, exp in self._expiry.items() if exp < now]
        for k in expired:
            del self[k]

@dataclass
class RFIDTag:
    epc: str
    rssi: int
    timestamp: int
    tlv_data: List[bytes] = None

class RFIDReader:
    def __init__(self, port='/dev/ttyUSB0', baudrate=115200):
        self.serial_port = serial.Serial(port, baudrate)
        self.tag_callback = None
        self.port = port
        self.baudrate = baudrate
        
    def calculate_checksum(self, data: bytes) -> int:
        checksum = 0
        for byte in data:
            checksum += byte
        return (~checksum + 1) & 0xFF

    def start_serial(self):
        self.serial_port = serial.Serial(self.port, self.baudrate)
    
    def create_command(self, frame_code: int, parameters: bytes = b'') -> bytes:
        address = b'\x00\x00'  # Default address
        param_length = len(parameters).to_bytes(2, 'big')
        
        frame = b'RF' + b'\x00' + address + bytes([frame_code]) + param_length + parameters
        checksum = self.calculate_checksum(frame)
        return frame + bytes([checksum])
    
    def parse_tag_notification(self, data: bytes) -> Optional[RFIDTag]:
        try:
            # Skip header(2) + frame_type(1) + address(2) + frame_code(1) + param_length(2)
            tlv_data = data[8:-1]  # Exclude checksum
            
            # Parse TLV structure
            tag = RFIDTag(epc="", rssi=0, timestamp=0, tlv_data=tlv_data)
            i = 0
            while i < len(tlv_data):
                tag_type = tlv_data[i]
                length = tlv_data[i + 1]
                value = tlv_data[i + 2:i + 2 + length]
                
                if tag_type == 0x01:  # EPC
                    tag.epc = binascii.hexlify(value).decode('ascii')
                elif tag_type == 0x05:  # RSSI
                    tag.rssi = int.from_bytes(value, 'big')
                elif tag_type == 0x06:  # Timestamp
                    tag.timestamp = int.from_bytes(value, 'big')
                    
                i += 2 + length
                
            return tag
        except Exception as e:
            print(f"Error parsing tag notification: {e}")
            return None

    def start_inventory(self):
        # Send start inventory command
        command = self.create_command(0x21)
        # command = self.create_command(0x22)
        print(f"start_inventory: {binascii.hexlify(command)}")
        self.serial_port.write(command)
        
    def stop_inventory(self):
        # Send stop inventory command
        command = self.create_command(0x23)
        print(f"stop_inventory: {binascii.hexlify(command)}")
        self.serial_port.write(command)

    def read_response(self):
        # print("read repsonse")
        if self.serial_port.in_waiting >= 8:  # Minimum frame size
            # Read header
            header = self.serial_port.read(2)
            if header == b'RF':
                frame_type = ord(self.serial_port.read(1))
                address = self.serial_port.read(2)
                frame_code = ord(self.serial_port.read(1))
                param_length = int.from_bytes(self.serial_port.read(2), 'big')
                
                # Read parameters and checksum
                remaining_data = self.serial_port.read(param_length + 1)
                
                if frame_type == 0x02 and frame_code == 0x80:  # Tag notification
                    full_frame = header + bytes([frame_type]) + address + bytes([frame_code]) + \
                                param_length.to_bytes(2, 'big') + remaining_data
                    
                    tag = self.parse_tag_notification(full_frame)
                    if tag and self.tag_callback:
                        self.tag_callback(tag)
                        return True

        elif self.serial_port.in_waiting > 0:
            data = self.serial_port.read(self.serial_port.in_waiting)
            print(f"Leftover data: {binascii.hexlify(data)}, length = {len(data)}")
            return True
        
        return False
        
        # print("Exiting read_response loop")

    def on_tag_read(self, callback):
        """Set callback function to be called when a tag is read"""
        self.tag_callback = callback


class TagHandler:
    def __init__(self, lookup, reader: RFIDReader):
        self.lookup = lookup
        self.reader = reader

    def handle_tag(self, tag: RFIDTag):
        """Handle RFID tag detection logic."""
        tag_flag = False
        try:
            # Extract RFID tag number from TLV data
            rfid_tag_number = binascii.hexlify(tag.tlv_data[0:-2]).decode('utf-8').upper()
            rfid_tag_number = rfid_tag_number[8:32]
            self.lookup.cleanup()
            if self.lookup.get(rfid_tag_number):
                print("Tag already detected")
            else:
                print(f"RFID tag: {rfid_tag_number}")
                self.lookup[rfid_tag_number] = rfid_tag_number
                tag_flag = True

            # Reset the reader state
            self.reader.serial_port.cancel_read()
            self.reader.serial_port.reset_input_buffer()
            self.reader.serial_port.reset_output_buffer()
            return tag_flag

        except Exception as e:
            print(f"Error handling tag: {e}")
            return False

if __name__ == "__main__":
    reader = RFIDReader()
    lookup = ExpiringDict(default_expiry=5)

    # Initialize the tag handler
    handler = TagHandler(lookup, reader)

    # Set the callback for tag detection
    reader.on_tag_read(handler.handle_tag)    
    reader.start_inventory()
    while True:
        try:
            reader.read_response()
            time.sleep(0.01)
        except KeyboardInterrupt:
            reader.stop_inventory()
            reader.serial_port.close()
            break
