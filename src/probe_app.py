"""Probe service."""

from __future__ import annotations

import argparse
import asyncio
import collections
import logging
import os
import platform
import signal
from asyncio.events import AbstractEventLoop
from asyncio.exceptions import CancelledError
from typing import Awaitable, Callable, Final, Sequence

import asyncio_paho
import box
import confuse  # type: ignore
import paho.mqtt.client as paho  # type: ignore

import common
import dns_probe
import ping_probe
import publish

VERSION: Final = "0.9.2"

CONF_PROBE_DNS: Final = "dns"
CONF_PROBE_PING: Final = "ping"

DEFAULT_LOG_LEVEL: Final = "INFO"
DEFAULT_MQTT_PORT: Final = 1883
DEFAULT_PROBE_PUBLISH_PRECISION: Final = 1
DEFAULT_PROBE_PING_PAYLOAD_SIZE: Final = 56
DEFAULT_PROBE_PING_PRIVILEGED: Final = False
DEFAULT_PROBE_INTERVAL: Final = 1.0
DEFAULT_PROBE_TIMEOUT: Final = 1.0
DEFAULT_QUERY_NAMES: list[str] = [
    "amazon.com",
    "apple.com",
    "facebook.com",
    "google.com",
    "microsoft.com",
    "netflix.com",
    "snapchat.com",
    "tiktok.com",
    "youtube.com",
]
DEFAULT_SENSOR_HISTORY_LEN: Final = 100
DEFAULT_SERVICE_NAME: Final = "Net probe service"
DEFAULT_TRANSPORT: Final = "tcp"

CONF_TEMPLATE: Final = {
    "service": {
        "id": confuse.Optional(str, default=platform.node()),
        "name": confuse.Optional(str, default=DEFAULT_SERVICE_NAME),
        "log-level": confuse.Choice(
            ["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"], default=DEFAULT_LOG_LEVEL
        ),
    },
    "mqtt": {
        "host": str,
        "port": confuse.Optional(int, DEFAULT_MQTT_PORT),
        "transport": confuse.Choice(["websockets", "tcp"], default=DEFAULT_TRANSPORT),
        "username": confuse.Optional(str),
        "password": confuse.Optional(str),
    },
    "probes": {
        CONF_PROBE_DNS: confuse.Sequence(
            {
                "name": str,
                "target-adr": str,
                "interval": confuse.Optional(float, DEFAULT_PROBE_INTERVAL),
                "timeout": confuse.Optional(float, DEFAULT_PROBE_TIMEOUT),
                "query-names": confuse.Optional(confuse.StrSeq(), DEFAULT_QUERY_NAMES),
                "history-len": confuse.Optional(int, DEFAULT_SENSOR_HISTORY_LEN),
                "publish-precision": confuse.Optional(
                    int, DEFAULT_PROBE_PUBLISH_PRECISION
                ),
            }
        ),
        CONF_PROBE_PING: confuse.Sequence(
            {
                "name": str,
                "target-adr": str,
                "interval": confuse.Optional(float, DEFAULT_PROBE_INTERVAL),
                "timeout": confuse.Optional(float, DEFAULT_PROBE_TIMEOUT),
                "history-len": confuse.Optional(int, DEFAULT_SENSOR_HISTORY_LEN),
                "payload_size": confuse.Optional(int, DEFAULT_PROBE_PING_PAYLOAD_SIZE),
                "publish-precision": confuse.Optional(
                    int, DEFAULT_PROBE_PUBLISH_PRECISION
                ),
                "privileged": confuse.Optional(bool, DEFAULT_PROBE_PING_PRIVILEGED),
            }
        ),
    },
    "compound": {
        "all-down": confuse.Sequence(
            {
                "name": str,
                "probes": confuse.Sequence(
                    {
                        "type": confuse.Choice([CONF_PROBE_DNS, CONF_PROBE_PING]),
                        "name": str,
                    }
                ),
            }
        ),
    },
}


logging.basicConfig(format="%(levelname)7s: %(message)s")

logger = logging.getLogger()

shutdown_event = asyncio.Event()


