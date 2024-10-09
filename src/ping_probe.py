"""Ping-probe module."""
from __future__ import annotations

import logging

import icmplib  # type: ignore

import common

logger = logging.getLogger(__name__)


class PingProbe(common.ProbeBase):
    """Ping probe."""

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
                "ping-probe %s: timed out after %.1f sec.",
                self.name,
                self.probe_config.interval,
            )
            return common.ProbeResult(None, packet_size, 0)

        elapsed_ms = ping_result.rtts[0]

        logger.info(
            "ping-probe %s: received %d bytes after %.0f ms.",
            self.name,
            64,
            elapsed_ms,
        )

        return common.ProbeResult(elapsed_ms, packet_size, packet_size)
