# src/avsip/meshtastic_handler.py

import logging
import time
import json
import meshtastic
import meshtastic.serial_interface
from meshtastic.util import Timeout # Import Timeout for graceful connection attempts
# from meshtastic.node import Node # For type hinting if needed
# from pubsub import pub # If we need to subscribe to Meshtastic events like 'meshtastic.receive.data'

logger = logging.getLogger(__name__)

class MeshtasticHandler:
    """
    Handles communication with a Meshtastic device for AVSIP.
    - Establishes connection to the Meshtastic device.
    - Retrieves the device's node ID.
    - Fetches GPS data.
    - Sends data packets over the Meshtastic network.
    """

    def __init__(self, config: dict):
        """
        Initializes the MeshtasticHandler.

        Args:
            config: A dictionary containing Meshtastic specific configuration:
                {
                    "enabled": True,
                    "device_port": "/dev/ttyUSB0" or None for auto-detect,
                    "data_port_num": 250, // PortNum for AVSIP data
                    "connection_timeout_seconds": 10, // Time to wait for initial connection
                    "send_retries": 2,
                    "send_retry_delay_seconds": 3
                }
        """
        self.config = config
        self.interface = None
        self.node_id = None
        self.node_num = None # Meshtastic internal node number
        self.is_connected = False

        if not self.config.get("enabled", True): # Default to enabled if key is missing
            logger.info("MeshtasticHandler is disabled in configuration.")
            return

        self._connect()

    def _connect(self):
        """Attempts to connect to the Meshtastic device."""
        device_port = self.config.get("device_port")
        connection_timeout = self.config.get("connection_timeout_seconds", 10)

        try:
            logger.info(f"Attempting to connect to Meshtastic device on port: {device_port if device_port else 'auto-detect'}...")
            if device_port:
                self.interface = meshtastic.serial_interface.SerialInterface(devPath=device_port)
            else:
                self.interface = meshtastic.serial_interface.SerialInterface()  # Auto-detect

            # Wait for connection and node information with a timeout
            # The nodes attribute is populated once the interface is connected and has received nodeDB.
            # We can check myInfo directly.
            start_time = time.monotonic()
            while time.monotonic() - start_time < connection_timeout:
                if self.interface and self.interface.myInfo:
                    self.node_id = self.interface.myInfo.my_node_num # This is the node number
                    # For a more user-friendly ID, we can use the hex string if available,
                    # but my_node_num is the unique integer ID.
                    # Node ID string (e.g., "!aabbccdd") is usually self.interface.myInfo.user.id
                    # Let's use the user.id if available, otherwise the node_num as hex.
                    if hasattr(self.interface.myInfo, 'user') and self.interface.myInfo.user and self.interface.myInfo.user.id:
                        self.node_id = self.interface.myInfo.user.id
                    else:
                        self.node_id = f"!{self.interface.myInfo.my_node_num:08x}" # Hex representation of node num
                    
                    self.node_num = self.interface.myInfo.my_node_num
                    self.is_connected = True
                    logger.info(f"Successfully connected to Meshtastic device. Node ID: {self.node_id} (Num: {self.node_num})")
                    
                    # Optionally, print more node info
                    logger.debug(f"My Meshtastic Info: {self.interface.myInfo}")
                    # logger.debug(f"Radio Config: {self.interface.radioConfig}") # Can be large
                    # logger.debug(f"Primary Channel URL: {self.interface.channelURL}")
                    return
                time.sleep(0.5)
            
            logger.error(f"Failed to get node info from Meshtastic device within {connection_timeout}s timeout.")
            if self.interface:
                self.interface.close()
            self.interface = None
            self.is_connected = False

        except meshtastic.util.MeshtasticException as e:
            logger.error(f"Meshtastic connection error: {e}", exc_info=True)
            self.is_connected = False
        except Exception as e:
            logger.error(f"Failed to connect to Meshtastic device: {e}", exc_info=True)
            self.is_connected = False

    def get_device_id(self) -> str | None:
        """Returns the connected Meshtastic device's node ID."""
        return self.node_id if self.is_connected else None
        
    def get_node_num(self) -> int | None:
        """Returns the connected Meshtastic device's internal node number."""
        return self.node_num if self.is_connected else None

    def get_gps_data(self) -> dict | None:
        """
        Retrieves GPS data from the Meshtastic device.

        Returns:
            A dictionary containing GPS data if available and valid, otherwise None.
            Example: {"latitude": 40.7128, "longitude": -74.0060, "altitude": 10,
                      "speed": 5.5, "course": 120.0, "satellites": 5,
                      "hdop": 1.5, "timestamp_gps": 1678886400}
        """
        if not self.is_connected or not self.interface:
            logger.warning("Not connected to Meshtastic device, cannot get GPS data.")
            return None

        try:
            # Position is part of myInfo or can be requested from local node's remote module
            # For simplicity, we check the local node's position if available in nodeDB
            # Note: The `localNode` property handles fetching the local node object.
            node = self.interface.localNode
            if node and 'position' in node.record:
                pos = node.record['position']
                # Check for valid latitude and longitude (Meshtastic sets them to 0 or 1000 if invalid/unset)
                # A more robust check is if 'latitudeI' or 'longitudeI' are non-zero.
                # Or if 'time' field in position is non-zero (indicates a valid fix has been received)
                if pos.get('time', 0) != 0 and pos.get('latitudeI', 0) != 0 and pos.get('longitudeI', 0) != 0:
                    gps_data = {
                        "latitude": pos.get('latitude', 0.0),
                        "longitude": pos.get('longitude', 0.0),
                        "altitude": pos.get('altitude', 0), # meters
                        "speed": pos.get('speed', 0), # m/s - convert if needed
                        "course": pos.get('heading', 0), # degrees
                        "satellites": pos.get('satsInView', 0), # Older field, 'sats_in_view' might be newer
                        "precision_bits": pos.get('precisionBits',0), # Can be used to estimate HDOP
                        "timestamp_gps": pos.get('time', 0) # Unix timestamp from GPS
                    }
                    # HDOP is not directly available, but precision_bits can give an idea.
                    # For AVSIP, we might simplify or just report what's available.
                    # Let's add a placeholder for HDOP if we can't derive it easily.
                    gps_data["hdop"] = round( (1 << ( (pos.get('precisionBits',0) / 2) -1 ) ) /10.0, 1) if pos.get('precisionBits',0) > 0 else 99.0


                    logger.debug(f"GPS data retrieved: {gps_data}")
                    return gps_data
                else:
                    logger.debug("No valid GPS fix available from Meshtastic device (time, lat, or lon is zero).")
                    return None
            else:
                logger.debug("No position data in local Meshtastic node record.")
                return None
        except Exception as e:
            logger.error(f"Error getting GPS data from Meshtastic: {e}", exc_info=True)
            return None

    def send_data(self, payload: dict, destination_node_id: str = "^all") -> bool:
        """
        Sends data as a JSON string over the Meshtastic network.

        Args:
            payload: The dictionary payload to send.
            destination_node_id: The destination node ID (e.g., "!aabbccdd" or "^all" for broadcast).
                                 Default is broadcast.

        Returns:
            True if data was sent successfully (or queued), False otherwise.
        """
        if not self.is_connected or not self.interface:
            logger.warning("Not connected to Meshtastic device, cannot send data.")
            return False

        port_num = self.config.get("data_port_num", 250) # Default to AVSIP data port
        send_retries = self.config.get("send_retries", 2)
        retry_delay = self.config.get("send_retry_delay_seconds", 3)

        try:
            # Serialize payload to JSON string
            # Ensure all data types in payload are JSON serializable (e.g. no sets)
            # For simplicity, assuming payload is already prepared by AVSIP core.
            data_bytes = json.dumps(payload).encode('utf-8')

            if len(data_bytes) > meshtastic.MAX_PAYLOAD_BYTES: # Check against Meshtastic max payload size
                logger.error(f"Data payload size ({len(data_bytes)} bytes) exceeds Meshtastic limit ({meshtastic.MAX_PAYLOAD_BYTES} bytes). Cannot send.")
                # Consider chunking or alternative serialization if this is a common issue.
                return False

            for attempt in range(send_retries + 1):
                try:
                    logger.debug(f"Sending data to {destination_node_id} on port {port_num} (Attempt {attempt + 1})")
                    # The sendData method handles protobuf wrapping.
                    # We send bytes, with a DataApp portnum.
                    self.interface.sendData(
                        data_bytes,
                        destinationId=destination_node_id, # Can be specific node or broadcast
                        portNum=port_num,
                        wantAck=False, # Set to True if ACK is desired, though this makes it blocking or requires callback
                        channelIndex=0 # Usually 0 for primary channel
                    )
                    logger.info(f"Data successfully sent/queued to Meshtastic: {len(data_bytes)} bytes to {destination_node_id} on port {port_num}.")
                    return True
                except meshtastic.util.Timeout as t_err: # Specific timeout error from meshtastic-python
                    logger.warning(f"Timeout sending Meshtastic data (Attempt {attempt + 1}/{send_retries+1}): {t_err}")
                    if attempt < send_retries:
                        time.sleep(retry_delay)
                    else:
                        logger.error("Max retries reached for sending Meshtastic data due to timeout.")
                        return False
                except Exception as e_inner: # Other errors during send
                    logger.error(f"Error sending Meshtastic data (Attempt {attempt + 1}): {e_inner}", exc_info=True)
                    return False # Don't retry on unexpected errors immediately

        except json.JSONDecodeError as e:
            logger.error(f"Failed to serialize payload to JSON: {e}", exc_info=True)
            return False
        except Exception as e:
            logger.error(f"An unexpected error occurred during Meshtastic send_data: {e}", exc_info=True)
            return False
        return False # Should not be reached if logic is correct

    def close(self):
        """Closes the connection to the Meshtastic device."""
        if self.interface:
            try:
                logger.info("Closing Meshtastic interface...")
                self.interface.close()
                self.is_connected = False
                logger.info("Meshtastic interface closed.")
            except Exception as e:
                logger.error(f"Error closing Meshtastic interface: {e}", exc_info=True)
        self.interface = None


