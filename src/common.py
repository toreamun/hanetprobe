"""Common module."""
from __future__ import annotations

import asyncio
import collections
import logging
import statistics
import time
from abc import ABC, abstractmethod
from asyncio.exceptions import CancelledError
from dataclasses import dataclass
from typing import Final

import box

APPNAME: Final = "ha-net-probe"

ProbeResult = collections.namedtuple(
    "ProbeResult", ["rtt", "bytes_sent", "bytes_received"]
)


logger = logging.getLogger(__name__)


@dataclass
class ProbeState:
    """Probe state data class."""

    total_count: int = 0
    total_lost_count: int = 0
    bytes_sent: int = 0
    bytes_received: int = 0
    current: ProbeResult | None = None


class ProbeBase(ABC):
    """Probe base class."""

    def __init__(self, probe_config: box.Box) -> None:
        """Initialize Probe."""
        self.probe_config = probe_config
        self._time_previous = 0.0
        self._hist: list[None | float] = []
        self.state = ProbeState()

    @property
    @abstractmethod
    def probe_type(self) -> str:
        """Get probe type."""

    @property
    def name(self) -> str:
        """Get name of probe."""
        return self.probe_config.name

    @property
    def history(self) -> list[None | float]:
        """Get history in sequential order (old to new)."""
        if len(self._hist) < self.probe_config.history_len:
            return self._hist[:]
        pos = self.state.total_count % self.probe_config.history_len
        return self._hist[pos:] + self._hist[:pos]

    @property
    def history_fill_factor(self) -> float:
        """Get history fill factor."""
        return 100 * len(self._hist) / self.probe_config.history_len

    def get_average(self) -> float | None:
        """Calculate history average."""
        values = [i for i in self._hist if i is not None]
        if values:
            return statistics.fmean(values)
        return None

    def get_loss_percent(self) -> float | None:
        """Calculate result loss percent from history."""
        if len(self._hist) == 0:
            return None
        loss_count = self._hist.count(None)
        return 100 * loss_count / len(self._hist)

    def get_jitter(self) -> float | None:
        """Caclculate jitter."""
        history = [i for i in self.history if i is not None]
        if len(history) <= 1:
            return None

        #  find differences between every (i)-th elements and its (i+1)
        diffs = [abs(j - i) for i, j in zip(history[:-1], history[1:])]
        return statistics.fmean(diffs)

    async def probe(self) -> None:
        """Execute probe."""
        # Ensure max interval between queries
        interval = self.probe_config.interval
        elapsed = time.perf_counter() - self._time_previous
        if elapsed < interval:
            sleep_time = interval - elapsed
            logger.debug(
                "%s-probe %s: sleep %f sec.", self.probe_type, self.name, sleep_time
            )
            await asyncio.sleep(sleep_time)
        self._time_previous = time.perf_counter()

        try:
            self.state.current = await self._probe_action()
        except CancelledError:
            logger.debug("%s-probe %s: probe cancelled.", self.probe_type, self.name)
            raise
        except Exception as ex:  # pylint: disable=broad-except
            logger.warning(
                "%s-probe %s: Error executing probe action: %s",
                self.probe_type,
                self.name,
                ex,
            )

            self.state.current = ProbeResult(None, 0, 0)

        self.state.bytes_sent += self.state.current.bytes_sent
        self.state.bytes_received += self.state.current.bytes_received
        if self.state.current.rtt is None:
            rtt = None
            self.state.total_lost_count += 1
        else:
            rtt = self.state.current.rtt

        self._add_hist(rtt)

    @abstractmethod
    async def _probe_action(self) -> ProbeResult:
        """Execute probe action."""

    def _add_hist(self, value: float | None) -> None:
        if len(self._hist) < self.probe_config.history_len:
            self._hist.append(value)
        else:
            self._hist[self.state.total_count % self.probe_config.history_len] = value
        self.state.total_count += 1
