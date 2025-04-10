# /config/custom_components/lumentree/config_flow.py
# Version using Device ID authentication

import json
import time
from typing import Any, Dict, Optional
import logging

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

# Import các const cần thiết
try:
    from .const import (
        DOMAIN, CONF_DEVICE_ID, # <<< Key nhập liệu chính
        CONF_DEVICE_SN, CONF_DEVICE_NAME, CONF_USER_ID, CONF_HTTP_TOKEN,
        _LOGGER
    )
    # Import API thật để sử dụng
    from .api import LumentreeHttpApiClient, AuthException, ApiException
except ImportError:
    _LOGGER = logging.getLogger(__name__)
    _LOGGER.warning("Could not import constants or API, using fallback definitions for Config Flow.")
    DOMAIN = "lumentree"; CONF_DEVICE_ID = "device_id";
    CONF_DEVICE_SN = "device_sn"; CONF_DEVICE_NAME = "device_name"; CONF_USER_ID = "user_id"
    CONF_HTTP_TOKEN = "http_token";
    class LumentreeHttpApiClient:
        def __init__(self, session): pass
        # Fallback trả về (uid, token)
        async def authenticate_device_id(self, device_id): return None, None
        async def get_device_info(self, dev_id): return {}
        def set_token(self, token): pass
    class AuthException(Exception): pass
    class ApiException(Exception): pass


class LumentreeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for Lumentree (using Device ID)."""
    VERSION = 1

    def __init__(self) -> None:
        """Initialize."""
        self._device_id_input: Optional[str] = None # <<< Lưu Device ID người dùng nhập
        self._user_id: Optional[int] = None
        self._http_token: Optional[str] = None
        self._device_sn: Optional[str] = None # <<< SN lấy từ API
        self._device_name: Optional[str] = None
        self._api_client: Optional[LumentreeHttpApiClient] = None

    async def _get_api_client(self) -> LumentreeHttpApiClient:
        """Get or create HTTP API client."""
        if not self._api_client:
            self._api_client = LumentreeHttpApiClient(async_get_clientsession(self.hass))
        # Gán token vào client nếu đã có
        if self._http_token and hasattr(self._api_client, "set_token"):
             self._api_client.set_token(self._http_token)
        return self._api_client

    async def async_step_user(self, user_input: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Handle the initial step -> directly ask for Device ID."""
        # Bỏ qua bước chọn phương thức, đi thẳng vào nhập Device ID
        return await self.async_step_device_id()

    # --- BƯỚC MỚI: NHẬP DEVICE ID ---
    async def async_step_device_id(self, user_input: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Handle device ID input and authentication."""
        errors: Dict[str, str] = {}
        if user_input is not None:
            self._device_id_input = user_input[CONF_DEVICE_ID].strip() # <<< Lấy Device ID nhập vào
            # Luôn tạo client mới ở bước này
            self._api_client = LumentreeHttpApiClient(async_get_clientsession(self.hass))
            api = self._api_client

            try:
                # Gọi hàm xác thực mới bằng Device ID
                uid, http_token = await api.authenticate_device_id(self._device_id_input)

                # Lưu lại thông tin xác thực thành công
                self._user_id = uid
                self._http_token = http_token
                _LOGGER.info(f"Authentication successful for Device ID: {self._device_id_input}. UID: {self._user_id}, Token received.")

                # Gán token vào API client ngay lập tức để dùng cho bước confirm
                if hasattr(api, "set_token"):
                     api.set_token(self._http_token)
                else:
                     _LOGGER.warning("API client does not have set_token method (using fallback?).")

                # Chuyển sang bước xác nhận thiết bị
                return await self.async_step_confirm_device()

            except AuthException as exc:
                errors["base"] = "invalid_auth" # Lỗi chung cho auth fail
                _LOGGER.warning(f"Authentication error for Device ID {self._device_id_input}: {exc}")
            except ApiException as exc:
                errors["base"] = "cannot_connect"
                _LOGGER.error(f"API connection error during authentication: {exc}")
            except Exception:
                _LOGGER.exception("Unexpected error during device ID authentication")
                errors["base"] = "unknown"

        # Hiển thị lại form nếu có lỗi hoặc lần đầu
        return self.async_show_form(
            step_id="device_id",
            data_schema=vol.Schema({vol.Required(CONF_DEVICE_ID, default=self._device_id_input or ""): str}),
            description_placeholders={"device_id_example": "Pxxxxxxxxxxxxxxx"}, # Ví dụ ID
            errors=errors,
        )

    # --- BƯỚC XÁC NHẬN THIẾT BỊ (Dùng get_device_info đã sửa) ---
    async def async_step_confirm_device(self, user_input: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Confirm device info fetched using the authenticated token and create entry."""
        errors: Dict[str, str] = {}
        # Lấy client đã có token
        api = await self._get_api_client()

        if user_input is None: # Lần đầu hiển thị form xác nhận
            if not self._device_id_input or not self._http_token:
                 _LOGGER.error("Device ID or token not available in confirm step. Aborting.")
                 # Có thể quay lại bước device_id thay vì abort hoàn toàn
                 return self.async_abort(reason="auth_error_occurred")

            try:
                _LOGGER.debug(f"Calling get_device_info (POST) for Device ID: {self._device_id_input}")
                # Gọi API get_device_info (đã sửa thành POST và dùng Device ID)
                device_info = await api.get_device_info(self._device_id_input)

                if "_error" in device_info or not device_info or not device_info.get("sn"):
                    error_msg = device_info.get("_error", "Could not get device info or SN missing")
                    _LOGGER.error(f"Failed to get device info/SN for ID {self._device_id_input}: {error_msg}")
                    # Nếu lỗi là AuthException, có thể token hết hạn
                    if "Auth failed" in error_msg or "Token not available" in error_msg:
                         errors["base"] = "token_error_deviceinfo"
                    else:
                         errors["base"] = "cannot_connect_deviceinfo"
                    # Hiển thị lại form lỗi, không thể tiếp tục nếu không có SN
                    return self.async_show_form(
                         step_id="confirm_device",
                         description_placeholders={"device_name": "Error", "device_sn": "Unknown"},
                         errors=errors,
                    )

                else:
                    # Lấy SN và tên từ device_info
                    self._device_sn = device_info.get("sn")
                    self._device_name = device_info.get("remarkName") or device_info.get("alias") or f"Lumentree {self._device_sn}"
                    _LOGGER.info(f"Device Info retrieved: SN='{self._device_sn}', Name='{self._device_name}'")

                # Đặt unique_id dựa trên SN (SN là định danh duy nhất cho thiết bị vật lý)
                await self.async_set_unique_id(self._device_sn)
                # Kiểm tra nếu SN đã được cấu hình
                self._abort_if_unique_id_configured(updates={
                    CONF_DEVICE_NAME: self._device_name,
                    CONF_HTTP_TOKEN: self._http_token # Cập nhật token nếu cấu hình lại
                })

                # Hiển thị form xác nhận
                return self.async_show_form(
                    step_id="confirm_device",
                    description_placeholders={CONF_DEVICE_NAME: self._device_name, CONF_DEVICE_SN: self._device_sn},
                    errors={}, # Không có lỗi ở đây nếu lấy được info
                )

            except AuthException as exc:
                 _LOGGER.error(f"Authentication error fetching device info: {exc}")
                 errors["base"] = "token_error_deviceinfo" # Lỗi token/auth khi lấy info
            except ApiException as exc:
                 _LOGGER.error(f"API error fetching device info: {exc}")
                 errors["base"] = "cannot_connect_deviceinfo"
            except Exception:
                _LOGGER.exception("Unexpected error during device confirmation")
                errors["base"] = "unknown"

            # Hiển thị lại form lỗi nếu có exception xảy ra
            return self.async_show_form(
                step_id="confirm_device",
                description_placeholders={CONF_DEVICE_NAME: "Error", CONF_DEVICE_SN: "Unknown"},
                errors=errors,
            )

        # Người dùng nhấn Submit trên form xác nhận -> Tạo entry
        if not self._device_sn or not self._device_id_input or self._user_id is None or not self._http_token:
             _LOGGER.error("Missing required data before creating entry. Aborting.")
             return self.async_abort(reason="missing_data_final")

        config_data = {
            # Lưu cả hai ID
            CONF_DEVICE_ID: self._device_id_input, # ID đã nhập (P...)
            CONF_DEVICE_SN: self._device_sn,       # SN lấy từ API
            CONF_DEVICE_NAME: self._device_name,   # Tên lấy từ API hoặc tạo ra
            CONF_USER_ID: self._user_id,           # UID lấy từ authenticate
            CONF_HTTP_TOKEN: self._http_token,     # Token lấy từ authenticate
        }
        _LOGGER.info(f"Creating config entry for SN: {self._device_sn} (Device ID: {self._device_id_input})")
        # title dùng device_name cho dễ nhìn, data chứa thông tin đầy đủ
        return self.async_create_entry(title=self._device_name, data=config_data)
