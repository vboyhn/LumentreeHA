# /config/custom_components/lumentree/sensor.py
# Removed hardcoded names to use translations from strings.json

from typing import Any, Dict, Optional, Callable
import logging

from homeassistant.components.sensor import (
    SensorEntity, SensorEntityDescription, SensorDeviceClass, SensorStateClass
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfPower, UnitOfEnergy, PERCENTAGE, UnitOfTemperature, UnitOfElectricPotential,
    UnitOfFrequency, UnitOfElectricCurrent, UnitOfApparentPower,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator
)

try:
    from .const import (
        DOMAIN, _LOGGER, CONF_DEVICE_SN, CONF_DEVICE_NAME,
        SIGNAL_UPDATE_FORMAT,
        KEY_PV_POWER, KEY_BATTERY_POWER, KEY_BATTERY_SOC, KEY_GRID_POWER,
        KEY_LOAD_POWER, KEY_BATTERY_VOLTAGE, KEY_BATTERY_CURRENT, KEY_AC_OUT_VOLTAGE,
        KEY_GRID_VOLTAGE, KEY_AC_OUT_FREQ, KEY_AC_OUT_POWER, KEY_AC_OUT_VA,
        KEY_DEVICE_TEMP, KEY_PV1_VOLTAGE, KEY_PV1_POWER, KEY_PV2_VOLTAGE,
        KEY_PV2_POWER,
        KEY_DAILY_PV_KWH, KEY_DAILY_CHARGE_KWH, KEY_DAILY_DISCHARGE_KWH,
        KEY_DAILY_GRID_IN_KWH, KEY_DAILY_LOAD_KWH,
        KEY_LAST_RAW_MQTT
    )
    from .coordinator_stats import LumentreeStatsCoordinator
except ImportError:
    # Fallback
    DOMAIN = "lumentree"; _LOGGER = logging.getLogger(__name__)
    CONF_DEVICE_SN = "device_sn"; CONF_DEVICE_NAME = "device_name"; SIGNAL_UPDATE_FORMAT = "lumentree_mqtt_update_{device_sn}"
    KEY_PV_POWER="pv_power"; KEY_BATTERY_POWER="battery_power"; KEY_BATTERY_SOC="battery_soc"; KEY_GRID_POWER="grid_power"; KEY_LOAD_POWER="load_power"; KEY_BATTERY_VOLTAGE="battery_voltage"; KEY_BATTERY_CURRENT="battery_current"; KEY_AC_OUT_VOLTAGE="ac_output_voltage"; KEY_GRID_VOLTAGE="grid_voltage"; KEY_AC_OUT_FREQ="ac_output_frequency"; KEY_AC_OUT_POWER="ac_output_power"; KEY_AC_OUT_VA="ac_output_va"; KEY_DEVICE_TEMP="device_temperature"; KEY_PV1_VOLTAGE="pv1_voltage"; KEY_PV1_POWER="pv1_power"; KEY_PV2_VOLTAGE="pv2_voltage"; KEY_PV2_POWER="pv2_power"; KEY_LAST_RAW_MQTT="last_raw_mqtt_hex"
    KEY_DAILY_PV_KWH="pv_today"; KEY_DAILY_CHARGE_KWH="charge_today"; KEY_DAILY_DISCHARGE_KWH="discharge_today"; KEY_DAILY_GRID_IN_KWH="grid_in_today"; KEY_DAILY_LOAD_KWH="load_today"
    class LumentreeStatsCoordinator: pass


