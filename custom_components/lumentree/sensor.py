# /config/custom_components/lumentree/sensor.py
# Final cleanup - Remove unavailable MQTT mode sensors

from typing import Any, Dict, Optional, Callable, cast
import logging
import re

from homeassistant.components.sensor import (
    SensorEntity, SensorEntityDescription, SensorDeviceClass, SensorStateClass
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfPower, UnitOfEnergy, PERCENTAGE, UnitOfTemperature, UnitOfElectricPotential,
    UnitOfFrequency, UnitOfElectricCurrent, UnitOfApparentPower, EntityCategory,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo, generate_entity_id
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator
)
#from homeassistant.helpers.template import slugify

try:
    from .const import (
        DOMAIN, _LOGGER, CONF_DEVICE_SN, CONF_DEVICE_NAME,
        SIGNAL_UPDATE_FORMAT, # Removed initial signal
        KEY_PV_POWER, KEY_BATTERY_POWER, KEY_BATTERY_SOC, KEY_GRID_POWER,
        KEY_LOAD_POWER, KEY_BATTERY_VOLTAGE, KEY_BATTERY_CURRENT, KEY_AC_OUT_VOLTAGE,
        KEY_GRID_VOLTAGE, KEY_AC_OUT_FREQ, KEY_AC_OUT_POWER, KEY_AC_OUT_VA,
        KEY_DEVICE_TEMP, KEY_PV1_VOLTAGE, KEY_PV1_POWER, KEY_PV2_VOLTAGE,
        KEY_PV2_POWER, KEY_BATTERY_STATUS, KEY_GRID_STATUS, KEY_AC_IN_VOLTAGE,
        KEY_AC_IN_FREQ, KEY_AC_IN_POWER, KEY_BATTERY_TYPE,
        KEY_MASTER_SLAVE_STATUS, KEY_MQTT_DEVICE_SN,
        KEY_BATTERY_CELL_INFO,
        KEY_DAILY_PV_KWH, KEY_DAILY_CHARGE_KWH, KEY_DAILY_DISCHARGE_KWH,
        KEY_DAILY_GRID_IN_KWH, KEY_DAILY_LOAD_KWH,
        KEY_LAST_RAW_MQTT
    )
    from .coordinator_stats import LumentreeStatsCoordinator
except ImportError:
    DOMAIN = "lumentree"; _LOGGER = logging.getLogger(__name__)
    CONF_DEVICE_SN = "device_sn"; CONF_DEVICE_NAME = "device_name"; SIGNAL_UPDATE_FORMAT = "lumentree_mqtt_update_{device_sn}"
    KEY_PV_POWER="pv_power"; KEY_BATTERY_POWER="battery_power"; KEY_BATTERY_SOC="battery_soc"; KEY_GRID_POWER="grid_power"; KEY_LOAD_POWER="load_power"; KEY_BATTERY_VOLTAGE="battery_voltage"; KEY_BATTERY_CURRENT="battery_current"; KEY_AC_OUT_VOLTAGE="ac_output_voltage"; KEY_GRID_VOLTAGE="grid_voltage"; KEY_AC_OUT_FREQ="ac_output_frequency"; KEY_AC_OUT_POWER="ac_output_power"; KEY_AC_OUT_VA="ac_output_va"; KEY_DEVICE_TEMP="device_temperature"; KEY_PV1_VOLTAGE="pv1_voltage"; KEY_PV1_POWER="pv1_power"; KEY_PV2_VOLTAGE="pv2_voltage"; KEY_PV2_POWER="pv2_power"; KEY_LAST_RAW_MQTT="last_raw_mqtt_hex"
    KEY_BATTERY_STATUS="battery_status"; KEY_GRID_STATUS="grid_status"; KEY_AC_IN_VOLTAGE="ac_input_voltage"; KEY_AC_IN_FREQ="ac_input_frequency"; KEY_AC_IN_POWER="ac_input_power"; KEY_BATTERY_TYPE="battery_type"; KEY_MASTER_SLAVE_STATUS="master_slave_status"; KEY_MQTT_DEVICE_SN="mqtt_device_sn"; KEY_BATTERY_CELL_INFO="battery_cell_info"
    KEY_DAILY_PV_KWH="pv_today"; KEY_DAILY_CHARGE_KWH="charge_today"; KEY_DAILY_DISCHARGE_KWH="discharge_today"; KEY_DAILY_GRID_IN_KWH="grid_in_today"; KEY_DAILY_LOAD_KWH="load_today"
    class LumentreeStatsCoordinator: pass
    def slugify(text): return re.sub(r"[^a-z0-9_]+", "_", text.lower())


