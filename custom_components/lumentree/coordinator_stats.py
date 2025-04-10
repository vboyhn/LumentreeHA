# /config/custom_components/lumentree/coordinator_stats.py
# Adapted to use device_id for API calls

import asyncio
import datetime
from typing import Any, Dict, Optional
import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util
from homeassistant.exceptions import ConfigEntryAuthFailed

try:
    from .api import LumentreeHttpApiClient, ApiException, AuthException
    from .const import DOMAIN, _LOGGER, DEFAULT_STATS_INTERVAL, CONF_DEVICE_ID # <<< Import CONF_DEVICE_ID
except ImportError as import_err:
    # --- Fallback Definitions ---
    _LOGGER = logging.getLogger(__name__)
    _LOGGER.error(f"ImportError in coordinator_stats: {import_err}. Using fallback definitions.")
    DOMAIN = "lumentree"
    DEFAULT_STATS_INTERVAL = 1800
    CONF_DEVICE_ID = "device_id" # <<< Fallback key

    class LumentreeHttpApiClient:
        def __init__(self, session=None): pass
        # <<< Sửa fallback stats để nhận device_id >>>
        async def get_daily_stats(self, dev_id, date):
            _LOGGER.warning("Using fallback get_daily_stats - returning empty dict.")
            return {}

    class ApiException(Exception): pass
    class AuthException(ApiException): pass
    try: from homeassistant.helpers.update_coordinator import UpdateFailed
    except ImportError: class UpdateFailed(Exception): pass
    try: from homeassistant.exceptions import ConfigEntryAuthFailed
    except ImportError: class ConfigEntryAuthFailed(Exception): pass
    # --- Hết phần Fallback ---

# --- Định nghĩa Lớp Coordinator ---
class LumentreeStatsCoordinator(DataUpdateCoordinator[Dict[str, Optional[float]]]):
    """Coordinator to fetch daily statistics via HTTP API using Device ID."""

    # <<< SỬA INIT: NHẬN device_id THAY VÌ device_sn >>>
    def __init__(self, hass: HomeAssistant, api_client: LumentreeHttpApiClient, device_id: str):
        """Initialize the coordinator."""
        self.api_client = api_client
        self.device_id = device_id # <<< LƯU device_id
        update_interval = datetime.timedelta(seconds=DEFAULT_STATS_INTERVAL)

        # Tên logger coordinator có thể dùng device_id hoặc tên entry nếu muốn
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_stats_{device_id}", # Tên để debug
            update_interval=update_interval,
        )
        _LOGGER.info(
            f"Initialized Stats Coordinator for Device ID {device_id} with interval: {update_interval}"
        )
        # Lưu ý: Các sensor thuộc coordinator này vẫn sẽ được nhóm dưới device có identifier là SN trong HA.

    async def _async_update_data(self) -> Dict[str, Optional[float]]:
        """Fetch data from the HTTP API endpoint using Device ID."""
        _LOGGER.debug(f"Fetching daily stats via HTTP for Device ID: {self.device_id}")
        try:
            # Lấy timezone và ngày hiện tại
            timezone = dt_util.get_time_zone(self.hass.config.time_zone) if self.hass.config.time_zone else dt_util.get_default_time_zone()
            today_str = dt_util.now(timezone).strftime("%Y-%m-%d")
            _LOGGER.debug(f"Querying daily stats for date: {today_str}")

            # Gọi API dùng device_id
            async with asyncio.timeout(60): # Timeout cho toàn bộ quá trình lấy stats
                # <<< SỬA LẠI: GỌI API VỚI self.device_id >>>
                stats_data = await self.api_client.get_daily_stats(self.device_id, today_str)

            # Xử lý kết quả (giữ nguyên)
            if stats_data is None:
                 _LOGGER.warning(f"API client returned None stats data for {self.device_id} on {today_str}")
                 raise UpdateFailed("API client failed to return stats data")
            if not isinstance(stats_data, dict):
                _LOGGER.error(f"API client returned unexpected data type for stats: {type(stats_data)}")
                raise UpdateFailed("Invalid data type received from API")

            _LOGGER.debug(f"Successfully fetched daily stats for {self.device_id}: {stats_data}")
            return stats_data

        # Xử lý lỗi (giữ nguyên)
        except AuthException as err:
            _LOGGER.error(f"Authentication error fetching stats for {self.device_id}: {err}. Check token.")
            # Raise ConfigEntryAuthFailed để HA biết có vấn đề về auth
            raise ConfigEntryAuthFailed(f"Authentication error fetching stats: {err}") from err
        except ApiException as err:
            _LOGGER.error(f"API error fetching stats for {self.device_id}: {err}")
            raise UpdateFailed(f"API error fetching stats: {err}") from err
        except asyncio.TimeoutError as err:
            _LOGGER.error(f"Timeout fetching stats for {self.device_id}")
            raise UpdateFailed("Timeout fetching statistics data") from err
        except Exception as err:
            _LOGGER.exception(f"Unexpected error fetching stats data for {self.device_id}")
            raise UpdateFailed(f"Unexpected error: {err}") from err
