# /config/custom_components/lumentree/config_flow.py
# Version to Save HTTP Token

import json
import time
from typing import Any, Dict, Optional
import logging

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

# Import các const cần thiết, bao gồm cả CONF_HTTP_TOKEN
try:
    from .const import (
        DOMAIN, CONF_QR_CONTENT, CONF_DEVICE_ID,
        CONF_DEVICE_SN, CONF_DEVICE_NAME, CONF_USER_ID, CONF_HTTP_TOKEN, # <<< Thêm CONF_HTTP_TOKEN
        AUTH_METHOD_GUEST, CONF_AUTH_METHOD, _LOGGER
    )
    # Import API thật để sử dụng
    from .api import LumentreeHttpApiClient, AuthException, ApiException
except ImportError:
    _LOGGER = logging.getLogger(__name__)
    _LOGGER.warning("Could not import constants or API, using fallback definitions for Config Flow.")
    DOMAIN = "lumentree"; CONF_QR_CONTENT = "qr_content"; CONF_DEVICE_ID = "device_id"
    CONF_DEVICE_SN = "device_sn"; CONF_DEVICE_NAME = "device_name"; CONF_USER_ID = "user_id"
    CONF_HTTP_TOKEN = "http_token"; AUTH_METHOD_GUEST = "guest"; CONF_AUTH_METHOD = "auth_method"
    class LumentreeHttpApiClient:
        def __init__(self, session): pass
        # Sửa fallback để trả về 3 giá trị (token có thể là None)
        async def authenticate_guest(self, qr): return None, None, None
        async def get_device_info(self, dev_id): return {}
        # Thêm fallback cho set_token
        def set_token(self, token): pass
    class AuthException(Exception): pass
    class ApiException(Exception): pass


class LumentreeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for Lumentree (Handles HTTP Token)."""
    VERSION = 1

    def __init__(self) -> None:
        """Initialize."""
        self._qr_content: Optional[str] = None
        self._user_id: Optional[int] = None
        self._device_id: Optional[str] = None
        self._http_token: Optional[str] = None # <<< Thêm biến lưu token tạm thời
        self._device_sn: Optional[str] = None
        self._device_name: Optional[str] = None
        self._api_client: Optional[LumentreeHttpApiClient] = None

    async def _get_api_client(self) -> LumentreeHttpApiClient:
        """Get or create HTTP API client."""
        if not self._api_client:
            self._api_client = LumentreeHttpApiClient(async_get_clientsession(self.hass))
        # Gán token vào client nếu đã có (quan trọng cho bước confirm)
        # Cần đảm bảo lớp API thật có hàm set_token
        if self._http_token and hasattr(self._api_client, "set_token"):
             self._api_client.set_token(self._http_token)
        return self._api_client

    async def async_step_user(self, user_input: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Handle the initial step."""
        return await self.async_step_guest()

    async def async_step_guest(self, user_input: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Handle guest login via QR content."""
        errors: Dict[str, str] = {}
        if user_input is not None:
            self._qr_content = user_input[CONF_QR_CONTENT]
            # Luôn tạo client mới ở bước này để đảm bảo không dùng token cũ (nếu có lỗi trước đó)
            self._api_client = LumentreeHttpApiClient(async_get_clientsession(self.hass))
            api = self._api_client # Dùng client vừa tạo

            try:
                # <<< Sửa lại để nhận cả 3 giá trị >>>
                uid, device_id_qr, http_token = await api.authenticate_guest(self._qr_content)
                if uid is None or device_id_qr is None:
                    _LOGGER.error("Failed to retrieve UID or DeviceID after guest login attempt.")
                    raise AuthException("Failed to retrieve UID or DeviceID.")

                self._user_id = uid
                self._device_id = device_id_qr
                self._http_token = http_token # <<< Lưu token lại

                _LOGGER.info(f"Guest login successful. UID: {self._user_id}, DeviceID: {self._device_id}, Token {'found' if http_token else 'not found'}.")

                # <<< Gán token vào API client ngay lập tức để dùng cho bước confirm >>>
                if hasattr(api, "set_token"):
                     api.set_token(self._http_token)
                else:
                     _LOGGER.warning("API client does not have set_token method (using fallback?).")

                # Chuyển sang bước xác nhận thiết bị
                return await self.async_step_confirm_device()

            except AuthException as exc:
                errors["base"] = "invalid_guest_auth"
                _LOGGER.warning(f"Guest auth error: {exc}")
            except ApiException as exc:
                errors["base"] = "cannot_connect"
                _LOGGER.error(f"API connection error during guest auth: {exc}")
            except Exception:
                _LOGGER.exception("Unexpected error during guest login")
                errors["base"] = "unknown"

        # Hiển thị lại form nếu có lỗi
        return self.async_show_form(
            step_id="guest",
            data_schema=vol.Schema({vol.Required(CONF_QR_CONTENT, default=self._qr_content or ""): str}),
            description_placeholders={"qr_example": '{"devices":"P...","expiryTime":"..."}'},
            errors=errors,
        )

    async def async_step_confirm_device(self, user_input: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Confirm device info and create entry."""
        errors: Dict[str, str] = {}
        # Lấy client đã có token (nếu set_token thành công ở bước trước)
        api = await self._get_api_client()

        if user_input is None: # Lần đầu hiển thị form xác nhận
            if not self._device_id:
                 _LOGGER.error("Device ID not available in confirm step. Aborting.")
                 return self.async_abort(reason="missing_device_id")

            try:
                _LOGGER.debug(f"Calling get_device_info for ID: {self._device_id}")
                # Gọi API deviceInfo (nên dùng token nếu có)
                device_info = await api.get_device_info(self._device_id)

                if "_error" in device_info or not device_info:
                    _LOGGER.warning(f"Could not get device info for {self._device_id}. Using Device ID as SN.")
                    self._device_sn = self._device_id
                    self._device_name = f"Device {self._device_id}"
                else:
                    self._device_sn = device_info.get("sn") or self._device_id
                    self._device_name = device_info.get("remarkName") or device_info.get("alias") or f"Device {self._device_sn}"
                    _LOGGER.info(f"Device Info retrieved: SN='{self._device_sn}', Name='{self._device_name}'")

                # Đặt unique_id dựa trên SN
                await self.async_set_unique_id(self._device_sn)
                # Kiểm tra nếu SN đã được cấu hình, cho phép cập nhật tên
                self._abort_if_unique_id_configured(updates={CONF_DEVICE_NAME: self._device_name})

                # Hiển thị form xác nhận
                return self.async_show_form(
                    step_id="confirm_device",
                    description_placeholders={CONF_DEVICE_NAME: self._device_name, CONF_DEVICE_SN: self._device_sn},
                    errors={},
                )
            except (ApiException, AuthException) as exc:
                 _LOGGER.error(f"Error fetching device info: {exc}")
                 errors["base"] = "cannot_connect_deviceinfo"
            except Exception:
                _LOGGER.exception("Unexpected error during device confirmation")
                errors["base"] = "unknown"

            # Hiển thị lại form lỗi nếu không lấy được device info
            return self.async_show_form(
                step_id="confirm_device",
                description_placeholders={CONF_DEVICE_NAME: "Error", CONF_DEVICE_SN: "Unknown"},
                errors=errors,
            )

        # Người dùng nhấn Submit trên form xác nhận -> Tạo entry
        config_data = {
            CONF_AUTH_METHOD: AUTH_METHOD_GUEST,
            CONF_DEVICE_ID: self._device_id,
            CONF_DEVICE_SN: self._device_sn,
            CONF_DEVICE_NAME: self._device_name,
            CONF_USER_ID: self._user_id,
            CONF_HTTP_TOKEN: self._http_token, # <<< LƯU TOKEN HTTP VÀO ENTRY DATA
        }
        _LOGGER.info(f"Creating config entry for SN: {self._device_sn}")
        # title dùng device_name cho dễ nhìn, data chứa thông tin đầy đủ
        return self.async_create_entry(title=self._device_name, data=config_data)