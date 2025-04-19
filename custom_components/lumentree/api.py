# /config/custom_components/lumentree/api.py
# Final version - Fixed SyntaxError AGAIN in get_daily_stats try block

import asyncio
import json
from typing import Any, Dict, Optional, Tuple
import logging
import time

import aiohttp
from aiohttp.client import ClientTimeout

try:
    from .const import (
        BASE_URL, DEFAULT_HEADERS, _LOGGER,
        URL_GET_SERVER_TIME, URL_SHARE_DEVICES, URL_DEVICE_MANAGE,
        URL_GET_OTHER_DAY_DATA, URL_GET_PV_DAY_DATA, URL_GET_BAT_DAY_DATA
    )
except ImportError:
    _LOGGER = logging.getLogger(__name__); BASE_URL = "http://lesvr.suntcn.com"
    URL_GET_SERVER_TIME = "/lesvr/getServerTime"; URL_SHARE_DEVICES = "/lesvr/shareDevices"
    URL_DEVICE_MANAGE = "/lesvr/deviceManage";
    URL_GET_OTHER_DAY_DATA = "/lesvr/getOtherDayData"; URL_GET_PV_DAY_DATA = "/lesvr/getPVDayData"; URL_GET_BAT_DAY_DATA = "/lesvr/getBatDayData"
    DEFAULT_HEADERS = {"versionCode": "1.6.3", "platform": "2", "wifiStatus": "1", "User-Agent": "Mozilla/5.0", "Accept": "application/json, text/plain, */*", "Accept-Language": "en-US,en;q=0.9"}

DEFAULT_TIMEOUT = ClientTimeout(total=30)
AUTH_RETRY_DELAY = 0.5
AUTH_MAX_RETRIES = 3

class ApiException(Exception): pass
class AuthException(ApiException): pass

