# /config/custom_components/lumentree/mqtt.py

import asyncio
import json
import ssl
import time
import logging # <<< ĐẢM BẢO CÓ IMPORT LOGGING Ở ĐẦU FILE
from typing import Any, Dict, Optional, Callable
from functools import partial

import paho.mqtt.client as paho
from paho.mqtt.client import MQTTMessage

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send

try:
    from .const import (
        DOMAIN, _LOGGER, MQTT_BROKER, MQTT_PORT, MQTT_USERNAME, MQTT_PASSWORD,
        MQTT_SUB_TOPIC_FORMAT, MQTT_PUB_TOPIC_FORMAT,
        SIGNAL_UPDATE_FORMAT, CONF_DEVICE_SN, MQTT_KEEPALIVE, KEY_LAST_RAW_MQTT
    )
    from .parser import parse_mqtt_payload, generate_modbus_read_command
except ImportError:
    # Fallback imports (vẫn cần logging ở đây phòng trường hợp import chính lỗi)
    # import logging # Không cần import lại nếu đã import ở trên
    _LOGGER = logging.getLogger(__name__)
    DOMAIN = "lumentree";
    MQTT_BROKER = "lesvr.suntcn.com"; MQTT_PORT = 1886; MQTT_USERNAME = "appuser"; MQTT_PASSWORD = "app666"
    MQTT_KEEPALIVE = 20; MQTT_SUB_TOPIC_FORMAT = "reportApp/{device_sn}"; MQTT_PUB_TOPIC_FORMAT = "listenApp/{device_sn}"
    SIGNAL_UPDATE_FORMAT = f"{DOMAIN}_mqtt_update_{{device_sn}}"; CONF_DEVICE_SN = "device_sn"; KEY_LAST_RAW_MQTT = "last_raw_mqtt_hex"
    def parse_mqtt_payload(payload_hex: str) -> Optional[Dict[str, Any]]: return None
    def generate_modbus_read_command(slave_id: int, func_code: int, start_addr: int, num_registers: int) -> Optional[str]: return None

RECONNECT_DELAY_SECONDS = 5
MAX_RECONNECT_ATTEMPTS = 10
CONNECT_TIMEOUT = 20

