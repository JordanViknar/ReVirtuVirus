"""
Agent model: ``AgentType`` enum and ``Agent`` class.

Each Agent owns its Tkinter canvas oval and runs its own movement /
infection threads.  ``SimulationZone`` manages the collections.
"""
from __future__ import annotations

import random
import time
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
	"""

	def __init__(
		self,
		zone: SimulationZone,
		x: float,
		y: float,
		agent_type: AgentType,
		is_symptomless: bool = False,
	) -> None:
		from modules.state import state

		self.zone: SimulationZone = zone
		self.size: int = state.config.agent_size
		self.is_symptomless: bool = is_symptomless
		self._type: AgentType = agent_type
		self.infection_zone: Optional[int] = None  # canvas item id

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

	# Movement thread

	def run_movement(self, origin_zone: Optional[SimulationZone] = None) -> None:
		"""
		Thread target.  Bounces agent around canvas, handles central travel,
		and returns quarantined agents to their origin zone when they recover.
		*origin_zone* is ``None`` for regular (non-transferred) agents.
		"""
		from modules.state import state

		cfg = state.config
		canvas = self.zone.canvas

		vx = cfg.maximum_agent_speed * random.random() * random.choice([-1, 1])
		vy = cfg.maximum_agent_speed * random.random() * random.choice([-1, 1])
		time.sleep(0.5)  # prevents freeze on startup

		while (
			state.is_running
			and self._type != AgentType.DEAD
			and self in self.zone.agents
			and self.zone.threads
		):
			# Central travel
			if cfg.is_central_travel_enabled:
				roll = random.random()
				if cfg.is_human_logic_enabled:
					if self._type == AgentType.INFECTED:
						roll *= 3
					elif self._type == AgentType.SANE and self.zone.agents:
						ratio = (len(self.zone.infected) - len(self.zone.dead) * 3) / len(self.zone.agents)
						roll /= max(1 - ratio, 1e-9)
				if roll <= cfg.central_travel_chance:
					self._do_central_travel(cfg)
					vx = cfg.maximum_agent_speed * random.random() * random.choice([-1, 1])
					vy = cfg.maximum_agent_speed * random.random() * random.choice([-1, 1])

			# Move and bounce
			try:
				canvas.move(self.model, vx, vy)
				x1, y1, x2, y2 = canvas.coords(self.model)
			except Exception:
				break

			# Return cured quarantine agents to their origin simulation
			if self.zone.is_quarantine and self._type == AgentType.IMMUNE and origin_zone is not None:
				self.zone.transfer_agent_to(self, origin_zone)
				return

			if x1 <= 0 or x2 >= cfg.canvas_width:
				vx = -vx
			if y1 <= 0 or y2 >= cfg.canvas_height:
				vy = -vy

			_wait_if_paused()
			time.sleep(1 / cfg.framerate)

	# Infection thread

	def run_infection(self) -> None:
		"""
		Thread target.  Runs the infection lifecycle: spreading, recovery,
		death, and quarantine transfer.
		"""
		from modules.state import state

		cfg = state.config
		canvas = self.zone.canvas

		# Guard against duplicate or invalid calls
		if self._type in (AgentType.DEAD, AgentType.IMMUNE) or self.infection_zone is not None:
			time.sleep(1)
			if self._type in (AgentType.DEAD, AgentType.IMMUNE) or self.infection_zone is not None:
				return

		# Sane → Infected transition (list management done explicitly)
		_list_remove(self.zone.sane, self)
		if self not in self.zone.infected:
			self.zone.infected.append(self)
		self._type = AgentType.INFECTED
		canvas.itemconfig(self.model, fill=self._current_color)

		iz = canvas.create_oval(
			0, 0,
			cfg.agent_size * cfg.infective_range,
			cfg.agent_size * cfg.infective_range,
		)
		self.infection_zone = iz

		local_recovery_progress: float = 0.0
		quarantine_timer: float = 0.0

		while state.is_running and self._type == AgentType.INFECTED:
			# Sync infection-zone oval to agent centre
			try:
				ax1, ay1, ax2, ay2 = canvas.coords(self.model)
			except ValueError:
				break

			acx, acy = (ax1 + ax2) / 2, (ay1 + ay2) / 2
			ix1, iy1, ix2, iy2 = canvas.coords(iz)
			canvas.move(iz, acx - (ix1 + ix2) / 2, acy - (iy1 + iy2) / 2)

			# Spread infection (not in quarantine)
			if not self.zone.is_quarantine:
				for mid in canvas.find_overlapping(ix1, iy1, ix2, iy2):
					if mid in (self.model, iz):
						continue
					if random.random() < cfg.infection_risk:
						target = next(
							(a for a in list(self.zone.sane) if a.model == mid and a._type == AgentType.SANE),
							None,
						)
						if target:
							self.zone.spawn_thread(target.run_infection)

			# Recovery
			if random.random() < cfg.default_recovery_chance + local_recovery_progress:
				canvas.delete(iz)
				self.infection_zone = None
				self.zone.immunize(self)
				return
			local_recovery_progress += cfg.recovery_chance_progress

			# Death
			n_inf = len(self.zone.infected)
			n_alive = len(self.zone.sane) + len(self.zone.immune) + 1
			base_death = random.random() < cfg.death_risk - local_recovery_progress / 4
			logic_death = (
				cfg.is_human_logic_enabled
				and not self.zone.is_quarantine
				and random.random() < cfg.death_risk * n_inf / n_alive - local_recovery_progress / 3
			)
			if not self.is_symptomless and (base_death or logic_death):
				canvas.delete(iz)
				self.infection_zone = None
				self.zone.kill(self)
				return

			# Quarantine
			quarantine_timer += 1 / cfg.framerate
			q = state.quarantine
			if (
				not self.zone.is_quarantine
				and quarantine_timer >= cfg.quarantine_timer_limit
				and cfg.is_last_simulation_quarantine
				and not self.is_symptomless
				and q is not None
			):
				canvas.delete(iz)
				self.infection_zone = None
				self.zone.transfer_agent_to(self, q)
				return

			_wait_if_paused()
			time.sleep(1 / cfg.framerate)

		canvas.delete(iz)
		self.infection_zone = None

	# Central travel helper

	def _do_central_travel(self, cfg) -> None:
		from modules.state import state

		canvas = self.zone.canvas
		old_color: Optional[str] = None

		if cfg.make_central_travel_obvious:
			old_color = canvas.itemcget(self.model, "fill")
			canvas.itemconfig(self.model, fill="yellow")

		try:
			cx, cy = self.center
		except (ValueError, IndexError):
			return

		hw, hh = cfg.canvas_width / 2, cfg.canvas_height / 2

		while (
			state.is_running
			and self in self.zone.agents
			and self._type != AgentType.DEAD
			and self.zone.threads
			and sqrt((cx - hw) ** 2 + (cy - hh) ** 2) > cfg.center_range
		):
			canvas.move(self.model, (hw - cx) / cfg.framerate, (hh - cy) / cfg.framerate)
			try:
				cx, cy = self.center
			except (ValueError, IndexError):
				break
			_wait_if_paused()
			time.sleep(1 / cfg.framerate)

		if old_color is not None:
			try:
				if canvas.itemcget(self.model, "fill") == "yellow":
					canvas.itemconfig(self.model, fill=old_color)
			except Exception:
				pass


# Helpers

def _list_remove(lst: list[Agent], agent: Agent) -> None:
	try:
		lst.remove(agent)
	except ValueError:
		pass


def _wait_if_paused() -> None:
	from modules.state import state
	while state.is_paused:
		time.sleep(0.1)
