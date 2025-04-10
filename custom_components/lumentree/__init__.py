# /config/custom_components/lumentree/__init__.py
# Fixed UpdateFailed import

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
from homeassistant.exceptions import ConfigEntryNotReady, ConfigEntryAuthFailed # Bỏ UpdateFailed ở đây
from homeassistant.helpers.update_coordinator import UpdateFailed # <<< THÊM IMPORT TỪ ĐÂY
from homeassistant.helpers.typing import ConfigType

try:
    # Import đầy đủ các thành phần cần thiết
    from .const import (
        DOMAIN, _LOGGER, CONF_DEVICE_SN, CONF_USER_ID, MQTT_BROKER,
        DEFAULT_POLLING_INTERVAL,
        CONF_HTTP_TOKEN
    )
    from .mqtt import LumentreeMqttClient
    from .api import LumentreeHttpApiClient, AuthException, ApiException
    from .coordinator_stats import LumentreeStatsCoordinator
except ImportError as import_err:
    # Fallback
    _LOGGER = logging.getLogger(__name__)
    _LOGGER.error(f"ImportError during component setup: {import_err}. Using fallback definitions.")
    DOMAIN = "lumentree"; CONF_DEVICE_SN = "device_sn"; CONF_USER_ID = "user_id"; MQTT_BROKER = "lesvr.suntcn.com"
    DEFAULT_POLLING_INTERVAL = 15; CONF_HTTP_TOKEN = "http_token"
    class LumentreeMqttClient:
        async def connect(self): pass
        async def disconnect(self): pass
        async def async_request_data(self): pass
        @property
        def is_connected(self): return False
    class LumentreeHttpApiClient:
         def __init__(self, session): pass
         def set_token(self, token): pass
         async def authenticate_guest(self, qr): return None, None, None
         async def get_device_info(self, dev_id): return {}
         async def get_daily_stats(self, sn, date): return {}
    class LumentreeStatsCoordinator:
         def __init__(self, hass, client, sn): pass
         async def async_config_entry_first_refresh(self): pass
         async def async_refresh(self): pass
         @property
         def data(self): return {}
         last_update_success = False
    # Fallback cho exceptions
    class AuthException(Exception): pass
    class ApiException(Exception): pass
    try: # Thử import lại UpdateFailed từ đúng chỗ
        from homeassistant.helpers.update_coordinator import UpdateFailed
    except ImportError:
        class UpdateFailed(Exception): pass # Fallback cuối cùng
    try: # Thử import ConfigEntryAuthFailed
        from homeassistant.exceptions import ConfigEntryAuthFailed
    except ImportError:
        class ConfigEntryAuthFailed(Exception): pass # Fallback cuối cùng

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]

