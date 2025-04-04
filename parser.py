# /config/custom_components/lumentree/parser.py

from typing import Optional, Dict, Any, Tuple, List
import logging # <<< THÊM IMPORT LOGGING Ở ĐÂY
import struct

# --- Cố gắng import thư viện và const ---
try:
    import crcmod.predefined
    crc16_modbus_func = crcmod.predefined.mkCrcFun('modbus')
    # Lấy logger từ component gốc nếu được
    try: _LOGGER = logging.getLogger(__package__)
    except NameError: _LOGGER = logging.getLogger(__name__) # Fallback nếu __package__ không tồn tại
    _LOGGER.info("Using crcmod 'modbus' function for CRC check.")
    from .const import (
         REG_ADDR, KEY_ONLINE_STATUS, KEY_PV_POWER, KEY_BATTERY_POWER, KEY_BATTERY_SOC,
        KEY_GRID_POWER, KEY_LOAD_POWER, KEY_GENERATION_TODAY, KEY_GENERATION_TOTAL,
        KEY_BATTERY_VOLTAGE, KEY_BATTERY_CURRENT, KEY_AC_OUT_VOLTAGE, KEY_GRID_VOLTAGE,
        KEY_AC_OUT_FREQ, KEY_AC_OUT_POWER, KEY_AC_OUT_VA, KEY_DEVICE_TEMP,
        KEY_PV1_VOLTAGE, KEY_PV1_POWER, KEY_PV2_VOLTAGE, KEY_PV2_POWER,
        KEY_IS_UPS_MODE, KEY_TOTAL_PV_GEN_KWH, KEY_TOTAL_BAT_CHARGE_KWH,
        KEY_TOTAL_BAT_DISCHARGE_KWH, KEY_TOTAL_GRID_INPUT_KWH, KEY_TOTAL_HOME_LOAD_KWH
    )
except ImportError:
    _LOGGER = logging.getLogger(__name__) # Đảm bảo logger được định nghĩa
    crc16_modbus_func = None
    _LOGGER.warning("Could not import component logger/const or crcmod library. Using fallback values. CRC check might be skipped.")
    REG_ADDR = {"BATTERY_SOC": 50, "GRID_POWER": 59, "BATTERY_POWER": 61, "LOAD_POWER": 67, "GENERATION_TOTAL": 90, "BATTERY_VOLTAGE": 11, "BATTERY_CURRENT": 12, "AC_OUT_VOLTAGE": 13, "GRID_VOLTAGE": 15, "AC_OUT_FREQ": 16, "AC_OUT_POWER": 18, "PV1_VOLTAGE": 20, "PV1_POWER": 22, "DEVICE_TEMP": 24, "PV2_VOLTAGE": 72, "PV2_POWER": 74, "AC_OUT_VA": 58, "UPS_MODE": 68, "TOTAL_PV_GEN_KWH": 0, "TOTAL_BAT_CHARGE_KWH": 4, "TOTAL_BAT_DISCHARGE_KWH": 5, "TOTAL_GRID_INPUT_KWH": 2, "TOTAL_HOME_LOAD_KWH": 3}
    KEY_ONLINE_STATUS="online_status"; KEY_PV_POWER="pv_power"; KEY_BATTERY_POWER="battery_power"; KEY_BATTERY_SOC="battery_soc"; KEY_GRID_POWER="grid_power"; KEY_LOAD_POWER="load_power"; KEY_GENERATION_TODAY="generation_today"; KEY_GENERATION_TOTAL="generation_total"; KEY_BATTERY_VOLTAGE="battery_voltage"; KEY_BATTERY_CURRENT="battery_current"; KEY_AC_OUT_VOLTAGE="ac_output_voltage"; KEY_GRID_VOLTAGE="grid_voltage"; KEY_AC_OUT_FREQ="ac_output_frequency"; KEY_AC_OUT_POWER="ac_output_power"; KEY_AC_OUT_VA="ac_output_va"; KEY_DEVICE_TEMP="device_temperature"; KEY_PV1_VOLTAGE="pv1_voltage"; KEY_PV1_POWER="pv1_power"; KEY_PV2_VOLTAGE="pv2_voltage"; KEY_PV2_POWER="pv2_power"; KEY_IS_UPS_MODE="is_ups_mode"; KEY_TOTAL_PV_GEN_KWH="total_pv_gen_kwh"; KEY_TOTAL_BAT_CHARGE_KWH="total_bat_charge_kwh"; KEY_TOTAL_BAT_DISCHARGE_KWH="total_bat_discharge_kwh"; KEY_TOTAL_GRID_INPUT_KWH="total_grid_input_kwh"; KEY_TOTAL_HOME_LOAD_KWH="total_home_load_kwh"
