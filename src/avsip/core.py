# src/avsip/core.py

import logging
import threading
import time
import json
from queue import Queue, Empty # For potential future inter-thread communication

from . import config_manager
from . import utils # Assuming utils.py is in the same package directory
# Placeholder for actual handler imports - will be created later
# from .meshtastic_handler import MeshtasticHandler
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
        # These will be instances of their respective handler classes
        self.meshtastic_handler = None
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
        self._threads = [] # To keep track of all started threads for graceful shutdown

        # --- Data Storage ---
        self.current_sensor_data: dict = {} # Stores the latest aggregated sensor data
        self.data_queue = Queue() # For passing data between threads if needed (e.g. from CAN to main)

        self._initialize_handlers()
        logger.info("AVSIP initialization complete.")

    def _configure_logging(self):
        """Configures the logging system based on the loaded configuration."""
        log_level_str = self.config.get("general", {}).get("log_level", "INFO").upper()
        log_level = getattr(logging, log_level_str, logging.INFO)
        
        # Configure root logger. If other modules also use logging.getLogger(__name__),
        # they will inherit this configuration unless they override it.
        # Using basicConfig is fine for simpler apps, but for more control,
        # one might configure handlers and formatters on the root logger directly.
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        # Suppress overly verbose logs from specific libraries if needed
        # logging.getLogger("paho").setLevel(logging.WARNING)
        # logging.getLogger("meshtastic").setLevel(logging.INFO) # Meshtastic can be chatty on DEBUG
        logger.info(f"Logging configured to level: {log_level_str}")


    def _initialize_handlers(self):
        """Initializes and starts all configured data handlers."""
        logger.info("Initializing handlers...")

        # Meshtastic Handler (Core for device ID and potentially GPS)
        # This needs to be initialized first to get the device_id
        try:
            # self.meshtastic_handler = MeshtasticHandler(self.config.get("meshtastic", {}), self.data_queue)
            # self.avsip_device_id = self.meshtastic_handler.get_device_id()
            # if not self.avsip_device_id:
            #     logger.error("Failed to get AVSIP device ID from Meshtastic. Using default.")
            #     self.avsip_device_id = "default_avsip_id" # Fallback
            # else:
            #     logger.info(f"AVSIP Device ID set to: {self.avsip_device_id}")
            # self._threads.append(self.meshtastic_handler.get_thread()) # If it runs its own thread
            logger.warning("MeshtasticHandler not yet implemented. Using placeholder device ID.")
            self.avsip_device_id = self.config.get("general", {}).get("custom_device_id", "placeholder_avsip_id")
            if self.config.get("general", {}).get("device_id_source") == "meshtastic_node_id":
                 logger.info("Device ID source is 'meshtastic_node_id', but handler is not implemented.")
            logger.info(f"AVSIP Device ID (placeholder): {self.avsip_device_id}")

        except Exception as e:
            logger.error(f"Failed to initialize MeshtasticHandler: {e}", exc_info=True)
            # Potentially critical, decide if AVSIP can run without it.
            # For now, we assume it might be critical for device_id.

        # OBD Handler
        if self.config.get("obd", {}).get("enabled"):
            try:
                # self.obd_handler = OBDHandler(self.config.get("obd", {}))
                logger.info("OBDHandler initialized (placeholder).")
            except Exception as e:
                logger.error(f"Failed to initialize OBDHandler: {e}", exc_info=True)
                self.config["obd"]["enabled"] = False # Disable if init fails

        # CAN Handler
        if self.config.get("can", {}).get("enabled"):
            try:
                # self.can_handler = CANHandler(self.config.get("can", {}), self.data_queue)
                # self._threads.append(self.can_handler.get_thread()) # If it runs its own thread
                logger.info("CANHandler initialized (placeholder).")
            except Exception as e:
                logger.error(f"Failed to initialize CANHandler: {e}", exc_info=True)
                self.config["can"]["enabled"] = False

        # MQTT Handler
        if self.config.get("mqtt", {}).get("enabled"):
            try:
                # self.mqtt_handler = MQTTHandler(self.config.get("mqtt", {}), self.avsip_device_id)
                logger.info("MQTTHandler initialized (placeholder).")
            except Exception as e:
                logger.error(f"Failed to initialize MQTTHandler: {e}", exc_info=True)
                self.config["mqtt"]["enabled"] = False

        # Traccar Handler
        if self.config.get("traccar", {}).get("enabled"):
            try:
                # self.traccar_handler = TraccarHandler(self.config.get("traccar", {}), self.avsip_device_id)
                logger.info("TraccarHandler initialized (placeholder).")
            except Exception as e:
                logger.error(f"Failed to initialize TraccarHandler: {e}", exc_info=True)
                self.config["traccar"]["enabled"] = False
        
        logger.info("Handler initialization sequence complete.")

    def _collect_data(self) -> dict:
        """Collects data from all enabled sensor handlers."""
        collected_data = {
            "timestamp_utc": time.time(), # Unix timestamp UTC
            "device_id": self.avsip_device_id,
            "sensors": {},
            "gps": {},
            "dtcs": [],
            "can_data": {}
        }

        # GPS Data (from Meshtastic or other GPS source)
        if self.meshtastic_handler and hasattr(self.meshtastic_handler, 'get_gps_data'):
            # gps_data = self.meshtastic_handler.get_gps_data()
            # if gps_data:
            #    collected_data["gps"] = gps_data
            pass # Placeholder
        else: # Placeholder GPS data if no handler
            collected_data["gps"] = {"latitude": 0.0, "longitude": 0.0, "altitude": 0.0, "speed": 0.0, "satellites":0}


        # OBD Data
        if self.config.get("obd", {}).get("enabled") and self.obd_handler:
            # obd_values, dtc_list = self.obd_handler.read_data()
            # if obd_values:
            #     collected_data["sensors"].update(obd_values)
            # if dtc_list:
            #     collected_data["dtcs"] = dtc_list
            collected_data["sensors"]["rpm"] = 0 # Placeholder
            collected_data["sensors"]["speed_kph"] = 0 # Placeholder
            collected_data["dtcs"] = ["P0000"] # Placeholder
            logger.debug("Collected OBD data (placeholder).")


        # CAN Data (could be read from a queue populated by CANHandler's thread)
        if self.config.get("can", {}).get("enabled") and self.can_handler:
            # try:
            #     while not self.data_queue.empty():
            #         can_msg = self.data_queue.get_nowait() # timestamp, name, value
            #         if can_msg and isinstance(can_msg, dict) and 'name' in can_msg and 'value' in can_msg:
            #             collected_data["can_data"][can_msg['name']] = can_msg['value']
            #         self.data_queue.task_done()
            # except Empty:
            #     pass # No new CAN data
            collected_data["can_data"]["oil_pressure"] = 0 # Placeholder
            logger.debug("Collected CAN data (placeholder).")


        # Combine CAN data into main sensors for easier access if desired,
        # or keep it separate under "can_data". For now, keeping separate.
        # collected_data["sensors"].update(collected_data["can_data"])


        self.current_sensor_data = collected_data
        logger.debug(f"Aggregated sensor data: {json.dumps(self.current_sensor_data, indent=2)}")
        return self.current_sensor_data

    def _process_and_transmit_data(self, data: dict):
        """Processes and transmits data to enabled output handlers."""
        if not data:
            logger.warning("No data to process or transmit.")
            return

        logger.info(f"Processing and transmitting data for device {data.get('device_id', 'N/A')}")

        # Meshtastic Transmission
        if self.config.get("meshtastic", {}).get("enabled") and self.meshtastic_handler:
            # self.meshtastic_handler.send_data(data)
            logger.debug("Sent data via Meshtastic (placeholder).")


        # MQTT Transmission
        if self.config.get("mqtt", {}).get("enabled") and self.mqtt_handler:
            # self.mqtt_handler.publish_data(data)
            logger.debug("Sent data via MQTT (placeholder).")

        # Traccar Transmission
        if self.config.get("traccar", {}).get("enabled") and self.traccar_handler and self.traccar_rate_limiter:
            if self.traccar_rate_limiter.try_trigger():
                # self.traccar_handler.send_data(data)
                logger.debug("Sent data via Traccar (placeholder).")
            else:
                logger.debug(f"Traccar send rate limited. Next attempt in {self.traccar_rate_limiter.time_to_next_trigger():.1f}s")


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
                else:
                    logger.info("No data collected in this cycle.")

            except Exception as e:
                logger.error(f"Error in data loop: {e}", exc_info=True)
                # Potentially add more robust error handling here, e.g., backoff delays

            # Calculate sleep time to maintain the desired interval
            loop_duration = time.monotonic() - loop_start_time
            sleep_time = max(0, data_interval - loop_duration)

            if self._stop_event.wait(sleep_time): # Wait for sleep_time or until stop_event is set
                break # Exit loop if stop_event is set during wait
            
        logger.info("Data loop stopped.")

    def start(self):
        """Starts the AVSIP data collection and transmission thread."""
        if self._data_thread is not None and self._data_thread.is_alive():
            logger.warning("AVSIP data loop is already running.")
            return

        logger.info("Starting AVSIP data loop...")
        self._stop_event.clear()
        
        # Start handler threads if they have them (e.g., CAN, Meshtastic listener)
        # for handler_thread in self._threads:
        #    if handler_thread and not handler_thread.is_alive():
        #        handler_thread.start()
        #        logger.info(f"Started thread: {handler_thread.name}")


        self._data_thread = threading.Thread(target=self._data_loop, name="AVSIPDataLoop")
        self._data_thread.daemon = True  # Allow main program to exit even if thread is running
        self._data_thread.start()
        logger.info("AVSIP data loop thread started.")

    def stop(self):
        """Stops the AVSIP data collection and transmission thread and cleans up resources."""
        logger.info("Stopping AVSIP...")
        self._stop_event.set()

        # Stop handler threads
        # if self.can_handler: self.can_handler.stop()
        # if self.meshtastic_handler: self.meshtastic_handler.stop()
        # ... and wait for them to join
        # for thread in self._threads:
        #    if thread and thread.is_alive():
        #        logger.debug(f"Waiting for thread {thread.name} to join...")
        #        thread.join(timeout=5) # Add timeout
        #        if thread.is_alive():
        #            logger.warning(f"Thread {thread.name} did not join in time.")


        if self._data_thread is not None and self._data_thread.is_alive():
            logger.debug("Waiting for data loop thread to join...")
            self._data_thread.join(timeout=self.config.get("general",{}).get("data_interval_seconds",10) + 2) # Wait a bit longer than interval
            if self._data_thread.is_alive():
                 logger.warning("Data loop thread did not join in time.")


        # Cleanup handlers
        logger.info("Cleaning up handlers...")
        # if self.obd_handler: self.obd_handler.close()
        # if self.mqtt_handler: self.mqtt_handler.disconnect()
        # if self.meshtastic_handler: self.meshtastic_handler.close() # If it holds resources like serial port
        # Traccar handler might not need explicit close unless it holds persistent connections

        logger.info("AVSIP stopped.")

