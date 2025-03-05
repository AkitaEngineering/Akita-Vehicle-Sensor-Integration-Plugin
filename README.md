# Akita Vehicle Sensor Integration Plugin (AVSIP)

AVSIP is a comprehensive Meshtastic plugin designed for advanced vehicle monitoring, integrating OBD-II, CAN bus, and Traccar support. It sends data over Meshtastic and MQTT, tailored for enhanced performance, robustness, and commercial vehicle readiness.

## Features

-   **OBD-II Integration:** Reads live vehicle data from an OBD-II adapter.
-   **CAN Bus Support:** Reads data from the vehicle's CAN bus (requires `python-can`).
-   **DTC (Diagnostic Trouble Code) Reporting:** Reads and reports vehicle DTCs.
-   **Meshtastic Broadcast:** Broadcasts vehicle sensor data, including DTCs and GPS, over the Meshtastic network.
-   **MQTT Upload:** Uploads vehicle sensor data and DTCs to an MQTT server.
-   **Traccar Integration:** Sends data to a Traccar server for fleet management.
-   **GPS Integration:** Includes GPS data from Meshtastic in broadcasts.
-   **Configurable Interval:** Allows users to adjust the data broadcast and upload interval.
-   **Configurable MQTT Settings:** Loads MQTT server settings from a JSON configuration file, including QoS.
-   **Configurable OBD-II Commands:** Users can specify which OBD-II commands to query.
-   **Configurable Meshtastic Port:** Allows the user to change which Meshtastic port the data is sent on.
-   **Thread Safety:** Implements locks for OBD-II and MQTT interactions.
-   **Robust Error Handling:** Includes granular error handling for OBD-II commands, CAN bus, MQTT connections, Traccar, and data processing.
-   **Data Optimization:** Reduces bandwidth usage by allowing configurable data points and reducing decimal places.
-   **Automatic OBD-II Connection Check:** Only connects to OBDII when the vehicle is running, and rechecks on a timed interval.
-   **Comprehensive Logging:** Provides detailed logging for debugging and monitoring.
-   **Fleet Management Integration Considerations:** Provides a foundation for integrating with fleet management systems.
-   **Security Considerations:** Highlights the importance of implementing security measures for vehicle data.
-   **Compliance Considerations:** Emphasizes the need to comply with industry standards and regulations.

## Installation

1.  Install the required Python packages: `pip install python-obd paho-mqtt python-can`.
2.  Place `avsip.py` in your Meshtastic plugins directory.
3.  Create an `avsip_config.json` file with your configuration settings.
4.  Connect an OBD-II adapter and, if applicable, a CAN bus adapter to your vehicle.
5.  Run Meshtastic with the plugin enabled.

## Usage

-   Vehicle sensor data, DTCs, and GPS data are automatically broadcast and uploaded at the configured interval.
-   Received sensor data and DTCs are displayed in the Meshtastic logs.
-   Detailed logs are written to the console.

## Command-Line Arguments
--config: Specifies the AVSIP configuration file (default: avsip_config.json).

## Dependencies
- Meshtastic Python API
- python-obd
- paho-mqtt
- python-can

## Commercial Vehicle Readiness
-This plugin is designed with commercial vehicle applications in mind, including support for CAN bus and Traccar.
-DTC reporting and GPS integration are crucial for vehicle diagnostics and tracking.

## Configuration (avsip_config.json)

-   `interval`: The data broadcast and upload interval in seconds (default: 10).
-   `meshtastic_port`: The Meshtastic port number that the data will be sent on (default: 2).
-   `obd_commands`: An array of OBD-II command names to query (e.g., `["SPEED", "RPM", "COOLANT_TEMP"]`).
-   `can_enabled`: Boolean to enable CAN bus reading (default: `false`).
-   `mqtt`: MQTT server settings:
    -   `host`: The MQTT server hostname or IP address.
    -   `port`: The MQTT server port.
    -   `topic`: The MQTT topic to publish messages to.
    -   `user`: The MQTT username (optional).
    -   `password`: The MQTT password (optional).
    -   `qos`: The MQTT Quality of Service level (0, 1, or 2) (default: 1).
-   `traccar`: Traccar server settings:
    -   `enabled`: Boolean to enable Traccar integration (default: `false`).
    -   `host`: The Traccar server hostname or IP address.
    -   `port`: The Traccar server port.
    -   `device_id`: The Traccar device ID.

**Example avsip_config.json:**

```json
{
    "interval": 10,
    "meshtastic_port": 2,
    "obd_commands": ["SPEED", "RPM", "COOLANT_TEMP", "FUEL_LEVEL"],
    "can_enabled": true,
    "mqtt": {
        "host": "mqtt.example.com",
        "port": 1883,
        "topic": "vehicle/data",
        "user": "mqtt_user",
        "password": "mqtt_password",
        "qos": 1
    },
    "traccar": {
        "enabled": true,
        "host": "[traccar.example.com](https://www.google.com/search?q=traccar.example.com)",
        "port": 5000,
        "device_id": "vehicle123"
    }
}
