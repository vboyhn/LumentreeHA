# /config/custom_components/lumentree/binary_sensor.py

from typing import Any, Dict, Optional, Callable

from homeassistant.components.binary_sensor import (
    BinarySensorEntity, BinarySensorEntityDescription, BinarySensorDeviceClass
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

try:
    from .const import (
        DOMAIN, _LOGGER, CONF_DEVICE_SN, CONF_DEVICE_NAME, SIGNAL_UPDATE_FORMAT,
        KEY_ONLINE_STATUS # Key cho trạng thái online
    )
except ImportError:
    from const import (
        DOMAIN, _LOGGER, CONF_DEVICE_SN, CONF_DEVICE_NAME, SIGNAL_UPDATE_FORMAT,
        KEY_ONLINE_STATUS
    )

# --- Định nghĩa mô tả Binary Sensor ---
BINARY_SENSOR_DESCRIPTIONS: tuple[BinarySensorEntityDescription, ...] = (
    BinarySensorEntityDescription(
        key=KEY_ONLINE_STATUS, # Key này phải khớp với key parser trả về
        name="Online Status",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
    ),
    # Thêm binary sensor khác nếu parser trả về key tương ứng
)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Lumentree binary sensor entities via MQTT."""
    _LOGGER.debug(f"Setting up binary_sensor platform for {entry.title}")
    device_sn = entry.data[CONF_DEVICE_SN]
    device_name = entry.data[CONF_DEVICE_NAME]

    device_info = DeviceInfo(
        identifiers={(DOMAIN, device_sn)},
        name=device_name,
        manufacturer="YS Tech (YiShen)",
    )

    entities = [
        LumentreeMqttBinarySensor(hass, entry, device_info, description)
        for description in BINARY_SENSOR_DESCRIPTIONS
    ]

    async_add_entities(entities)
    _LOGGER.info(f"Added {len(entities)} binary sensors for {entry.title}")

class LumentreeMqttBinarySensor(BinarySensorEntity):
    """Representation of a Lumentree binary sensor updated via MQTT."""

    _attr_has_entity_name = True
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

        self._attr_unique_id = f"{self._device_sn}_{description.key}"
        self._attr_device_info = device_info
        self._attr_is_on = None # Trạng thái ban đầu là unknown
        self._remove_dispatcher: Optional[Callable[[], None]] = None

        _LOGGER.debug(f"Initializing binary_sensor: {self.unique_id}")

    @callback
    def _handle_update(self, data: Dict[str, Any]) -> None:
        """Handle updates pushed from MQTT client."""
        if self.entity_description.key in data:
            new_state = data[self.entity_description.key]
            _LOGGER.debug(f"Binary sensor {self.unique_id} received update: {new_state}")
            if isinstance(new_state, bool):
                self._attr_is_on = new_state
            else:
                # Xử lý trường hợp khác nếu cần (ví dụ "1"/"0")
                _LOGGER.warning(f"Unexpected state type for {self.unique_id}: {type(new_state)}. Expecting bool.")
                self._attr_is_on = None # Đặt là unknown nếu không đúng kiểu
            self.async_write_ha_state()
        # Thêm logic xử lý khi nhận được trạng thái "mqtt_connected": False?
        elif "mqtt_connected" in data and not data["mqtt_connected"]:
             _LOGGER.warning(f"MQTT disconnected for {self._device_sn}, setting {self.unique_id} to unknown")
             self._attr_is_on = None # Đặt là unknown khi mất kết nối MQTT
             self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Register callbacks when entity is added."""
        _LOGGER.debug(f"Binary sensor {self.unique_id} added to hass. Registering dispatcher.")
        signal = SIGNAL_UPDATE_FORMAT.format(device_sn=self._device_sn)
        self._remove_dispatcher = async_dispatcher_connect(
            self.hass, signal, self._handle_update
        )

    async def async_will_remove_from_hass(self) -> None:
        """Unregister callbacks when entity is removed."""
        _LOGGER.debug(f"Binary sensor {self.unique_id} removing from hass. Unregistering dispatcher.")
        if self._remove_dispatcher:
            self._remove_dispatcher()
            self._remove_dispatcher = None