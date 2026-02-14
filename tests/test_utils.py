# tests/test_utils.py

import unittest
import time
import logging

# Add src to sys.path to allow importing avsip package
import sys
import os
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir) # Assuming tests is a subdir of project root
src_path = os.path.join(project_root, 'src')
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from avsip import utils # type: ignore

# Suppress logging during tests
logging.disable(logging.CRITICAL)

class TestUtils(unittest.TestCase):

    def tearDown(self):
        """Re-enable logging after tests if it was disabled."""
        logging.disable(logging.NOTSET)

    def test_get_safe_nested_dict_value(self):
        """Test retrieving values from nested dictionaries safely."""
        data = {
            "level1_a": {
                "level2_a": "value2a",
                "level2_b": {
                    "level3_a": 100,
                    "level3_b": [1, 2, 3]
                }
            },
            "level1_b": "value1b"
        }

        self.assertEqual(utils.get_safe_nested_dict_value(data, ["level1_a", "level2_a"]), "value2a")
        self.assertEqual(utils.get_safe_nested_dict_value(data, ["level1_a", "level2_b", "level3_a"]), 100)
        self.assertEqual(utils.get_safe_nested_dict_value(data, ["level1_a", "level2_b", "level3_b"]), [1, 2, 3])
        self.assertEqual(utils.get_safe_nested_dict_value(data, ["level1_b"]), "value1b")

        # Test non-existent paths
        self.assertIsNone(utils.get_safe_nested_dict_value(data, ["level1_a", "level2_c"]))
        self.assertIsNone(utils.get_safe_nested_dict_value(data, ["level1_c"]))
        self.assertIsNone(utils.get_safe_nested_dict_value(data, ["level1_a", "level2_b", "level3_c"]))

        # Test with default value
        self.assertEqual(utils.get_safe_nested_dict_value(data, ["level1_a", "level2_c"], "default_val"), "default_val")

        # Test with invalid input
        self.assertIsNone(utils.get_safe_nested_dict_value(None, ["level1_a"]))
        self.assertEqual(utils.get_safe_nested_dict_value("not_a_dict", ["level1_a"], "default_val"), "default_val")
        self.assertIsNone(utils.get_safe_nested_dict_value(data, [])) # Empty keys list

    def test_speed_conversions(self):
        """Test kph_to_knots and mph_to_knots conversions."""
        self.assertAlmostEqual(utils.kph_to_knots(0), 0.0)
        self.assertAlmostEqual(utils.kph_to_knots(100), 53.9957, places=4)
        self.assertAlmostEqual(utils.kph_to_knots(55.5), 29.9676, places=4)

        self.assertAlmostEqual(utils.mph_to_knots(0), 0.0)
        self.assertAlmostEqual(utils.mph_to_knots(100), 86.8976, places=4)
        self.assertAlmostEqual(utils.mph_to_knots(62.1371), 53.9957, places=4) # Approx 100 kph

        # Test invalid input types (should log warning and return 0.0)
        logging.disable(logging.NOTSET) # Enable logging for this specific check
        with self.assertLogs(utils.logger, level='WARNING') as cm_kph:
            self.assertEqual(utils.kph_to_knots("not_a_number"), 0.0) # type: ignore
        self.assertTrue(any("Invalid type for kph_to_knots" in log_msg for log_msg in cm_kph.output))

        with self.assertLogs(utils.logger, level='WARNING') as cm_mph:
            self.assertEqual(utils.mph_to_knots(None), 0.0) # type: ignore
        self.assertTrue(any("Invalid type for mph_to_knots" in log_msg for log_msg in cm_mph.output))
        logging.disable(logging.CRITICAL) # Disable again


    def test_clean_sensor_name(self):
        """Test cleaning of sensor names for use as keys."""
        self.assertEqual(utils.clean_sensor_name("Engine RPM"), "engine_rpm")
        self.assertEqual(utils.clean_sensor_name("Coolant Temp. (C)"), "coolant_temp_c")
        self.assertEqual(utils.clean_sensor_name("Fuel Level %"), "fuel_level")
        self.assertEqual(utils.clean_sensor_name("  Leading/Trailing Spaces  "), "leading_trailing_spaces")
        self.assertEqual(utils.clean_sensor_name("Special!@#Chars"), "special_chars")
        self.assertEqual(utils.clean_sensor_name("Multiple___Underscores"), "multiple_underscores")
        self.assertEqual(utils.clean_sensor_name("_StartEnd_"), "startend")
        self.assertEqual(utils.clean_sensor_name(""), "") # Empty string
        self.assertEqual(utils.clean_sensor_name(123), "unknown_sensor") # type: ignore Invalid type

    def test_rate_limiter(self):
        """Test the RateLimiter class."""
        interval = 0.1  # 100 ms
        limiter = utils.RateLimiter(interval)

        # First trigger should always be allowed
        self.assertTrue(limiter.try_trigger(), "First trigger should be allowed.")
        self.assertAlmostEqual(limiter.time_since_last_trigger(), 0.0, delta=0.01)

        # Second trigger immediately after should be disallowed
        self.assertFalse(limiter.try_trigger(), "Immediate second trigger should be disallowed.")
        
        # Check time to next trigger
        self.assertLessEqual(limiter.time_to_next_trigger(), interval)
        self.assertGreater(limiter.time_to_next_trigger(), 0)

        # Wait for less than the interval
        time.sleep(interval / 2)
        self.assertFalse(limiter.try_trigger(), "Trigger before interval completion should be disallowed.")
        
        # Wait for the remainder of the interval (plus a small epsilon)
        time.sleep((interval / 2) + 0.01)
        self.assertTrue(limiter.try_trigger(), "Trigger after interval completion should be allowed.")
        self.assertAlmostEqual(limiter.time_since_last_trigger(), 0.0, delta=0.01)

        # Test reset: ensure limiter blocks immediately after a trigger,
        # and that reset() allows an immediate trigger again.
        self.assertFalse(limiter.try_trigger()) # Should be limited immediately after previous trigger
        limiter.reset()
        self.assertTrue(limiter.try_trigger(), "Trigger after reset should be allowed.")

    def test_rate_limiter_invalid_interval(self):
        """Test RateLimiter with invalid interval."""
        with self.assertRaises(ValueError):
            utils.RateLimiter(0)
        with self.assertRaises(ValueError):
            utils.RateLimiter(-1.0)

if __name__ == '__main__':
    # To run tests from the command line from the project root:
    # python -m unittest tests.test_utils
    # Or using pytest:
    # pytest tests/test_utils.py
    unittest.main(verbosity=2)
