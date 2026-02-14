# tests/test_meshtastic_handler.py

import unittest
import logging
import time
import json
from unittest.mock import MagicMock, patch, PropertyMock

# Add src to sys.path to allow importing avsip package
import sys
import os
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
src_path = os.path.join(project_root, 'src')
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from avsip.meshtastic_handler import MeshtasticHandler # type: ignore
import meshtastic # For meshtastic.util.Timeout and (possibly) MAX_PAYLOAD_BYTES
# Backwards-compatible fallbacks for meshtastic API differences across versions
MeshtasticException = getattr(meshtastic.util, 'MeshtasticException', Exception)
MESHTASTIC_MAX_PAYLOAD = getattr(meshtastic, 'MAX_PAYLOAD_BYTES', 237)
# Some meshtastic versions expose Timeout as a plain type (not an Exception subclass).
# Use a test-friendly Exception class for mock side_effects when needed.
TestTimeout = getattr(meshtastic.util, 'Timeout', Exception)
if not issubclass(TestTimeout, BaseException):
    TestTimeout = Exception

# Suppress logging during tests
logging.disable(logging.CRITICAL)

class MockMeshtasticUser:
    def __init__(self, user_id_str):
        self.id = user_id_str

class MockMeshtasticMyInfo:
    def __init__(self, node_num, user_id_str=None):
        self.my_node_num = node_num
        if user_id_str:
            self.user = MockMeshtasticUser(user_id_str)
        else:
            # Simulate case where user object or user.id might be missing initially
            self.user = None # Or MockMeshtasticUser(None) if user always exists

class MockMeshtasticNodeRecordPosition:
    def __init__(self, lat, lon, alt, speed, course, sats, precision_bits, ts):
        self.record = {
            'position': {
                'latitude': lat,
                'longitude': lon,
                'altitude': alt,
                'speed': speed,
                'heading': course, # Meshtastic uses 'heading' for course
                'satsInView': sats, # Older field name
                'precisionBits': precision_bits,
                'time': ts, # GPS timestamp
                'latitudeI': int(lat * 10**7) if lat is not None else 0, # Simulate internal integer representation
                'longitudeI': int(lon * 10**7) if lon is not None else 0
            }
        }

class MockMeshtasticNode:
     def __init__(self, position_record=None):
        if position_record:
            self.record = position_record.record
        else:
            self.record = {}


