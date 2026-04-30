"""
Simulation lifecycle management.

``SimulationRunner`` starts / stops / pauses the simulation.

On start:
  - A ``threading.Barrier(n_zones)`` is created so every zone's frame loop
	waits for all siblings before advancing to the next frame.
  - One daemon thread is spawned per zone, targeting ``zone.run_frame_loop``.
  - A separate clock thread collects stats and drives the UI labels.

On stop:
  - ``state.is_running`` is set to ``False`` and every zone's ``_running``
	flag is cleared, which causes all frame loops to exit at their next
	barrier wait.  The barrier itself is aborted to unblock any waiting threads.
"""
from __future__ import annotations

import time
import tkinter.messagebox as tkmb
from threading import Barrier, BrokenBarrierError, Thread
from typing import TYPE_CHECKING

if TYPE_CHECKING:
	from modules.simulation_zone import SimulationZone

class SimulationRunner:
	"""Manages the start / stop / pause lifecycle of all simulation zones."""

	def __init__(self) -> None:
		self._barrier: Barrier | None = None
		self._zone_threads: list[Thread] = []
		self._clock_thread: Thread | None = None

	# Public API

	def start(self, zones: list[SimulationZone]) -> None:
		from modules.state import state

		state.is_running = True
		state.reset_data()

		# One barrier shared by all zone threads
		self._barrier = Barrier(len(zones))

		# One thread per zone
		self._zone_threads = []
		for zone in zones:
			t = Thread(
				target=zone.run_frame_loop,
				args=(self._barrier,),
				daemon=True,
				name=f"zone-{'quarantine' if zone.is_quarantine else id(zone)}",
			)
			zone._thread = t
			self._zone_threads.append(t)

		# Clock thread (stats + UI updates)
		self._clock_thread = Thread(
			target=self._run_clock,
			daemon=True,
			name="simulation-clock",
		)

		# Start everything
		for t in self._zone_threads:
			t.start()
		self._clock_thread.start()

		print("Simulation started.")
		if state.gui:
			state.gui.set_status("A simulation is currently running.")

	def stop(self, zones: list[SimulationZone]) -> None:
		from modules.state import state

		state.is_running = False
		state.is_paused  = False

		# Signal every zone loop to exit
		for zone in zones:
			zone.stop()

		# Abort the barrier so any thread currently blocked in barrier.wait()
		# receives a BrokenBarrierError and exits cleanly
		if self._barrier is not None:
			self._barrier.abort()
			self._barrier = None

		self._zone_threads.clear()

		print("Simulation stopped.")
		if state.gui:
			state.gui.set_status("The simulation has been stopped.")
			state.gui.set_pause_button_text("Pause Simulation")

	# Clock thread

	def _run_clock(self) -> None:
		from modules.state import state

		cfg	= state.config
		frame_time = 0
		state.frame_time = 0
		did_auto_pause = False

		while state.is_running:
			_wait_if_paused()

			# Collect counts
			sane_count = state.total_count("Sane")
			infected_count = state.total_count("Infected")
			immune_count = state.total_count("Immune")
			dead_count = state.total_count("Dead")

			if state.gui:
				state.gui.update_counts(sane_count, infected_count, immune_count, dead_count)

			# Per-simulation snapshot for the graph module
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

			# Time label
			if state.gui:
				state.gui.set_time_label(
					f"Frames : {frame_time} | "
					f"Time (in-simulation) : {int(frame_time / cfg.framerate)}s"
				)

			# Auto-pause when no infected agents remain
			if infected_count <= 0 and not did_auto_pause and not state.is_paused:
				did_auto_pause = True
				if state.gui:
					state.gui.pause_or_resume()
				tkmb.showinfo(
					"Out of infected agents.",
					"There are no more infected agents. "
					"The simulation was automatically paused.",
				)

			time.sleep(1 / cfg.framerate)
			frame_time	  += 1
			state.frame_time = frame_time


# Helpers

def _wait_if_paused() -> None:
	from modules.state import state
	while state.is_paused:
		time.sleep(0.05)

# Module-level singleton used by the GUI
runner = SimulationRunner()