except KeyError:
    _LOGGER = logging.getLogger(__package__) if '__package__' in globals() else logging.getLogger(__name__)
    crc16_modbus_func = None
    _LOGGER.warning("crcmod 'modbus' definition not found. CRC check will be skipped.")
    REG_ADDR = {"BATTERY_SOC": 50, "GRID_POWER": 59, "BATTERY_POWER": 61, "LOAD_POWER": 67, "GENERATION_TOTAL": 90, "BATTERY_VOLTAGE": 11, "BATTERY_CURRENT": 12, "AC_OUT_VOLTAGE": 13, "GRID_VOLTAGE": 15, "AC_OUT_FREQ": 16, "AC_OUT_POWER": 18, "PV1_VOLTAGE": 20, "PV1_POWER": 22, "DEVICE_TEMP": 24, "PV2_VOLTAGE": 72, "PV2_POWER": 74, "AC_OUT_VA": 58, "UPS_MODE": 68, "TOTAL_PV_GEN_KWH": 0, "TOTAL_BAT_CHARGE_KWH": 4, "TOTAL_BAT_DISCHARGE_KWH": 5, "TOTAL_GRID_INPUT_KWH": 2, "TOTAL_HOME_LOAD_KWH": 3}
    KEY_ONLINE_STATUS="online_status"; KEY_PV_POWER="pv_power"; KEY_BATTERY_POWER="battery_power"; KEY_BATTERY_SOC="battery_soc"; KEY_GRID_POWER="grid_power"; KEY_LOAD_POWER="load_power"; KEY_GENERATION_TODAY="generation_today"; KEY_GENERATION_TOTAL="generation_total"; KEY_BATTERY_VOLTAGE="battery_voltage"; KEY_BATTERY_CURRENT="battery_current"; KEY_AC_OUT_VOLTAGE="ac_output_voltage"; KEY_GRID_VOLTAGE="grid_voltage"; KEY_AC_OUT_FREQ="ac_output_frequency"; KEY_AC_OUT_POWER="ac_output_power"; KEY_AC_OUT_VA="ac_output_va"; KEY_DEVICE_TEMP="device_temperature"; KEY_PV1_VOLTAGE="pv1_voltage"; KEY_PV1_POWER="pv1_power"; KEY_PV2_VOLTAGE="pv2_voltage"; KEY_PV2_POWER="pv2_power"; KEY_IS_UPS_MODE="is_ups_mode"; KEY_TOTAL_PV_GEN_KWH="total_pv_gen_kwh"; KEY_TOTAL_BAT_CHARGE_KWH="total_bat_charge_kwh"; KEY_TOTAL_BAT_DISCHARGE_KWH="total_bat_discharge_kwh"; KEY_TOTAL_GRID_INPUT_KWH="total_grid_input_kwh"; KEY_TOTAL_HOME_LOAD_KWH="total_home_load_kwh"


def calculate_crc16_modbus(payload_bytes: bytes) -> Optional[int]:
    if crc16_modbus_func:
        try: return crc16_modbus_func(payload_bytes)
        except Exception as e: _LOGGER.error(f"Error calculating MODBUS CRC: {e}"); return None
    return None

def verify_crc(payload_hex: str) -> Tuple[bool, Optional[str]]:
    if len(payload_hex) < 4: return False, None
    data_hex = payload_hex[:-4]; crc_hex_received = payload_hex[-4:]
    try: data_bytes = bytes.fromhex(data_hex); received_crc_bytes = bytes.fromhex(crc_hex_received)
    except ValueError: return False, None
    calculated_crc = calculate_crc16_modbus(data_bytes)
    if calculated_crc is None: return True, data_hex
    calculated_crc_bytes_le = calculated_crc.to_bytes(2, byteorder='little')
    is_valid = (received_crc_bytes == calculated_crc_bytes_le)
    _LOGGER.debug(f"MODBUS CRC Check: Valid={is_valid}")
    return is_valid, data_hex if is_valid else None

