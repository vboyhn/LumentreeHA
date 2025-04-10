# /config/custom_components/lumentree/const.py# /config/custom_components/lumentree/const.py
import logging
from typing import Final

DOMAIN: Final = "lumentree"
_LOGGER = logging.getLogger(__package__)

# --- HTTP API Constants ---
BASE_URL: Final = "http://lesvr.suntcn.com" # Giữ HTTP
# URL_LOGIN_TOURIST: Final = "/lesvr/shareDevices" # Bỏ URL này, dùng shareDevices cho Device ID
URL_GET_SERVER_TIME: Final = "/lesvr/getServerTime" # <<< THÊM URL LẤY SERVER TIME
URL_SHARE_DEVICES: Final = "/lesvr/shareDevices" # <<< URL LẤY TOKEN TỪ DEVICE ID
# URL_DEVICE_INFO: Final = "/lesvr/deviceInfo" # <<< Bỏ URL GET cũ
URL_GET_DEVICE: Final = "/lesvr/getDevice" # <<< SỬ DỤNG URL POST NÀY CHO DEVICE INFO
URL_GET_OTHER_DAY_DATA = "/lesvr/getOtherDayData"
URL_GET_PV_DAY_DATA = "/lesvr/getPVDayData"
URL_GET_BAT_DAY_DATA = "/lesvr/getBatDayData"

# Headers dùng chung ít hơn, quản lý trong từng request
DEFAULT_HEADERS: Final = {
    "versionCode": "1.6.3", # <<< CẬP NHẬT VERSION CODE GIỐNG C#
    "platform": "2",
    "wifiStatus": "1",
    # User-Agent và Accept sẽ thêm trong request nếu cần
}

# --- MQTT Constants ---
MQTT_BROKER: Final = "lesvr.suntcn.com"
MQTT_PORT: Final = 1886
MQTT_USERNAME: Final = "appuser"
MQTT_PASSWORD: Final = "app666"
MQTT_KEEPALIVE: Final = 20
MQTT_SUB_TOPIC_FORMAT: Final = "reportApp/{device_sn}"
MQTT_PUB_TOPIC_FORMAT: Final = "listenApp/{device_sn}"
MQTT_CLIENT_ID_FORMAT: Final = "android-{user_id}-{timestamp}"

# --- Configuration Keys ---
# CONF_AUTH_METHOD: Final = "auth_method" # Không cần thiết nữa nếu chỉ có 1 cách
# CONF_QR_CONTENT: Final = "qr_content" # Bỏ key QR
CONF_DEVICE_ID: Final = "device_id" # <<< KEY QUAN TRỌNG: ID NHẬP VÀO (vd: P...)
CONF_DEVICE_SN: Final = "device_sn" # <<< KEY QUAN TRỌNG: SN LẤY TỪ API
CONF_DEVICE_NAME: Final = "device_name"
CONF_USER_ID: Final = "user_id" # UID lấy từ shareDevices response
CONF_HTTP_TOKEN: Final = "http_token" # Key lưu token HTTP

# AUTH_METHOD_GUEST: Final = "guest" # Bỏ

# --- Polling and Timeout ---
DEFAULT_POLLING_INTERVAL = 5 # Giây (MQTT Real-time)
DEFAULT_STATS_INTERVAL = 1800 # Giây (30 phút cho HTTP Stats) <<< Tăng lên 30 phút
HTTPS_PING_TIMEOUT = 5 # Giây (Không còn dùng trong init nhưng giữ lại const)

# --- Dispatcher Signal ---
SIGNAL_UPDATE_FORMAT: Final = f"{DOMAIN}_mqtt_update_{{device_sn}}" # Signal cho MQTT
SIGNAL_STATS_UPDATE_FORMAT: Final = f"{DOMAIN}_stats_update_{{device_sn}}" # Signal cho HTTP Stats (dùng SN làm key)

