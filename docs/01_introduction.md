# 01: Introduction to AVSIP

## Project Vision and Goals

The Akita Vehicle Sensor Integration Plugin (AVSIP) is envisioned as a versatile and reliable open-source solution for vehicle telemetry. Our primary goal is to empower users, from automotive enthusiasts to professional fleet managers, with the ability to easily access, process, and transmit a wide range of vehicle data.

We aim to:
* Provide a **comprehensive** data acquisition platform supporting common automotive interfaces like OBD-II and CAN bus.
* Offer **flexible** data transmission options, including low-power, long-range Meshtastic networks and standard IoT protocols like MQTT.
* Enable **seamless integration** with popular vehicle tracking platforms such as Traccar.
* Ensure the system is **highly configurable** to adapt to diverse vehicle types and user requirements.
* Build a **robust and resilient** plugin capable of operating reliably in real-world vehicle environments.
* Foster an **active community** for ongoing development, support, and feature enhancement.

## Core Functionalities

AVSIP is built around the following core functionalities:

1.  **Data Acquisition:**
    * **OBD-II:** Connects to standard OBD-II adapters to read parameters like speed, RPM, engine coolant temperature, fuel level, diagnostic trouble codes (DTCs), and more. Users can specify which parameters to query.
    * **CAN Bus:** Interfaces with vehicle CAN buses to capture raw message frames. AVSIP allows users to define custom parsers to decode these messages into meaningful sensor data (e.g., tire pressure, specific component temperatures, custom sensor readings).
    * **GPS (via Meshtastic):** Leverages the GPS capabilities of connected Meshtastic devices to obtain location data (latitude, longitude, altitude, speed, etc.).

2.  **Data Processing:**
    * Aggregates data from all configured sources into a structured format.
    * Applies necessary conversions or calculations as defined by the user (primarily for CAN data).
    * Timestamps data for accurate logging and tracking.

3.  **Data Transmission:**
    * **Meshtastic:** Broadcasts the collected sensor data over a Meshtastic mesh network. This is ideal for off-grid scenarios or applications requiring peer-to-peer data sharing.
    * **MQTT:** Publishes sensor data to an MQTT broker. This enables integration with a wide array of IoT platforms, databases, and dashboards for further analysis and visualization.
    * **Traccar:** Sends formatted location and telemetry data directly to a Traccar server, allowing for real-time vehicle tracking and fleet management.

4.  **Configuration and Control:**
    * All operational aspects are managed through a single JSON configuration file (`avsip_config.json`).
    * The plugin operates as a background service or script, continuously collecting and transmitting data at user-defined intervals.

## System Architecture Overview

AVSIP typically runs on a small single-board computer (like a Raspberry Pi) or a laptop situated within the vehicle. The main components and data flow are as follows:

