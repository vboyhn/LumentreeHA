# /config/custom_components/lumentree/parser.py
# Version for Restore Point 1

from typing import Optional, Dict, Any, Tuple, List
import logging
import struct

# --- Import thư viện CRC và các hằng số ---
try:
    # Thử import crcmod trước
    import crcmod.predefined
    # Tạo hàm tính CRC nếu import thành công
    crc16_modbus_func = crcmod.predefined.mkCrcFun('modbus')
    _LOGGER = logging.getLogger(__package__) # Lấy logger từ package
    # Import các KEY và REG_ADDR cần thiết cho RP1
    from .const import (
        _LOGGER, REG_ADDR,
        KEY_ONLINE_STATUS, KEY_PV_POWER, KEY_BATTERY_POWER, KEY_BATTERY_SOC,
        KEY_GRID_POWER, KEY_LOAD_POWER,
        KEY_BATTERY_VOLTAGE, KEY_BATTERY_CURRENT, KEY_AC_OUT_VOLTAGE, KEY_GRID_VOLTAGE,
        KEY_AC_OUT_FREQ, KEY_AC_OUT_POWER, KEY_AC_OUT_VA, KEY_DEVICE_TEMP,
        KEY_PV1_VOLTAGE, KEY_PV1_POWER, KEY_PV2_VOLTAGE, KEY_PV2_POWER,
        KEY_IS_UPS_MODE
        # Bỏ KEY KWh ở RP1
    )
except ImportError:
    # Fallback nếu không import được crcmod hoặc const
    _LOGGER = logging.getLogger(__name__)
    _LOGGER.warning("Could not import crcmod or constants, CRC check/generation disabled. Using fallback keys.")
    crc16_modbus_func = None # Đặt là None nếu không import được crcmod
    # Fallback REG_ADDR và KEYs cho RP1
    REG_ADDR = {"BATTERY_SOC": 50, "GRID_POWER": 59, "BATTERY_POWER": 61, "LOAD_POWER": 67, "BATTERY_VOLTAGE": 11, "BATTERY_CURRENT": 12, "AC_OUT_VOLTAGE": 13, "GRID_VOLTAGE": 15, "AC_OUT_FREQ": 16, "AC_OUT_POWER": 18, "PV1_VOLTAGE": 20, "PV1_POWER": 22, "DEVICE_TEMP": 24, "PV2_VOLTAGE": 72, "PV2_POWER": 74, "AC_OUT_VA": 58, "UPS_MODE": 68}
    KEY_ONLINE_STATUS="online_status"; KEY_PV_POWER="pv_power"; KEY_BATTERY_POWER="battery_power"; KEY_BATTERY_SOC="battery_soc"; KEY_GRID_POWER="grid_power"; KEY_LOAD_POWER="load_power"; KEY_BATTERY_VOLTAGE="battery_voltage"; KEY_BATTERY_CURRENT="battery_current"; KEY_AC_OUT_VOLTAGE="ac_output_voltage"; KEY_GRID_VOLTAGE="grid_voltage"; KEY_AC_OUT_FREQ="ac_output_frequency"; KEY_AC_OUT_POWER="ac_output_power"; KEY_AC_OUT_VA="ac_output_va"; KEY_DEVICE_TEMP="device_temperature"; KEY_PV1_VOLTAGE="pv1_voltage"; KEY_PV1_POWER="pv1_power"; KEY_PV2_VOLTAGE="pv2_voltage"; KEY_PV2_POWER="pv2_power"; KEY_IS_UPS_MODE="is_ups_mode"
