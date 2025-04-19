# /config/custom_components/lumentree/mqtt.py
# Final stable version - Reads 95 regs, manages online status, STRICT FORMATTING

import asyncio
import json
import ssl
import time
import logging
from typing import Any, Dict, Optional, Callable
from functools import partial

import paho.mqtt.client as paho
from paho.mqtt.client import MQTTMessage

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_call_later

try:
    from .const import (
        DOMAIN, _LOGGER, MQTT_BROKER, MQTT_PORT, MQTT_USERNAME, MQTT_PASSWORD,
        MQTT_SUB_TOPIC_FORMAT, MQTT_PUB_TOPIC_FORMAT,
        SIGNAL_UPDATE_FORMAT, # Removed INITIAL signal
        CONF_DEVICE_SN, CONF_DEVICE_ID,
        MQTT_CLIENT_ID_FORMAT, MQTT_KEEPALIVE, KEY_ONLINE_STATUS,
        KEY_LAST_RAW_MQTT, DEFAULT_POLLING_INTERVAL,
        REG_ADDR_CELL_START, REG_ADDR_CELL_COUNT
    )
    from .parser import parse_mqtt_payload, generate_modbus_read_command
except ImportError:
    _LOGGER = logging.getLogger(__name__); _LOGGER.warning("ImportError mqtt.py")
    DOMAIN = "lumentree"; MQTT_BROKER = "lesvr.suntcn.com"; MQTT_PORT = 1886; MQTT_USERNAME = "appuser"; MQTT_PASSWORD = "app666"; MQTT_KEEPALIVE = 20; MQTT_SUB_TOPIC_FORMAT = "reportApp/{device_sn}"; MQTT_PUB_TOPIC_FORMAT = "listenApp/{device_sn}"; SIGNAL_UPDATE_FORMAT = f"{DOMAIN}_mqtt_update_{{device_sn}}"; CONF_DEVICE_SN = "device_sn"; CONF_DEVICE_ID = "device_id"; MQTT_CLIENT_ID_FORMAT = "android-{device_id}-{timestamp}"; KEY_ONLINE_STATUS="online_status"; KEY_LAST_RAW_MQTT = "last_raw_mqtt_hex"; DEFAULT_POLLING_INTERVAL=5; REG_ADDR_CELL_START=250; REG_ADDR_CELL_COUNT=50;
    def parse_mqtt_payload(ph:str)->Optional[Dict[str,Any]]: return None
    def generate_modbus_read_command(sid:int,fc:int,addr:int,num:int)->Optional[str]: return None
    def async_call_later(hass, delay, target): pass

RECONNECT_DELAY_SECONDS = 5
MAX_RECONNECT_ATTEMPTS = 10
CONNECT_TIMEOUT = 20
OFFLINE_TIMEOUT_SECONDS = DEFAULT_POLLING_INTERVAL * 2.5
NUM_MAIN_REGISTERS_TO_READ = 95 # Read registers 0-94

