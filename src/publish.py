"""Pubish module."""

from __future__ import annotations

import asyncio
import json
import logging
import math
from enum import Enum
from typing import Any, Final, Sequence

import asyncio_paho
import box
import slugify as unicode_slug

import common

# Home Assistant constants
HASS_COMPONENT_BINARY_SENSOR: Final = "binary_sensor"
HASS_COMPONENT_SENSOR: Final = "sensor"
HASS_DEVICE_CLASS_CONNECTIVITY: Final = "connectivity"
HASS_ENTITY_CATEGORY_DIAGNOSTIC: Final = "diagnostic"
HASS_STATE_CLASS_MEASUREMENT: Final = "measurement"
HASS_STATE_CLASS_TOTAL_INCREASING: Final = "total_increasing"
HASS_STATE_CONNECTED: Final = "ON"
HASS_STATE_DISCONNECTED: Final = "OFF"
HASS_STATE_UNAVAILABLE: Final = "unavailable"
HASS_UNIT_DATA_BYTES: Final = "B"
HASS_UNIT_PERCENTAGE: Final = "%"
HASS_UNIT_TIME_MILLISECONDS: Final = "ms"

HASS_CONF_DEVICE_CLASS: Final = "device_class"
HASS_CONF_DEVICE: Final = "device"
HASS_CONF_ENTITY_CATEGORY: Final = "entity_category"
HASS_CONF_EXPIRE_AFTER = "expire_after"
HASS_CONF_FORCE_UPDATE: Final = "force_update"
HASS_CONF_ICON: Final = "icon"
HASS_CONF_NAME: Final = "name"
HASS_CONF_STATE_CLASS: Final = "state_class"
HASS_CONF_STATE_TOPIC: Final = "state_topic"
HASS_CONF_UNIQUE_ID: Final = "unique_id"
HASS_CONF_UNIT_OF_MEASUREMENT: Final = "unit_of_measurement"

HASS_ATTR_IDENTIFIERS: Final = "identifiers"
HASS_ATTR_MANUFACTURER: Final = "manufacturer"
HASS_ATTR_MODEL: Final = "model"
HASS_ATTR_NAME: Final = "name"
HASS_ATTR_SUGGESTED_AREA: Final = "suggested_area"
HASS_ATTR_SW_VERSION: Final = "sw_version"

ICON_TIMER: Final = "mdi:timer"
ICON_NETWORK_DOWNLOAD: Final = "mdi:download-network"
ICON_NETWORK_UPLOAD: Final = "mdi:upload-network"
ICON_PACKET_LOSS: Final = "mdi:close-network"

REQUIRED_AVERAGE_HISTORY_PERCENT: Final = 40

logger = logging.getLogger(__name__)


def slugify(text: str | None, *, separator: str = "_") -> str:
    """Slugify a given text."""
    if text == "" or text is None:
        return ""
    slug = unicode_slug.slugify(text, separator=separator)
    return "unknown" if slug == "" else slug


class HassEntity:
    """Home Assistant Entity."""

    def __init__(  # pylint: disable=too-many-arguments
        self,
        mqtt: asyncio_paho.AsyncioPahoClient,
        component: str,
        node_id: str,
        object_id: str,
        hass_config: dict[str, Any],
        update_interval: float | None = None,
    ) -> None:
        """Initialize HassEntity."""
        self._mqtt = mqtt
        self._component = component
        base_topic = (
            f"homeassistant/{component}/{slugify(node_id)}/{slugify(object_id)}"
        )
        self.config_topic = f"{base_topic}/config"
        self.state_topic = f"{base_topic}/state"

        self._hass_config = {
            HASS_CONF_NAME: object_id,
            HASS_CONF_FORCE_UPDATE: True,
            HASS_CONF_STATE_TOPIC: self.state_topic,
            HASS_CONF_UNIQUE_ID: slugify(f"{node_id}_{object_id}"),
            HASS_CONF_DEVICE: {HASS_ATTR_IDENTIFIERS: node_id},
        }
        if update_interval is not None:
            self._hass_config[HASS_CONF_EXPIRE_AFTER] = math.ceil(update_interval + 2)

        if hass_config:
            self._hass_config = {**self._hass_config, **hass_config}

    async def send_configuration(self) -> None:
        """Send configuration to MQTT discovery topic."""
        config_str = json.dumps(self._hass_config)
        logger.debug(
            "Publish %s config to topic %s: %s",
            self._component,
            self.config_topic,
            config_str,
        )
        await self._mqtt.asyncio_publish(
            self.config_topic, json.dumps(self._hass_config), retain=True
        )

    async def send_state(self, value: Any, qos: int = 0, retain: bool = False) -> None:
        """Send state to MQTT topic."""
        logger.debug(
            "Publish %s state %s to topic %s",
            self._component,
            value,
            self.state_topic,
        )
        try:
            await self._mqtt.asyncio_publish(str(self.state_topic), value, qos, retain)
        except Exception as ex:  # pylint: disable=broad-except
            logger.warning(
                "Error publishing %s state to topic %s: %s",
                self._component,
                self.state_topic,
                ex,
            )


