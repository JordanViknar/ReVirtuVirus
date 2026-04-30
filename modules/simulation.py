"""
Simulation lifecycle management and the clock thread.

``SimulationRunner`` starts / stops / pauses the simulation.
``ClockThread`` runs as a background thread to update counts and detect
the end condition (no more infected agents).
"""
from __future__ import annotations

import time
import tkinter.messagebox as tkmb
from threading import Thread
from typing import TYPE_CHECKING

if TYPE_CHECKING:
	from modules.simulation_zone import SimulationZone

class SimulationRunner:
	"""Manages the start / stop / pause lifecycle of all simulation zones."""

	def __init__(self) -> None:
		self._clock_thread: Thread | None = None

	# Public API

	def start(self, zones: list[SimulationZone]) -> None:
		from modules.agent import AgentType
		from modules.state import state

		state.is_running = True

		# Start the clock
		self._clock_thread = Thread(target=self._run_clock, daemon=True)
		self._clock_thread.start()

		# Kick off agent threads for every zone
		for zone in zones:
			for agent in zone.agents:
				if agent.type != AgentType.DEAD:
					zone.spawn_thread(agent.run_movement)
				if agent.type == AgentType.INFECTED:
					zone.spawn_thread(agent.run_infection)

		print("Simulation started.")
		if state.gui:
			state.gui.set_status("A simulation is currently running.")

	def stop(self, zones: list[SimulationZone]) -> None:
		from modules.state import state

		state.is_running = False
		state.is_paused = False

		for zone in zones:
			zone.stop_all_threads()

		print("Simulation stopped.")
		if state.gui:
			state.gui.set_status("The simulation has been stopped.")
			state.gui.set_pause_button_text("Pause Simulation")

	# Clock thread

	def _run_clock(self) -> None:
		from modules.state import state

		cfg = state.config
		frame_time = 0
		state.frame_time = 0
		state.reset_data()
		did_auto_pause = False

		while state.is_running:
			# Collect per-frame snapshot
			sane_count = state.total_count("Sane")
			infected_count = state.total_count("Infected")
			immune_count = state.total_count("Immune")
			dead_count = state.total_count("Dead")

			if state.gui:
				state.gui.update_counts(sane_count, infected_count, immune_count, dead_count)

			# Build per-simulation snapshot for the graph module
			if state.simulations:
				frame_data = [
					{
						"Index": i,
						"Sane": len(z.sane),
						"Infected": len(z.infected),
						"Immune": len(z.immune),
						"Dead": len(z.dead),
					}
					for i, z in enumerate(state.simulations)
				]
				state.add_frame_data(frame_data)

			if state.gui:
				state.gui.set_time_label(
					f"Frames : {frame_time} | Time (in-simulation) : {int(frame_time / cfg.framerate)}s"
				)

			# Auto-pause when infection is cleared
			if infected_count <= 0 and not did_auto_pause and not state.is_paused:
				from modules.gui import Application
				did_auto_pause = True
				if state.gui:
					state.gui.pause_or_resume()
				tkmb.showinfo(
					"Out of infected agents.",
					"There are no more infected agents. The simulation was automatically paused.",
				)

			_wait_if_paused()
			time.sleep(1 / cfg.framerate)
			frame_time += 1
			state.frame_time = frame_time


# Module helpers

def _wait_if_paused() -> None:
	from modules.state import state
	while state.is_paused:
		time.sleep(0.1)


# Module-level singleton used by the GUI
runner = SimulationRunner()