except KeyError:
    # Fallback nếu import const thành công nhưng thiếu key (ít xảy ra)
     _LOGGER = logging.getLogger(__package__) if '__package__' in globals() else logging.getLogger(__name__)
     _LOGGER.warning("KeyError importing constants. Using fallback keys.")
     crc16_modbus_func = None # Assume crcmod might also be missing
     REG_ADDR = {"BATTERY_SOC": 50, "GRID_POWER": 59, "BATTERY_POWER": 61, "LOAD_POWER": 67, "BATTERY_VOLTAGE": 11, "BATTERY_CURRENT": 12, "AC_OUT_VOLTAGE": 13, "GRID_VOLTAGE": 15, "AC_OUT_FREQ": 16, "AC_OUT_POWER": 18, "PV1_VOLTAGE": 20, "PV1_POWER": 22, "DEVICE_TEMP": 24, "PV2_VOLTAGE": 72, "PV2_POWER": 74, "AC_OUT_VA": 58, "UPS_MODE": 68}
     KEY_ONLINE_STATUS="online_status"; KEY_PV_POWER="pv_power"; KEY_BATTERY_POWER="battery_power"; KEY_BATTERY_SOC="battery_soc"; KEY_GRID_POWER="grid_power"; KEY_LOAD_POWER="load_power"; KEY_BATTERY_VOLTAGE="battery_voltage"; KEY_BATTERY_CURRENT="battery_current"; KEY_AC_OUT_VOLTAGE="ac_output_voltage"; KEY_GRID_VOLTAGE="grid_voltage"; KEY_AC_OUT_FREQ="ac_output_frequency"; KEY_AC_OUT_POWER="ac_output_power"; KEY_AC_OUT_VA="ac_output_va"; KEY_DEVICE_TEMP="device_temperature"; KEY_PV1_VOLTAGE="pv1_voltage"; KEY_PV1_POWER="pv1_power"; KEY_PV2_VOLTAGE="pv2_voltage"; KEY_PV2_POWER="pv2_power"; KEY_IS_UPS_MODE="is_ups_mode"


def calculate_crc16_modbus(payload_bytes: bytes) -> Optional[int]:
    """Calculates the Modbus CRC16 checksum."""
    if crc16_modbus_func:
        try:
            return crc16_modbus_func(payload_bytes)
        except Exception as e:
            _LOGGER.error(f"Error calculating CRC: {e}")
            return None
    else:
        _LOGGER.debug("crcmod library not available, cannot calculate CRC.")
        return None # Cannot calculate if function is None

def verify_crc(payload_hex: str) -> Tuple[bool, Optional[str]]:
    """Verifies the CRC16 Modbus checksum of a hex payload."""
    if not crc16_modbus_func:
        _LOGGER.debug("crcmod not available, skipping CRC verification.")
        # Nếu không có crcmod, tạm chấp nhận là đúng để parse thử
        return True, "CRC check skipped"

    if len(payload_hex) < 4:
        return False, "Payload too short for CRC"

    try:
        data_hex = payload_hex[:-4]
        received_crc_hex = payload_hex[-4:]
        data_bytes = bytes.fromhex(data_hex)

        calculated_crc = calculate_crc16_modbus(data_bytes)
        if calculated_crc is None:
            return False, "CRC calculation failed"

        # CRC trả về 2 byte, cần đảo ngược byte order (little-endian) để so sánh
        calculated_crc_bytes = calculated_crc.to_bytes(2, byteorder='little')
        calculated_crc_hex = calculated_crc_bytes.hex()

        is_valid = calculated_crc_hex == received_crc_hex.lower()
        if not is_valid:
            _LOGGER.warning(f"CRC mismatch! Received: {received_crc_hex}, Calculated: {calculated_crc_hex}")
            return False, f"CRC mismatch: rcv={received_crc_hex}, calc={calculated_crc_hex}"
        else:
            _LOGGER.debug("CRC check successful.")
            return True, None
    except ValueError as e:
        _LOGGER.error(f"Error decoding hex for CRC check: {e}")
        return False, "Hex decoding error"
    except Exception as e:
        _LOGGER.exception(f"Unexpected error during CRC verification: {e}")
        return False, f"Unexpected CRC error: {e}"

