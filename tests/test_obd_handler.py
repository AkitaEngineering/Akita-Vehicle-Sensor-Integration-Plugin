# tests/test_obd_handler.py

import unittest
import logging
import time
from unittest.mock import MagicMock, patch, PropertyMock, call

# Add src to sys.path to allow importing avsip package
import sys
import os
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
src_path = os.path.join(project_root, 'src')
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from avsip.obd_handler import OBDHandler # type: ignore
# Mock the obd library itself before OBDHandler imports it if necessary,
# but patching within tests is usually sufficient.
# We need to mock obd.OBD, obd.commands, obd.OBDStatus etc.
import obd # Import the real library to mock its parts

# Suppress logging during tests
logging.disable(logging.CRITICAL)

# Helper mock classes/objects
class MockOBDResponse:
    def __init__(self, value, unit=None):
        # Simulate Pint quantities for some values
        if isinstance(value, (int, float)) and unit:
            self.value = MagicMock() # Mock the Pint Quantity object
            self.value.magnitude = value
            self.value.units = unit
        else: # Handle non-Pint values (like DTC lists or strings)
            self.value = value
            
    def is_null(self):
        return self.value is None

# Mock command objects (needs names matching those used in config)
MockRPMCmd = MagicMock(spec=obd.OBDCommand)
MockRPMCmd.name = "RPM"
MockSpeedCmd = MagicMock(spec=obd.OBDCommand)
MockSpeedCmd.name = "SPEED"
MockCoolantTempCmd = MagicMock(spec=obd.OBDCommand)
MockCoolantTempCmd.name = "COOLANT_TEMP"
MockFuelLevelCmd = MagicMock(spec=obd.OBDCommand)
MockFuelLevelCmd.name = "FUEL_LEVEL" # Example of unsupported command
MockGetDTCCmd = MagicMock(spec=obd.OBDCommand)
MockGetDTCCmd.name = "GET_DTC"

# Dictionary to map command names to mock command objects
MOCK_OBD_COMMANDS = {
    "RPM": MockRPMCmd,
    "SPEED": MockSpeedCmd,
    "COOLANT_TEMP": MockCoolantTempCmd,
    "FUEL_LEVEL": MockFuelLevelCmd,
    "GET_DTC": MockGetDTCCmd,
}

