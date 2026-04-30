"""
Main application window and all dialog boxes.

``Application`` inherits from ``tk.Tk`` and owns every widget.  It also
exposes a small public API that the simulation threads call to update
labels without reaching into the widget tree themselves.
"""
from __future__ import annotations

import sys
import os
import tkinter as tk
import tkinter.ttk as ttk
import tkinter.messagebox as tkmb
from typing import Optional

from PIL import Image, ImageTk

from modules.config import Config, WINDOW_WIDTH, WINDOW_HEIGHT
from modules.graph import GraphGenerator
from modules.state import state


# Path resolution (works for normal run and PyInstaller bundle)

def _asset(filename: str) -> str:
	if getattr(sys, "frozen", False):
		base = sys._MEIPASS  # type: ignore[attr-defined]
	else:
		base = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
	return os.path.join(base, "assets", filename)


# Helper: create a packed ttk.Frame

def _frame(
	parent: tk.Widget,
	side: str,
	*,
	padding: tuple[int, int, int, int] = (0, 0, 0, 0),
	fill: Optional[str] = None,
	expand: bool = False,
	anchor: Optional[str] = None,
	ipady: int = 0,
) -> ttk.Frame:
	f = ttk.Frame(parent, padding=padding)
	f.pack(side=side, fill=fill, expand=expand, anchor=anchor, ipady=ipady)
	return f


# Application window

