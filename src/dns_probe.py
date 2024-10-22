"""DNS-probe module."""

from __future__ import annotations

import logging
import random

import box
import dns.asyncquery
import dns.flags
import dns.message
import dns.resolver

import common

logger = logging.getLogger(__name__)


class DnsProbe(common.ProbeBase):
    """DNS probe."""

    def __init__(self, probe_config: box.Box) -> None:
        """Initialize DnsProbe."""
        super().__init__(logger, probe_config)
        self._query_data = [
            self._make_query_data(qname) for qname in probe_config.query_names
        ]

    @property
    def probe_type(self) -> str:
        """Get probe type."""
        return "dns"

    async def _probe_action(self) -> common.ProbeResult:
        """Execute probe action."""
        query = random.choice(self._query_data)
        bytes_to_send = len(query.to_wire())
        logger.debug(
            "dns-probe %s: Send %d bytes query to %s",
            self.name,
            bytes_to_send,
            self.probe_config.target_adr,
        )

        try:
            answers: dns.message.Message = await dns.asyncquery.udp(
                query,
                self.probe_config.target_adr,
                timeout=self.probe_config.timeout,
                ignore_unexpected=True,
            )

            elapsed_ms = answers.time * 1000  # type: ignore
            bytes_received = len(answers.to_wire())
            logger.info(
                "dns-probe %s: received %d bytes after %d ms.",
                self.name,
                bytes_received,
                elapsed_ms,
            )

            return common.ProbeResult(elapsed_ms, bytes_to_send, bytes_received)

        except dns.exception.Timeout:
            logger.info(
                "dns-probe %s: timed out after %.1f sec.",
                self.name,
                self.probe_config.interval,
            )
            return common.ProbeResult(None, bytes_to_send, 0)

    def _make_query_data(self, qname) -> dns.message.Message:
        return dns.message.make_query(
            qname,
            dns.rdatatype.A,
            dns.rdataclass.IN,
            use_edns=False,
            want_dnssec=False,
        )