# --- Sensor Descriptions (MQTT Realtime - Chỉ chứa các key đọc được từ 0-94) ---
REALTIME_SENSOR_DESCRIPTIONS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(key=KEY_PV_POWER, name="PV Power", native_unit_of_measurement=UnitOfPower.WATT, device_class=SensorDeviceClass.POWER, state_class=SensorStateClass.MEASUREMENT, icon="mdi:solar-power"),
    SensorEntityDescription(key=KEY_BATTERY_POWER, name="Battery Power (Absolute)", native_unit_of_measurement=UnitOfPower.WATT, device_class=SensorDeviceClass.POWER, state_class=SensorStateClass.MEASUREMENT, icon="mdi:battery"),
    SensorEntityDescription(key=KEY_GRID_POWER, name="Grid Power", native_unit_of_measurement=UnitOfPower.WATT, device_class=SensorDeviceClass.POWER, state_class=SensorStateClass.MEASUREMENT, icon="mdi:transmission-tower", suggested_display_precision=0),
    SensorEntityDescription(key=KEY_LOAD_POWER, name="Load Power", native_unit_of_measurement=UnitOfPower.WATT, device_class=SensorDeviceClass.POWER, state_class=SensorStateClass.MEASUREMENT, icon="mdi:power-plug"),
    SensorEntityDescription(key=KEY_AC_OUT_POWER, name="AC Output Power", native_unit_of_measurement=UnitOfPower.WATT, device_class=SensorDeviceClass.POWER, state_class=SensorStateClass.MEASUREMENT),
    SensorEntityDescription(key=KEY_AC_IN_POWER, name="AC Input Power", native_unit_of_measurement=UnitOfPower.WATT, device_class=SensorDeviceClass.POWER, state_class=SensorStateClass.MEASUREMENT, entity_registry_enabled_default=True, suggested_display_precision=2),
    SensorEntityDescription(key=KEY_PV1_POWER, name="PV1 Power", native_unit_of_measurement=UnitOfPower.WATT, device_class=SensorDeviceClass.POWER, state_class=SensorStateClass.MEASUREMENT, entity_registry_enabled_default=False),
    SensorEntityDescription(key=KEY_PV2_POWER, name="PV2 Power", native_unit_of_measurement=UnitOfPower.WATT, device_class=SensorDeviceClass.POWER, state_class=SensorStateClass.MEASUREMENT, entity_registry_enabled_default=False),
    SensorEntityDescription(key=KEY_AC_OUT_VA, name="AC Output Apparent Power", native_unit_of_measurement=UnitOfApparentPower.VOLT_AMPERE, device_class=SensorDeviceClass.APPARENT_POWER, state_class=SensorStateClass.MEASUREMENT),
    SensorEntityDescription(key=KEY_BATTERY_VOLTAGE, name="Battery Voltage", native_unit_of_measurement=UnitOfElectricPotential.VOLT, device_class=SensorDeviceClass.VOLTAGE, state_class=SensorStateClass.MEASUREMENT, icon="mdi:battery-outline", suggested_display_precision=2),
    SensorEntityDescription(key=KEY_AC_OUT_VOLTAGE, name="AC Output Voltage", native_unit_of_measurement=UnitOfElectricPotential.VOLT, device_class=SensorDeviceClass.VOLTAGE, state_class=SensorStateClass.MEASUREMENT, suggested_display_precision=1),
    SensorEntityDescription(key=KEY_GRID_VOLTAGE, name="Grid Voltage", native_unit_of_measurement=UnitOfElectricPotential.VOLT, device_class=SensorDeviceClass.VOLTAGE, state_class=SensorStateClass.MEASUREMENT, suggested_display_precision=1),
    SensorEntityDescription(key=KEY_AC_IN_VOLTAGE, name="AC Input Voltage", native_unit_of_measurement=UnitOfElectricPotential.VOLT, device_class=SensorDeviceClass.VOLTAGE, state_class=SensorStateClass.MEASUREMENT, suggested_display_precision=1, entity_registry_enabled_default=False),
    SensorEntityDescription(key=KEY_PV1_VOLTAGE, name="PV1 Voltage", native_unit_of_measurement=UnitOfElectricPotential.VOLT, device_class=SensorDeviceClass.VOLTAGE, state_class=SensorStateClass.MEASUREMENT, entity_registry_enabled_default=False),
    SensorEntityDescription(key=KEY_PV2_VOLTAGE, name="PV2 Voltage", native_unit_of_measurement=UnitOfElectricPotential.VOLT, device_class=SensorDeviceClass.VOLTAGE, state_class=SensorStateClass.MEASUREMENT, entity_registry_enabled_default=False),
    SensorEntityDescription(key=KEY_BATTERY_CURRENT, name="Battery Current", native_unit_of_measurement=UnitOfElectricCurrent.AMPERE, device_class=SensorDeviceClass.CURRENT, state_class=SensorStateClass.MEASUREMENT, icon="mdi:current-dc", suggested_display_precision=2),
    SensorEntityDescription(key=KEY_AC_OUT_FREQ, name="AC Output Frequency", native_unit_of_measurement=UnitOfFrequency.HERTZ, device_class=SensorDeviceClass.FREQUENCY, state_class=SensorStateClass.MEASUREMENT, suggested_display_precision=2),
    SensorEntityDescription(key=KEY_AC_IN_FREQ, name="AC Input Frequency", native_unit_of_measurement=UnitOfFrequency.HERTZ, device_class=SensorDeviceClass.FREQUENCY, state_class=SensorStateClass.MEASUREMENT, suggested_display_precision=2, entity_registry_enabled_default=True),
    SensorEntityDescription(key=KEY_BATTERY_SOC, name="Battery SOC", native_unit_of_measurement=PERCENTAGE, device_class=SensorDeviceClass.BATTERY, state_class=SensorStateClass.MEASUREMENT),
    SensorEntityDescription(key=KEY_BATTERY_STATUS, name="Battery Status", device_class=SensorDeviceClass.ENUM, icon="mdi:battery-sync-outline"),
    SensorEntityDescription(key=KEY_BATTERY_TYPE, name="Battery Type", device_class=SensorDeviceClass.ENUM, icon="mdi:battery-unknown", entity_category=EntityCategory.DIAGNOSTIC),
    SensorEntityDescription(key=KEY_GRID_STATUS, name="Grid Status", device_class=SensorDeviceClass.ENUM, icon="mdi:transmission-tower-export"),
    SensorEntityDescription(key=KEY_DEVICE_TEMP, name="Device Temperature", native_unit_of_measurement=UnitOfTemperature.CELSIUS, device_class=SensorDeviceClass.TEMPERATURE, state_class=SensorStateClass.MEASUREMENT, suggested_display_precision=1),
    SensorEntityDescription(key=KEY_MASTER_SLAVE_STATUS, name="Master/Slave Status", icon="mdi:account-multiple", entity_category=EntityCategory.DIAGNOSTIC),
    SensorEntityDescription(key=KEY_MQTT_DEVICE_SN, name="Device SN (MQTT)", icon="mdi:barcode-scan", entity_category=EntityCategory.DIAGNOSTIC, entity_registry_enabled_default=False),
    SensorEntityDescription(key=KEY_BATTERY_CELL_INFO, name="Battery Cell Info", icon="mdi:battery-heart-variant", entity_category=EntityCategory.DIAGNOSTIC),
    SensorEntityDescription(key=KEY_LAST_RAW_MQTT, name="Last Raw MQTT Hex", icon="mdi:text-hexadecimal", entity_category=EntityCategory.DIAGNOSTIC, entity_registry_enabled_default=False),
)