# --- Định nghĩa mô tả Sensor TỨC THỜI (MQTT) - Bỏ thuộc tính 'name' ---
REALTIME_SENSOR_DESCRIPTIONS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(key=KEY_PV_POWER, native_unit_of_measurement=UnitOfPower.WATT, device_class=SensorDeviceClass.POWER, state_class=SensorStateClass.MEASUREMENT, icon="mdi:solar-power"),
    SensorEntityDescription(key=KEY_BATTERY_POWER, native_unit_of_measurement=UnitOfPower.WATT, device_class=SensorDeviceClass.POWER, state_class=SensorStateClass.MEASUREMENT, icon="mdi:battery"),
    SensorEntityDescription(key=KEY_BATTERY_SOC, native_unit_of_measurement=PERCENTAGE, device_class=SensorDeviceClass.BATTERY, state_class=SensorStateClass.MEASUREMENT),
    SensorEntityDescription(key=KEY_GRID_POWER, native_unit_of_measurement=UnitOfPower.WATT, device_class=SensorDeviceClass.POWER, state_class=SensorStateClass.MEASUREMENT, icon="mdi:transmission-tower"),
    SensorEntityDescription(key=KEY_LOAD_POWER, native_unit_of_measurement=UnitOfPower.WATT, device_class=SensorDeviceClass.POWER, state_class=SensorStateClass.MEASUREMENT, icon="mdi:power-plug"),
    SensorEntityDescription(key=KEY_BATTERY_VOLTAGE, native_unit_of_measurement=UnitOfElectricPotential.VOLT, device_class=SensorDeviceClass.VOLTAGE, state_class=SensorStateClass.MEASUREMENT, icon="mdi:battery-outline", suggested_display_precision=2),
    SensorEntityDescription(key=KEY_BATTERY_CURRENT, native_unit_of_measurement=UnitOfElectricCurrent.AMPERE, device_class=SensorDeviceClass.CURRENT, state_class=SensorStateClass.MEASUREMENT, icon="mdi:current-dc", suggested_display_precision=2),
    SensorEntityDescription(key=KEY_AC_OUT_VOLTAGE, native_unit_of_measurement=UnitOfElectricPotential.VOLT, device_class=SensorDeviceClass.VOLTAGE, state_class=SensorStateClass.MEASUREMENT, suggested_display_precision=1),
    SensorEntityDescription(key=KEY_GRID_VOLTAGE, native_unit_of_measurement=UnitOfElectricPotential.VOLT, device_class=SensorDeviceClass.VOLTAGE, state_class=SensorStateClass.MEASUREMENT, suggested_display_precision=1),
    SensorEntityDescription(key=KEY_AC_OUT_FREQ, native_unit_of_measurement=UnitOfFrequency.HERTZ, device_class=SensorDeviceClass.FREQUENCY, state_class=SensorStateClass.MEASUREMENT, suggested_display_precision=2),
    SensorEntityDescription(key=KEY_AC_OUT_POWER, native_unit_of_measurement=UnitOfPower.WATT, device_class=SensorDeviceClass.POWER, state_class=SensorStateClass.MEASUREMENT),
    SensorEntityDescription(key=KEY_AC_OUT_VA, native_unit_of_measurement=UnitOfApparentPower.VOLT_AMPERE, device_class=SensorDeviceClass.APPARENT_POWER, state_class=SensorStateClass.MEASUREMENT),
    SensorEntityDescription(key=KEY_DEVICE_TEMP, native_unit_of_measurement=UnitOfTemperature.CELSIUS, device_class=SensorDeviceClass.TEMPERATURE, state_class=SensorStateClass.MEASUREMENT, suggested_display_precision=1),
    SensorEntityDescription(key=KEY_PV1_VOLTAGE, native_unit_of_measurement=UnitOfElectricPotential.VOLT, device_class=SensorDeviceClass.VOLTAGE, state_class=SensorStateClass.MEASUREMENT),
    SensorEntityDescription(key=KEY_PV1_POWER, native_unit_of_measurement=UnitOfPower.WATT, device_class=SensorDeviceClass.POWER, state_class=SensorStateClass.MEASUREMENT),
    SensorEntityDescription(key=KEY_PV2_VOLTAGE, native_unit_of_measurement=UnitOfElectricPotential.VOLT, device_class=SensorDeviceClass.VOLTAGE, state_class=SensorStateClass.MEASUREMENT, entity_registry_enabled_default=False),
    SensorEntityDescription(key=KEY_PV2_POWER, native_unit_of_measurement=UnitOfPower.WATT, device_class=SensorDeviceClass.POWER, state_class=SensorStateClass.MEASUREMENT, entity_registry_enabled_default=False),
    SensorEntityDescription(key=KEY_LAST_RAW_MQTT, icon="mdi:text-hexadecimal", entity_registry_enabled_default=False), # Không cần tên cho sensor debug này
)

