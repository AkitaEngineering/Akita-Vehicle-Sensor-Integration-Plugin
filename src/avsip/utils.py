# src/avsip/utils.py

import logging
import time
from typing import Any, Dict, Optional, Union
import re

logger = logging.getLogger(__name__)

def get_safe_nested_dict_value(data_dict: Dict, keys: list[str], default: Optional[Any] = None) -> Optional[Any]:
    """
    Safely retrieves a value from a nested dictionary.

    Args:
        data_dict: The dictionary to traverse.
        keys: A list of keys representing the path to the desired value.
        default: The value to return if any key is not found or the path is invalid.

    Returns:
        The value if found, otherwise the default.
    """
    if not isinstance(data_dict, dict):
        return default
    temp_dict = data_dict
    for key in keys:
        if isinstance(temp_dict, dict) and key in temp_dict:
            temp_dict = temp_dict[key]
        else:
            return default
    return temp_dict

def kph_to_knots(kph: Union[float, int]) -> float:
    """
    Converts speed from kilometers per hour (KPH) to knots.

    Args:
        kph: Speed in KPH.

    Returns:
        Speed in knots.
    """
    if not isinstance(kph, (float, int)):
        logger.warning(f"Invalid type for kph_to_knots: {type(kph)}. Returning 0.0.")
        return 0.0
    return kph * 0.539957

def mph_to_knots(mph: Union[float, int]) -> float:
    """
    Converts speed from miles per hour (MPH) to knots.

    Args:
        mph: Speed in MPH.

    Returns:
        Speed in knots.
    """
    if not isinstance(mph, (float, int)):
        logger.warning(f"Invalid type for mph_to_knots: {type(mph)}. Returning 0.0.")
        return 0.0
    return mph * 0.868976

def clean_sensor_name(name: str) -> str:
    """
    Cleans a sensor name to be a valid key (e.g., for MQTT topics or JSON keys).
    Replaces non-alphanumeric characters (except underscore) with underscores.
    Converts to lowercase.

    Args:
        name: The original sensor name.

    Returns:
        A cleaned version of the sensor name.
    """
    if not isinstance(name, str):
        return "unknown_sensor"
    # Replace spaces and special characters with underscores
    name = re.sub(r'[^\w_]', '_', name)
    # Remove consecutive underscores
    name = re.sub(r'_+', '_', name)
    # Remove leading/trailing underscores
    name = name.strip('_')
    return name.lower()

class RateLimiter:
    """
    A simple rate limiter to control the frequency of an action.
    """
    def __init__(self, interval_seconds: float):
        """
        Initializes the RateLimiter.

        Args:
            interval_seconds: The minimum time interval (in seconds) between allowed actions.
        """
        if interval_seconds <= 0:
            raise ValueError("Interval must be positive.")
        self.interval = interval_seconds
        self.last_triggered_time = 0.0

    def try_trigger(self) -> bool:
        """
        Checks if the action can be triggered based on the interval.
        If allowed, updates the last triggered time and returns True.

        Returns:
            True if the action is allowed, False otherwise.
        """
        current_time = time.monotonic()
        if current_time - self.last_triggered_time >= self.interval:
            self.last_triggered_time = current_time
            return True
        return False

    def reset(self):
        """Resets the last triggered time, allowing an immediate trigger next time."""
        self.last_triggered_time = 0.0

    def time_since_last_trigger(self) -> float:
        """Returns the time elapsed since the last successful trigger."""
        return time.monotonic() - self.last_triggered_time

    def time_to_next_trigger(self) -> float:
        """Returns the remaining time until the next trigger is allowed."""
        elapsed = self.time_since_last_trigger()
        remaining = self.interval - elapsed
        return max(0, remaining)

if __name__ == "__main__":
    # Example Usage
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # Test get_safe_nested_dict_value
    my_dict = {"a": {"b": {"c": 100, "d": [1,2,3]}, "e": 200}, "f": 300}
    logger.info(f"Value of a.b.c: {get_safe_nested_dict_value(my_dict, ['a', 'b', 'c'])}") # Expected: 100
    logger.info(f"Value of a.b.d: {get_safe_nested_dict_value(my_dict, ['a', 'b', 'd'])}") # Expected: [1,2,3]
    logger.info(f"Value of a.x.y (non-existent): {get_safe_nested_dict_value(my_dict, ['a', 'x', 'y'])}") # Expected: None
    logger.info(f"Value of a.x.y with default: {get_safe_nested_dict_value(my_dict, ['a', 'x', 'y'], 'Not Found')}") # Expected: Not Found
    logger.info(f"Value from non-dict: {get_safe_nested_dict_value('not a dict', ['a'])}") # Expected: None

    # Test speed conversions
    logger.info(f"100 KPH to Knots: {kph_to_knots(100):.2f}") # Expected: 54.00
    logger.info(f"60 MPH to Knots: {mph_to_knots(60):.2f}")   # Expected: 52.14

    # Test clean_sensor_name
    logger.info(f"Clean 'Engine RPM!': {clean_sensor_name('Engine RPM!')}") # Expected: engine_rpm
    logger.info(f"Clean 'Coolant Temp. (C)': {clean_sensor_name('Coolant Temp. (C)')}") # Expected: coolant_temp_c
    logger.info(f"Clean '  leading_trailing_  ': {clean_sensor_name('  leading_trailing_  ')}") # Expected: leading_trailing

    # Test RateLimiter
    limiter = RateLimiter(2.0) # Allow action every 2 seconds
    for i in range(10):
        if limiter.try_trigger():
            logger.info(f"Action triggered at iteration {i} (Time: {time.monotonic():.2f})")
        else:
            logger.info(f"Action rate limited at iteration {i}. Next trigger in {limiter.time_to_next_trigger():.2f}s")
        time.sleep(0.5)

    limiter.reset()
    logger.info(f"Limiter reset. try_trigger(): {limiter.try_trigger()}") # Should be True