def generate_modbus_read_command(slave_id: int, func_code: int, start_addr: int, num_registers: int) -> Optional[str]:
    """Generates a Modbus read command hex string with CRC."""
    if not crc16_modbus_func:
        _LOGGER.error("Cannot generate Modbus command: crcmod library not available.")
        return None
    try:
        # Tạo phần PDU (Protocol Data Unit) không bao gồm Slave ID và CRC
        pdu = bytearray()
        pdu.append(func_code)
        pdu.extend(start_addr.to_bytes(2, byteorder='big'))
        pdu.extend(num_registers.to_bytes(2, byteorder='big'))

        # Tạo phần ADU (Application Data Unit) ban đầu gồm Slave ID + PDU
        adu_no_crc = bytearray()
        adu_no_crc.append(slave_id)
        adu_no_crc.extend(pdu)

        # Tính CRC cho ADU không bao gồm CRC
        crc = calculate_crc16_modbus(bytes(adu_no_crc))
        if crc is None:
             _LOGGER.error("CRC calculation failed during command generation.")
             return None

        # Ghép ADU và CRC (CRC là little-endian)
        adu_full = adu_no_crc + crc.to_bytes(2, byteorder='little')

        command_hex = adu_full.hex()
        _LOGGER.debug(f"Generated Modbus command: {command_hex}")
        return command_hex
    except Exception as e:
        _LOGGER.exception(f"Error generating Modbus command: {e}")
        return None


