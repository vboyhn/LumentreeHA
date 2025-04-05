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
        KEY_ONLINE_STATUS, KEY_IS_UPS_MODE # Thêm KEY_IS_UPS_MODE
    )
except ImportError:
    # Fallback
    DOMAIN = "lumentree"; import logging; _LOGGER = logging.getLogger(__name__)
    CONF_DEVICE_SN = "device_sn"; CONF_DEVICE_NAME = "device_name"; SIGNAL_UPDATE_FORMAT = "lumentree_mqtt_update_{device_sn}"
    KEY_ONLINE_STATUS = "online_status"; KEY_IS_UPS_MODE = "is_ups_mode"

# --- Định nghĩa mô tả Binary Sensor ---
BINARY_SENSOR_DESCRIPTIONS: tuple[BinarySensorEntityDescription, ...] = (
    BinarySensorEntityDescription(
        key=KEY_ONLINE_STATUS, # Key này do parser.py tự thêm vào
        name="Online Status",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
    ),
    BinarySensorEntityDescription(
        key=KEY_IS_UPS_MODE, # Đọc từ Reg 68
        name="UPS Mode",
        icon="mdi:power-plug-off-outline", # Icon ví dụ, có thể đổi
        # device_class=BinarySensorDeviceClass.RUNNING, # Hoặc POWER?
    ),
)

async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Lumentree binary sensor entities via MQTT."""
    _LOGGER.debug(f"Setting up binary_sensor platform for {entry.title}")
    device_sn = entry.data[CONF_DEVICE_SN]; device_name = entry.data[CONF_DEVICE_NAME]
    device_info = DeviceInfo(identifiers={(DOMAIN, device_sn)}, name=device_name, manufacturer="YS Tech (YiShen)")
    entities = [ LumentreeMqttBinarySensor(hass, entry, device_info, desc) for desc in BINARY_SENSOR_DESCRIPTIONS ]
    async_add_entities(entities)
    _LOGGER.info(f"Added {len(entities)} binary sensors for {entry.title}")

class LumentreeMqttBinarySensor(BinarySensorEntity):
    """Representation of a Lumentree binary sensor updated via MQTT."""
    _attr_has_entity_name = True; _attr_should_poll = False
    def __init__(self, hass, entry, device_info, description):
        self.hass = hass; self.entity_description = description; self._device_sn = entry.data[CONF_DEVICE_SN]
        self._attr_unique_id = f"{self._device_sn}_{description.key}"; self._attr_device_info = device_info
        self._attr_is_on = None; self._remove_dispatcher = None
    @callback
    def _handle_update(self, data: Dict[str, Any]) -> None:
        """Handle updates pushed from MQTT client."""
        new_state = None
        is_mqtt_update = False
        # Xử lý trạng thái kết nối MQTT đặc biệt
        if "mqtt_connected" in data:
            is_mqtt_update = True
            if self.entity_description.key == KEY_ONLINE_STATUS:
                new_state = data["mqtt_connected"] # Bool
                _LOGGER.debug(f"Binary sensor {self.unique_id} got MQTT connection status: {new_state}")
            elif not data["mqtt_connected"]:
                # Nếu mất kết nối MQTT, đặt các sensor khác thành Unknown/None
                new_state = None
        # Xử lý dữ liệu từ parser
        elif self.entity_description.key in data:
             val = data[self.entity_description.key]
             if isinstance(val, bool):
                 new_state = val
             else:
                 # Chuyển đổi các giá trị khác nếu cần (ví dụ: 1/0)
                 _LOGGER.warning(f"Unexpected state type for {self.unique_id}: {type(val)}. Expecting bool.")
                 new_state = None
        # Nếu không có key hoặc không phải update trạng thái MQTT, không làm gì
        else:
             return

        if self._attr_is_on != new_state:
             self._attr_is_on = new_state
             _LOGGER.debug(f"Updating state for {self.unique_id} to: {new_state}")
             self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        signal = SIGNAL_UPDATE_FORMAT.format(device_sn=self._device_sn)
        self._remove_dispatcher = async_dispatcher_connect(self.hass, signal, self._handle_update)
    async def async_will_remove_from_hass(self) -> None:
        if self._remove_dispatcher: self._remove_dispatcher()