class LumentreeHttpApiClient:
    """Handles HTTP Login, Device Info, and Daily Stats API calls."""
    def __init__(self, session: aiohttp.ClientSession) -> None: self._session = session; self._token: Optional[str] = None
    def set_token(self, token: Optional[str]): self._token = token; _LOGGER.debug(f"API token {'set' if token else 'cleared'}.")

    async def _request(
        self, method: str, endpoint: str, params: Optional[Dict[str, Any]] = None, data: Optional[Dict[str, Any]] = None,
        extra_headers: Optional[Dict[str, str]] = None, requires_auth: bool = True
    ) -> Dict[str, Any]:
        url = f"{BASE_URL}{endpoint}"; headers = DEFAULT_HEADERS.copy();
        if extra_headers: headers.update(extra_headers)
        if requires_auth:
            if self._token: headers["Authorization"] = self._token
            else: _LOGGER.error(f"Token needed for {endpoint}"); raise AuthException("Token required")
        if data and method.upper() == "POST": headers["Content-Type"] = headers.get("Content-Type", "application/x-www-form-urlencoded")
        _LOGGER.debug(f"HTTP Req: {method} {url}, H: {headers}, P: {params}, D: {data}")
        try:
            async with self._session.request(method, url, headers=headers, params=params, data=data, timeout=DEFAULT_TIMEOUT) as response:
                _LOGGER.debug(f"HTTP Resp Status: {response.status} from {url}"); resp_text = await response.text(); resp_text_short = resp_text[:300]
                try: resp_json = await response.json(content_type=None); _LOGGER.debug(f"HTTP Resp JSON: {resp_json}")
                except (json.JSONDecodeError, aiohttp.ContentTypeError) as json_err: _LOGGER.error(f"Invalid JSON {url}: {resp_text_short}"); raise ApiException(f"Invalid JSON: {resp_text_short}") from json_err
                if not response.ok and not resp_json: response.raise_for_status()
                return_value = resp_json.get("returnValue")
                if endpoint == URL_GET_SERVER_TIME and "data" in resp_json and "serverTime" in resp_json["data"]: return resp_json
                if return_value != 1:
                    msg = resp_json.get("msg", "Unknown"); _LOGGER.error(f"API Error {url}: RC={return_value}, Msg='{msg}'")
                    if return_value == 203 or response.status in [401, 403]: raise AuthException(f"Auth failed (RC={return_value}, HTTP={response.status}): {msg}")
                    raise ApiException(f"API error {msg} (RC={return_value})")
                return resp_json
        except asyncio.TimeoutError as exc: _LOGGER.error(f"Timeout {url}"); raise ApiException("Timeout") from exc
        except aiohttp.ClientResponseError as exc:
            if exc.status in [401, 403]: raise AuthException(f"Auth error ({exc.status}): {exc.message}") from exc
            _LOGGER.error(f"HTTP error {url}: {exc.status}"); raise ApiException(f"HTTP error: {exc.status}") from exc
        except aiohttp.ClientError as exc: _LOGGER.error(f"Client error {url}: {exc}"); raise ApiException(f"Client error: {exc}") from exc
        except AuthException: raise
        except ApiException: raise
        except Exception as exc: _LOGGER.exception(f"Unexpected HTTP error {url}"); raise ApiException(f"Unexpected: {exc}") from exc

    async def _get_server_time(self) -> Optional[int]:
        _LOGGER.debug("Fetching server time...")
        try:
            resp = await self._request("GET", URL_GET_SERVER_TIME, requires_auth=False)
            t = resp.get("data", {}).get("serverTime")
            return int(t) if t else None
        except Exception as e:
            _LOGGER.exception(f"Failed get server time: {e}")
            return None

    async def _get_token(self, device_id: str, server_time: int) -> Optional[str]:
        _LOGGER.debug(f"Requesting token {device_id} @ {server_time}")
        try:
            payload = {"deviceIds": device_id, "serverTime": str(server_time)}
            headers = {"source": "2", "Content-Type": "application/x-www-form-urlencoded"}
            resp = await self._request("POST", URL_SHARE_DEVICES, data=payload, extra_headers=headers, requires_auth=False)
            token = resp.get("data", {}).get("token")
            return token if token else None
        except Exception as e:
            _LOGGER.exception(f"Failed get token: {e}")
            return None

    async def authenticate_device(self, device_id: str) -> str:
        _LOGGER.info(f"Authenticating {device_id}"); last_exc: Optional[Exception] = None
        for attempt in range(AUTH_MAX_RETRIES):
            try:
                server_time = await self._get_server_time()
                if not server_time: raise ApiException("Failed to get server time for token request.")
                token = await self._get_token(device_id, server_time)
                if not token: raise AuthException(f"Failed get token (attempt {attempt+1})")
                _LOGGER.info(f"Auth success {device_id}"); self.set_token(token); return token
            except (ApiException, AuthException) as exc: _LOGGER.warning(f"Auth attempt {attempt+1} fail: {exc}"); last_exc = exc
            except Exception as exc: _LOGGER.exception(f"Unexpected auth err {attempt+1}"); last_exc = AuthException(f"Unexpected: {exc}")
            # Sleep only if not the last attempt
            if attempt < AUTH_MAX_RETRIES - 1: await asyncio.sleep(AUTH_RETRY_DELAY)

        _LOGGER.error(f"Auth failed after {AUTH_MAX_RETRIES} attempts.");
        if last_exc: raise last_exc
        else: raise AuthException("Auth failed (Unknown reason)")

    async def get_device_info(self, device_id: str) -> Dict[str, Any]:
        _LOGGER.debug(f"Fetching HTTP device info for ID: {device_id} using {URL_DEVICE_MANAGE}")
        if not device_id: _LOGGER.warning("Device ID missing."); return {"_error": "Device ID missing"}
        try:
            params = {"page": "1", "snName": device_id}
            response_json = await self._request("POST", URL_DEVICE_MANAGE, params=params, requires_auth=True)
            response_data = response_json.get("data", {})
            devices_list = response_data.get("devices") if isinstance(response_data, dict) else None
            if isinstance(devices_list, list) and len(devices_list) > 0:
                device_info_dict = devices_list[0]
                if isinstance(device_info_dict, dict):
                    _LOGGER.debug(f"Device info via HTTP ({URL_DEVICE_MANAGE}): {device_info_dict}")
                    _LOGGER.info(f"API Info: ID={device_info_dict.get('deviceId')}, Type={device_info_dict.get('deviceType')}, Ctrl={device_info_dict.get('controllerVersion')}, Lcd={device_info_dict.get('liquidCrystalVersion')}")
                    return device_info_dict
                else: _LOGGER.warning(f"Invalid data: {device_info_dict}"); return {"_error": "Invalid data format"}
            else: _LOGGER.warning(f"No devices list/empty {device_id}"); return {"_error": "Device not found or empty"}
        except (ApiException, AuthException) as exc: _LOGGER.error(f"Failed get info {device_id}: {exc}"); raise
        except Exception as exc: _LOGGER.exception(f"Unexpected get info {device_id}"); return {"_error": f"Unexpected: {exc}"}

    # --- SỬA HÀM NÀY ---
    async def get_daily_stats(self, device_identifier: str, query_date: str) -> Dict[str, Optional[float]]:
        _LOGGER.debug(f"Fetching daily stats {device_identifier} @ {query_date}")
        results: Dict[str, Optional[float]] = {
            "pv_today": None, "charge_today": None, "discharge_today": None,
            "grid_in_today": None, "load_today": None
        }
        base_params = {"deviceId": device_identifier, "queryDate": query_date}

        # Define API calls configuration
        api_calls_config = [
            {"url": URL_GET_PV_DAY_DATA, "data_key": "pv", "result_key": "pv_today"},
            {"url": URL_GET_BAT_DAY_DATA, "data_key": "bats", "result_key": ["charge_today", "discharge_today"]},
            {"url": URL_GET_OTHER_DAY_DATA, "data_key": ["grid", "homeload"], "result_key": ["grid_in_today", "load_today"]},
        ]

        # Loop through each API call configuration
        for config in api_calls_config:
            url = config["url"]
            data_key = config["data_key"]
            result_key = config["result_key"]

            try: # <<< Khối try bao quanh mỗi lệnh gọi API >>>
                resp = await self._request("GET", url, params=base_params, requires_auth=True)
                data = resp.get("data", {})

                # Process based on data_key type
                if isinstance(data_key, list): # Handle multiple keys (Other data)
                    for i, dk in enumerate(data_key):
                        item_data = data.get(dk, {})
                        val = item_data.get("tableValue")
                        rk = result_key[i]
                        if val is not None:
                             # Check if rk is a valid key before assigning
                            if rk in results:
                                results[rk] = float(val) / 10.0
                            else:
                                 _LOGGER.warning(f"Result key '{rk}' not defined in results dict.")
                elif data_key == "bats": # Handle battery list
                    bats_data = data.get(data_key, [])
                    if isinstance(bats_data, list):
                        rk_charge, rk_discharge = result_key[0], result_key[1]
                        if len(bats_data) > 0 and "tableValue" in bats_data[0]:
                             if rk_charge in results: results[rk_charge] = float(bats_data[0]["tableValue"]) / 10.0
                        if len(bats_data) > 1 and "tableValue" in bats_data[1]:
                             if rk_discharge in results: results[rk_discharge] = float(bats_data[1]["tableValue"]) / 10.0
                else: # Handle single key (PV data)
                    item_data = data.get(data_key, {})
                    val = item_data.get("tableValue")
                    # Ensure result_key is a string and exists in results
                    if isinstance(result_key, str) and result_key in results:
                         if val is not None: results[result_key] = float(val) / 10.0
                    else:
                         _LOGGER.warning(f"Result key '{result_key}' not valid or not defined.")

            # <<< Khối except tương ứng với try ở trên >>>
            except (ApiException, AuthException) as e:
                _LOGGER.warning(f"Failed {result_key} stats ({type(e).__name__}): {e}")
                # Don't raise here to allow other stats calls to proceed,
                # but if it's an Auth error, the coordinator should eventually fail.
                if isinstance(e, AuthException):
                     # Optionally raise immediately if auth failure should stop all stats
                     # raise
                     pass # Continue for now
            except Exception:
                _LOGGER.exception(f"Unexpected {result_key} stats error")

        _LOGGER.debug(f"Processed daily stats: {results}")
        return {k: v for k, v in results.items() if v is not None}