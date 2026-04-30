"""
Central application state.

A single module-level ``state`` instance is imported by every module that
needs shared data, removing the need for getter/setter helper functions.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from modules.config import Config

if TYPE_CHECKING:
	from modules.simulation_zone import SimulationZone

class AppState:
	"""Holds all mutable runtime state for the simulation."""

	def __init__(self) -> None:
		self.config: Config = Config.default()

		# Set by the GUI after it creates the canvases
		self.simulations: list[SimulationZone] | None = None
		self.quarantine: SimulationZone | None = None

		# Simulation control flags
		self.is_running: bool = False
		self.is_paused: bool = False
		self.frame_time: int = 0

		# Reference to the Application window (set in gui.py after construction)
		self.gui: Any | None = None  # type: modules.gui.Application

		# Per-frame population snapshots used by the graph module
		self._collected_data: list[list[dict[str, int]]] = []

	# Data collection

	def add_frame_data(self, frame: list[dict[str, int]]) -> None:
		self._collected_data.append(frame)

	def get_collected_data(self) -> list[list[dict[str, int]]]:
		return self._collected_data

	def reset_data(self) -> None:
		self._collected_data.clear()

	# Convenience counters

	def total_count(self, category: str) -> int:
		"""Return the total agent count across all simulations for *category*."""
		if self.simulations is None:
			return 0
		attr = {"Sane": "sane", "Infected": "infected", "Immune": "immune", "Dead": "dead"}.get(category)
		if attr is None:
			return 0
		return sum(len(getattr(s, attr)) for s in self.simulations)

# Module-level singleton — import this everywhere instead of the class itself.
state = AppState()
