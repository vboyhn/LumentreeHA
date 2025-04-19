# /config/custom_components/lumentree/parser.py
# Final version - STRICT NO SEMICOLONS, CORRECT INDENTATION EVERYWHERE

from typing import Optional, Dict, Any, Tuple, List
import logging
import struct
import math

# --- Import ---
try:
    import crcmod.predefined
    crc16_modbus_func = crcmod.predefined.mkCrcFun('modbus')
    _LOGGER = logging.getLogger(__package__)
    from .const import (
        _LOGGER, REG_ADDR,
        KEY_ONLINE_STATUS, KEY_PV_POWER, KEY_BATTERY_POWER, KEY_BATTERY_SOC,
        KEY_GRID_POWER, KEY_LOAD_POWER, KEY_BATTERY_VOLTAGE, KEY_BATTERY_CURRENT,
        KEY_AC_OUT_VOLTAGE, KEY_GRID_VOLTAGE, KEY_AC_OUT_FREQ, KEY_AC_OUT_POWER,
        KEY_AC_OUT_VA, KEY_DEVICE_TEMP, KEY_PV1_VOLTAGE, KEY_PV1_POWER,
        KEY_PV2_VOLTAGE, KEY_PV2_POWER, KEY_IS_UPS_MODE, KEY_BATTERY_STATUS,
        KEY_GRID_STATUS, KEY_AC_IN_VOLTAGE, KEY_AC_IN_FREQ, KEY_AC_IN_POWER,
        KEY_BATTERY_TYPE,
        KEY_MASTER_SLAVE_STATUS,
        KEY_MQTT_DEVICE_SN,
        KEY_BATTERY_CELL_INFO, REG_ADDR_CELL_START, REG_ADDR_CELL_COUNT,
        MAP_BATTERY_TYPE
    )
except ImportError:
    _LOGGER = logging.getLogger(__name__); _LOGGER.warning("ImportError parser.py")
    crc16_modbus_func = None; REG_ADDR = {}; KEY_ONLINE_STATUS="online"; KEY_IS_UPS_MODE="ups"; KEY_PV_POWER="pv"; KEY_BATTERY_POWER="bat_p"; KEY_BATTERY_SOC="soc"; KEY_GRID_POWER="grid_p"; KEY_LOAD_POWER="load_p"; KEY_BATTERY_VOLTAGE="bat_v"; KEY_BATTERY_CURRENT="bat_c"; KEY_AC_OUT_VOLTAGE="ac_out_v"; KEY_GRID_VOLTAGE="grid_v"; KEY_AC_OUT_FREQ="ac_out_f"; KEY_AC_OUT_POWER="ac_out_p"; KEY_AC_OUT_VA="ac_out_va"; KEY_DEVICE_TEMP="temp"; KEY_PV1_VOLTAGE="pv1_v"; KEY_PV1_POWER="pv1_p"; KEY_PV2_VOLTAGE="pv2_v"; KEY_PV2_POWER="pv2_p"; KEY_BATTERY_STATUS="bat_stat"; KEY_GRID_STATUS="grid_stat"; KEY_AC_IN_VOLTAGE="ac_in_v"; KEY_AC_IN_FREQ="ac_in_f"; KEY_AC_IN_POWER="ac_in_p"; KEY_BATTERY_TYPE="bat_type"; KEY_MASTER_SLAVE_STATUS="ms_stat"; KEY_MQTT_DEVICE_SN="mqtt_sn"; KEY_BATTERY_CELL_INFO="cells"
    REG_ADDR_CELL_START=250; REG_ADDR_CELL_COUNT=50; MAP_BATTERY_TYPE={}
except KeyError: _LOGGER = logging.getLogger(__name__); _LOGGER.warning("KeyError parser.py const")


# --- CRC Functions --- (Giữ nguyên)
def calculate_crc16_modbus(pb: bytes) -> Optional[int]:
    if crc16_modbus_func:
        try: return crc16_modbus_func(pb)
        except Exception: return None
    return None

def verify_crc(ph: str) -> Tuple[bool, Optional[str]]:
    if not crc16_modbus_func: return True, "CRC skipped"
    if len(ph) < 4: return False, "Too short"
    try:
        dh, rc = ph[:-4], ph[-4:].lower(); db = bytes.fromhex(dh)
        cc = calculate_crc16_modbus(db)
        if cc is None: return False, "Calc fail"
        cch = cc.to_bytes(2,'little').hex()
        ok = cch == rc
        if not ok: _LOGGER.warning(f"CRC mismatch! Rcv: {rc}, Calc: {cch}")
        else: _LOGGER.debug("CRC check successful.")
        return ok, None if ok else f"Mismatch {rc} vs {cch}"
    except Exception: return False, "Verify error"