class Application(tk.Tk):
	"""Root window of ReVirtuVirus."""

	_ENABLE_DEBUG_BUTTONS: bool = False

	def __init__(self) -> None:
		super().__init__()

		self._setup_window()
		self._build_layout()

		# Connect state back to this window so threads can call our API
		state.gui = self

	# Window initialisation

	def _setup_window(self) -> None:
		self.title("ReVirtuVirus")
		self.iconname("ReVirtuVirus")
		self.wm_title("ReVirtuVirus")
		self.wm_iconname("ReVirtuVirus")
		self.minsize(WINDOW_WIDTH, WINDOW_HEIGHT)

		if "win" in sys.platform and "darwin" not in sys.platform:
			try:
				self.wm_iconbitmap(default=_asset("icon.ico"))
			except Exception:
				print("Could not set .ico icon.")
		else:
			img = tk.PhotoImage(file=_asset("icon.png"))
			self.tk.call("wm", "iconphoto", self._w, img)

		style = ttk.Style(self)
		style.theme_use("vista" if "win" in sys.platform else "clam")

	# ── Widget layout ─────────────────────────────────────────────────────────

	def _build_layout(self) -> None:
		# ── Top section: simulation canvases (right) + control panel (left) ──
		top = _frame(self, tk.TOP, fill="both", expand=True)

		# Canvas area
		canvas_zone = _frame(top, tk.RIGHT, fill="both", expand=True)
		self.bg_canvas = tk.Canvas(canvas_zone, bg="grey")
		self.bg_canvas.pack(fill="both", expand=True)

		# Control panel
		ctrl = _frame(top, tk.LEFT)

		# Logo
		logo_img = Image.open(_asset("icon.png")).resize(
			(int(WINDOW_WIDTH / 5.2), int(WINDOW_HEIGHT / 4)),
			Image.Resampling.LANCZOS,
		)
		self._logo_ref = ImageTk.PhotoImage(logo_img)
		tk.Label(ctrl, image=self._logo_ref).pack(side=tk.TOP)
		tk.Label(ctrl, text="ReVirtuVirus", font=("Helvetica", 20)).pack(side=tk.TOP, pady=(0, 20))

		# Simulation buttons
		sim_ctrl = _frame(ctrl, tk.TOP, padding=(5, 5, 5, 5), ipady=10)
		ttk.Label(sim_ctrl, text="Simulation", padding=(5, 5, 5, 5), font=("Helvetica", 10, "bold")).pack(side=tk.TOP)

		btn_row = _frame(sim_ctrl, tk.TOP)
		self.btn_start = ttk.Button(btn_row, text="Start", padding=(2, 2, 2, 2), command=self._on_start)
		self.btn_start.pack(side=tk.LEFT)
		self.btn_stop = ttk.Button(btn_row, text="Stop", padding=(2, 2, 2, 2), command=self._on_stop, state=tk.DISABLED)
		self.btn_stop.pack(side=tk.RIGHT)

		self.btn_pause = ttk.Button(sim_ctrl, text="Pause Simulation", padding=(2, 2, 2, 2), command=self.pause_or_resume, state=tk.DISABLED)
		self.btn_pause.pack(side=tk.TOP)
		self.btn_clear = ttk.Button(sim_ctrl, text="Clear Simulation", padding=(2, 2, 2, 2), command=self._on_clear)
		self.btn_clear.pack(side=tk.TOP)
		self.btn_settings = ttk.Button(sim_ctrl, text="Modify Settings", padding=(2, 2, 2, 2), command=lambda: SettingsDialog(self))
		self.btn_settings.pack(side=tk.TOP)
		self.btn_graph = ttk.Button(sim_ctrl, text="Show Graph", padding=(2, 2, 2, 2), command=lambda: GraphDialog(self), state=tk.DISABLED)
		self.btn_graph.pack(side=tk.TOP)

		if self._ENABLE_DEBUG_BUTTONS:
			ttk.Button(sim_ctrl, text="Print State", padding=(2, 2, 2, 2), command=lambda: print(vars(state))).pack(side=tk.TOP)

		# Agent counters
		agent_ctrl = _frame(ctrl, tk.TOP, padding=(5, 5, 5, 5))
		ttk.Label(agent_ctrl, text="Agents", padding=(5, 5, 5, 5), font=("Helvetica", 10, "bold")).pack(side=tk.TOP)
		counter_zone = _frame(agent_ctrl, tk.LEFT)
		self.lbl_sane	= ttk.Label(counter_zone, text="Sane : 0");	self.lbl_sane.pack(side=tk.TOP)
		self.lbl_infected= ttk.Label(counter_zone, text="Infected : 0"); self.lbl_infected.pack(side=tk.TOP)
		self.lbl_immune  = ttk.Label(counter_zone, text="Immune : 0");  self.lbl_immune.pack(side=tk.TOP)
		self.lbl_dead	= ttk.Label(counter_zone, text="Dead : 0");	self.lbl_dead.pack(side=tk.TOP)

		# Status bar
		status_zone = _frame(self, tk.BOTTOM, padding=(5, 5, 5, 5), fill="x")
		self.lbl_status = ttk.Label(status_zone, text="No simulation zone has been spawned.", padding=(10, 0, 0, 0))
		self.lbl_status.pack(side=tk.LEFT)
		self.lbl_time = ttk.Label(status_zone, text="Time has not been initiated.", padding=(0, 0, 5, 0))
		self.lbl_time.pack(side=tk.RIGHT)

	# Public API (called from simulation threads)

	def update_counts(self, sane: int, infected: int, immune: int, dead: int) -> None:
		self.lbl_sane.config(text=f"Sane : {sane}")
		self.lbl_infected.config(text=f"Infected : {infected}")
		self.lbl_immune.config(text=f"Immune : {immune}")
		self.lbl_dead.config(text=f"Dead : {dead}")

	def set_status(self, text: str) -> None:
		self.lbl_status.config(text=text)

	def set_time_label(self, text: str) -> None:
		self.lbl_time.config(text=text)

	def set_pause_button_text(self, text: str) -> None:
		self.btn_pause.config(text=text)

	# Simulation controls

	def _on_start(self) -> None:
		from modules.simulation import runner

		if state.simulations is None:
			tkmb.showwarning(
				"Warning",
				'No simulation zone has been spawned. Use the "Modify Settings" button to spawn them.',
			)
			return

		print("Starting simulation…")
		self.btn_start.config(state=tk.DISABLED)
		self.btn_settings.config(state=tk.DISABLED)
		self.btn_clear.config(state=tk.DISABLED)
		self.btn_pause.config(state=tk.NORMAL)
		self.btn_stop.config(state=tk.NORMAL)
		self.btn_graph.config(state=tk.NORMAL)
		self.set_status("Attempting to start the simulation…")
		self.lbl_time.config(text="Initiating time…")

		runner.start(state.simulations)

	def _on_stop(self) -> None:
		from modules.simulation import runner

		print("Stopping simulation…")
		self.btn_start.config(state=tk.DISABLED)
		self.btn_settings.config(state=tk.NORMAL)
		self.btn_clear.config(state=tk.NORMAL)
		self.btn_pause.config(state=tk.DISABLED)
		self.btn_stop.config(state=tk.DISABLED)
		self.btn_graph.config(state=tk.NORMAL)
		self.set_status("Attempting to stop simulation…")

		if state.simulations:
			runner.stop(state.simulations)

	def _on_clear(self) -> None:
		self._clear_canvas_zone()
		self.btn_start.config(state=tk.NORMAL)
		self.btn_pause.config(state=tk.DISABLED)
		self.btn_stop.config(state=tk.DISABLED)
		self.btn_graph.config(state=tk.DISABLED)
		self.set_status("No simulation zone has been spawned.")
		self.lbl_time.config(text="Time has not been initiated.")

	def pause_or_resume(self) -> None:
		if not state.is_paused:
			print("Pausing simulation…")
			state.is_paused = True
			self.btn_pause.config(text="Resume Simulation")
			self.set_status("Simulation is paused.")
		else:
			print("Resuming simulation…")
			state.is_paused = False
			self.btn_pause.config(text="Pause Simulation")
			self.set_status("Simulation has resumed.")

	# Canvas / zone management

	def spawn_zones(self, cfg: Config) -> None:
		"""Create simulation canvases and populate them with agents."""
		from modules.agent import AgentType
		from modules.simulation_zone import SimulationZone

		self._clear_canvas_zone()

		n = cfg.simulation_quantity
		w, h = cfg.canvas_width, cfg.canvas_height
		zones: list[SimulationZone] = []

		col, row = 0, 0
		for idx in range(n):
			is_quar = cfg.is_last_simulation_quarantine and idx == n - 1 and n > 1
			canvas = tk.Canvas(self.bg_canvas, width=w, height=h, bg="white")
			canvas.grid(row=row, column=col, sticky="NSEW", padx=2, pady=2)
			canvas.grid_propagate(False)

			zone = SimulationZone(canvas, is_quarantine=is_quar)
			if is_quar:
				canvas.config(highlightthickness=2, highlightbackground="red")
				state.quarantine = zone
			zones.append(zone)

			col += 1
			if col >= 5:
				col, row = 0, row + 1

		state.simulations = zones

		# Populate non-quarantine zones with agents
		for zone in zones:
			if not zone.is_quarantine:
				for _ in range(cfg.number_of_sane_agents):
					zone.spawn_agent(AgentType.SANE)
				for _ in range(cfg.number_of_infected_agents):
					zone.spawn_agent(AgentType.INFECTED)
				for _ in range(cfg.number_of_immune_agents):
					zone.spawn_agent(AgentType.IMMUNE)

		# Update minimum window size
		active_count = n - (1 if cfg.is_last_simulation_quarantine and n > 1 else 0)
		self.minsize(
			int(w * min(5, n) + 200),
			max(int(h * (row + 1) + 55), WINDOW_HEIGHT),
		)

		# Update buttons
		self.btn_start.config(state=tk.NORMAL)
		self.btn_pause.config(state=tk.DISABLED)
		self.btn_stop.config(state=tk.DISABLED)
		self.btn_graph.config(state=tk.DISABLED)

		# Update initial counts
		sane_n = cfg.number_of_sane_agents * active_count
		inf_n  = cfg.number_of_infected_agents * active_count
		imm_n  = cfg.number_of_immune_agents * active_count
		self.update_counts(sane_n, inf_n, imm_n, 0)

		self.set_status("The simulation has not been started.")
		self.lbl_time.config(text="Waiting for simulation to start…")

	def _clear_canvas_zone(self) -> None:
		for widget in self.bg_canvas.grid_slaves():
			widget.destroy()
		self.bg_canvas.config(width=0, height=0)

		state.simulations = None
		state.quarantine = None
		state.reset_data()
		state.is_running = False
		state.is_paused = False
		self.minsize(WINDOW_WIDTH, WINDOW_HEIGHT)
		self.update_counts(0, 0, 0, 0)


