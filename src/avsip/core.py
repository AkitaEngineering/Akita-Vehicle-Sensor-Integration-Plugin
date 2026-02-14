# src/avsip/core.py

import logging
import threading
import time
import json
from queue import Queue, Empty # For potential future inter-thread communication
from typing import List # Added List for type hinting

from . import config_manager
from . import utils
from .meshtastic_handler import MeshtasticHandler
from .obd_handler import OBDHandler
from .can_handler import CANHandler
from .mqtt_handler import MQTTHandler
from .traccar_handler import TraccarHandler # Import the actual Traccar handler

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

        self.avsip_device_id: str = "unknown_avsip_device"

        # --- Handlers ---
        self.meshtastic_handler: MeshtasticHandler | None = None
        self.obd_handler: OBDHandler | None = None
        self.can_handler: CANHandler | None = None
        self.mqtt_handler: MQTTHandler | None = None
        self.traccar_handler: TraccarHandler | None = None # Type hint for TraccarHandler
        
        # --- Rate Limiters ---
        self.traccar_rate_limiter = None
        if self.config.get("traccar", {}).get("enabled"):
            report_interval = self.config.get("traccar", {}).get("report_interval_seconds", 30)
            self.traccar_rate_limiter = utils.RateLimiter(float(report_interval)) # Ensure float for RateLimiter

        # --- Threading Control ---
        self._stop_event = threading.Event()
        self._data_thread = None
        self._handler_threads: List[threading.Thread] = [] 

        # --- Data Storage ---
        self.current_sensor_data: dict = {}
        self.data_queue = Queue(maxsize=200) 

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
                else:
                    logger.error("Failed to get AVSIP device ID from Meshtastic. Using fallback.")
                    self.avsip_device_id = f"fallback_{int(time.time())}"
            else:
                logger.warning(f"Configured to use Meshtastic Node ID, but handler not available/connected. Using fallback.")
                self.avsip_device_id = f"fallback_{int(time.time())}"
        else:
            logger.warning(f"Unknown device_id_source '{id_source}'. Using fallback.")
            self.avsip_device_id = f"fallback_{int(time.time())}"
        
        logger.info(f"Final AVSIP Device ID: {self.avsip_device_id}")
        
        self._reinitialize_dependent_handlers()
        logger.info("AVSIP initialization complete.")

    def _configure_logging(self):
        """Configures the logging system based on the loaded configuration."""
        log_level_str = self.config.get("general", {}).get("log_level", "INFO").upper()
        log_level = getattr(logging, log_level_str, logging.INFO)
        
        # Clear existing handlers from the root logger to avoid duplicate messages
        # if basicConfig has been called before (e.g. by a library or in testing)
        for handler in logging.root.handlers[:]:
            logging.root.removeHandler(handler)

        logging.basicConfig(
            level=log_level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        # Set library log levels
        # These should be set after basicConfig if basicConfig affects the root logger's level
        # or if libraries get their own loggers that inherit from root.
        # If AVSIP's level is DEBUG, we might want more from libraries too.
        lib_log_level = logging.WARNING # Default for less verbose libraries
        if log_level == logging.DEBUG:
            lib_log_level = logging.INFO # Or even DEBUG for specific libraries

        logging.getLogger("meshtastic").setLevel(lib_log_level if lib_log_level != logging.INFO else logging.INFO) # Meshtastic can be noisy
        logging.getLogger("obd").setLevel(lib_log_level)
        logging.getLogger("can").setLevel(lib_log_level) 
        logging.getLogger("paho.mqtt.client").setLevel(lib_log_level)
        logging.getLogger("requests").setLevel(logging.WARNING) # Requests can be verbose with INFO/DEBUG
        logging.getLogger("urllib3").setLevel(logging.WARNING) # urllib3 (used by requests)

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
                self.obd_handler = OBDHandler(obd_config)
                if self.obd_handler.is_connected:
                    logger.info("OBDHandler initialized and connected.")
                else:
                    logger.warning("OBDHandler initialized but not connected.")
            except Exception as e:
                logger.error(f"Failed to initialize OBDHandler: {e}", exc_info=True)
                self.config["obd"]["enabled"] = False
        else:
            logger.info("OBD component is disabled in configuration.")

        # CAN Handler
        can_config = self.config.get("can", {})
        if can_config.get("enabled"):
            try:
                self.can_handler = CANHandler(can_config, self.data_queue)
                if self.can_handler.is_connected:
                    logger.info("CANHandler initialized and connected.")
                    # Listener is started by CANHandler itself if connection is successful
                    # We track its thread if it's created and alive.
                    if self.can_handler._listener_thread and self.can_handler._listener_thread.is_alive():
                         self._handler_threads.append(self.can_handler._listener_thread)
                         logger.info("CANHandler listener thread started and tracked.")
                else:
                    logger.warning("CANHandler initialized but not connected. CAN data will not be available.")
            except Exception as e:
                logger.error(f"Failed to initialize CANHandler: {e}", exc_info=True)
                self.config["can"]["enabled"] = False
        else:
            logger.info("CAN component is disabled in configuration.")
        
        logger.info("Handler initialization (first pass) complete.")

    def _reinitialize_dependent_handlers(self):
        """Initializes handlers that depend on the final avsip_device_id."""
        logger.info("Re-initializing device ID dependent handlers...")
        
        # MQTT Handler
        mqtt_config = self.config.get("mqtt", {})
        if mqtt_config.get("enabled"):
            if self.mqtt_handler: 
                logger.debug("MQTT Handler instance already exists. Disconnecting before re-init.")
                self.mqtt_handler.disconnect()
            try:
                self.mqtt_handler = MQTTHandler(mqtt_config, self.avsip_device_id)
                if self.mqtt_handler.is_connected:
                    logger.info(f"MQTTHandler initialized and connected with device ID {self.avsip_device_id}.")
                elif mqtt_config.get("enabled"): 
                    logger.warning(f"MQTTHandler initialized for device ID {self.avsip_device_id} but failed to connect.")
            except Exception as e:
                logger.error(f"Failed to initialize MQTTHandler: {e}", exc_info=True)
                self.config["mqtt"]["enabled"] = False
        else:
            logger.info("MQTT component is disabled in configuration.")

        # Traccar Handler
        traccar_config = self.config.get("traccar", {})
        if traccar_config.get("enabled"):
            if self.traccar_handler:
                 logger.debug("Traccar Handler instance already exists. No re-init needed unless config changed externally.")
            try:
                traccar_device_id_for_handler = self.avsip_device_id # Default
                traccar_id_source = traccar_config.get("device_id_source", "avsip_device_id")
                
                if traccar_id_source == "custom_traccar_id":
                    custom_id = traccar_config.get("custom_traccar_id")
                    if custom_id:
                        traccar_device_id_for_handler = custom_id
                        logger.info(f"Using custom Traccar device ID: {custom_id}")
                    else:
                        logger.warning("Traccar device_id_source is 'custom_traccar_id' but no custom ID provided. Using AVSIP device ID as fallback for Traccar.")
                else: # avsip_device_id or other
                    logger.info(f"Using AVSIP device ID '{self.avsip_device_id}' for Traccar.")

                self.traccar_handler = TraccarHandler(traccar_config, traccar_device_id_for_handler)
                if self.traccar_handler.is_configured: # TraccarHandler uses is_configured
                    logger.info(f"TraccarHandler initialized for Traccar device ID {traccar_device_id_for_handler}.")
                elif traccar_config.get("enabled"): # Check if it was disabled by its own init logic
                    logger.warning(f"TraccarHandler initialized for device ID {traccar_device_id_for_handler} but is not configured (e.g. missing host).")
            except Exception as e:
                logger.error(f"Failed to initialize TraccarHandler: {e}", exc_info=True)
                self.config["traccar"]["enabled"] = False
        else:
            logger.info("Traccar component is disabled in configuration.")


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
                logger.warning("OBD enabled but handler not connected.")

        # CAN Data
        if self.config.get("can", {}).get("enabled") and self.can_handler and self.can_handler.is_connected:
            can_messages_processed_this_cycle = 0
            try:
                while not self.data_queue.empty(): 
                    can_msg = self.data_queue.get_nowait() 
                    if can_msg and isinstance(can_msg, dict) and 'name' in can_msg and 'value' in can_msg:
                        collected_data["can_data"][can_msg['name']] = can_msg['value']
                        can_messages_processed_this_cycle +=1
                    self.data_queue.task_done() 
            except Empty:
                pass 
            if can_messages_processed_this_cycle > 0:
                logger.debug(f"Collected {can_messages_processed_this_cycle} CAN data items from queue: {collected_data['can_data']}")
            else:
                logger.debug("No new CAN data in queue this cycle.")

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
        if self.config.get("mqtt", {}).get("enabled") and self.mqtt_handler and self.mqtt_handler.is_connected:
            if self.mqtt_handler.publish_data(data, sub_topic="data_all"):
                logger.info("Aggregated data sent via MQTT to 'data_all' sub-topic.")
            else:
                logger.warning("Failed to send aggregated data via MQTT.")
            
        # Traccar Transmission
        if self.config.get("traccar", {}).get("enabled") and \
           self.traccar_handler and self.traccar_handler.is_configured and \
           self.traccar_rate_limiter:
            # Traccar primarily needs GPS data.
            if data.get("gps") and data["gps"].get("latitude") is not None and data["gps"].get("longitude") is not None \
               and (data["gps"]["latitude"] != 0.0 or data["gps"]["longitude"] != 0.0): # Ensure not (0,0) which can be invalid default
                if self.traccar_rate_limiter.try_trigger():
                    if self.traccar_handler.send_data(data):
                        logger.info("Data sent via Traccar.")
                    else:
                        logger.warning("Failed to send data via Traccar.")
                else:
                    logger.debug(f"Traccar send rate limited. Next attempt in {self.traccar_rate_limiter.time_to_next_trigger():.1f}s")
            else:
                logger.debug("Skipping Traccar transmission due to missing, invalid, or (0,0) GPS data.")


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
        
        if self.can_handler and self.can_handler.is_connected:
            if not self.can_handler._listener_thread or not self.can_handler._listener_thread.is_alive():
                logger.info("CAN listener was not running, attempting to start it now.")
                self.can_handler.start_listener() # This is safe, CANHandler checks if already running
                # Re-track the thread if it was re-created
                if self.can_handler._listener_thread and self.can_handler._listener_thread.is_alive() and \
                   self.can_handler._listener_thread not in self._handler_threads:
                     self._handler_threads.append(self.can_handler._listener_thread)


        self._data_thread = threading.Thread(target=self._data_loop, name="AVSIPDataLoop")
        self._data_thread.daemon = True
        self._data_thread.start()
        logger.info("AVSIP data loop thread started.")

    def stop(self):
        """Stops the AVSIP data collection and transmission thread and cleans up resources."""
        logger.info("Stopping AVSIP...")
        self._stop_event.set() 

        if self.can_handler: 
            logger.info("Stopping CAN handler listener...")
            self.can_handler.stop_listener() 

        for thread in self._handler_threads: 
            if thread and thread.is_alive():
                logger.debug(f"Waiting for handler thread {thread.name} to join...")
                thread.join(timeout=5) 
                if thread.is_alive():
                    logger.warning(f"Handler thread {thread.name} did not join in time.")
        self._handler_threads.clear()


        if self._data_thread is not None and self._data_thread.is_alive():
            logger.debug("Waiting for data loop thread to join...")
            self._data_thread.join(timeout=self.config.get("general",{}).get("data_interval_seconds",10) + 5)
            if self._data_thread.is_alive():
                 logger.warning("Data loop thread did not join in time.")

        logger.info("Cleaning up handlers...")
        if self.meshtastic_handler:
            self.meshtastic_handler.close()
        if self.obd_handler: 
            self.obd_handler.close()
        if self.can_handler: 
            self.can_handler.close() 
        if self.mqtt_handler: 
            self.mqtt_handler.disconnect()
        if self.traccar_handler: # Add Traccar handler cleanup
            self.traccar_handler.close()


        logger.info("AVSIP stopped.")

if __name__ == "__main__":
    import os 
    if not os.path.exists("avsip_config.json"):
        dummy_cfg = {
            "general": {
                "log_level": "DEBUG", 
                "data_interval_seconds": 10, 
                "device_id_source": "meshtastic_node_id" 
                # "custom_device_id": "avsip_main_test_001"
            },
            "meshtastic": { "enabled": True, "device_port": None, "data_port_num": 251 },
            "obd": { 
                "enabled": False, 
                "port_string": None, 
                "commands": ["RPM", "SPEED"],
                "connection_timeout_seconds": 30
            },
            "can": { 
                "enabled": False, 
                "interface_type": "socketcan",
                "channel": "vcan0", 
                "bitrate": 500000,
                "message_definitions": [
                    {"id": "0x123", "name": "TestCANSignal", "parser": {
                        "type": "simple_scalar", "start_byte": 0, "length_bytes": 1,
                        "scale": 1, "offset": 0, "is_signed": False, "byte_order": "big"
                    }}
                ]
            },
            "mqtt": { 
                "enabled": False, 
                "host": "test.mosquitto.org", 
                "port": 1883,
                "topic_prefix": "vehicle/avsip_coretest",
                "lwt_topic_suffix": "status"
            },
            "traccar": { # Add Traccar section for testing
                "enabled": False, # Set to True to test Traccar
                "host": "localhost", # Replace with your Traccar server
                "port": 5055,
                "device_id_source": "custom_traccar_id", # or "avsip_device_id"
                "custom_traccar_id": "avsip_test_traccar_01" # Must exist in Traccar
            }
        }
        with open("avsip_config.json", "w") as f:
            json.dump(dummy_cfg, f, indent=2)
        print("Created a dummy avsip_config.json for testing core.py. Please ensure hardware/virtual interfaces are set up.")

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
