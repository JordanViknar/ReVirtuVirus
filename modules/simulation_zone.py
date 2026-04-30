"""
``SimulationZone`` wraps a Tkinter canvas together with its agent lists
and worker threads.  It replaces the raw ``dict`` used throughout the
original codebase.
"""
from __future__ import annotations

import random
from threading import Thread
from typing import TYPE_CHECKING

import tkinter as tk

if TYPE_CHECKING:
	from modules.agent import Agent, AgentType


class SimulationZone:
	"""
	One simulation canvas plus bookkeeping for agents and threads.

	Agent lists are plain Python lists so iteration order is stable and
	list semantics (remove, append, ``in``) work as expected everywhere.
	"""

	def __init__(self, canvas: tk.Canvas, is_quarantine: bool = False) -> None:
		self.canvas: tk.Canvas = canvas
		self.is_quarantine: bool = is_quarantine

		# All agents in this zone
		self.agents: list[Agent] = []
		# Per-type subsets (always subsets of self.agents)
		self.sane: list[Agent] = []
		self.infected: list[Agent] = []
		self.immune: list[Agent] = []
		self.dead: list[Agent] = []

		# Background threads spawned for this zone
		self.threads: list[Thread] = []

	# Agent registration

	def _register(self, agent: Agent) -> None:
		"""Called by ``Agent.__init__`` to add the new agent to our lists."""
		from modules.agent import AgentType

		self.agents.append(agent)
		match agent.type:
			case AgentType.SANE:
				self.sane.append(agent)
			case AgentType.INFECTED:
				self.infected.append(agent)
			case AgentType.IMMUNE:
				self.immune.append(agent)
			# DEAD agents are never spawned directly

	# State transitions

	def immunize(self, agent: Agent) -> None:
		"""Transition *agent* to the Immune state."""
		from modules.agent import AgentType, _list_remove

		if agent in self.dead:
			return
		if agent not in self.immune:
			self.immune.append(agent)
		else:
			return  # already immune — avoid double-processing

		agent._type = AgentType.IMMUNE
		self.canvas.itemconfig(agent.model, fill="green")
		_list_remove(self.sane, agent)
		_list_remove(self.infected, agent)

	def kill(self, agent: Agent) -> None:
		"""Transition *agent* to the Dead state."""
		from modules.agent import AgentType, _list_remove

		if agent in self.dead:
			return
		self.dead.append(agent)

		agent._type = AgentType.DEAD
		self.canvas.itemconfig(agent.model, fill="grey")
		self.canvas.tag_lower(agent.model)
		_list_remove(self.sane, agent)
		_list_remove(self.infected, agent)

	# Inter-zone transfer

	def transfer_agent_to(
		self,
		agent: Agent,
		destination: SimulationZone,
	) -> None:
		"""
		Remove *agent* from this zone and spawn an equivalent new agent
		in *destination*, complete with fresh movement / infection threads.

		The new agent's ``run_movement`` receives ``self`` as *origin_zone*
		so that quarantined agents can find their way back once cured.
		"""
		from modules.agent import AgentType, _list_remove
		from modules.state import state

		agent_type = agent.type
		symptomless = agent.is_symptomless

		# Remove from every list in this zone
		for lst in (self.sane, self.infected, self.immune, self.dead, self.agents):
			_list_remove(lst, agent)

		# Delete canvas items; any threads still using them will hit ValueError
		# and exit naturally.
		self.canvas.delete(agent.model)
		if agent.infection_zone is not None:
			self.canvas.delete(agent.infection_zone)
			agent.infection_zone = None

		# Spawn replacement in destination
		new_agent = destination.spawn_agent(agent_type, symptomless)

		if state.is_running and new_agent.type != AgentType.DEAD:
			destination.spawn_thread(new_agent.run_movement, (self,))
			if new_agent.type == AgentType.INFECTED:
				destination.spawn_thread(new_agent.run_infection)

	# Agent factory

	def spawn_agent(
		self,
		agent_type: AgentType,
		is_symptomless: bool | None = None,
	) -> Agent:
		"""Create and register a new agent of *agent_type* at a random position."""
		from modules.agent import Agent
		from modules.state import state

		cfg = state.config
		x = random.randint(0, cfg.canvas_width)
		y = random.randint(0, cfg.canvas_height)

		if is_symptomless is None:
			symptomless = (
				cfg.enable_symptomless_agents
				and random.random() <= cfg.symptomless_agents_chance
			)
		else:
			symptomless = is_symptomless

		# Agent.__init__ calls self._register(agent) automatically
		return Agent(self, x, y, agent_type, symptomless)

	# Thread management

	def spawn_thread(self, func, args: tuple = ()) -> Thread:
		"""Start a daemon thread, register it, and return it."""
		t = Thread(target=func, args=args, daemon=True)
		t.start()
		self.threads.append(t)
		return t

	def stop_all_threads(self) -> None:
		"""Clear the thread list (signals all thread loops to exit)."""
		self.threads.clear()
