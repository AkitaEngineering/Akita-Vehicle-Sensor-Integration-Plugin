# src/avsip/core.py

import logging
import threading
import time
import json
from queue import Queue, Empty # For potential future inter-thread communication

from . import config_manager
from . import utils
from .meshtastic_handler import MeshtasticHandler # Import the actual handler
# Placeholder for actual handler imports - will be created later
# from .obd_handler import OBDHandler
# from .can_handler import CANHandler
# from .mqtt_handler import MQTTHandler
# from .traccar_handler import TraccarHandler

# Initialize a module-level logger
logger = logging.getLogger(__name__)

class AVSIP:
    """
    Akita Vehicle Sensor Integration Plugin (AVSIP) core class.
    Manages sensor data acquisition, processing, and transmission.
    """

    def __init__(self, config_file_path: str = "avsip_config.json"):
        """
        Initializes the AVSIP application.

        Args:
            config_file_path: Path to the AVSIP configuration JSON file.
        """
        self.config = config_manager.load_config(config_file_path)
        self._configure_logging()

        logger.info("Initializing AVSIP...")
        logger.debug(f"Loaded configuration: {json.dumps(self.config, indent=2)}")

        self.avsip_device_id: str = "unknown_avsip_device" # Will be set by Meshtastic handler or config

        # --- Handlers ---
        self.meshtastic_handler: MeshtasticHandler | None = None # Type hint
        self.obd_handler = None
        self.can_handler = None
        self.mqtt_handler = None
        self.traccar_handler = None
        
        # --- Rate Limiters ---
        self.traccar_rate_limiter = None
        if self.config.get("traccar", {}).get("enabled"):
            report_interval = self.config["traccar"].get("report_interval_seconds", 30)
            self.traccar_rate_limiter = utils.RateLimiter(report_interval)


        # --- Threading Control ---
        self._stop_event = threading.Event()
        self._data_thread = None
        # self._threads = [] # To keep track of all started threads for graceful shutdown
                           # Meshtastic lib handles its own threads, CAN might need one.

        # --- Data Storage ---
        self.current_sensor_data: dict = {} # Stores the latest aggregated sensor data
        self.data_queue = Queue() # For passing data between threads if needed (e.g. from CAN to main)

        self._initialize_handlers() # This will now attempt to set self.avsip_device_id
        
        # Determine final AVSIP device ID based on configuration
        id_source = self.config.get("general", {}).get("device_id_source", "meshtastic_node_id")
        if id_source == "custom" and self.config.get("general", {}).get("custom_device_id"):
            self.avsip_device_id = self.config["general"]["custom_device_id"]
            logger.info(f"Using custom AVSIP Device ID: {self.avsip_device_id}")
        elif id_source == "meshtastic_node_id" and self.meshtastic_handler and self.meshtastic_handler.is_connected:
            # This was already attempted in _initialize_handlers, just confirming
            if not self.avsip_device_id or self.avsip_device_id == "unknown_avsip_device": # if it failed during init
                 retrieved_id = self.meshtastic_handler.get_device_id()
                 if retrieved_id:
                     self.avsip_device_id = retrieved_id
                     logger.info(f"AVSIP Device ID set from Meshtastic: {self.avsip_device_id}")
                 else:
                     logger.error("Failed to get AVSIP device ID from Meshtastic. Using fallback.")
                     self.avsip_device_id = f"fallback_{int(time.time())}" # Unique fallback
            # else: ID was already set
        else:
            if id_source == "meshtastic_node_id":
                 logger.warning(f"Configured to use Meshtastic Node ID as device_id, but Meshtastic handler is not available or failed. Using fallback.")
            else: # Should not happen if config validation is good
                 logger.warning(f"Unknown device_id_source '{id_source}'. Using fallback.")
            self.avsip_device_id = f"fallback_{int(time.time())}"
        
        logger.info(f"Final AVSIP Device ID: {self.avsip_device_id}")
        
        # Re-initialize handlers that depend on the final avsip_device_id (MQTT, Traccar)
        # This is a bit clunky; a better design might pass the core AVSIP instance or a shared context.
        # For now, we re-initialize if they were enabled.
        self._reinitialize_dependent_handlers()

        logger.info("AVSIP initialization complete.")

    def _configure_logging(self):
        """Configures the logging system based on the loaded configuration."""
        log_level_str = self.config.get("general", {}).get("log_level", "INFO").upper()
        log_level = getattr(logging, log_level_str, logging.INFO)
        
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        # Suppress overly verbose logs from specific libraries if needed
        logging.getLogger("meshtastic").setLevel(logging.INFO) # Meshtastic can be chatty on DEBUG
        # logging.getLogger("paho").setLevel(logging.WARNING)
        logger.info(f"Logging configured to level: {log_level_str}")


    def _initialize_handlers(self):
        """Initializes and starts all configured data handlers."""
        logger.info("Initializing handlers (first pass)...")

        # Meshtastic Handler (Core for device ID and potentially GPS)
        meshtastic_config = self.config.get("meshtastic", {})
        if meshtastic_config.get("enabled", True): # Default True as it's core
            try:
                self.meshtastic_handler = MeshtasticHandler(meshtastic_config)
                if self.meshtastic_handler.is_connected:
                    retrieved_id = self.meshtastic_handler.get_device_id()
                    if retrieved_id:
                        self.avsip_device_id = retrieved_id # Tentative ID
                        logger.info(f"Meshtastic handler initialized. Tentative AVSIP Device ID: {self.avsip_device_id}")
                    else:
                        logger.warning("Meshtastic handler connected but failed to retrieve a device ID.")
                else:
                    logger.warning("MeshtasticHandler initialized but not connected to a device.")
            except Exception as e:
                logger.error(f"Failed to initialize MeshtasticHandler: {e}", exc_info=True)
        else:
            logger.info("Meshtastic component is explicitly disabled in config.")


        # OBD Handler
        if self.config.get("obd", {}).get("enabled"):
            try:
                # self.obd_handler = OBDHandler(self.config.get("obd", {}))
                logger.info("OBDHandler initialized (placeholder).")
            except Exception as e:
                logger.error(f"Failed to initialize OBDHandler: {e}", exc_info=True)
                self.config["obd"]["enabled"] = False

        # CAN Handler
        if self.config.get("can", {}).get("enabled"):
            try:
                # self.can_handler = CANHandler(self.config.get("can", {}), self.data_queue)
                # self._threads.append(self.can_handler.get_thread())
                logger.info("CANHandler initialized (placeholder).")
            except Exception as e:
                logger.error(f"Failed to initialize CANHandler: {e}", exc_info=True)
                self.config["can"]["enabled"] = False
        
        # MQTT and Traccar will be initialized in _reinitialize_dependent_handlers
        # after the final avsip_device_id is determined.
        logger.info("Handler initialization (first pass) complete.")

    def _reinitialize_dependent_handlers(self):
        """Initializes handlers that depend on the final avsip_device_id."""
        logger.info("Re-initializing device ID dependent handlers...")
        # MQTT Handler
        if self.config.get("mqtt", {}).get("enabled"):
            if self.mqtt_handler: # If it was somehow initialized before (should not happen with current logic)
                logger.info("MQTT Handler was already initialized. Cleaning up before re-init.")
                # self.mqtt_handler.disconnect() # Assuming a disconnect method
            try:
                # self.mqtt_handler = MQTTHandler(self.config.get("mqtt", {}), self.avsip_device_id)
                logger.info(f"MQTTHandler initialized with device ID {self.avsip_device_id} (placeholder).")
            except Exception as e:
                logger.error(f"Failed to initialize MQTTHandler: {e}", exc_info=True)
                self.config["mqtt"]["enabled"] = False

        # Traccar Handler
        if self.config.get("traccar", {}).get("enabled"):
            if self.traccar_handler:
                logger.info("Traccar Handler was already initialized. No re-init needed unless device ID changed it.")
            try:
                # Determine Traccar device ID
                traccar_device_id = self.avsip_device_id # Default to AVSIP device ID
                traccar_id_source = self.config.get("traccar",{}).get("device_id_source", "avsip_device_id")
                if traccar_id_source == "custom_traccar_id":
                    custom_id = self.config.get("traccar",{}).get("custom_traccar_id")
                    if custom_id:
                        traccar_device_id = custom_id
                    else:
                        logger.warning("Traccar device_id_source is 'custom_traccar_id' but no custom ID provided. Using AVSIP device ID.")
                
                # self.traccar_handler = TraccarHandler(self.config.get("traccar", {}), traccar_device_id)
                logger.info(f"TraccarHandler initialized with Traccar device ID {traccar_device_id} (placeholder).")
            except Exception as e:
                logger.error(f"Failed to initialize TraccarHandler: {e}", exc_info=True)
                self.config["traccar"]["enabled"] = False


    def _collect_data(self) -> dict | None:
        """Collects data from all enabled sensor handlers."""
        # Ensure we have a valid device ID, otherwise data collection might be pointless for some outputs
        if not self.avsip_device_id or self.avsip_device_id.startswith("unknown") or self.avsip_device_id.startswith("fallback"):
            logger.warning(f"AVSIP device ID is not properly set ('{self.avsip_device_id}'). Data might not be processed correctly by outputs.")
            # Depending on strictness, one might return None here if a valid ID is critical.

        collected_data = {
            "timestamp_utc": time.time(),
            "device_id": self.avsip_device_id,
            "sensors": {},
            "gps": {},
            "dtcs": [],
            "can_data": {}
        }

        # GPS Data
        if self.meshtastic_handler and self.meshtastic_handler.is_connected:
            gps_payload = self.meshtastic_handler.get_gps_data()
            if gps_payload:
               collected_data["gps"] = gps_payload
               logger.debug(f"GPS data collected: {gps_payload}")
            else:
                logger.debug("No GPS data available from Meshtastic this cycle.")
        elif self.config.get("meshtastic",{}).get("enabled"):
            logger.warning("Meshtastic enabled but handler not available or not connected for GPS.")


        # OBD Data
        if self.config.get("obd", {}).get("enabled") and self.obd_handler:
            # obd_values, dtc_list = self.obd_handler.read_data()
            # if obd_values:
            #     collected_data["sensors"].update(obd_values)
            # if dtc_list:
            #     collected_data["dtcs"] = dtc_list
            collected_data["sensors"]["rpm"] = 1500 # Placeholder
            collected_data["sensors"]["speed_kph"] = 60 # Placeholder
            collected_data["dtcs"] = ["P0101"] # Placeholder
            logger.debug("Collected OBD data (placeholder).")


        # CAN Data
        if self.config.get("can", {}).get("enabled") and self.can_handler:
            # try:
            #     while not self.data_queue.empty():
            #         can_msg = self.data_queue.get_nowait()
            #         if can_msg and isinstance(can_msg, dict) and 'name' in can_msg and 'value' in can_msg:
            #             collected_data["can_data"][can_msg['name']] = can_msg['value']
            #         self.data_queue.task_done()
            # except Empty:
            #     pass
            collected_data["can_data"]["oil_pressure_psi"] = 60 # Placeholder
            logger.debug("Collected CAN data (placeholder).")

        # Only return data if we have something other than just timestamp and device_id
        if collected_data["sensors"] or collected_data["gps"] or collected_data["dtcs"] or collected_data["can_data"]:
            self.current_sensor_data = collected_data
            logger.debug(f"Aggregated sensor data: {json.dumps(self.current_sensor_data, indent=2, default=str)}")
            return self.current_sensor_data
        else:
            logger.debug("No new sensor, GPS, DTC, or CAN data collected in this cycle.")
            return None


    def _process_and_transmit_data(self, data: dict):
        """Processes and transmits data to enabled output handlers."""
        if not data: # Should be caught by caller, but double check
            logger.warning("No data provided to _process_and_transmit_data.")
            return

        logger.debug(f"Processing and transmitting data for device {data.get('device_id', 'N/A')}")

        # Meshtastic Transmission
        if self.config.get("meshtastic", {}).get("enabled") and self.meshtastic_handler and self.meshtastic_handler.is_connected:
            # We might want to send a subset of data or a specially formatted packet via Meshtastic
            # For now, sending the whole thing (could be large)
            if self.meshtastic_handler.send_data(data):
                 logger.info("Data sent via Meshtastic.")
            else:
                 logger.warning("Failed to send data via Meshtastic.")


        # MQTT Transmission
        if self.config.get("mqtt", {}).get("enabled") and self.mqtt_handler:
            # self.mqtt_handler.publish_data(data)
            logger.info("Data sent via MQTT (placeholder).")

        # Traccar Transmission
        if self.config.get("traccar", {}).get("enabled") and self.traccar_handler and self.traccar_rate_limiter:
            if data.get("gps") and data["gps"].get("latitude") != 0.0 and data["gps"].get("longitude") != 0.0 : # Only send if GPS is valid
                if self.traccar_rate_limiter.try_trigger():
                    # self.traccar_handler.send_data(data)
                    logger.info("Data sent via Traccar (placeholder).")
                else:
                    logger.debug(f"Traccar send rate limited. Next attempt in {self.traccar_rate_limiter.time_to_next_trigger():.1f}s")
            else:
                logger.debug("Skipping Traccar transmission due to missing or invalid GPS data.")


    def _data_loop(self):
        """Main data collection and transmission loop. Runs in a separate thread."""
        logger.info("Data loop started.")
        data_interval = self.config.get("general", {}).get("data_interval_seconds", 10)

        while not self._stop_event.is_set():
            loop_start_time = time.monotonic()
            try:
                logger.debug("Starting new data collection cycle.")
                collected_data = self._collect_data()
                if collected_data: # Check if any data was actually collected
                    self._process_and_transmit_data(collected_data)
                # else: No new data, just wait for next interval. Logged in _collect_data

            except Exception as e:
                logger.error(f"Critical error in data loop: {e}", exc_info=True)
                # Consider a small delay after a critical error before retrying
                if self._stop_event.wait(min(data_interval, 5.0)): # Shorter wait after error
                    break

            loop_duration = time.monotonic() - loop_start_time
            sleep_time = max(0.1, data_interval - loop_duration) # Ensure at least a small sleep

            if self._stop_event.wait(sleep_time):
                break 
            
        logger.info("Data loop stopped.")

    def start(self):
        """Starts the AVSIP data collection and transmission thread."""
        if self._data_thread is not None and self._data_thread.is_alive():
            logger.warning("AVSIP data loop is already running.")
            return

        logger.info("Starting AVSIP data loop...")
        self._stop_event.clear()
        
        # Start handler-specific threads if they exist and need to be managed here
        # Example: if self.can_handler and hasattr(self.can_handler, 'start_thread'):
        # self.can_handler.start_thread()

        self._data_thread = threading.Thread(target=self._data_loop, name="AVSIPDataLoop")
        self._data_thread.daemon = True
        self._data_thread.start()
        logger.info("AVSIP data loop thread started.")

    def stop(self):
        """Stops the AVSIP data collection and transmission thread and cleans up resources."""
        logger.info("Stopping AVSIP...")
        self._stop_event.set()

        # Stop handler-specific threads
        # Example: if self.can_handler and hasattr(self.can_handler, 'stop_thread'):
        #    self.can_handler.stop_thread() # This method should signal its internal thread to stop
        #    # Then join the thread here or in the handler's own stop method.

        if self._data_thread is not None and self._data_thread.is_alive():
            logger.debug("Waiting for data loop thread to join...")
            self._data_thread.join(timeout=self.config.get("general",{}).get("data_interval_seconds",10) + 5) # Increased timeout
            if self._data_thread.is_alive():
                 logger.warning("Data loop thread did not join in time.")

        logger.info("Cleaning up handlers...")
        if self.meshtastic_handler:
            self.meshtastic_handler.close()
        # if self.obd_handler: self.obd_handler.close()
        # if self.mqtt_handler: self.mqtt_handler.disconnect()
        # if self.can_handler: self.can_handler.stop() # Assuming CAN handler manages its own resources/thread cleanup

        logger.info("AVSIP stopped.")

