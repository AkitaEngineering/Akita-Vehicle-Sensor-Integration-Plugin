# AVSIP Documentation Hub

Welcome to the comprehensive documentation for the Akita Vehicle Sensor Integration Plugin (AVSIP). This collection of documents will guide you through understanding, installing, configuring, and utilizing AVSIP for your vehicle telemetry needs.

AVSIP is a powerful tool designed for flexibility and robustness, enabling you to gather critical vehicle data and transmit it through various channels. Whether you're a hobbyist looking to monitor your personal vehicle or an engineer integrating telemetry into a commercial fleet, AVSIP provides the necessary features and customization options.

## Table of Contents

1.  [**Introduction (01_introduction.md)**](01_introduction.md)
    * Project Vision and Goals
    * Core Functionalities
    * System Architecture Overview
    * Target Audience

2.  [**Installation (02_installation.md)**](02_installation.md)
    * Prerequisites (Software and Hardware)
    * Cloning the Repository
    * Setting up a Python Virtual Environment
    * Installing Dependencies (`requirements.txt`)
    * Initial Hardware Setup (Meshtastic, OBD-II, CAN Interface)

3.  [**Configuration (03_configuration.md)**](03_configuration.md)
    * Understanding `avsip_config.json`
    * General Settings (Logging, Intervals)
    * Meshtastic Configuration
    * OBD-II Configuration (Commands, Connection Parameters)
    * CAN Bus Configuration (Interface, Bitrate, Message Definitions)
    * MQTT Broker Configuration
    * Traccar Server Configuration
    * Example Configuration Snippets

4.  [**OBD-II Integration (04_obd_integration.md)**](04_obd_integration.md)
    * Supported OBD-II Adapters
    * Selecting OBD-II Commands
    * Understanding OBD-II Data Units
    * Troubleshooting OBD-II Connections

5.  [**CAN Bus Integration (05_can_integration.md)**](05_can_integration.md)
    * Supported CAN Interfaces (`python-can` backends)
    * Identifying CAN IDs and Messages
    * Defining CAN Message Parsers in `avsip_config.json`
        * Data Extraction (Byte Order, Start Bit, Length)
        * Scaling and Offset Application
        * Signed vs. Unsigned Values
    * Tools for CAN Bus Analysis (e.g., `candump`, `can-utils`)
    * Troubleshooting CAN Bus Connections

6.  [**Meshtastic Setup (06_meshtastic_setup.md)**](06_meshtastic_setup.md)
    * Basic Meshtastic Network Requirements
    * AVSIP Data Transmission over Meshtastic
    * Configuring Meshtastic Port Numbers

7.  [**MQTT Setup (07_mqtt_setup.md)**](07_mqtt_setup.md)
    * Connecting to an MQTT Broker
    * Understanding MQTT Topics and QoS
    * Securing MQTT Communication (User/Pass, TLS - if applicable)
    * Integrating AVSIP data with other MQTT-compatible services

8.  [**Traccar Setup (08_traccar_setup.md)**](08_traccar_setup.md)
    * Configuring your Traccar Server to receive data from AVSIP
    * Understanding the Traccar data format used by AVSIP
    * Setting up Device ID in Traccar
    * Viewing AVSIP data in the Traccar interface

9.  [**Troubleshooting (09_troubleshooting.md)**](09_troubleshooting.md)
    * Common Issues and Solutions
    * Interpreting Log Files
    * Diagnosing Connection Problems (OBD, CAN, MQTT, Traccar, Meshtastic)
    * Reporting Bugs and Requesting Support

10. [**Developer Guide (10_developer_guide.md)**](10_developer_guide.md)
    * Project Structure Overview
    * Setting up a Development Environment
    * Coding Standards and Style (PEP 8, Docstrings)
    * Adding Support for New OBD-II Commands
    * Extending CAN Bus Message Parsing Capabilities
    * Integrating New Data Transmission Channels
    * Running Tests
    * Contribution Guidelines and Pull Request Process

11. [**Logging (11_logging.md)**](11_logging.md)
    * Understanding AVSIP's Logging System
    * Log Levels and Their Meanings
    * Log Format
    * Configuring Log Output (e.g., to file - if implemented)

We encourage you to read through these documents to get the most out of AVSIP. If you have any questions or find areas that need clarification, please don't hesitate to open an issue on the project's GitHub repository.
