# /config/custom_components/lumentree/coordinator.py

import asyncio
from datetime import timedelta
from typing import Any, Dict

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

# Đảm bảo import từ thư mục hiện tại (.) hoặc tên component (lumentree)
try:
    from .api import LightEarthApiClient, ApiException, AuthException
    from .const import DOMAIN, _LOGGER, UPDATE_INTERVAL_SECONDS, CONF_DEVICE_SN
except ImportError:
    from api import LightEarthApiClient, ApiException, AuthException
    from const import DOMAIN, _LOGGER, UPDATE_INTERVAL_SECONDS, CONF_DEVICE_SN


class LightEarthDataUpdateCoordinator(DataUpdateCoordinator[Dict[str, Any]]):
    """Class to manage fetching Lumentree data."""

    def __init__(self, hass: HomeAssistant, api_client: LightEarthApiClient, device_sn: str) -> None:
        """Initialize."""
        self.api_client = api_client
        self.device_sn = device_sn
        _LOGGER.info(f"Initializing data coordinator for device SN: {device_sn}")

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} ({device_sn})",
            update_interval=timedelta(seconds=UPDATE_INTERVAL_SECONDS),
        )

    async def _async_update_data(self) -> Dict[str, Any]:
        """Fetch data from API endpoint."""
        _LOGGER.debug(f"Coordinator: Attempting to update data for device SN: {self.device_sn}")
        try:
            # Gọi hàm trong API client để lấy dữ liệu
            data = await self.api_client.get_device_data(self.device_sn)

            # --- LOG DEBUG DỮ LIỆU CUỐI CÙNG ---
            # Log dữ liệu mà coordinator sẽ cung cấp cho entities
            _LOGGER.debug(f"Coordinator: Successfully fetched and processed data for {self.device_sn}. Providing to entities: {data}")
            # --- KẾT THÚC LOG DEBUG ---

            return data

        except AuthException as err:
             _LOGGER.error(f"Coordinator: Authentication error during data update for {self.device_sn}: {err}. Re-authentication might be needed.")
             # Có thể trigger reauth flow ở đây nếu cần
             # self.hass.async_create_task(self.config_entry.async_start_reauth(self.hass))
             raise UpdateFailed(f"Authentication error: {err}") from err
        except ApiException as err:
            _LOGGER.error(f"Coordinator: API error during data update for {self.device_sn}: {err}")
            raise UpdateFailed(f"Error communicating with API: {err}") from err
        except Exception as err:
             _LOGGER.exception(f"Coordinator: Unexpected error during data update for {self.device_sn}")
             raise UpdateFailed(f"Unexpected error: {err}") from err