# tests/test_traccar_handler.py

import unittest
import logging
import time
import requests # Import the real library to mock its parts
from unittest.mock import MagicMock, patch, call

# Add src to sys.path to allow importing avsip package
import sys
import os
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
src_path = os.path.join(project_root, 'src')
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from avsip.traccar_handler import TraccarHandler # type: ignore
from avsip import utils # For speed conversion check

# Suppress logging during tests
logging.disable(logging.CRITICAL)

class TestTraccarHandler(unittest.TestCase):

    def tearDown(self):
        """Re-enable logging after tests."""
        logging.disable(logging.NOTSET)

    def test_init_success_http(self):
        """Test successful initialization with HTTP OsmAnd config."""
        config = {
            "enabled": True, "host": "demo.traccar.org", "port": 5055,
            "use_http": True, "http_path": "/", "request_timeout_seconds": 5
        }
        device_id = "test_device_01"
        handler = TraccarHandler(config, device_id)

        self.assertTrue(handler.is_configured)
        self.assertEqual(handler.traccar_device_id, device_id)
        self.assertEqual(handler.base_url, "http://demo.traccar.org:5055/")

    def test_init_success_http_custom_path(self):
        """Test successful initialization with custom HTTP path."""
        config = {
            "enabled": True, "host": "mytraccar.local", "port": 5055,
            "use_http": True, "http_path": "/api/osmand" # Test custom path
        }
        device_id = "test_device_02"
        handler = TraccarHandler(config, device_id)

        self.assertTrue(handler.is_configured)
        self.assertEqual(handler.base_url, "http://mytraccar.local:5055/api/osmand")

    def test_init_disabled(self):
        """Test initialization when handler is disabled."""
        config = {"enabled": False, "host": "demo.traccar.org", "port": 5055}
        device_id = "test_device_03"
        handler = TraccarHandler(config, device_id)
        self.assertFalse(handler.is_configured)

    def test_init_missing_device_id(self):
        """Test initialization with a missing device ID."""
        config = {"enabled": True, "host": "demo.traccar.org", "port": 5055}
        device_id = "" # Empty device ID
        logging.disable(logging.NOTSET)
        with self.assertLogs(level='ERROR') as cm:
            handler = TraccarHandler(config, device_id)
        logging.disable(logging.CRITICAL)
        self.assertFalse(handler.is_configured)
        self.assertTrue(any("initialized with no device_id" in log_msg for log_msg in cm.output))

    def test_init_missing_host(self):
        """Test initialization with a missing host."""
        config = {"enabled": True, "host": None, "port": 5055}
        device_id = "test_device_04"
        logging.disable(logging.NOTSET)
        with self.assertLogs(level='ERROR') as cm:
            handler = TraccarHandler(config, device_id)
        logging.disable(logging.CRITICAL)
        self.assertFalse(handler.is_configured)
        self.assertTrue(any("Traccar host not specified" in log_msg for log_msg in cm.output))

    def test_init_non_http_mode(self):
        """Test initialization when use_http is false (currently unsupported)."""
        config = {"enabled": True, "host": "demo.traccar.org", "port": 5001, "use_http": False}
        device_id = "test_device_05"
        logging.disable(logging.NOTSET)
        with self.assertLogs(level='WARNING') as cm:
            handler = TraccarHandler(config, device_id)
        logging.disable(logging.CRITICAL)
        # is_configured should be False because _construct_base_url returns None
        self.assertFalse(handler.is_configured)
        self.assertTrue(any("non-HTTP mode, which is not fully supported" in log_msg for log_msg in cm.output))

    def test_prepare_osmand_payload_full(self):
        """Test preparing a full OsmAnd payload."""
        config = {"enabled": True, "convert_speed_to_knots": True}
        device_id = "prep_test_01"
        handler = TraccarHandler(config, device_id)

        ts = int(time.time())
        avsip_data = {
            "timestamp_utc": ts, "device_id": "avsip_core_id",
            "gps": {"latitude": 40.1, "longitude": -74.2, "altitude": 50, "speed": 10.0, "course": 180, "hdop": 1.5},
            "sensors": {"RPM": 2000, "speed_kph": 36.0}, # Speed from OBD might differ from GPS speed
            "can_data": {"OilPressure": 55.0},
            "dtcs": ["P0300"]
        }
        payload = handler._prepare_osmand_payload(avsip_data)

        self.assertEqual(payload["id"], device_id)
        self.assertEqual(payload["timestamp"], ts)
        self.assertEqual(payload["lat"], 40.1)
        self.assertEqual(payload["lon"], -74.2)
        self.assertEqual(payload["altitude"], 50)
        self.assertAlmostEqual(payload["speed"], 10.0 * 1.94384) # Check knots conversion
        self.assertEqual(payload["bearing"], 180)
        self.assertEqual(payload["hdop"], 1.5)
        self.assertEqual(payload["rpm"], 2000)
        self.assertEqual(payload["speed_kph"], 36.0) # Sensor data passed through
        self.assertEqual(payload["can_oilpressure"], 55.0) # CAN data prefixed
        self.assertEqual(payload["dtcs"], "P0300")

    def test_prepare_osmand_payload_minimal_gps(self):
        """Test preparing payload with only essential GPS data."""
        config = {"enabled": True, "convert_speed_to_knots": False} # Test without knots conversion
        device_id = "prep_test_02"
        handler = TraccarHandler(config, device_id)

        ts = int(time.time())
        avsip_data = {
            "timestamp_utc": ts, "device_id": "avsip_core_id",
            "gps": {"latitude": 40.1, "longitude": -74.2, "speed": 5.0}, # Only lat, lon, speed
            "sensors": {}, "can_data": {}, "dtcs": []
        }
        payload = handler._prepare_osmand_payload(avsip_data)

        self.assertEqual(payload["id"], device_id)
        self.assertEqual(payload["timestamp"], ts)
        self.assertEqual(payload["lat"], 40.1)
        self.assertEqual(payload["lon"], -74.2)
        self.assertAlmostEqual(payload["speed"], 5.0) # Speed passed as m/s
        self.assertNotIn("altitude", payload)
        self.assertNotIn("bearing", payload)
        self.assertNotIn("rpm", payload) # No sensor data

    # Patch requests.post for the send_data tests
    @patch('avsip.traccar_handler.requests.post')
    def test_send_data_success(self, mock_post):
        """Test successful data sending via HTTP POST."""
        # Configure the mock response
        mock_response = MagicMock(spec=requests.Response)
        mock_response.status_code = 200
        mock_response.text = "OK"
        mock_response.raise_for_status = MagicMock() # Mock this method to do nothing on 200 OK
        mock_post.return_value = mock_response

        config = {"enabled": True, "host": "test.traccar", "port": 5055, "use_http": True, "http_path": "/"}
        device_id = "send_test_01"
        handler = TraccarHandler(config, device_id)
        self.assertTrue(handler.is_configured)

        avsip_data = {"timestamp_utc": time.time(), "gps": {"latitude": 10.0, "longitude": 20.0}}
        result = handler.send_data(avsip_data)

        self.assertTrue(result)
        mock_post.assert_called_once()
        # Check args passed to requests.post
        call_args, call_kwargs = mock_post.call_args
        self.assertEqual(call_args[0], handler.base_url) # Check URL
        self.assertIn("params", call_kwargs)
        self.assertEqual(call_kwargs["params"]["id"], device_id)
        self.assertEqual(call_kwargs["params"]["lat"], 10.0)
        self.assertEqual(call_kwargs["params"]["lon"], 20.0)
        self.assertEqual(call_kwargs["timeout"], config.get("request_timeout_seconds", 10))

    @patch('avsip.traccar_handler.requests.post')
    def test_send_data_http_error(self, mock_post):
        """Test send_data failure due to HTTP error."""
        mock_response = MagicMock(spec=requests.Response)
        mock_response.status_code = 400 # Bad Request
        mock_response.reason = "Bad Request"
        mock_response.text = "Device unknown"
        # Configure raise_for_status to raise an HTTPError
        mock_response.raise_for_status = MagicMock(side_effect=requests.exceptions.HTTPError(response=mock_response))
        mock_post.return_value = mock_response

        config = {"enabled": True, "host": "test.traccar", "port": 5055, "use_http": True}
        device_id = "send_test_02_unknown"
        handler = TraccarHandler(config, device_id)
        self.assertTrue(handler.is_configured)

        avsip_data = {"timestamp_utc": time.time(), "gps": {"latitude": 10.0, "longitude": 20.0}}
        
        logging.disable(logging.NOTSET)
        with self.assertLogs(level='ERROR') as cm:
            result = handler.send_data(avsip_data)
        logging.disable(logging.CRITICAL)

        self.assertFalse(result)
        mock_post.assert_called_once()
        self.assertTrue(any("HTTP error sending data to Traccar: 400 Bad Request" in log_msg for log_msg in cm.output))
        self.assertTrue(any("Device unknown" in log_msg for log_msg in cm.output))


    @patch('avsip.traccar_handler.requests.post', side_effect=requests.exceptions.Timeout)
    def test_send_data_timeout(self, mock_post):
        """Test send_data failure due to requests.exceptions.Timeout."""
        config = {"enabled": True, "host": "test.traccar", "port": 5055, "use_http": True, "request_timeout_seconds": 1}
        device_id = "send_test_03_timeout"
        handler = TraccarHandler(config, device_id)
        self.assertTrue(handler.is_configured)

        avsip_data = {"timestamp_utc": time.time(), "gps": {"latitude": 10.0, "longitude": 20.0}}
        
        logging.disable(logging.NOTSET)
        with self.assertLogs(level='WARNING') as cm:
             result = handler.send_data(avsip_data)
        logging.disable(logging.CRITICAL)

        self.assertFalse(result)
        mock_post.assert_called_once()
        self.assertTrue(any("Request to Traccar server timed out" in log_msg for log_msg in cm.output))

    @patch('avsip.traccar_handler.requests.post', side_effect=requests.exceptions.ConnectionError)
    def test_send_data_connection_error(self, mock_post):
        """Test send_data failure due to requests.exceptions.ConnectionError."""
        config = {"enabled": True, "host": "nonexistent.traccar.host", "port": 5055, "use_http": True}
        device_id = "send_test_04_conn_err"
        handler = TraccarHandler(config, device_id)
        self.assertTrue(handler.is_configured)

        avsip_data = {"timestamp_utc": time.time(), "gps": {"latitude": 10.0, "longitude": 20.0}}
        
        logging.disable(logging.NOTSET)
        with self.assertLogs(level='WARNING') as cm:
             result = handler.send_data(avsip_data)
        logging.disable(logging.CRITICAL)

        self.assertFalse(result)
        mock_post.assert_called_once()
        self.assertTrue(any("Failed to connect to Traccar server" in log_msg for log_msg in cm.output))

    def test_send_data_missing_gps(self):
        """Test send_data skips sending if essential GPS data is missing."""
        config = {"enabled": True, "host": "test.traccar", "port": 5055, "use_http": True}
        device_id = "send_test_05_no_gps"
        handler = TraccarHandler(config, device_id)
        self.assertTrue(handler.is_configured)

        # Payload missing gps['latitude']
        avsip_data = {"timestamp_utc": time.time(), "gps": {"longitude": 20.0}}
        
        # Patch post just to ensure it's not called
        with patch('avsip.traccar_handler.requests.post') as mock_post:
             result = handler.send_data(avsip_data)
             self.assertFalse(result)
             mock_post.assert_not_called()

    def test_send_data_handler_not_configured(self):
        """Test send_data does nothing if handler is not configured."""
        config = {"enabled": True, "host": None} # Missing host -> not configured
        device_id = "send_test_06_not_cfg"
        handler = TraccarHandler(config, device_id)
        self.assertFalse(handler.is_configured)

        avsip_data = {"timestamp_utc": time.time(), "gps": {"latitude": 10.0, "longitude": 20.0}}
        with patch('avsip.traccar_handler.requests.post') as mock_post:
             result = handler.send_data(avsip_data)
             self.assertFalse(result)
             mock_post.assert_not_called()

    def test_close_handler(self):
        """Test the close method (should be no-op for HTTP)."""
        config = {"enabled": True, "host": "test.traccar", "port": 5055}
        device_id = "close_test"
        handler = TraccarHandler(config, device_id)
        self.assertTrue(handler.is_configured)
        
        # Call close and check state
        handler.close()
        self.assertFalse(handler.is_configured) # Close marks it as not configured


if __name__ == '__main__':
    unittest.main(verbosity=2)
