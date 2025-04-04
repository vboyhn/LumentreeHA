# /config/custom_components/lumentree/sensor.py

from typing import Any, Dict, Optional, Callable

from homeassistant.components.sensor import (
    SensorEntity, SensorEntityDescription, SensorDeviceClass, SensorStateClass
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfPower, UnitOfEnergy, PERCENTAGE, UnitOfTemperature, UnitOfElectricPotential,
    UnitOfFrequency, UnitOfElectricCurrent, UnitOfApparentPower, # Thêm các đơn vị mới
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

try:
    from .const import (
        DOMAIN, _LOGGER, CONF_DEVICE_SN, CONF_DEVICE_NAME, SIGNAL_UPDATE_FORMAT,
        # Import tất cả các KEY sensor bạn muốn hiển thị
        KEY_PV_POWER, KEY_BATTERY_POWER, KEY_BATTERY_SOC, KEY_GRID_POWER,
        KEY_LOAD_POWER, KEY_GENERATION_TODAY, KEY_GENERATION_TOTAL,
        KEY_BATTERY_VOLTAGE, KEY_BATTERY_CURRENT, KEY_AC_OUT_VOLTAGE, KEY_GRID_VOLTAGE,
        KEY_AC_OUT_FREQ, KEY_AC_OUT_POWER, KEY_AC_OUT_VA, KEY_DEVICE_TEMP,
        KEY_PV1_VOLTAGE, KEY_PV1_POWER, KEY_PV2_VOLTAGE, KEY_PV2_POWER,
        KEY_TOTAL_PV_GEN_KWH, KEY_TOTAL_BAT_CHARGE_KWH, KEY_TOTAL_BAT_DISCHARGE_KWH,
        KEY_TOTAL_GRID_INPUT_KWH, KEY_TOTAL_HOME_LOAD_KWH,
        KEY_LAST_RAW_MQTT
    )
except ImportError:
    # Fallback imports
    # ... (Giữ nguyên fallback imports cho const) ...
    pass
import logging # Đảm bảo import logging

# --- Định nghĩa mô tả Sensor ---
# Thêm các mô tả mới và cập nhật các mô tả cũ nếu cần
SENSOR_DESCRIPTIONS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key=KEY_PV_POWER, name="PV Power",
        native_unit_of_measurement=UnitOfPower.WATT, device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT, icon="mdi:solar-power", suggested_display_precision=1,
    ),
    SensorEntityDescription(
        key=KEY_BATTERY_POWER, name="Battery Power (Abs)", # Giá trị tuyệt đối
        native_unit_of_measurement=UnitOfPower.WATT, device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT, icon="mdi:battery-charging", suggested_display_precision=0,
    ),
    SensorEntityDescription(
        key=KEY_BATTERY_SOC, name="Battery SOC",
        native_unit_of_measurement=PERCENTAGE, device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT, suggested_display_precision=0,
    ),
    SensorEntityDescription(
        key=KEY_GRID_POWER, name="Grid Power", # Có dấu
        native_unit_of_measurement=UnitOfPower.WATT, device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT, icon="mdi:transmission-tower", suggested_display_precision=0,
    ),
    SensorEntityDescription(
        key=KEY_LOAD_POWER, name="Load Power",
        native_unit_of_measurement=UnitOfPower.WATT, device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT, icon="mdi:power-plug", suggested_display_precision=0,
    ),
    SensorEntityDescription(
        key=KEY_GENERATION_TODAY, name="Generation Today", # Từ Reg 0? Chia 10?
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR, device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING, icon="mdi:solar-power", suggested_display_precision=1,
    ),
    SensorEntityDescription(
        key=KEY_GENERATION_TOTAL, name="Total Generation", # Từ Reg 90-91? Chia 10?
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR, device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL, icon="mdi:chart-line", suggested_display_precision=1,
    ),
    # --- Các Sensor Mới ---
    SensorEntityDescription(
        key=KEY_BATTERY_VOLTAGE, name="Battery Voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT, device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT, icon="mdi:battery", suggested_display_precision=2,
    ),
    SensorEntityDescription(
        key=KEY_BATTERY_CURRENT, name="Battery Current", # Có dấu
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE, device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT, icon="mdi:current-dc", suggested_display_precision=2,
    ),
     SensorEntityDescription(
        key=KEY_AC_OUT_VOLTAGE, name="AC Output Voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT, device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT, icon="mdi:power-plug", suggested_display_precision=1,
    ),
     SensorEntityDescription(
        key=KEY_GRID_VOLTAGE, name="Grid Voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT, device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT, icon="mdi:transmission-tower", suggested_display_precision=1,
    ),
     SensorEntityDescription(
        key=KEY_AC_OUT_FREQ, name="AC Output Frequency",
        native_unit_of_measurement=UnitOfFrequency.HERTZ, device_class=SensorDeviceClass.FREQUENCY,
        state_class=SensorStateClass.MEASUREMENT, icon="mdi:sine-wave", suggested_display_precision=2,
    ),
     SensorEntityDescription(
        key=KEY_AC_OUT_POWER, name="AC Output Power",
        native_unit_of_measurement=UnitOfPower.WATT, device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT, icon="mdi:power-plug-outline", suggested_display_precision=0,
    ),
      SensorEntityDescription(
        key=KEY_AC_OUT_VA, name="AC Output Apparent Power",
        native_unit_of_measurement=UnitOfApparentPower.VOLT_AMPERE, device_class=SensorDeviceClass.APPARENT_POWER,
        state_class=SensorStateClass.MEASUREMENT, icon="mdi:power-plug-outline", suggested_display_precision=0,
    ),
     SensorEntityDescription(
        key=KEY_DEVICE_TEMP, name="Device Temperature", # Có dấu
        native_unit_of_measurement=UnitOfTemperature.CELSIUS, device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT, icon="mdi:thermometer", suggested_display_precision=1,
    ),
     SensorEntityDescription(
        key=KEY_PV1_VOLTAGE, name="PV1 Voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT, device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT, icon="mdi:solar-power-variant", suggested_display_precision=1,
    ),
     SensorEntityDescription(
        key=KEY_PV1_POWER, name="PV1 Power",
        native_unit_of_measurement=UnitOfPower.WATT, device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT, icon="mdi:solar-power-variant-outline", suggested_display_precision=0,
    ),
     SensorEntityDescription(
        key=KEY_PV2_VOLTAGE, name="PV2 Voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT, device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT, icon="mdi:solar-power-variant", suggested_display_precision=1, entity_registry_enabled_default=False, # Ẩn nếu không phải lúc nào cũng có
    ),
     SensorEntityDescription(
        key=KEY_PV2_POWER, name="PV2 Power",
        native_unit_of_measurement=UnitOfPower.WATT, device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT, icon="mdi:solar-power-variant-outline", suggested_display_precision=0, entity_registry_enabled_default=False, # Ẩn nếu không phải lúc nào cũng có
    ),
    # --- Các Sensor Tổng KWH (Nếu muốn) ---
    SensorEntityDescription(
        key=KEY_TOTAL_PV_GEN_KWH, name="Total PV Generation", # Từ Reg 0
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR, device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL, icon="mdi:chart-line", suggested_display_precision=1, entity_registry_enabled_default=False,
    ),
    SensorEntityDescription(
        key=KEY_TOTAL_BAT_CHARGE_KWH, name="Total Battery Charge", # Từ Reg 4
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR, device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL, icon="mdi:battery-plus-variant", suggested_display_precision=1, entity_registry_enabled_default=False,
    ),
    SensorEntityDescription(
        key=KEY_TOTAL_BAT_DISCHARGE_KWH, name="Total Battery Discharge", # Từ Reg 5
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR, device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL, icon="mdi:battery-minus-variant", suggested_display_precision=1, entity_registry_enabled_default=False,
    ),
    SensorEntityDescription(
        key=KEY_TOTAL_GRID_INPUT_KWH, name="Total Grid Input", # Từ Reg 2
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR, device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL, icon="mdi:transmission-tower-import", suggested_display_precision=1, entity_registry_enabled_default=False,
    ),
     SensorEntityDescription(
        key=KEY_TOTAL_HOME_LOAD_KWH, name="Total Home Load", # Từ Reg 3
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR, device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL, icon="mdi:home-lightning-bolt", suggested_display_precision=1, entity_registry_enabled_default=False,
    ),
    # --- Sensor Debug ---
    SensorEntityDescription(
        key=KEY_LAST_RAW_MQTT, name="Last Raw MQTT Hex",
        icon="mdi:text-hexadecimal", entity_registry_enabled_default=False,
    ),
)

