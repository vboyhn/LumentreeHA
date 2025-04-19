# /config/custom_components/lumentree/config_flow.py
# Final version - Add robustness to _get_api_client

import json
import time
from typing import Any, Dict, Optional
import logging

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

try:
    from .const import (
        DOMAIN, CONF_DEVICE_ID, CONF_DEVICE_SN, CONF_DEVICE_NAME, CONF_HTTP_TOKEN, _LOGGER
    )
    from .api import LumentreeHttpApiClient, AuthException, ApiException
except ImportError:
    _LOGGER = logging.getLogger(__name__)
    _LOGGER.warning("ImportError config_flow.py: Using fallback definitions.")
    DOMAIN = "lumentree"; CONF_DEVICE_ID = "device_id"; CONF_DEVICE_SN = "device_sn"; CONF_DEVICE_NAME = "device_name"; CONF_HTTP_TOKEN = "http_token"
    class LumentreeHttpApiClient:
        def __init__(self, session): pass
        async def authenticate_device(self, device_id): return "fallback_token"
        async def get_device_info(self, dev_id): return {"deviceId": dev_id, "deviceType": "Fallback Model"}
        def set_token(self, token): pass
    class AuthException(Exception): pass
    class ApiException(Exception): pass

class LumentreeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for Lumentree (Device ID based auth)."""
    VERSION = 1; CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL
    def __init__(self) -> None: self._device_id_input: Optional[str] = None; self._http_token: Optional[str] = None; self._device_sn_from_api: Optional[str] = None; self._device_name: Optional[str] = None; self._api_client: Optional[LumentreeHttpApiClient] = None; self._reauth_entry: Optional[config_entries.ConfigEntry] = None

    # --- SỬA HÀM NÀY ---
    async def _get_api_client(self) -> LumentreeHttpApiClient:
        """Get or create HTTP API client, ensuring it's not None."""
        _LOGGER.debug("Attempting to get API client instance...")
        if self._api_client is None:
            _LOGGER.debug("API client is None, creating new instance.")
            try:
                session = async_get_clientsession(self.hass)
                if session is None:
                    _LOGGER.error("Failed to get aiohttp client session!")
                    raise ApiException("Could not get client session") # Raise exception

                # Tạo instance trong try/except riêng
                try:
                    self._api_client = LumentreeHttpApiClient(session)
                    _LOGGER.debug(f"Created new API client instance: {type(self._api_client)}")
                except Exception as create_exc:
                     _LOGGER.exception("Error creating LumentreeHttpApiClient instance!")
                     raise ApiException("Failed to create API client instance") from create_exc

            except Exception as session_exc:
                 # Bắt lỗi từ get session hoặc lỗi tạo client
                 _LOGGER.error(f"Failed to initialize API client: {session_exc}")
                 # Raise ApiException để báo lỗi cho các bước sau
                 raise ApiException(f"API Client Initialization failed: {session_exc}") from session_exc
        else:
             _LOGGER.debug(f"Reusing existing API client instance: {type(self._api_client)}")

        # Kiểm tra lại lần nữa trước khi set token và return
        if self._api_client is None:
            # Trường hợp này không nên xảy ra nếu logic trên đúng
            _LOGGER.critical("API client is unexpectedly None after initialization attempt!")
            raise ApiException("API client is None after creation attempt")

        # Gán token nếu có
        if self._http_token:
             if hasattr(self._api_client, "set_token"):
                 self._api_client.set_token(self._http_token)
                 _LOGGER.debug("Set token on API client.")
             else:
                 _LOGGER.warning("API client (or fallback) missing 'set_token' method.")

        return self._api_client
    # --- HẾT PHẦN SỬA ---

    async def async_step_user(self, user_input: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        errors: Dict[str, str] = {}; api: Optional[LumentreeHttpApiClient] = None # Khởi tạo api là None
        if user_input is not None:
            self._device_id_input = user_input[CONF_DEVICE_ID].strip()
            try:
                # Lấy API client, hàm này giờ sẽ raise ApiException nếu thất bại
                api = await self._get_api_client()
                _LOGGER.info(f"Authenticating with Device ID: {self._device_id_input}")
                token = await api.authenticate_device(self._device_id_input) # Gọi method trên instance đã được xác nhận khác None
                self._http_token = token
                _LOGGER.info(f"Auth success for {self._device_id_input}.")
                return await self.async_step_confirm_device()
            except AuthException as exc: _LOGGER.warning(f"Auth failed {self._device_id_input}: {exc}"); errors["base"] = "invalid_auth"
            except ApiException as exc: _LOGGER.error(f"API conn/init error auth {self._device_id_input}: {exc}"); errors["base"] = "cannot_connect"
            except Exception as exc: _LOGGER.exception(f"Unexpected auth error {self._device_id_input}: {exc}"); errors["base"] = "unknown" # Bắt lỗi khác nếu có

        schema = vol.Schema({vol.Required(CONF_DEVICE_ID, default=self._device_id_input or ""): str})
        # Nếu có lỗi, hiển thị lại form user
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)


    async def async_step_confirm_device(self, user_input: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        errors: Dict[str, str] = {}; api: Optional[LumentreeHttpApiClient] = None
        if not self._http_token: _LOGGER.error("Token missing"); return self.async_abort(reason="token_missing")

        try: # Thêm try bao quanh việc lấy api client ở bước này
            api = await self._get_api_client() # Lấy client (đã có token được set bên trong)
        except ApiException as exc: # Bắt lỗi nếu không lấy được client ở bước confirm
             _LOGGER.error(f"Failed to get API client in confirm step: {exc}")
             errors["base"] = "cannot_connect"
             # Hiển thị lại form user nếu không có client? Hoặc abort? Tạm hiển thị lỗi confirm
             return self.async_show_form(step_id="confirm_device", description_placeholders={"device_name":"Error", "device_sn":"Error"}, errors=errors)

        if user_input is None:
            if not self._device_id_input: _LOGGER.error("Device ID missing"); return self.async_abort(reason="cannot_connect")
            try:
                _LOGGER.info(f"Fetching device info for {self._device_id_input} via API..."); device_info_api = await api.get_device_info(self._device_id_input) # api chắc chắn không None ở đây
                if "_error" in device_info_api: api_error = device_info_api["_error"]; _LOGGER.error(f"API error get info: {api_error}"); errors["base"] = "invalid_auth" if "Auth" in api_error else "cannot_connect_deviceinfo"; return self.async_show_form(step_id="confirm_device", description_placeholders={"device_name":"Err", "device_sn":"Err"}, errors=errors)

                self._device_sn_from_api = device_info_api.get("deviceId")
                if not self._device_sn_from_api: _LOGGER.warning(f"deviceId not found for {self._device_id_input}. Using input ID."); self._device_sn_from_api = self._device_id_input
                elif self._device_sn_from_api != self._device_id_input: _LOGGER.warning(f"API deviceId '{self._device_sn_from_api}' differs from input '{self._device_id_input}'. Using API ID.")

                self._device_name = device_info_api.get("remarkName") or device_info_api.get("deviceType") or f"Lumentree {self._device_sn_from_api}"
                _LOGGER.info(f"Device Info: ID/SN='{self._device_sn_from_api}', Name='{self._device_name}', Type='{device_info_api.get('deviceType')}'")

                await self.async_set_unique_id(self._device_sn_from_api)
                updates = {CONF_DEVICE_NAME: self._device_name, CONF_DEVICE_ID: self._device_id_input, CONF_HTTP_TOKEN: self._http_token}
                if self._reauth_entry: pass
                else: self._abort_if_unique_id_configured(updates=updates)

                return self.async_show_form(step_id="confirm_device", description_placeholders={CONF_DEVICE_NAME: self._device_name, CONF_DEVICE_SN: self._device_sn_from_api}, errors={})
            except AuthException as exc: _LOGGER.error(f"Auth error get info {self._device_id_input}: {exc}"); errors["base"] = "invalid_auth"
            except ApiException as exc: _LOGGER.error(f"API error get info {self._device_id_input}: {exc}"); errors["base"] = "cannot_connect_deviceinfo"
            except Exception: _LOGGER.exception(f"Unexpected confirm error {self._device_id_input}"); errors["base"] = "unknown"
            return self.async_show_form(step_id="confirm_device", description_placeholders={"device_name":"Err", "device_sn":"Err"}, errors=errors)

        config_data = {CONF_DEVICE_ID: self._device_id_input, CONF_DEVICE_SN: self._device_sn_from_api, CONF_DEVICE_NAME: self._device_name, CONF_HTTP_TOKEN: self._http_token}
        if self._reauth_entry:
            _LOGGER.info(f"Updating entry {self._reauth_entry.entry_id} for {self._device_sn_from_api} reauth."); self.hass.config_entries.async_update_entry(self._reauth_entry, data=config_data)
            await self.hass.config_entries.async_reload(self._reauth_entry.entry_id); return self.async_abort(reason="reauth_successful")
        _LOGGER.info(f"Creating new entry for SN/ID: {self._device_sn_from_api}"); return self.async_create_entry(title=self._device_name, data=config_data)

    async def async_step_reauth(self, user_input: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        _LOGGER.info("Reauth flow started."); self._reauth_entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        if not self._reauth_entry: return self.async_abort(reason="unknown_entry")
        self._device_id_input = self._reauth_entry.data.get(CONF_DEVICE_ID)
        if not self._device_id_input: _LOGGER.error(f"Cannot reauth {self._reauth_entry.entry_id}: Device ID missing."); return self.async_abort(reason="missing_device_id")
        self._http_token = None; self._api_client = None; return await self.async_step_user(user_input={CONF_DEVICE_ID: self._device_id_input})