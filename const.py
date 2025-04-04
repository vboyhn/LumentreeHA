# /config/custom_components/lumentree/const.py
import logging
from typing import Final

DOMAIN: Final = "lumentree"
_LOGGER = logging.getLogger(__package__)

# --- HTTP API Constants ---
BASE_URL: Final = "https://lesvr.suntcn.com"
URL_LOGIN_TOURIST: Final = "/lesvr/shareDevices" # For Guest login
URL_DEVICE_INFO: Final = "/lesvr/deviceInfo" # To get detailed info (maybe SN)

DEFAULT_HEADERS: Final = {
    "versionCode": "100",
    "platform": "2",
    "wifiStatus": "1",
    "User-Agent": "okhttp/3.12.0",
    "Accept": "application/json, text/plain, */*"
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

AUTH_METHOD_GUEST: Final = "guest"

# --- Dispatcher Signal ---
SIGNAL_UPDATE_FORMAT: Final = f"{DOMAIN}_mqtt_update_{{device_sn}}"

# --- Register Addresses (Decimal, based on valueMap keys in Java) ---
REG_ADDR = {
    "TOTAL_PV_GEN_KWH": 0, # Suy đoán Gen Today từ setTotalData
    "TOTAL_ESSENTIAL_LOAD_KWH": 1,
    "TOTAL_GRID_INPUT_KWH": 2,
    "TOTAL_HOME_LOAD_KWH": 3,
    "TOTAL_BAT_CHARGE_KWH": 4,
    "TOTAL_BAT_DISCHARGE_KWH": 5,
    "BATTERY_VOLTAGE": 11,
    "BATTERY_CURRENT": 12,
    "AC_OUT_VOLTAGE": 13,
    "GRID_VOLTAGE": 15,
    "AC_OUT_FREQ": 16,
    "GRID_FREQ": 17, # Có trong initDataList nhưng không dùng?
    "AC_OUT_POWER": 18,
    "PV1_VOLTAGE": 20,
    "PV1_POWER": 22,
    "DEVICE_TEMP": 24,
    "BATTERY_MODE": 37, # 2 = No Battery?
    "BATTERY_SOC": 50,
    "UNKNOWN_53": 53, # Signed, check grid direction?
    "UNKNOWN_54": 54, # Signed, check grid direction?
    "AC_OUT_VA": 58,
    "GRID_POWER": 59, # Signed
    "BATTERY_POWER": 61, # Signed
    "LOAD_POWER": 67,
    "UPS_MODE": 68, # 0 = UPS Mode?
    "UNKNOWN_70": 70, # Signed, check P Chongji?
    "PV2_VOLTAGE": 72, # Chỉ có khi đặc biệt?
    "PV2_POWER": 74, # Chỉ có khi đặc biệt?
    "GENERATION_TOTAL": 90, # Địa chỉ bắt đầu cho 32-bit
}

# --- Entity Keys (Should match keys returned by parser.py) ---
# Binary Sensor Keys
KEY_ONLINE_STATUS: Final = "online_status"
# Thêm KEY cho UPS Mode nếu muốn
KEY_IS_UPS_MODE: Final = "is_ups_mode"

# Sensor Keys
KEY_PV_POWER: Final = "pv_power" # Tổng PV1 + PV2
KEY_BATTERY_POWER: Final = "battery_power" # Giá trị tuyệt đối
KEY_BATTERY_SOC: Final = "battery_soc"
KEY_GRID_POWER: Final = "grid_power" # Có dấu
KEY_LOAD_POWER: Final = "load_power"
KEY_GENERATION_TODAY: Final = "generation_today" # Map từ Reg 0?
KEY_GENERATION_TOTAL: Final = "generation_total" # 32-bit từ Reg 90
KEY_BATTERY_VOLTAGE: Final = "battery_voltage"
KEY_BATTERY_CURRENT: Final = "battery_current" # Có dấu
KEY_AC_OUT_VOLTAGE: Final = "ac_output_voltage"
KEY_GRID_VOLTAGE: Final = "grid_voltage"
KEY_AC_OUT_FREQ: Final = "ac_output_frequency"
# KEY_GRID_FREQ: Final = "grid_frequency" # Có thể thêm nếu cần
KEY_AC_OUT_POWER: Final = "ac_output_power"
KEY_AC_OUT_VA: Final = "ac_output_va"
KEY_DEVICE_TEMP: Final = "device_temperature"
KEY_PV1_VOLTAGE: Final = "pv1_voltage"
KEY_PV1_POWER: Final = "pv1_power"
KEY_PV2_VOLTAGE: Final = "pv2_voltage"
KEY_PV2_POWER: Final = "pv2_power"
# Các Key tổng KWh nếu muốn tách riêng
KEY_TOTAL_PV_GEN_KWH: Final = "total_pv_gen_kwh"
KEY_TOTAL_BAT_CHARGE_KWH: Final = "total_bat_charge_kwh"
KEY_TOTAL_BAT_DISCHARGE_KWH: Final = "total_bat_discharge_kwh"
KEY_TOTAL_GRID_INPUT_KWH: Final = "total_grid_input_kwh"
KEY_TOTAL_HOME_LOAD_KWH: Final = "total_home_load_kwh"

# Debug Key
KEY_LAST_RAW_MQTT: Final = "last_raw_mqtt_hex"