# --- SỬA HÀM NÀY ---
def generate_modbus_read_command(sid: int, fc: int, addr: int, num: int) -> Optional[str]:
    """Generates a Modbus read command hex string with CRC."""
    if not crc16_modbus_func:
        _LOGGER.error("Cannot generate command: crcmod library missing.")
        return None
    try:
        pdu = bytearray([fc]) + addr.to_bytes(2,'big') + num.to_bytes(2,'big')
        adu = bytearray([sid]) + pdu
        crc = calculate_crc16_modbus(bytes(adu))
        # <<< Tách kiểm tra None và gán giá trị >>>
        if crc is None:
            _LOGGER.error("CRC calculation failed.")
            return None
        full = adu + crc.to_bytes(2,'little')
        command_hex = full.hex()
        # <<< Tách log và return >>>
        _LOGGER.debug(f"Generated Modbus command: {command_hex}")
        return command_hex
    except Exception as e:
        _LOGGER.exception(f"Error generating Modbus command: {e}")
        return None
# --- HẾT PHẦN SỬA ---

# --- Helper Functions --- (Giữ nguyên)
def _read_register(db: bytes, ra: int, s: bool, f: float = 1.0, bc: int = 2) -> Optional[float]:
    offset_bytes = ra * 2
    if offset_bytes + bc <= len(db):
        try:
            raw_bytes = db[offset_bytes : offset_bytes + bc]
            fmt = None
            if bc == 2: fmt = '>h' if s else '>H'
            elif bc == 4: fmt = '>i' if s else '>I'
            else: _LOGGER.warning(f"Unsupported byte_count {bc}.")
            if fmt:
                 raw_val = struct.unpack(fmt, raw_bytes)[0]
                 result = round(raw_val * f, 3)
                 if not math.isfinite(result): _LOGGER.warning(f"Invalid float read from reg {ra}."); return None
                 return result
            else: return None
        except struct.error as e: _LOGGER.error(f"Struct error reading reg {ra}: {e}"); return None
        except Exception as e: _LOGGER.exception(f"Unexpected error reading reg {ra}: {e}"); return None
    return None

def _read_string(db: bytes, sa: int, nr: int) -> Optional[str]:
    o, nb = sa*2, nr*2;
    if o + nb <= len(db):
        try: rb = db[o:o+nb]; ds = rb.decode('ascii', 'ignore').replace('\x00','').strip(); return ds if ds else None
        except Exception: return None
    return None

def _parse_battery_cells(db: bytes) -> Optional[Dict[str, Any]]:
    _LOGGER.debug(f"Parsing {len(db)} cell bytes..."); cd, nc, tv, mnv, mxv = {}, 0, 0.0, 999.0, 0.0; npc = len(db)//2
    for i in range(npc):
        v_mv = _read_register(db, i, False);
        if v_mv is not None:
            cv = round(v_mv/1000.0, 3);
            if 1.0 < cv < 5.0:
                cd[f"c_{i+1:02d}"]=cv
                nc+=1
                tv+=cv
                mnv=min(mnv,cv)
                mxv=max(mxv,cv)
    if nc > 0:
        avg=round(tv/nc,3); diff=round(mxv-mnv,3) if nc > 1 else 0.0
        res={"num":nc,"avg":avg,"min":mnv if mnv!=999.0 else None,"max":mxv if mxv!=0.0 else None,"diff":diff,"cells":cd}
        _LOGGER.debug(f"Parsed cells: {res}"); return res
    else: _LOGGER.warning("No valid cells."); return None