# --- Định nghĩa mô tả Sensor THỐNG KÊ NGÀY (HTTP API) - Bỏ thuộc tính 'name' ---
STATS_SENSOR_DESCRIPTIONS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key=KEY_DAILY_PV_KWH,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        icon="mdi:solar-power",
        suggested_display_precision=1,
    ),
    SensorEntityDescription(
        key=KEY_DAILY_CHARGE_KWH,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        icon="mdi:battery-plus-variant",
        suggested_display_precision=1,
    ),
    SensorEntityDescription(
        key=KEY_DAILY_DISCHARGE_KWH,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        icon="mdi:battery-minus-variant",
        suggested_display_precision=1,
    ),
    SensorEntityDescription(
        key=KEY_DAILY_GRID_IN_KWH,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        icon="mdi:transmission-tower-import",
        suggested_display_precision=1,
    ),
     SensorEntityDescription(
        key=KEY_DAILY_LOAD_KWH,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        icon="mdi:home-lightning-bolt",
        suggested_display_precision=1,
    ),
)
# ------------------------------------------------------

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Lumentree sensor entities from config entry."""
    _LOGGER.debug(f"Setting up sensor platform for {entry.title}")
    try:
        entry_data = hass.data[DOMAIN][entry.entry_id]
        coordinator_stats: LumentreeStatsCoordinator = entry_data.get("coordinator_stats")
    except KeyError:
        _LOGGER.error(f"Lumentree data not found for entry {entry.entry_id}. Setup failed?")
        return

    device_sn = entry.data[CONF_DEVICE_SN]
    device_name = entry.data[CONF_DEVICE_NAME] # Vẫn lấy tên thiết bị chung

    device_info = DeviceInfo(
        identifiers={(DOMAIN, device_sn)},
        name=device_name, # Tên của device registry
        manufacturer="YS Tech (YiShen)",
    )

    entities_to_add: list[SensorEntity] = []

    # --- Tạo các Sensor Real-time (MQTT) ---
    for description in REALTIME_SENSOR_DESCRIPTIONS:
         # Truyền device_info và description
         entities_to_add.append(LumentreeMqttSensor(hass, entry, device_info, description))
    _LOGGER.info(f"Adding {len(REALTIME_SENSOR_DESCRIPTIONS)} real-time sensors")

    # --- Tạo các Sensor Thống kê Ngày (HTTP API) ---
    if coordinator_stats:
        initial_stats_data = coordinator_stats.data or {}
        added_stats_keys = set()

        for description in STATS_SENSOR_DESCRIPTIONS:
            if description.key in initial_stats_data and description.key not in added_stats_keys:
                 # Truyền coordinator, device_info và description
                 entities_to_add.append(LumentreeDailyStatsSensor(coordinator_stats, device_info, description))
                 added_stats_keys.add(description.key)
                 _LOGGER.debug(f"Adding stats sensor {description.key}")

        _LOGGER.info(f"Adding {len(added_stats_keys)} daily stats sensors")
    else:
        _LOGGER.warning("Stats Coordinator not available, skipping daily stats sensors.")

    if entities_to_add:
        async_add_entities(entities_to_add)
    else:
        _LOGGER.warning("No sensors were added.")


# --- Lớp Sensor Real-time (MQTT) ---
# Thêm _attr_has_entity_name = True để HA tự tìm tên từ key
class LumentreeMqttSensor(SensorEntity):
    _attr_has_entity_name = True # <<< THÊM DÒNG NÀY
    _attr_should_poll = False

    # ... (Phần còn lại của lớp LumentreeMqttSensor giữ nguyên) ...
    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        device_info: DeviceInfo,
        description: SensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        self.hass = hass
        self.entity_description = description
        self._device_sn = entry.data[CONF_DEVICE_SN]
        self._attr_unique_id = f"{self._device_sn}_{description.key}"
        self._attr_device_info = device_info
        self._attr_native_value = None
        self._remove_dispatcher: Optional[Callable[[], None]] = None
        _LOGGER.debug(f"Initializing MQTT sensor: {self.unique_id}")

    @callback
    def _handle_update(self, data: Dict[str, Any]) -> None:
        """Handle updates pushed from MQTT client via dispatcher."""
        if self.entity_description.key not in data: return
        new_value = data[self.entity_description.key]
        _LOGGER.debug(f"MQTT Sensor {self.unique_id} received update: {new_value!r}")
        processed_value = None
        if new_value is not None:
            if self.entity_description.key == KEY_LAST_RAW_MQTT:
                processed_value = str(new_value); processed_value = processed_value[:252] + "..." if len(processed_value) > 255 else processed_value
            elif self.entity_description.state_class in [SensorStateClass.MEASUREMENT, SensorStateClass.TOTAL, SensorStateClass.TOTAL_INCREASING]:
                try: processed_value = float(new_value)
                except (ValueError, TypeError): processed_value = None
            else: processed_value = str(new_value); processed_value = processed_value[:252] + "..." if len(processed_value) > 255 else processed_value
        if self._attr_native_value != processed_value:
            self._attr_native_value = processed_value; self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Register callbacks when entity is added."""
        signal = SIGNAL_UPDATE_FORMAT.format(device_sn=self._device_sn)
        self._remove_dispatcher = async_dispatcher_connect(self.hass, signal, self._handle_update)
        _LOGGER.debug(f"MQTT sensor {self.unique_id} registered dispatcher.")

    async def async_will_remove_from_hass(self) -> None:
        """Unregister callbacks when entity is removed."""
        if self._remove_dispatcher: self._remove_dispatcher(); self._remove_dispatcher = None
        _LOGGER.debug(f"MQTT sensor {self.unique_id} unregistered dispatcher.")