# --- async_setup_entry và async_unload_entry giữ nguyên như phiên bản trước ---
# Đảm bảo phần try...except trong async_setup_entry bắt đúng UpdateFailed
async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Lumentree from a config entry."""
    _LOGGER.info(f"Setting up Lumentree integration for: {entry.title}")
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {}

    try:
        device_sn = entry.data[CONF_DEVICE_SN]
        user_id = entry.data[CONF_USER_ID]
        http_token = entry.data.get(CONF_HTTP_TOKEN)
        if not http_token: _LOGGER.warning("HTTP Token not found. Stats fetching might fail.")
    except KeyError as err:
        _LOGGER.error(f"Missing required config entry data: {err}")
        hass.data[DOMAIN].pop(entry.entry_id, None)
        return False

    session = async_get_clientsession(hass)
    api_client = LumentreeHttpApiClient(session)
    api_client.set_token(http_token)
    hass.data[DOMAIN][entry.entry_id]["api_client"] = api_client

    client_id = f"android-{user_id}-{int(time.time())}"
    mqtt_client = LumentreeMqttClient(hass, entry, client_id, device_sn)
    hass.data[DOMAIN][entry.entry_id]["mqtt_client"] = mqtt_client

    try:
        await mqtt_client.connect()
    except (ConnectionRefusedError, asyncio.TimeoutError, ApiException) as conn_err:
        _LOGGER.error(f"Failed initial MQTT connection: {conn_err}")
        hass.data[DOMAIN].pop(entry.entry_id, None)
        raise ConfigEntryNotReady(f"MQTT connection failed: {conn_err}") from conn_err
    except Exception as e:
        _LOGGER.exception("Unexpected error during MQTT connection setup")
        hass.data[DOMAIN].pop(entry.entry_id, None)
        raise ConfigEntryNotReady(f"Unexpected MQTT setup error: {e}") from e

    coordinator_stats = LumentreeStatsCoordinator(hass, api_client, device_sn)
    try:
        _LOGGER.debug("Performing initial fetch for daily stats coordinator...")
        await coordinator_stats.async_config_entry_first_refresh()
        _LOGGER.debug(f"Initial stats fetch completed. Success: {coordinator_stats.last_update_success}")
        if not coordinator_stats.last_update_success:
             _LOGGER.warning("Initial daily stats fetch failed. Check logs. Will retry later.")
    except ConfigEntryAuthFailed as auth_fail:
         _LOGGER.error(f"Auth failed during initial stats fetch: {auth_fail}. Check config.")
         pass
    except UpdateFailed as update_fail: # <<< Bắt đúng exception này
         _LOGGER.warning(f"Initial daily stats fetch failed: {update_fail}. Will retry later.")
    except Exception as e:
         _LOGGER.exception("Unexpected error during initial stats coordinator refresh")
    hass.data[DOMAIN][entry.entry_id]["coordinator_stats"] = coordinator_stats

    polling_interval = datetime.timedelta(seconds=DEFAULT_POLLING_INTERVAL)
    remove_interval: Optional[Callable] = None

    async def _async_poll_data(now=None):
        """Callback function to poll MQTT data."""
        _LOGGER.debug("MQTT Polling timer triggered.")
        entry_data = hass.data.get(DOMAIN, {}).get(entry.entry_id)
        if not entry_data:
             _LOGGER.warning("Entry data not found during MQTT poll. Stopping poll.")
             if remove_interval: remove_interval()
             return

        active_mqtt_client = entry_data.get("mqtt_client")
        if not isinstance(active_mqtt_client, LumentreeMqttClient) or not active_mqtt_client.is_connected:
             _LOGGER.warning("MQTT client not connected/ready, skipping MQTT data request.")
             return

        _LOGGER.debug("Requesting real-time data via MQTT...")
        try:
            await active_mqtt_client.async_request_data()
        except Exception as poll_err:
             _LOGGER.error(f"Error during MQTT data request polling: {poll_err}")

    await _async_poll_data()
    remove_interval = async_track_time_interval(hass, _async_poll_data, polling_interval)
    _LOGGER.info(f"Started MQTT polling every {polling_interval}")

    async def _unload_wrapper():
        """Clean up resources when entry is unloaded."""
        _LOGGER.debug(f"Unloading entry {entry.entry_id}...")
        if remove_interval: remove_interval(); _LOGGER.debug("MQTT polling timer cancelled.")
        entry_data_to_unload = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
        if entry_data_to_unload:
            client_to_unload = entry_data_to_unload.get("mqtt_client")
            if isinstance(client_to_unload, LumentreeMqttClient):
                _LOGGER.debug("Disconnecting MQTT client during unload.")
                await client_to_unload.disconnect()
            _LOGGER.debug(f"Removed entry data for {entry.entry_id}.")

    async def _async_stop_mqtt(event: Event) -> None:
        """Ensure MQTT disconnect when Home Assistant stops."""
        _LOGGER.info("Home Assistant stopping event received.")

    entry.async_on_unload(_unload_wrapper)
    entry.async_on_unload(hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_stop_mqtt))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _LOGGER.info(f"Successfully set up Lumentree integration for {entry.title}")
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info(f"Unloading Lumentree integration for: {entry.title}")
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok: _LOGGER.info(f"Successfully unloaded Lumentree integration for {entry.title}.")
    else: _LOGGER.warning(f"Failed to cleanly unload Lumentree platforms for {entry.title}.")
    return unload_ok