# Akita Vehicle Sensor Integration Plugin (AVSIP)

AVSIP is a comprehensive vehicle telemetry system designed to gather and transmit sensor data from various sources, including OBD-II, CAN bus, and GPS, across multiple communication channels such as Meshtastic and MQTT. It also provides seamless integration with Traccar for vehicle tracking.

## Features

* **Multi-Source Data Acquisition:**
    * OBD-II data retrieval (speed, RPM, coolant temperature, etc.).
    * Diagnostic Trouble Code (DTC) reading.
    * CAN bus message capture.
    * GPS data integration via Meshtastic.
* **Multi-Channel Data Transmission:**
    * Meshtastic network communication.
    * MQTT broker integration.
    * Traccar server integration for vehicle tracking.
* **Highly Configurable:**
    * Utilizes a `avsip_config.json` file for easy customization of settings.
    * Configurable OBD-II commands, MQTT settings, Traccar integration, and more.
* **Robust Error Handling:**
    * Extensive logging and exception handling for reliable operation.
* **Threading Implementation:**
    * Sensor data collection and transmission run in a dedicated thread for non-blocking execution.
* **Connection Status Monitoring:**
    * Checks OBD-II connection status and vehicle running status.
    * MQTT connection and disconnection callbacks.
* **CAN Bus Integration:**
    * Configurable CAN bus integration.

## Prerequisites

* Python 3.x
* Required Python packages:
    * `meshtastic`
    * `obd`
    * `paho-mqtt`
    * `python-can`
* A configured Meshtastic network.
* An OBD-II adapter.
* An MQTT broker.
* A Traccar server (optional).
* A CAN bus interface (optional).

## Installation

1.  Clone the repository.
2.  Install the required Python packages:

    ```bash
    pip install meshtastic obd paho-mqtt python-can
    ```

## Configuration

1.  Create an `avsip_config.json` file in the same directory as the script.
2.  Populate the `avsip_config.json` file with your specific settings. Here's an example:

    ```json
    {
        "mqtt": {
            "host": "your_mqtt_broker_host",
            "port": 1883,
            "user": "your_mqtt_username",
            "password": "your_mqtt_password",
            "topic": "vehicle/sensors",
            "qos": 0
        },
        "obd_commands": ["SPEED", "RPM", "COOLANT_TEMP"],
        "interval": 10,
        "meshtastic_port": 4802,
        "traccar": {
            "enabled": true,
            "host": "your_traccar_host",
            "port": 5000,
            "device_id": "your_device_id"
        },
        "can_enabled": true
    }
    ```

    * Replace placeholder values with your actual settings.
    * `obd_commands` is a list of OBD-II commands to retrieve.
    * `interval` is the data collection and transmission frequency in seconds.
    * `meshtastic_port` is the Meshtastic port number.
    * `traccar` contains the settings for the Traccar server.
    * `can_enabled` enables or disables the CAN bus functionality.
    * `qos` is the MQTT quality of service setting.

## Running the Script

1.  Ensure all prerequisites are met and your configuration file is properly configured.
2.  Connect your Meshtastic device and OBD-II adapter.
3.  Run the Python script:

    ```bash
    python your_script_name.py --config avsip_config.json
    ```

4.  To stop the script, press `Ctrl+C`.

## Logging

* The script utilizes the `logging` module to log information, warnings, and errors.
* Logs are output to the console.
* The logging level can be adjusted in the code.

## Contributing

Contributions are welcome! Please feel free to submit pull requests or open issues.

