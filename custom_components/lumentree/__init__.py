# /config/custom_components/lumentree/__init__.py
# Final version - Fixed NameError: name 'callback' is not defined
# MODIFIED: Disabled battery cell MQTT request

import asyncio
import time
import datetime
import ssl
import logging
from contextlib import suppress
from functools import partial
from typing import Optional, Callable # Added Callable for type hint

from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform, EVENT_HOMEASSISTANT_STOP
# <<< THÊM IMPORT callback >>>
from homeassistant.core import HomeAssistant, Event, callback
from homeassistant.exceptions import ConfigEntryNotReady, ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.device_registry import DeviceEntry

try:
    # Import các const đã cập nhật
    from .const import (
        DOMAIN, _LOGGER, CONF_DEVICE_SN, CONF_DEVICE_ID,
        MQTT_BROKER, DEFAULT_POLLING_INTERVAL, CONF_HTTP_TOKEN, DEFAULT_STATS_INTERVAL
    )
    from .mqtt import LumentreeMqttClient
    from .api import LumentreeHttpApiClient, AuthException, ApiException
    from .coordinator_stats import LumentreeStatsCoordinator
except ImportError as import_err:
    # --- Fallback Definitions (Formatted Correctly AGAIN) ---
    _LOGGER = logging.getLogger(__name__)
    _LOGGER.error(f"ImportError during component setup: {import_err}. Using fallback definitions.")
    DOMAIN = "lumentree"; CONF_DEVICE_SN = "device_sn"; CONF_DEVICE_ID = "device_id";
    MQTT_BROKER = "lesvr.suntcn.com"; DEFAULT_POLLING_INTERVAL = 5; CONF_HTTP_TOKEN = "http_token"; DEFAULT_STATS_INTERVAL = 600

    # Fallback Class MQTT
    class LumentreeMqttClient:
        def __init__(self, hass, entry, device_sn, device_id): pass
        async def connect(self): _LOGGER.warning("Using fallback MQTT connect"); await asyncio.sleep(0)
        async def disconnect(self): _LOGGER.warning("Using fallback MQTT disconnect"); await asyncio.sleep(0)
        async def async_request_data(self): _LOGGER.warning("Using fallback MQTT request_data"); await asyncio.sleep(0)
        # async def async_request_battery_cells(self): _LOGGER.warning("Using fallback MQTT request_cells"); await asyncio.sleep(0) # Keep commented if needed
        @property
        def is_connected(self) -> bool: return False

    # Fallback Class API
    class LumentreeHttpApiClient:
        def __init__(self, session): pass
        def set_token(self, token): pass
        async def authenticate_device(self, dev_id): _LOGGER.warning("Using fallback API authenticate"); return "fallback_token"
        async def get_device_info(self, dev_id): _LOGGER.warning("Using fallback API get_info"); return {"deviceId": dev_id, "deviceType": "Fallback Model"}
        async def get_daily_stats(self, sn, date): _LOGGER.warning("Using fallback API get_stats"); return {}

    # Fallback Class Coordinator
    class LumentreeStatsCoordinator:
        def __init__(self, hass, client, sn): pass
        async def async_config_entry_first_refresh(self): _LOGGER.warning("Using fallback Coordinator refresh"); await asyncio.sleep(0)
        async def async_refresh(self): _LOGGER.warning("Using fallback Coordinator refresh"); await asyncio.sleep(0)
        @property
        def data(self): return {}
        last_update_success = False

    # Fallback Exceptions (Tách class ra dòng riêng)
    class AuthException(Exception):
        pass
    class ApiException(Exception):
        pass
    # Lấy chúng từ global scope nếu đã được import ở trên, nếu không thì định nghĩa class fallback
    if "UpdateFailed" not in globals():
         class UpdateFailed(Exception):
             pass
    if "ConfigEntryAuthFailed" not in globals():
         class ConfigEntryAuthFailed(Exception):
             pass
    if "ConfigEntryNotReady" not in globals():
         class ConfigEntryNotReady(Exception):
             pass
    # --- Hết phần Fallback ---


PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    _LOGGER.info(f"Setting up Lumentree: {entry.title} ({entry.entry_id})")
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {}
    api_client: Optional[LumentreeHttpApiClient] = None
    mqtt_client: Optional[LumentreeMqttClient] = None
    remove_interval: Optional[Callable] = None

    try:
        device_sn = entry.data[CONF_DEVICE_SN]
        device_id = entry.data.get(CONF_DEVICE_ID, device_sn)
        http_token = entry.data.get(CONF_HTTP_TOKEN)
        if not http_token: _LOGGER.warning(f"HTTP Token missing for {device_sn}.")
        if device_id != entry.data.get(CONF_DEVICE_ID): _LOGGER.warning(f"Using SN {device_sn} as Device ID.")

        session = async_get_clientsession(hass)
        api_client = LumentreeHttpApiClient(session)
        api_client.set_token(http_token)
        hass.data[DOMAIN][entry.entry_id]["api_client"] = api_client

        _LOGGER.info(f"Fetching device info via HTTP for {device_id}...")
        try:
            device_api_info = await api_client.get_device_info(device_id)
            if "_error" in device_api_info:
                 _LOGGER.warning(f"Could not fetch device info setup: {device_api_info['_error']}. Using fallback.")
                 hass.data[DOMAIN][entry.entry_id]['device_api_info'] = {"deviceId": device_sn, "alias": entry.title}
            else:
                 hass.data[DOMAIN][entry.entry_id]['device_api_info'] = device_api_info
                 _LOGGER.info(f"Stored API info: Model={device_api_info.get('deviceType')}, ID={device_api_info.get('deviceId')}")
        except (ApiException, AuthException) as api_err:
             _LOGGER.error(f"Failed initial device info fetch {device_id}: {api_err}.")
             raise ConfigEntryNotReady(f"Failed device info: {api_err}") from api_err

        mqtt_client = LumentreeMqttClient(hass, entry, device_sn, device_id)
        hass.data[DOMAIN][entry.entry_id]["mqtt_client"] = mqtt_client
        await mqtt_client.connect()

        coordinator_stats = LumentreeStatsCoordinator(hass, api_client, device_sn)
        hass.data[DOMAIN][entry.entry_id]["coordinator_stats"] = coordinator_stats
        try:
             await coordinator_stats.async_config_entry_first_refresh()
             _LOGGER.debug(f"Initial stats fetch {device_sn}: Success={coordinator_stats.last_update_success}")
             if not coordinator_stats.last_update_success: _LOGGER.warning(f"Initial stats fetch failed {device_sn}.")
        except ConfigEntryAuthFailed: _LOGGER.error(f"HTTP Auth failed for stats {device_sn}."); pass
        except UpdateFailed: _LOGGER.warning(f"Initial stats fetch failed {device_sn}.")
        except Exception: _LOGGER.exception(f"Unexpected initial stats error {device_sn}")

        polling_interval = datetime.timedelta(seconds=DEFAULT_POLLING_INTERVAL)

        async def _async_poll_data(now=None):
            _LOGGER.debug(f"MQTT Poll {device_sn}.")
            domain_data = hass.data.get(DOMAIN)
            if not domain_data: _LOGGER.warning("Lumentree domain data gone. Stop poll."); return
            entry_data = domain_data.get(entry.entry_id)
            if not entry_data:
                _LOGGER.warning(f"Entry data missing {entry.entry_id}. Stop poll.")
                nonlocal remove_interval
                current_timer = remove_interval
                if callable(current_timer):
                    try: current_timer(); _LOGGER.info(f"MQTT poll timer cancelled {device_sn}."); remove_interval=None
                    except Exception as timer_err: _LOGGER.error(f"Error cancel timer {device_sn}: {timer_err}")
                return

            active_mqtt_client = entry_data.get("mqtt_client")
            if not isinstance(active_mqtt_client, LumentreeMqttClient) or not active_mqtt_client.is_connected: _LOGGER.warning(f"MQTT {device_sn} not ready."); return
            try:
                _LOGGER.debug(f"Req MQTT (main data) {device_sn}...")
                await active_mqtt_client.async_request_data()
                # --- DISABLED BATTERY CELL REQUEST ---
                # await active_mqtt_client.async_request_battery_cells()
                # --- END DISABLED ---
                _LOGGER.debug(f"MQTT req sent {device_sn}.")
            except Exception as poll_err: _LOGGER.error(f"MQTT poll error {device_sn}: {poll_err}")

        remove_interval = async_track_time_interval(hass, _async_poll_data, polling_interval)
        _LOGGER.info(f"Started MQTT polling {polling_interval} for {device_sn}")

        # <<< THÊM @callback decorator >>>
        @callback
        def _cancel_timer_on_unload():
            """Cancel the polling timer when the entry is unloaded."""
            nonlocal remove_interval
            _LOGGER.debug(f"Unload: Cancelling MQTT timer for {device_sn}.")
            current_timer = remove_interval
            if callable(current_timer):
                try:
                    current_timer()
                    _LOGGER.info(f"MQTT polling timer cancelled for {device_sn} during unload.")
                    remove_interval = None # Đảm bảo không gọi lại
                except Exception as timer_err:
                    _LOGGER.error(f"Error cancelling timer during unload {device_sn}: {timer_err}")

        async def _async_stop_mqtt(event: Event) -> None:
            _LOGGER.info("HA stop.");
            client_to_stop = hass.data.get(DOMAIN, {}).get(entry.entry_id, {}).get("mqtt_client")
            if isinstance(client_to_stop, LumentreeMqttClient):
                _LOGGER.info(f"Disconnecting MQTT {device_sn}.")
                await client_to_stop.disconnect()

        entry.async_on_unload(_cancel_timer_on_unload)
        entry.async_on_unload(hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_stop_mqtt))

        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        _LOGGER.info(f"Setup complete for {entry.title} (SN/ID: {device_sn})")
        return True

    except ConfigEntryNotReady as e:
        _LOGGER.warning(f"Setup failed {entry.title}: {e}. Cleanup...")
        if isinstance(mqtt_client, LumentreeMqttClient): await mqtt_client.disconnect()
        if entry.entry_id in hass.data.get(DOMAIN, {}):
             hass.data[DOMAIN].pop(entry.entry_id, None)
        raise
    except Exception as final_exception:
        _LOGGER.exception(f"Unexpected setup error {entry.title}")
        if isinstance(mqtt_client, LumentreeMqttClient): await mqtt_client.disconnect()
        if entry.entry_id in hass.data.get(DOMAIN, {}):
            hass.data[DOMAIN].pop(entry.entry_id, None)
        return False # Indicate setup failure

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    _LOGGER.info(f"Unloading Lumentree: {entry.title} (SN/ID: {entry.data.get(CONF_DEVICE_SN)})")
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    entry_data = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    if entry_data:
        mqtt_client = entry_data.get("mqtt_client")
        if isinstance(mqtt_client, LumentreeMqttClient):
             _LOGGER.debug(f"Disconnecting MQTT {entry.data.get(CONF_DEVICE_SN)}.");
             # Ensure disconnect task runs even during unload
             hass.async_create_task(mqtt_client.disconnect())
        _LOGGER.debug(f"Removed entry data {entry.entry_id}.")
    else: _LOGGER.warning(f"No entry data {entry.entry_id} to clean.")
    _LOGGER.info(f"Unload {entry.title}: {'OK' if unload_ok else 'Failed'}.")
    return unload_ok
