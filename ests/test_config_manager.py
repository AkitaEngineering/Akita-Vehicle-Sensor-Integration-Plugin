# tests/test_config_manager.py

import unittest
import json
import os
import logging
from unittest.mock import patch, mock_open

# Add src to sys.path to allow importing avsip package
# This is a common pattern for running tests from the 'tests' directory
import sys
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir) # Assuming tests is a subdir of project root
src_path = os.path.join(project_root, 'src')
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from avsip import config_manager # type: ignore

# Suppress logging during most tests unless specifically testing logging
logging.disable(logging.CRITICAL) # Disable all logging levels CRITICAL and below

class TestConfigManager(unittest.TestCase):

    def setUp(self):
        """Set up for test methods."""
        self.test_config_dir = "test_configs_temp"
        os.makedirs(self.test_config_dir, exist_ok=True)
        self.default_config = config_manager.DEFAULT_CONFIG

    def tearDown(self):
        """Tear down after test methods."""
        for f_name in os.listdir(self.test_config_dir):
            os.remove(os.path.join(self.test_config_dir, f_name))
        os.rmdir(self.test_config_dir)
        logging.disable(logging.NOTSET) # Re-enable logging

    def _write_test_config(self, filename: str, content: dict):
        """Helper to write a temporary config file."""
        path = os.path.join(self.test_config_dir, filename)
        with open(path, "w") as f:
            json.dump(content, f, indent=4)
        return path

    def test_load_config_file_not_found(self):
        """Test loading config when the file does not exist; should return defaults."""
        config = config_manager.load_config("non_existent_config.json")
        self.assertEqual(config, self.default_config, "Should return default config if file not found.")

    def test_load_valid_config_file(self):
        """Test loading a valid configuration file with some overrides."""
        user_overrides = {
            "general": {
                "log_level": "DEBUG",
                "data_interval_seconds": 5
            },
            "mqtt": {
                "host": "mqtt.example.com",
                "enabled": True
            }
        }
        config_path = self._write_test_config("valid_config.json", user_overrides)
        
        loaded_config = config_manager.load_config(config_path)

        # Check if overrides are applied and defaults are present for non-overridden keys
        self.assertEqual(loaded_config["general"]["log_level"], "DEBUG")
        self.assertEqual(loaded_config["general"]["data_interval_seconds"], 5)
        self.assertEqual(loaded_config["mqtt"]["host"], "mqtt.example.com")
        self.assertTrue(loaded_config["mqtt"]["enabled"])
        self.assertEqual(loaded_config["obd"]["enabled"], self.default_config["obd"]["enabled"]) # Check a default

    def test_load_empty_config_file(self):
        """Test loading an empty JSON object; should merge with defaults."""
        config_path = self._write_test_config("empty_config.json", {})
        loaded_config = config_manager.load_config(config_path)
        self.assertEqual(loaded_config, self.default_config, "Empty config should result in default config.")

    def test_load_invalid_json_config_file(self):
        """Test loading a file with invalid JSON; should return defaults."""
        invalid_json_path = os.path.join(self.test_config_dir, "invalid_json.json")
        with open(invalid_json_path, "w") as f:
            f.write("{'general': {'log_level': 'DEBUG'}") # Invalid JSON (single quotes, missing brace)
        
        # Temporarily enable logging to check for error messages
        logging.disable(logging.NOTSET)
        with self.assertLogs(config_manager.logger, level='ERROR') as cm:
            loaded_config = config_manager.load_config(invalid_json_path)
        logging.disable(logging.CRITICAL)

        self.assertEqual(loaded_config, self.default_config, "Invalid JSON should result in default config.")
        self.assertTrue(any("Error decoding JSON" in log_msg for log_msg in cm.output))


    def test_deep_update_logic(self):
        """Test that nested dictionaries are updated, not replaced."""
        user_overrides = {
            "obd": { # This whole dict is in defaults
                "port_string": "/dev/ttyOBD0", # Override one value
                "new_custom_obd_param": True # Add a new value
            }
        }
        config_path = self._write_test_config("deep_update_test.json", user_overrides)
        loaded_config = config_manager.load_config(config_path)

        # Check overridden value
        self.assertEqual(loaded_config["obd"]["port_string"], "/dev/ttyOBD0")
        # Check that other default values in the 'obd' dict are still present
        self.assertEqual(loaded_config["obd"]["enabled"], self.default_config["obd"]["enabled"])
        self.assertEqual(loaded_config["obd"]["baudrate"], self.default_config["obd"]["baudrate"])
        # Check that the new parameter was added
        self.assertTrue(loaded_config["obd"]["new_custom_obd_param"])


    def test_validate_config_invalid_interval(self):
        """Test validation for data_interval_seconds."""
        test_cfg = json.loads(json.dumps(self.default_config)) # Deep copy
        test_cfg["general"]["data_interval_seconds"] = -5
        
        logging.disable(logging.NOTSET)
        with self.assertLogs(config_manager.logger, level='WARNING') as cm:
            config_manager.validate_config(test_cfg)
        logging.disable(logging.CRITICAL)
            
        self.assertEqual(test_cfg["general"]["data_interval_seconds"], self.default_config["general"]["data_interval_seconds"])
        self.assertTrue(any("Invalid 'general.data_interval_seconds'" in log_msg for log_msg in cm.output))

    def test_validate_config_invalid_log_level(self):
        """Test validation for log_level."""
        test_cfg = json.loads(json.dumps(self.default_config))
        test_cfg["general"]["log_level"] = "SUPERDEBUG"

        logging.disable(logging.NOTSET)
        with self.assertLogs(config_manager.logger, level='WARNING') as cm:
            config_manager.validate_config(test_cfg)
        logging.disable(logging.CRITICAL)

        self.assertEqual(test_cfg["general"]["log_level"], self.default_config["general"]["log_level"].upper())
        self.assertTrue(any("Invalid log level 'SUPERDEBUG'" in log_msg for log_msg in cm.output))

    def test_validate_mqtt_missing_host_when_enabled(self):
        """Test MQTT validation: if enabled, host must be present."""
        test_cfg = json.loads(json.dumps(self.default_config))
        test_cfg["mqtt"]["enabled"] = True
        test_cfg["mqtt"]["host"] = "" # Empty host string

        logging.disable(logging.NOTSET)
        with self.assertLogs(config_manager.logger, level='WARNING') as cm:
            config_manager.validate_config(test_cfg)
        logging.disable(logging.CRITICAL)

        self.assertFalse(test_cfg["mqtt"]["enabled"], "MQTT should be disabled if host is missing when enabled.")
        self.assertTrue(any("MQTT 'host' not specified. Disabling MQTT." in log_msg for log_msg in cm.output))

    def test_validate_can_message_definitions_not_list(self):
        """Test CAN validation: message_definitions should be a list."""
        test_cfg = json.loads(json.dumps(self.default_config))
        test_cfg["can"]["enabled"] = True
        test_cfg["can"]["message_definitions"] = {"not_a": "list"}

        logging.disable(logging.NOTSET)
        with self.assertLogs(config_manager.logger, level='WARNING') as cm:
            config_manager.validate_config(test_cfg)
        logging.disable(logging.CRITICAL)
        
        self.assertFalse(test_cfg["can"]["enabled"], "CAN should be disabled if message_definitions is not a list.")

    def test_validate_can_message_definition_invalid_parser(self):
        """Test CAN validation: individual message definition with bad parser."""
        test_cfg = json.loads(json.dumps(self.default_config))
        test_cfg["can"]["enabled"] = True
        test_cfg["can"]["message_definitions"] = [
            {
                "id": "0x123",
                "name": "TestSignal",
                "parser": "not_a_dict" # Invalid parser
            }
        ]
        # This specific validation is now inside CANHandler's _parse_message_definitions
        # config_manager.validate_config only checks if message_definitions is a list.
        # However, we can check the logger output from CANHandler if we were testing it.
        # For config_manager, this should still pass as long as message_definitions is a list.
        config_manager.validate_config(test_cfg) # Should not disable CAN based on this alone
        self.assertTrue(test_cfg["can"]["enabled"]) # config_manager doesn't dive this deep

        # A more detailed test for parser content would be in test_can_handler.py
        # or if config_manager.validate_config was made more stringent.
        # The current validate_config in config_manager.py for CAN defs is:
        # for i, msg_def in enumerate(config["can"].get("message_definitions", [])):
        #     if not all(k in msg_def for k in ["id", "name", "parser"]):
        #         logger.warning(f"CAN message definition at index {i} is missing required keys (id, name, parser). It will be skipped.")
        #     elif not isinstance(msg_def["parser"], dict):
        #          logger.warning(f"Parser for CAN message '{msg_def.get('name', 'Unknown')}' is not a dictionary. It will be skipped.")
        # This means it logs a warning but doesn't disable CAN itself.

        # Let's refine the test to match the actual validation in config_manager.py
        test_cfg_refined = json.loads(json.dumps(self.default_config))
        test_cfg_refined["can"]["enabled"] = True
        test_cfg_refined["can"]["message_definitions"] = [
            {"id": "0x123", "name": "TestSignal"} # Missing "parser" key entirely
        ]
        logging.disable(logging.NOTSET)
        with self.assertLogs(config_manager.logger, level='WARNING') as cm:
            config_manager.validate_config(test_cfg_refined)
        logging.disable(logging.CRITICAL)
        self.assertTrue(any("missing required keys (id, name, parser)" in log_msg for log_msg in cm.output))
        # CAN remains enabled because the overall structure (list of dicts) is okay for config_manager.
        # The actual skipping of this definition happens in CANHandler.
        self.assertTrue(test_cfg_refined["can"]["enabled"])


if __name__ == '__main__':
    # To run tests from the command line from the project root:
    # python -m unittest tests.test_config_manager
    # Or using pytest:
    # pytest tests/test_config_manager.py
    unittest.main(verbosity=2)
