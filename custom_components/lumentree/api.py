# /config/custom_components/lumentree/api.py
# Version with C#-like authentication and API calls

import asyncio
import json
from typing import Any, Dict, Optional, Tuple
import logging

import aiohttp
from aiohttp.client import ClientTimeout

try:
    # Import các URL mới và BASE_URL đã sửa (HTTP)
    from .const import (
        BASE_URL, DEFAULT_HEADERS, _LOGGER,
        URL_GET_SERVER_TIME, URL_SHARE_DEVICES, URL_GET_DEVICE, # <<< URL MỚI
        URL_GET_OTHER_DAY_DATA, URL_GET_PV_DAY_DATA, URL_GET_BAT_DAY_DATA
    )
except ImportError:
    # Fallback
    _LOGGER = logging.getLogger(__name__)
    BASE_URL = "http://lesvr.suntcn.com" # Đảm bảo fallback dùng HTTP
    DEFAULT_HEADERS = {"versionCode": "1.6.3", "platform": "2", "wifiStatus": "1"}
    URL_GET_SERVER_TIME = "/lesvr/getServerTime"
    URL_SHARE_DEVICES = "/lesvr/shareDevices"
    URL_GET_DEVICE = "/lesvr/getDevice"
    URL_GET_OTHER_DAY_DATA = "/lesvr/getOtherDayData"
    URL_GET_PV_DAY_DATA = "/lesvr/getPVDayData"
    URL_GET_BAT_DAY_DATA = "/lesvr/getBatDayData"


DEFAULT_TIMEOUT = ClientTimeout(total=30) # Giữ timeout

class ApiException(Exception): pass
class AuthException(ApiException): pass