# --- Lớp LumentreeMqttSensor và hàm async_setup_entry ---
# (Giữ nguyên như phiên bản trước, không cần thay đổi gì ở đây
#  vì logic xử lý dispatcher và cắt chuỗi hex đã đúng)
async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    _LOGGER.debug(f"Setting up sensor platform for {entry.title}")
    device_sn = entry.data[CONF_DEVICE_SN]
    device_name = entry.data[CONF_DEVICE_NAME]
    device_info = DeviceInfo(
        identifiers={(DOMAIN, device_sn)},
        name=device_name,
        manufacturer="YS Tech (YiShen)",
    )
    entities = [
        LumentreeMqttSensor(hass, entry, device_info, description)
        for description in SENSOR_DESCRIPTIONS
    ]
    async_add_entities(entities)
    _LOGGER.info(f"Added {len(entities)} sensors for {entry.title}")

class LumentreeMqttSensor(SensorEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        device_info: DeviceInfo,
        description: SensorEntityDescription,
    ) -> None:
        self.hass = hass
        self.entity_description = description
        self._device_sn = entry.data[CONF_DEVICE_SN]
        self._attr_unique_id = f"{self._device_sn}_{description.key}"
        self._attr_device_info = device_info
        self._attr_native_value = None
        self._remove_dispatcher: Optional[Callable[[], None]] = None
        _LOGGER.debug(f"Initializing sensor: {self.unique_id}")

    @callback
    def _handle_update(self, data: Dict[str, Any]) -> None:
        if self.entity_description.key not in data: return
        new_value = data[self.entity_description.key]
        _LOGGER.debug(f"Sensor {self.unique_id} received update raw value: {new_value!r}")
        processed_value = None
        if new_value is not None:
            if self.entity_description.key == KEY_LAST_RAW_MQTT:
                processed_value = str(new_value)
                if len(processed_value) > 255:
                    processed_value = processed_value[:252] + "..."
            elif self.entity_description.state_class in [
                SensorStateClass.MEASUREMENT, SensorStateClass.TOTAL, SensorStateClass.TOTAL_INCREASING
            ]:
                try: processed_value = float(new_value)
                except (ValueError, TypeError): processed_value = None
            else:
                 processed_value = str(new_value)
                 if len(processed_value) > 255: processed_value = processed_value[:252] + "..."

        if self._attr_native_value != processed_value:
            self._attr_native_value = processed_value
            _LOGGER.debug(f"Updating state for {self.unique_id} to: {processed_value!r}")
            self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        _LOGGER.debug(f"Sensor {self.unique_id} added to hass. Registering dispatcher.")
        signal = SIGNAL_UPDATE_FORMAT.format(device_sn=self._device_sn)
        self._remove_dispatcher = async_dispatcher_connect(self.hass, signal, self._handle_update)

    async def async_will_remove_from_hass(self) -> None:
        _LOGGER.debug(f"Sensor {self.unique_id} removing from hass. Unregistering dispatcher.")
        if self._remove_dispatcher:
            self._remove_dispatcher()
            self._remove_dispatcher = None