# --- Sensor Descriptions (HTTP Daily Stats) ---
STATS_SENSOR_DESCRIPTIONS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(key=KEY_DAILY_PV_KWH, name="PV Generation Today", native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR, device_class=SensorDeviceClass.ENERGY, state_class=SensorStateClass.TOTAL_INCREASING, icon="mdi:solar-power", suggested_display_precision=1),
    SensorEntityDescription(key=KEY_DAILY_CHARGE_KWH, name="Battery Charge Today", native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR, device_class=SensorDeviceClass.ENERGY, state_class=SensorStateClass.TOTAL_INCREASING, icon="mdi:battery-plus-variant", suggested_display_precision=1),
    SensorEntityDescription(key=KEY_DAILY_DISCHARGE_KWH, name="Battery Discharge Today", native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR, device_class=SensorDeviceClass.ENERGY, state_class=SensorStateClass.TOTAL_INCREASING, icon="mdi:battery-minus-variant", suggested_display_precision=1),
    SensorEntityDescription(key=KEY_DAILY_GRID_IN_KWH, name="Grid Input Today", native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR, device_class=SensorDeviceClass.ENERGY, state_class=SensorStateClass.TOTAL_INCREASING, icon="mdi:transmission-tower-import", suggested_display_precision=1),
    SensorEntityDescription(key=KEY_DAILY_LOAD_KWH, name="Load Consumption Today", native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR, device_class=SensorDeviceClass.ENERGY, state_class=SensorStateClass.TOTAL_INCREASING, icon="mdi:home-lightning-bolt", suggested_display_precision=1),
)