# --- LỚP SENSOR THỐNG KÊ NGÀY (HTTP API) ---
# Lớp này đã có _attr_has_entity_name = True rồi
class LumentreeDailyStatsSensor(CoordinatorEntity[LumentreeStatsCoordinator], SensorEntity):
    _attr_has_entity_name = True

    # ... (Phần còn lại của lớp LumentreeDailyStatsSensor giữ nguyên) ...
    def __init__(
        self,
        coordinator: LumentreeStatsCoordinator,
        device_info: DeviceInfo,
        description: SensorEntityDescription
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._device_sn = coordinator.device_sn
        self._attr_unique_id = f"{self._device_sn}_{description.key}"
        self._attr_device_info = device_info
        self._attr_attribution = "Data fetched via Lumentree HTTP API"
        self._update_state_from_coordinator()
        _LOGGER.debug(f"Initializing Stats sensor: {self.unique_id} with init value: {self.native_value}")

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._update_state_from_coordinator()
        _LOGGER.debug(f"Stats sensor {self.unique_id} received coordinator update: {self.native_value}")
        self.async_write_ha_state()

    def _update_state_from_coordinator(self) -> None:
        """Update the entity state from coordinator data."""
        key = self.entity_description.key
        value = None
        if self.coordinator.data:
            value = self.coordinator.data.get(key)
        if isinstance(value, (int, float)):
             self._attr_native_value = value
        else:
             if value is not None:
                  _LOGGER.warning(f"Unexpected data type '{type(value)}' for stats sensor {self.unique_id}")
             self._attr_native_value = None