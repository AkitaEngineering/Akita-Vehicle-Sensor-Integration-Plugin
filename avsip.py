import meshtastic
import time
import json
import threading
import os
import argparse
import obd
import paho.mqtt.client as mqtt
from meshtastic.util import get_lora_config
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class AVSIP:
    def __init__(self, interface, config_file="avsip_config.json"):
        self.interface = interface
        self.config_file = config_file
        self.sensor_data = {}
        self.sensor_thread = None
        self.user_id = interface.meshtastic.getMyNodeInfo()['num']
        self.lora_config = get_lora_config(interface.meshtastic)
        self.load_config()
        self.obd_connection = None
        self.mqtt_client = None
        self.connect_obd()
        self.connect_mqtt()
        self.obd_lock = threading.Lock()
        self.mqtt_lock = threading.Lock()

    def load_config(self):
        try:
            with open(self.config_file, "r") as f:
                self.config = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logging.error(f"Error loading config: {e}")
            self.config = {}

    def connect_obd(self):
        try:
            if obd.OBD().status() == obd.OBDStatus.CAR_RUNNING:
                with self.obd_lock:
                    self.obd_connection = obd.OBD()
                    if self.obd_connection.is_connected():
                        logging.info("AVSIP: OBD-II connection established.")
                    else:
                        logging.warning("AVSIP: OBD-II connection failed.")
            else:
                logging.warning("AVSIP: Vehicle not running, OBD-II not connected.")
        except Exception as e:
            logging.error(f"AVSIP: Error connecting to OBD-II: {e}")

    def connect_mqtt(self):
        try:
            with self.mqtt_lock:
                self.mqtt_client = mqtt.Client("avsip_mqtt")
                self.mqtt_client.on_connect = self.on_mqtt_connect
                self.mqtt_client.on_disconnect = self.on_mqtt_disconnect
                if self.config.get("mqtt", {}).get("user"):
                    self.mqtt_client.username_pw_set(self.config["mqtt"]["user"], self.config["mqtt"]["password"])
                self.mqtt_client.connect(self.config["mqtt"]["host"], self.config["mqtt"]["port"], 60)
                self.mqtt_client.loop_start()
                logging.info("AVSIP: MQTT connection established.")
        except Exception as e:
            logging.error(f"AVSIP: Error connecting to MQTT: {e}")

    def on_mqtt_connect(self, client, userdata, flags, rc):
        if rc == 0:
            logging.info(f"AVSIP: MQTT connected: {client._client_id}")
        else:
            logging.warning(f"AVSIP: MQTT connection failed: {client._client_id}, rc={rc}")

    def on_mqtt_disconnect(self, client, userdata, rc):
        logging.warning(f"AVSIP: MQTT disconnected: {client._client_id}, rc={rc}")

    def start_sensor_broadcast(self):
        self.sensor_thread = threading.Thread(target=self._send_sensor_broadcast)
        self.sensor_thread.start()
        logging.info("AVSIP: Sensor broadcast started.")

    def stop_sensor_broadcast(self):
        if self.sensor_thread:
            self.sensor_thread.join(timeout=2)
            logging.info("AVSIP: Sensor broadcast stopped.")

    def _send_sensor_broadcast(self):
        while True:
            try:
                self.connect_obd() #recheck obd connection.
                if self.obd_connection and self.obd_connection.is_connected():
                    sensor_values = self.get_obd_data()
                    if sensor_values:
                        self.sensor_data = {
                            "type": "vehicle_sensor",
                            "user_id": self.user_id,
                            "sensor_values": sensor_values,
                            "timestamp": time.time(),
                        }
                        self.interface.sendData(self.sensor_data, portNum=self.config.get("meshtastic_port", meshtastic.constants.DATA_APP))
                        if self.mqtt_client and self.mqtt_client.is_connected():
                            with self.mqtt_lock:
                                self.mqtt_client.publish(self.config["mqtt"]["topic"], json.dumps(self.sensor_data), qos=self.config.get("mqtt", {}).get("qos", 0))
                time.sleep(self.config.get("interval", 10))
            except Exception as e:
                logging.error(f"AVSIP: Error in sensor broadcast: {e}")

    def get_obd_data(self):
        if not self.obd_connection or not self.obd_connection.is_connected():
            return None
        data = {}
        commands = self.config.get("obd_commands", ["SPEED", "RPM", "COOLANT_TEMP"])
        for command_name in commands:
            try:
                command = getattr(obd.commands, command_name)
                response = self.obd_connection.query(command)
                if response and not response.is_null():
                    if type(response.value.magnitude) is float:
                        data[str(command)] = round(response.value.magnitude, 2)
                    else:
                        data[str(command)] = response.value.magnitude
                else:
                    data[str(command)] = None
            except Exception as e:
                logging.warning(f"Error querying OBD-II command {command_name}: {e}")
        return data

    def handle_incoming(self, packet, interface):
        if packet['decoded']['portNum'] == meshtastic.constants.DATA_APP:
            decoded = packet['decoded']['payload']
            if decoded.get("type") == "vehicle_sensor":
                logging.info(f"AVSIP: Vehicle sensor data received: {decoded}")

    def onConnection(self, interface, connected):
        if connected:
            logging.info("AVSIP: Meshtastic connected.")
            self.start_sensor_broadcast()
        else:
            logging.info("AVSIP: Meshtastic disconnected.")
            self.stop_sensor_broadcast()

def onReceive(packet, interface):
    avsip.handle_incoming(packet, interface)

def onConnection(interface, connected):
    avsip.onConnection(interface, connected)

def main():
    parser = argparse.ArgumentParser(description="Akita Vehicle Sensor Integration Plugin")
    parser.add_argument("--config", default="avsip_config.json", help="AVSIP config file")
    args = parser.parse_args()

    interface = meshtastic.SerialInterface()
    global avsip
    avsip = AVSIP(interface, args.config)
    interface.addReceiveCallback(onReceive)
    interface.addConnectionCallback(onConnection)

if __name__ == '__main__':
    main()
