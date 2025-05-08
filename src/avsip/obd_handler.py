# src/avsip/obd_handler.py

import logging
import time
import obd # Import the python-obd library
from typing import List, Tuple, Dict, Any, Optional

logger = logging.getLogger(__name__)

# Define a mapping from common AVSIP command names to python-obd command names if they differ
# For now, we assume they are the same and are uppercase (e.g., "RPM", "SPEED")
# This can be expanded if needed, e.g., {"engine_rpm": "RPM"}
OBD_COMMAND_MAP = {}

class OBDHandler:
    """
    Handles communication with an OBD-II adapter for AVSIP.
    - Establishes connection to the OBD-II adapter.
    - Queries specified OBD-II commands.
    - Retrieves Diagnostic Trouble Codes (DTCs).
    """

    def __init__(self, config: dict):
        """
        Initializes the OBDHandler.

        Args:
            config: A dictionary containing OBD specific configuration:
                {
                    "enabled": True,
                    "port_string": "/dev/ttyUSB0" or None for auto,
                    "baudrate": None or specific rate,
                    "protocol": None or specific protocol ID string,
                    "fast_commands": True,
                    "commands": ["RPM", "SPEED", "COOLANT_TEMP"],
                    "include_dtc_codes": True,
                    "connection_retries": 3,
                    "retry_delay_seconds": 5
                }
        """
        self.config = config
        self.connection: Optional[obd.OBD] = None
        self.is_connected: bool = False
        self.supported_commands: List[obd.OBDCommand] = []

        if not self.config.get("enabled", False):
            logger.info("OBDHandler is disabled in configuration.")
            return

        self._connect()

    def _connect(self) -> None:
        """Attempts to connect to the OBD-II adapter."""
        port_string = self.config.get("port_string")
        baudrate = self.config.get("baudrate")
        protocol_id = self.config.get("protocol")
        fast = self.config.get("fast_commands", True)
        retries = self.config.get("connection_retries", 3)
        retry_delay = self.config.get("retry_delay_seconds", 5)

        for attempt in range(retries + 1):
            try:
                logger.info(
                    f"Attempting to connect to OBD-II adapter (Attempt {attempt + 1}/{retries + 1}). "
                    f"Port: {port_string if port_string else 'auto-detect'}, Baud: {baudrate}, "
                    f"Protocol: {protocol_id}, Fast: {fast}"
                )
                # obd.OBD() can block for a while during auto-detection
                # If a specific port is given, it's usually faster.
                self.connection = obd.OBD(
                    portstr=port_string,
                    baudrate=baudrate,
                    protocol=protocol_id,
                    fast=fast,
                    timeout=self.config.get("connection_timeout_seconds", 30) # OBD connection timeout
                )

                if self.connection.is_connected():
                    self.is_connected = True
                    logger.info(f"Successfully connected to OBD-II adapter. Status: {self.connection.status()}")
                    self._check_supported_commands()
                    return
                else:
                    logger.warning(f"OBD-II connection attempt {attempt + 1} failed. Status: {self.connection.status()}")
                    # Ensure connection is None if it failed but didn't raise an exception
                    if self.connection:
                        self.connection.close()
                    self.connection = None

            except Exception as e: # Catching broader exceptions as python-obd can raise various things
                logger.error(f"Error connecting to OBD-II adapter (Attempt {attempt + 1}): {e}", exc_info=True)
                if self.connection: # Ensure it's closed if partially opened
                    self.connection.close()
                self.connection = None
            
            if attempt < retries:
                logger.info(f"Retrying OBD-II connection in {retry_delay} seconds...")
                time.sleep(retry_delay)

        self.is_connected = False
        logger.error("Failed to connect to OBD-II adapter after all retries.")


    def _check_supported_commands(self) -> None:
        """
        Checks which of the configured commands are supported by the vehicle
        and stores them.
        """
        if not self.is_connected or not self.connection:
            return

        configured_command_names = self.config.get("commands", [])
        self.supported_commands = [] # Reset
        
        logger.info("Checking for supported OBD-II commands...")
        # Query for the list of supported commands from the ECU
        # This itself is an OBD command (e.g., PID 00 for mode 01)
        # The python-obd library handles this when we query obd.commands
        
        available_obd_commands = {cmd.name: cmd for cmd in obd.commands.PIDS[1]} # Mode 01 PIDs

        for cmd_name in configured_command_names:
            actual_cmd_name = OBD_COMMAND_MAP.get(cmd_name.lower(), cmd_name.upper())
            if actual_cmd_name in available_obd_commands:
                command_to_check = available_obd_commands[actual_cmd_name]
                # The library's support check is more reliable than just checking presence in ECU's list
                if self.connection.supports(command_to_check):
                    self.supported_commands.append(command_to_check)
                    logger.debug(f"Command '{actual_cmd_name}' is supported by vehicle.")
                else:
                    logger.warning(f"Command '{actual_cmd_name}' configured but NOT supported by vehicle.")
            else:
                logger.warning(f"Command '{actual_cmd_name}' (from '{cmd_name}') is not a recognized python-obd command name.")
        
        if not self.supported_commands:
            logger.warning("No configured OBD-II commands are supported by the vehicle or recognized by the library.")
        else:
            logger.info(f"Supported configured commands: {[cmd.name for cmd in self.supported_commands]}")


    def read_data(self) -> Tuple[Dict[str, Any], List[str]]:
        """
        Reads data for the configured and supported OBD-II commands and DTCs.

        Returns:
            A tuple containing:
                - A dictionary of sensor values (e.g., {"RPM": 1500, "SPEED": 60}).
                - A list of DTC strings (e.g., ["P0101", "C0300"]).
        """
        sensor_values: Dict[str, Any] = {}
        dtc_codes: List[str] = []

        if not self.is_connected or not self.connection:
            logger.warning("Not connected to OBD-II, cannot read data.")
            # Attempt to reconnect if not connected
            # self._connect() # Be careful about recursion or too frequent retries here
            # if not self.is_connected:
            return sensor_values, dtc_codes

        # Check vehicle status, if not running, some commands might not be available
        # or it might be desirable to not query.
        vehicle_status = self.connection.status()
        if vehicle_status not in [obd.OBDStatus.CAR_CONNECTED, obd.OBDStatus.OBD_CONNECTED, obd.OBDStatus.ELM_CONNECTED]:
             logger.warning(f"Vehicle status is '{vehicle_status}'. OBD data might be unavailable or inaccurate.")
             # Depending on policy, we might return empty or try anyway. For now, try anyway.

        logger.debug(f"Reading data for supported commands: {[cmd.name for cmd in self.supported_commands]}")
        for command in self.supported_commands:
            try:
                response = self.connection.query(command, force=True) # Force to bypass ECU's support list sometimes
                if response is not None and not response.is_null():
                    # Sanitize command name for key (e.g., "SPEED" -> "speed_kph")
                    # For now, using the command name directly, but lowercase.
                    # Units are important. python-obd usually returns Pint quantities.
                    # We should extract the magnitude and ideally note the unit.
                    key_name = command.name.lower()
                    value = response.value
                    
                    if hasattr(value, 'magnitude'): # Check if it's a Pint Quantity
                        sensor_values[key_name] = round(value.magnitude, 2) if isinstance(value.magnitude, float) else value.magnitude
                        # sensor_values[f"{key_name}_unit"] = str(value.units) # Optionally include units
                    else: # If it's not a Pint quantity (e.g. string, tuple)
                        sensor_values[key_name] = value 

                    logger.debug(f"OBD Read: {command.name} = {response.value}")
                else:
                    logger.debug(f"OBD Read: {command.name} = No response or null value.")
                    sensor_values[command.name.lower()] = None # Indicate no data
            except Exception as e:
                logger.warning(f"Error querying OBD-II command {command.name}: {e}", exc_info=False) # Keep log less noisy
                sensor_values[command.name.lower()] = None # Indicate error

        if self.config.get("include_dtc_codes", True):
            try:
                dtc_response = self.connection.query(obd.commands.GET_DTC, force=True) # Query for DTCs
                if dtc_response is not None and not dtc_response.is_null() and dtc_response.value:
                    # dtc_response.value is usually a list of tuples (DTC_CODE, DESCRIPTION)
                    dtc_codes = [dtc_tuple[0] for dtc_tuple in dtc_response.value]
                    logger.info(f"DTCs retrieved: {dtc_codes}")
                elif dtc_response is not None and not dtc_response.value: # Empty list means no DTCs
                    logger.debug("No active DTCs found.")
                else:
                    logger.debug("No DTC response or null value for GET_DTC.")
            except Exception as e:
                logger.warning(f"Error reading DTC codes: {e}", exc_info=False)
        
        return sensor_values, dtc_codes

    def close(self) -> None:
        """Closes the connection to the OBD-II adapter."""
        if self.connection:
            try:
                logger.info("Closing OBD-II connection...")
                self.connection.close()
                logger.info("OBD-II connection closed.")
            except Exception as e:
                logger.error(f"Error closing OBD-II connection: {e}", exc_info=True)
        self.is_connected = False
        self.connection = None