# --- Register Addresses (MQTT Real-time) ---
# (Giữ nguyên)
REG_ADDR = {
    "BATTERY_VOLTAGE": 11, "BATTERY_CURRENT": 12, "AC_OUT_VOLTAGE": 13,
    "GRID_VOLTAGE": 15, "AC_OUT_FREQ": 16, "AC_OUT_POWER": 18,
    "PV1_VOLTAGE": 20, "PV1_POWER": 22, "DEVICE_TEMP": 24,
    "BATTERY_SOC": 50, "AC_OUT_VA": 58, "GRID_POWER": 59,
    "BATTERY_POWER": 61, "LOAD_POWER": 67, "UPS_MODE": 68,
    "PV2_VOLTAGE": 72, "PV2_POWER": 74,
}

# --- Entity Keys ---
# (Giữ nguyên)
# Binary Sensor
KEY_ONLINE_STATUS: Final = "online_status"
KEY_IS_UPS_MODE: Final = "is_ups_mode"
# Sensor Tức thời (Từ MQTT)
KEY_PV_POWER: Final = "pv_power"
KEY_BATTERY_POWER: Final = "battery_power"
KEY_BATTERY_SOC: Final = "battery_soc"
KEY_GRID_POWER: Final = "grid_power"
KEY_LOAD_POWER: Final = "load_power"
KEY_BATTERY_VOLTAGE: Final = "battery_voltage"
KEY_BATTERY_CURRENT: Final = "battery_current"
KEY_AC_OUT_VOLTAGE: Final = "ac_output_voltage"
KEY_GRID_VOLTAGE: Final = "grid_voltage"
KEY_AC_OUT_FREQ: Final = "ac_output_frequency"
KEY_AC_OUT_POWER: Final = "ac_output_power"
KEY_AC_OUT_VA: Final = "ac_output_va"
KEY_DEVICE_TEMP: Final = "device_temperature"
KEY_PV1_VOLTAGE: Final = "pv1_voltage"
KEY_PV1_POWER: Final = "pv1_power"
KEY_PV2_VOLTAGE: Final = "pv2_voltage"
KEY_PV2_POWER: Final = "pv2_power"
# Sensor Thống kê Ngày (Từ HTTP API - Key này phải khớp key trong coordinator_stats.py)
KEY_DAILY_PV_KWH: Final = "pv_today"
KEY_DAILY_CHARGE_KWH: Final = "charge_today"
KEY_DAILY_DISCHARGE_KWH: Final = "discharge_today"
KEY_DAILY_GRID_IN_KWH: Final = "grid_in_today"
KEY_DAILY_LOAD_KWH: Final = "load_today"
# Debug Key
KEY_LAST_RAW_MQTT: Final = "last_raw_mqtt_hex"
import logging
from typing import Final

DOMAIN: Final = "lumentree"
_LOGGER = logging.getLogger(__package__)

# --- HTTP API Constants ---
# BASE_URL: Final = "https://lesvr.suntcn.com" # Dòng cũ
BASE_URL: Final = "http://lesvr.suntcn.com" # <<< SỬA THÀNH HTTP
URL_LOGIN_TOURIST: Final = "/lesvr/shareDevices"
URL_DEVICE_INFO: Final = "/lesvr/deviceInfo"
URL_GET_OTHER_DAY_DATA = "/lesvr/getOtherDayData"
URL_GET_PV_DAY_DATA = "/lesvr/getPVDayData"
URL_GET_BAT_DAY_DATA = "/lesvr/getBatDayData"

DEFAULT_HEADERS: Final = {
    "versionCode": "1.7.0", "platform": "2", "wifiStatus": "1",
    "User-Agent": "okhttp/3.12.0", "Accept": "application/json, text/plain, */*"
}

# --- MQTT Constants ---
MQTT_BROKER: Final = "lesvr.suntcn.com"
MQTT_PORT: Final = 1886
MQTT_USERNAME: Final = "appuser"
MQTT_PASSWORD: Final = "app666"
MQTT_KEEPALIVE: Final = 20
MQTT_SUB_TOPIC_FORMAT: Final = "reportApp/{device_sn}"
MQTT_PUB_TOPIC_FORMAT: Final = "listenApp/{device_sn}"
MQTT_CLIENT_ID_FORMAT: Final = "android-{user_id}-{timestamp}"

