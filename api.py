# /config/custom_components/lumentree/api.py
# Version with HTTP KWh API logic

import asyncio
import json
from typing import Any, Dict, Optional, Tuple
import logging

import aiohttp
from aiohttp.client import ClientTimeout

try:
    # Import các URL mới và BASE_URL đã sửa (HTTP)
    from .const import (
        BASE_URL, DEFAULT_HEADERS, URL_LOGIN_TOURIST, URL_DEVICE_INFO, _LOGGER,
        URL_GET_OTHER_DAY_DATA, URL_GET_PV_DAY_DATA, URL_GET_BAT_DAY_DATA
    )
except ImportError:
    # Fallback
    _LOGGER = logging.getLogger(__name__)
    BASE_URL = "http://lesvr.suntcn.com" # Đảm bảo fallback dùng HTTP
    URL_LOGIN_TOURIST = "/lesvr/shareDevices"
    URL_DEVICE_INFO = "/lesvr/deviceInfo"
    DEFAULT_HEADERS = {"User-Agent": "okhttp/3.12.0", "Accept": "application/json, text/plain, */*"}
    URL_GET_OTHER_DAY_DATA = "/lesvr/getOtherDayData"
    URL_GET_PV_DAY_DATA = "/lesvr/getPVDayData"
    URL_GET_BAT_DAY_DATA = "/lesvr/getBatDayData"


DEFAULT_TIMEOUT = ClientTimeout(total=30) # Tăng timeout một chút cho API request

class ApiException(Exception): pass
class AuthException(ApiException): pass