if __name__ == "__main__":
    import os # Ensure os is imported for the __main__ block
    # This is an example of how to run AVSIP.
    # In a real deployment, you might have a separate run.py script.

    # Create a dummy config for direct execution testing
    if not os.path.exists("avsip_config.json"):
        dummy_cfg = {
            "general": {
                "log_level": "DEBUG", 
                "data_interval_seconds": 7,
                "device_id_source": "meshtastic_node_id" # or "custom"
                # "custom_device_id": "my_vehicle_001" 
            },
            "meshtastic": {
                "enabled": True,
                "device_port": None, # Auto-detect
                "data_port_num": 251
            },
            # "obd": {"enabled": True, "commands": ["RPM"]}, 
            # "mqtt": {"enabled": True, "host": "test.mosquitto.org", "topic_prefix": "vehicle/avsip_test"}, 
            # "traccar": {"enabled": True, "host": "demo.traccar.org", "device_id_source": "avsip_device_id"}
        }
        with open("avsip_config.json", "w") as f:
            json.dump(dummy_cfg, f, indent=2)
        print("Created a dummy avsip_config.json for testing core.py. Please ensure a Meshtastic device is connected.")

    avsip_app = None
    try:
        avsip_app = AVSIP(config_file_path="avsip_config.json")
        avsip_app.start()
        
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received. Stopping AVSIP...")
    except Exception as e:
        logger.critical(f"Unhandled exception in main: {e}", exc_info=True)
    finally:
        if avsip_app:
            avsip_app.stop()
        # Clean up dummy config to avoid interfering with subsequent runs if it was created by this script
        # Check if dummy_cfg was defined in this scope, implying it was created here.
        if 'dummy_cfg' in locals() and os.path.exists("avsip_config.json"): 
            # os.remove("avsip_config.json")
            # logger.info("Dummy avsip_config.json removed.")
            print("Note: Dummy avsip_config.json was NOT removed for inspection. Please remove it manually if desired.")


    logger.info("AVSIP application finished.")