# --- async_setup_entry ---
async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    _LOGGER.debug(f"Setting up sensor platform for {entry.title}")
    try:
        entry_data = hass.data[DOMAIN][entry.entry_id]
        coordinator_stats: Optional[LumentreeStatsCoordinator] = entry_data.get("coordinator_stats")
        device_sn = entry.data[CONF_DEVICE_SN]
        device_name = entry.data[CONF_DEVICE_NAME]
        device_api_info = entry_data.get('device_api_info', {})
        # Không cần initial_data nữa
    except KeyError as e: _LOGGER.error(f"Missing key {e} in entry data."); return

    device_info = DeviceInfo(
        identifiers={(DOMAIN, device_sn)}, name=device_name, manufacturer="YS Tech (YiShen)",
        model=device_api_info.get("deviceType"),
        sw_version=device_api_info.get("controllerVersion"),
        hw_version=device_api_info.get("liquidCrystalVersion"),
    )
    _LOGGER.debug(f"Creating DeviceInfo for sensors {device_sn}: {device_info}")

    entities_to_add: list[SensorEntity] = []
    for description in REALTIME_SENSOR_DESCRIPTIONS:
        if description.key == KEY_BATTERY_CELL_INFO:
            # <<< Truyền dict rỗng cho initial_data >>>
            entities_to_add.append(LumentreeBatteryCellSensor(hass, entry, device_info, description, {}))
        else:
            # <<< Truyền dict rỗng cho initial_data >>>
            entities_to_add.append(LumentreeMqttSensor(hass, entry, device_info, description, {}))
    _LOGGER.info(f"Adding {len(REALTIME_SENSOR_DESCRIPTIONS)} real-time sensors for {device_sn}")
    if coordinator_stats:
        added_stats_keys = set()
        for description in STATS_SENSOR_DESCRIPTIONS: entities_to_add.append(LumentreeDailyStatsSensor(coordinator_stats, device_info, description)); added_stats_keys.add(description.key)
        _LOGGER.info(f"Adding {len(added_stats_keys)} daily stats sensors for {device_sn}")
    else: _LOGGER.warning(f"Stats Coordinator not available for {device_sn}.")
    if entities_to_add: async_add_entities(entities_to_add)
    else: _LOGGER.warning(f"No sensors added for {device_sn}.")


