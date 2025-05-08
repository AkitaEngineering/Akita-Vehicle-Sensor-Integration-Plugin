# src/avsip/core.py

import logging
import threading
import time
import json
from queue import Queue, Empty # For potential future inter-thread communication

from . import config_manager
from . import utils
from .meshtastic_handler import MeshtasticHandler
from .obd_handler import OBDHandler # Import the actual OBD handler
# Placeholder for actual handler imports - will be created later
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
        self.meshtastic_handler: MeshtasticHandler | None = None
        self.obd_handler: OBDHandler | None = None # Type hint for OBDHandler
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

        # --- Data Storage ---
        self.current_sensor_data: dict = {}
        self.data_queue = Queue()

        self._initialize_handlers()
        
        # Determine final AVSIP device ID
        id_source = self.config.get("general", {}).get("device_id_source", "meshtastic_node_id")
        if id_source == "custom" and self.config.get("general", {}).get("custom_device_id"):
            self.avsip_device_id = self.config["general"]["custom_device_id"]
        elif id_source == "meshtastic_node_id":
            if self.meshtastic_handler and self.meshtastic_handler.is_connected:
                retrieved_id = self.meshtastic_handler.get_device_id()
                if retrieved_id:
                    self.avsip_device_id = retrieved_id
                else: # Handler connected but no ID, or ID was already 'unknown_avsip_device'
                    logger.error("Failed to get AVSIP device ID from Meshtastic. Using fallback.")
                    self.avsip_device_id = f"fallback_{int(time.time())}"
            else: # Meshtastic not enabled or not connected
                logger.warning(f"Configured to use Meshtastic Node ID, but handler not available/connected. Using fallback.")
                self.avsip_device_id = f"fallback_{int(time.time())}"
        else: # Unknown source
            logger.warning(f"Unknown device_id_source '{id_source}'. Using fallback.")
            self.avsip_device_id = f"fallback_{int(time.time())}"
        
        logger.info(f"Final AVSIP Device ID: {self.avsip_device_id}")
        
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
        logging.getLogger("meshtastic").setLevel(logging.INFO)
        logging.getLogger("obd").setLevel(logging.INFO) # Set python-obd log level
        logger.info(f"Logging configured to level: {log_level_str}")


    def _initialize_handlers(self):
        """Initializes core handlers. Dependent handlers are initialized later."""
        logger.info("Initializing handlers (first pass)...")

        # Meshtastic Handler
        meshtastic_config = self.config.get("meshtastic", {})
        if meshtastic_config.get("enabled", True):
            try:
                self.meshtastic_handler = MeshtasticHandler(meshtastic_config)
                if self.meshtastic_handler.is_connected:
                    # Tentative ID set here, will be finalized after this method
                    tentative_id = self.meshtastic_handler.get_device_id()
                    if tentative_id:
                        self.avsip_device_id = tentative_id 
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
        obd_config = self.config.get("obd", {})
        if obd_config.get("enabled"):
            try:
                self.obd_handler = OBDHandler(obd_config) # Instantiate OBDHandler
                if self.obd_handler.is_connected:
                    logger.info("OBDHandler initialized and connected.")
                else:
                    logger.warning("OBDHandler initialized but not connected. OBD features may be unavailable.")
                    # Optionally disable OBD if connection failed critically, or let it retry internally
                    # For now, we assume OBDHandler handles its connection state.
            except Exception as e:
                logger.error(f"Failed to initialize OBDHandler: {e}", exc_info=True)
                self.config["obd"]["enabled"] = False # Disable if init fails catastrophically
        else:
            logger.info("OBD component is disabled in configuration.")


        # CAN Handler
        if self.config.get("can", {}).get("enabled"):
            try:
                # self.can_handler = CANHandler(self.config.get("can", {}), self.data_queue)
                logger.info("CANHandler initialized (placeholder).")
            except Exception as e:
                logger.error(f"Failed to initialize CANHandler: {e}", exc_info=True)
                self.config["can"]["enabled"] = False
        
        logger.info("Handler initialization (first pass) complete.")

    def _reinitialize_dependent_handlers(self):
        """Initializes handlers that depend on the final avsip_device_id."""
        logger.info("Re-initializing device ID dependent handlers...")
        # MQTT Handler
        if self.config.get("mqtt", {}).get("enabled"):
            if self.mqtt_handler: 
                logger.debug("MQTT Handler instance already exists. Disconnecting before re-init.")
                # self.mqtt_handler.disconnect() 
            try:
                # self.mqtt_handler = MQTTHandler(self.config.get("mqtt", {}), self.avsip_device_id)
                logger.info(f"MQTTHandler initialized with device ID {self.avsip_device_id} (placeholder).")
            except Exception as e:
                logger.error(f"Failed to initialize MQTTHandler: {e}", exc_info=True)
                self.config["mqtt"]["enabled"] = False

        # Traccar Handler
        if self.config.get("traccar", {}).get("enabled"):
            if self.traccar_handler:
                 logger.debug("Traccar Handler instance already exists.")
            try:
                traccar_device_id = self.avsip_device_id 
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
        if not self.avsip_device_id or self.avsip_device_id.startswith("unknown") or self.avsip_device_id.startswith("fallback"):
            logger.warning(f"AVSIP device ID is not properly set ('{self.avsip_device_id}'). Data might not be processed correctly by outputs.")

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
            logger.debug("Meshtastic enabled but handler not available or not connected for GPS.")


        # OBD Data
        if self.config.get("obd", {}).get("enabled") and self.obd_handler:
            if self.obd_handler.is_connected:
                obd_values, dtc_list = self.obd_handler.read_data()
                if obd_values:
                    collected_data["sensors"].update(obd_values)
                    logger.debug(f"OBD sensor data collected: {obd_values}")
                if dtc_list:
                    collected_data["dtcs"] = dtc_list
                    logger.debug(f"OBD DTCs collected: {dtc_list}")
            else:
                logger.warning("OBD enabled but handler not connected. Attempting to reconnect OBD.")
                # Potentially add a specific reconnect call or rely on OBDHandler's internal logic if it has periodic retries.
                # For now, OBDHandler tries to connect on init. If it fails, it stays disconnected until AVSIP restarts.
                # A more robust system might have obd_handler.ensure_connected() or similar.
                # self.obd_handler._connect() # Avoid direct call to private method if possible.

        # CAN Data
        if self.config.get("can", {}).get("enabled") and self.can_handler:
            collected_data["can_data"]["oil_pressure_psi"] = 60 # Placeholder
            logger.debug("Collected CAN data (placeholder).")

        if collected_data["sensors"] or collected_data["gps"] or collected_data["dtcs"] or collected_data["can_data"]:
            self.current_sensor_data = collected_data
            logger.debug(f"Aggregated sensor data: {json.dumps(self.current_sensor_data, indent=2, default=str)}")
            return self.current_sensor_data
        else:
            logger.debug("No new sensor, GPS, DTC, or CAN data collected in this cycle.")
            return None


    def _process_and_transmit_data(self, data: dict):
        """Processes and transmits data to enabled output handlers."""
        if not data: 
            logger.warning("No data provided to _process_and_transmit_data.")
            return

        logger.debug(f"Processing and transmitting data for device {data.get('device_id', 'N/A')}")

        # Meshtastic Transmission
        if self.config.get("meshtastic", {}).get("enabled") and self.meshtastic_handler and self.meshtastic_handler.is_connected:
            if self.meshtastic_handler.send_data(data):
                 logger.info("Data sent via Meshtastic.")
            else:
                 logger.warning("Failed to send data via Meshtastic.")

        # MQTT Transmission
        if self.config.get("mqtt", {}).get("enabled") and self.mqtt_handler:
            logger.info("Data sent via MQTT (placeholder).")

        # Traccar Transmission
        if self.config.get("traccar", {}).get("enabled") and self.traccar_handler and self.traccar_rate_limiter:
            if data.get("gps") and data["gps"].get("latitude") != 0.0 and data["gps"].get("longitude") != 0.0 : 
                if self.traccar_rate_limiter.try_trigger():
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
                if collected_data: 
                    self._process_and_transmit_data(collected_data)

            except Exception as e:
                logger.error(f"Critical error in data loop: {e}", exc_info=True)
                if self._stop_event.wait(min(data_interval, 5.0)): 
                    break

            loop_duration = time.monotonic() - loop_start_time
            sleep_time = max(0.1, data_interval - loop_duration) 

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
        
        self._data_thread = threading.Thread(target=self._data_loop, name="AVSIPDataLoop")
        self._data_thread.daemon = True
        self._data_thread.start()
        logger.info("AVSIP data loop thread started.")

    def stop(self):
        """Stops the AVSIP data collection and transmission thread and cleans up resources."""
        logger.info("Stopping AVSIP...")
        self._stop_event.set()

        if self._data_thread is not None and self._data_thread.is_alive():
            logger.debug("Waiting for data loop thread to join...")
            self._data_thread.join(timeout=self.config.get("general",{}).get("data_interval_seconds",10) + 5)
            if self._data_thread.is_alive():
                 logger.warning("Data loop thread did not join in time.")

        logger.info("Cleaning up handlers...")
        if self.meshtastic_handler:
            self.meshtastic_handler.close()
        if self.obd_handler: # Add OBD handler cleanup
            self.obd_handler.close()
        # if self.mqtt_handler: self.mqtt_handler.disconnect()
        # if self.can_handler: self.can_handler.stop() 

        logger.info("AVSIP stopped.")

