# /config/custom_components/lumentree/binary_sensor.py
# Removed hardcoded names to use translations

import logging
from typing import Any, Dict, Optional, Callable

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
    BinarySensorDeviceClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

try:
    from .const import DOMAIN, _LOGGER, CONF_DEVICE_SN, CONF_DEVICE_NAME, SIGNAL_UPDATE_FORMAT, KEY_ONLINE_STATUS, KEY_IS_UPS_MODE
except ImportError:
    DOMAIN = "lumentree"; _LOGGER = logging.getLogger(__name__)
    CONF_DEVICE_SN = "device_sn"; CONF_DEVICE_NAME = "device_name"
    SIGNAL_UPDATE_FORMAT = "lumentree_mqtt_update_{device_sn}"
    KEY_IS_UPS_MODE = "is_ups_mode"; KEY_ONLINE_STATUS="online_status"


# --- Định nghĩa mô tả Binary Sensor - Bỏ thuộc tính 'name' ---
BINARY_SENSOR_DESCRIPTIONS: tuple[BinarySensorEntityDescription, ...] = (
    BinarySensorEntityDescription( # Trạng thái kết nối MQTT (từ mqtt.py)
        key=KEY_ONLINE_STATUS, # Key này được gửi từ LumentreeMqttClient
        # name="Online Status", # <<< XÓA DÒNG NÀY
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_registry_enabled_default=True,
    ),
     BinarySensorEntityDescription( # Trạng thái UPS mode (từ parser.py)
        key=KEY_IS_UPS_MODE,
        # name="UPS Mode", # <<< XÓA DÒNG NÀY
        icon="mdi:power-plug-outline", # Hoặc icon khác phù hợp
        device_class=None, # Không có device class chuẩn
        entity_registry_enabled_default=True,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Lumentree binary sensor entities."""
    _LOGGER.debug(f"Setting up binary sensor platform for {entry.title}")

    device_sn = entry.data[CONF_DEVICE_SN]
    device_name = entry.data[CONF_DEVICE_NAME]

    device_info = DeviceInfo(
        identifiers={(DOMAIN, device_sn)},
        name=device_name,
        manufacturer="YS Tech (YiShen)",
    )

    entities = [
        LumentreeBinarySensor(hass, entry, device_info, description)
        for description in BINARY_SENSOR_DESCRIPTIONS
    ]

    if entities:
        async_add_entities(entities)
        _LOGGER.info(f"Added {len(entities)} binary sensors for {entry.title}")


# Thêm _attr_has_entity_name = True để HA tự tìm tên từ key
class LumentreeBinarySensor(BinarySensorEntity):
    """Representation of a Lumentree binary sensor."""

    _attr_has_entity_name = True # <<< THÊM DÒNG NÀY
    _attr_should_poll = False # Data is pushed via dispatcher

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        device_info: DeviceInfo,
        description: BinarySensorEntityDescription,
    ) -> None:
        """Initialize the binary sensor."""
        self.hass = hass
        self.entity_description = description
        self._device_sn = entry.data[CONF_DEVICE_SN]

        self._attr_unique_id = f"{self._device_sn}_{description.key}"
        self._attr_device_info = device_info
        self._attr_is_on = None # Trạng thái ban đầu
        self._remove_dispatcher: Optional[Callable] = None

        _LOGGER.debug(f"Initializing binary sensor: {self.unique_id}")

    @callback
    def _handle_update(self, data: Dict[str, Any]) -> None:
        """Handle updates pushed from the MQTT client."""
        if self.entity_description.key in data:
            new_state = data[self.entity_description.key]
            _LOGGER.debug(f"Binary sensor {self.unique_id} received update: {new_state}")
            if isinstance(new_state, bool): # Đảm bảo giá trị là boolean
                if self._attr_is_on != new_state:
                    self._attr_is_on = new_state
                    self.async_write_ha_state()
            else:
                 _LOGGER.warning(f"Received non-boolean value for binary sensor {self.unique_id}: {new_state}")

    async def async_added_to_hass(self) -> None:
        """Register dispatcher listener."""
        signal = SIGNAL_UPDATE_FORMAT.format(device_sn=self._device_sn)
        self._remove_dispatcher = async_dispatcher_connect(
            self.hass, signal, self._handle_update
        )
        _LOGGER.debug(f"Binary sensor {self.unique_id} registered dispatcher.")
        # Có thể cần yêu cầu update ban đầu nếu trạng thái không được gửi ngay
        # await self.hass.services.async_call(...)

    async def async_will_remove_from_hass(self) -> None:
        """Disconnect dispatcher listener when removed."""
        if self._remove_dispatcher:
            self._remove_dispatcher()
        _LOGGER.debug(f"Binary sensor {self.unique_id} unregistered dispatcher.")