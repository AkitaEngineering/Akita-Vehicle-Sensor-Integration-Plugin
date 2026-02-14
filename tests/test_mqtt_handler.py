# tests/test_mqtt_handler.py

import unittest
import logging
import time
import json
from unittest.mock import MagicMock, patch, call, ANY

# Add src to sys.path to allow importing avsip package
import sys
import os
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
src_path = os.path.join(project_root, 'src')
if src_path not in sys.path:
    sys.path.insert(0, src_path)

# Mock paho library *before* importing the handler that uses it
# This prevents the handler from importing the real paho module
paho_mock = MagicMock()
sys.modules['paho'] = paho_mock
sys.modules['paho.mqtt'] = paho_mock.mqtt
sys.modules['paho.mqtt.client'] = paho_mock.mqtt.client

# Now import the handler
from avsip.mqtt_handler import MQTTHandler # type: ignore

# Define constants used by paho that might be needed in tests
paho_mock.mqtt.client.MQTTv311 = 3 # Example protocol version
paho_mock.mqtt.client.MQTT_ERR_SUCCESS = 0
paho_mock.mqtt.client.MQTT_ERR_NO_CONN = 1
paho_mock.mqtt.client.MQTT_ERR_QUEUE_SIZE = 14 # Example error code
paho_mock.mqtt.client.MQTT_ERR_CONN_REFUSED = 5
paho_mock.mqtt.client.connack_string = lambda rc: f"Connack_{rc}" # Mock connack string function
# Mock log levels if needed by _on_log callback tests
paho_mock.mqtt.client.MQTT_LOG_INFO = 1
paho_mock.mqtt.client.MQTT_LOG_WARNING = 8
paho_mock.mqtt.client.MQTT_LOG_ERR = 16
paho_mock.mqtt.client.MQTT_LOG_DEBUG = 4

# Suppress logging during tests
logging.disable(logging.CRITICAL)