class TestOBDHandler(unittest.TestCase):

    def tearDown(self):
        logging.disable(logging.NOTSET) # Re-enable logging

    # Patch 'obd.OBD' in the module where it's used (avsip.obd_handler)
    @patch('avsip.obd_handler.obd.OBD') 
    @patch('avsip.obd_handler.obd.commands') # Patch the commands module access
    def test_connect_success(self, mock_obd_commands, MockOBD):
        """Test successful connection and initialization."""
        # Configure mock OBD connection
        mock_connection_instance = MockOBD.return_value
        mock_connection_instance.is_connected.return_value = True
        mock_connection_instance.status.return_value = obd.OBDStatus.CAR_CONNECTED
        # Configure mock commands module access
        mock_obd_commands.PIDS = {1: MOCK_OBD_COMMANDS.values()} # Simulate Mode 01 PIDs
        mock_obd_commands.RPM = MockRPMCmd
        mock_obd_commands.SPEED = MockSpeedCmd
        mock_obd_commands.COOLANT_TEMP = MockCoolantTempCmd
        mock_obd_commands.FUEL_LEVEL = MockFuelLevelCmd
        # Configure mock support check
        mock_connection_instance.supports.side_effect = lambda cmd: cmd.name != "FUEL_LEVEL" # Support all but FUEL_LEVEL

        config = {
            "enabled": True,
            "port_string": "/dev/ttyFAKE",
            "commands": ["RPM", "SPEED", "COOLANT_TEMP", "FUEL_LEVEL"], # Request FUEL_LEVEL too
            "connection_retries": 0 # No retries for this test
        }
        handler = OBDHandler(config)

        self.assertTrue(handler.is_connected)
        self.assertIsNotNone(handler.connection)
        MockOBD.assert_called_once() # Check constructor called
        # Check supported commands were identified correctly
        self.assertEqual(len(handler.supported_commands), 3)
        supported_names = {cmd.name for cmd in handler.supported_commands}
        self.assertIn("RPM", supported_names)
        self.assertIn("SPEED", supported_names)
        self.assertIn("COOLANT_TEMP", supported_names)
        self.assertNotIn("FUEL_LEVEL", supported_names)
        mock_connection_instance.close.assert_not_called()

    @patch('avsip.obd_handler.obd.OBD')
    def test_connect_failure_and_retry(self, MockOBD):
        """Test connection failure with retries."""
        # Simulate connection failing twice, then succeeding
        mock_conn_fail1 = MagicMock()
        mock_conn_fail1.is_connected.return_value = False
        mock_conn_fail1.status.return_value = obd.OBDStatus.NOT_CONNECTED
        mock_conn_fail1.close = MagicMock()

        mock_conn_fail2 = MagicMock()
        mock_conn_fail2.is_connected.return_value = False
        # Some python-obd versions don't define ELM_ERROR; use NOT_CONNECTED as a
        # representative failure status for the test environment.
        mock_conn_fail2.status.return_value = getattr(obd.OBDStatus, 'ELM_ERROR', obd.OBDStatus.NOT_CONNECTED)
        mock_conn_fail2.close = MagicMock()

        mock_conn_success = MagicMock()
        mock_conn_success.is_connected.return_value = True
        mock_conn_success.status.return_value = obd.OBDStatus.CAR_CONNECTED
        mock_conn_success.supports.return_value = True # Assume supports for simplicity here
        mock_conn_success.close = MagicMock()

        MockOBD.side_effect = [mock_conn_fail1, mock_conn_fail2, mock_conn_success]

        config = {
            "enabled": True,
            "port_string": "/dev/ttyFAKE",
            "commands": ["RPM"],
            "connection_retries": 2, # Allow 2 retries (total 3 attempts)
            "retry_delay_seconds": 0.01 # Fast retry for test
        }
        
        logging.disable(logging.NOTSET) # Check logs
        with self.assertLogs(level='WARNING') as cm:
             handler = OBDHandler(config)
        logging.disable(logging.CRITICAL)

        self.assertTrue(handler.is_connected)
        self.assertEqual(MockOBD.call_count, 3)
        mock_conn_fail1.close.assert_called_once() # Ensure failed connections are closed
        mock_conn_fail2.close.assert_called_once()
        mock_conn_success.close.assert_not_called() # Successful one shouldn't be closed yet
        self.assertTrue(any("connection attempt 1 failed" in log_msg for log_msg in cm.output))
        self.assertTrue(any("connection attempt 2 failed" in log_msg for log_msg in cm.output))

    @patch('avsip.obd_handler.obd.OBD')
    def test_connect_failure_max_retries(self, MockOBD):
        """Test connection failure after exhausting all retries."""
        mock_conn_fail = MagicMock()
        mock_conn_fail.is_connected.return_value = False
        mock_conn_fail.status.return_value = obd.OBDStatus.NOT_CONNECTED
        mock_conn_fail.close = MagicMock()
        MockOBD.return_value = mock_conn_fail # Always return the failing mock

        config = {
            "enabled": True,
            "port_string": "/dev/ttyFAKE",
            "commands": ["RPM"],
            "connection_retries": 1, # Total 2 attempts
            "retry_delay_seconds": 0.01
        }

        logging.disable(logging.NOTSET)
        with self.assertLogs(level='ERROR') as cm:
            handler = OBDHandler(config)
        logging.disable(logging.CRITICAL)

        self.assertFalse(handler.is_connected)
        self.assertIsNone(handler.connection)
        self.assertEqual(MockOBD.call_count, 2) # Initial + 1 retry
        self.assertEqual(mock_conn_fail.close.call_count, 2) # Closed after each failed attempt
        self.assertTrue(any("Failed to connect to OBD-II adapter after all retries" in log_msg for log_msg in cm.output))

    def test_handler_disabled(self):
        """Test handler initialization when disabled."""
        config = {"enabled": False}
        handler = OBDHandler(config)
        self.assertFalse(handler.is_connected)
        self.assertIsNone(handler.connection)

    @patch('avsip.obd_handler.obd.OBD')
    @patch('avsip.obd_handler.obd.commands')
    def test_read_data_success(self, mock_obd_commands, MockOBD):
        """Test reading sensor data and DTCs successfully."""
        # Setup connection mock
        mock_connection_instance = MockOBD.return_value
        mock_connection_instance.is_connected.return_value = True
        mock_connection_instance.status.return_value = obd.OBDStatus.CAR_CONNECTED
        # Setup command mocks
        mock_obd_commands.PIDS = {1: MOCK_OBD_COMMANDS.values()}
        mock_obd_commands.RPM = MockRPMCmd
        mock_obd_commands.SPEED = MockSpeedCmd
        mock_obd_commands.GET_DTC = MockGetDTCCmd
        # Setup support mock
        mock_connection_instance.supports.side_effect = lambda cmd: cmd.name in ["RPM", "SPEED", "GET_DTC"]
        # Setup query mock responses
        mock_connection_instance.query.side_effect = lambda cmd, force=False: {
            MockRPMCmd: MockOBDResponse(1500.55, unit='rpm'),
            MockSpeedCmd: MockOBDResponse(65, unit='kph'),
            MockGetDTCCmd: MockOBDResponse([("P0101", "MAF Sensor"), ("C0011", "Some Chassis Code")])
        }.get(cmd)

        config = {
            "enabled": True,
            "commands": ["RPM", "SPEED"],
            "include_dtc_codes": True,
            "connection_retries": 0
        }
        handler = OBDHandler(config)
        self.assertTrue(handler.is_connected)
        
        sensors, dtcs = handler.read_data()

        # Check sensor values
        self.assertIn("rpm", sensors)
        self.assertAlmostEqual(sensors["rpm"], 1500.55)
        self.assertIn("speed", sensors)
        self.assertEqual(sensors["speed"], 65)
        self.assertEqual(len(sensors), 2) # Only supported commands queried

        # Check DTCs
        self.assertIsInstance(dtcs, list)
        self.assertEqual(len(dtcs), 2)
        self.assertIn("P0101", dtcs)
        self.assertIn("C0011", dtcs)

        # Verify query calls
        expected_calls = [call(MockRPMCmd, force=True), call(MockSpeedCmd, force=True), call(MockGetDTCCmd, force=True)]
        mock_connection_instance.query.assert_has_calls(expected_calls, any_order=True)


    @patch('avsip.obd_handler.obd.OBD')
    @patch('avsip.obd_handler.obd.commands')
    def test_read_data_no_dtcs_found(self, mock_obd_commands, MockOBD):
        """Test reading data when GET_DTC returns an empty list."""
        mock_connection_instance = MockOBD.return_value
        mock_connection_instance.is_connected.return_value = True
        mock_connection_instance.status.return_value = obd.OBDStatus.CAR_CONNECTED
        mock_obd_commands.GET_DTC = MockGetDTCCmd
        mock_connection_instance.supports.return_value = True # Support GET_DTC
        mock_connection_instance.query.return_value = MockOBDResponse([]) # Empty list for DTCs

        config = {"enabled": True, "commands": [], "include_dtc_codes": True}
        handler = OBDHandler(config)
        self.assertTrue(handler.is_connected)
        
        sensors, dtcs = handler.read_data()

        self.assertEqual(sensors, {}) # No sensor commands configured
        self.assertEqual(dtcs, []) # Expect empty list


    @patch('avsip.obd_handler.obd.OBD')
    @patch('avsip.obd_handler.obd.commands')
    def test_read_data_dtc_disabled(self, mock_obd_commands, MockOBD):
        """Test reading data when include_dtc_codes is false."""
        mock_connection_instance = MockOBD.return_value
        mock_connection_instance.is_connected.return_value = True
        mock_connection_instance.status.return_value = obd.OBDStatus.CAR_CONNECTED
        mock_obd_commands.GET_DTC = MockGetDTCCmd
        mock_connection_instance.supports.return_value = True
        mock_connection_instance.query = MagicMock() # Mock query generally

        config = {"enabled": True, "commands": [], "include_dtc_codes": False} # DTC disabled
        handler = OBDHandler(config)
        self.assertTrue(handler.is_connected)
        
        sensors, dtcs = handler.read_data()

        self.assertEqual(sensors, {})
        self.assertEqual(dtcs, []) # DTC list should be empty as it wasn't queried
        # Assert that GET_DTC was NOT queried
        for query_call in mock_connection_instance.query.call_args_list:
            args, kwargs = query_call
            self.assertNotEqual(args[0], MockGetDTCCmd, "GET_DTC should not have been queried.")


    @patch('avsip.obd_handler.obd.OBD')
    @patch('avsip.obd_handler.obd.commands')
    def test_read_data_command_null_response(self, mock_obd_commands, MockOBD):
        """Test reading data when a command returns a null response."""
        mock_connection_instance = MockOBD.return_value
        mock_connection_instance.is_connected.return_value = True
        mock_connection_instance.status.return_value = obd.OBDStatus.CAR_CONNECTED
        mock_obd_commands.RPM = MockRPMCmd
        mock_connection_instance.supports.return_value = True
        # Simulate RPM returning null
        mock_connection_instance.query.return_value = MockOBDResponse(None) 

        config = {"enabled": True, "commands": ["RPM"], "include_dtc_codes": False}
        handler = OBDHandler(config)
        self.assertTrue(handler.is_connected)
        
        sensors, dtcs = handler.read_data()

        self.assertIn("rpm", sensors)
        self.assertIsNone(sensors["rpm"]) # Expect None for null response


    @patch('avsip.obd_handler.obd.OBD')
    def test_read_data_not_connected(self, MockOBD):
        """Test read_data when not connected."""
        mock_connection_instance = MockOBD.return_value
        mock_connection_instance.is_connected.return_value = False # Simulate not connected

        config = {"enabled": True, "commands": ["RPM"], "include_dtc_codes": False}
        handler = OBDHandler(config)
        # Force handler state for test, assuming connect failed
        handler.is_connected = False
        handler.connection = None 
        
        sensors, dtcs = handler.read_data()

        self.assertEqual(sensors, {})
        self.assertEqual(dtcs, [])


    @patch('avsip.obd_handler.obd.OBD')
    def test_close_handler(self, MockOBD):
        """Test closing the handler."""
        mock_connection_instance = MockOBD.return_value
        mock_connection_instance.is_connected.return_value = True
        mock_connection_instance.status.return_value = obd.OBDStatus.CAR_CONNECTED
        mock_connection_instance.close = MagicMock()

        config = {"enabled": True, "commands": [], "connection_retries": 0}
        handler = OBDHandler(config)
        self.assertTrue(handler.is_connected)
        
        handler.close()
        self.assertFalse(handler.is_connected)
        self.assertIsNone(handler.connection)
        mock_connection_instance.close.assert_called_once()


if __name__ == '__main__':
    unittest.main(verbosity=2)