class SensorCode(Enum):
    """Sensor code."""

    RTT = "rtt"
    RTT_AVERAGE = "average rtt"
    AVERAGE_LOSS = "average loss"
    JITTER = "jitter"
    JITTER_GRADE = "jitter grade"
    CONNECTIVITY = "connectivity"
    BYTES_SENT = "bytes sent"
    BYTES_RECEIVED = "bytes received"


class ProbePublisher:
    """Probe mqtt publisher."""

    def __init__(
        self,
        probe: common.ProbeBase,
        mqtt: asyncio_paho.AsyncioPahoClient,
        node_id: str,
    ) -> None:
        """Initialize ProbePublisher."""
        self._probe = probe
        self._mqtt = mqtt

        update_interval = self._probe.probe_config.interval

        base_object_id = f"{probe.probe_type} {probe.name}"
        self._sensors = {
            SensorCode.RTT: HassEntity(
                mqtt,
                HASS_COMPONENT_SENSOR,
                node_id,
                f"{base_object_id} {SensorCode.RTT.value}",
                {
                    HASS_CONF_ICON: ICON_TIMER,
                    HASS_CONF_UNIT_OF_MEASUREMENT: HASS_UNIT_TIME_MILLISECONDS,
                    HASS_CONF_STATE_CLASS: HASS_STATE_CLASS_MEASUREMENT,
                },
                update_interval,
            ),
            SensorCode.RTT_AVERAGE: HassEntity(
                mqtt,
                HASS_COMPONENT_SENSOR,
                node_id,
                f"{base_object_id} {SensorCode.RTT_AVERAGE.value}",
                {
                    HASS_CONF_ICON: ICON_TIMER,
                    HASS_CONF_UNIT_OF_MEASUREMENT: HASS_UNIT_TIME_MILLISECONDS,
                    HASS_CONF_STATE_CLASS: HASS_STATE_CLASS_MEASUREMENT,
                },
                update_interval,
            ),
            SensorCode.AVERAGE_LOSS: HassEntity(
                mqtt,
                HASS_COMPONENT_SENSOR,
                node_id,
                f"{base_object_id} {SensorCode.AVERAGE_LOSS.value}",
                {
                    HASS_CONF_ICON: ICON_PACKET_LOSS,
                    HASS_CONF_UNIT_OF_MEASUREMENT: HASS_UNIT_PERCENTAGE,
                    HASS_CONF_STATE_CLASS: HASS_STATE_CLASS_MEASUREMENT,
                },
                update_interval,
            ),
            SensorCode.JITTER: HassEntity(
                mqtt,
                HASS_COMPONENT_SENSOR,
                node_id,
                f"{base_object_id} {SensorCode.JITTER.value}",
                {
                    HASS_CONF_ICON: ICON_TIMER,
                    HASS_CONF_UNIT_OF_MEASUREMENT: HASS_UNIT_TIME_MILLISECONDS,
                    HASS_CONF_STATE_CLASS: HASS_STATE_CLASS_MEASUREMENT,
                },
                update_interval,
            ),
            SensorCode.JITTER_GRADE: HassEntity(
                mqtt,
                HASS_COMPONENT_SENSOR,
                node_id,
                f"{base_object_id} {SensorCode.JITTER_GRADE.value}",
                {
                    HASS_CONF_UNIT_OF_MEASUREMENT: HASS_UNIT_PERCENTAGE,
                    HASS_CONF_STATE_CLASS: HASS_STATE_CLASS_MEASUREMENT,
                },
                update_interval,
            ),
            SensorCode.CONNECTIVITY: HassEntity(
                mqtt,
                HASS_COMPONENT_BINARY_SENSOR,
                node_id,
                f"{base_object_id} {SensorCode.CONNECTIVITY.value}",
                {
                    HASS_CONF_DEVICE_CLASS: HASS_DEVICE_CLASS_CONNECTIVITY,
                },
                update_interval,
            ),
            SensorCode.BYTES_SENT: HassEntity(
                mqtt,
                HASS_COMPONENT_SENSOR,
                node_id,
                f"{base_object_id} {SensorCode.BYTES_SENT.value}",
                {
                    HASS_CONF_ICON: ICON_NETWORK_UPLOAD,
                    HASS_CONF_ENTITY_CATEGORY: HASS_ENTITY_CATEGORY_DIAGNOSTIC,
                    HASS_CONF_UNIT_OF_MEASUREMENT: HASS_UNIT_DATA_BYTES,
                    HASS_CONF_STATE_CLASS: HASS_STATE_CLASS_TOTAL_INCREASING,
                },
                update_interval,
            ),
            SensorCode.BYTES_RECEIVED: HassEntity(
                mqtt,
                HASS_COMPONENT_SENSOR,
                node_id,
                f"{base_object_id} {SensorCode.BYTES_RECEIVED.value}",
                {
                    HASS_CONF_ICON: ICON_NETWORK_DOWNLOAD,
                    HASS_CONF_ENTITY_CATEGORY: HASS_ENTITY_CATEGORY_DIAGNOSTIC,
                    HASS_CONF_UNIT_OF_MEASUREMENT: HASS_UNIT_DATA_BYTES,
                    HASS_CONF_STATE_CLASS: HASS_STATE_CLASS_TOTAL_INCREASING,
                },
                update_interval,
            ),
        }

    async def send_configuration(self) -> None:
        """Send configuration to MQTT discovery topic."""
        await asyncio.gather(
            *[sensor.send_configuration() for sensor in self._sensors.values()]
        )

    async def send_state(self) -> None:
        """Send measurement to MQTT topic."""
        precision = self._probe.probe_config.publish_precision

        def to_hass_numeric(value: float | None) -> float | str:
            if value is None:
                return HASS_STATE_UNAVAILABLE
            return round(value, precision) if precision > 0 else round(value)

        pub_tasks = []

        if (
            self._probe.state.current is not None
            and self._probe.state.current.rtt is not None
        ):
            pub_tasks.append(
                self._sensors[SensorCode.RTT].send_state(
                    to_hass_numeric(self._probe.state.current.rtt)
                )
            )
            pub_tasks.append(
                self._sensors[SensorCode.CONNECTIVITY].send_state(HASS_STATE_CONNECTED)
            )
        else:
            pub_tasks.append(
                self._sensors[SensorCode.CONNECTIVITY].send_state(
                    HASS_STATE_DISCONNECTED
                )
            )

        if self._probe.history_fill_factor >= REQUIRED_AVERAGE_HISTORY_PERCENT:
            average = self._probe.get_average()
            pub_tasks.append(
                self._sensors[SensorCode.RTT_AVERAGE].send_state(
                    to_hass_numeric(average)
                )
            )

            loss = self._probe.get_loss_percent()
            pub_tasks.append(
                self._sensors[SensorCode.AVERAGE_LOSS].send_state(to_hass_numeric(loss))
            )

            jitter = self._probe.get_jitter()
            pub_tasks.append(
                self._sensors[SensorCode.JITTER].send_state(to_hass_numeric(jitter))
            )

            pub_tasks.append(
                self._sensors[SensorCode.JITTER_GRADE].send_state(
                    HASS_STATE_UNAVAILABLE
                    if jitter is None or average is None
                    else to_hass_numeric(100 * jitter / average)
                )
            )

        else:
            logger.debug(
                (
                    "History fill factory of %.1f%% is below threshold of %d%%. "
                    "Skip publishing statistics."
                ),
                self._probe.history_fill_factor,
                REQUIRED_AVERAGE_HISTORY_PERCENT,
            )

        pub_tasks.append(
            self._sensors[SensorCode.BYTES_SENT].send_state(
                self._probe.state.bytes_sent
            )
        )
        pub_tasks.append(
            self._sensors[SensorCode.BYTES_RECEIVED].send_state(
                self._probe.state.bytes_received
            )
        )

        await asyncio.gather(*pub_tasks)