class TestMQTTHandler(unittest.TestCase):

    def setUp(self):
        """Reset mocks for paho client before each test."""
        # We need to mock the Client *instance* returned by paho_mock.mqtt.client.Client()
        self.mock_mqtt_client_instance = MagicMock()
        paho_mock.mqtt.client.Client.return_value = self.mock_mqtt_client_instance
        
        # Reset call counts etc. on the class mock itself if needed
        paho_mock.mqtt.client.Client.reset_mock()

    def tearDown(self):
        """Re-enable logging after tests."""
        logging.disable(logging.NOTSET)

    def test_init_success_no_tls_no_auth(self):
        """Test successful initialization without TLS or auth."""
        config = {
            "enabled": True, "host": "mqtt.local", "port": 1883,
            "topic_prefix": "avsip/test", "lwt_topic_suffix": "status",
            "lwt_payload_offline": "kaput", "lwt_qos": 1, "lwt_retain": True,
            "connection_timeout_seconds": 5, "keepalive": 30
        }
        device_id = "device_init_01"
        
        handler = MQTTHandler(config, device_id)

        self.assertTrue(config["enabled"]) # Should still be enabled
        self.assertIsNotNone(handler.client)
        paho_mock.mqtt.client.Client.assert_called_once() # Check constructor called
        
        # Check LWT configuration
        expected_lwt_topic = f"avsip/test/{device_id}/status"
        self.mock_mqtt_client_instance.will_set.assert_called_once_with(
            expected_lwt_topic, payload="kaput", qos=1, retain=True
        )
        # Check TLS was not configured
        self.mock_mqtt_client_instance.tls_set.assert_not_called()
        # Check auth was not configured
        self.mock_mqtt_client_instance.username_pw_set.assert_not_called()
        # Check callbacks were assigned
        self.assertIsNotNone(self.mock_mqtt_client_instance.on_connect)
        self.assertIsNotNone(self.mock_mqtt_client_instance.on_disconnect)
        self.assertIsNotNone(self.mock_mqtt_client_instance.on_publish)
        # Check connect was called
        self.mock_mqtt_client_instance.connect_async.assert_called_once_with(
            "mqtt.local", 1883, 30
        )
        self.mock_mqtt_client_instance.loop_start.assert_called_once()

    def test_init_success_with_tls_and_auth(self):
        """Test successful initialization with TLS (CA only) and auth."""
        config = {
            "enabled": True, "host": "secure.mqtt", "port": 8883,
            "user": "testuser", "password": "testpassword",
            "topic_prefix": "avsip/secure", "lwt_topic_suffix": "conn",
            "tls_enabled": True, "tls_ca_certs": "/path/to/ca.crt",
             "connection_timeout_seconds": 5, "keepalive": 60
        }
        device_id = "device_init_02"
        handler = MQTTHandler(config, device_id)

        self.assertTrue(config["enabled"])
        # Check TLS configuration
        self.mock_mqtt_client_instance.tls_set.assert_called_once_with(
            ca_certs="/path/to/ca.crt", certfile=None, keyfile=None
        )
        # Check auth configuration
        self.mock_mqtt_client_instance.username_pw_set.assert_called_once_with("testuser", "testpassword")
        # Check connect
        self.mock_mqtt_client_instance.connect_async.assert_called_once_with("secure.mqtt", 8883, 60)
        self.mock_mqtt_client_instance.loop_start.assert_called_once()

    def test_init_tls_config_error(self):
        """Test initialization fails if TLS config raises an error."""
        self.mock_mqtt_client_instance.tls_set.side_effect = Exception("TLS Config Error")
        config = {
            "enabled": True, "host": "secure.mqtt", "port": 8883,
            "tls_enabled": True, "tls_ca_certs": "/bad/path/ca.crt"
        }
        device_id = "device_init_03_tls_err"
        
        logging.disable(logging.NOTSET)
        with self.assertLogs(level='ERROR') as cm:
            handler = MQTTHandler(config, device_id)
        logging.disable(logging.CRITICAL)

        self.assertFalse(config["enabled"], "MQTT should be disabled if TLS config fails")
        self.assertTrue(any("Failed to configure MQTT TLS" in log_msg for log_msg in cm.output))
        self.mock_mqtt_client_instance.connect_async.assert_not_called() # Connect should not be attempted


    def test_init_invalid_device_id(self):
        """Test initialization fails with invalid device ID."""
        config = {"enabled": True, "host": "mqtt.local"}
        invalid_ids = ["", None, "unknown_avsip_device", "fallback_123"]
        for device_id in invalid_ids:
            paho_mock.mqtt.client.Client.reset_mock() # Reset mock for each iteration
            logging.disable(logging.NOTSET)
            with self.assertLogs(level='ERROR') as cm:
                 handler = MQTTHandler(config, device_id) # type: ignore
            logging.disable(logging.CRITICAL)
            self.assertFalse(config["enabled"]) # Config dict itself is modified
            self.assertIsNone(handler.client) # Client shouldn't be created
            self.assertTrue(any(f"invalid device_id: '{device_id}'" in log_msg for log_msg in cm.output))
            config["enabled"] = True # Reset for next iteration


    def test_on_connect_success(self):
        """Test the _on_connect callback for successful connection."""
        config = {
            "enabled": True, "host": "mqtt.local", "port": 1883,
            "topic_prefix": "avsip/test", "lwt_topic_suffix": "status",
            "lwt_payload_online": "Connected", "lwt_qos": 1, "lwt_retain": True
        }
        device_id = "device_connect_01"
        handler = MQTTHandler(config, device_id)
        
        # Simulate the callback being called by Paho client
        handler._on_connect(handler.client, None, {}, 0) # rc=0 for success

        self.assertTrue(handler.is_connected)
        # Check that online status was published to LWT topic
        expected_lwt_topic = f"avsip/test/{device_id}/status"
        self.mock_mqtt_client_instance.publish.assert_called_once_with(
            expected_lwt_topic, payload="Connected", qos=1, retain=True
        )

    def test_on_connect_failure(self):
        """Test the _on_connect callback for failed connection."""
        config = {"enabled": True, "host": "mqtt.local", "port": 1883}
        device_id = "device_connect_02_fail"
        handler = MQTTHandler(config, device_id)
        handler.is_connected = True # Assume it thought it was connected

        # Simulate callback with failure code (e.g., bad credentials)
        rc = paho_mock.mqtt.client.MQTT_ERR_CONN_REFUSED # 5
        logging.disable(logging.NOTSET)
        with self.assertLogs(level='ERROR') as cm:
            handler._on_connect(handler.client, None, {}, rc)
        logging.disable(logging.CRITICAL)

        self.assertFalse(handler.is_connected)
        self.assertTrue(config["enabled"] == False) # Auth errors should disable handler
        self.assertTrue(any(f"MQTT connection failed with result code {rc}" in log_msg for log_msg in cm.output))
        self.assertTrue(any("connection refused" in log_msg for log_msg in cm.output))

    def test_on_disconnect_unexpected(self):
        """Test the _on_disconnect callback for unexpected disconnection."""
        config = {"enabled": True, "host": "mqtt.local"}
        device_id = "device_disconnect_01"
        handler = MQTTHandler(config, device_id)
        handler.is_connected = True # Assume it was connected

        logging.disable(logging.NOTSET)
        with self.assertLogs(level='WARNING') as cm:
            handler._on_disconnect(handler.client, None, 1) # rc=1 (non-zero indicates unexpected)
        logging.disable(logging.CRITICAL)

        self.assertFalse(handler.is_connected)
        self.assertTrue(any("MQTT client unexpectedly disconnected" in log_msg for log_msg in cm.output))
        self.assertTrue(handler._connection_lost_event.is_set()) # Event should be set

    def test_on_disconnect_graceful(self):
        """Test the _on_disconnect callback for graceful disconnection."""
        config = {"enabled": True, "host": "mqtt.local"}
        device_id = "device_disconnect_02"
        handler = MQTTHandler(config, device_id)
        handler.is_connected = True

        logging.disable(logging.NOTSET)
        with self.assertLogs(level='INFO') as cm:
            handler._on_disconnect(handler.client, None, 0) # rc=0 for graceful
        logging.disable(logging.CRITICAL)

        self.assertFalse(handler.is_connected)
        self.assertTrue(any("MQTT client disconnected gracefully" in log_msg for log_msg in cm.output))
        self.assertFalse(handler._connection_lost_event.is_set()) # Event should not be set

    def test_publish_data_success(self):
        """Test successful data publishing."""
        config = {"enabled": True, "host": "mqtt.local", "topic_prefix": "avsip/pub", "qos": 0}
        device_id = "device_pub_01"
        handler = MQTTHandler(config, device_id)
        handler.is_connected = True # Assume connected for test

        # Mock publish result
        mock_msg_info = MagicMock()
        mock_msg_info.rc = paho_mock.mqtt.client.MQTT_ERR_SUCCESS
        mock_msg_info.mid = 123
        self.mock_mqtt_client_instance.publish.return_value = mock_msg_info

        payload = {"sensor": "temp", "value": 22.5}
        result = handler.publish_data(payload, sub_topic="measurements")

        self.assertTrue(result)
        expected_topic = f"avsip/pub/{device_id}/measurements"
        expected_payload_str = json.dumps(payload)
        self.mock_mqtt_client_instance.publish.assert_called_once_with(
            expected_topic, payload=expected_payload_str, qos=0, retain=False
        )

    def test_publish_data_not_connected(self):
        """Test publishing data when not connected."""
        config = {"enabled": True, "host": "mqtt.local"}
        device_id = "device_pub_02_noconn"
        handler = MQTTHandler(config, device_id)
        handler.is_connected = False # Ensure not connected

        payload = {"sensor": "temp", "value": 22.5}
        result = handler.publish_data(payload, sub_topic="measurements")

        self.assertFalse(result)
        self.mock_mqtt_client_instance.publish.assert_not_called()

    def test_publish_data_queue_full(self):
        """Test publishing data when the Paho queue is full."""
        config = {"enabled": True, "host": "mqtt.local"}
        device_id = "device_pub_03_qfull"
        handler = MQTTHandler(config, device_id)
        handler.is_connected = True

        # Mock publish result indicating queue full
        mock_msg_info = MagicMock()
        mock_msg_info.rc = paho_mock.mqtt.client.MQTT_ERR_QUEUE_SIZE
        mock_msg_info.mid = 0
        self.mock_mqtt_client_instance.publish.return_value = mock_msg_info

        payload = {"sensor": "temp", "value": 22.5}
        
        logging.disable(logging.NOTSET)
        with self.assertLogs(level='WARNING') as cm:
             result = handler.publish_data(payload, sub_topic="measurements")
        logging.disable(logging.CRITICAL)

        self.assertFalse(result)
        self.mock_mqtt_client_instance.publish.assert_called_once()
        self.assertTrue(any("Publish queue is full" in log_msg for log_msg in cm.output))

    def test_publish_data_json_error(self):
        """Test publishing data that cannot be JSON serialized."""
        config = {"enabled": True, "host": "mqtt.local"}
        device_id = "device_pub_04_jsonerr"
        handler = MQTTHandler(config, device_id)
        handler.is_connected = True

        payload = {"sensor": "bad", "value": set([1, 2, 3])} # Sets are not JSON serializable by default
        
        logging.disable(logging.NOTSET)
        with self.assertLogs(level='ERROR') as cm:
             result = handler.publish_data(payload, sub_topic="measurements")
        logging.disable(logging.CRITICAL)

        self.assertFalse(result)
        self.mock_mqtt_client_instance.publish.assert_not_called() # Fails before publish
        self.assertTrue(any("Failed to serialize payload to JSON" in log_msg for log_msg in cm.output))

    def test_disconnect_publishes_offline_lwt(self):
        """Test that disconnect publishes the offline LWT message."""
        config = {
            "enabled": True, "host": "mqtt.local", "port": 1883,
            "topic_prefix": "avsip/test", "lwt_topic_suffix": "status",
            "lwt_payload_offline": "DeviceFellOver", "lwt_qos": 1, "lwt_retain": True
        }
        device_id = "device_disc_01"
        handler = MQTTHandler(config, device_id)
        handler.is_connected = True # Assume connected

        # Reset publish mock to check only the disconnect call
        self.mock_mqtt_client_instance.publish.reset_mock() 
        
        handler.disconnect()

        # Check that offline status was published to LWT topic
        expected_lwt_topic = f"avsip/test/{device_id}/status"
        self.mock_mqtt_client_instance.publish.assert_called_once_with(
            expected_lwt_topic, payload="DeviceFellOver", qos=1, retain=True
        )
        self.mock_mqtt_client_instance.loop_stop.assert_called_once()
        self.mock_mqtt_client_instance.disconnect.assert_called_once()


if __name__ == '__main__':
    unittest.main(verbosity=2)
