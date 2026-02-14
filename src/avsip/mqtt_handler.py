# src/avsip/mqtt_handler.py

import logging
import json
import time
import threading
import paho.mqtt.client as mqtt
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class MQTTHandler:
    """
    Handles communication with an MQTT broker for AVSIP.
    - Establishes connection to the MQTT broker (with TLS support).
    - Publishes sensor data to specified topics.
    - Implements Last Will and Testament (LWT) for device status.
    """

    def __init__(self, config: Dict[str, Any], device_id: str):
        """
        Initializes the MQTTHandler.

        Args:
            config: A dictionary containing MQTT specific configuration:
                {
                    "enabled": True,
                    "host": "localhost",
                    "port": 1883,
                    "user": None,
                    "password": None,
                    "topic_prefix": "vehicle/avsip",
                    "qos": 0,
                    "retain_messages": False,
                    "tls_enabled": False,
                    "tls_ca_certs": None,
                    "tls_certfile": None,
                    "tls_keyfile": None,
                    "lwt_topic_suffix": "status",
                    "lwt_payload_online": "online",
                    "lwt_payload_offline": "offline",
                    "lwt_qos": 0,
                    "lwt_retain": True,
                    "connection_timeout_seconds": 10,
                    "keepalive": 60
                }
            device_id: The unique ID for this AVSIP device, used in topic construction.
        """
        self.config = config
        self.device_id = device_id
        self.client: Optional[mqtt.Client] = None
        self.is_connected: bool = False
        self._connection_lost_event = threading.Event() # Used to signal connection loss for retry logic

        if not self.config.get("enabled", False):
            logger.info("MQTTHandler is disabled in configuration.")
            return

        if not self.device_id or self.device_id.startswith("unknown") or self.device_id.startswith("fallback"):
            logger.error(f"MQTTHandler received an invalid device_id: '{self.device_id}'. MQTT will be disabled.")
            self.config["enabled"] = False # Effectively disable
            return
            
        self._client_id = f"avsip-{self.device_id}-{int(time.time())}" # Unique client ID
        self.client = mqtt.Client(client_id=self._client_id, protocol=mqtt.MQTTv311, transport="tcp")

        self._configure_client()
        self.connect()

    def _configure_client(self) -> None:
        """Configures MQTT client options, LWT, TLS, and callbacks."""
        if not self.client:
            return

        # Configure Last Will and Testament (LWT)
        lwt_topic_suffix = self.config.get("lwt_topic_suffix", "status")
        self.lwt_topic = f"{self.config.get('topic_prefix', 'vehicle/avsip')}/{self.device_id}/{lwt_topic_suffix}"
        lwt_payload_offline = self.config.get("lwt_payload_offline", "offline")
        lwt_qos = self.config.get("lwt_qos", 0)
        lwt_retain = self.config.get("lwt_retain", True)
        
        self.client.will_set(
            self.lwt_topic,
            payload=lwt_payload_offline,
            qos=lwt_qos,
            retain=lwt_retain
        )
        logger.info(f"MQTT LWT configured: Topic='{self.lwt_topic}', OfflinePayload='{lwt_payload_offline}'")

        # Configure TLS if enabled
        if self.config.get("tls_enabled", False):
            ca_certs = self.config.get("tls_ca_certs")
            certfile = self.config.get("tls_certfile")
            keyfile = self.config.get("tls_keyfile")
            try:
                self.client.tls_set(
                    ca_certs=ca_certs,
                    certfile=certfile,
                    keyfile=keyfile
                    # cert_reqs=ssl.CERT_REQUIRED, # Default
                    # tls_version=ssl.PROTOCOL_TLS_CLIENT, # Default
                )
                logger.info("MQTT TLS enabled.")
                if ca_certs: logger.debug(f"MQTT TLS using CA: {ca_certs}")
                if certfile: logger.debug(f"MQTT TLS using client cert: {certfile}")

            except Exception as e:
                logger.error(f"Failed to configure MQTT TLS: {e}. Disabling MQTT.", exc_info=True)
                self.config["enabled"] = False # Disable MQTT if TLS config fails
                return


        # Set username and password
        username = self.config.get("user")
        password = self.config.get("password")
        if username:
            self.client.username_pw_set(username, password)
            logger.info("MQTT username/password set.")

        # Assign callbacks
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_publish = self._on_publish
        self.client.on_log = self._on_log # Optional: for paho-mqtt internal logging

    def _on_connect(self, client: mqtt.Client, userdata: Any, flags: Dict[str, Any], rc: int, properties: Optional[Any] = None) -> None:
        """Callback for when the client receives a CONNACK response from the server."""
        if rc == 0:
            self.is_connected = True
            self._connection_lost_event.clear() # Connection is good
            logger.info(f"Successfully connected to MQTT broker: {self.config.get('host')}:{self.config.get('port')}")
            # Publish online status via LWT topic (explicitly)
            lwt_payload_online = self.config.get("lwt_payload_online", "online")
            lwt_qos = self.config.get("lwt_qos", 0) # Use same QoS as LWT will
            lwt_retain = self.config.get("lwt_retain", True) # Use same retain as LWT will
            self.client.publish(self.lwt_topic, payload=lwt_payload_online, qos=lwt_qos, retain=lwt_retain)
            logger.info(f"Published online status to LWT topic: '{self.lwt_topic}'")
        else:
            self.is_connected = False
            logger.error(f"MQTT connection failed with result code {rc}: {mqtt.connack_string(rc)}")
            if rc == mqtt.MQTT_ERR_CONN_REFUSED or rc == mqtt.MQTT_ERR_AUTH or rc == mqtt.MQTT_ERR_NOT_AUTHORIZED:
                logger.error("MQTT connection refused (check credentials, client ID, broker ACLs). Disabling MQTT for this session.")
                self.config["enabled"] = False # Prevent further retries if auth fails

    def _on_disconnect(self, client: mqtt.Client, userdata: Any, rc: int, properties: Optional[Any] = None) -> None:
        """Callback for when the client disconnects from the broker."""
        self.is_connected = False
        if rc == 0:
            logger.info("MQTT client disconnected gracefully.")
        else:
            logger.warning(f"MQTT client unexpectedly disconnected with result code {rc}. LWT should publish offline status.")
            self._connection_lost_event.set() # Signal connection loss for potential retry logic
            # The Paho client's loop() or loop_start() handles automatic reconnections by default
            # unless connect_async is used without loop_start.
            # We are using loop_start, so it should attempt to reconnect.

    def _on_publish(self, client: mqtt.Client, userdata: Any, mid: int) -> None:
        """Callback for when a message is successfully published."""
        logger.debug(f"MQTT message (MID: {mid}) published successfully.")

    def _on_log(self, client: mqtt.Client, userdata: Any, level: int, buf: str) -> None:
        """Paho MQTT client internal logging callback."""
        # Map Paho log levels to Python logging levels
        if level == mqtt.MQTT_LOG_INFO:
            logger.debug(f"PahoMQTT INFO: {buf}") # Downgrade Paho INFO to our DEBUG
        elif level == mqtt.MQTT_LOG_NOTICE:
            logger.info(f"PahoMQTT NOTICE: {buf}")
        elif level == mqtt.MQTT_LOG_WARNING:
            logger.warning(f"PahoMQTT WARNING: {buf}")
        elif level == mqtt.MQTT_LOG_ERR:
            logger.error(f"PahoMQTT ERROR: {buf}")
        elif level == mqtt.MQTT_LOG_DEBUG: # Paho DEBUG is very verbose
            if logger.isEnabledFor(logging.DEBUG): # Only log if our logger is also at DEBUG
                 logger.debug(f"PahoMQTT DEBUG: {buf}")


    def connect(self) -> None:
        """Connects to the MQTT broker."""
        if not self.client or not self.config.get("enabled"):
            logger.debug("MQTT client not available or MQTT is disabled. Skipping connect.")
            return

        if self.is_connected:
            logger.debug("MQTT client is already connected.")
            return

        host = self.config.get("host")
        port = self.config.get("port", 1883)
        keepalive = self.config.get("keepalive", 60)
        connection_timeout = self.config.get("connection_timeout_seconds", 10)

        try:
            logger.info(f"Attempting to connect to MQTT broker at {host}:{port}...")
            self.client.loop_start() # Starts a background thread for network traffic, reconnections
            # Using connect_async to avoid blocking, then wait for on_connect callback or timeout
            self.client.connect_async(host, port, keepalive)
            
            # Wait for connection with a timeout
            # The on_connect callback will set self.is_connected
            # We can monitor self.is_connected or use an event
            start_time = time.monotonic()
            while not self.is_connected and (time.monotonic() - start_time) < connection_timeout:
                if self._connection_lost_event.is_set() and not self.config.get("enabled"): # If on_connect failed and disabled MQTT
                    logger.error("MQTT connection permanently failed during initial connect sequence.")
                    self.client.loop_stop() # Stop the loop if we're giving up
                    return
                time.sleep(0.1)

            if not self.is_connected:
                logger.error(f"MQTT connection attempt timed out after {connection_timeout} seconds.")
                # Do not stop the client's network loop here; leave loop running so
                # the client can perform automatic reconnects if configured. The
                # caller may choose to disconnect/stop the loop explicitly.
                # self.client.loop_stop() intentionally omitted to avoid double-stops in tests.
        except Exception as e:
            logger.error(f"Exception during MQTT connect: {e}", exc_info=True)
            if self.client.is_connected(): # Should not happen if exception occurred before connect
                 self.client.disconnect()
            self.client.loop_stop(force=True) # Ensure loop is stopped
            self.is_connected = False


    def publish_data(self, data_payload: Dict[str, Any], sub_topic: str = "sensors") -> bool:
        """
        Publishes data to a sub-topic under the device's main topic prefix.

        Args:
            data_payload: The dictionary payload to publish.
            sub_topic: The sub-topic to append to <topic_prefix>/<device_id>/.

        Returns:
            True if the message was successfully queued for publishing, False otherwise.
        """
        if not self.is_connected or not self.client:
            logger.warning("MQTT client not connected. Cannot publish data.")
            # Optionally, try to reconnect here if appropriate, or rely on Paho's auto-reconnect
            # if not self.client.is_connected() and self.config.get("enabled"):
            #    logger.info("Attempting to reconnect MQTT before publishing...")
            #    self.connect() # This might block or take time
            #    if not self.is_connected:
            #        return False
            return False

        topic = f"{self.config.get('topic_prefix', 'vehicle/avsip')}/{self.device_id}/{sub_topic}"
        qos = self.config.get("qos", 0)
        retain = self.config.get("retain_messages", False)

        try:
            # Fail fast on non-JSON-serializable payloads to surface errors to callers
            payload_str = json.dumps(data_payload)
            msg_info = self.client.publish(topic, payload=payload_str, qos=qos, retain=retain)
            
            if msg_info.rc == mqtt.MQTT_ERR_SUCCESS:
                logger.info(f"Successfully queued message for MQTT topic '{topic}' (MID: {msg_info.mid})")
                # msg_info.wait_for_publish(timeout=2) # Optional: block until published (or timeout)
                # if msg_info.is_published():
                #    logger.debug(f"MQTT message (MID: {msg_info.mid}) confirmed published to topic '{topic}'.")
                # else:
                #    logger.warning(f"MQTT message (MID: {msg_info.mid}) to topic '{topic}' not confirmed published within timeout.")
                return True
            elif msg_info.rc == mqtt.MQTT_ERR_NO_CONN:
                logger.warning(f"Failed to queue message for MQTT topic '{topic}': No connection. (MID: {msg_info.mid})")
                self.is_connected = False # Update connection status
                self._connection_lost_event.set()
                return False
            elif msg_info.rc == mqtt.MQTT_ERR_QUEUE_SIZE:
                logger.warning(f"Failed to queue message for MQTT topic '{topic}': Publish queue is full. (MID: {msg_info.mid})")
                return False
            else:
                logger.warning(f"Failed to queue message for MQTT topic '{topic}' with error code {msg_info.rc}. (MID: {msg_info.mid})")
                return False

        except (TypeError, ValueError) as e:
            # JSON serialization errors typically raise TypeError (or ValueError for some inputs)
            logger.error(f"Failed to serialize payload to JSON for MQTT topic '{topic}': {e}", exc_info=True)
            return False
        except Exception as e:
            logger.error(f"An unexpected error occurred during MQTT publish to '{topic}': {e}", exc_info=True)
            return False

    def disconnect(self) -> None:
        """Disconnects from the MQTT broker and stops the network loop."""
        if self.client:
            logger.info("Disconnecting from MQTT broker...")
            try:
                # Publish offline status before disconnecting if connected
                if self.is_connected:
                    lwt_payload_offline = self.config.get("lwt_payload_offline", "offline")
                    lwt_qos = self.config.get("lwt_qos", 0)
                    lwt_retain = self.config.get("lwt_retain", True)
                    self.client.publish(self.lwt_topic, payload=lwt_payload_offline, qos=lwt_qos, retain=lwt_retain)
                    logger.info(f"Published offline status to LWT topic '{self.lwt_topic}' before disconnect.")
                    # Allow a moment for the message to go out
                    time.sleep(0.1) 

                self.client.loop_stop() # Stop the background thread first
                self.client.disconnect() # Request disconnect
                # The on_disconnect callback will set self.is_connected to False
                logger.info("MQTT client disconnect requested.")
            except Exception as e:
                logger.error(f"Error during MQTT disconnect: {e}", exc_info=True)
        self.is_connected = False # Ensure status is updated


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG,
                        format='%(asctime)s - %(name)s - %(levelname)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s')
    
    # Public broker for testing: test.mosquitto.org, port 1883 (no auth, no TLS)
    # For TLS testing: test.mosquitto.org, port 8883 (requires ca_certs='mosquitto.org.crt' or system CA)
    # or port 8884 (requires client cert)

    test_mqtt_config_no_tls = {
        "enabled": True,
        "host": "test.mosquitto.org",
        "port": 1883,
        "user": None,
        "password": None,
        "topic_prefix": "vehicle/avsip/test",
        "qos": 1,
        "retain_messages": False, # LWT retain is separate
        "lwt_topic_suffix": "connection_status",
        "lwt_payload_online": "DeviceOnline",
        "lwt_payload_offline": "DeviceOffline",
        "lwt_qos": 1,
        "lwt_retain": True,
        "connection_timeout_seconds": 10,
        "keepalive": 60
    }
    
    # To test TLS, you might need to download mosquitto.org.crt if your system CAs don't include it
    # test_mqtt_config_tls = {
    #     "enabled": True,
    #     "host": "test.mosquitto.org",
    #     "port": 8883,
    #     "tls_enabled": True,
    #     "tls_ca_certs": None, # None to use system CAs, or path to "mosquitto.org.crt"
    #     "topic_prefix": "vehicle/avsip/tls_test",
    #     # ... other params similar to no_tls
    # }

    test_device_id = f"testdevice_{int(time.time())%1000}"
    logger.info(f"--- Testing MQTTHandler with Device ID: {test_device_id} ---")

    mqtt_handler = MQTTHandler(test_mqtt_config_no_tls, test_device_id)
    
    if not mqtt_handler.client or not mqtt_handler.config.get("enabled"):
        logger.error("MQTTHandler initialization failed or was disabled. Exiting test.")
        exit()

    # Wait for connection to establish (on_connect sets is_connected)
    # The connect method itself has a timeout loop.
    # Here we just check the status after connect() call.
    if not mqtt_handler.is_connected:
        logger.error("MQTT client failed to connect initially. Check logs. Exiting.")
        mqtt_handler.disconnect() # Ensure cleanup
        exit()

    logger.info("MQTT Handler connected. Publishing test data...")

    test_data_1 = {"temperature": 25.5, "rpm": 1500, "location": {"lat": 40.1, "lon": -74.2}}
    mqtt_handler.publish_data(test_data_1, sub_topic="engine_sensors")

    time.sleep(2) # Give time for message to go out and LWT to be visible

    test_data_2 = {"speed": 60, "fuel_level": 0.75}
    mqtt_handler.publish_data(test_data_2, sub_topic="vehicle_status")

    logger.info("Test messages published. Check your MQTT client subscribed to vehicle/avsip/test/#")
    logger.info(f"LWT topic should be: vehicle/avsip/test/{test_device_id}/connection_status")
    
    logger.info("Waiting for 10 seconds before disconnecting to observe LWT if connection drops...")
    # To test LWT, you could manually kill this script or disconnect network here.
    time.sleep(10)

    mqtt_handler.disconnect()
    logger.info("MQTTHandler test finished.")