class TestMeshtasticHandler(unittest.TestCase):

    def tearDown(self):
        logging.disable(logging.NOTSET) # Re-enable logging

    @patch('meshtastic.serial_interface.SerialInterface')
    def test_connect_success_with_user_id(self, MockSerialInterface):
        """Test successful connection when device provides user.id."""
        mock_my_info = MockMeshtasticMyInfo(node_num=12345678, user_id_str="!testuserid")
        
        mock_interface_instance = MockSerialInterface.return_value
        type(mock_interface_instance).myInfo = PropertyMock(return_value=mock_my_info) # Use PropertyMock for attributes

        config = {"enabled": True, "device_port": "/dev/ttyFAKE", "connection_timeout_seconds": 1}
        handler = MeshtasticHandler(config)

        self.assertTrue(handler.is_connected)
        self.assertEqual(handler.get_device_id(), "!testuserid")
        self.assertEqual(handler.get_node_num(), 12345678)
        MockSerialInterface.assert_called_once_with(devPath="/dev/ttyFAKE")
        mock_interface_instance.close.assert_not_called() # Not closed during successful init

    @patch('meshtastic.serial_interface.SerialInterface')
    def test_connect_success_without_user_id(self, MockSerialInterface):
        """Test successful connection, deriving ID from node_num if user.id is missing."""
        mock_my_info = MockMeshtasticMyInfo(node_num=0x075BCD15) # 123456789 in decimal
        
        mock_interface_instance = MockSerialInterface.return_value
        type(mock_interface_instance).myInfo = PropertyMock(return_value=mock_my_info)

        config = {"enabled": True, "device_port": None, "connection_timeout_seconds": 1} # Auto-detect port
        handler = MeshtasticHandler(config)

        self.assertTrue(handler.is_connected)
        self.assertEqual(handler.get_device_id(), "!075bcd15") # Hex representation of node_num
        self.assertEqual(handler.get_node_num(), 0x075BCD15)
        MockSerialInterface.assert_called_once_with() # Called with no args for auto-detect
    
    @patch('meshtastic.serial_interface.SerialInterface')
    def test_connect_timeout(self, MockSerialInterface):
        """Test connection timeout if myInfo is not available."""
        mock_interface_instance = MockSerialInterface.return_value
        # Simulate myInfo never becoming available
        type(mock_interface_instance).myInfo = PropertyMock(return_value=None) 

        config = {"enabled": True, "device_port": "/dev/ttyFAKE", "connection_timeout_seconds": 0.1}
        
        logging.disable(logging.NOTSET) # Enable logging to check for error messages
        with self.assertLogs(level='ERROR') as cm:
            handler = MeshtasticHandler(config)
        logging.disable(logging.CRITICAL)

        self.assertFalse(handler.is_connected)
        self.assertIsNone(handler.get_device_id())
        self.assertTrue(any("Failed to get node info" in log_msg for log_msg in cm.output))
        mock_interface_instance.close.assert_called_once() # Should close if timeout occurs

    @patch('meshtastic.serial_interface.SerialInterface', side_effect=MeshtasticException("Connection failed"))
    def test_connect_meshtastic_exception(self, MockSerialInterface):
        """Test connection failure due to MeshtasticException."""
        config = {"enabled": True, "device_port": "/dev/ttyFAKE"}
        
        logging.disable(logging.NOTSET)
        with self.assertLogs(level='ERROR') as cm:
            handler = MeshtasticHandler(config)
        logging.disable(logging.CRITICAL)

        self.assertFalse(handler.is_connected)
        # Accept either the older Meshtastic-specific message or the generic connection message
        self.assertTrue(any("Connection failed" in log_msg for log_msg in cm.output))

    def test_handler_disabled(self):
        """Test that handler does nothing if disabled in config."""
        config = {"enabled": False}
        handler = MeshtasticHandler(config)
        self.assertFalse(handler.is_connected)
        self.assertIsNone(handler.interface)

    @patch('meshtastic.serial_interface.SerialInterface')
    def test_get_gps_data_success(self, MockSerialInterface):
        """Test successful retrieval of GPS data."""
        mock_my_info = MockMeshtasticMyInfo(node_num=1)
        mock_interface_instance = MockSerialInterface.return_value
        type(mock_interface_instance).myInfo = PropertyMock(return_value=mock_my_info)
        
        ts = int(time.time())
        mock_pos_rec = MockMeshtasticNodeRecordPosition(
            lat=40.123, lon=-74.456, alt=100, speed=10.5, course=90, 
            sats=7, precision_bits=10, ts=ts
        )
        # Mock the localNode property to return a node with position data
        type(mock_interface_instance).localNode = PropertyMock(return_value=MockMeshtasticNode(mock_pos_rec))


        config = {"enabled": True}
        handler = MeshtasticHandler(config)
        self.assertTrue(handler.is_connected) # Assume connection is fine for this test part

        gps_data = handler.get_gps_data()
        self.assertIsNotNone(gps_data)
        self.assertEqual(gps_data["latitude"], 40.123)
        self.assertEqual(gps_data["longitude"], -74.456)
        self.assertEqual(gps_data["altitude"], 100)
        self.assertEqual(gps_data["speed"], 10.5) # m/s
        self.assertEqual(gps_data["course"], 90)
        self.assertEqual(gps_data["satellites"], 7)
        self.assertEqual(gps_data["timestamp_gps"], ts)
        # precisionBits=10 -> (1<<(10/2 -1))/10 = (1<<4)/10 = 16/10 = 1.6
        self.assertAlmostEqual(gps_data["hdop"], 1.6)


    @patch('meshtastic.serial_interface.SerialInterface')
    def test_get_gps_data_no_fix(self, MockSerialInterface):
        """Test GPS data retrieval when there's no valid fix (e.g., time is 0)."""
        mock_my_info = MockMeshtasticMyInfo(node_num=1)
        mock_interface_instance = MockSerialInterface.return_value
        type(mock_interface_instance).myInfo = PropertyMock(return_value=mock_my_info)

        mock_pos_rec_no_fix = MockMeshtasticNodeRecordPosition(
            lat=0.0, lon=0.0, alt=0, speed=0, course=0, sats=0, precision_bits=0, ts=0 # time = 0 indicates no fix
        )
        type(mock_interface_instance).localNode = PropertyMock(return_value=MockMeshtasticNode(mock_pos_rec_no_fix))

        config = {"enabled": True}
        handler = MeshtasticHandler(config)
        self.assertTrue(handler.is_connected)

        gps_data = handler.get_gps_data()
        self.assertIsNone(gps_data, "Should return None if GPS time is 0, indicating no fix.")

    @patch('meshtastic.serial_interface.SerialInterface')
    def test_get_gps_data_no_position_in_node(self, MockSerialInterface):
        """Test GPS data retrieval when node has no 'position' record."""
        mock_my_info = MockMeshtasticMyInfo(node_num=1)
        mock_interface_instance = MockSerialInterface.return_value
        type(mock_interface_instance).myInfo = PropertyMock(return_value=mock_my_info)
        type(mock_interface_instance).localNode = PropertyMock(return_value=MockMeshtasticNode()) # Node with empty record

        config = {"enabled": True}
        handler = MeshtasticHandler(config)
        self.assertTrue(handler.is_connected)
        gps_data = handler.get_gps_data()
        self.assertIsNone(gps_data)


    @patch('meshtastic.serial_interface.SerialInterface')
    def test_get_gps_data_not_connected(self, MockSerialInterface):
        """Test get_gps_data when not connected."""
        # Simulate failed connection by not setting up myInfo on the mock
        mock_interface_instance = MockSerialInterface.return_value
        type(mock_interface_instance).myInfo = PropertyMock(return_value=None)

        config = {"enabled": True, "connection_timeout_seconds": 0.01} # Force quick timeout
        handler = MeshtasticHandler(config)
        self.assertFalse(handler.is_connected)
        
        gps_data = handler.get_gps_data()
        self.assertIsNone(gps_data)


    @patch('meshtastic.serial_interface.SerialInterface')
    def test_send_data_success(self, MockSerialInterface):
        """Test successful data sending."""
        mock_my_info = MockMeshtasticMyInfo(node_num=1)
        mock_interface_instance = MockSerialInterface.return_value
        type(mock_interface_instance).myInfo = PropertyMock(return_value=mock_my_info)
        # Mock the sendData method
        mock_interface_instance.sendData = MagicMock()

        config = {"enabled": True, "data_port_num": 252}
        handler = MeshtasticHandler(config)
        self.assertTrue(handler.is_connected)

        payload = {"key": "value", "num": 123}
        result = handler.send_data(payload)

        self.assertTrue(result)
        expected_bytes = json.dumps(payload).encode('utf-8')
        mock_interface_instance.sendData.assert_called_once_with(
            expected_bytes,
            destinationId="^all",
            portNum=252,
            wantAck=False,
            channelIndex=0
        )

    @patch('meshtastic.serial_interface.SerialInterface')
    def test_send_data_payload_too_large(self, MockSerialInterface):
        """Test sending data when payload exceeds Meshtastic limit."""
        mock_my_info = MockMeshtasticMyInfo(node_num=1)
        mock_interface_instance = MockSerialInterface.return_value
        type(mock_interface_instance).myInfo = PropertyMock(return_value=mock_my_info)
        mock_interface_instance.sendData = MagicMock()

        config = {"enabled": True}
        handler = MeshtasticHandler(config)
        self.assertTrue(handler.is_connected)

        # Create a payload larger than the expected Meshtastic limit
        large_payload = {"data": "A" * (MESHTASTIC_MAX_PAYLOAD + 10)}
        
        logging.disable(logging.NOTSET)
        with self.assertLogs(level='ERROR') as cm:
            result = handler.send_data(large_payload)
        logging.disable(logging.CRITICAL)

        self.assertFalse(result)
        self.assertTrue(any("exceeds Meshtastic limit" in log_msg for log_msg in cm.output))
        mock_interface_instance.sendData.assert_not_called()


    @patch('meshtastic.serial_interface.SerialInterface')
    def test_send_data_not_connected(self, MockSerialInterface):
        """Test send_data when not connected."""
        mock_interface_instance = MockSerialInterface.return_value
        type(mock_interface_instance).myInfo = PropertyMock(return_value=None) # Simulate no connection
        config = {"enabled": True, "connection_timeout_seconds": 0.01}
        handler = MeshtasticHandler(config)
        self.assertFalse(handler.is_connected)

        result = handler.send_data({"key": "value"})
        self.assertFalse(result)

    @patch('meshtastic.serial_interface.SerialInterface')
    def test_send_data_timeout_with_retries(self, MockSerialInterface):
        """Test sendData timeout with retries."""
        mock_my_info = MockMeshtasticMyInfo(node_num=1)
        mock_interface_instance = MockSerialInterface.return_value
        type(mock_interface_instance).myInfo = PropertyMock(return_value=mock_my_info)
        # Simulate sendData raising Timeout on first call, then succeeding
        mock_interface_instance.sendData.side_effect = [
            TestTimeout("Send timed out"), 
            None # Success on second attempt
        ]

        config = {"enabled": True, "send_retries": 1, "send_retry_delay_seconds": 0.01}
        handler = MeshtasticHandler(config)
        self.assertTrue(handler.is_connected)
        
        logging.disable(logging.NOTSET)
        with self.assertLogs(level='WARNING') as cm: # Expect a warning for the timeout
            result = handler.send_data({"key": "value"})
        logging.disable(logging.CRITICAL)

        self.assertTrue(result, "Should succeed after one retry")
        self.assertEqual(mock_interface_instance.sendData.call_count, 2)
        self.assertTrue(any("Timeout sending Meshtastic data (Attempt 1/2)" in log_msg for log_msg in cm.output))


    @patch('meshtastic.serial_interface.SerialInterface')
    def test_send_data_max_retries_exceeded(self, MockSerialInterface):
        """Test sendData failing after max retries."""
        mock_my_info = MockMeshtasticMyInfo(node_num=1)
        mock_interface_instance = MockSerialInterface.return_value
        type(mock_interface_instance).myInfo = PropertyMock(return_value=mock_my_info)
        mock_interface_instance.sendData.side_effect = TestTimeout("Send always times out")

        config = {"enabled": True, "send_retries": 1, "send_retry_delay_seconds": 0.01} # Total 2 attempts
        handler = MeshtasticHandler(config)
        self.assertTrue(handler.is_connected)

        logging.disable(logging.NOTSET)
        with self.assertLogs(level='WARNING') as cm: # Capture warnings and errors
            result = handler.send_data({"key": "value"})
        logging.disable(logging.CRITICAL)

        self.assertFalse(result, "Should fail after all retries")
        self.assertEqual(mock_interface_instance.sendData.call_count, 2) # 1 initial + 1 retry
        self.assertTrue(any("Max retries reached" in log_msg for log_msg in cm.output))
        self.assertTrue(any("Timeout sending Meshtastic data (Attempt 1/2)" in log_msg for log_msg in cm.output))
        self.assertTrue(any("Timeout sending Meshtastic data (Attempt 2/2)" in log_msg for log_msg in cm.output))


    @patch('meshtastic.serial_interface.SerialInterface')
    def test_close_handler(self, MockSerialInterface):
        """Test closing the handler."""
        mock_my_info = MockMeshtasticMyInfo(node_num=1)
        mock_interface_instance = MockSerialInterface.return_value
        type(mock_interface_instance).myInfo = PropertyMock(return_value=mock_my_info)
        mock_interface_instance.close = MagicMock()

        config = {"enabled": True}
        handler = MeshtasticHandler(config)
        self.assertTrue(handler.is_connected)
        
        handler.close()
        self.assertFalse(handler.is_connected)
        self.assertIsNone(handler.interface)
        mock_interface_instance.close.assert_called_once()


if __name__ == '__main__':
    unittest.main(verbosity=2)