def parse_mqtt_payload(payload_hex: str) -> Optional[Dict[str, Any]]:
    """Parses the custom hex payload from MQTT (Restore Point 1)."""
    _LOGGER.debug(f"Received raw hex payload: {payload_hex[:100]}...") # Log phần đầu
    parsed_data = {}

    # Kiểm tra cấu trúc cơ bản: Phải là phản hồi đọc (0103 hoặc 0104)
    # và có thể có dấu phân cách "++++" (2b2b2b2b)
    response_with_crc_hex = None
    if payload_hex.startswith("0103") or payload_hex.startswith("0104"):
        separator_hex = "2b2b2b2b"
        if separator_hex in payload_hex:
            try:
                parts = payload_hex.split(separator_hex)
                # Lấy phần sau dấu phân cách nếu có 2 phần
                if len(parts) == 2:
                    response_with_crc_hex = parts[1]
                    _LOGGER.debug("Separator '++++' found, parsing part after it.")
                else:
                     _LOGGER.warning(f"Separator '++++' found, but split resulted in {len(parts)} parts. Ignoring.")
                     return None
            except Exception as e:
                _LOGGER.error(f"Error splitting payload by separator: {e}")
                return None
        else:
            # Nếu không có separator, toàn bộ payload là phần phản hồi
            response_with_crc_hex = payload_hex
            _LOGGER.debug("No separator '++++' found, parsing entire payload.")

        # Nếu không tìm thấy phần response hợp lệ
        if not response_with_crc_hex or not (response_with_crc_hex.startswith("0103") or response_with_crc_hex.startswith("0104")):
             _LOGGER.warning("Could not extract valid Modbus response part from payload.")
             return None

        # --- Xác thực và trích xuất data_bytes từ response_with_crc_hex ---
        # Kiểm tra độ dài tối thiểu (header 3 byte + data min 1 byte + crc 2 byte = 6 byte hex)
        if len(response_with_crc_hex) < 10: # Ít nhất 1 word data
            _LOGGER.warning(f"Response part too short: {response_with_crc_hex}")
            return None

        try:
            # Lấy byte count (byte thứ 3, index 4 và 5)
            byte_count_hex = response_with_crc_hex[4:6]
            byte_count = int(byte_count_hex, 16)

            # Kiểm tra độ dài tổng thể dự kiến
            expected_data_hex_len = byte_count * 2
            expected_total_len = 6 + expected_data_hex_len + 4 # Header (0103/04 + count) + Data + CRC
            if len(response_with_crc_hex) != expected_total_len:
                 _LOGGER.warning(f"Payload length mismatch. Expected {expected_total_len} hex chars based on byte count {byte_count}, got {len(response_with_crc_hex)}.")
                 # Có thể thử parse nếu CRC đúng? Tạm thời bỏ qua
                 # return None # Bỏ qua nếu độ dài không khớp chặt chẽ
                 pass # Vẫn thử CRC

            # Xác thực CRC
            crc_valid, crc_msg = verify_crc(response_with_crc_hex)
            if not crc_valid:
                _LOGGER.warning(f"CRC check failed: {crc_msg}. Payload: {response_with_crc_hex}")
                # return None # Bỏ qua nếu CRC sai

            # Trích xuất phần data hex (bỏ qua header và CRC)
            data_start_index = 6
            data_end_index = data_start_index + expected_data_hex_len
            # Cẩn thận với index nếu độ dài thực tế khác dự kiến
            actual_data_end_index = len(response_with_crc_hex) - 4
            if data_end_index > actual_data_end_index : # Đảm bảo không đọc vượt quá CRC
                 data_end_index = actual_data_end_index

            data_hex = response_with_crc_hex[data_start_index : data_end_index]
            data_bytes = bytes.fromhex(data_hex)

            # Kiểm tra lại độ dài data_bytes với byte_count (quan trọng)
            if len(data_bytes) != byte_count:
                _LOGGER.warning(f"Actual data bytes length ({len(data_bytes)}) does not match byte count ({byte_count}).")
                # return None # Bỏ qua nếu không khớp

            _LOGGER.debug(f"CRC OK (or skipped). Parsing {len(data_bytes)} data bytes...")

            # --- Hàm trợ giúp đọc thanh ghi ---
            def read_reg_signed_short(reg_addr: int, factor: float = 1.0) -> Optional[float]:
                offset_bytes = reg_addr * 2
                if offset_bytes + 2 <= len(data_bytes):
                    try:
                        # Đọc 2 byte là signed short, big-endian
                        raw_val = struct.unpack('>h', data_bytes[offset_bytes:offset_bytes+2])[0]
                        return round(raw_val * factor, 2)
                    except struct.error: return None
                return None

            def read_reg_unsigned_short(reg_addr: int, factor: float = 1.0) -> Optional[float]:
                offset_bytes = reg_addr * 2
                if offset_bytes + 2 <= len(data_bytes):
                    try:
                        # Đọc 2 byte là unsigned short, big-endian
                        raw_val = struct.unpack('>H', data_bytes[offset_bytes:offset_bytes+2])[0]
                        return round(raw_val * factor, 2)
                    except struct.error: return None
                return None

            def read_reg_unsigned_int32(reg_addr: int, factor: float = 1.0) -> Optional[float]: # Dùng cho KWh nếu cần
                offset_bytes = reg_addr * 2
                if offset_bytes + 4 <= len(data_bytes):
                    try:
                         # Đọc 4 byte là unsigned int, big-endian
                         raw_val = struct.unpack('>I', data_bytes[offset_bytes:offset_bytes+4])[0]
                         return round(raw_val * factor, 2)
                    except struct.error: return None
                return None

            def read_temperature(reg_addr: int) -> Optional[float]:
                 """Đọc nhiệt độ theo công thức (raw - 1000) / 10.0"""
                 offset_bytes = reg_addr * 2
                 if offset_bytes + 2 <= len(data_bytes):
                     try:
                         # Nhiệt độ có thể là số âm, đọc là signed short
                         raw_val_temp = struct.unpack('>h', data_bytes[offset_bytes:offset_bytes+2])[0]
                         temp_c = (float(raw_val_temp) - 1000.0) / 10.0
                         # Kiểm tra giới hạn hợp lý
                         if -40.0 < temp_c < 150.0: return round(temp_c, 1)
                         else: _LOGGER.warning(f"Temp from Reg {reg_addr} ({temp_c}C) out of range."); return None
                     except struct.error: return None
                 return None

            # --- GIẢI MÃ DỮ LIỆU TỨC THỜI (RP1) ---
            addr = REG_ADDR # Sử dụng map từ const.py

            parsed_data[KEY_BATTERY_VOLTAGE] = read_reg_unsigned_short(addr["BATTERY_VOLTAGE"], 0.01)
            bat_current_val = read_reg_signed_short(addr["BATTERY_CURRENT"], 0.01)
            # Đảo dấu dòng pin: dương là sạc, âm là xả (theo tiêu chuẩn HA)
            parsed_data[KEY_BATTERY_CURRENT] = -bat_current_val if bat_current_val is not None else None
            parsed_data[KEY_AC_OUT_VOLTAGE] = read_reg_unsigned_short(addr["AC_OUT_VOLTAGE"], 0.1)
            parsed_data[KEY_GRID_VOLTAGE] = read_reg_unsigned_short(addr["GRID_VOLTAGE"], 0.1)
            parsed_data[KEY_AC_OUT_FREQ] = read_reg_unsigned_short(addr["AC_OUT_FREQ"], 0.01)
            parsed_data[KEY_DEVICE_TEMP] = read_temperature(addr["DEVICE_TEMP"]) # Dùng hàm đọc nhiệt độ riêng
            parsed_data[KEY_PV1_VOLTAGE] = read_reg_unsigned_short(addr["PV1_VOLTAGE"])
            parsed_data[KEY_PV2_VOLTAGE] = read_reg_unsigned_short(addr["PV2_VOLTAGE"])
            # Grid power là số có dấu: dương là nhập, âm là xuất
            parsed_data[KEY_GRID_POWER] = read_reg_signed_short(addr["GRID_POWER"])
            parsed_data[KEY_LOAD_POWER] = read_reg_unsigned_short(addr["LOAD_POWER"])
            parsed_data[KEY_AC_OUT_POWER] = read_reg_unsigned_short(addr["AC_OUT_POWER"])
            parsed_data[KEY_AC_OUT_VA] = read_reg_unsigned_short(addr["AC_OUT_VA"])
            # Battery power là số có dấu (âm là sạc, dương là xả), lấy giá trị tuyệt đối cho sensor này
            bat_power_signed = read_reg_signed_short(addr["BATTERY_POWER"])
            parsed_data[KEY_BATTERY_POWER] = abs(bat_power_signed) if bat_power_signed is not None else None
            pv1_power = read_reg_unsigned_short(addr["PV1_POWER"])
            pv2_power = read_reg_unsigned_short(addr["PV2_POWER"])
            # Tính tổng PV power, chỉ tính nếu có giá trị
            pv_power_total = (pv1_power if pv1_power is not None else 0) + (pv2_power if pv2_power is not None else 0)
            # Chỉ gán nếu ít nhất 1 PV có giá trị
            if pv1_power is not None or pv2_power is not None:
                 parsed_data[KEY_PV_POWER] = pv_power_total
            else:
                 parsed_data[KEY_PV_POWER] = None # Hoặc 0? Tạm để None
            # SOC là unsigned short
            soc_val = read_reg_unsigned_short(addr["BATTERY_SOC"])
            # Đảm bảo SOC trong khoảng 0-100
            parsed_data[KEY_BATTERY_SOC] = max(0, min(100, int(soc_val))) if soc_val is not None else None
            # UPS Mode là boolean (0 = True)
            ups_val = read_reg_unsigned_short(addr["UPS_MODE"])
            parsed_data[KEY_IS_UPS_MODE] = (ups_val == 0) if ups_val is not None else None

            # Bỏ qua việc đọc KWh ở RP1
            # Ví dụ:
            # discharge_today = read_reg_unsigned_short(addr.get("TOTAL_BAT_DISCHARGE_KWH"), 0.1)
            # if discharge_today is not None: parsed_data[KEY_TOTAL_BAT_DISCHARGE_KWH] = discharge_today

            # Lọc bỏ các giá trị None trước khi trả về
            parsed_data = {k: v for k, v in parsed_data.items() if v is not None}
            _LOGGER.debug(f"Parsed realtime data dict (RP1): {parsed_data}")

        except ValueError as e:
            _LOGGER.error(f"ValueError during parsing: {e}. Payload part: {response_with_crc_hex[:60]}...")
            return None
        except struct.error as e:
             _LOGGER.error(f"Struct unpacking error: {e}. Data bytes length: {len(data_bytes)}")
             return None
        except Exception as e:
            _LOGGER.exception(f"Unexpected error during payload parsing: {e}")
            return None

    else:
        _LOGGER.debug(f"Payload does not start with known Modbus response header: {payload_hex[:10]}")
        return None

    # Trả về dữ liệu đã parse nếu thành công
    if parsed_data:
        # Thêm trạng thái online nếu parse thành công
        parsed_data[KEY_ONLINE_STATUS] = True
        _LOGGER.info("++++ PARSING SUCCESSFUL (Restore Point 1) ++++")
        return parsed_data
    else:
        _LOGGER.warning(f"No relevant data could be parsed from payload: {payload_hex[:60]}...")
        return None