class LumentreeMqttClient:
    """Manages the MQTT connection, subscription, and message handling."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client_id: str, device_sn: str):
        """Initialize the MQTT client."""
        self.hass = hass; self.entry = entry; self._device_sn = device_sn; self._mqttc = None; self._client_id = client_id
        self._signal_update = SIGNAL_UPDATE_FORMAT.format(device_sn=self._device_sn)
        self._topic_sub = MQTT_SUB_TOPIC_FORMAT.format(device_sn=self._device_sn)
        self._topic_pub = MQTT_PUB_TOPIC_FORMAT.format(device_sn=self._device_sn)
        self._connect_lock = asyncio.Lock(); self._reconnect_attempts = 0; self._is_connected = False
        self._stopping = False; self._connected_event = asyncio.Event()

    @property
    def is_connected(self) -> bool: return self._is_connected

    async def connect(self) -> None:
        async with self._connect_lock:
            if self._is_connected: _LOGGER.debug(f"MQTT already connected for {self._device_sn}."); return
            self._stopping = False; self._connected_event.clear()
            self._mqttc = paho.Client(client_id=self._client_id, protocol=paho.MQTTv311, callback_api_version=paho.CallbackAPIVersion.VERSION1)
            self._mqttc.username_pw_set(username=MQTT_USERNAME, password=MQTT_PASSWORD)
            self._mqttc.on_connect = self._on_connect
            self._mqttc.on_disconnect = self._on_disconnect
            self._mqttc.on_message = self._on_message
            _LOGGER.info(f"Attempting connect: {MQTT_BROKER}:{MQTT_PORT} (Client: {self._client_id})")
            try:
                await self.hass.async_add_executor_job(self._mqttc.connect, MQTT_BROKER, MQTT_PORT, MQTT_KEEPALIVE)
                self._mqttc.loop_start()
                _LOGGER.info(f"MQTT loop started. Waiting for CONNACK (timeout: {CONNECT_TIMEOUT}s).")
                try:
                    await asyncio.wait_for(self._connected_event.wait(), timeout=CONNECT_TIMEOUT)
                    if not self._is_connected: raise ConnectionRefusedError("MQTT connection refused.")
                    _LOGGER.info(f"MQTT connection established.")
                except asyncio.TimeoutError: _LOGGER.error(f"MQTT connection timed out."); await self.disconnect(); raise ConnectionRefusedError("MQTT timeout.")
            except Exception as e:
                _LOGGER.error(f"Failed MQTT connect/loop start: {e}")
                if self._mqttc:
                    try: self._mqttc.loop_stop()
                    except Exception as stop_err: _LOGGER.warning(f"Error stopping loop: {stop_err}")
                self._mqttc = None; self._is_connected = False; self._connected_event.set()
                if isinstance(e, ConnectionRefusedError): raise
                raise ConnectionRefusedError(f"MQTT setup error: {e}") from e

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        if rc == paho.CONNACK_ACCEPTED:
            _LOGGER.info(f"MQTT connected (rc={rc}). Subscribing: {[self._topic_sub, self._topic_pub]}")
            self._reconnect_attempts = 0; self._is_connected = True
            try:
                topics_to_subscribe = [(self._topic_sub, 0), (self._topic_pub, 0)]
                result, mid = client.subscribe(topics_to_subscribe)
                if result == paho.MQTT_ERR_SUCCESS: _LOGGER.debug(f"Subscribe sent (mid={mid})")
                else: _LOGGER.error(f"Failed subscribe send (rc={result})")
                self.hass.loop.call_soon_threadsafe(async_dispatcher_send, self.hass, self._signal_update, {"mqtt_connected": True})
            except Exception as e: _LOGGER.error(f"Failed subscribe to topics: {e}")
            finally: self.hass.loop.call_soon_threadsafe(self._connected_event.set)
        else:
            err_map = {1: "Protocol Ver", 2: "ID Rejected", 3: "Server Unavailable", 4: "Bad User/Pass", 5: "Not Authorized"}
            _LOGGER.error(f"MQTT connection refused (rc={rc}): {err_map.get(rc, 'Unknown')}.")
            self._is_connected = False
            if rc != paho.CONNACK_REFUSED_SERVER_UNAVAILABLE: self.hass.loop.call_soon_threadsafe(self._connected_event.set)
            elif not self._stopping: self._schedule_reconnect()

    def _on_disconnect(self, client, userdata, rc, properties=None):
        was_connected = self._is_connected; self._is_connected = False
        self.hass.loop.call_soon_threadsafe(async_dispatcher_send, self.hass, self._signal_update, {"mqtt_connected": False})
        if rc == 0: _LOGGER.info(f"MQTT disconnected gracefully.")
        else: _LOGGER.warning(f"MQTT unexpectedly disconnected (rc={rc}).")
        if was_connected and not self._stopping: self._schedule_reconnect()

    def _schedule_reconnect(self):
        if self._reconnect_attempts < MAX_RECONNECT_ATTEMPTS:
            self._reconnect_attempts += 1; delay = min(RECONNECT_DELAY_SECONDS * (2 ** (self._reconnect_attempts - 1)), 60)
            _LOGGER.info(f"Scheduling MQTT reconnect {self._reconnect_attempts}/{MAX_RECONNECT_ATTEMPTS} in {delay}s.")
            self.hass.async_create_task(self._async_reconnect(delay))
        else:
            _LOGGER.error(f"MQTT reconnect failed after {MAX_RECONNECT_ATTEMPTS} attempts. Giving up.")
            self.hass.loop.call_soon_threadsafe(async_dispatcher_send, self.hass, self._signal_update, {"error": "MQTT_reconnect_failed"})

    async def _async_reconnect(self, delay):
         await asyncio.sleep(delay)
         if not self.is_connected and not self._stopping and self._mqttc:
             _LOGGER.debug(f"Attempting MQTT reconnect job...")
             try: await self.hass.async_add_executor_job(self._mqttc.reconnect)
             except Exception as e: _LOGGER.warning(f"MQTT reconnect job failed: {e}")

    def _on_message(self, client, userdata, msg):
        topic = msg.topic
        try:
            payload_bytes = msg.payload; payload_hex = payload_bytes.hex()
            _LOGGER.debug(f"MQTT msg recv: Topic='{topic}', Payload='{payload_hex[:60]}...'")
            if topic == self._topic_sub:
                parsed_data = parse_mqtt_payload(payload_hex)
                if parsed_data:
                    _LOGGER.debug(f"Parsed data from {topic}: {parsed_data}")
                    parsed_data["mqtt_connected"] = True
                    # Gán KEY_LAST_RAW_MQTT trong khối try để tránh lỗi nếu import const lỗi
                    try: parsed_data[KEY_LAST_RAW_MQTT] = payload_hex
                    except NameError: pass # Bỏ qua nếu KEY_LAST_RAW_MQTT không tồn tại
                    self.hass.loop.call_soon_threadsafe(async_dispatcher_send, self.hass, self._signal_update, parsed_data)
            elif topic == self._topic_pub: _LOGGER.info(f"Received ACK/echo on PUBLISH topic '{topic}'. Payload(hex)='{payload_hex}'. Ignoring.")
            else: _LOGGER.warning(f"Received msg on unexpected topic: {topic}")
        except Exception as e: _LOGGER.exception(f"Error processing MQTT msg on topic {topic}")

    async def async_request_data(self):
        if not self.is_connected: _LOGGER.debug("MQTT not connected, skipping data request."); return
        start_address = 0; num_registers = 95; slave_id = 1; func_code = 3 # Dùng Func Code 3
        command_hex = generate_modbus_read_command(slave_id, func_code, start_address, num_registers)
        if command_hex: await self.publish(command_hex)
        else: _LOGGER.error("Failed to generate Modbus read command hex.")

    async def publish(self, command_hex: str):
        if not self.is_connected or not self._mqttc: _LOGGER.error(f"MQTT not connected, cannot publish."); return False
        _LOGGER.debug(f"Publishing to {self._topic_pub}: {command_hex}")
        try:
            payload_bytes = bytes.fromhex(command_hex)
            publish_task = partial(self._mqttc.publish, self._topic_pub, payload=payload_bytes, qos=0)
            msg_info = await self.hass.async_add_executor_job(publish_task)
            if msg_info is None: _LOGGER.error(f"MQTT publish executor failed."); return False
            elif msg_info.rc == paho.MQTT_ERR_SUCCESS: _LOGGER.debug(f"Publish successful (mid={msg_info.mid})"); return True
            else: _LOGGER.error(f"MQTT publish failed with RC: {msg_info.rc}"); return False
        except ValueError as e: _LOGGER.error(f"Invalid hex payload for publish: {e}"); return False
        except Exception as e: _LOGGER.error(f"Failed to publish MQTT message: {e}"); return False

    async def disconnect(self) -> None:
        _LOGGER.info(f"Disconnecting MQTT client request.")
        self._stopping = True; self._reconnect_attempts = MAX_RECONNECT_ATTEMPTS; self._connected_event.set()
        mqttc_to_disconnect = None
        async with self._connect_lock:
            if self._mqttc: mqttc_to_disconnect = self._mqttc; self._mqttc = None
            self._is_connected = False
        if mqttc_to_disconnect:
            try:
                _LOGGER.debug(f"Stopping MQTT loop")
                await self.hass.async_add_executor_job(mqttc_to_disconnect.loop_stop)
                _LOGGER.debug(f"Executing MQTT disconnect")
                await self.hass.async_add_executor_job(mqttc_to_disconnect.disconnect)
                _LOGGER.info(f"MQTT client disconnected.")
            except Exception as e: _LOGGER.warning(f"Error during MQTT disconnect: {e}")
        else: _LOGGER.debug(f"MQTT client was already None during disconnect.")