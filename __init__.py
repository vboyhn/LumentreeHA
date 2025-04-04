# /config/custom_components/lumentree/__init__.py

import asyncio
import time
import datetime
import ssl # <<< GIỮ IMPORT SSL
from contextlib import suppress
from functools import partial # <<< THÊM IMPORT PARTIAL
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform, EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant, Event
from homeassistant.exceptions import ConfigEntryNotReady

try:
    from .const import (
        DOMAIN, _LOGGER, CONF_DEVICE_SN, CONF_USER_ID, MQTT_BROKER
    )
    from .mqtt import LumentreeMqttClient
except ImportError:
    # Fallback imports (giữ nguyên)
    DOMAIN = "lumentree"; _LOGGER = logging.getLogger(__name__)
    CONF_DEVICE_SN = "device_sn"; CONF_USER_ID = "user_id"; MQTT_BROKER = "lesvr.suntcn.com"
    class LumentreeMqttClient: # Giả lập class
        async def connect(self): pass
        async def disconnect(self): pass
        async def async_request_data(self): pass
        @property
        def is_connected(self): return False
    import logging

# Chu kỳ polling và timeout
DEFAULT_POLLING_INTERVAL = 15
HTTPS_PING_TIMEOUT = 5

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]

# --- HÀM TẠO SSL CONTEXT (BLOCKING) ---
def _create_non_verifying_ssl_context():
    """Creates an SSL context that doesn't verify certificates (Blocking Call)."""
    _LOGGER.debug("Creating non-verifying SSL context (blocking call)...")
    try:
        # Hàm này là blocking
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        _LOGGER.debug("SSL context created.")
        return ssl_context
    except Exception as e:
        _LOGGER.error(f"Failed to create SSL context: {e}")
        return None # Trả về None nếu lỗi
# --- KẾT THÚC HÀM TẠO SSL CONTEXT ---