# --- Configuration Keys ---
CONF_AUTH_METHOD: Final = "auth_method"
CONF_QR_CONTENT: Final = "qr_content"
CONF_DEVICE_ID: Final = "device_id"
CONF_DEVICE_SN: Final = "device_sn"
CONF_DEVICE_NAME: Final = "device_name"
CONF_USER_ID: Final = "user_id"
CONF_HTTP_TOKEN: Final = "http_token" # Key lưu token HTTP

AUTH_METHOD_GUEST: Final = "guest"

# --- Polling and Timeout ---
DEFAULT_POLLING_INTERVAL = 5 # Giây (MQTT Real-time)
DEFAULT_STATS_INTERVAL = 30 # Giây (30 phút cho HTTP Stats)
HTTPS_PING_TIMEOUT = 5 # Giây (Không còn dùng trong init nhưng giữ lại const)

# --- Dispatcher Signal ---
SIGNAL_UPDATE_FORMAT: Final = f"{DOMAIN}_mqtt_update_{{device_sn}}" # Signal cho MQTT
SIGNAL_STATS_UPDATE_FORMAT: Final = f"{DOMAIN}_stats_update_{{device_sn}}" # Signal cho HTTP Stats

# --- Register Addresses (MQTT Real-time) ---
# (Chỉ chứa các thanh ghi tức thời đã xác nhận)
REG_ADDR = {
    "BATTERY_VOLTAGE": 11, "BATTERY_CURRENT": 12, "AC_OUT_VOLTAGE": 13,
    "GRID_VOLTAGE": 15, "AC_OUT_FREQ": 16, "AC_OUT_POWER": 18,
    "PV1_VOLTAGE": 20, "PV1_POWER": 22, "DEVICE_TEMP": 24,
    "BATTERY_SOC": 50, "AC_OUT_VA": 58, "GRID_POWER": 59,
    "BATTERY_POWER": 61, "LOAD_POWER": 67, "UPS_MODE": 68,
    "PV2_VOLTAGE": 72, "PV2_POWER": 74,
}

# --- Entity Keys ---
# Binary Sensor
KEY_ONLINE_STATUS: Final = "online_status"
KEY_IS_UPS_MODE: Final = "is_ups_mode"
# Sensor Tức thời (Từ MQTT)
KEY_PV_POWER: Final = "pv_power"
KEY_BATTERY_POWER: Final = "battery_power"
KEY_BATTERY_SOC: Final = "battery_soc"
KEY_GRID_POWER: Final = "grid_power"
KEY_LOAD_POWER: Final = "load_power"
KEY_BATTERY_VOLTAGE: Final = "battery_voltage"
KEY_BATTERY_CURRENT: Final = "battery_current"
KEY_AC_OUT_VOLTAGE: Final = "ac_output_voltage"
KEY_GRID_VOLTAGE: Final = "grid_voltage"
KEY_AC_OUT_FREQ: Final = "ac_output_frequency"
KEY_AC_OUT_POWER: Final = "ac_output_power"
KEY_AC_OUT_VA: Final = "ac_output_va"
KEY_DEVICE_TEMP: Final = "device_temperature"
KEY_PV1_VOLTAGE: Final = "pv1_voltage"
KEY_PV1_POWER: Final = "pv1_power"
KEY_PV2_VOLTAGE: Final = "pv2_voltage"
KEY_PV2_POWER: Final = "pv2_power"
# Sensor Thống kê Ngày (Từ HTTP API - Key này phải khớp key trong coordinator_stats.py)
KEY_DAILY_PV_KWH: Final = "pv_today"
KEY_DAILY_CHARGE_KWH: Final = "charge_today"
KEY_DAILY_DISCHARGE_KWH: Final = "discharge_today"
KEY_DAILY_GRID_IN_KWH: Final = "grid_in_today"
KEY_DAILY_LOAD_KWH: Final = "load_today"
# Debug Key
KEY_LAST_RAW_MQTT: Final = "last_raw_mqtt_hex"
