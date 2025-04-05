# /config/custom_components/lumentree/binary_sensor.py
# Attempting entity_id format: device_{SN}_{key} using object_id

import logging
from typing import Any, Dict, Optional, Callable
import re

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
    BinarySensorDeviceClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
# Import generate_entity_id và slugify
from homeassistant.helpers.entity import DeviceInfo, generate_entity_id
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.template import slugify


try:
    from .const import DOMAIN, _LOGGER, CONF_DEVICE_SN, CONF_DEVICE_NAME, SIGNAL_UPDATE_FORMAT, KEY_ONLINE_STATUS, KEY_IS_UPS_MODE
except ImportError:
    DOMAIN = "lumentree"; _LOGGER = logging.getLogger(__name__)
    CONF_DEVICE_SN = "device_sn"; CONF_DEVICE_NAME = "device_name"
    SIGNAL_UPDATE_FORMAT = "lumentree_mqtt_update_{device_sn}"
    KEY_IS_UPS_MODE = "is_ups_mode"; KEY_ONLINE_STATUS="online_status"
    def slugify(text): return re.sub(r"[^a-z0-9_]+", "_", text.lower())


BINARY_SENSOR_DESCRIPTIONS: tuple[BinarySensorEntityDescription, ...] = (
    BinarySensorEntityDescription(key=KEY_ONLINE_STATUS, name="Online Status", device_class=BinarySensorDeviceClass.CONNECTIVITY, entity_registry_enabled_default=True),
    BinarySensorEntityDescription(key=KEY_IS_UPS_MODE, name="UPS Mode", icon="mdi:power-plug-outline", device_class=None, entity_registry_enabled_default=True),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    # ... (Giữ nguyên) ...
    _LOGGER.debug(f"Setting up binary sensor platform for {entry.title}")
    device_sn = entry.data[CONF_DEVICE_SN]
    device_name = entry.data[CONF_DEVICE_NAME]
    device_info = DeviceInfo( identifiers={(DOMAIN, device_sn)}, name=device_name, manufacturer="YS Tech (YiShen)" )
    entities = [ LumentreeBinarySensor(hass, entry, device_info, description) for description in BINARY_SENSOR_DESCRIPTIONS ]
    if entities: async_add_entities(entities); _LOGGER.info(f"Added {len(entities)} binary sensors")


class LumentreeBinarySensor(BinarySensorEntity):
    _attr_should_poll = False

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

        # 1. Unique ID
        self._attr_unique_id = f"{self._device_sn}_{description.key}" # Giữ key ở cuối để HA không tự thêm số

        # 2. Object ID
        # Giữ nguyên chữ hoa/thường của SN
        object_id = f"device_{self._device_sn}_{slugify(description.key)}"
        # Hoặc nếu muốn SN viết thường:
        # object_id = slugify(f"device_{self._device_sn}_{description.key}")
        self._attr_object_id = object_id

        # 3. Entity ID
        self.entity_id = generate_entity_id(
            "binary_sensor.{}", self._attr_object_id, hass=hass
        )

        self._attr_device_info = device_info
        self._attr_is_on = None
        self._remove_dispatcher: Optional[Callable] = None
        _LOGGER.debug(f"Initializing binary sensor: unique_id={self.unique_id}, entity_id={self.entity_id}, name={self.name}")

    # ... (Phần còn lại của lớp giữ nguyên) ...
    @callback
    def _handle_update(self, data: Dict[str, Any]) -> None:
        if self.entity_description.key in data:
            new_state = data[self.entity_description.key]
            if isinstance(new_state, bool):
                if self._attr_is_on != new_state:
                    self._attr_is_on = new_state; self.async_write_ha_state()
            else: _LOGGER.warning(f"Received non-boolean value for binary sensor {self.unique_id} ({self.name}): {new_state}")

    async def async_added_to_hass(self) -> None:
        signal = SIGNAL_UPDATE_FORMAT.format(device_sn=self._device_sn)
        self._remove_dispatcher = async_dispatcher_connect( self.hass, signal, self._handle_update )
        _LOGGER.debug(f"Binary sensor {self.unique_id} ({self.name}) registered dispatcher.")

    async def async_will_remove_from_hass(self) -> None:
        if self._remove_dispatcher: self._remove_dispatcher()
        _LOGGER.debug(f"Binary sensor {self.unique_id} ({self.name}) unregistered dispatcher.")