class LumentreeHttpApiClient:
    """Handles HTTP Login, Device Info, and Daily Stats API calls."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        """Initialize the API client."""
        self._session = session
        self._token: Optional[str] = None # Thêm lại biến lưu token

    def set_token(self, token: Optional[str]):
        """Set the HTTP token obtained after login."""
        self._token = token
        _LOGGER.debug(f"HTTP API client token {'set' if token else 'cleared'}.")

    async def _request(
        self, method: str, endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        requires_auth: bool = True # Mặc định API cần xác thực
    ) -> Dict[str, Any]:
        """Make an HTTP request."""
        url = f"{BASE_URL}{endpoint}"
        headers = DEFAULT_HEADERS.copy()

        # <<< SỬA LẠI: Dùng header Authorization >>>
        if requires_auth:
            if self._token:
                headers["Authorization"] = self._token # <<< Dùng Authorization
                _LOGGER.debug(f"Adding Authorization header for request to {endpoint}")
            else:
                _LOGGER.error(f"Token required for {endpoint} but none set.")
                raise AuthException(f"Authentication token required for {endpoint}")

        _LOGGER.debug(f"HTTP Request: {method} {url}, Params: {params}, Data: {data}")
        try:
            async with self._session.request(
                method, url, headers=headers, params=params, data=data, timeout=DEFAULT_TIMEOUT
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
                        return {"returnValue": 1, "data": {}, "msg": "OK, non-JSON response"}
                    else:
                         response.raise_for_status()

                except (json.JSONDecodeError, aiohttp.ContentTypeError) as json_err:
                    if not resp_text_short: resp_text_short = (await response.text())[:200]
                    _LOGGER.error(f"Invalid JSON response from {url}: {resp_text_short}")
                    raise ApiException(f"Invalid JSON response: {resp_text_short}") from json_err

                # Kiểm tra returnValue
                return_value = resp_json.get("returnValue")
                msg = resp_json.get("msg", "Unknown API error")
                if return_value != 1:
                    _LOGGER.error(f"API Error: {url}, RC={return_value}, Msg='{msg}'")
                    if return_value == 203: # Mã lỗi auth từ server
                        raise AuthException(f"Auth failed (RC=203): {msg}")
                    # Lỗi API chung
                    raise ApiException(f"API error: {msg} (Code: {return_value})")
                return resp_json

        except asyncio.TimeoutError as exc:
            _LOGGER.error(f"Timeout reaching {url}")
            raise ApiException(f"Timeout reaching {url}") from exc
        except aiohttp.ClientResponseError as exc:
            # Phân biệt lỗi auth rõ hơn
            if exc.status in [401, 403]:
                raise AuthException(f"Authorization error ({exc.status}): {exc.message}")
            _LOGGER.error(f"HTTP error from {url}: {exc.status} {exc.message}")
            raise ApiException(f"HTTP error: {exc.status} {exc.message}") from exc
        except aiohttp.ClientError as exc:
            _LOGGER.error(f"Client error during request to {url}: {exc}")
            raise ApiException(f"Client error: {exc}") from exc
        except Exception as exc:
            _LOGGER.exception(f"Unexpected HTTP error during request to {url}")
            raise ApiException(f"Unexpected: {exc}")

    async def authenticate_guest(self, qr_content: str) -> Tuple[Optional[int], Optional[str], Optional[str]]:
        """Authenticate using QR code. Returns (uid, device_id_from_qr, http_token)."""
        _LOGGER.info("Attempting guest authentication via HTTP")
        if not qr_content:
            raise AuthException("QR Code content missing")
        try:
            qr_data = json.loads(qr_content)
            device_id_qr = qr_data.get("devices")
            server_time = qr_data.get("expiryTime")
            if not device_id_qr or not server_time:
                raise ValueError("Invalid QR format (missing 'devices' or 'expiryTime')")

            payload = {"deviceIds": device_id_qr, "serverTime": server_time}
            # Gọi login không cần auth
            response_json = await self._request("POST", URL_LOGIN_TOURIST, data=payload, requires_auth=False)
            response_data = response_json.get("data", {})
            uid = response_data.get("uid")
            http_token = response_data.get("token") # <<< Lấy token

            if uid is not None:
                _LOGGER.info(f"Guest auth successful. UID: {uid}, Token: {'****' if http_token else 'N/A'}")
                try:
                    # <<< Trả về cả 3 giá trị >>>
                    return int(uid), device_id_qr, http_token
                except (ValueError, TypeError):
                     _LOGGER.error("Could not parse UID to int.")
                     return None, None, None
            else:
                raise AuthException("Login succeeded but UID missing in response.")
        except (json.JSONDecodeError, ValueError) as exc:
            _LOGGER.error(f"Invalid QR JSON: {exc}")
            raise AuthException(f"Invalid QR JSON: {exc}") from exc
        # Các exception ApiException, AuthException từ _request sẽ được raise lên

    async def get_device_info(self, device_id: str) -> Dict[str, Any]:
        """Fetch detailed device info. Uses token if set via Authorization header."""
        _LOGGER.debug(f"Fetching HTTP device info for ID: {device_id}")
        if not device_id:
            _LOGGER.warning("Device ID is missing for get_device_info.")
            return {"_error": "Device ID missing"}
        try:
            params = {"deviceId": device_id}
            # Gọi _request mặc định requires_auth=True
            response_json = await self._request("GET", URL_DEVICE_INFO, params=params)
            response_data = response_json.get("data", {})
            return response_data if isinstance(response_data, dict) else {}
        except (ApiException, AuthException) as exc: # Bắt cả lỗi Auth
            _LOGGER.error(f"Failed get device info for {device_id}: {exc}")
            return {"_error": str(exc)}

    # --- HÀM GỌI API THỐNG KÊ NGÀY (ĐÃ SỬA) ---
    async def get_daily_stats(self, device_sn: str, query_date: str) -> Dict[str, Optional[float]]:
        """
        Fetch all daily statistics (PV, Bat, Grid, Load) for a specific date.
        Uses GET requests with query parameters and Authorization header.
        Returns a dictionary with aggregated kWh values (already divided by 10).
        Keys match KEY_DAILY_* in const.py (e.g., "pv_today").
        """
        _LOGGER.debug(f"Fetching daily stats for SN: {device_sn}, Date: {query_date}")
        # Các key trả về phải khớp với KEY_DAILY_* trong const.py
        results = {
            "pv_today": None,
            "charge_today": None,
            "discharge_today": None,
            "grid_in_today": None,
            "load_today": None,
        }
        # <<< Sửa key tham số thành 'deviceId' >>>
        base_params = {"deviceId": device_sn, "queryDate": query_date}

        # Chạy các request tuần tự để dễ debug
        try:
            # <<< Dùng GET và params >>>
            pv_resp = await self._request("GET", URL_GET_PV_DAY_DATA, params=base_params)
            pv_data = pv_resp.get("data", {}).get("pv", {})
            if pv_data and "tableValue" in pv_data:
                results["pv_today"] = float(pv_data["tableValue"]) / 10.0
        except (ApiException, AuthException) as e:
            _LOGGER.warning(f"Failed to get PV daily data ({type(e).__name__}): {e}")
        except Exception as e: # Bắt lỗi khác (vd: float conversion)
             _LOGGER.exception(f"Unexpected error processing PV daily data: {e}")


        try:
            # <<< Dùng GET và params >>>
            bat_resp = await self._request("GET", URL_GET_BAT_DAY_DATA, params=base_params)
            bat_data_list = bat_resp.get("data", {}).get("bats", [])
            if isinstance(bat_data_list, list):
                 # Giả định list[0] là Charge, list[1] là Discharge
                 if len(bat_data_list) > 0 and "tableValue" in bat_data_list[0]:
                      results["charge_today"] = float(bat_data_list[0]["tableValue"]) / 10.0
                 if len(bat_data_list) > 1 and "tableValue" in bat_data_list[1]:
                      results["discharge_today"] = float(bat_data_list[1]["tableValue"]) / 10.0
        except (ApiException, AuthException) as e:
            _LOGGER.warning(f"Failed to get Battery daily data ({type(e).__name__}): {e}")
        except Exception as e:
             _LOGGER.exception(f"Unexpected error processing Battery daily data: {e}")

        try:
            # <<< Dùng GET và params >>>
            other_resp = await self._request("GET", URL_GET_OTHER_DAY_DATA, params=base_params)
            other_data = other_resp.get("data", {})
            grid_data = other_data.get("grid", {})
            load_data = other_data.get("homeload", {}) # Giả định homeload là total load
            if grid_data and "tableValue" in grid_data:
                 results["grid_in_today"] = float(grid_data["tableValue"]) / 10.0
            if load_data and "tableValue" in load_data:
                 results["load_today"] = float(load_data["tableValue"]) / 10.0
        except (ApiException, AuthException) as e:
            _LOGGER.warning(f"Failed to get Other (Grid/Load) daily data ({type(e).__name__}): {e}")
        except Exception as e:
             _LOGGER.exception(f"Unexpected error processing Other daily data: {e}")

        _LOGGER.debug(f"Fetched daily stats results for {query_date}: {results}")
        # Chỉ trả về các giá trị khác None để coordinator biết key nào thực sự có dữ liệu
        return {k: v for k, v in results.items() if v is not None}
    # --- KẾT THÚC HÀM API STATS ---