class ProbeService:  # pylint: disable=too-few-public-methods
    """Probe service."""

    def __init__(self, loop: AbstractEventLoop, config: box.Box) -> None:
        """Initialize ProbeService."""
        self._loop = loop
        self._config = config
        self._node_id = f"{common.APPNAME}_{config.service.id}"
        self._mqtt = asyncio_paho.AsyncioPahoClient(
            client_id=self._node_id, loop=loop, transport=config.mqtt.transport
        )

        dns_probes = [dns_probe.DnsProbe(cfg) for cfg in self._config.probes.dns]
        ping_probes = [ping_probe.PingProbe(cfg) for cfg in self._config.probes.ping]
        self._probes: Sequence[common.ProbeBase] = [*dns_probes, *ping_probes]

        self._compound_publisher: list[publish.CompositeAllConnectedPublisher] = []
        for publisher_config in self._config.compound.all_down:
            publisher = publish.create_composite_publisher(
                publisher_config, self._probes, self._node_id, self._mqtt
            )
            self._compound_publisher.append(publisher)

    async def _run_probes(self):
        tasks = []

        publisher_lookup = {}
        for pub in self._compound_publisher:
            asyncio.create_task(pub.send_configuration())

            # make lookup dictionary (from probe instace to compound publisher)
            for probe in pub.probes:
                publisher_lookup.setdefault(probe, []).append(pub)

        async def on_update_published(probe: common.ProbeBase) -> None:
            publishers = publisher_lookup.get(probe)
            if publishers:
                try:
                    publish_tasks = (publisher.send_state() for publisher in publishers)
                    await asyncio.gather(*publish_tasks)
                except CancelledError:
                    return

        # start probes
        for probe in self._probes:
            tasks.append(
                asyncio.create_task(self._run_probe(probe, on_update_published))
            )

        logger.info(
            "%d probe(s) started: %s",
            len(self._probes),
            [p.name for p in self._probes],
        )

        await asyncio.gather(*tasks)

    async def _run_probe(
        self,
        probe: common.ProbeBase,
        published_callback: Callable[[common.ProbeBase], Awaitable[None]],
    ) -> None:
        logger.debug("Start probe query loop '%s'.", probe.name)
        try:
            publisher = publish.ProbePublisher(probe, self._mqtt, self._node_id)
            await publisher.send_configuration()

            while True:
                await probe.probe()
                await asyncio.gather(publisher.send_state(), published_callback(probe))
        except CancelledError:
            logger.debug("Probe query loop '%s' cancelled.", probe.name)

    async def _on_mqtt_connect(
        self,
        result_code: int,
    ):
        if result_code == paho.MQTT_ERR_SUCCESS:
            logger.info(
                "Connected to MQTT server %s on port %d",
                self._config.mqtt.host,
                self._config.mqtt.port,
            )
        else:
            logger.warning(
                "Error connecting to MQTT server %s on port %d: %d - %s",
                self._config.mqtt.host,
                self._config.mqtt.port,
                result_code,
                str(asyncio_paho.AsyncioMqttConnectError(result_code)),
            )

    def _on_mqtt_disconnect(self, result_code: int):
        if result_code == paho.MQTT_ERR_SUCCESS:
            logger.info(
                "Disconnected from MQTT server %s",
                self._config.mqtt.host,
            )
        else:
            logger.warning(
                "Unexpected disconnected from MQTT server %s: %d - %s",
                self._config.mqtt.host,
                result_code,
                str(asyncio_paho.AsyncioMqttConnectError(result_code)),
            )

    def _configure_mqtt(self, will_topic) -> None:
        self._mqtt.enable_logger(logger)

        if self._config.mqtt.username:
            self._mqtt.username_pw_set(
                self._config.mqtt.username,
                self._config.mqtt.password,
            )

        # Set MQTT last will message (ungracefully disconnected message) before connect
        self._mqtt.will_set(
            will_topic,
            publish.HASS_STATE_DISCONNECTED,
            qos=1,
            retain=True,
        )

    async def _connect_mqtt(self) -> None:
        sleep_on_error = 0
        max_sleep_on_error = 10
        while True:
            try:
                if sleep_on_error > 0:
                    sleep_time = (
                        sleep_on_error
                        if sleep_on_error < max_sleep_on_error
                        else max_sleep_on_error
                    )
                    logger.debug(
                        "Sleep %f sec before mqtt retry.",
                        sleep_time,
                    )
                    await asyncio.sleep(sleep_time)

                await self._mqtt.asyncio_connect(
                    self._config.mqtt.host,
                    port=self._config.mqtt.port,
                )

                logger.info(
                    "Connected to MQTT server %s on port %d",
                    self._config.mqtt.host,
                    self._config.mqtt.port,
                )

                # Paho mqtt will reconnect automatic when first connected
                # add callbacks after initial connect
                self._mqtt.on_disconnect = (
                    lambda _, __, result_code: self._on_mqtt_disconnect(result_code)
                )
                self._mqtt.asyncio_listeners.add_on_connect(
                    lambda *args: self._on_mqtt_connect(args[3])
                )

                break

            except CancelledError as ex:
                raise ex
            except Exception as ex:  # pylint: disable=broad-except
                logger.warning(
                    "Unable to connect to mqtt host %s: %s",
                    self._config.mqtt.host,
                    ex,
                )
                sleep_on_error += 2

    async def run(self) -> None:
        """Run service."""
        if len(self._probes) == 0:
            logger.info("No probes configured. Exit.")
            return

        service_online_sensor = publish.HassEntity(
            mqtt=self._mqtt,
            component=publish.HASS_COMPONENT_BINARY_SENSOR,
            node_id=self._node_id,
            object_id=common.APPNAME,
            hass_config={
                publish.HASS_CONF_DEVICE_CLASS: publish.HASS_DEVICE_CLASS_CONNECTIVITY,
                publish.HASS_CONF_ENTITY_CATEGORY: publish.HASS_ENTITY_CATEGORY_DIAGNOSTIC,
                publish.HASS_CONF_DEVICE: {
                    publish.HASS_ATTR_NAME: self._config.service.name,
                    publish.HASS_ATTR_IDENTIFIERS: self._node_id,
                    publish.HASS_ATTR_MANUFACTURER: "Tore Amundsen",
                    publish.HASS_ATTR_MODEL: "Python",
                    publish.HASS_ATTR_SW_VERSION: VERSION,
                },
            },
            update_interval=None,
        )

        self._configure_mqtt(service_online_sensor.state_topic)

        try:
            await self._connect_mqtt()
            try:
                await service_online_sensor.send_configuration()
                logger.info("Sensor configurations published to MQTT.")

                try:
                    await asyncio.gather(
                        self._run_probes(),
                        service_online_sensor.send_state(
                            publish.HASS_STATE_CONNECTED, qos=1, retain=True
                        ),
                    )
                except CancelledError:
                    pass
                try:
                    await service_online_sensor.send_state(
                        publish.HASS_STATE_DISCONNECTED, retain=True
                    )
                except Exception:  # pylint: disable=broad-except
                    pass  # ignore trouble sending disconnect state
            finally:
                self._mqtt.disconnect()
                await asyncio.sleep(0.5)  # wait for disconnect to complete gracefully

        except CancelledError:
            pass
        finally:
            logger.debug("Probe run-task complete")


