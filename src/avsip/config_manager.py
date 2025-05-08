# src/avsip/config_manager.py

import json
import logging
import os

# Default configuration structure to ensure all keys are present
DEFAULT_CONFIG = {
    "general": {
        "log_level": "INFO",
        "data_interval_seconds": 10,
        "device_id_source": "meshtastic_node_id" # or "custom"
        # "custom_device_id": "my_vehicle_001" # if device_id_source is "custom"
    },
    "meshtastic": {
        "enabled": True, # Meshtastic is core for device_id and potentially GPS
        "device_port": None,
        "data_port_num": 250, # Default DATA_APP port for AVSIP
        "send_config_on_connect": False # Whether to send radio/channel config
    },
    "obd": {
        "enabled": False,
        "port_string": None,
        "baudrate": None,
        "protocol": None,
        "fast_commands": True,
        "commands": ["RPM", "SPEED", "COOLANT_TEMP"],
        "include_dtc_codes": True,
        "connection_retries": 3,
        "retry_delay_seconds": 5
    },
    "can": {
        "enabled": False,
        "interface_type": "socketcan",
        "channel": "can0",
        "bitrate": 500000,
        "message_definitions": [],
        "connection_retries": 3,
        "retry_delay_seconds": 5
    },
    "mqtt": {
        "enabled": False,
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
        "lwt_topic_suffix": "status", # Suffix for Last Will and Testament topic
        "lwt_payload_online": "online",
        "lwt_payload_offline": "offline",
        "lwt_qos": 0,
        "lwt_retain": True,
        "connection_timeout_seconds": 10
    },
    "traccar": {
        "enabled": False,
        "host": "localhost",
        "port": 5055, # OsmAnd port
        "device_id_source": "avsip_device_id", # or "custom_traccar_id"
        # "custom_traccar_id": "traccar_device_123", # if device_id_source is "custom_traccar_id"
        "use_http": True, # OsmAnd protocol
        "http_path": "/",
        "report_interval_seconds": 30,
        "request_timeout_seconds": 10,
        "convert_speed_to_knots": True
    }
}

logger = logging.getLogger(__name__)

def deep_update(source, overrides):
    """
    Recursively update a dictionary.
    Modifies 'source' in place.
    """
    for key, value in overrides.items():
        if isinstance(value, dict) and key in source and isinstance(source[key], dict):
            deep_update(source[key], value)
        else:
            source[key] = value
    return source

def load_config(config_file_path: str = "avsip_config.json") -> dict:
    """
    Loads the configuration from a JSON file, merges with defaults, and performs basic validation.

    Args:
        config_file_path: Path to the configuration JSON file.

    Returns:
        A dictionary containing the configuration.
        Returns default configuration if the file is not found or is invalid.
    """
    config = {}  # Start with an empty dict
    # Make a deep copy of defaults to avoid modifying the global DEFAULT_CONFIG
    current_config = json.loads(json.dumps(DEFAULT_CONFIG))


    if not os.path.exists(config_file_path):
        logger.warning(f"Configuration file '{config_file_path}' not found. Using default configuration values.")
        # In this case, current_config (a copy of DEFAULT_CONFIG) is returned.
    else:
        try:
            with open(config_file_path, "r") as f:
                user_config = json.load(f)
            # Recursively update the default config with user-provided values
            current_config = deep_update(current_config, user_config)
            logger.info(f"Successfully loaded configuration from '{config_file_path}'.")
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding JSON from '{config_file_path}': {e}. Using default configuration values.")
            # current_config remains a copy of DEFAULT_CONFIG
        except Exception as e:
            logger.error(f"An unexpected error occurred while loading '{config_file_path}': {e}. Using default configuration values.")
            # current_config remains a copy of DEFAULT_CONFIG

    # Perform basic validation and adjustments
    validate_config(current_config)

    return current_config

