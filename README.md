# Akita Vehicle Sensor Integration Plugin (AVSIP)

AVSIP is a comprehensive vehicle telemetry system designed to gather and transmit sensor data from various sources, including OBD-II, CAN bus, and GPS, across multiple communication channels such as Meshtastic and MQTT. It also provides seamless integration with Traccar for vehicle tracking.

This plugin is tailored for enhanced performance, robustness, and is suitable for both hobbyist and commercial vehicle applications.

## Key Features

* **Multi-Source Data Acquisition:**
    * Real-time OBD-II data retrieval (e.g., speed, RPM, coolant temperature, fuel level).
    * Diagnostic Trouble Code (DTC) reading and reporting.
    * Flexible CAN bus message capture and decoding.
    * GPS data integration via connected Meshtastic devices.
* **Multi-Channel Data Transmission:**
    * Efficient data broadcast over Meshtastic networks.
    * Reliable data publishing to MQTT brokers for IoT integration.
    * Direct data forwarding to Traccar servers for live vehicle tracking.
* **Highly Configurable:**
    * Centralized JSON configuration file (`avsip_config.json`) for easy customization of all operational parameters.
    * User-definable OBD-II commands, CAN bus message definitions, MQTT settings, Traccar integration details, and data transmission intervals.
* **Robust and Resilient:**
    * Extensive logging for diagnostics and monitoring.
    * Graceful error handling and automatic reconnection attempts for network services (OBD-II, MQTT, Traccar).
    * Threaded architecture for non-blocking sensor data collection and transmission.
* **Status Monitoring:**
    * Checks and reports OBD-II connection status and vehicle running status.
    * MQTT connection and disconnection callbacks and logging.
    * CAN bus interface status monitoring.

## Quick Start

1.  **Prerequisites:**
    * Python 3.7+
    * Meshtastic device
    * OBD-II adapter (Bluetooth, Wi-Fi, or USB depending on your `python-obd` setup)
    * CAN bus interface (if CAN bus integration is enabled)
    * Access to an MQTT broker (optional)
    * Access to a Traccar server (optional)

2.  **Installation:**
    ```bash
    git clone [https://github.com/AkitaEngineering/Akita-Vehicle-Sensor-Integration-Plugin.git](https://github.com/AkitaEngineering/Akita-Vehicle-Sensor-Integration-Plugin.git)
    cd Akita-Vehicle-Sensor-Integration-Plugin
    pip install -r requirements.txt
    ```

3.  **Configuration:**
    * Copy `config/avsip_config.example.json` to the root directory as `avsip_config.json`.
    * Edit `avsip_config.json` with your specific settings for OBD-II, CAN bus, Meshtastic, MQTT, and Traccar. See the [Full Configuration Guide](docs/03_configuration.md) for details.

4.  **Running AVSIP:**
    * Ensure your Meshtastic device and OBD-II adapter are connected and powered.
    * If using CAN bus, ensure your CAN interface is connected.
    * Execute the main script (e.g., located in `src/avsip/core.py` or an example script like `run_avsip.py`):
        ```bash
        python run_avsip.py --config avsip_config.json
        ```
    * To stop the script, press `Ctrl+C`.

## Documentation

For detailed information on installation, configuration, specific integrations, troubleshooting, and development, please refer to the [**Full AVSIP Documentation**](./docs/index.md).

## Contributing

Contributions are highly welcome! Whether it's bug reports, feature requests, documentation improvements, or code contributions, please feel free to:
* Open an issue on the [GitHub Issues page](https://github.com/AkitaEngineering/Akita-Vehicle-Sensor-Integration-Plugin/issues).
* Submit a pull request with your proposed changes. Please refer to the [Developer Guide](./docs/10_developer_guide.md) for contribution guidelines.

## License

This project is licensed under the GNU General Public License v3.0. See the [LICENSE](./LICENSE) file for full details.


**License:** [GPLv3](https://www.gnu.org/licenses/gpl-3.0.en.html)
**Organization:** Akita Engineering
**Website:** [www.akitaengineering.com](http://www.akitaengineering.com)
**Project Repository:** [AkitaEngineering/Akita-Vehicle-Sensor-Integration-Plugin](https://github.com/AkitaEngineering/Akita-Vehicle-Sensor-Integration-Plugin)