def load_configuration(config_file: str) -> box.Box:
    """Load configuration."""
    config = confuse.Configuration(common.APPNAME, read=False)
    config.set_file(config_file)
    template_config = config.get(CONF_TEMPLATE)

    config = box.Box(template_config, frozen_box=True)
    validate_config(config)

    return config


def validate_config(config: box.Box) -> None:
    """Validate configuration."""

    def check_duplicate_name(probes, element_type) -> None:
        probe_names = [probe.name for probe in probes]
        duplicates = [
            item
            for item, count in collections.Counter(probe_names).items()
            if count > 1
        ]
        if duplicates:
            raise confuse.ConfigError(
                f"Duplicate {element_type} probe name(s): {duplicates}"
            )

    check_duplicate_name(config.probes.dns, "dns probe")
    check_duplicate_name(config.probes.ping, "ping probe")
    check_duplicate_name(config.compound.all_down, "compund all-down")

    dns_probes = [cfg.name for cfg in config.probes.dns]
    ping_probes = [cfg.name for cfg in config.probes.ping]
    for cfg in config.compound.all_down:
        for probe_cfg in cfg.probes:
            if probe_cfg.type == CONF_PROBE_DNS:
                if probe_cfg.name not in dns_probes:
                    raise confuse.ConfigError(
                        f"dns probe {probe_cfg.name} used by {cfg.name} not found."
                    )
            if probe_cfg.type == CONF_PROBE_PING:
                if probe_cfg.name not in ping_probes:
                    raise confuse.ConfigError(
                        f"ping probe {probe_cfg.name} used by {cfg.name} not found."
                    )


async def shutdown(sig: signal.Signals, loop: AbstractEventLoop):
    """Cleanup tasks tied to the service's shutdown."""

    if sig != signal.SIGHUP:
        shutdown_event.set()

    logger.info(
        "Received %s signal from parent process %s. %s.",
        sig.name,
        os.getppid(),
        "Restarting" if sig == signal.SIGHUP else "Shutting down",
    )

    tasks = [
        t
        for t in asyncio.all_tasks(loop=loop)
        if t is not asyncio.current_task(loop=loop)
    ]

    if tasks:
        logger.info("Cancelling %d outstanding tasks", len(tasks))
        for task in tasks:
            task.cancel()

        logger.debug("All tasks cancelled.")


async def main() -> None:
    """Start probe service."""
    parser = argparse.ArgumentParser(description="Home Assistant Net probe service.")
    parser.add_argument(
        "config",
        nargs="?",
        default="probe.yaml",
        help="Yaml configuration file. Default is probe.yaml.",
    )
    args = parser.parse_args()

    loop = asyncio.get_running_loop()
    for sig in signal.SIGHUP, signal.SIGTERM, signal.SIGINT:
        loop.add_signal_handler(
            sig, lambda s=sig: loop.create_task(shutdown(s, loop))  # type: ignore
        )

    while shutdown_event.is_set() is False:
        try:
            config = load_configuration(args.config)
            logger.debug("Configuration successfully loaded.")
        except confuse.ConfigError as err:
            logger.error("Configuration error: %s", err)
            shutdown_event.set()
        else:
            logger.setLevel(config.service.log_level)

            logger.info("Starting probe service...")

            service = ProbeService(loop, config)
            await service.run()

            logger.info("Successfully stopped.")


if __name__ == "__main__":
    asyncio.run(main())
