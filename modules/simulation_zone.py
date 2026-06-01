"""
``SimulationZone`` wraps a Tkinter canvas together with its agent lists.

One worker thread is assigned per zone at simulation start.  Each frame
the thread calls ``move()`` then ``infect()`` on every agent, then waits
at a shared ``threading.Barrier`` so all zones stay in lock-step.
"""
from __future__ import annotations

import random
import time
from threading import Barrier, Thread
from typing import TYPE_CHECKING

import tkinter as tk

if TYPE_CHECKING:
	from modules.agent import Agent, AgentType


class SimulationZone:
	"""
	One simulation canvas plus bookkeeping for agents and the zone thread.

	Agent lists are plain Python lists so iteration order is stable and
	list semantics (remove, append, ``in``) work everywhere.
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

		# The single worker thread for this zone (set by SimulationRunner.start)
		self._thread: Thread | None = None
		self._running: bool = False

		# Agents that became infected mid-frame and need their infection oval
		# created at the top of the next infect pass (avoids mutating self.sane
		# while we are iterating over it in infect()).
		self._pending_infect: list[Agent] = []

	# Zone thread

	def run_frame_loop(self, barrier: Barrier) -> None:
		"""
		Thread target.  Runs the simulation loop for this zone:

		1. Move all agents.
		2. Flush pending-infect queue (Sane → Infected transitions).
		3. Run infection logic on every infected agent.
		4. Wait at the barrier until all other zones finish the same frame.
		"""
		from modules.state import state

		cfg = state.config
		self._running = True

		while state.is_running and self._running:
			_wait_if_paused()

			# Step 1: move
			for agent in list(self.agents):
				agent.move()

			# Step 2: flush newly infected agents
			for agent in self._pending_infect:
				_list_remove(self.sane, agent)
				if agent not in self.infected:
					self.infected.append(agent)
				agent._type.__class__  # ensure import is resolved
				from modules.agent import AgentType
				agent._type = AgentType.INFECTED
				self.canvas.itemconfig(agent.model, fill=agent._current_color)
			self._pending_infect.clear()

			# Step 3: infect
			for agent in list(self.infected):
				agent.infect()

			# Step 4: barrier
			try:
				barrier.wait()
			except Exception:
				# Barrier broken (e.g. simulation stopped) — exit cleanly
				break

			time.sleep(1 / cfg.framerate)

	def stop(self) -> None:
		"""Signal the frame loop to exit."""
		self._running = False

	# Infection queue

	def begin_infect(self, agent: Agent) -> None:
		"""
		Mark a Sane agent as newly infected.

		The actual list transition happens at the top of the next frame so
		we never mutate ``self.sane`` while ``infect()`` is iterating it.
		"""
		from modules.agent import AgentType
		if agent._type == AgentType.SANE and agent not in self._pending_infect:
			self._pending_infect.append(agent)

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
		from modules.agent import AgentType

		if agent in self.dead or agent in self.immune:
			return
		self.immune.append(agent)
		agent._type = AgentType.IMMUNE
		self.canvas.itemconfig(agent.model, fill="green")
		_list_remove(self.sane, agent)
		_list_remove(self.infected, agent)

	def kill(self, agent: Agent) -> None:
		"""Transition *agent* to the Dead state."""
		from modules.agent import AgentType

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
		Remove *agent* from this zone and create an equivalent new agent in
		*destination*.  The new agent carries ``self`` as its ``origin_zone``
		so quarantined agents can return once they recover.
		"""
		agent_type  = agent.type
		symptomless = agent.is_symptomless

		# Remove from every list in this zone
		for lst in (self.sane, self.infected, self.immune, self.dead, self.agents):
			_list_remove(lst, agent)

		# Delete canvas items (the frame loop may attempt coords() on them
		# and will get a ValueError, which each method handles gracefully)
		self.canvas.delete(agent.model)
		agent._clear_infection_zone()

		# Spawn equivalent agent in the destination zone
		destination.spawn_agent(agent_type, symptomless, origin_zone=self)

	# Agent factory

	def spawn_agent(
		self,
		agent_type: AgentType,
		is_symptomless: bool | None = None,
		*,
		origin_zone: SimulationZone | None = None,
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
		return Agent(self, x, y, agent_type, symptomless, origin_zone=origin_zone)


# Helpers

def _list_remove(lst: list[Agent], agent: Agent) -> None:
	try:
		lst.remove(agent)
	except ValueError:
		pass

def _wait_if_paused() -> None:
	from modules.state import state
	while state.is_paused:
		time.sleep(0.05)
