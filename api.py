# /config/custom_components/lumentree/api.py

import asyncio
import json
from typing import Any, Dict, Optional, Tuple

import aiohttp
from aiohttp.client import ClientTimeout

try:
    from .const import (
        BASE_URL, DEFAULT_HEADERS, URL_LOGIN_TOURIST, URL_DEVICE_INFO, _LOGGER
    )
except ImportError:
    from const import (
        BASE_URL, DEFAULT_HEADERS, URL_LOGIN_TOURIST, URL_DEVICE_INFO, _LOGGER
    )

DEFAULT_TIMEOUT = ClientTimeout(total=20)

class ApiException(Exception): pass
class AuthException(ApiException): pass

class LumentreeHttpApiClient: # Đổi tên để phân biệt với MQTT client
    """Handles HTTP Login and initial device info fetching."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session

    async def _request(
        self, method: str, endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Make an HTTP request."""
        url = f"{BASE_URL}{endpoint}"
        headers = DEFAULT_HEADERS.copy()

        _LOGGER.debug(f"HTTP Request: {method} {url}")
        if params: _LOGGER.debug(f"Params: {params}")
        if data: _LOGGER.debug(f"Data: {data}")

        try:
            async with self._session.request(
                method, url, headers=headers, params=params, data=data, timeout=DEFAULT_TIMEOUT
            ) as response:
                _LOGGER.debug(f"HTTP Response Status from {url}: {response.status}")
                response.raise_for_status() # Check for 4xx/5xx
                try:
                    resp_json = await response.json(content_type=None)
                    _LOGGER.debug(f"HTTP Response JSON from {url}: {resp_json}")
                except (json.JSONDecodeError, aiohttp.ContentTypeError) as json_err:
                    resp_text = await response.text()
                    _LOGGER.error(f"Failed to decode JSON response from {url}: {resp_text[:500]}")
                    raise ApiException(f"Invalid JSON response: {json_err}") from json_err

                return_value = resp_json.get("returnValue")
                msg = resp_json.get("msg", "Unknown error")

                if return_value != 1:
                    _LOGGER.error(f"HTTP API request failed: {url}, returnValue={return_value}, msg='{msg}'")
                    if return_value in [203]:
                         raise AuthException(f"Authentication failed: {msg} (Code: {return_value})")
                    raise ApiException(f"API error: {msg} (Code: {return_value})")

                return resp_json # Trả về toàn bộ JSON nếu thành công
        except asyncio.TimeoutError as exc:
            _LOGGER.error(f"Timeout error requesting {url}: {exc}")
            raise ApiException(f"Timeout contacting API: {exc}") from exc
        except aiohttp.ClientResponseError as exc:
            _LOGGER.error(f"HTTP error requesting {url}: {exc.status}, {exc.message}")
            if exc.status in [401, 403]:
                 raise AuthException(f"Authorization error: {exc.message}") from exc
            raise ApiException(f"HTTP error: {exc.status} {exc.message}") from exc
        except aiohttp.ClientError as exc:
            _LOGGER.error(f"Client error requesting {url}: {exc}")
            raise ApiException(f"Error contacting API: {exc}") from exc
        except Exception as exc:
             _LOGGER.exception(f"Unexpected error during HTTP request to {url}")
             raise ApiException(f"Unexpected error: {exc}") from exc

    async def authenticate_guest(self, qr_content: str) -> Tuple[Optional[int], Optional[str]]:
        """Authenticate using QR code. Returns (uid, device_id_from_qr) or (None, None) on failure."""
        _LOGGER.info("Attempting guest authentication via HTTP")
        if not qr_content:
             raise AuthException("QR Code content not provided")
        try:
            qr_data = json.loads(qr_content)
            device_id_from_qr = qr_data.get("devices")
            server_time = qr_data.get("expiryTime")
            if not device_id_from_qr or not server_time:
                 raise ValueError("Invalid QR code format")

            payload = {"deviceIds": device_id_from_qr, "serverTime": server_time}
            response_json = await self._request("POST", URL_LOGIN_TOURIST, data=payload)

            response_data = response_json.get("data", {})
            uid = response_data.get("uid")

            if uid is not None:
                 _LOGGER.info(f"Guest authentication successful. UID: {uid}")
                 try:
                     uid_int = int(uid)
                     return uid_int, device_id_from_qr # Trả về cả uid và deviceId từ QR
                 except (ValueError, TypeError):
                     _LOGGER.warning(f"Could not convert UID '{uid}' to integer.")
                     return None, None
            else:
                _LOGGER.error("Guest authentication succeeded (returnValue=1) but UID not found in response.")
                raise AuthException("Login succeeded but UID was missing.")

        except (json.JSONDecodeError, ValueError) as exc:
             _LOGGER.error(f"Invalid QR code content format: {exc}")
             raise AuthException(f"Invalid QR code JSON: {exc}") from exc
        except (ApiException, AuthException) as exc:
            _LOGGER.error(f"Guest authentication failed: {exc}")
            raise

    async def get_device_info(self, device_id: str) -> Dict[str, Any]:
        """Fetch detailed device info (potentially including SN). Assumes no extra auth needed."""
        _LOGGER.debug(f"Fetching HTTP device info for device ID: {device_id}")
        try:
            params = {"deviceId": device_id}
            # Giả định API này không cần token/cookie đặc biệt sau login guest
            response_json = await self._request("GET", URL_DEVICE_INFO, params=params)
            response_data = response_json.get("data", {})
            if not isinstance(response_data, dict):
                 _LOGGER.warning(f"Device info response data not a dict: {response_data}")
                 return {}
            _LOGGER.debug(f"Device Info HTTP response data: {response_data}")
            return response_data
        except (ApiException, AuthException) as exc:
            _LOGGER.error(f"Failed to get HTTP device info for {device_id}: {exc}")
            return {"_error": str(exc)} # Trả về lỗi