class LumentreeHttpApiClient:
    """Handles HTTP Login, Device Info, and Daily Stats API calls."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        """Initialize the API client."""
        self._session = session
        self._token: Optional[str] = None

    def set_token(self, token: Optional[str]):
        """Set the HTTP token obtained after login."""
        self._token = token
        _LOGGER.debug(f"HTTP API client token {'set' if token else 'cleared'}.")

    async def _request(
        self, method: str, endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None, # For form data
        json_payload: Optional[Dict[str, Any]] = None, # For json data
        extra_headers: Optional[Dict[str, str]] = None,
        requires_auth: bool = False # Mặc định API không cần auth, trừ khi được chỉ định
    ) -> Dict[str, Any]:
        """Make an HTTP request. Handles form data and JSON."""
        url = f"{BASE_URL}{endpoint}"
        headers = DEFAULT_HEADERS.copy()
        if extra_headers:
            headers.update(extra_headers)

        # Thêm User-Agent và Accept nếu chưa có
        headers.setdefault("User-Agent", "okhttp/3.12.0") # Giống C# hoặc HA agent
        headers.setdefault("Accept", "application/json, text/plain, */*")

        if requires_auth:
            if self._token:
                headers["Authorization"] = self._token
                _LOGGER.debug(f"Adding Authorization header for request to {endpoint}")
            else:
                _LOGGER.error(f"Token required for {endpoint} but none set.")
                raise AuthException(f"Authentication token required for {endpoint}")

        _LOGGER.debug(f"HTTP Request: {method} {url}, Headers: {headers}, Params: {params}, Data: {data}, JSON: {json_payload}")
        try:
            async with self._session.request(
                method, url, headers=headers, params=params, data=data, json=json_payload, timeout=DEFAULT_TIMEOUT
            ) as response:
                _LOGGER.debug(f"HTTP Response Status: {response.status} from {url}")
                resp_text_short = ""
                try:
                    # Xử lý response JSON
                    if 'application/json' in response.headers.get('Content-Type', ''):
                        resp_json = await response.json(content_type=None)
                        _LOGGER.debug(f"HTTP Response JSON: {resp_json}")
                    elif response.ok:
                        resp_text = await response.text()
                        resp_text_short = resp_text[:200]
                        _LOGGER.warning(f"Non-JSON response with OK status from {url}. Text: {resp_text_short}")
                        # Trả về cấu trúc giống success nhưng data rỗng
                        return {"returnValue": 1, "data": {}, "msg": "OK, non-JSON response"}
                    else:
                         response.raise_for_status() # Gây lỗi nếu status không OK và không phải JSON

                except (json.JSONDecodeError, aiohttp.ContentTypeError) as json_err:
                    if not resp_text_short: resp_text_short = (await response.text())[:200]
                    _LOGGER.error(f"Invalid JSON response from {url}: {resp_text_short}")
                    raise ApiException(f"Invalid JSON response: {resp_text_short}") from json_err

                # Kiểm tra returnValue
                return_value = resp_json.get("returnValue")
                msg = resp_json.get("msg", "Unknown API error")

                # Mã lỗi 203 hoặc các mã lỗi token khác (ví dụ từ các API sau khi login)
                if return_value == 203:
                    _LOGGER.error(f"Authentication/Authorization failed for {url} (RC={return_value}): {msg}")
                    raise AuthException(f"Auth failed (RC=203): {msg}")

                # Các lỗi API khác
                if return_value != 1:
                    _LOGGER.error(f"API Error: {url}, RC={return_value}, Msg='{msg}'")
                    raise ApiException(f"API error: {msg} (Code: {return_value})")

                return resp_json

        except asyncio.TimeoutError as exc:
            _LOGGER.error(f"Timeout reaching {url}")
            raise ApiException(f"Timeout reaching {url}") from exc
        except aiohttp.ClientResponseError as exc:
            # Phân biệt lỗi auth rõ hơn nếu server trả về 401/403
            if exc.status in [401, 403]:
                raise AuthException(f"Authorization error ({exc.status}): {exc.message}")
            _LOGGER.error(f"HTTP error from {url}: {exc.status} {exc.message}")
            raise ApiException(f"HTTP error: {exc.status} {exc.message}") from exc
        except aiohttp.ClientError as exc:
            _LOGGER.error(f"Client error during request to {url}: {exc}")
            raise ApiException(f"Client error: {exc}") from exc
        # Bắt AuthException được raise từ kiểm tra returnValue=203
        except AuthException:
             raise # Re-raise AuthException để config flow xử lý
        except Exception as exc:
            _LOGGER.exception(f"Unexpected HTTP error during request to {url}")
            raise ApiException(f"Unexpected: {exc}")

    # --- HÀM MỚI: LẤY SERVER TIME ---
    async def get_server_time(self) -> Optional[int]:
        """Fetches the current server time from the API."""
        _LOGGER.debug("Requesting server time from API")
        try:
            # Request này không cần auth
            response_json = await self._request("GET", URL_GET_SERVER_TIME, requires_auth=False)
            server_time = response_json.get("data", {}).get("serverTime")
            if server_time:
                _LOGGER.debug(f"Successfully retrieved server time: {server_time}")
                return int(server_time)
            else:
                _LOGGER.warning("Server time not found in response.")
                return None
        except (ApiException, ValueError, TypeError) as exc:
            _LOGGER.error(f"Failed to get or parse server time: {exc}")
            return None # Trả về None nếu có lỗi

    # --- HÀM MỚI: XÁC THỰC BẰNG DEVICE ID ---
    async def authenticate_device_id(self, device_id: str) -> Tuple[Optional[int], Optional[str]]:
        """
        Authenticates using device ID and server time to get token and UID.
        Returns (uid, http_token).
        """
        _LOGGER.info(f"Attempting authentication for Device ID: {device_id}")
        if not device_id:
            raise AuthException("Device ID is missing")

        # 1. Lấy server time
        server_time = await self.get_server_time()
        if server_time is None:
            raise AuthException("Could not retrieve server time for authentication.")

        _LOGGER.debug(f"Using Device ID '{device_id}' and Server Time '{server_time}' for token request.")

        # 2. Gọi API shareDevices để lấy token
        try:
            payload = {
                "deviceIds": device_id,
                "serverTime": str(server_time) # API C# gửi dạng string
            }
            # Headers cần thiết cho request này
            headers = {
                "Content-Type": "application/x-www-form-urlencoded",
                "source": "2" # Giống C#
            }
            # Gọi API shareDevices (không cần auth ban đầu)
            response_json = await self._request(
                "POST",
                URL_SHARE_DEVICES,
                data=payload, # <<< Dùng form data
                extra_headers=headers,
                requires_auth=False
            )
            response_data = response_json.get("data", {})
            uid = response_data.get("uid")
            http_token = response_data.get("token")

            if uid is not None and http_token:
                _LOGGER.info(f"Authentication successful. UID: {uid}, Token received.")
                try:
                    return int(uid), http_token
                except (ValueError, TypeError):
                     _LOGGER.error("Could not parse UID to int.")
                     raise AuthException("Received invalid UID format from API.")
            else:
                # Lấy msg lỗi nếu có
                msg = response_json.get("msg", "Token or UID missing in response.")
                _LOGGER.error(f"Authentication failed: {msg} (UID: {uid}, Token Present: {bool(http_token)})")
                raise AuthException(f"Authentication failed: {msg}")

        # Các exception ApiException, AuthException từ _request hoặc logic trên sẽ được raise lên
        except AuthException:
             raise # Re-raise để config flow biết là lỗi auth
        except ApiException as exc:
             _LOGGER.error(f"API error during device ID authentication: {exc}")
             # Bọc lỗi API chung vào AuthException cho config flow xử lý như lỗi login
             raise AuthException(f"API error during authentication: {exc}") from exc

    # --- HÀM CŨ authenticate_guest -> BỎ ---
    # async def authenticate_guest(self, qr_content: str) -> Tuple[Optional[int], Optional[str], Optional[str]]:
    #     ... # Bỏ hàm này

    # --- HÀM SỬA LẠI: GET DEVICE INFO DÙNG POST ---
    async def get_device_info(self, device_id: str) -> Dict[str, Any]:
        """Fetch detailed device info using POST. Requires prior authentication (token)."""
        _LOGGER.debug(f"Fetching HTTP device info for ID: {device_id} using POST")
        if not device_id:
            _LOGGER.warning("Device ID is missing for get_device_info.")
            return {"_error": "Device ID missing"}
        if not self._token:
             _LOGGER.error("Cannot get device info: HTTP token is not set.")
             # Raise AuthException để có thể trigger reauth nếu cần
             raise AuthException("Token not available for get_device_info")

        try:
            payload = {
                "snName": device_id, # <<< Key là snName theo C#
                "onlineStatus": "1"  # <<< Tham số onlineStatus theo C#
            }
            headers = {
                "Content-Type": "application/x-www-form-urlencoded"
                # Authorization được thêm tự động bởi _request khi requires_auth=True
            }
            # Gọi API getDevice bằng POST, yêu cầu auth
            response_json = await self._request(
                "POST",
                URL_GET_DEVICE, # <<< Dùng URL mới
                data=payload,
                extra_headers=headers,
                requires_auth=True # <<< Yêu cầu token
            )
            # Cấu trúc response C#: data -> devices (list) -> device object
            response_data = response_json.get("data", {})
            devices_list = response_data.get("devices")
            if isinstance(devices_list, list) and len(devices_list) > 0:
                 # Lấy thiết bị đầu tiên trong danh sách
                 device_info_data = devices_list[0]
                 if isinstance(device_info_data, dict):
                     _LOGGER.debug(f"Device info retrieved successfully: {device_info_data.get('sn')}")
                     return device_info_data
                 else:
                     _LOGGER.warning("First item in 'devices' list is not a dictionary.")
                     return {"_error": "Invalid device data format in list"}
            else:
                 _LOGGER.warning(f"No 'devices' list found or empty in response for {device_id}")
                 return {"_error": "No device data found in response"}

        except AuthException as exc: # Bắt lỗi Auth từ _request hoặc raise ở trên
            _LOGGER.error(f"Auth failed getting device info for {device_id}: {exc}")
            # Re-raise để config flow hoặc coordinator xử lý
            raise
        except ApiException as exc:
            _LOGGER.error(f"API error getting device info for {device_id}: {exc}")
            return {"_error": str(exc)}
        except Exception as exc:
             _LOGGER.exception(f"Unexpected error getting device info for {device_id}")
             return {"_error": f"Unexpected error: {exc}"}

    # --- HÀM SỬA LẠI: GET DAILY STATS DÙNG DEVICE ID ---
    async def get_daily_stats(self, device_id: str, query_date: str) -> Dict[str, Optional[float]]:
        """
        Fetch all daily statistics (PV, Bat, Grid, Load) for a specific date using Device ID.
        Uses GET requests with query parameters and Authorization header.
        Returns a dictionary with aggregated kWh values (already divided by 10).
        Keys match KEY_DAILY_* in const.py (e.g., "pv_today").
        Requires prior authentication (token).
        """
        _LOGGER.debug(f"Fetching daily stats for Device ID: {device_id}, Date: {query_date}")
        if not self._token:
             _LOGGER.error("Cannot get daily stats: HTTP token is not set.")
             raise AuthException("Token not available for get_daily_stats")

        results = {
            "pv_today": None, "charge_today": None, "discharge_today": None,
            "grid_in_today": None, "load_today": None,
        }
        # <<< Sửa key tham số thành 'deviceId' và dùng device_id thay vì SN >>>
        base_params = {"deviceId": device_id, "queryDate": query_date}
        headers = {
            "Content-Type": "application/x-www-form-urlencoded" # Giống C#
            # Authorization được thêm tự động
        }

        # Chạy các request tuần tự để dễ debug
        try:
            # PV Data (GET request)
            pv_resp = await self._request("GET", URL_GET_PV_DAY_DATA, params=base_params, extra_headers=headers, requires_auth=True)
            pv_data = pv_resp.get("data", {}).get("pv", {})
            if pv_data and "tableValue" in pv_data:
                results["pv_today"] = float(pv_data["tableValue"]) / 10.0
        except (ApiException, AuthException) as e:
            _LOGGER.warning(f"Failed to get PV daily data ({type(e).__name__}): {e}")
            if isinstance(e, AuthException): raise # Re-raise AuthException
        except Exception as e:
             _LOGGER.exception(f"Unexpected error processing PV daily data: {e}")

        try:
            # Battery Data (GET request)
            bat_resp = await self._request("GET", URL_GET_BAT_DAY_DATA, params=base_params, extra_headers=headers, requires_auth=True)
            bat_data_list = bat_resp.get("data", {}).get("bats", [])
            if isinstance(bat_data_list, list):
                 if len(bat_data_list) > 0 and "tableValue" in bat_data_list[0]:
                      results["charge_today"] = float(bat_data_list[0]["tableValue"]) / 10.0
                 if len(bat_data_list) > 1 and "tableValue" in bat_data_list[1]:
                      results["discharge_today"] = float(bat_data_list[1]["tableValue"]) / 10.0
        except (ApiException, AuthException) as e:
            _LOGGER.warning(f"Failed to get Battery daily data ({type(e).__name__}): {e}")
            if isinstance(e, AuthException): raise
        except Exception as e:
             _LOGGER.exception(f"Unexpected error processing Battery daily data: {e}")

        try:
            # Other Data (GET request)
            other_resp = await self._request("GET", URL_GET_OTHER_DAY_DATA, params=base_params, extra_headers=headers, requires_auth=True)
            other_data = other_resp.get("data", {})
            grid_data = other_data.get("grid", {})
            load_data = other_data.get("homeload", {}) # Giả định homeload là total load
            if grid_data and "tableValue" in grid_data:
                 results["grid_in_today"] = float(grid_data["tableValue"]) / 10.0
            if load_data and "tableValue" in load_data:
                 results["load_today"] = float(load_data["tableValue"]) / 10.0
        except (ApiException, AuthException) as e:
            _LOGGER.warning(f"Failed to get Other (Grid/Load) daily data ({type(e).__name__}): {e}")
            if isinstance(e, AuthException): raise
        except Exception as e:
             _LOGGER.exception(f"Unexpected error processing Other daily data: {e}")

        _LOGGER.debug(f"Fetched daily stats results for {query_date}: {results}")
        # Chỉ trả về các giá trị khác None để coordinator biết key nào thực sự có dữ liệu
        return {k: v for k, v in results.items() if v is not None}
    # --- KẾT THÚC HÀM API STATS ---