if __name__ == "__main__":
    import os 
    if not os.path.exists("avsip_config.json"):
        dummy_cfg = {
            "general": {
                "log_level": "DEBUG", 
                "data_interval_seconds": 10, # Increased for OBD testing
                "device_id_source": "meshtastic_node_id" 
            },
            "meshtastic": {
                "enabled": True,
                "device_port": None, 
                "data_port_num": 251
            },
            "obd": { # Add OBD section for testing
                "enabled": True, 
                "port_string": None, # User needs to set this or have adapter auto-detectable
                "commands": ["RPM", "SPEED", "COOLANT_TEMP"],
                "include_dtc_codes": True,
                "connection_timeout_seconds": 45
            }
            # "mqtt": {"enabled": True, "host": "test.mosquitto.org", "topic_prefix": "vehicle/avsip_test"}, 
            # "traccar": {"enabled": True, "host": "demo.traccar.org", "device_id_source": "avsip_device_id"}
        }
        with open("avsip_config.json", "w") as f:
            json.dump(dummy_cfg, f, indent=2)
        print("Created a dummy avsip_config.json for testing core.py. Please ensure Meshtastic and/or OBD adapter are connected and configured.")

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
        if 'dummy_cfg' in locals() and os.path.exists("avsip_config.json"): 
            print("Note: Dummy avsip_config.json was NOT removed for inspection. Please remove it manually if desired.")

    logger.info("AVSIP application finished.")
