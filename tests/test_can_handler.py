# tests/test_can_handler.py

import unittest
import logging
import time
import threading
from queue import Queue, Empty, Full
from unittest.mock import MagicMock, patch, call

# Add src to sys.path to allow importing avsip package
import sys
import os
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
src_path = os.path.join(project_root, 'src')
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from avsip.can_handler import CANHandler # type: ignore
import can # Import the real library to mock its parts and CanError

# Suppress logging during tests
logging.disable(logging.CRITICAL)

# Helper mock for can.Message
def create_mock_can_message(arb_id: int, data: bytes, timestamp: float = None) -> can.Message:
    """Creates a mock CAN message object."""
    if timestamp is None:
        timestamp = time.time()
    # We can instantiate a real can.Message as it's mostly a data container
    return can.Message(
        arbitration_id=arb_id,
        data=data,
        is_extended_id=False, # Assume standard IDs for tests unless specified
        timestamp=timestamp
    )

class TestCANHandler(unittest.TestCase):

    def setUp(self):
        """Set up for test methods."""
        self.data_queue = Queue(maxsize=10) # Use a small queue for testing full scenario

    def tearDown(self):
        """Re-enable logging after tests."""
        logging.disable(logging.NOTSET)
        # Ensure queue is empty after test if needed
        while not self.data_queue.empty():
            try:
                self.data_queue.get_nowait()
            except Empty:
                break

    # Patch 'can.interface.Bus' in the module where it's used (avsip.can_handler)
    @patch('avsip.can_handler.can.interface.Bus')
    def test_connect_success(self, MockCanBus):
        """Test successful connection and initialization."""
        mock_bus_instance = MockCanBus.return_value
        mock_bus_instance.channel_info = "Mock CAN Interface"

        config = {
            "enabled": True,
            "interface_type": "mockcan",
            "channel": "mock0",
            "bitrate": 500000,
            "message_definitions": [], # No definitions needed for connect test
            "connection_retries": 0
        }
        handler = CANHandler(config, self.data_queue)

        self.assertTrue(handler.is_connected)
        self.assertIsNotNone(handler.bus)
        MockCanBus.assert_called_once_with(bustype="mockcan", channel="mock0", bitrate=500000)
        mock_bus_instance.shutdown.assert_not_called()

    @patch('avsip.can_handler.can.interface.Bus')
    def test_connect_failure_and_retry(self, MockCanBus):
        """Test connection failure with retries."""
        # Simulate connection failing twice, then succeeding
        MockCanBus.side_effect = [
            can.CanError("Connection Error 1"),
            can.CanError("Connection Error 2"),
            MagicMock(channel_info="Successful Mock") # Successful connection mock
        ]

        config = {
            "enabled": True,
            "interface_type": "mockcan",
            "channel": "mock0",
            "bitrate": 500000,
            "message_definitions": [],
            "connection_retries": 2, # Allow 2 retries (total 3 attempts)
            "retry_delay_seconds": 0.01 # Fast retry for test
        }
        
        logging.disable(logging.NOTSET) # Check logs
        with self.assertLogs(level='ERROR') as cm_err: # Expect errors for failed attempts
             with self.assertLogs(level='INFO') as cm_info: # Expect info for retries/success
                 handler = CANHandler(config, self.data_queue)
        logging.disable(logging.CRITICAL)

        self.assertTrue(handler.is_connected)
        self.assertEqual(MockCanBus.call_count, 3)
        self.assertTrue(any("Connection Error 1" in log_msg for log_msg in cm_err.output))
        self.assertTrue(any("Connection Error 2" in log_msg for log_msg in cm_err.output))
        self.assertTrue(any("Retrying CAN connection" in log_msg for log_msg in cm_info.output))
        self.assertTrue(any("Successfully connected to CAN bus" in log_msg for log_msg in cm_info.output))
        # Check shutdown wasn't called on the final successful mock instance
        self.assertFalse(MockCanBus.side_effect[2].shutdown.called)


    @patch('avsip.can_handler.can.interface.Bus')
    def test_connect_failure_max_retries(self, MockCanBus):
        """Test connection failure after exhausting all retries."""
        MockCanBus.side_effect = can.CanError("Persistent Connection Error")

        config = {
            "enabled": True,
            "interface_type": "mockcan",
            "channel": "mock0",
            "bitrate": 500000,
            "message_definitions": [],
            "connection_retries": 1, # Total 2 attempts
            "retry_delay_seconds": 0.01
        }

        logging.disable(logging.NOTSET)
        with self.assertLogs(level='ERROR') as cm:
            handler = CANHandler(config, self.data_queue)
        logging.disable(logging.CRITICAL)

        self.assertFalse(handler.is_connected)
        self.assertIsNone(handler.bus)
        self.assertEqual(MockCanBus.call_count, 2) # Initial + 1 retry
        self.assertTrue(any("Failed to connect to CAN bus after all retries" in log_msg for log_msg in cm.output))


    def test_handler_disabled(self):
        """Test handler initialization when disabled."""
        config = {"enabled": False}
        handler = CANHandler(config, self.data_queue)
        self.assertFalse(handler.is_connected)
        self.assertIsNone(handler.bus)

    def test_parse_message_definitions(self):
        """Test parsing of valid and invalid message definitions."""
        config = {
            "enabled": True,
            "message_definitions": [
                # Valid definition
                {"id": "0x100", "name": "ValidSensor1", "parser": {
                    "type": "simple_scalar", "start_byte": 0, "length_bytes": 1,
                    "scale": 1, "offset": 0, "is_signed": False, "byte_order": "big"}},
                # Missing 'parser'
                {"id": "0x200", "name": "MissingParser"},
                # Invalid ID format
                {"id": "0x30G", "name": "InvalidID", "parser": {}},
                # Invalid parser type
                {"id": "0x400", "name": "InvalidParserType", "parser": {"type": "complex_unsupported"}},
                 # Valid definition 2
                {"id": "0x100", "name": "ValidSensor2", "parser": { # Same ID as first
                    "type": "simple_scalar", "start_byte": 1, "length_bytes": 2,
                    "scale": 0.1, "offset": -5, "is_signed": True, "byte_order": "little"}},
                # Parser config missing keys
                 {"id": "0x500", "name": "IncompleteParser", "parser": {
                    "type": "simple_scalar", "start_byte": 0, "length_bytes": 1,
                    "scale": 1, "offset": 0, "is_signed": False}}, # Missing byte_order
            ]
        }
        # Patch connect to avoid actual connection attempt
        with patch('avsip.can_handler.can.interface.Bus'):
            handler = CANHandler(config, self.data_queue)

        # Check parsed definitions
        self.assertIn(0x100, handler.message_definitions)
        self.assertEqual(len(handler.message_definitions[0x100]), 2) # Two definitions for ID 0x100
        self.assertEqual(handler.message_definitions[0x100][0]['name'], "ValidSensor1")
        self.assertEqual(handler.message_definitions[0x100][1]['name'], "ValidSensor2")

        # Check that invalid definitions were skipped
        self.assertNotIn(0x200, handler.message_definitions)
        self.assertNotIn(0x300, handler.message_definitions) # Invalid ID 0x30G
        self.assertNotIn(0x400, handler.message_definitions)
        self.assertNotIn(0x500, handler.message_definitions)

    @patch('avsip.can_handler.can.interface.Bus')
    def test_parse_can_message_simple_scalar(self, MockCanBus):
        """Test parsing a CAN message with the simple_scalar parser."""
        config = {
            "enabled": True,
            "message_definitions": [
                {"id": "0x1A0", "name": "SteeringAngle", "parser": {
                    "type": "simple_scalar", "start_byte": 2, "length_bytes": 2,
                    "scale": 0.1, "offset": -3276.8, "is_signed": True, "byte_order": "big"}},
                {"id": "0x1A0", "name": "SteeringRate", "parser": {
                    "type": "simple_scalar", "start_byte": 0, "length_bytes": 1,
                    "scale": 0.5, "offset": 0, "is_signed": False, "byte_order": "big"}},
                {"id": "0x2B4", "name": "BrakePressure", "parser": {
                    "type": "simple_scalar", "start_byte": 0, "length_bytes": 1,
                    "scale": 1.5, "offset": 0, "is_signed": False, "byte_order": "big"}}
            ]
        }
        handler = CANHandler(config, self.data_queue) # Assume connection is mocked okay

        # Test message 1 (ID 0x1A0)
        msg1_data = bytes([0x50, 0x00, 0x0C, 0x7B, 0x00, 0x00, 0x00, 0x00]) # Rate=0x50=80, Angle=0x0C7B=3195
        msg1 = create_mock_can_message(0x1A0, msg1_data)
        parsed1 = handler._parse_can_message(msg1)

        self.assertEqual(len(parsed1), 2)
        parsed1_dict = {item['name']: item['value'] for item in parsed1}
        self.assertIn("SteeringAngle", parsed1_dict)
        self.assertAlmostEqual(parsed1_dict["SteeringAngle"], (3195 * 0.1) - 3276.8) # -2957.3
        self.assertIn("SteeringRate", parsed1_dict)
        self.assertAlmostEqual(parsed1_dict["SteeringRate"], 80 * 0.5) # 40.0

        # Test message 2 (ID 0x2B4)
        msg2_data = bytes([0x64, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]) # Pressure=0x64=100
        msg2 = create_mock_can_message(0x2B4, msg2_data)
        parsed2 = handler._parse_can_message(msg2)
        self.assertEqual(len(parsed2), 1)
        self.assertEqual(parsed2[0]['name'], "BrakePressure")
        self.assertAlmostEqual(parsed2[0]['value'], 100 * 1.5) # 150.0

        # Test message 3 (ID not defined)
        msg3 = create_mock_can_message(0x999, b'\x01\x02')
        parsed3 = handler._parse_can_message(msg3)
        self.assertEqual(len(parsed3), 0)

    @patch('avsip.can_handler.can.interface.Bus')
    def test_listener_loop_and_queue(self, MockCanBus):
        """Test the listener loop receiving messages and putting them on the queue."""
        mock_bus_instance = MockCanBus.return_value
        
        # Messages to simulate receiving
        msg1 = create_mock_can_message(0x123, b'\xAA') # Defined
        msg2 = create_mock_can_message(0x456, b'\xBB') # Undefined
        msg3 = create_mock_can_message(0x123, b'\xCC') # Defined again
        # Simulate recv returning these messages then None (timeout) repeatedly
        mock_bus_instance.recv.side_effect = [msg1, msg2, msg3, None, None, None] 

        config = {
            "enabled": True,
            "interface_type": "mockcan", "channel": "mock0", "bitrate": 500000,
            "receive_timeout_seconds": 0.1,
            "message_definitions": [
                {"id": "0x123", "name": "TestData", "parser": {
                    "type": "simple_scalar", "start_byte": 0, "length_bytes": 1,
                    "scale": 1, "offset": 0, "is_signed": False, "byte_order": "big"}}
            ]
        }
        handler = CANHandler(config, self.data_queue)
        self.assertTrue(handler.is_connected)
        
        # Start listener in a separate thread for the test
        handler.start_listener()
        
        # Wait a bit for the listener to process messages
        time.sleep(0.5) 

        # Stop the listener
        handler.stop_listener() 

        # Check the queue content
        items_in_queue = []
        while not self.data_queue.empty():
            items_in_queue.append(self.data_queue.get_nowait())
        
        self.assertEqual(len(items_in_queue), 2) # Should have received msg1 and msg3
        self.assertEqual(items_in_queue[0]['name'], "TestData")
        self.assertEqual(items_in_queue[0]['value'], 0xAA) # 170
        self.assertEqual(items_in_queue[1]['name'], "TestData")
        self.assertEqual(items_in_queue[1]['value'], 0xCC) # 204
        
        # Ensure recv was called multiple times (at least the number of messages + timeouts)
        self.assertGreaterEqual(mock_bus_instance.recv.call_count, 6)


    @patch('avsip.can_handler.can.interface.Bus')
    def test_listener_loop_queue_full(self, MockCanBus):
        """Test the listener loop when the data queue becomes full."""
        mock_bus_instance = MockCanBus.return_value
        
        # Simulate receiving many messages quickly
        messages = [create_mock_can_message(0x123, bytes([i])) for i in range(15)] # 15 messages
        mock_bus_instance.recv.side_effect = messages + [None] * 5 # Messages then timeouts

        config = {
            "enabled": True, "interface_type": "mockcan", "channel": "mock0", "bitrate": 500000,
            "receive_timeout_seconds": 0.1,
            "message_definitions": [
                {"id": "0x123", "name": "TestData", "parser": {
                    "type": "simple_scalar", "start_byte": 0, "length_bytes": 1,
                    "scale": 1, "offset": 0, "is_signed": False, "byte_order": "big"}}
            ]
        }
        # Use the setUp queue which has maxsize=10
        handler = CANHandler(config, self.data_queue)
        self.assertTrue(handler.is_connected)

        logging.disable(logging.NOTSET)
        with self.assertLogs(level='WARNING') as cm:
             handler.start_listener()
             time.sleep(0.5) # Let listener process
             handler.stop_listener()
        logging.disable(logging.CRITICAL)

        # Check that a warning about the queue being full was logged
        self.assertTrue(any("CAN data queue is full" in log_msg for log_msg in cm.output))

        # Check that the queue contains exactly maxsize items
        q_count = 0
        while not self.data_queue.empty():
            self.data_queue.get_nowait()
            q_count += 1
        self.assertEqual(q_count, self.data_queue.maxsize) # Should contain 10 items

    @patch('avsip.can_handler.can.interface.Bus')
    def test_listener_loop_can_error_and_reconnect(self, MockCanBus):
        """Test handling of CanError during recv and attempting reconnect."""
        mock_bus_instance_1 = MagicMock()
        mock_bus_instance_2 = MagicMock(channel_info="Reconnected Mock") # Mock for after reconnect

        # Simulate recv raising CanError, then successful recv after reconnect
        mock_bus_instance_1.recv.side_effect = [
            create_mock_can_message(0x123, b'\x11'), # First message OK
            can.CanError("Bus Error"), # Error occurs
        ]
        mock_bus_instance_2.recv.side_effect = [
             create_mock_can_message(0x123, b'\x22'), # Message after reconnect
             None # Timeout
        ]
        
        # Simulate Bus constructor: first returns bus1, second returns bus2 (after error)
        MockCanBus.side_effect = [mock_bus_instance_1, mock_bus_instance_2]

        config = {
            "enabled": True, "interface_type": "mockcan", "channel": "mock0", "bitrate": 500000,
            "receive_timeout_seconds": 0.1, "connection_retries": 1, "retry_delay_seconds": 0.01,
            "message_definitions": [
                {"id": "0x123", "name": "TestData", "parser": {
                    "type": "simple_scalar", "start_byte": 0, "length_bytes": 1,
                    "scale": 1, "offset": 0, "is_signed": False, "byte_order": "big"}}
            ]
        }
        handler = CANHandler(config, self.data_queue)
        self.assertTrue(handler.is_connected)

        logging.disable(logging.NOTSET)
        with self.assertLogs(level='ERROR') as cm: # Expect error for bus error
             handler.start_listener()
             time.sleep(0.5) # Let listener process, encounter error, and reconnect
             handler.stop_listener()
        logging.disable(logging.CRITICAL)

        self.assertTrue(any("CAN bus error in listener loop: Bus Error" in log_msg for log_msg in cm.output))
        self.assertEqual(MockCanBus.call_count, 2) # Initial connect + reconnect attempt
        mock_bus_instance_1.shutdown.assert_called_once() # Original bus should be shut down

        # Check queue contains messages from before and after reconnect
        items_in_queue = []
        while not self.data_queue.empty():
            items_in_queue.append(self.data_queue.get_nowait())
        
        self.assertEqual(len(items_in_queue), 2)
        self.assertEqual(items_in_queue[0]['value'], 0x11)
        self.assertEqual(items_in_queue[1]['value'], 0x22)


    @patch('avsip.can_handler.can.interface.Bus')
    def test_close_handler(self, MockCanBus):
        """Test closing the handler stops the listener and shuts down the bus."""
        mock_bus_instance = MockCanBus.return_value
        mock_bus_instance.shutdown = MagicMock()

        config = {"enabled": True, "message_definitions": []}
        handler = CANHandler(config, self.data_queue)
        self.assertTrue(handler.is_connected)
        
        # Start listener to ensure stop_listener is effective
        handler.start_listener()
        self.assertTrue(handler._listener_thread and handler._listener_thread.is_alive())

        handler.close()

        self.assertFalse(handler.is_connected)
        self.assertIsNone(handler.bus)
        mock_bus_instance.shutdown.assert_called_once()
        # Check thread stopped (or attempted to stop)
        self.assertFalse(handler._listener_thread and handler._listener_thread.is_alive())


if __name__ == '__main__':
    unittest.main(verbosity=2)
