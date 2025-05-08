# src/avsip/can_handler.py

import logging
import time
import threading
import can # Import the python-can library
from queue import Queue, Full
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

class CANHandler:
    """
    Handles communication with a CAN bus for AVSIP.
    - Establishes connection to the CAN interface.
    - Listens for CAN messages in a separate thread.
    - Parses messages based on configured definitions.
    - Puts parsed data onto a queue for the main AVSIP loop.
    """

    def __init__(self, config: dict, data_queue: Queue):
        """
        Initializes the CANHandler.

        Args:
            config: A dictionary containing CAN specific configuration:
                {
                    "enabled": True,
                    "interface_type": "socketcan",
                    "channel": "can0",
                    "bitrate": 500000,
                    "message_definitions": [
                        {
                            "id": "0x123", # Hex CAN ID string
                            "name": "SensorName",
                            "parser": {
                                "type": "simple_scalar",
                                "start_byte": 0,
                                "length_bytes": 2,
                                "scale": 0.1,
                                "offset": 0,
                                "is_signed": False,
                                "byte_order": "big" # 'big' or 'little'
                            }
                        }
                    ],
                    "connection_retries": 3,
                    "retry_delay_seconds": 5,
                    "receive_timeout_seconds": 1.0 # Timeout for bus.recv()
                }
            data_queue: A queue to put parsed CAN data into. Each item will be a dict:
                        {"timestamp": float, "name": str, "value": float_or_int}
        """
        self.config = config
        self.data_queue = data_queue
        self.bus: Optional[can.interface.BusABC] = None
        self.is_connected: bool = False
        self.message_definitions: Dict[int, List[Dict[str, Any]]] = {} # Parsed definitions keyed by CAN ID (int)

        self._stop_event = threading.Event()
        self._listener_thread: Optional[threading.Thread] = None

        if not self.config.get("enabled", False):
            logger.info("CANHandler is disabled in configuration.")
            return

        self._parse_message_definitions()
        if not self.message_definitions:
            logger.warning("No valid CAN message definitions found. CAN processing might be limited.")
            # Continue to connect, might be used for raw logging later or if definitions are added dynamically.

        self._connect()

    def _parse_message_definitions(self):
        """Parses and validates message definitions from config."""
        raw_defs = self.config.get("message_definitions", [])
        if not isinstance(raw_defs, list):
            logger.error("'can.message_definitions' is not a list. Cannot parse CAN definitions.")
            return

        for i, definition in enumerate(raw_defs):
            try:
                can_id_str = definition.get("id")
                if not can_id_str or not isinstance(can_id_str, str):
                    logger.warning(f"CAN definition at index {i} has invalid or missing 'id'. Skipping.")
                    continue
                
                can_id = int(can_id_str, 16) # Convert hex string to int
                name = definition.get("name")
                parser_config = definition.get("parser")

                if not name or not isinstance(name, str):
                    logger.warning(f"CAN definition for ID {can_id_str} has invalid or missing 'name'. Skipping.")
                    continue
                if not parser_config or not isinstance(parser_config, dict):
                    logger.warning(f"CAN definition for ID {can_id_str} ('{name}') has invalid or missing 'parser' object. Skipping.")
                    continue
                
                # Validate parser config (simple_scalar for now)
                if parser_config.get("type") == "simple_scalar":
                    required_keys = ["start_byte", "length_bytes", "scale", "offset", "is_signed", "byte_order"]
                    if not all(k in parser_config for k in required_keys):
                        logger.warning(f"Parser for '{name}' (ID {can_id_str}) is missing required keys for 'simple_scalar'. Skipping.")
                        continue
                    # Further type validation could be added here for each parser key
                else:
                    logger.warning(f"Parser type '{parser_config.get('type')}' for '{name}' (ID {can_id_str}) is not supported. Skipping.")
                    continue

                if can_id not in self.message_definitions:
                    self.message_definitions[can_id] = []
                self.message_definitions[can_id].append({"name": name, "parser_config": parser_config})
                logger.debug(f"Successfully parsed CAN definition for ID {can_id_str} ('{name}').")

            except ValueError:
                logger.warning(f"CAN definition at index {i} has invalid 'id' format (not hex): '{can_id_str}'. Skipping.")
            except Exception as e:
                logger.error(f"Error parsing CAN definition at index {i}: {definition}. Error: {e}", exc_info=True)
        
        if self.message_definitions:
            logger.info(f"Loaded {sum(len(v) for v in self.message_definitions.values())} CAN message parsing definitions for {len(self.message_definitions)} unique IDs.")


    def _connect(self) -> None:
        """Attempts to connect to the CAN interface."""
        interface_type = self.config.get("interface_type", "socketcan")
        channel = self.config.get("channel", "can0")
        bitrate = self.config.get("bitrate", 500000)
        retries = self.config.get("connection_retries", 3)
        retry_delay = self.config.get("retry_delay_seconds", 5)

        for attempt in range(retries + 1):
            try:
                logger.info(
                    f"Attempting to connect to CAN bus (Attempt {attempt + 1}/{retries + 1}). "
                    f"Interface: {interface_type}, Channel: {channel}, Bitrate: {bitrate}"
                )
                self.bus = can.interface.Bus(bustype=interface_type, channel=channel, bitrate=bitrate)
                self.is_connected = True
                logger.info(f"Successfully connected to CAN bus: {self.bus.channel_info if self.bus else 'N/A'}")
                return # Exit on successful connection
            except can.CanError as e:
                logger.error(f"CAN connection error (Attempt {attempt + 1}): {e}", exc_info=True)
            except Exception as e:
                logger.error(f"Unexpected error connecting to CAN bus (Attempt {attempt + 1}): {e}", exc_info=True)
            
            if self.bus: # Ensure bus is None if connection failed
                try:
                    self.bus.shutdown()
                except Exception:
                    pass # Ignore errors during shutdown of a failed bus
                self.bus = None

            if attempt < retries:
                logger.info(f"Retrying CAN connection in {retry_delay} seconds...")
                if self._stop_event.wait(retry_delay): # Allow interruption if stopping
                    logger.info("CAN connection retry aborted due to stop signal.")
                    break 
        
        self.is_connected = False
        logger.error("Failed to connect to CAN bus after all retries.")

    def _parse_can_message(self, msg: can.Message) -> List[Dict[str, Any]]:
        """
        Parses a raw CAN message based on loaded definitions.
        A single CAN message ID might have multiple signals defined.
        """
        parsed_data_list = []
        if msg.arbitration_id in self.message_definitions:
            definitions = self.message_definitions[msg.arbitration_id]
            for definition in definitions:
                parser_cfg = definition["parser_config"]
                name = definition["name"]
                try:
                    if parser_cfg["type"] == "simple_scalar":
                        start_byte = parser_cfg["start_byte"]
                        length = parser_cfg["length_bytes"]
                        byte_order = parser_cfg["byte_order"]
                        is_signed = parser_cfg["is_signed"]
                        scale = parser_cfg["scale"]
                        offset = parser_cfg["offset"]

                        if start_byte + length > len(msg.data):
                            logger.warning(f"CAN parser for '{name}' (ID {msg.arbitration_id:#0x}): data length too short. "
                                           f"Need {start_byte + length} bytes, got {len(msg.data)}.")
                            continue

                        raw_bytes = msg.data[start_byte : start_byte + length]
                        
                        if byte_order == 'little':
                            raw_value = int.from_bytes(raw_bytes, byteorder='little', signed=is_signed)
                        else: # Default to big-endian
                            raw_value = int.from_bytes(raw_bytes, byteorder='big', signed=is_signed)
                        
                        final_value = (raw_value * scale) + offset
                        
                        parsed_data_list.append({
                            "timestamp": msg.timestamp, # CAN message timestamp
                            "name": name,
                            "value": round(final_value, 4) if isinstance(final_value, float) else final_value
                        })
                        logger.debug(f"Parsed CAN ID {msg.arbitration_id:#0x} ('{name}'): raw={raw_value}, final={final_value}")
                except Exception as e:
                    logger.error(f"Error parsing CAN message ID {msg.arbitration_id:#0x} for signal '{name}': {e}", exc_info=False)
        return parsed_data_list


    def _listener_loop(self) -> None:
        """Continuously listens for CAN messages and processes them."""
        logger.info("CAN listener thread started.")
        receive_timeout = self.config.get("receive_timeout_seconds", 1.0)

        while not self._stop_event.is_set() and self.is_connected and self.bus:
            try:
                msg = self.bus.recv(timeout=receive_timeout)
                if msg is not None:
                    logger.debug(f"Raw CAN Rcvd: ID={msg.arbitration_id:#05x} DLC={msg.dlc} Data={' '.join(f'{b:02X}' for b in msg.data)}")
                    parsed_items = self._parse_can_message(msg)
                    for item in parsed_items:
                        try:
                            self.data_queue.put_nowait(item) # Use put_nowait to avoid blocking if queue is full
                        except Full:
                            logger.warning(f"CAN data queue is full. Discarding message for '{item.get('name')}'. Consider increasing queue size or processing speed.")
                # else: timeout, no message received, which is normal.
            except can.CanError as e:
                logger.error(f"CAN bus error in listener loop: {e}. Attempting to reconnect...", exc_info=True)
                self.is_connected = False # Mark as disconnected
                self.bus.shutdown() # Shutdown current bus
                self.bus = None
                self._connect() # Attempt to reconnect
                if not self.is_connected: # If reconnect fails, stop the loop
                    logger.error("Failed to re-establish CAN connection. Stopping listener thread.")
                    break
            except Exception as e:
                logger.error(f"Unexpected error in CAN listener loop: {e}", exc_info=True)
                # Add a small delay to prevent rapid error looping
                time.sleep(1) 
        
        logger.info("CAN listener thread stopped.")

    def start_listener(self) -> None:
        """Starts the CAN message listener thread."""
        if not self.is_connected:
            logger.warning("CAN bus not connected. Cannot start listener thread.")
            return

        if self._listener_thread is not None and self._listener_thread.is_alive():
            logger.warning("CAN listener thread is already running.")
            return

        self._stop_event.clear()
        self._listener_thread = threading.Thread(target=self._listener_loop, name="CANListenerThread")
        self._listener_thread.daemon = True
        self._listener_thread.start()

    def stop_listener(self) -> None:
        """Stops the CAN message listener thread."""
        logger.info("Stopping CAN listener thread...")
        self._stop_event.set()
        if self._listener_thread and self._listener_thread.is_alive():
            self._listener_thread.join(timeout=self.config.get("receive_timeout_seconds", 1.0) + 1)
            if self._listener_thread.is_alive():
                logger.warning("CAN listener thread did not join in time.")
        self._listener_thread = None
        logger.info("CAN listener thread stop signal sent.")

    def close(self) -> None:
        """Stops the listener and closes the CAN bus connection."""
        self.stop_listener() # Ensure thread is stopped first
        if self.bus:
            try:
                logger.info("Shutting down CAN bus interface...")
                self.bus.shutdown()
                logger.info("CAN bus interface shut down.")
            except Exception as e:
                logger.error(f"Error shutting down CAN bus: {e}", exc_info=True)
        self.is_connected = False
        self.bus = None

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG,
                        format='%(asctime)s - %(name)s - %(levelname)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s')

    # For testing, you might need a virtual CAN interface:
    # sudo modprobe vcan
    # sudo ip link add dev vcan0 type vcan
    # sudo ip link set up vcan0
    #
    # Then you can send messages using cansend from can-utils:
    # cansend vcan0 123#1122334455667788

    test_can_config = {
        "enabled": True,
        "interface_type": "socketcan",  # Use 'virtual' if using slcan with a virtual com port for testing
        "channel": "vcan0",            # Or your actual CAN interface
        "bitrate": 500000,
        "message_definitions": [
            {
                "id": "0x123",
                "name": "EngineSpeed",
                "parser": {
                    "type": "simple_scalar",
                    "start_byte": 0,
                    "length_bytes": 2,
                    "scale": 0.25, # Example: (Byte0*256 + Byte1) * 0.25 RPM
                    "offset": 0,
                    "is_signed": False,
                    "byte_order": "big"
                }
            },
            {
                "id": "0x123", # Same ID, different signal
                "name": "CoolantTemp",
                "parser": {
                    "type": "simple_scalar",
                    "start_byte": 2,
                    "length_bytes": 1,
                    "scale": 1,
                    "offset": -40, # Example: Byte2 - 40 deg C
                    "is_signed": False, # Temps are usually unsigned offsets
                    "byte_order": "big"
                }
            },
            {
                "id": "0x456",
                "name": "OilPressure",
                "parser": {
                    "type": "simple_scalar",
                    "start_byte": 1,
                    "length_bytes": 1,
                    "scale": 0.5, # PSI
                    "offset": 0,
                    "is_signed": False,
                    "byte_order": "big"
                }
            }
        ],
        "receive_timeout_seconds": 1.0,
        "connection_retries": 1
    }

    q = Queue(maxsize=100) # Max 100 items in queue
    can_handler = CANHandler(test_can_config, q)

    if can_handler.is_connected:
        can_handler.start_listener()
        logger.info("CAN Handler listener started. Listening for messages for 20 seconds...")
        logger.info("Try sending messages: e.g., 'cansend vcan0 123#AABBCCDD' or 'cansend vcan0 456#0078'")
        
        end_time = time.time() + 20
        try:
            while time.time() < end_time:
                try:
                    data = q.get(timeout=0.5) # Wait up to 0.5s for an item
                    logger.info(f"Received from queue: {data}")
                    q.task_done() # Important for JoinableQueue, good practice for Queue
                except Empty:
                    pass # No item in queue
                except KeyboardInterrupt:
                    logger.info("Keyboard interrupt during queue read.")
                    break
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt, stopping test.")
        finally:
            can_handler.close() # This will also stop the listener
            logger.info("CAN Handler test finished.")
    else:
        logger.error("CAN Handler failed to connect. Test aborted.")