# --- Class LumentreeMqttSensor ---
class LumentreeMqttSensor(SensorEntity):
    _attr_should_poll = False; _attr_has_entity_name = True
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, device_info: DeviceInfo, description: SensorEntityDescription, initial_data: Dict[str, Any]) -> None:
        self.hass = hass; self.entity_description = description; self._device_sn = entry.data[CONF_DEVICE_SN]
        self._attr_unique_id = f"{self._device_sn}_{description.key}"; object_id = f"device_{self._device_sn}_{slugify(description.key)}"; self._attr_object_id = object_id
        self.entity_id = generate_entity_id("sensor.{}", self._attr_object_id, hass=hass)
        self._attr_device_info = device_info; self._remove_dispatcher: Optional[Callable[[], None]] = None
        self._attr_native_value = self._process_value(initial_data.get(description.key)) # Vẫn thử lấy giá trị ban đầu (dù thường là None)
        _LOGGER.debug(f"Init MQTT sensor: uid={self.unique_id}, name={self.name}, initial_state={self._attr_native_value}")

    def _process_value(self, value: Any) -> Any: # Giữ nguyên
        processed_value: Any = None
        if value is not None:
            desc = self.entity_description
            if desc.state_class in [SensorStateClass.MEASUREMENT, SensorStateClass.TOTAL, SensorStateClass.TOTAL_INCREASING] and desc.native_unit_of_measurement != PERCENTAGE:
                try: processed_value = float(value)
                except (ValueError, TypeError): pass
            elif desc.native_unit_of_measurement == PERCENTAGE or desc.key == KEY_MASTER_SLAVE_STATUS:
                 try: processed_value = int(value)
                 except (ValueError, TypeError): pass
            else:
                processed_value = str(value)
                if desc.key == KEY_LAST_RAW_MQTT and len(processed_value) > 255: processed_value = processed_value[:252] + "..."
        return processed_value

    @callback
    def _handle_update(self, data: Dict[str, Any]) -> None: # Giữ nguyên (không xử lý modes)
        key = self.entity_description.key
        if key == KEY_BATTERY_CELL_INFO: return
        if key in data:
            new_value = self._process_value(data[key])
            if self._attr_native_value != new_value: self._attr_native_value = new_value; self.async_write_ha_state(); _LOGGER.debug(f"Update MQTT sensor {self.entity_id}: {new_value}")

    async def async_added_to_hass(self) -> None: # Chỉ đăng ký listener thường
        signal = SIGNAL_UPDATE_FORMAT.format(device_sn=self._device_sn); self._remove_dispatcher = async_dispatcher_connect(self.hass, signal, self._handle_update); _LOGGER.debug(f"MQTT sensor {self.unique_id} registered.")

    async def async_will_remove_from_hass(self) -> None: # Chỉ hủy listener thường
        if self._remove_dispatcher: self._remove_dispatcher(); self._remove_dispatcher = None;
        _LOGGER.debug(f"MQTT sensor {self.unique_id} unregistered.")