class CompositeAllConnectedPublisher:
    """Composite publisher."""

    def __init__(
        self,
        pub_config: box.Box,
        probes: Sequence[common.ProbeBase],
        mqtt: asyncio_paho.AsyncioPahoClient,
        node_id: str,
    ) -> None:
        """Initialize CompositePublisher."""
        self._pub_config = pub_config
        self.probes = probes
        self._mqtt = mqtt
        self._node_id = node_id

        update_interval = min(p.probe_config.interval for p in probes)
        self._sensor = HassEntity(
            mqtt,
            HASS_COMPONENT_BINARY_SENSOR,
            node_id,
            f"all connected {pub_config.name}",
            {
                HASS_CONF_DEVICE_CLASS: HASS_DEVICE_CLASS_CONNECTIVITY,
            },
            update_interval,
        )

    async def send_configuration(self) -> None:
        """Send configuration to MQTT discovery topic."""
        await self._sensor.send_configuration()

    async def send_state(self) -> None:
        """Send measurement to MQTT topic."""
        states = [p.state.current for p in self.probes]
        all_is_down = all(state is None for state in states)
        state = HASS_STATE_DISCONNECTED if all_is_down else HASS_STATE_CONNECTED
        await self._sensor.send_state(state)


def create_composite_publisher(
    publisher_config: box.Box,
    all_probes: Sequence[common.ProbeBase],
    node_id: str,
    mqtt: asyncio_paho.AsyncioPahoClient,
) -> CompositeAllConnectedPublisher:
    """Create composite publiser from configured probes."""
    probes = []
    for target_config in publisher_config.probes:
        probe = next(
            (
                p
                for p in all_probes
                if p.probe_type == target_config.type and p.name == target_config.name
            ),
            None,
        )
        if probe:
            probes.append(probe)
        else:
            logger.warning(
                "%s probe '%s' used by %s not found.",
                target_config.type,
                target_config.name,
                publisher_config,
            )
    if probes:
        return CompositeAllConnectedPublisher(publisher_config, probes, mqtt, node_id)
    raise Exception("Probes % not found")
