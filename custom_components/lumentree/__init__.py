# /config/custom_components/lumentree/__init__.py
# Fixed SyntaxError in fallback definitions (again)

import asyncio
import time
import datetime
import ssl
import logging
from contextlib import suppress
from functools import partial

from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform, EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant, Event
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
    # --- Fallback Definitions (Sửa lỗi cú pháp) ---
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
        async def async_request_battery_cells(self): _LOGGER.warning("Using fallback MQTT request_cells"); await asyncio.sleep(0)
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
    try:
        from homeassistant.helpers.update_coordinator import UpdateFailed
    except ImportError:
        class UpdateFailed(Exception): # <<< Tách class ra dòng riêng
            pass
    try:
        from homeassistant.exceptions import ConfigEntryAuthFailed
    except ImportError:
        class ConfigEntryAuthFailed(Exception): # <<< Tách class ra dòng riêng
            pass
    # --- Hết phần Fallback ---


PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    _LOGGER.info(f"Setting up Lumentree: {entry.title} ({entry.entry_id})")
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {}
    api_client: Optional[LumentreeHttpApiClient] = None

    try:
        device_sn = entry.data[CONF_DEVICE_SN] # This is the deviceId used as HA unique ID
        device_id = entry.data.get(CONF_DEVICE_ID, device_sn) # Original user input or fallback
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

        mqtt_client = LumentreeMqttClient(hass, entry, device_sn, device_id) # Pass HA SN (deviceId) and original ID
        hass.data[DOMAIN][entry.entry_id]["mqtt_client"] = mqtt_client
        await mqtt_client.connect()

        coordinator_stats = LumentreeStatsCoordinator(hass, api_client, device_sn) # Use HA SN (deviceId) for coordinator ID and API calls
        hass.data[DOMAIN][entry.entry_id]["coordinator_stats"] = coordinator_stats
        try:
             await coordinator_stats.async_config_entry_first_refresh()
             _LOGGER.debug(f"Initial stats fetch {device_sn}: Success={coordinator_stats.last_update_success}")
             if not coordinator_stats.last_update_success: _LOGGER.warning(f"Initial stats fetch failed {device_sn}.")
        except ConfigEntryAuthFailed: _LOGGER.error(f"HTTP Auth failed for stats {device_sn}."); pass
        except UpdateFailed: _LOGGER.warning(f"Initial stats fetch failed {device_sn}.")
        except Exception: _LOGGER.exception(f"Unexpected initial stats error {device_sn}")

        polling_interval = datetime.timedelta(seconds=DEFAULT_POLLING_INTERVAL)
        remove_interval: Optional[Callable] = None
        async def _async_poll_data(now=None):
            _LOGGER.debug(f"MQTT Poll {device_sn}."); entry_data = hass.data.get(DOMAIN, {}).get(entry.entry_id)
            if not entry_data: _LOGGER.warning(f"Data missing {entry.entry_id}. Stop poll."); timer = hass.data.get(DOMAIN, {}).get(entry.entry_id, {}).pop("remove_interval", None); timer(); return # type: ignore
            active_mqtt_client = entry_data.get("mqtt_client")
            if not isinstance(active_mqtt_client, LumentreeMqttClient) or not active_mqtt_client.is_connected: _LOGGER.warning(f"MQTT {device_sn} not ready."); return
            try: _LOGGER.debug(f"Req MQTT {device_sn}..."); await active_mqtt_client.async_request_data(); await active_mqtt_client.async_request_battery_cells(); _LOGGER.debug(f"MQTT req sent {device_sn}.")
            except Exception as poll_err: _LOGGER.error(f"MQTT poll error {device_sn}: {poll_err}")

        remove_interval = async_track_time_interval(hass, _async_poll_data, polling_interval)
        hass.data[DOMAIN][entry.entry_id]["remove_interval"] = remove_interval
        _LOGGER.info(f"Started MQTT polling {polling_interval} for {device_sn}")

        async def _cancel_timer_on_unload(): _LOGGER.debug(f"Unload: Cancelling MQTT timer {device_sn}."); timer = hass.data.get(DOMAIN, {}).get(entry.entry_id, {}).pop("remove_interval", None); timer() # type: ignore
        async def _async_stop_mqtt(event: Event) -> None: _LOGGER.info("HA stop."); mqtt_client = hass.data.get(DOMAIN, {}).get(entry.entry_id, {}).get("mqtt_client"); await mqtt_client.disconnect() # type: ignore

        entry.async_on_unload(_cancel_timer_on_unload)
        entry.async_on_unload(hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_stop_mqtt))

        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        _LOGGER.info(f"Setup complete for {entry.title} (SN/ID: {device_sn})")
        return True

    except ConfigEntryNotReady as e:
        _LOGGER.warning(f"Setup failed for {entry.title}: {e}. Cleaning up...")
        mqtt_client = hass.data.get(DOMAIN, {}).get(entry.entry_id, {}).get("mqtt_client")
        if isinstance(mqtt_client, LumentreeMqttClient): await mqtt_client.disconnect()
        hass.data[DOMAIN].pop(entry.entry_id, None)
        raise
    except Exception as final_exception:
        _LOGGER.exception(f"Unexpected setup error {entry.title}")
        mqtt_client = hass.data.get(DOMAIN, {}).get(entry.entry_id, {}).get("mqtt_client")
        if isinstance(mqtt_client, LumentreeMqttClient): await mqtt_client.disconnect()
        hass.data[DOMAIN].pop(entry.entry_id, None)
        return False

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    _LOGGER.info(f"Unloading Lumentree: {entry.title} (SN/ID: {entry.data.get(CONF_DEVICE_SN)})")
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    entry_data = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    if entry_data:
        mqtt_client = entry_data.get("mqtt_client")
        if isinstance(mqtt_client, LumentreeMqttClient): _LOGGER.debug(f"Disconnecting MQTT {entry.data.get(CONF_DEVICE_SN)}."); hass.async_create_task(mqtt_client.disconnect())
        _LOGGER.debug(f"Removed entry data {entry.entry_id}.")
    else: _LOGGER.warning(f"No entry data {entry.entry_id} to clean.")
    _LOGGER.info(f"Unload {entry.title}: {'OK' if unload_ok else 'Failed'}.")
    return unload_ok