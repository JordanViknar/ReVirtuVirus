"""Simulation configuration, stored as a typed dataclass."""
from __future__ import annotations

from dataclasses import dataclass, field

# Default window dimensions (not part of runtime config)
WINDOW_WIDTH: int = 800
WINDOW_HEIGHT: int = 600

@dataclass
class Config:
	"""
	All per-second rate values are stored at their human-readable scale.
	Call :meth:`normalize_for_framerate` once to convert them to per-frame
	values before the simulation runs.  :meth:`default` does both steps.
	"""

	# Simulation
	simulation_quantity: int = 4
	framerate: int = 24
	canvas_width: int = 300
	canvas_height: int = 300
	is_last_simulation_quarantine: bool = True

	# Agents
	number_of_sane_agents: int = 99
	number_of_infected_agents: int = 1
	number_of_immune_agents: int = 0
	maximum_agent_speed: float = 48.0	   # pixels / second
	agent_size: int = 10
	is_central_travel_enabled: bool = True
	central_travel_chance: float = 0.05	 # probability / second
	make_central_travel_obvious: bool = True
	center_range: int = 30
	quarantine_timer_limit: int = 3		 # seconds before isolation
	is_human_logic_enabled: bool = True
	enable_symptomless_agents: bool = True
	symptomless_agents_chance: float = 1 / 30   # probability

	# Virus
	infective_range: float = 4.0			# multiplier on agent_size
	infection_risk: float = 0.48			# probability / second
	default_recovery_chance: float = 0.024  # probability / second
	recovery_chance_progress: float = 0.00036  # added per second
	death_risk: float = 0.018			  # probability / second

	def normalize_for_framerate(self) -> None:
		"""Convert all per-second rates to per-frame rates in-place."""
		fps = self.framerate
		self.maximum_agent_speed /= fps
		self.central_travel_chance /= fps
		self.infection_risk /= fps
		self.default_recovery_chance /= fps
		self.recovery_chance_progress /= fps
		self.death_risk /= fps

	@classmethod
	def default(cls) -> Config:
		"""Return a ready-to-use Config with per-frame rates already applied."""
		cfg = cls()
		cfg.normalize_for_framerate()
		return cfg

	@classmethod
	def from_ui_values(
		cls, *,
		simulation_quantity: int,
		framerate: int,
		canvas_width: int,
		canvas_height: int,
		is_last_simulation_quarantine: bool,
		quarantine_timer_limit: int,
		number_of_sane_agents: int,
		number_of_infected_agents: int,
		number_of_immune_agents: int,
		maximum_agent_speed: int,
		agent_size: int,
		is_central_travel_enabled: bool,
		central_travel_chance_pct: int,   # 0-100
		center_range: int,
		make_central_travel_obvious: bool,
		is_human_logic_enabled: bool,
		infective_range: int,
		infection_risk_pct: int,		  # 0-100
		default_recovery_chance_pct: int, # 0-100, divided by 10 internally
		recovery_chance_progress_pct: int,# 0-100, divided by 1000 internally
		death_risk_pct: int,			  # 0-100, divided by 10 internally
		enable_symptomless_agents: bool,
		symptomless_agents_chance_pct: int,  # 0-100
	) -> Config:
		"""Build a Config from raw UI entry values, apply limits, and normalize."""
		cfg = Config(
			simulation_quantity=max(1, min(simulation_quantity, 15)),
			framerate=max(1, framerate),
			canvas_width=max(1, min(canvas_width, 300)),
			canvas_height=max(1, min(canvas_height, 300)),
			is_last_simulation_quarantine=is_last_simulation_quarantine,
			quarantine_timer_limit=max(0, quarantine_timer_limit),
			number_of_sane_agents=max(0, number_of_sane_agents),
			number_of_infected_agents=max(0, number_of_infected_agents),
			number_of_immune_agents=max(0, number_of_immune_agents),
			maximum_agent_speed=float(max(1, maximum_agent_speed)),
			agent_size=max(1, agent_size),
			is_central_travel_enabled=is_central_travel_enabled,
			central_travel_chance=max(0.0, min(central_travel_chance_pct, 100)) / 100,
			center_range=max(0, center_range),
			make_central_travel_obvious=make_central_travel_obvious,
			is_human_logic_enabled=is_human_logic_enabled,
			infective_range=float(infective_range),
			infection_risk=max(0.0, min(infection_risk_pct, 100)) / 100,
			default_recovery_chance=max(0.0, min(default_recovery_chance_pct, 100)) / 100 / 10,
			recovery_chance_progress=max(0.0, min(recovery_chance_progress_pct, 100)) / 100 / 1000,
			death_risk=max(0.0, min(death_risk_pct, 100)) / 100 / 10,
			enable_symptomless_agents=enable_symptomless_agents,
			symptomless_agents_chance=max(0.0, min(symptomless_agents_chance_pct, 100)) / 100,
		)
		cfg.normalize_for_framerate()
		return cfg
