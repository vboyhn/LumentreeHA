# /config/custom_components/lumentree/coordinator_stats.py
# Final corrected version with fixed fallback syntax and timezone logic

import asyncio
import datetime
from typing import Any, Dict, Optional
import logging

from homeassistant.core import HomeAssistant
# Import UpdateFailed và DataUpdateCoordinator từ đúng module
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
# Import các hàm tiện ích datetime và timezone
from homeassistant.util import dt as dt_util
# Import ConfigEntryAuthFailed từ đúng module
from homeassistant.exceptions import ConfigEntryAuthFailed

try:
    # Import các thành phần cần thiết từ component
    from .api import LumentreeHttpApiClient, ApiException, AuthException
    from .const import DOMAIN, _LOGGER, DEFAULT_STATS_INTERVAL, CONF_DEVICE_SN
except ImportError as import_err:
    # --- Fallback Definitions (Đã sửa lỗi cú pháp) ---
    _LOGGER = logging.getLogger(__name__)
    _LOGGER.error(f"ImportError in coordinator_stats: {import_err}. Using fallback definitions.")
    DOMAIN = "lumentree"
    DEFAULT_STATS_INTERVAL = 1800
    CONF_DEVICE_SN = "device_sn"

    # Fallback Class API (Đã sửa lỗi cú pháp)
    class LumentreeHttpApiClient:
        def __init__(self, session=None):
            pass
        # Định nghĩa async def đúng cách (thụt lề)
        async def get_daily_stats(self, sn, date):
            _LOGGER.warning("Using fallback get_daily_stats - returning empty dict.")
            return {}

    # Fallback cho Exceptions (Tách dòng)
    class ApiException(Exception):
        pass
    class AuthException(ApiException):
        pass

    try:
        from homeassistant.helpers.update_coordinator import UpdateFailed
    # Tách except và class fallback ra dòng riêng
    except ImportError:
        class UpdateFailed(Exception):
            pass
    try:
        from homeassistant.exceptions import ConfigEntryAuthFailed
    # Tách except và class fallback ra dòng riêng
    except ImportError:
        class ConfigEntryAuthFailed(Exception):
            pass
    # --- Hết phần Fallback ---

# --- Định nghĩa Lớp Coordinator ---
class LumentreeStatsCoordinator(DataUpdateCoordinator[Dict[str, Optional[float]]]):
    """Coordinator to fetch daily statistics via HTTP API."""

    def __init__(self, hass: HomeAssistant, api_client: LumentreeHttpApiClient, device_sn: str):
        """Initialize the coordinator."""
        self.api_client = api_client
        self.device_sn = device_sn
        update_interval = datetime.timedelta(seconds=DEFAULT_STATS_INTERVAL)

        # Gọi super().__init__
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_stats_{device_sn}", # Tên để debug
            update_interval=update_interval,
        )
        _LOGGER.info(
            f"Initialized Stats Coordinator for {device_sn} with interval: {update_interval}"
        )

    async def _async_update_data(self) -> Dict[str, Optional[float]]:
        """Fetch data from the HTTP API endpoint."""
        _LOGGER.debug(f"Fetching daily stats via HTTP for {self.device_sn}")
        try:
            # Lấy timezone và ngày hiện tại (Đã sửa lỗi TypeError)
            timezone = None
            try:
                tz_string = self.hass.config.time_zone
                if tz_string:
                    timezone = dt_util.get_time_zone(tz_string)
                    if not timezone:
                        _LOGGER.warning(f"Could not get timezone object for '{tz_string}', using default.")
                        timezone = dt_util.get_default_time_zone()
                else:
                    _LOGGER.warning("Timezone not configured in HA, using default.")
                    timezone = dt_util.get_default_time_zone()
            except Exception as tz_err:
                 _LOGGER.error(f"Error getting timezone from HA config: {tz_err}. Using default.")
                 timezone = dt_util.get_default_time_zone()

            today_str = dt_util.now(timezone).strftime("%Y-%m-%d")
            _LOGGER.debug(f"Querying daily stats for date: {today_str}")

            # Gọi API
            async with asyncio.timeout(60):
                stats_data = await self.api_client.get_daily_stats(self.device_sn, today_str)

            # Xử lý kết quả
            if stats_data is None:
                 _LOGGER.warning(f"API client returned None stats data for {self.device_sn} on {today_str}")
                 raise UpdateFailed("API client failed to return stats data")
            if not isinstance(stats_data, dict):
                _LOGGER.error(f"API client returned unexpected data type for stats: {type(stats_data)}")
                raise UpdateFailed("Invalid data type received from API")

            _LOGGER.debug(f"Successfully fetched daily stats: {stats_data}")
            return stats_data

        # Xử lý lỗi
        except AuthException as err:
            _LOGGER.error(f"Authentication error fetching stats: {err}. Please reconfigure integration.")
            raise ConfigEntryAuthFailed(f"Authentication error: {err}") from err
        except ApiException as err:
            _LOGGER.error(f"API error fetching stats: {err}")
            raise UpdateFailed(f"API error: {err}") from err
        except asyncio.TimeoutError as err:
            _LOGGER.error(f"Timeout fetching stats for {self.device_sn}")
            raise UpdateFailed("Timeout fetching statistics data") from err
        except Exception as err:
            _LOGGER.exception(f"Unexpected error fetching stats data")
            raise UpdateFailed(f"Unexpected error: {err}") from err