if __name__ == "__main__":
    # This is an example of how to run AVSIP.
    # In a real deployment, you might have a separate run.py script.

    # Create a dummy config for direct execution testing
    if not os.path.exists("avsip_config.json"):
        dummy_cfg = {
            "general": {"log_level": "DEBUG", "data_interval_seconds": 5},
            "meshtastic": {"enabled": True}, # Keep Meshtastic enabled for device ID
            # "obd": {"enabled": True, "commands": ["RPM"]}, # Uncomment to test OBD placeholder
            # "mqtt": {"enabled": True, "host": "test.mosquitto.org"}, # Uncomment for MQTT placeholder
            # "traccar": {"enabled": True, "host": "demo.traccar.org", "device_id_source": "custom_traccar_id", "custom_traccar_id": "avsip_test_001"}
        }
        with open("avsip_config.json", "w") as f:
            json.dump(dummy_cfg, f, indent=2)
        print("Created a dummy avsip_config.json for testing core.py")

    avsip_app = None
    try:
        avsip_app = AVSIP(config_file_path="avsip_config.json")
        avsip_app.start()
        
        # Keep the main thread alive, e.g., for a set duration or until Ctrl+C
        while True:
            time.sleep(1) # Keep main thread alive, listen for KeyboardInterrupt

    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received. Stopping AVSIP...")
    except Exception as e:
        logger.critical(f"Unhandled exception in main: {e}", exc_info=True)
    finally:
        if avsip_app:
            avsip_app.stop()
        if os.path.exists("avsip_config.json") and "dummy_cfg" in locals(): # Clean up dummy config
            # os.remove("avsip_config.json")
            print("Note: Dummy avsip_config.json was NOT removed for inspection. Please remove it manually if desired.")

    logger.info("AVSIP application finished.")
