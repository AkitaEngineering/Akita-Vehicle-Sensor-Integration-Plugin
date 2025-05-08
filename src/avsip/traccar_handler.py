# src/avsip/traccar_handler.py

import logging
import json
import time
import requests # Using requests library for HTTP communication
from typing import Dict, Any, Optional

from . import utils # For kph_to_knots, mph_to_knots

logger = logging.getLogger(__name__)

class TraccarHandler:
    """
    Handles communication with a Traccar server for AVSIP.
    - Formats and sends data (primarily GPS and selected sensor values) to Traccar.
    - Supports OsmAnd HTTP protocol.
    """

    def __init__(self, config: Dict[str, Any], traccar_device_id: str):
        """
        Initializes the TraccarHandler.

        Args:
            config: A dictionary containing Traccar specific configuration:
                {
                    "enabled": True,
                    "host": "localhost",
                    "port": 5055, // OsmAnd port
                    "use_http": True, // True for OsmAnd protocol
                    "http_path": "/",
                    "request_timeout_seconds": 10,
                    "convert_speed_to_knots": True
                    // device_id_source and custom_traccar_id are handled by core.py
                }
            traccar_device_id: The unique device identifier to be used with Traccar.
        """
        self.config = config
        self.traccar_device_id = traccar_device_id
        self.is_configured: bool = False

        if not self.config.get("enabled", False):
            logger.info("TraccarHandler is disabled in configuration.")
            return

        if not self.traccar_device_id:
            logger.error("TraccarHandler initialized with no device_id. Disabling Traccar.")
            self.config["enabled"] = False # Effectively disable
            return

        if not self.config.get("host"):
            logger.error("Traccar host not specified in configuration. Disabling Traccar.")
            self.config["enabled"] = False
            return
            
        self.base_url = self._construct_base_url()
        if self.base_url:
            self.is_configured = True
            logger.info(f"TraccarHandler initialized. Target URL: {self.base_url}, Device ID: {self.traccar_device_id}")
        else:
            logger.error("Failed to construct Traccar base URL. Disabling Traccar.")
            self.config["enabled"] = False


    def _construct_base_url(self) -> Optional[str]:
        """Constructs the base URL for Traccar based on configuration."""
        host = self.config.get("host")
        port = self.config.get("port", 5055)
        use_http = self.config.get("use_http", True) # Default to OsmAnd (HTTP)

        if not use_http:
            logger.warning("Traccar configured for non-HTTP mode, which is not fully supported by this handler. Please use OsmAnd (use_http: true).")
            return None # Or handle raw TCP if implemented later

        http_path = self.config.get("http_path", "/").strip()
        if not http_path.startswith("/"):
            http_path = "/" + http_path
        
        # Determine scheme based on common Traccar port usage (though not foolproof)
        scheme = "http"
        if port == 443 or port == 8082: # 8082 is often Traccar's web UI HTTPS port
             # This is a guess; Traccar's OsmAnd port (5055) is usually HTTP.
             # For proper HTTPS on OsmAnd port, server needs to be configured for it.
             # User should ensure their Traccar host/port config matches their server's scheme.
             pass # Stick to http for OsmAnd port unless explicitly configured for https

        return f"{scheme}://{host}:{port}{http_path}"


    def _prepare_osmand_payload(self, avsip_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Prepares the data payload for the OsmAnd protocol.

        Args:
            avsip_data: The aggregated data dictionary from AVSIP.

        Returns:
            A dictionary of parameters suitable for an OsmAnd HTTP request.
        """
        params: Dict[str, Any] = {}
        params["id"] = self.traccar_device_id
        params["timestamp"] = int(avsip_data.get("timestamp_utc", time.time()))

        gps_data = avsip_data.get("gps", {})
        if gps_data and gps_data.get("latitude") is not None and gps_data.get("longitude") is not None:
            params["lat"] = gps_data["latitude"]
            params["lon"] = gps_data["longitude"]
            if gps_data.get("altitude") is not None:
                params["altitude"] = gps_data["altitude"]
            if gps_data.get("speed") is not None: # Assuming speed from GPS is in m/s
                speed_mps = gps_data["speed"]
                # Convert m/s to knots for Traccar if configured
                if self.config.get("convert_speed_to_knots", True):
                    params["speed"] = round(speed_mps * 1.94384, 2) # m/s to knots
                else: # Send as m/s, Traccar might handle or display as is
                    params["speed"] = round(speed_mps, 2)

            if gps_data.get("course") is not None:
                params["bearing"] = gps_data["course"] # OsmAnd uses 'bearing'
            if gps_data.get("hdop") is not None:
                params["hdop"] = gps_data["hdop"]
            # Traccar also accepts 'accuracy' which might be derived from HDOP or other GPS precision metrics
        else:
            logger.debug("No valid GPS lat/lon in AVSIP data for Traccar payload.")
            # Traccar usually requires lat/lon. If not present, the point might be invalid.

        # Add other sensor data as custom attributes
        # Traccar's OsmAnd protocol accepts arbitrary key-value pairs.
        sensors = avsip_data.get("sensors", {})
        for key, value in sensors.items():
            if value is not None:
                clean_key = utils.clean_sensor_name(key) # Ensure keys are simple
                params[clean_key] = value
        
        # Add CAN data, prefixing keys to avoid collisions
        can_data = avsip_data.get("can_data", {})
        for key, value in can_data.items():
            if value is not None:
                clean_key = f"can_{utils.clean_sensor_name(key)}"
                params[clean_key] = value

        # Add DTCs as a comma-separated string or individual params
        dtcs = avsip_data.get("dtcs", [])
        if dtcs:
            params["dtcs"] = ",".join(dtcs)
            # Alternatively, params["dtc_count"] = len(dtcs)

        # Battery level (map from vehicle voltage if available)
        # Example: if "control_module_voltage" in sensors:
        #    params["batt"] = sensors["control_module_voltage"]

        return params

    def send_data(self, avsip_data: Dict[str, Any]) -> bool:
        """
        Sends data to the Traccar server.

        Args:
            avsip_data: The aggregated data dictionary from AVSIP.

        Returns:
            True if data was successfully sent, False otherwise.
        """
        if not self.is_configured or not self.config.get("enabled"):
            logger.debug("TraccarHandler not configured or disabled. Skipping send.")
            return False

        if not avsip_data.get("gps") or avsip_data["gps"].get("latitude") is None or avsip_data["gps"].get("longitude") is None:
            logger.debug("Skipping Traccar send: Essential GPS data (lat/lon) is missing.")
            return False

        if self.config.get("use_http", True): # OsmAnd protocol
            payload = self._prepare_osmand_payload(avsip_data)
            if not payload.get("lat") is not None: # Double check after prep
                logger.warning("Traccar OsmAnd payload missing lat/lon after preparation. Aborting send.")
                return False

            timeout = self.config.get("request_timeout_seconds", 10)
            try:
                logger.debug(f"Sending data to Traccar (OsmAnd): {self.base_url} with params: {payload}")
                response = requests.post(self.base_url, params=payload, timeout=timeout)
                response.raise_for_status() # Raises an HTTPError for bad responses (4XX or 5XX)
                
                logger.info(f"Data successfully sent to Traccar. Response: {response.status_code} {response.text[:100]}")
                return True
            except requests.exceptions.Timeout:
                logger.warning(f"Request to Traccar server timed out ({timeout}s). URL: {self.base_url}")
            except requests.exceptions.ConnectionError:
                logger.warning(f"Failed to connect to Traccar server. URL: {self.base_url}. Check host and network.")
            except requests.exceptions.HTTPError as e:
                logger.error(f"HTTP error sending data to Traccar: {e.response.status_code} {e.response.reason}. Response: {e.response.text[:200]}")
            except Exception as e:
                logger.error(f"An unexpected error occurred sending data to Traccar: {e}", exc_info=True)
        else:
            logger.warning("Traccar send_data called, but non-HTTP mode is not implemented.")
            return False
            
        return False

    def close(self) -> None:
        """Closes any persistent connections (not typically needed for HTTP)."""
        logger.info("TraccarHandler close called (no specific resources to release for HTTP).")
        self.is_configured = False # Mark as not configured to prevent further sends


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG,
                        format='%(asctime)s - %(name)s - %(levelname)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s')

    # Ensure your Traccar server is running and accessible.
    # The device ID "avsip_traccar_test_001" must be registered in your Traccar server.
    # Default Traccar OsmAnd port is 5055.
    test_traccar_config = {
        "enabled": True,
        "host": "localhost",  # Replace with your Traccar server's host/IP if not local
        "port": 5055,
        "use_http": True,
        "http_path": "/",
        "request_timeout_seconds": 10,
        "convert_speed_to_knots": True
    }
    test_device_id = "avsip_traccar_test_001" # This ID must exist in your Traccar server

    traccar_handler = TraccarHandler(test_traccar_config, test_device_id)

    if not traccar_handler.is_configured:
        logger.error("TraccarHandler failed to initialize or was disabled. Exiting test.")
        exit()

    logger.info("--- Testing TraccarHandler ---")

    # Test Case 1: Valid GPS data and some sensor data
    avsip_payload_1 = {
        "timestamp_utc": time.time(),
        "device_id": "avsip_core_id_123", # This is AVSIP's internal ID
        "gps": {
            "latitude": 40.7128,
            "longitude": -74.0060,
            "altitude": 15,
            "speed": 27.78, # m/s (approx 100 kph)
            "course": 45.0,
            "hdop": 1.2,
            "satellites": 8,
            "timestamp_gps": time.time() - 5 # Simulate GPS time slightly older
        },
        "sensors": {
            "RPM": 2500,
            "COOLANT_TEMP": 90, # Celsius
            "speed_kph": 100.0 # From OBD, for example
        },
        "can_data": {
            "OilPressure": 45.5,
            "SteeringAngle": 15.2
        },
        "dtcs": ["P0101", "U0073"]
    }
    logger.info(f"Sending Test Payload 1 to Traccar Device ID: {test_device_id}...")
    if traccar_handler.send_data(avsip_payload_1):
        logger.info("Test Payload 1 sent successfully.")
    else:
        logger.error("Failed to send Test Payload 1.")

    time.sleep(2)

    # Test Case 2: Minimal GPS data
    avsip_payload_2 = {
        "timestamp_utc": time.time(),
        "device_id": "avsip_core_id_123",
        "gps": {
            "latitude": 40.7135,
            "longitude": -74.0050,
            "timestamp_gps": time.time()
        }
        # No sensors, CAN, or DTCs
    }
    logger.info(f"Sending Test Payload 2 to Traccar Device ID: {test_device_id}...")
    if traccar_handler.send_data(avsip_payload_2):
        logger.info("Test Payload 2 sent successfully.")
    else:
        logger.error("Failed to send Test Payload 2.")

    time.sleep(2)
    
    # Test Case 3: Missing essential GPS data (should be skipped by send_data)
    avsip_payload_3 = {
        "timestamp_utc": time.time(),
        "device_id": "avsip_core_id_123",
        "gps": { # Missing latitude/longitude
            "altitude": 20
        },
        "sensors": {"RPM": 1000}
    }
    logger.info(f"Sending Test Payload 3 (missing lat/lon) to Traccar Device ID: {test_device_id}...")
    if traccar_handler.send_data(avsip_payload_3): # Expected False
        logger.error("Test Payload 3 was sent, but should have been skipped due to missing GPS.")
    else:
        logger.info("Test Payload 3 correctly not sent (or failed as expected).")

    traccar_handler.close()
    logger.info("TraccarHandler test finished.")