# --- Main Parsing Function ---
def parse_mqtt_payload(ph: str) -> Optional[Dict[str, Any]]:
    _LOGGER.debug(f"Parsing: {ph[:100]}...")
    parsed_data: Dict[str, Any] = {}
    db: Optional[bytes] = None
    is_cell_data = False
    resp_hex: Optional[str] = None
    sep = "2b2b2b2b"

    if sep in ph: parts=ph.split(sep); resp_hex = parts[1] if len(parts)==2 and (parts[1].startswith("0103") or parts[1].startswith("0104")) else None
    elif ph.startswith("0103") or ph.startswith("0104"): resp_hex = ph
    if not resp_hex or len(resp_hex)<12: return None

    try:
        crc_ok, _ = verify_crc(resp_hex)
        bc = int(resp_hex[4:6],16); dh = resp_hex[6:-4]; db = bytes.fromhex(dh)
        if len(db)!=bc: _LOGGER.warning(f"Len mismatch:{len(db)} vs {bc}.")
        if len(db)==0 and bc>0: _LOGGER.error("No data."); return None
        _LOGGER.debug(f"Parsing {len(db)} bytes...")

        expected_cell_bytes = REG_ADDR_CELL_COUNT * 2
        expected_main_bytes = 95 * 2

        if bc==expected_cell_bytes and len(db)==expected_cell_bytes: is_cell=True; _LOGGER.info("Cell data.")
        elif bc==expected_main_bytes and len(db)==expected_main_bytes: is_cell=False; _LOGGER.info("Main data (95 regs).")
        else: _LOGGER.error(f"Unrec len ({len(db)}/{bc}) for 95/50 regs."); return None

        if is_cell:
            cell_res = _parse_battery_cells(db)
            if cell_res: parsed_data[KEY_BATTERY_CELL_INFO] = cell_res
        else:
            addr = REG_ADDR
            def rr(k, s, f=1.0, bc=2): r=addr.get(k); return _read_register(db,r,s,f,bc) if r is not None else None

            bat_volt = rr("BATTERY_VOLTAGE",False,0.01);
            if bat_volt is not None: parsed_data[KEY_BATTERY_VOLTAGE] = bat_volt
            bat_curr = rr("BATTERY_CURRENT",True,0.01)
            if bat_curr is not None: parsed_data[KEY_BATTERY_CURRENT] = -bat_curr
            ac_out_v = rr("AC_OUT_VOLTAGE",False,0.1)
            if ac_out_v is not None: parsed_data[KEY_AC_OUT_VOLTAGE] = ac_out_v
            grid_v = rr("GRID_VOLTAGE",False,0.1)
            if grid_v is not None: parsed_data[KEY_GRID_VOLTAGE] = grid_v; parsed_data[KEY_AC_IN_VOLTAGE] = grid_v
            ac_out_f = rr("AC_OUT_FREQ",False,0.01)
            if ac_out_f is not None: parsed_data[KEY_AC_OUT_FREQ] = ac_out_f
            ac_in_f = rr("AC_IN_FREQ",False,0.01)
            if ac_in_f is not None: parsed_data[KEY_AC_IN_FREQ] = ac_in_f
            temp_raw=rr("DEVICE_TEMP",True)
            if temp_raw is not None: temp_c=round((temp_raw-1000)/10,1); parsed_data[KEY_DEVICE_TEMP]=temp_c if -40<temp_c<150 else None
            pv1_v=rr("PV1_VOLTAGE",False)
            if pv1_v is not None: parsed_data[KEY_PV1_VOLTAGE]=pv1_v
            pv2_v=rr("PV2_VOLTAGE",False)
            if pv2_v is not None: parsed_data[KEY_PV2_VOLTAGE]=pv2_v
            grid_p=rr("GRID_POWER",True)
            if grid_p is not None: parsed_data[KEY_GRID_POWER]=grid_p
            ac_in_p_r=rr("AC_IN_POWER",False); ac_in_p=round(ac_in_p_r/100,2) if ac_in_p_r is not None else None;
            if ac_in_p is not None: parsed_data[KEY_AC_IN_POWER]=ac_in_p
            load_p=rr("LOAD_POWER",False)
            if load_p is not None: parsed_data[KEY_LOAD_POWER]=load_p
            ac_out_p=rr("AC_OUT_POWER",False)
            if ac_out_p is not None: parsed_data[KEY_AC_OUT_POWER]=ac_out_p
            ac_out_va=rr("AC_OUT_VA",False)
            if ac_out_va is not None: parsed_data[KEY_AC_OUT_VA]=ac_out_va
            bp_s=rr("BATTERY_POWER",True)
            if bp_s is not None: parsed_data[KEY_BATTERY_POWER], parsed_data[KEY_BATTERY_STATUS] = abs(bp_s), ("Charging" if bp_s < 0 else "Discharging")
            else: parsed_data[KEY_BATTERY_POWER], parsed_data[KEY_BATTERY_STATUS] = None, "Unknown"
            pd_grid_s="Importing" if parsed_data.get(KEY_GRID_POWER,0)>0 else "Exporting" if parsed_data.get(KEY_GRID_POWER) is not None else "Unknown"; parsed_data[KEY_GRID_STATUS] = pd_grid_s
            pv1=rr("PV1_POWER",False); pv2=rr("PV2_POWER",False);
            if pv1 is not None: parsed_data[KEY_PV1_POWER]=pv1
            if pv2 is not None: parsed_data[KEY_PV2_POWER]=pv2
            pd_pv_p=(pv1 or 0)+(pv2 or 0) if (pv1 is not None or pv2 is not None) else None
            if pd_pv_p is not None: parsed_data[KEY_PV_POWER]=pd_pv_p
            soc=rr("BATTERY_SOC",False); pd_soc=max(0,min(100,int(soc))) if soc is not None else None
            if pd_soc is not None: parsed_data[KEY_BATTERY_SOC]=pd_soc
            ups=rr("UPS_MODE",False); pd_ups=(ups==0) if ups is not None else None
            if pd_ups is not None: parsed_data[KEY_IS_UPS_MODE]=pd_ups
            bt=rr("BATTERY_TYPE",False); pd_bt=MAP_BATTERY_TYPE.get(int(bt),"Present") if bt is not None else None
            if pd_bt is not None: parsed_data[KEY_BATTERY_TYPE]=pd_bt
            pd_ms=rr("MASTER_SLAVE_STATUS",False)
            if pd_ms is not None: parsed_data[KEY_MASTER_SLAVE_STATUS]=pd_ms
            pd_sn=_read_string(db, addr["DEVICE_MODEL_START"], 5)
            if pd_sn is not None: parsed_data[KEY_MQTT_DEVICE_SN]=pd_sn

            _LOGGER.debug(f"Parsed main data final: {parsed_data}")

    except Exception as e: _LOGGER.exception(f"Parse error: {e}"); return None

    if parsed_data: data_type="Cells" if is_cell else "Main (Std)"; _LOGGER.info(f"++++ PARSE OK ({data_type}) ++++"); return parsed_data
    else: _LOGGER.warning(f"No data parsed: {resp_hex[:60]}..."); return None
