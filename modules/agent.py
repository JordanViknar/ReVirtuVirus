"""
Agent model: ``AgentType`` enum and ``Agent`` class.

Agents no longer own threads.  Each frame the zone's worker thread calls
``agent.move()`` then ``agent.infect()`` for every agent it owns.
Per-frame state (velocity, recovery progress, etc.) lives on the instance.
"""
from __future__ import annotations

import random
from enum import Enum
from math import sqrt
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
	from modules.simulation_zone import SimulationZone

# AgentType

class AgentType(str, Enum):
	SANE = "Sane"
	INFECTED = "Infected"
	IMMUNE = "Immune"
	DEAD = "Dead"

	@property
	def color(self) -> str:
		return _COLORS[self]

_COLORS: dict[AgentType, str] = {
	AgentType.SANE: "blue",
	AgentType.INFECTED: "red",
	AgentType.IMMUNE: "green",
	AgentType.DEAD: "grey",
}

# Agent

class Agent:
	"""
	A single simulation agent.

	On construction the agent draws its canvas oval and self-registers
	into its owning :class:`~modules.simulation_zone.SimulationZone`.

	``move()`` and ``infect()`` are called once per frame by the zone's
	worker thread; they must not block.
	"""

	def __init__(
		self,
		zone: SimulationZone,
		x: float,
		y: float,
		agent_type: AgentType,
		is_symptomless: bool = False,
		origin_zone: Optional[SimulationZone] = None,
	) -> None:
		from modules.state import state

		cfg = state.config

		self.zone: SimulationZone = zone
		self.size: int = cfg.agent_size
		self.is_symptomless: bool = is_symptomless
		self._type: AgentType = agent_type

		# Velocity (per-frame pixels, already normalised by Config)
		self.vx: float = cfg.maximum_agent_speed * random.random() * random.choice([-1, 1])
		self.vy: float = cfg.maximum_agent_speed * random.random() * random.choice([-1, 1])

		# Central-travel flag; when True, move() steers toward canvas centre
		self.traveling_to_center: bool = False

		# Infection state (only meaningful when type == INFECTED)
		self.infection_zone: Optional[int] = None  # canvas item id
		self.recovery_progress: float = 0.0
		self.quarantine_timer: float = 0.0

		# The zone this agent came from (set when transferred to quarantine)
		self.origin_zone: Optional[SimulationZone] = origin_zone

		self.model: int = zone.canvas.create_oval(
			x, y, x + self.size, y + self.size,
			fill=self._current_color,
		)
		zone._register(self)

	# Properties

	@property
	def type(self) -> AgentType:
		return self._type

	@type.setter
	def type(self, value: AgentType) -> None:
		self._type = value
		try:
			self.zone.canvas.itemconfig(self.model, fill=self._current_color)
		except Exception:
			pass

	@property
	def _current_color(self) -> str:
		if self._type == AgentType.INFECTED and self.is_symptomless:
			return "pink"
		return self._type.color

	@property
	def center(self) -> tuple[float, float]:
		x1, y1, x2, y2 = self.zone.canvas.coords(self.model)
		return (x1 + x2) / 2, (y1 + y2) / 2

	# Per-frame: movement

	def move(self) -> None:
		"""
		Called once per frame by the zone's worker thread.

		Handles central travel, wall bouncing, and quarantine returns.
		Must not block.
		"""
		if self._type == AgentType.DEAD:
			return

		from modules.state import state
		cfg = state.config
		canvas = self.zone.canvas

		# Central travel
		if cfg.is_central_travel_enabled:
			if self.traveling_to_center:
				self._step_central_travel(cfg)
				return  # skip normal movement this frame

			# Decide whether to start central travel
			roll = random.random()
			if cfg.is_human_logic_enabled:
				if self._type == AgentType.INFECTED:
					roll *= 3  # infected agents are less inclined to travel
				elif self._type == AgentType.SANE and self.zone.agents:
					ratio = (
						len(self.zone.infected) - len(self.zone.dead) * 3
					) / len(self.zone.agents)
					roll /= max(1 - ratio, 1e-9)  # sane agents avoid crowded zones

			if roll <= cfg.central_travel_chance:
				self.traveling_to_center = True
				if cfg.make_central_travel_obvious:
					canvas.itemconfig(self.model, fill="yellow")
				return

		# Normal movement
		try:
			canvas.move(self.model, self.vx, self.vy)
			x1, y1, x2, y2 = canvas.coords(self.model)
		except Exception:
			return

		# Quarantine return: cured agent heads back to its origin simulation
		if (
			self.zone.is_quarantine
			and self._type == AgentType.IMMUNE
			and self.origin_zone is not None
		):
			self.zone.transfer_agent_to(self, self.origin_zone)
			return

		# Wall bounce
		if x1 <= 0 or x2 >= cfg.canvas_width:
			self.vx = -self.vx
		if y1 <= 0 or y2 >= cfg.canvas_height:
			self.vy = -self.vy

	# Per-frame: infection

	def infect(self) -> None:
		"""
		Called once per frame by the zone's worker thread.

		Handles infection spreading, recovery, death, and quarantine transfer.
		Only runs for INFECTED agents.  Must not block.
		"""
		if self._type != AgentType.INFECTED:
			return

		from modules.state import state
		cfg = state.config
		canvas = self.zone.canvas

		# Lazily create the infection-zone oval on first infect() call
		if self.infection_zone is None:
			size = cfg.agent_size * cfg.infective_range
			self.infection_zone = canvas.create_oval(0, 0, size, size)

		# Sync infection-zone oval to agent centre
		try:
			ax1, ay1, ax2, ay2 = canvas.coords(self.model)
		except ValueError:
			return
		acx, acy = (ax1 + ax2) / 2, (ay1 + ay2) / 2
		ix1, iy1, ix2, iy2 = canvas.coords(self.infection_zone)
		canvas.move(
			self.infection_zone,
			acx - (ix1 + ix2) / 2,
			acy - (iy1 + iy2) / 2,
		)

		# Spread to overlapping sane agents
		if not self.zone.is_quarantine:
			ix1, iy1, ix2, iy2 = canvas.coords(self.infection_zone)
			for mid in canvas.find_overlapping(ix1, iy1, ix2, iy2):
				if mid in (self.model, self.infection_zone):
					continue
				if random.random() < cfg.infection_risk:
					target = next(
						(a for a in list(self.zone.sane) if a.model == mid),
						None,
					)
					if target is not None:
						self.zone.begin_infect(target)

		# Recovery
		if random.random() < cfg.default_recovery_chance + self.recovery_progress:
			self._clear_infection_zone()
			self.zone.immunize(self)
			return
		self.recovery_progress += cfg.recovery_chance_progress

		# Death
		n_inf   = len(self.zone.infected)
		n_alive = len(self.zone.sane) + len(self.zone.immune) + 1
		base_death = random.random() < cfg.death_risk - self.recovery_progress / 4
		logic_death = (
			cfg.is_human_logic_enabled
			and not self.zone.is_quarantine
			and random.random() < cfg.death_risk * n_inf / n_alive - self.recovery_progress / 3
		)
		if not self.is_symptomless and (base_death or logic_death):
			self._clear_infection_zone()
			self.zone.kill(self)
			return

		# Quarantine isolation
		self.quarantine_timer += 1 / cfg.framerate
		q = state.quarantine
		if (
			not self.zone.is_quarantine
			and self.quarantine_timer >= cfg.quarantine_timer_limit
			and cfg.is_last_simulation_quarantine
			and not self.is_symptomless
			and q is not None
		):
			self._clear_infection_zone()
			self.zone.transfer_agent_to(self, q)

	# Central travel helper

	def _step_central_travel(self, cfg) -> None:  # type: ignore[no-untyped-def]
		"""Advance one frame toward the canvas centre."""
		hw = cfg.canvas_width  / 2
		hh = cfg.canvas_height / 2

		try:
			cx, cy = self.center
		except (ValueError, IndexError):
			self.traveling_to_center = False
			return

		if sqrt((cx - hw) ** 2 + (cy - hh) ** 2) <= cfg.center_range:
			# Reached the centre — resume normal movement with a fresh velocity
			self.traveling_to_center = False
			self.vx = cfg.maximum_agent_speed * random.random() * random.choice([-1, 1])
			self.vy = cfg.maximum_agent_speed * random.random() * random.choice([-1, 1])
			if cfg.make_central_travel_obvious:
				try:
					self.zone.canvas.itemconfig(self.model, fill=self._current_color)
				except Exception:
					pass
			return

		self.zone.canvas.move(
			self.model,
			(hw - cx) / cfg.framerate,
			(hh - cy) / cfg.framerate,
		)

	# Internal helpers

	def _clear_infection_zone(self) -> None:
		if self.infection_zone is not None:
			try:
				self.zone.canvas.delete(self.infection_zone)
			except Exception:
				pass
			self.infection_zone = None


# Module helpers

def _list_remove(lst: list[Agent], agent: Agent) -> None:
	try:
		lst.remove(agent)
	except ValueError:
		pass
