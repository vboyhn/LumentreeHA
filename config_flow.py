# /config/custom_components/lumentree/config_flow.py

import json
import time
from typing import Any, Dict, Optional

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

try:
    from .api import LumentreeHttpApiClient, AuthException, ApiException # Đổi tên import
    from .const import (
        DOMAIN, _LOGGER, CONF_AUTH_METHOD, CONF_QR_CONTENT, CONF_DEVICE_ID,
        CONF_DEVICE_SN, CONF_DEVICE_NAME, CONF_USER_ID, AUTH_METHOD_GUEST
    )
except ImportError:
    from api import LumentreeHttpApiClient, AuthException, ApiException
    from const import (
        DOMAIN, _LOGGER, CONF_AUTH_METHOD, CONF_QR_CONTENT, CONF_DEVICE_ID,
        CONF_DEVICE_SN, CONF_DEVICE_NAME, CONF_USER_ID, AUTH_METHOD_GUEST
    )

class LumentreeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for Lumentree."""
    VERSION = 1

    def __init__(self) -> None:
        """Initialize."""
        self._auth_method: Optional[str] = None
        self._qr_content: Optional[str] = None
        self._user_id: Optional[int] = None
        self._device_id: Optional[str] = None # ID từ QR
        self._device_sn: Optional[str] = None # SN thực tế (hy vọng lấy từ deviceInfo)
        self._device_name: Optional[str] = None
        self._api_client: Optional[LumentreeHttpApiClient] = None # Đổi tên class

    async def _get_api_client(self) -> LumentreeHttpApiClient:
        """Get HTTP API client."""
        if not self._api_client:
            self._api_client = LumentreeHttpApiClient(async_get_clientsession(self.hass))
        return self._api_client

    async def async_step_user(self, user_input: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Handle selecting auth method (only Guest supported)."""
        _LOGGER.debug("Config flow: step_user (Guest only)")
        # Chỉ hỗ trợ Guest
        return await self.async_step_guest()

        # --- Code cũ nếu hỗ trợ nhiều phương thức ---
        # if user_input is not None:
        #     self._auth_method = user_input[CONF_AUTH_METHOD]
        #     if self._auth_method == AUTH_METHOD_GUEST:
        #         return await self.async_step_guest()
        # return self.async_show_form(
        #     step_id="user",
        #     data_schema=vol.Schema({
        #         vol.Required(CONF_AUTH_METHOD, default=AUTH_METHOD_GUEST): vol.In({
        #             AUTH_METHOD_GUEST: "Guest Login (QR Code Content)"
        #         })
        #     })
        # )
        # --- Hết code cũ ---

    async def async_step_guest(self, user_input: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Handle guest login."""
        _LOGGER.debug("Config flow: step_guest")
        errors: Dict[str, str] = {}
        if user_input is not None:
            self._qr_content = user_input[CONF_QR_CONTENT]
            api = await self._get_api_client()
            try:
                # Login để lấy uid và deviceId từ QR
                uid, device_id_qr = await api.authenticate_guest(self._qr_content)
                if uid is None or device_id_qr is None:
                    raise AuthException("Failed to retrieve UID or DeviceID after guest login.")
                self._user_id = uid
                self._device_id = device_id_qr # Lưu ID từ QR

                _LOGGER.info(f"Guest login successful, UID: {self._user_id}, DeviceID from QR: {self._device_id}. Proceeding to confirm.")
                # Chuyển sang bước xác nhận (lấy SN/tên)
                return await self.async_step_confirm_device()

            except AuthException as exc:
                _LOGGER.warning(f"Guest authentication failed: {exc}")
                errors["base"] = "invalid_guest_auth"
            except ApiException as exc:
                _LOGGER.error(f"API connection error during guest login: {exc}")
                errors["base"] = "cannot_connect"
            except Exception as exc:
                _LOGGER.exception("Unexpected error during guest login")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="guest",
            data_schema=vol.Schema({vol.Required(CONF_QR_CONTENT, default=self._qr_content or ""): str}),
            description_placeholders={"qr_example": '{"devices":"Pxxxxxxxxxx","expiryTime":"xxxxxxxxxxxxx"}'},
            errors=errors,
        )

    async def async_step_confirm_device(self, user_input: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Try to get device info (SN, name) and confirm."""
        _LOGGER.debug("Config flow: step_confirm_device")
        errors: Dict[str, str] = {}

        if user_input is None: # Chạy lần đầu để lấy info và hiển thị form
            api = await self._get_api_client()
            try:
                # Gọi API deviceInfo với device_id lấy từ QR
                _LOGGER.debug(f"Calling get_device_info for ID: {self._device_id}")
                device_info = await api.get_device_info(self._device_id)

                if "_error" in device_info:
                    _LOGGER.warning(f"Could not get device info for {self._device_id}: {device_info['_error']}. Assuming SN = Device ID.")
                    self._device_sn = self._device_id
                    self._device_name = f"Device {self._device_id}"
                else:
                    # Lấy SN và Name
                    self._device_sn = device_info.get("sn", self._device_id) # Ưu tiên SN
                    self._device_name = device_info.get("remarkName") or device_info.get("alias") or f"Device {self._device_sn}"
                    _LOGGER.info(f"Device Info retrieved: SN='{self._device_sn}', Name='{self._device_name}'")

                # Đặt unique_id dựa trên SN để tránh trùng lặp
                await self.async_set_unique_id(self._device_sn)
                self._abort_if_unique_id_configured(updates={CONF_DEVICE_NAME: self._device_name})

                # Hiển thị form xác nhận
                return self.async_show_form(
                    step_id="confirm_device",
                    description_placeholders={CONF_DEVICE_NAME: self._device_name, CONF_DEVICE_SN: self._device_sn},
                    errors={}, # Không có lỗi ở bước hiển thị form
                )
            except (ApiException, AuthException) as exc:
                 _LOGGER.error(f"Error fetching device info for confirmation: {exc}")
                 errors["base"] = "cannot_connect_deviceinfo" # Lỗi cụ thể hơn
            except Exception as exc:
                 _LOGGER.exception("Unexpected error during device confirmation")
                 errors["base"] = "unknown"

            # Nếu lỗi khi lấy info, không thể tiếp tục, quay lại bước trước? Hay báo lỗi?
            # Tạm thời báo lỗi ở bước này
            return self.async_show_form(
                step_id="confirm_device",
                description_placeholders={CONF_DEVICE_NAME: f"Error fetching info for {self._device_id}", CONF_DEVICE_SN: "Unknown"},
                errors=errors,
            )

        # Người dùng nhấn Submit trên form xác nhận -> Tạo entry
        _LOGGER.info(f"User confirmed device: Name='{self._device_name}', SN='{self._device_sn}', UID='{self._user_id}'")
        config_data = {
            CONF_AUTH_METHOD: AUTH_METHOD_GUEST, # Chỉ hỗ trợ Guest
            CONF_DEVICE_ID: self._device_id, # Lưu ID gốc từ QR
            CONF_DEVICE_SN: self._device_sn, # Lưu SN thực tế
            CONF_DEVICE_NAME: self._device_name,
            CONF_USER_ID: self._user_id, # Lưu UID cho MQTT client ID
            CONF_QR_CONTENT: self._qr_content, # Lưu QR phòng khi cần (ít khả năng)
        }
        return self.async_create_entry(title=self._device_name, data=config_data)