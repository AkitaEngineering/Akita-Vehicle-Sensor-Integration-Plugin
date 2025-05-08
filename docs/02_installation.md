# 02: Installation Guide

This guide will walk you through the steps to install AVSIP on your system. It's recommended to use a Linux-based system (like Raspberry Pi OS, Ubuntu, or Debian) as the primary development and deployment environment, though it may work on other systems with Python 3 support.

## Prerequisites

### Software
* **Python:** Python 3.7 or newer. You can check your Python version by running `python3 --version`.
* **pip:** The Python package installer. Usually comes with Python. Check with `pip3 --version`.
* **git:** For cloning the repository. Check with `git --version`.
* **Build Essentials (Linux):** For some Python packages that compile from source, you might need build tools.
    ```bash
    sudo apt-get update
    sudo apt-get install python3-dev build-essential libffi-dev libssl-dev -y # For Debian/Ubuntu based
    ```

### Hardware
* **Host System:** A computer to run AVSIP (e.g., Raspberry Pi 3/4/5, laptop, or other single-board computer).
* **Meshtastic Device:** A compatible Meshtastic device (e.g., LilyGo T-Beam, Heltec LoRa 32) flashed with recent Meshtastic firmware. This device should be connectable to your host system (usually via USB).
* **OBD-II Adapter:**
    * A standard ELM327-compatible OBD-II adapter.
    * Connection type depends on your `python-obd` setup:
        * **USB:** Typically `/dev/ttyUSB0` or similar.
        * **Bluetooth:** Requires Bluetooth pairing with the host system. The MAC address will be needed.
        * **Wi-Fi:** Requires connection to the adapter's Wi-Fi network. IP and port will be needed.
* **CAN Bus Interface (Optional):**
    * If you plan to use CAN bus integration, you'll need a CAN interface compatible with `python-can` on your host system.
    * Common options for Raspberry Pi include:
        * MCP2515-based SPI CAN controllers (e.g., PiCAN2, Waveshare RS485 CAN HAT).
        * USB CAN adapters (e.g., Kvaser, PEAK-System PCAN-USB).
    * Ensure drivers and kernel modules (like `socketcan`) are correctly set up.

## Installation Steps

### 1. Clone the Repository

Open a terminal and navigate to the directory where you want to install AVSIP. Then, clone the official repository:
```bash
git clone [https://github.com/AkitaEngineering/Akita-Vehicle-Sensor-Integration-Plugin.git](https://github.com/AkitaEngineering/Akita-Vehicle-Sensor-Integration-Plugin.git)
cd Akita-Vehicle-Sensor-Integration-Plugin
```
## 2. Set Up a Python Virtual Environment (Recommended)

Using a virtual environment is highly recommended to isolate AVSIP's dependencies from your system's global Python packages.

- **Ensure `venv` is installed**:

  ```bash
  sudo apt-get install python3-venv -y  # For Debian/Ubuntu based
  ```

- **Create a virtual environment (e.g., named `.venv`)**:

  ```bash
  python3 -m venv .venv
  ```

- **Activate the virtual environment**:

  - On **Linux/macOS**:

    ```bash
    source .venv/bin/activate
    ```

  - On **Windows**:

    - Git Bash:

      ```bash
      source .venv/Scripts/activate
      ```

    - PowerShell:

      ```powershell
      .venv\Scripts\Activate.ps1
      ```

      *(You might need to set execution policy:)*

      ```powershell
      Set-ExecutionPolicy Unrestricted -Scope Process
      ```

  You should see the virtual environment's name (e.g., `(.venv)`) in your terminal prompt.

---

## 3. Install Dependencies

With the virtual environment activated, install the required Python packages using the `requirements.txt` file:

```bash
pip install -r requirements.txt
```

This will install `meshtastic`, `paho-mqtt`, `python-obd`, `python-can`, `jsonschema` (if added for config validation), and any other necessary libraries.

> **Note on `python-can`**:  
> Depending on your CAN interface, you might need to install additional drivers or system libraries.  
> Refer to the `python-can` documentation for interface-specific setup instructions (e.g., for SocketCAN, Kvaser, PEAK).

---

## 4. Initial Hardware Setup

### Meshtastic Device:

- Connect your Meshtastic device to the host system (usually via USB).
- Ensure it's powered on and recognized by the system. You might need to identify its serial port (e.g., `/dev/ttyUSB0` or `/dev/ttyACM0` on Linux).
- You can test the connection using the Meshtastic CLI:

  ```bash
  meshtastic --info
  ```

### OBD-II Adapter:

- **USB**: Connect the adapter. Note the serial port (e.g., `/dev/ttyUSB1`).
- **Bluetooth**: Pair the OBD-II adapter with your host system using your system's Bluetooth manager. Note the MAC address.
- **Wi-Fi**: Connect your host system to the Wi-Fi network broadcast by the OBD-II adapter. Note its IP address and port (often `35000`).
- Ensure your vehicle's ignition is in the "ON" position (or the engine is running) for the OBD-II adapter to communicate with the ECU.

### CAN Bus Interface (If Used):

- Connect your CAN interface to the host system and to the vehicle's CAN bus.

- For **SocketCAN** (e.g., MCP2515 on Raspberry Pi):

  ```bash
  sudo ip link set can0 up type can bitrate 500000  # Adjust bitrate as needed
  ```

- You can test with:

  ```bash
  candump can0
  ```

- Refer to your specific CAN interface's documentation for setup.

---

## 5. Configuration File

AVSIP requires a configuration file named `avsip_config.json` in the root directory where you run the script (or specified via the `--config` argument).

- An example configuration file is provided at:

  ```bash
  config/avsip_config.example.json
  ```

- Copy this example to the root of the project (or your desired runtime directory) and rename it:

  ```bash
  cp config/avsip_config.example.json ./avsip_config.json
  ```

- Crucially, edit `avsip_config.json` with your specific settings for Meshtastic, OBD-II, CAN bus, MQTT, and Traccar.  
  Refer to the `03_configuration.md` guide for detailed instructions on each parameter.

---

## ✅ Installation Complete!

Once you have completed these steps and properly configured your `avsip_config.json` file, you are ready to run AVSIP.  
See the main `README.md` or the upcoming sections for instructions on running the application.

If you encounter any issues during installation, refer to the `09_troubleshooting.md` guide or open an issue on the GitHub repository.