if __name__ == "__main__":
    # Example Usage (requires a Meshtastic device connected)
    logging.basicConfig(level=logging.DEBUG, 
                        format='%(asctime)s - %(name)s - %(levelname)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s')

    # Create a dummy config for testing
    # Ensure your device is on a port, or set device_port to None for auto-detect
    # You might need to run `meshtastic --setchan psk_default 1` or similar if your device has no channels.
    # Or, configure a channel via the Meshtastic app.
    test_config = {
        "enabled": True,
        "device_port": None, # Set to your device's port e.g., "/dev/ttyUSB0" or None
        "data_port_num": 251, # Use a test port
        "connection_timeout_seconds": 15,
        "send_retries": 1
    }

    handler = MeshtasticHandler(test_config)

    if handler.is_connected:
        logger.info(f"Device ID: {handler.get_device_id()}")
        logger.info(f"Node Num: {handler.get_node_num()}")

        for _ in range(3): # Try to get GPS data a few times
            gps_info = handler.get_gps_data()
            if gps_info:
                logger.info(f"GPS Data: {gps_info}")
            else:
                logger.info("No GPS data available yet.")
            time.sleep(5) # Wait for potential GPS fix

        test_payload = {
            "message": "Hello from AVSIP MeshtasticHandler test!",
            "timestamp": time.time(),
            "value": 123.45
        }
        if handler.send_data(test_payload):
            logger.info("Test payload sent successfully.")
        else:
            logger.error("Failed to send test payload.")

        # Test sending to a specific (non-existent for this test) node
        # handler.send_data({"msg": "direct test"}, destination_node_id="!12345678")

        handler.close()
    else:
        logger.error("Could not connect to Meshtastic device for testing.")
