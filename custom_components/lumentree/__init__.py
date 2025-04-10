# /config/custom_components/lumentree/__init__.py
# Fixed UpdateFailed import, adapt to new config keys and coordinator init

import asyncio
import time
import datetime
import ssl
import logging
from contextlib import suppress
from functools import partial
from typing import Optional, Callable # <<< THÊM TYPING

from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform, EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant, Event
from homeassistant.exceptions import ConfigEntryNotReady, ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed
from homeassistant.helpers.typing import ConfigType

try:
    from .const import (
        DOMAIN, _LOGGER, CONF_DEVICE_SN, CONF_USER_ID, CONF_HTTP_TOKEN,
        CONF_DEVICE_ID, # <<< THÊM CONF_DEVICE_ID
        DEFAULT_POLLING_INTERVAL, MQTT_BROKER,
    )
    from .mqtt import LumentreeMqttClient
    from .api import LumentreeHttpApiClient, AuthException, ApiException
    from .coordinator_stats import LumentreeStatsCoordinator
except ImportError as import_err:
    # --- Fallback ---
    _LOGGER = logging.getLogger(__name__)
    _LOGGER.error(f"ImportError during component setup: {import_err}. Using fallback definitions.")
    DOMAIN = "lumentree"; CONF_DEVICE_SN = "device_sn"; CONF_USER_ID = "user_id"; MQTT_BROKER = "lesvr.suntcn.com"
    DEFAULT_POLLING_INTERVAL = 15; CONF_HTTP_TOKEN = "http_token"; CONF_DEVICE_ID = "device_id"
    class LumentreeMqttClient:
        async def connect(self): pass
        async def disconnect(self): pass
        async def async_request_data(self): pass
        @property
        def is_connected(self): return False
    class LumentreeHttpApiClient:
         def __init__(self, session): pass
         def set_token(self, token): pass
         # Sửa fallback để khớp API mới
         async def authenticate_device_id(self, device_id): return None, None
         async def get_device_info(self, dev_id): return {}
         async def get_daily_stats(self, dev_id, date): return {} # <<< SỬA FALLBACK STATS
    class LumentreeStatsCoordinator:
         # Sửa fallback init coordinator
         def __init__(self, hass, client, device_id): pass # <<< SỬA FALLBACK INIT
         async def async_config_entry_first_refresh(self): pass
         async def async_refresh(self): pass
         @property
         def data(self): return {}
         last_update_success = False
    # Fallback cho exceptions
    class AuthException(Exception): pass
    class ApiException(Exception): pass
    try: from homeassistant.helpers.update_coordinator import UpdateFailed
    except ImportError: class UpdateFailed(Exception): pass
    try: from homeassistant.exceptions import ConfigEntryAuthFailed
    except ImportError: class ConfigEntryAuthFailed(Exception): pass
    # --- Hết Fallback ---

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Lumentree from a config entry."""
    _LOGGER.info(f"Setting up Lumentree integration for: {entry.title}")
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {}

    try:
        # Đọc cả device_id và device_sn
        device_sn = entry.data[CONF_DEVICE_SN]
        device_id = entry.data[CONF_DEVICE_ID] # <<< ĐỌC DEVICE ID
        user_id = entry.data[CONF_USER_ID]
        http_token = entry.data.get(CONF_HTTP_TOKEN) # Token có thể không có nếu là entry cũ? (Nên có sau V1)
        if not http_token:
            _LOGGER.error("HTTP Token not found in config entry. Cannot proceed.")
            # Không thể hoạt động nếu không có token cho API HTTP
            return False # Hoặc raise ConfigEntryAuthFailed? Tạm thời False
        if not device_id:
             _LOGGER.error("Device ID not found in config entry. Cannot proceed.")
             return False
    except KeyError as err:
        _LOGGER.error(f"Missing required config entry data: {err}")
        # Không pop data ở đây vì entry vẫn tồn tại
        return False

    _LOGGER.info(f"Config data: SN={device_sn}, DeviceID={device_id}, UserID={user_id}, Token={'Present' if http_token else 'Missing'}")

    session = async_get_clientsession(hass)
    api_client = LumentreeHttpApiClient(session)
    api_client.set_token(http_token) # <<< GÁN TOKEN VÀO API CLIENT
    hass.data[DOMAIN][entry.entry_id]["api_client"] = api_client
    hass.data[DOMAIN][entry.entry_id]["device_id"] = device_id # Lưu lại device_id để coordinator dùng

    # MQTT vẫn dùng device_sn và user_id
    client_id = f"android-{user_id}-{int(time.time())}"
    mqtt_client = LumentreeMqttClient(hass, entry, client_id, device_sn)
    hass.data[DOMAIN][entry.entry_id]["mqtt_client"] = mqtt_client

    try:
        await mqtt_client.connect()
    except (ConnectionRefusedError, asyncio.TimeoutError, ApiException, AuthException) as conn_err: # Bắt thêm AuthException
        _LOGGER.error(f"Failed initial MQTT connection: {conn_err}")
        # Không pop data ở đây
        raise ConfigEntryNotReady(f"MQTT connection failed: {conn_err}") from conn_err
    except Exception as e:
        _LOGGER.exception("Unexpected error during MQTT connection setup")
        raise ConfigEntryNotReady(f"Unexpected MQTT setup error: {e}") from e

    # Khởi tạo Coordinator Stats dùng device_id
    # <<< SỬA LẠI: TRUYỀN device_id CHO COORDINATOR >>>
    coordinator_stats = LumentreeStatsCoordinator(hass, api_client, device_id)
    try:
        _LOGGER.debug("Performing initial fetch for daily stats coordinator...")
        await coordinator_stats.async_config_entry_first_refresh()
        _LOGGER.debug(f"Initial stats fetch completed. Success: {coordinator_stats.last_update_success}")
        if not coordinator_stats.last_update_success:
             _LOGGER.warning("Initial daily stats fetch failed. Check logs. Will retry later.")
             # Không raise lỗi ở đây, coordinator sẽ tự thử lại
    except ConfigEntryAuthFailed as auth_fail:
         _LOGGER.error(f"Auth failed during initial stats fetch: {auth_fail}. Check token/config.")
         # Không raise ConfigEntryNotReady nếu chỉ stats lỗi, có thể MQTT vẫn chạy
         pass # Cho phép tiếp tục setup MQTT
    except UpdateFailed as update_fail:
         _LOGGER.warning(f"Initial daily stats fetch failed: {update_fail}. Will retry later.")
         pass # Cho phép tiếp tục setup MQTT
    except Exception as e:
         _LOGGER.exception("Unexpected error during initial stats coordinator refresh")
         pass # Cho phép tiếp tục setup MQTT
    hass.data[DOMAIN][entry.entry_id]["coordinator_stats"] = coordinator_stats

    # --- Phần Polling MQTT giữ nguyên ---
    polling_interval = datetime.timedelta(seconds=DEFAULT_POLLING_INTERVAL)
    remove_interval: Optional[Callable] = None

    async def _async_poll_data(now=None):
        """Callback function to poll MQTT data."""
        # ... (Giữ nguyên logic polling MQTT) ...
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

    # Bỏ lần gọi poll đầu tiên ở đây, để interval tự chạy
    # await _async_poll_data() # <<< BỎ DÒNG NÀY ĐỂ TRÁNH GỌI NGAY
    remove_interval = async_track_time_interval(hass, _async_poll_data, polling_interval)
    _LOGGER.info(f"Started MQTT polling every {polling_interval}")
    hass.data[DOMAIN][entry.entry_id]["remove_interval"] = remove_interval # Lưu lại để unload

    # --- Phần Unload và Stop giữ nguyên ---
    async def _unload_wrapper():
        """Clean up resources when entry is unloaded."""
        _LOGGER.debug(f"Unloading entry {entry.entry_id}...")
        entry_data_to_unload = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
        if entry_data_to_unload:
            # Hủy interval trước
            interval_remover = entry_data_to_unload.get("remove_interval")
            if interval_remover: interval_remover(); _LOGGER.debug("MQTT polling timer cancelled.")
            # Ngắt kết nối MQTT
            client_to_unload = entry_data_to_unload.get("mqtt_client")
            if isinstance(client_to_unload, LumentreeMqttClient):
                _LOGGER.debug("Disconnecting MQTT client during unload.")
                await client_to_unload.disconnect()
            _LOGGER.debug(f"Removed entry data for {entry.entry_id}.")

    async def _async_stop_mqtt(event: Event) -> None:
        """Ensure MQTT disconnect when Home Assistant stops."""
        _LOGGER.info("Home Assistant stopping event received.")
        # Logic disconnect đã được xử lý trong _unload_wrapper khi HA stop
        # Hoặc có thể gọi disconnect trực tiếp ở đây nếu cần đảm bảo
        entry_data = hass.data.get(DOMAIN, {}).get(entry.entry_id)
        if entry_data and "mqtt_client" in entry_data:
             client_to_stop = entry_data["mqtt_client"]
             if isinstance(client_to_stop, LumentreeMqttClient):
                  _LOGGER.debug("Disconnecting MQTT client due to HA stop.")
                  await client_to_stop.disconnect()


    entry.async_on_unload(_unload_wrapper)
    entry.async_on_unload(hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_stop_mqtt))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _LOGGER.info(f"Successfully set up Lumentree integration for {entry.title} (SN: {device_sn})")
    return True

# --- async_unload_entry giữ nguyên ---
async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info(f"Unloading Lumentree integration for: {entry.title}")

    # Gọi các hàm unload platform trước
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    # Gọi hàm cleanup (_unload_wrapper) đã đăng ký trong async_setup_entry
    # Nó sẽ tự động được gọi bởi HA khi entry unload, không cần gọi lại ở đây.
    # Tuy nhiên, nếu muốn đảm bảo cleanup xảy ra ngay cả khi platform unload lỗi,
    # có thể gọi lại các bước cleanup chính (nhưng cẩn thận double cleanup).
    # Ví dụ:
    # entry_data = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None) # Lấy và xóa data
    # if entry_data:
    #     interval_remover = entry_data.get("remove_interval")
    #     if interval_remover: interval_remover()
    #     client = entry_data.get("mqtt_client")
    #     if client: await client.disconnect()

    if unload_ok:
        _LOGGER.info(f"Successfully unloaded Lumentree integration for {entry.title}.")
    else:
        _LOGGER.warning(f"Failed to cleanly unload Lumentree platforms for {entry.title}.")
        # Vẫn trả về True để HA coi như đã unload, tránh entry bị kẹt
        unload_ok = True

    return unload_ok