# Settings dialog

class SettingsDialog(tk.Toplevel):
	"""Modal dialog for adjusting all simulation parameters."""

	def __init__(self, parent: Application) -> None:
		super().__init__()
		self.parent_app = parent
		self.title("Simulation Setup")
		self.iconname("Simulation Setup")
		self.wm_title("Simulation Setup")
		self.wm_iconname("Simulation Setup")
		self.resizable(False, False)
		self.grab_set()
		self.wm_transient(parent)

		if "win" in sys.platform and "darwin" not in sys.platform:
			try:
				self.wm_iconbitmap(default=_asset("icon.ico"))
			except Exception:
				pass
		else:
			img = tk.PhotoImage(file=_asset("icon.png"))
			self.tk.call("wm", "iconphoto", self._w, img)

		self._build()

	def _build(self) -> None:
		main = _frame(self, tk.TOP, fill="both", expand=True)

		# Simulation column
		sim_f = _frame(main, tk.LEFT, padding=(5, 5, 5, 5), ipady=10, anchor=tk.N)
		ttk.Label(sim_f, text="Simulation", padding=(5, 5, 5, 5), font=("Helvetica", 10, "bold")).pack(side=tk.TOP)

		self.e_sim_count   = self._labeled_entry(sim_f, "Number of simulations (1-15) :", "4", width=3)
		self.e_framerate   = self._labeled_entry(sim_f, "Framerate :", "24", width=3)
		self.e_width	   = self._labeled_entry(sim_f, "Width (300 max) :", "300", width=4)
		self.e_height	  = self._labeled_entry(sim_f, "Height (300 max) :", "300", width=4)
		self.cb_quarantine = self._labeled_checkbox(sim_f, "Make last simulation quarantine :", checked=True)

		# Agents column
		ag_f = _frame(main, tk.LEFT, padding=(5, 5, 5, 5), ipady=10, anchor=tk.N)
		ttk.Label(ag_f, text="Agents", padding=(5, 5, 5, 5), font=("Helvetica", 10, "bold")).pack(side=tk.TOP)

		self.e_sane	 = self._labeled_entry(ag_f, "Sane agents per simulation :", "99", width=4)
		self.e_infected = self._labeled_entry(ag_f, "Infected agents per simulation :", "1", width=3)
		self.e_immune   = self._labeled_entry(ag_f, "Immune agents per simulation :", "0", width=3)
		self.e_speed	= self._labeled_entry(ag_f, "Maximum agent speed (px/s) :", "48", width=3)
		self.e_size	 = self._labeled_entry(ag_f, "Agent size (pixels) :", "10", width=3)
		self.cb_symptomless	   = self._labeled_checkbox(ag_f, "Enable symptomless agents :", checked=True)
		self.e_symptomless_chance = self._labeled_entry(ag_f, "Chance of symptomless (0-100) :", "3", width=3)

		# Behaviours column
		beh_f = _frame(main, tk.LEFT, padding=(5, 5, 5, 5), ipady=10, anchor=tk.N)
		ttk.Label(beh_f, text="Behaviours", padding=(5, 5, 5, 5), font=("Helvetica", 10, "bold")).pack(side=tk.TOP)

		self.cb_central_travel   = self._labeled_checkbox(beh_f, "Enable central travel :", checked=True)
		self.e_central_chance	= self._labeled_entry(beh_f, "Central travel chance (0-100) :", "5", width=3)
		self.cb_obvious_travel   = self._labeled_checkbox(beh_f, "Make central travel obvious :", checked=False)
		self.e_center_range	  = self._labeled_entry(beh_f, "Center range (pixels) :", "30", width=3)
		self.cb_human_logic	  = self._labeled_checkbox(beh_f, "Enable human logic :", checked=True)
		self.e_quarantine_timer  = self._labeled_entry(beh_f, "Time before quarantine (s) :", "3", width=2)

		# Virus column
		vir_f = _frame(main, tk.LEFT, padding=(5, 5, 5, 5), ipady=10, anchor=tk.N)
		ttk.Label(vir_f, text="Virus", padding=(5, 5, 5, 5), font=("Helvetica", 10, "bold")).pack(side=tk.TOP)

		self.e_infective_range   = self._labeled_entry(vir_f, "Infective range :", "4", width=2)
		self.e_infection_risk	= self._labeled_entry(vir_f, "Infection risk/s (0-100) :", "48", width=3)
		self.e_recovery_chance   = self._labeled_entry(vir_f, "Recovery chance/s (0-100)/10 :", "24", width=3)
		self.e_recovery_progress = self._labeled_entry(vir_f, "Recovery progress/s (0-100)/1000 :", "36", width=3)
		self.e_death_risk		= self._labeled_entry(vir_f, "Death risk/s (0-100)/10 :", "18", width=3)

		# Bottom buttons
		bot = _frame(self, tk.BOTTOM, padding=(5, 5, 5, 5))
		ttk.Button(bot, text="Spawn", padding=(2, 2, 2, 2), command=self._on_spawn).pack(side=tk.LEFT)
		ttk.Button(bot, text="Cancel", padding=(2, 2, 2, 2), command=self.destroy).pack(side=tk.RIGHT)

	# Widget factory helpers

	def _labeled_entry(
		self, parent: tk.Widget, label: str, default: str, width: int = 5
	) -> ttk.Entry:
		row = _frame(parent, tk.TOP, anchor=tk.W)
		ttk.Label(row, text=label, padding=(5, 5, 5, 5)).pack(side=tk.LEFT)
		entry = ttk.Entry(row, width=width)
		entry.pack(side=tk.RIGHT)
		entry.insert(0, default)
		return entry

	def _labeled_checkbox(
		self, parent: tk.Widget, label: str, *, checked: bool
	) -> ttk.Checkbutton:
		row = _frame(parent, tk.TOP, anchor=tk.W)
		ttk.Label(row, text=label, padding=(5, 5, 5, 5)).pack(side=tk.LEFT)
		cb = ttk.Checkbutton(row, variable=tk.IntVar())
		cb.pack(side=tk.RIGHT)
		if checked:
			cb.state(["selected"])
		return cb

	@staticmethod
	def _is_checked(cb: ttk.Checkbutton) -> bool:
		try:
			return cb.state()[0] == "selected"
		except Exception:
			return False

	# Apply settings

	def _on_spawn(self) -> None:
		try:
			cfg = Config.from_ui_values(
				simulation_quantity=int(self.e_sim_count.get()),
				framerate=int(self.e_framerate.get()),
				canvas_width=int(self.e_width.get()),
				canvas_height=int(self.e_height.get()),
				is_last_simulation_quarantine=self._is_checked(self.cb_quarantine),
				quarantine_timer_limit=int(self.e_quarantine_timer.get()),
				number_of_sane_agents=int(self.e_sane.get()),
				number_of_infected_agents=int(self.e_infected.get()),
				number_of_immune_agents=int(self.e_immune.get()),
				maximum_agent_speed=int(self.e_speed.get()),
				agent_size=int(self.e_size.get()),
				is_central_travel_enabled=self._is_checked(self.cb_central_travel),
				central_travel_chance_pct=int(self.e_central_chance.get()),
				center_range=int(self.e_center_range.get()),
				make_central_travel_obvious=self._is_checked(self.cb_obvious_travel),
				is_human_logic_enabled=self._is_checked(self.cb_human_logic),
				infective_range=int(self.e_infective_range.get()),
				infection_risk_pct=int(self.e_infection_risk.get()),
				default_recovery_chance_pct=int(self.e_recovery_chance.get()),
				recovery_chance_progress_pct=int(self.e_recovery_progress.get()),
				death_risk_pct=int(self.e_death_risk.get()),
				enable_symptomless_agents=self._is_checked(self.cb_symptomless),
				symptomless_agents_chance_pct=int(self.e_symptomless_chance.get()),
			)
		except ValueError as exc:
			tkmb.showerror("Invalid input", f"Please check your settings:\n{exc}")
			return

		state.config = cfg
		self.destroy()
		print("Settings applied.")

		self.parent_app.spawn_zones(cfg)