class LumentreeMqttClient:
    """Manages MQTT connection, messages, and online status."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, device_sn: str, device_id: str):
        """Initialize the MQTT client."""
        self.hass = hass
        self.entry = entry
        self._device_sn = device_sn
        self._device_id = device_id
        self._mqttc: Optional[paho.Client] = None
        timestamp = int(time.time())
        try:
            self._client_id = MQTT_CLIENT_ID_FORMAT.format(device_id=self._device_id, timestamp=timestamp)
        except KeyError:
            _LOGGER.error("Failed format MQTT Client ID.")
            self._client_id = f"ha-lumentree-{self._device_sn}-{timestamp}"
        _LOGGER.debug(f"MQTT Client ID: {self._client_id}")
        self._signal_update = SIGNAL_UPDATE_FORMAT.format(device_sn=self._device_sn)
        self._topic_sub = MQTT_SUB_TOPIC_FORMAT.format(device_sn=self._device_sn)
        self._topic_pub = MQTT_PUB_TOPIC_FORMAT.format(device_sn=self._device_sn)
        self._connect_lock = asyncio.Lock()
        self._reconnect_attempts = 0
        self._is_connected = False
        self._stopping = False
        self._connected_event = asyncio.Event()
        self._online: bool = False
        self._offline_timer_unsub: Optional[Callable] = None

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    def _cancel_offline_timer(self):
        """Cancel the offline timer if it's active."""
        if self._offline_timer_unsub:
            _LOGGER.debug(f"Cancelling offline timer {self._client_id}")
            try:
                self._offline_timer_unsub()
            except Exception as e:
                 _LOGGER.warning(f"Error cancelling timer {self._client_id}: {e}")
            self._offline_timer_unsub = None

    @callback
    def _set_offline(self, *args):
        """Set status to offline and dispatch update."""
        _LOGGER.info(f"MQTT data timeout or disconnect {self._client_id}. Offline.")
        self._cancel_offline_timer()
        if self._online:
            self._online = False
            async_dispatcher_send(self.hass, self._signal_update, {KEY_ONLINE_STATUS: False})

    def _start_offline_timer(self):
        """Start or restart the offline timer."""
        self._cancel_offline_timer()
        _LOGGER.debug(f"Start offline timer ({OFFLINE_TIMEOUT_SECONDS}s) {self._client_id}")
        self._offline_timer_unsub = async_call_later(
            self.hass, OFFLINE_TIMEOUT_SECONDS, self._set_offline
        )

    async def connect(self) -> None:
        """Establish MQTT connection."""
        async with self._connect_lock:
            if self._is_connected:
                _LOGGER.debug(f"MQTT connected {self._device_sn}.")
                return
            self._stopping = False
            self._connected_event.clear()
            self._mqttc = paho.Client(client_id=self._client_id, protocol=paho.MQTTv311, callback_api_version=paho.CallbackAPIVersion.VERSION1)
            self._mqttc.username_pw_set(username=MQTT_USERNAME, password=MQTT_PASSWORD)
            self._mqttc.on_connect=self._on_connect
            self._mqttc.on_disconnect=self._on_disconnect
            self._mqttc.on_message=self._on_message
            _LOGGER.info(f"MQTT connect: {MQTT_BROKER}:{MQTT_PORT} (Client: {self._client_id}) for SN: {self._device_sn}")
            try:
                await self.hass.async_add_executor_job(self._mqttc.connect, MQTT_BROKER, MQTT_PORT, MQTT_KEEPALIVE)
                self._mqttc.loop_start()
                _LOGGER.info(f"MQTT loop started {self._client_id}. Wait CONNACK {CONNECT_TIMEOUT}s.")
                try:
                    await asyncio.wait_for(self._connected_event.wait(), timeout=CONNECT_TIMEOUT)
                    if not self._is_connected:
                        raise ConnectionRefusedError("MQTT refused.")
                    _LOGGER.info(f"MQTT connected {self._client_id}.")
                except asyncio.TimeoutError:
                    _LOGGER.error(f"MQTT timeout {self._client_id}.")
                    await self.disconnect()
                    raise ConnectionRefusedError("MQTT timeout.")
            except Exception as e:
                _LOGGER.error(f"Failed MQTT connect {self._client_id}: {e}")
                if self._mqttc:
                    try:
                        self._mqttc.loop_stop()
                        _LOGGER.debug(f"MQTT loop stopped after failure {self._client_id}.")
                    except Exception as se:
                        _LOGGER.warning(f"Loop stop err: {se}")
                self._mqttc = None
                self._is_connected = False
                self._connected_event.set()
                if isinstance(e, ConnectionRefusedError):
                    raise
                raise ConnectionRefusedError(f"MQTT setup error: {e}") from e

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        """Callback when connection is established."""
        if rc == paho.CONNACK_ACCEPTED:
            _LOGGER.info(f"MQTT connected (rc={rc}) {self._client_id}. Sub: {self._topic_sub}")
            self._reconnect_attempts = 0
            self._is_connected = True
            try:
                result, mid = client.subscribe(self._topic_sub, 0)
                _LOGGER.debug(f"Sub {'OK' if result==0 else 'Fail'} {self._topic_sub} (mid={mid})")
            except Exception as e:
                _LOGGER.error(f"MQTT sub fail: {e}")
            finally:
                self.hass.loop.call_soon_threadsafe(self._connected_event.set)
        else:
            err_map={1:"Proto",2:"ID Rej",3:"Srv Unavail",4:"Bad User/Pass",5:"No Auth"}
            err=err_map.get(rc,'Unk')
            _LOGGER.error(f"MQTT refused {self._client_id} (rc={rc}): {err}.")
            self._is_connected = False
            self.hass.loop.call_soon_threadsafe(self._connected_event.set)
            self.hass.loop.call_soon_threadsafe(self._set_offline)
            if not self._stopping:
                self._schedule_reconnect()

    def _on_disconnect(self, client, userdata, rc, properties=None):
        """Callback when disconnected."""
        was_online = self._online
        self._is_connected = False
        self._cancel_offline_timer()
        self._set_offline()
        if rc == 0:
            _LOGGER.info(f"MQTT disconnect OK {self._client_id}.")
        else:
            _LOGGER.warning(f"MQTT unexpected disconnect {self._client_id} (rc={rc}).")
        if not self._stopping:
            self._schedule_reconnect()

    def _schedule_reconnect(self):
        """Schedules an asynchronous reconnection attempt with exponential backoff."""
        if self._reconnect_attempts < MAX_RECONNECT_ATTEMPTS:
            self._reconnect_attempts += 1
            delay = min(RECONNECT_DELAY_SECONDS * (2 ** (self._reconnect_attempts - 1)), 60)
            _LOGGER.info(f"Schedule MQTT reconn {self._reconnect_attempts}/{MAX_RECONNECT_ATTEMPTS} {self._client_id} in {delay}s.")
            self.hass.async_create_task(self._async_reconnect(delay))
        else:
            _LOGGER.error(f"MQTT reconn failed {self._client_id}.")
            self.hass.loop.call_soon_threadsafe(async_dispatcher_send, self.hass, self._signal_update, {"error": "MQTT_reconnect_failed"})

    async def _async_reconnect(self, delay: float):
        """Waits for the delay and attempts reconnection."""
        await asyncio.sleep(delay)
        if not self.is_connected and not self._stopping and self._mqttc:
             _LOGGER.debug(f"Try MQTT reconn job {self._client_id}...")
             try:
                 await self.hass.async_add_executor_job(self._mqttc.reconnect)
             except Exception as e:
                 _LOGGER.warning(f"MQTT reconn job fail {self._client_id}: {e}")

    def _on_message(self, client, userdata, msg: MQTTMessage):
        """Callback when a message is received."""
        topic = msg.topic
        try:
            payload_bytes = msg.payload
            payload_hex = ''.join(f'{b:02x}' for b in payload_bytes) if payload_bytes else ""
            _LOGGER.debug(f"MQTT msg recv {self._client_id}: T='{topic}', P='{payload_hex[:60]}...' (Len: {len(payload_bytes)})")

            if topic == self._topic_sub:
                parsed_data = parse_mqtt_payload(payload_hex)
                if parsed_data:
                    _LOGGER.debug(f"Parsed data {topic} ({self._client_id}): {parsed_data}")

                    # Update online status and reset timer
                    send_online_true = False
                    if not self._online:
                        self._online = True
                        parsed_data[KEY_ONLINE_STATUS] = True # Send True on first successful parse
                        send_online_true = True
                    self._start_offline_timer()

                    # Add raw hex data if needed
                    try:
                        parsed_data[KEY_LAST_RAW_MQTT] = payload_hex
                    except NameError:
                        pass

                    # Dispatch the parsed data (only regular updates now)
                    self.hass.loop.call_soon_threadsafe(async_dispatcher_send, self.hass, self._signal_update, parsed_data)

            else:
                _LOGGER.warning(f"Unexpected topic {self._client_id}: {topic}")
        except Exception as e:
            _LOGGER.exception(f"Error proc MQTT msg {topic} {self._client_id}")

    async def _publish_command(self, command_hex: str) -> bool:
        """Internal helper to publish a hex command."""
        if not self.is_connected or not self._mqttc:
            _LOGGER.error(f"MQTT not conn {self._client_id}, cannot pub.")
            return False
        _LOGGER.debug(f"Pub to {self._topic_pub} ({self._client_id}): {command_hex}")
        try:
            payload_bytes = bytes.fromhex(command_hex)
            publish_task = partial(self._mqttc.publish, self._topic_pub, payload=payload_bytes, qos=0)
            msg_info = await self.hass.async_add_executor_job(publish_task)

            if msg_info is None or msg_info.rc != paho.MQTT_ERR_SUCCESS:
                 _LOGGER.error(f"MQTT pub fail {self._client_id} RC: {msg_info.rc if msg_info else 'Executor Error'}")
                 return False
            else:
                 _LOGGER.debug(f"Pub OK (mid={msg_info.mid}) {self._client_id}")
                 return True
        except ValueError as e:
            _LOGGER.error(f"Invalid hex payload {self._client_id}: {e}")
            return False
        except Exception as e:
            _LOGGER.error(f"Failed MQTT pub {self._client_id}: {e}")
            return False

    async def async_request_data(self):
        """Requests the main device data (registers 0-94)."""
        start_address = 0
        num_registers = NUM_MAIN_REGISTERS_TO_READ # Should be 95
        slave_id = 1
        func_code = 3
        command_hex = generate_modbus_read_command(slave_id, func_code, start_address, num_registers)
        if command_hex:
            await self._publish_command(command_hex)
        else:
            _LOGGER.error(f"Failed gen Modbus read (0-{num_registers-1}) {self._client_id}.")

    # <<< REMOVED async_request_extended_data >>>

    async def async_request_battery_cells(self):
        """Requests the battery cell data."""
        start, count, sid, fc = REG_ADDR_CELL_START, REG_ADDR_CELL_COUNT, 1, 3
        command_hex = generate_modbus_read_command(sid, fc, start, count)
        if command_hex:
            await self._publish_command(command_hex)
        else:
            _LOGGER.error(f"Failed gen Modbus read ({start}-{start+count-1}) {self._client_id}.")

    async def disconnect(self) -> None:
        """Disconnects the MQTT client and cleans up timers."""
        _LOGGER.info(f"Disconnect MQTT req {self._client_id}.")
        self._stopping = True
        self._reconnect_attempts = MAX_RECONNECT_ATTEMPTS
        self._connected_event.set()
        self._cancel_offline_timer()
        self._set_offline()

        mqttc_to_disconnect = None
        async with self._connect_lock:
            if self._mqttc:
                mqttc_to_disconnect = self._mqttc
                self._mqttc = None
            self._is_connected = False

        if mqttc_to_disconnect:
            try:
                _LOGGER.debug(f"Stop MQTT loop {self._client_id}")
                await self.hass.async_add_executor_job(mqttc_to_disconnect.loop_stop)
                _LOGGER.debug(f"Exec MQTT disconnect {self._client_id}")
                await self.hass.async_add_executor_job(mqttc_to_disconnect.disconnect)
                _LOGGER.info(f"MQTT client disconnected {self._client_id}.")
            except Exception as e:
                _LOGGER.warning(f"Error MQTT disconnect {self._client_id}: {e}")
        else:
            _LOGGER.debug(f"MQTT client already None {self._client_id}.")