async def _try_https_handshake(hass: HomeAssistant, host: str, port: int = 443, timeout: int = 5):
    """
    Attempts a TLS handshake to potentially activate the server.
    Uses executor for blocking SSL context creation.
    """
    _LOGGER.debug(f"Attempting TLS handshake to https://{host}:{port}...")

    # --- SỬA LỖI: Chạy tạo SSL context trong executor ---
    ssl_context = await hass.async_add_executor_job(_create_non_verifying_ssl_context)
    if ssl_context is None:
        _LOGGER.error("Failed to create SSL context for HTTPS handshake.")
        return False # Không thể tiếp tục nếu không có context
    # ---------------------------------------------------

    writer = None
    try:
        _LOGGER.debug("Opening HTTPS connection...")
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port, ssl=ssl_context),
            timeout=timeout
        )
        _LOGGER.debug("HTTPS connection attempt successful. Closing.")
        # writer.close() # Không cần wait_closed() nếu chỉ handshake
        return True
    except asyncio.TimeoutError:
        _LOGGER.warning(f"HTTPS handshake/connection to {host}:{port} timed out.")
        return True
    except ssl.SSLError as e:
        _LOGGER.warning(f"HTTPS handshake to {host}:{port} failed with SSL error: {e}")
        return True
    except OSError as e:
         _LOGGER.warning(f"HTTPS connection to {host}:{port} failed with OS error: {e}")
         return True
    except Exception as e:
        _LOGGER.exception(f"Unexpected error during HTTPS handshake attempt to {host}:{port}")
        return False
    finally:
        if writer and not writer.is_closing():
            with suppress(Exception):
                 writer.close()
                 # await writer.wait_closed() # Không cần đợi ở đây

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Lumentree from a config entry using MQTT."""
    _LOGGER.info(f"Setting up Lumentree integration for entry: {entry.title} ({entry.entry_id})")
    hass.data.setdefault(DOMAIN, {})

    device_sn = entry.data[CONF_DEVICE_SN]
    user_id = entry.data[CONF_USER_ID]
    client_id = f"android-{user_id}-{int(time.time())}"
    _LOGGER.debug(f"Generated MQTT Client ID: {client_id}")

    mqtt_client = LumentreeMqttClient(hass, entry, client_id, device_sn)
    hass.data[DOMAIN][entry.entry_id] = mqtt_client

    try:
        _LOGGER.debug(f"Calling MQTT client connect and waiting for result...")
        await mqtt_client.connect()
        _LOGGER.debug(f"MQTT connect call completed successfully for {entry.title}.")

        # --- LOGIC POLLING ---
        polling_interval = datetime.timedelta(seconds=DEFAULT_POLLING_INTERVAL)

        async def _async_poll_data(now=None):
            _LOGGER.debug("Polling timer triggered.")
            active_client = hass.data[DOMAIN].get(entry.entry_id)
            if not isinstance(active_client, LumentreeMqttClient) or not active_client.is_connected:
                 _LOGGER.warning("MQTT client not connected/found during poll, skipping request.")
                 return

            _LOGGER.debug("MQTT client found and connected.")

            # *** BƯỚC 1: THỬ KẾT NỐI HTTPS ĐỂ KÍCH HOẠT ***
            try:
                # Gọi hàm đã sửa lỗi blocking
                await _try_https_handshake(hass, MQTT_BROKER, 443, timeout=HTTPS_PING_TIMEOUT)
            except Exception as https_err:
                _LOGGER.error(f"Ignoring error during HTTPS activation attempt: {https_err}")
            # ********************************************

            # *** BƯỚC 2: GỬI LỆNH ĐỌC MQTT ***
            _LOGGER.debug("Requesting data via MQTT...")
            try:
                await active_client.async_request_data()
            except Exception as poll_err:
                 _LOGGER.error(f"Error during MQTT data request: {poll_err}")
            # *********************************

        # Gọi lần đầu + đăng ký chạy định kỳ
        await _async_poll_data()
        polling_remover = async_track_time_interval(hass, _async_poll_data, polling_interval)
        entry.async_on_unload(polling_remover)
        _LOGGER.info(f"Started HTTPS activation + MQTT polling every {polling_interval} for {entry.title}")
        # --------------------

    # ... (Khối except và phần load platform giữ nguyên) ...
    except (ConnectionRefusedError, asyncio.TimeoutError) as conn_err:
        _LOGGER.error(f"Failed to establish initial MQTT connection for {entry.title}: {conn_err}")
        hass.data[DOMAIN].pop(entry.entry_id, None)
        raise ConfigEntryNotReady(f"MQTT connection failed: {conn_err}") from conn_err
    except Exception as e:
        _LOGGER.exception(f"Unexpected error during MQTT client setup for {entry.title}")
        client_to_clean = hass.data[DOMAIN].pop(entry.entry_id, None)
        if isinstance(client_to_clean, LumentreeMqttClient): await client_to_clean.disconnect()
        raise ConfigEntryNotReady(f"Unexpected MQTT setup error: {e}") from e

    # Load platforms
    _LOGGER.debug(f"Forwarding setup to platforms: {PLATFORMS} for {entry.title}")
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Đăng ký listener stop/unload (giữ nguyên)
    async def _async_stop_mqtt(event: Event) -> None:
        client_to_stop = hass.data[DOMAIN].get(entry.entry_id)
        if isinstance(client_to_stop, LumentreeMqttClient): await client_to_stop.disconnect()
    entry.async_on_unload( hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_stop_mqtt) )
    async def _unload_wrapper():
        client_to_unload = hass.data[DOMAIN].get(entry.entry_id)
        if isinstance(client_to_unload, LumentreeMqttClient): await client_to_unload.disconnect()
    entry.async_on_unload(_unload_wrapper)

    _LOGGER.info(f"Successfully set up Lumentree MQTT integration for {entry.title}")
    return True

# --- async_unload_entry giữ nguyên ---
async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info(f"Unloading Lumentree integration for entry: {entry.title}")
    # Hàm hủy timer và hàm disconnect đã được đăng ký qua entry.async_on_unload

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    hass.data[DOMAIN].pop(entry.entry_id, None) # Xóa client khỏi data

    if unload_ok: _LOGGER.info(f"Successfully unloaded Lumentree integration.")
    else: _LOGGER.warning(f"Failed to cleanly unload platforms.")
    return unload_ok