# Graph selection dialog

class GraphDialog(tk.Toplevel):
	"""Modal dialog for choosing graph parameters, then generating the plot."""

	def __init__(self, parent: Application) -> None:
		super().__init__()
		self.title("Graph Selection")
		self.iconname("Graph Selection")
		self.wm_title("Graph Selection")
		self.wm_iconname("Graph Selection")
		self.resizable(False, False)
		self.grab_set()
		self.wm_transient(parent)

		if "win" in sys.platform and "darwin" not in sys.platform:
			try:
				self.wm_iconbitmap(default=_asset("icon.ico"))
			except Exception:
				pass
		else:
			img = tk.PhotoImage(file=_asset("icon.png"))
			self.tk.call("wm", "iconphoto", self._w, img)

		# Auto-pause if running
		if not state.is_paused and state.is_running:
			parent.pause_or_resume()

		self._build()

	def _build(self) -> None:
		main = _frame(self, tk.TOP, fill="both", expand=True)

		# Data type
		self.v_data_type = tk.StringVar(value="total")
		dt_f = _frame(main, tk.LEFT, padding=(5, 5, 5, 5), ipady=10, anchor=tk.N)
		ttk.Label(dt_f, text="Data Type", font=("Helvetica", 10, "bold"), padding=(5, 5, 5, 5)).pack(side=tk.TOP, anchor=tk.N)
		ttk.Radiobutton(dt_f, text="Total", variable=self.v_data_type, value="total").pack(anchor=tk.W)
		ttk.Radiobutton(dt_f, text="Mean",  variable=self.v_data_type, value="mean").pack(anchor=tk.W)

		# Graph type
		self.v_graph_type = tk.StringVar(value="line")
		gt_f = _frame(main, tk.LEFT, padding=(5, 5, 5, 5), ipady=10, anchor=tk.N)
		ttk.Label(gt_f, text="Graph Type", font=("Helvetica", 10, "bold"), padding=(5, 5, 5, 5)).pack(side=tk.TOP, anchor=tk.N)
		ttk.Radiobutton(gt_f, text="Lines",	   variable=self.v_graph_type, value="line").pack(anchor=tk.W)
		ttk.Radiobutton(gt_f, text="Bars (heavy)", variable=self.v_graph_type, value="bar").pack(anchor=tk.W)
		ttk.Radiobutton(gt_f, text="Sums",		variable=self.v_graph_type, value="sum").pack(anchor=tk.W)

		# Simulation selection
		sim_f = _frame(main, tk.LEFT, padding=(5, 5, 5, 5), ipady=10, anchor=tk.N)
		ttk.Label(sim_f, text="Simulations", font=("Helvetica", 10, "bold"), padding=(5, 5, 5, 5)).pack(side=tk.TOP, anchor=tk.N)
		self.lb_sims = tk.Listbox(sim_f, selectmode=tk.MULTIPLE, height=5, width=15)
		self.lb_sims.pack(side=tk.LEFT, anchor=tk.N, expand=True, fill=tk.Y)
		sb = ttk.Scrollbar(sim_f, orient=tk.VERTICAL, command=self.lb_sims.yview)
		sb.pack(side=tk.RIGHT, anchor=tk.N, fill=tk.Y)
		self.lb_sims["yscrollcommand"] = sb.set

		if state.simulations:
			for i, zone in enumerate(state.simulations):
				label = "Quarantine" if zone.is_quarantine else f"Simulation {i + 1}"
				self.lb_sims.insert("end", label)

		# Agent toggles
		ag_f = _frame(main, tk.LEFT, padding=(5, 5, 5, 5), ipady=10, anchor=tk.N)
		ttk.Label(ag_f, text="Agents", font=("Helvetica", 10, "bold"), padding=(5, 5, 5, 5)).pack(side=tk.TOP, anchor=tk.N)
		self.cb_sane	 = self._agent_checkbox(ag_f, "Sane :", checked=True)
		self.cb_infected = self._agent_checkbox(ag_f, "Infected :", checked=True)
		self.cb_immune   = self._agent_checkbox(ag_f, "Immune :", checked=True)
		self.cb_dead	 = self._agent_checkbox(ag_f, "Dead :", checked=True)

		# Time format
		self.v_time_fmt = tk.StringVar(value="frames")
		tf_f = _frame(main, tk.LEFT, padding=(5, 5, 5, 5), ipady=10, anchor=tk.N)
		ttk.Label(tf_f, text="Time Format", font=("Helvetica", 10, "bold"), padding=(5, 5, 5, 5)).pack(side=tk.TOP, anchor=tk.N)
		ttk.Radiobutton(tf_f, text="Frames",			   variable=self.v_time_fmt, value="frames").pack(anchor=tk.W)
		ttk.Radiobutton(tf_f, text="Seconds (in-sim)",	 variable=self.v_time_fmt, value="seconds").pack(anchor=tk.W)

		# Bottom buttons
		bot = _frame(self, tk.BOTTOM, padding=(5, 5, 5, 5))
		ttk.Button(bot, text="Generate", padding=(2, 2, 2, 2), command=self._on_generate).pack(side=tk.LEFT)
		ttk.Button(bot, text="Close",	padding=(2, 2, 2, 2), command=self.destroy).pack(side=tk.RIGHT)

	def _agent_checkbox(self, parent: tk.Widget, label: str, *, checked: bool) -> ttk.Checkbutton:
		row = _frame(parent, tk.TOP, anchor=tk.W)
		ttk.Label(row, text=label, padding=(5, 5, 5, 5)).pack(side=tk.LEFT, anchor=tk.N)
		cb = ttk.Checkbutton(row, variable=tk.IntVar())
		cb.pack(side=tk.RIGHT)
		if checked:
			cb.state(["selected"])
		return cb

	@staticmethod
	def _is_checked(cb: ttk.Checkbutton) -> bool:
		try:
			return cb.state()[0] == "selected"
		except Exception:
			return False

	def _on_generate(self) -> None:
		selected_sims = [i for i in range(self.lb_sims.size()) if self.lb_sims.selection_includes(i)]
		if not selected_sims:
			tkmb.showerror("Error", "No simulations were selected.")
			return

		GraphGenerator().generate(
			data_type=self.v_data_type.get(),
			graph_type=self.v_graph_type.get(),
			selected_simulations=selected_sims,
			selected_agents={
				"Sane":	 self._is_checked(self.cb_sane),
				"Infected": self._is_checked(self.cb_infected),
				"Immune":   self._is_checked(self.cb_immune),
				"Dead":	 self._is_checked(self.cb_dead),
			},
			time_format=self.v_time_fmt.get(),
		)