# --- Class LumentreeBatteryCellSensor ---
class LumentreeBatteryCellSensor(SensorEntity):
    _attr_should_poll = False; _attr_has_entity_name = True
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, device_info: DeviceInfo, description: SensorEntityDescription, initial_data: Dict[str, Any]) -> None:
        self.hass = hass; self.entity_description = description; self._device_sn = entry.data[CONF_DEVICE_SN]
        self._attr_unique_id = f"{self._device_sn}_{description.key}"; object_id = f"device_{self._device_sn}_{slugify(description.key)}"; self._attr_object_id = object_id
        self.entity_id = generate_entity_id("sensor.{}", self._attr_object_id, hass=hass)
        self._attr_device_info = device_info; self._attr_extra_state_attributes: Dict[str, Any] = {}; self._remove_dispatcher: Optional[Callable[[], None]] = None
        initial_cell_info = initial_data.get(KEY_BATTERY_CELL_INFO)
        if isinstance(initial_cell_info, dict): self._attr_native_value = initial_cell_info.get("number_of_cells"); self._attr_extra_state_attributes = initial_cell_info
        else: self._attr_native_value = None
        _LOGGER.debug(f"Init Cell sensor: uid={self.unique_id}, name={self.name}, initial_state={self._attr_native_value}")

    @callback
    def _handle_update(self, data: Dict[str, Any]) -> None: # Giữ nguyên
        if KEY_BATTERY_CELL_INFO in data:
            cell_info_dict = data[KEY_BATTERY_CELL_INFO];
            if isinstance(cell_info_dict, dict):
                new_state = cell_info_dict.get("number_of_cells")
                new_attrs = cell_info_dict
                if self._attr_native_value != new_state or self._attr_extra_state_attributes != new_attrs:
                    self._attr_native_value = new_state
                    self._attr_extra_state_attributes = new_attrs
                    self.async_write_ha_state()
                    _LOGGER.info(f"Update Cell sensor {self.entity_id}: State={new_state}")
            else:
                 _LOGGER.warning(f"Invalid cell info type {self.unique_id}: {type(cell_info_dict)}")

    async def async_added_to_hass(self) -> None: # Giữ nguyên
        signal = SIGNAL_UPDATE_FORMAT.format(device_sn=self._device_sn); self._remove_dispatcher = async_dispatcher_connect(self.hass, signal, self._handle_update); _LOGGER.debug(f"Cell sensor {self.unique_id} registered.")

    async def async_will_remove_from_hass(self) -> None: # Giữ nguyên
        if self._remove_dispatcher:
            self._remove_dispatcher()
            self._remove_dispatcher = None
        _LOGGER.debug(f"Cell sensor {self.unique_id} unregistered.")

# --- Class LumentreeDailyStatsSensor --- (Giữ nguyên)
class LumentreeDailyStatsSensor(CoordinatorEntity[LumentreeStatsCoordinator], SensorEntity):
    _attr_has_entity_name = True; _attr_should_poll = False
    def __init__(self, coordinator: LumentreeStatsCoordinator, device_info: DeviceInfo, description: SensorEntityDescription) -> None:
        super().__init__(coordinator); self.entity_description = description; self._device_sn = coordinator.device_sn
        self._attr_unique_id = f"{self._device_sn}_{description.key}"; object_id = f"device_{self._device_sn}_{slugify(description.key)}"; self._attr_object_id = object_id
        self.entity_id = generate_entity_id("sensor.{}", self._attr_object_id, hass=coordinator.hass)
        self._attr_device_info = device_info; self._attr_attribution = "Data fetched via Lumentree HTTP API"; self._update_state_from_coordinator()
        _LOGGER.debug(f"Init Stats sensor: uid={self.unique_id}, eid={self.entity_id}, name={self.name}")
    @callback
    def _handle_coordinator_update(self) -> None: self._update_state_from_coordinator(); self.async_write_ha_state(); _LOGGER.debug(f"Stats sensor {self.entity_id} updated.")
    def _update_state_from_coordinator(self) -> None: key = self.entity_description.key; value = self.coordinator.data.get(key) if self.coordinator.data else None; self._attr_native_value = round(value, 2) if isinstance(value, (int, float)) else None
    @property

    def available(self) -> bool: return self.coordinator.last_update_success