def validate_config(config: dict):
    """
    Performs basic validation and adjustments on the loaded configuration.
    Modifies 'config' in place for adjustments.

    Args:
        config: The configuration dictionary to validate.
    """
    # Validate general settings
    if not isinstance(config.get("general", {}).get("data_interval_seconds"), (int, float)) or config["general"]["data_interval_seconds"] <= 0:
        logger.warning("Invalid 'general.data_interval_seconds'. Setting to default 10 seconds.")
        config["general"]["data_interval_seconds"] = DEFAULT_CONFIG["general"]["data_interval_seconds"]

    log_level = config.get("general", {}).get("log_level", "INFO").upper()
    if log_level not in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
        logger.warning(f"Invalid log level '{log_level}'. Defaulting to 'INFO'.")
        config["general"]["log_level"] = DEFAULT_CONFIG["general"]["log_level"]
    else:
        config["general"]["log_level"] = log_level # Ensure it's uppercase

    # Validate Meshtastic (always enabled for now as it's a core part)
    if not config.get("meshtastic", {}).get("enabled"):
        logger.info("Meshtastic is considered a core component and is enabled by default for device ID and potential GPS.")
        config["meshtastic"]["enabled"] = True # Enforce Meshtastic enabled for now

    if not isinstance(config.get("meshtastic", {}).get("data_port_num"), int) or \
       not (0 <= config["meshtastic"]["data_port_num"] <= 255): # PortNum range
        logger.warning("Invalid 'meshtastic.data_port_num'. Setting to default 250.")
        config["meshtastic"]["data_port_num"] = DEFAULT_CONFIG["meshtastic"]["data_port_num"]

    # Validate OBD settings if enabled
    if config.get("obd", {}).get("enabled"):
        if not isinstance(config["obd"].get("commands"), list):
            logger.warning("'obd.commands' is not a list. Disabling OBD.")
            config["obd"]["enabled"] = False
        if not config["obd"].get("commands"): # Empty list
            logger.warning("'obd.commands' is empty. Consider adding commands or disabling OBD.")


    # Validate CAN settings if enabled
    if config.get("can", {}).get("enabled"):
        if not isinstance(config["can"].get("message_definitions"), list):
            logger.warning("'can.message_definitions' is not a list. Disabling CAN.")
            config["can"]["enabled"] = False
        if not config["can"].get("interface_type") or not config["can"].get("channel"):
            logger.warning("CAN 'interface_type' or 'channel' not specified. Disabling CAN.")
            config["can"]["enabled"] = False
        for i, msg_def in enumerate(config["can"].get("message_definitions", [])):
            if not all(k in msg_def for k in ["id", "name", "parser"]):
                logger.warning(f"CAN message definition at index {i} is missing required keys (id, name, parser). It will be skipped.")
            elif not isinstance(msg_def["parser"], dict):
                 logger.warning(f"Parser for CAN message '{msg_def.get('name', 'Unknown')}' is not a dictionary. It will be skipped.")


    # Validate MQTT settings if enabled
    if config.get("mqtt", {}).get("enabled"):
        if not config["mqtt"].get("host"):
            logger.warning("MQTT 'host' not specified. Disabling MQTT.")
            config["mqtt"]["enabled"] = False
        if not isinstance(config["mqtt"].get("port"), int):
            logger.warning("MQTT 'port' is invalid. Disabling MQTT.")
            config["mqtt"]["enabled"] = False

    # Validate Traccar settings if enabled
    if config.get("traccar", {}).get("enabled"):
        if not config["traccar"].get("host"):
            logger.warning("Traccar 'host' not specified. Disabling Traccar.")
            config["traccar"]["enabled"] = False
        if not isinstance(config["traccar"].get("port"), int):
            logger.warning("Traccar 'port' is invalid. Disabling Traccar.")
            config["traccar"]["enabled"] = False
        if not config["traccar"].get("device_id_source"): # device_id_source is now required
             logger.warning("Traccar 'device_id_source' not specified. Defaulting to 'avsip_device_id'.")
             config["traccar"]["device_id_source"] = DEFAULT_CONFIG["traccar"]["device_id_source"]


    logger.debug(f"Final validated configuration: {json.dumps(config, indent=2)}")


if __name__ == "__main__":
    # Example usage:
    # Setup basic logging for testing this module directly
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # Create a dummy config file for testing
    dummy_config_content = {
        "general": {
            "log_level": "DEBUG",
            "data_interval_seconds": 5
        },
        "meshtastic": {
            "device_port": "/dev/ttyUSB0"
        },
        "obd": {
            "enabled": True,
            "commands": ["RPM", "SPEED", "THROTTLE_POS"],
            "port_string": "/dev/rfcomm0"
        },
        "mqtt": {
            "enabled": True,
            "host": "mqtt.myhome.com",
            "user": "testuser"
            # Missing password, will use default None
        },
        "can": {
            "enabled": True,
            "interface_type": "socketcan",
            "channel": "can1",
            "message_definitions": [
                {
                    "id": "0x123",
                    "name": "OilPressure",
                    "parser": { # Valid parser
                        "type": "simple_scalar",
                        "start_byte": 0,
                        "length_bytes": 1,
                        "scale": 0.5,
                        "offset": 0,
                        "is_signed": False,
                        "byte_order": "big"
                    }
                },
                { # Invalid parser - missing keys
                    "id": "0xABC",
                    "name": "MissingParserInfo"
                }
            ]
        }
    }
    dummy_file_path = "temp_avsip_config.json"
    with open(dummy_file_path, "w") as f:
        json.dump(dummy_config_content, f, indent=4)

    logger.info("--- Testing with existing config file ---")
    loaded_config = load_config(dummy_file_path)
    # print("\nLoaded Config (from dummy file):")
    # print(json.dumps(loaded_config, indent=4))

    # Test with non-existent config file
    logger.info("\n--- Testing with non-existent config file ---")
    loaded_config_default = load_config("non_existent_config.json")
    # print("\nLoaded Config (default):")
    # print(json.dumps(loaded_config_default, indent=4))

    # Clean up dummy file
    if os.path.exists(dummy_file_path):
        os.remove(dummy_file_path)

    # Test specific validations
    logger.info("\n--- Testing specific validations ---")
    test_val_conf = {"general": {"data_interval_seconds": -5}, "mqtt":{"enabled":True}} # missing host
    validate_config(test_val_conf) # Should log warnings and fix/disable
    # print("\nValidated Test Config:")
    # print(json.dumps(test_val_conf, indent=4))
