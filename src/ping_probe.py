"""Ping-probe module."""

from __future__ import annotations

import logging

import box
import icmplib  # type: ignore

import common

logger = logging.getLogger(__name__)


class PingProbe(common.ProbeBase):
    """Ping probe."""

    def __init__(self, probe_config: box.Box) -> None:
        """Initialize DnsProbe."""
        super().__init__(logger, probe_config)

    @property
    def probe_type(self) -> str:
        """Get probe type."""
        return "ping"

    async def _probe_action(self) -> common.ProbeResult:
        """Execute probe action."""
        ping_result = await icmplib.async_ping(
            self.probe_config.target_adr,
            count=1,
            timeout=self.probe_config.timeout,
            payload_size=self.probe_config.payload_size,
            privileged=self.probe_config.privileged,
        )

        packet_size = self.probe_config.payload_size + 8

        if ping_result.packet_loss:
            logger.info(
                "ping-probe %s: %s ping timed out after %.1f sec.",
                self.name,
                ping_result.address,
                self.probe_config.interval,
            )
            return common.ProbeResult(None, packet_size, 0)

        if len(ping_result.rtts) == 0:
            logger.warning(
                "ping-probe %s: the host %s is not reachable.",
                self.name,
                ping_result.address,
            )
            return common.ProbeResult(None, packet_size, 0)

        elapsed_ms = ping_result.rtts[0]

        logger.info(
            "ping-probe %s: received %d bytes from %s after %.0f ms.",
            self.name,
            packet_size,
            ping_result.address,
            elapsed_ms,
        )

        return common.ProbeResult(elapsed_ms, packet_size, packet_size)