# --- HÀM TẠO LỆNH ĐỌC MODBUS ---
def generate_modbus_read_command(slave_id: int, func_code: int, start_addr: int, num_registers: int) -> Optional[str]:
    """Generates a Modbus read command hex string with CRC16-MODBUS."""
    if not (0 <= start_addr <= 65535 and 1 <= num_registers <= 125): return None
    pdu_hex = f"{func_code:02X}{start_addr:04X}{num_registers:04X}"
    adu_hex_no_crc = f"{slave_id:02X}{pdu_hex}"
    try:
        adu_bytes_no_crc = bytes.fromhex(adu_hex_no_crc)
        crc_int = calculate_crc16_modbus(adu_bytes_no_crc)
        if crc_int is None: return None
        crc_bytes_le = crc_int.to_bytes(2, byteorder='little')
        command_hex = adu_hex_no_crc + crc_bytes_le.hex()
        _LOGGER.debug(f"Generated Modbus command: {command_hex.upper()}")
        return command_hex.upper()
    except Exception as e: _LOGGER.error(f"Error generating Modbus command: {e}"); return None
# --- KẾT THÚC HÀM TẠO LỆNH ĐỌC ---

def parse_mqtt_payload(payload_hex: str) -> Optional[Dict[str, Any]]:
    """Parses the custom hex payload from MQTT."""
    _LOGGER.debug(f"Attempting to parse payload hex (len={len(payload_hex)}): {payload_hex[:60]}...")
    parsed_data: Dict[str, Any] = {}
    if payload_hex.startswith("2010") or payload_hex.startswith("43") or payload_hex == "06": return None
    if payload_hex.startswith("0103") or payload_hex.startswith("0104"):
        separator_hex = "2b2b2b2b" # "++++"
        if separator_hex in payload_hex:
            try:
                parts = payload_hex.split(separator_hex)
                if len(parts) == 2:
                    response_with_crc_hex = parts[1]
                    if (response_with_crc_hex.startswith("0103") or response_with_crc_hex.startswith("0104")) and len(response_with_crc_hex) >= 10:
                        byte_count_hex = response_with_crc_hex[4:6]
                        byte_count = int(byte_count_hex, 16)
                        expected_data_hex_len = byte_count * 2
                        expected_total_len = 6 + expected_data_hex_len + 4
                        if len(response_with_crc_hex) != expected_total_len: return None
                        crc_valid, _ = verify_crc(response_with_crc_hex)
                        if not crc_valid: return None
                        data_start_index = 6
                        data_end_index = data_start_index + expected_data_hex_len
                        data_hex = response_with_crc_hex[data_start_index : data_end_index]
                        data_bytes = bytes.fromhex(data_hex)
                        if len(data_bytes) != byte_count: return None
                        _LOGGER.debug(f"MODBUS CRC OK. Parsing {byte_count} data bytes...")
                        def read_reg_signed_short(reg_addr: int, factor: float = 1.0) -> Optional[float]:
                            offset_bytes = reg_addr * 2
                            try:
                                if offset_bytes + 2 <= len(data_bytes):
                                    raw_val = struct.unpack('>h', data_bytes[offset_bytes:offset_bytes+2])[0]
                                    return round(raw_val * factor, 2)
                                return None
                            except: return None
                        def read_reg_unsigned_short(reg_addr: int, factor: float = 1.0) -> Optional[float]:
                            offset_bytes = reg_addr * 2
                            try:
                                if offset_bytes + 2 <= len(data_bytes):
                                    raw_val = struct.unpack('>H', data_bytes[offset_bytes:offset_bytes+2])[0]
                                    return round(raw_val * factor, 2)
                                return None
                            except: return None
                        def read_reg_unsigned_int32(reg_addr: int, factor: float = 1.0) -> Optional[float]:
                            offset_bytes = reg_addr * 2
                            try:
                                if offset_bytes + 4 <= len(data_bytes):
                                    raw_val = struct.unpack('>I', data_bytes[offset_bytes:offset_bytes+4])[0]
                                    return round(raw_val * factor, 2)
                                return None
                            except: return None
                        addr = REG_ADDR
                        val = read_reg_unsigned_short(addr["BATTERY_VOLTAGE"], 0.01); parsed_data[KEY_BATTERY_VOLTAGE] = val
                        val = read_reg_signed_short(addr["BATTERY_CURRENT"], 0.01); parsed_data[KEY_BATTERY_CURRENT] = -val if val is not None else None
                        val = read_reg_unsigned_short(addr["AC_OUT_VOLTAGE"], 0.1); parsed_data[KEY_AC_OUT_VOLTAGE] = val
                        val = read_reg_unsigned_short(addr["GRID_VOLTAGE"], 0.1); parsed_data[KEY_GRID_VOLTAGE] = val
                        val = read_reg_unsigned_short(addr["AC_OUT_FREQ"], 0.01); parsed_data[KEY_AC_OUT_FREQ] = val
                        val = read_reg_signed_short(addr["DEVICE_TEMP"], 0.1); parsed_data[KEY_DEVICE_TEMP] = val
                        val = read_reg_unsigned_short(addr["PV1_VOLTAGE"]); parsed_data[KEY_PV1_VOLTAGE] = val
                        val = read_reg_unsigned_short(addr["PV2_VOLTAGE"]); parsed_data[KEY_PV2_VOLTAGE] = val
                        val_grid = read_reg_signed_short(addr["GRID_POWER"]); parsed_data[KEY_GRID_POWER] = val_grid
                        val_load = read_reg_unsigned_short(addr["LOAD_POWER"]); parsed_data[KEY_LOAD_POWER] = val_load
                        val_ac_out = read_reg_unsigned_short(addr["AC_OUT_POWER"]); parsed_data[KEY_AC_OUT_POWER] = val_ac_out
                        val_ac_out_va = read_reg_unsigned_short(addr["AC_OUT_VA"]); parsed_data[KEY_AC_OUT_VA] = val_ac_out_va
                        val_bat_signed = read_reg_signed_short(addr["BATTERY_POWER"]); parsed_data[KEY_BATTERY_POWER] = abs(val_bat_signed) if val_bat_signed is not None else None
                        pv1_power = read_reg_unsigned_short(addr["PV1_POWER"])
                        pv2_power = read_reg_unsigned_short(addr["PV2_POWER"])
                        pv_power = (pv1_power or 0) + (pv2_power or 0)
                        parsed_data[KEY_PV_POWER] = pv_power if pv1_power is not None or pv2_power is not None else None
                        val_soc = read_reg_unsigned_short(addr["BATTERY_SOC"]); parsed_data[KEY_BATTERY_SOC] = max(0, min(100, int(val_soc))) if val_soc is not None else None
                        val_ups = read_reg_unsigned_short(addr["UPS_MODE"]); parsed_data[KEY_IS_UPS_MODE] = (val_ups == 0) if val_ups is not None else None
                        val = read_reg_unsigned_short(addr["TOTAL_PV_GEN_KWH"], 0.1); parsed_data[KEY_GENERATION_TODAY] = val
                        val = read_reg_unsigned_int32(addr["GENERATION_TOTAL"], 0.1); parsed_data[KEY_GENERATION_TOTAL] = val
                        val = read_reg_unsigned_short(addr["TOTAL_BAT_CHARGE_KWH"], 0.1); parsed_data[KEY_TOTAL_BAT_CHARGE_KWH] = val
                        val = read_reg_unsigned_short(addr["TOTAL_BAT_DISCHARGE_KWH"], 0.1); parsed_data[KEY_TOTAL_BAT_DISCHARGE_KWH] = val
                        val = read_reg_unsigned_short(addr["TOTAL_GRID_INPUT_KWH"], 0.1); parsed_data[KEY_TOTAL_GRID_INPUT_KWH] = val
                        val = read_reg_unsigned_short(addr["TOTAL_HOME_LOAD_KWH"], 0.1); parsed_data[KEY_TOTAL_HOME_LOAD_KWH] = val
                        parsed_data = {k: v for k, v in parsed_data.items() if v is not None}
                        _LOGGER.debug(f"Parsed data dict: {parsed_data}")
                    else: return None
                else: return None
            except ValueError as e: _LOGGER.error(f"Value error during hex/int conversion: {e}"); return None
            except Exception as e: _LOGGER.exception(f"Error parsing payload structure: {e}"); return None
        else: return None
    else: return None
    if parsed_data: parsed_data[KEY_ONLINE_STATUS] = True; _LOGGER.info(f"++++ PARSING SUCCESSFUL: Parsed {len(parsed_data)} data points. ++++"); return parsed_data
    else: _LOGGER.warning(f"No relevant data could be parsed from payload: {payload_hex[:60]}..."); return None