if __name__ == "__main__":
    # Example Usage (requires a vehicle with OBD-II adapter connected)
    logging.basicConfig(level=logging.DEBUG,
                        format='%(asctime)s - %(name)s - %(levelname)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s')

    # --- IMPORTANT ---
    # For this test to run, you need an OBD-II adapter connected to your computer
    # and the vehicle's ignition should be ON, or the engine running.
    #
    # Update "port_string" to your adapter's port (e.g., "/dev/ttyUSB0", "/dev/rfcomm0" for Bluetooth,
    # or None to attempt auto-detection, which can be slow).
    #
    # If using Bluetooth, ensure it's paired and the RFCOMM channel is set up if needed.
    # For example, on Linux:
    #   sudo rfcomm bind 0 AA:BB:CC:DD:EE:FF 1  (replace AA:BB... with your adapter's MAC)
    #   Then use "/dev/rfcomm0" as the port_string.
    # --- /IMPORTANT ---

    test_obd_config = {
        "enabled": True,
        "port_string": None,  # SET THIS TO YOUR ADAPTER'S PORT or None for auto-detect
        "baudrate": None,       # None for auto
        "protocol": None,       # None for auto
        "fast_commands": True,
        "commands": ["RPM", "SPEED", "COOLANT_TEMP", "FUEL_LEVEL", "ENGINE_LOAD", "THROTTLE_POS"],
        "include_dtc_codes": True,
        "connection_retries": 1, # Fewer retries for direct test
        "retry_delay_seconds": 2,
        "connection_timeout_seconds": 45 # Longer timeout for initial connection/scan
    }

    logger.info("Starting OBDHandler direct test...")
    obd_handler = OBDHandler(test_obd_config)

    if obd_handler.is_connected:
        logger.info("OBDHandler connected. Reading data for 15 seconds...")
        for i in range(5): # Read data a few times
            logger.info(f"--- Reading cycle {i+1} ---")
            sensors, dtcs = obd_handler.read_data()
            if sensors:
                logger.info(f"Sensor Values: {sensors}")
            else:
                logger.info("No sensor values retrieved.")
            if dtcs:
                logger.info(f"DTCs: {dtcs}")
            else:
                logger.info("No DTCs retrieved (or feature disabled).")
            
            if i < 4 : time.sleep(3) # Wait before next read, unless it's the last one

        obd_handler.close()
    else:
        logger.error("OBDHandler failed to connect. Test aborted.")
    
    logger.info("OBDHandler direct test finished.")
