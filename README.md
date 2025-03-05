# Akita Vehicle Sensor Integration Plugin (AVSIP)

AVSIP is a Meshtastic plugin that integrates OBD-II vehicle sensor data into the Meshtastic network and uploads it to an MQTT server, designed for enhanced performance, robustness, and potential commercial vehicle readiness.

## Features

-   **OBD-II Integration:** Reads live vehicle data from an OBD-II adapter.
-   **Meshtastic Broadcast:** Broadcasts vehicle sensor data over the Meshtastic network.
-   **MQTT Upload:** Uploads vehicle sensor data to an MQTT server.
-   **Configurable Interval:** Allows users to adjust the data broadcast and upload interval.
-   **Configurable MQTT Settings:** Loads MQTT server settings from a JSON configuration file, including QoS.
-   **Configurable OBD-II Commands:** Users can specify which OBD-II commands to query.
-   **Configurable Meshtastic Port:** Allows the user to change which meshtastic port the data is sent on.
-   **Thread Safety:** Implements locks for OBD-II and MQTT interactions.
-   **Robust Error Handling:** Includes granular error handling for OBD-II commands, MQTT connections, and data processing.
-   **Data Optimization:** Reduces bandwidth usage by allowing configurable data points and reducing decimal places.
-   **Automatic OBD-II Connection Check:** Only connects to OBDII when the vehicle is running, and rechecks on a timed interval.
-   **Comprehensive Logging:** Provides detailed logging for debugging and monitoring.

## Installation

1.  Install the `obd` and `paho-mqtt` Python packages: `pip install python-obd paho-mqtt`.
2.  Place `avsip.py` in your Meshtastic plugins directory.
3.  Create an `avsip_config.json` file with your configuration settings.
4.  Connect an OBD-II adapter to your vehicle.
5.  Run Meshtastic with the plugin enabled.

## Usage

-   Vehicle sensor data is automatically broadcast and uploaded at the configured interval.
-   Received sensor data is displayed in the Meshtastic logs.
-   Detailed logs are written to the console.

## Configuration (avsip_config.json)

-   `interval`: The data broadcast and upload interval in seconds (default: 10).
-   `meshtastic_port`: The meshtastic port number that the data will be sent on (default: 2).
-   `obd_commands`: An array of OBD-II command names to query (e.g., `["SPEED", "RPM", "COOLANT_TEMP"]`).
-   `mqtt`: MQTT server settings:
    -   `host`: The MQTT server hostname or IP address.
    -   `port`: The MQTT server port.
    -   `topic`: The MQTT topic to publish messages to.
    -   `user`: The MQTT username (optional).
    -   `password`: The MQTT password (optional).
    -   `qos`: The MQTT Quality of Service level (0, 1, or 2) (default: 1).
 
## Command-Line Arguments
--config: Specifies the AVSIP configuration file (default: avsip_config.json).

## Dependencies
- Meshtastic Python API
- python-obd
- paho-mqtt


**Example avsip_config.json:**

```json
{
    "interval": 10,
    "meshtastic_port": 2,
    "obd_commands": ["SPEED", "RPM", "COOLANT_TEMP", "FUEL_LEVEL"],
    "mqtt": {
        "host": "mqtt.example.com",
        "port": 1883,
        "topic": "vehicle/data",
        "user": "mqtt_user",
        "password": "mqtt_password",
        "qos": 1
    }
}


