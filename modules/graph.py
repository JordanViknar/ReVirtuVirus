"""
Graph generation for post-run analysis.

``GraphGenerator.generate()`` reads the collected frame data from
``AppState`` and plots it with Matplotlib.
"""
from __future__ import annotations

from matplotlib import use as _mpl_use
_mpl_use("TkAgg")

import matplotlib.pyplot as plt


class GraphGenerator:
	"""Builds and shows a Matplotlib figure from collected simulation data."""

	# Agent categories in a consistent order
	CATEGORIES: tuple[str, ...] = ("Sane", "Infected", "Immune", "Dead")
	COLORS: dict[str, str] = {
		"Sane": "blue",
		"Infected": "red",
		"Immune": "green",
		"Dead": "black",
	}

	def generate(
		self,
		data_type: str,		   # "total" | "mean"
		graph_type: str,		  # "line" | "bar" | "sum"
		selected_simulations: list[int],
		selected_agents: dict[str, bool],
		time_format: str,		 # "frames" | "seconds"
	) -> None:
		"""Build and display the requested graph. Does nothing if no simulations selected."""
		from modules.state import state

		if not selected_simulations:
			return

		plt.close()

		raw = state.get_collected_data()
		series = self._aggregate(raw, data_type, selected_simulations)

		if time_format == "seconds":
			series = self._resample_to_seconds(series, state.config.framerate)

		self._plot(graph_type, series, selected_agents)
		self._label_axes(data_type, time_format)
		plt.show()

	# Private helpers

	def _aggregate(
		self,
		raw: list[list[dict[str, int]]],
		data_type: str,
		selected: list[int],
	) -> dict[str, list[float]]:
		"""Sum (or average) agent counts across selected simulations per frame."""
		series: dict[str, list[float]] = {c: [] for c in self.CATEGORIES}

		for frame in raw:
			totals = {c: 0 for c in self.CATEGORIES}
			for sim_data in frame:
				if sim_data["Index"] in selected:
					for cat in self.CATEGORIES:
						totals[cat] += sim_data[cat]

			divisor = len(selected) if data_type == "mean" else 1
			for cat in self.CATEGORIES:
				series[cat].append(totals[cat] / divisor)

		return series

	def _resample_to_seconds(
		self,
		series: dict[str, list[float]],
		framerate: int,
	) -> dict[str, list[float]]:
		"""Collapse per-frame data into per-second averages."""
		result: dict[str, list[float]] = {c: [] for c in self.CATEGORIES}
		n = len(series[self.CATEGORIES[0]])

		for i in range(0, n, framerate):
			chunk = range(i, min(i + framerate, n))
			count = len(chunk)
			for cat in self.CATEGORIES:
				avg = sum(series[cat][j] for j in chunk) / count
				result[cat].append(avg)

		return result

	def _plot(
		self,
		graph_type: str,
		series: dict[str, list[float]],
		selected: dict[str, bool],
	) -> None:
		active_cats = [c for c in self.CATEGORIES if selected.get(c)]
		x = range(len(series[self.CATEGORIES[0]]))

		match graph_type:
			case "line":
				for cat in active_cats:
					plt.plot(series[cat], label=cat, color=self.COLORS[cat])

			case "bar":
				for cat in active_cats:
					plt.bar(x, series[cat], label=cat, color=self.COLORS[cat])

			case "sum":
				stacks = [series[c] for c in active_cats]
				labels = active_cats
				colors = [self.COLORS[c] for c in active_cats]
				plt.stackplot(x, stacks, labels=labels, colors=colors)

		plt.legend()

	def _label_axes(self, data_type: str, time_format: str) -> None:
		y_label, title_base = {
			"total": ("Population", "Agent population"),
			"mean":  ("Mean agent population", "Mean of the agent populations"),
		}[data_type]

		x_label, title_suffix = {
			"frames":  ("Frames", "over time (in frames)"),
			"seconds": ("Seconds (in-simulation)", "over time (in simulation seconds)"),
		}[time_format]

		plt.ylabel(y_label)
		plt.xlabel(x_label)
		plt.title(f"{title_base} {title_suffix}")
