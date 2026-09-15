#!/usr/bin/env python3
"""
Desktop GUI for dep-resolver.

Built with tkinter (Python stdlib) — no extra dependencies to install.
Reuses the exact same `resolver` package the CLI uses; this is just a
new frontend on top of the existing engine.

Run:
    python3 gui/app.py
"""

import json
import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from collections import deque

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from resolver import Universe, resolve  # noqa: E402
from resolver.pypi_source import build_universe_from_pypi, PyPIError  # noqa: E402

EXAMPLES_DIR = os.path.join(os.path.dirname(__file__), "..", "examples")

BG = "#1e1e2e"
PANEL = "#282a3a"
PANEL_HOVER = "#33364a"
FG = "#e4e4e8"
ACCENT = "#7aa2f7"
ACCENT_HOVER = "#5b84d6"
OK = "#9ece6a"
BAD = "#f7768e"
MUTED = "#565f89"
BORDER = "#3a3d52"

REPO_URL = "https://github.com/callmecla/dep-resolver"


def _styled_button(parent, text, command, bg=PANEL, hover_bg=PANEL_HOVER, fg=FG,
                    font=("Helvetica", 10), bold=False, padx=10):
    """A flat button with real mouse-over feedback (plain tk.Button doesn't
    show hover state with relief='flat' + custom colors by default)."""
    btn = tk.Button(
        parent, text=text, command=command, bg=bg, fg=fg,
        activebackground=hover_bg, activeforeground=fg, relief="flat",
        font=(font[0], font[1], "bold") if bold else font,
        padx=padx, pady=4, cursor="hand2", borderwidth=0,
    )
    btn.bind("<Enter>", lambda e: btn.configure(bg=hover_bg))
    btn.bind("<Leave>", lambda e: btn.configure(bg=bg))
    return btn


class ResolverApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("dep-resolver — dependency version resolver")
        self.geometry("1150x720")
        self.configure(bg=BG)
        self._last_loaded_text = ""

        self._build_toolbar()
        self._build_body()
        self._build_footer()

        self._load_json_text(self._default_scenario())

    # ---------- UI construction ----------

    def _build_toolbar(self):
        bar = tk.Frame(self, bg=PANEL, height=52)
        bar.pack(side="top", fill="x")

        tk.Label(bar, text="dep-resolver", bg=PANEL, fg=ACCENT,
                 font=("Helvetica", 13, "bold")).pack(side="left", padx=(14, 10), pady=10)

        tk.Frame(bar, bg=BORDER, width=1).pack(side="left", fill="y", pady=10, padx=(0, 8))

        for label, fname in [
            ("Simple OK", "simple_ok.json"),
            ("Simple Conflict", "simple_conflict.json"),
            ("Deep Chain", "deep_chain_backtrack.json"),
        ]:
            _styled_button(bar, label, lambda f=fname: self._load_example(f)
                            ).pack(side="left", padx=3, pady=9)

        tk.Frame(bar, bg=BORDER, width=1).pack(side="left", fill="y", pady=10, padx=8)

        _styled_button(bar, "Open File…", self._open_file).pack(side="left", padx=3, pady=9)
        _styled_button(bar, "🌐 From PyPI…", self._open_pypi_dialog, fg=OK
                        ).pack(side="left", padx=3, pady=9)
        _styled_button(bar, "↺ Reset", self._on_reset).pack(side="left", padx=3, pady=9)

        _styled_button(bar, "▶ Resolve", self._on_resolve, bg=ACCENT, hover_bg=ACCENT_HOVER,
                        fg="#1e1e2e", bold=True, padx=14).pack(side="right", padx=14, pady=9)

    def _build_footer(self):
        tk.Frame(self, bg=BORDER, height=1).pack(side="bottom", fill="x")
        footer = tk.Frame(self, bg=PANEL)
        footer.pack(side="bottom", fill="x")

        self.status_var = tk.StringVar(value="")
        tk.Label(footer, textvariable=self.status_var, bg=PANEL, fg=MUTED,
                 anchor="w", font=("Helvetica", 9), padx=12, pady=6).pack(side="left")

        tk.Label(footer, text=f"dep-resolver · {REPO_URL.replace('https://', '')}",
                 bg=PANEL, fg=MUTED, anchor="e", font=("Helvetica", 9), padx=12, pady=6
                 ).pack(side="right")

    def _build_body(self):
        tk.Frame(self, bg=BORDER, height=1).pack(side="top", fill="x")
        body = tk.PanedWindow(self, orient="horizontal", bg=BG, sashwidth=6,
                               sashrelief="flat")
        body.pack(fill="both", expand=True)

        # Left: JSON input
        left = tk.Frame(body, bg=BG)
        tk.Label(left, text="SCENARIO (JSON)", bg=BG, fg=MUTED,
                 font=("Helvetica", 9, "bold")).pack(anchor="w", padx=8, pady=(8, 2))
        self.json_text = tk.Text(left, bg=PANEL, fg=FG, insertbackground=FG,
                                  relief="flat", font=("Menlo", 11), wrap="none",
                                  padx=10, pady=10)
        self.json_text.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        body.add(left, minsize=380)

        # Right: notebook with Result + Graph tabs
        right = tk.Frame(body, bg=BG)
        style = ttk.Style()
        style.theme_use("default")
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", background=PANEL, foreground=FG, padding=(12, 6))
        style.map("TNotebook.Tab", background=[("selected", ACCENT)],
                   foreground=[("selected", "#1e1e2e")])

        notebook = ttk.Notebook(right)
        notebook.pack(fill="both", expand=True, padx=8, pady=8)

        result_frame = tk.Frame(notebook, bg=PANEL)
        self.result_text = tk.Text(result_frame, bg=PANEL, fg=FG, relief="flat",
                                    font=("Menlo", 11), padx=10, pady=10, state="disabled")
        self.result_text.pack(fill="both", expand=True)
        notebook.add(result_frame, text="Result")

        graph_frame = tk.Frame(notebook, bg=PANEL)
        self.graph_canvas = tk.Canvas(graph_frame, bg=PANEL, highlightthickness=0)
        h_scroll = tk.Scrollbar(graph_frame, orient="horizontal", command=self.graph_canvas.xview)
        v_scroll = tk.Scrollbar(graph_frame, orient="vertical", command=self.graph_canvas.yview)
        self.graph_canvas.configure(xscrollcommand=h_scroll.set, yscrollcommand=v_scroll.set)

        self.graph_canvas.grid(row=0, column=0, sticky="nsew")
        v_scroll.grid(row=0, column=1, sticky="ns")
        h_scroll.grid(row=1, column=0, sticky="ew")
        graph_frame.grid_rowconfigure(0, weight=1)
        graph_frame.grid_columnconfigure(0, weight=1)

        # Mouse wheel scrolling (vertical by default, horizontal with Shift)
        self.graph_canvas.bind("<MouseWheel>", lambda e: self.graph_canvas.yview_scroll(int(-e.delta / 120), "units"))
        self.graph_canvas.bind("<Shift-MouseWheel>", lambda e: self.graph_canvas.xview_scroll(int(-e.delta / 120), "units"))
        notebook.add(graph_frame, text="Dependency Graph")

        body.add(right, minsize=500)

    # ---------- data loading ----------

    def _default_scenario(self):
        with open(os.path.join(EXAMPLES_DIR, "simple_ok.json")) as f:
            return f.read()

    def _load_json_text(self, text, remember=True):
        self.json_text.delete("1.0", "end")
        self.json_text.insert("1.0", text)
        if remember:
            self._last_loaded_text = text

    def _on_reset(self):
        """Restore whatever was last officially loaded (a bundled example,
        an opened file, or the PyPI-derived scenario) — undoes accidental
        edits or an emptied textbox without needing to re-find the right
        example button."""
        self._load_json_text(self._last_loaded_text, remember=False)
        self.status_var.set("Scenario restored.")

    def _load_example(self, filename):
        path = os.path.join(EXAMPLES_DIR, filename)
        with open(path) as f:
            self._load_json_text(f.read())
        self._clear_outputs()

    def _open_file(self):
        path = filedialog.askopenfilename(filetypes=[("JSON files", "*.json")])
        if not path:
            return
        with open(path) as f:
            self._load_json_text(f.read())
        self._clear_outputs()

    def _clear_outputs(self):
        self.result_text.configure(state="normal")
        self.result_text.delete("1.0", "end")
        self.result_text.configure(state="disabled")
        self.graph_canvas.delete("all")

    # ---------- PyPI mode ----------

    def _open_pypi_dialog(self):
        dialog = tk.Toplevel(self, bg=PANEL)
        dialog.title("Resolve from PyPI")
        dialog.geometry("480x360")
        dialog.configure(bg=PANEL)
        dialog.transient(self)
        dialog.grab_set()

        tk.Label(dialog, text="One package per line, e.g.:\n  requests\n  urllib3<2.0.0",
                 bg=PANEL, fg=MUTED, justify="left", font=("Helvetica", 10)
                 ).pack(anchor="w", padx=14, pady=(14, 6))

        text = tk.Text(dialog, bg=BG, fg=FG, insertbackground=FG, relief="flat",
                        font=("Menlo", 11), height=8, padx=8, pady=8)
        text.insert("1.0", "requests\n")
        text.pack(fill="both", expand=True, padx=14)

        opts = tk.Frame(dialog, bg=PANEL)
        opts.pack(fill="x", padx=14, pady=10)

        def labeled_spinbox(parent, label, default, lo=1, hi=100):
            f = tk.Frame(parent, bg=PANEL)
            tk.Label(f, text=label, bg=PANEL, fg=MUTED, font=("Helvetica", 9)).pack(side="left")
            var = tk.IntVar(value=default)
            tk.Spinbox(f, from_=lo, to=hi, textvariable=var, width=5,
                       bg=BG, fg=FG, relief="flat").pack(side="left", padx=6)
            f.pack(side="left", padx=(0, 16))
            return var

        max_versions_var = labeled_spinbox(opts, "Versions/pkg", 6, 1, 20)
        max_depth_var = labeled_spinbox(opts, "Max depth", 4, 1, 10)
        max_packages_var = labeled_spinbox(opts, "Max packages", 40, 1, 200)

        btn_frame = tk.Frame(dialog, bg=PANEL)
        btn_frame.pack(fill="x", padx=14, pady=(0, 14))

        def on_fetch():
            raw_lines = [ln.strip() for ln in text.get("1.0", "end").splitlines() if ln.strip()]
            if not raw_lines:
                messagebox.showerror("No packages", "Enter at least one package name.")
                return
            root_packages = {}
            for line in raw_lines:
                matched = False
                for op in ("==", ">=", "<=", "!=", ">", "<", "~="):
                    if op in line:
                        name, constraint = line.split(op, 1)
                        root_packages[name.strip()] = f"{op}{constraint.strip()}"
                        matched = True
                        break
                if not matched:
                    root_packages[line] = "*"

            dialog.destroy()
            self._resolve_from_pypi(
                root_packages,
                max_versions_var.get(),
                max_depth_var.get(),
                max_packages_var.get(),
            )

        _styled_button(btn_frame, "Cancel", dialog.destroy, bg=PANEL, hover_bg=PANEL_HOVER
                        ).pack(side="right", padx=(6, 0))
        _styled_button(btn_frame, "Fetch & Resolve", on_fetch, bg=ACCENT, hover_bg=ACCENT_HOVER,
                        fg="#1e1e2e", bold=True).pack(side="right")

    def _resolve_from_pypi(self, root_packages, max_versions, max_depth, max_packages):
        self._clear_outputs()
        self.status_var.set("Starting PyPI fetch…")

        def progress(msg):
            self.after(0, lambda: self.status_var.set(msg))

        def worker():
            try:
                universe = build_universe_from_pypi(
                    root_packages,
                    max_versions_per_package=max_versions,
                    max_packages=max_packages,
                    max_depth=max_depth,
                    progress_callback=progress,
                )
                result = resolve(universe)
                self.after(0, lambda: self._on_pypi_done(universe, result, None))
            except PyPIError as e:
                self.after(0, lambda: self._on_pypi_done(None, None, str(e)))

        threading.Thread(target=worker, daemon=True).start()

    def _on_pypi_done(self, universe, result, error):
        if error:
            self.status_var.set(f"PyPI fetch failed: {error}")
            messagebox.showerror("PyPI fetch failed", error)
            return

        self.status_var.set(f"Done — {len(universe.packages)} package(s) fetched from PyPI.")
        # Show the resolved scenario as JSON-ish text for reference (read-only view)
        self._load_json_text(json.dumps(
            {name: str(req.constraint) for req in universe.root for name in [req.package]},
            indent=2,
        ))
        self._render_result(result)
        self.graph_canvas.delete("all")
        if result.success:
            self._render_graph(universe, result)
        else:
            self._render_no_graph(result)

    # ---------- resolve action ----------

    def _on_resolve(self):
        raw = self.json_text.get("1.0", "end")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            messagebox.showerror("Invalid JSON", str(e))
            return

        try:
            universe = Universe.from_dict(data)
        except Exception as e:
            messagebox.showerror("Invalid scenario", str(e))
            return

        result = resolve(universe)
        self._render_result(result)
        self.graph_canvas.delete("all")
        if result.success:
            self._render_graph(universe, result)
        else:
            self._render_no_graph(result)

    # ---------- result panel ----------

    def _render_result(self, result):
        self.result_text.configure(state="normal")
        self.result_text.delete("1.0", "end")

        if result.success:
            self.result_text.insert("end", "✓ Resolution succeeded\n\n", ("ok",))
            for name, pv in sorted(result.assignment.items()):
                self.result_text.insert("end", f"  {name}  →  {pv.version}\n")
        else:
            self.result_text.insert("end", "✗ Resolution FAILED\n\n", ("bad",))
            self.result_text.insert("end", f"  Package:  {result.conflict.package}\n")
            self.result_text.insert("end", f"  Reason:   {result.conflict.reason}\n")

        self.result_text.insert("end", f"\n(search steps: {result.steps})", ("muted",))
        self.result_text.tag_configure("ok", foreground=OK, font=("Helvetica", 12, "bold"))
        self.result_text.tag_configure("bad", foreground=BAD, font=("Helvetica", 12, "bold"))
        self.result_text.tag_configure("muted", foreground=MUTED)
        self.result_text.configure(state="disabled")

    def _render_no_graph(self, result):
        self.graph_canvas.create_text(
            20, 20, anchor="nw", fill=MUTED, font=("Helvetica", 11),
            text="No graph to show — resolution failed before a full\n"
                 "assignment was reached. See the Result tab for the conflict.",
        )

    # ---------- graph panel ----------

    def _compute_levels(self, universe, result):
        """Assign each resolved package a column (level) based on distance
        from the root requirements, via BFS over the chosen versions."""
        levels = {}
        queue = deque()
        for req in universe.root:
            if req.package in result.assignment and req.package not in levels:
                levels[req.package] = 0
                queue.append(req.package)

        seen_edges = 0
        while queue and seen_edges < 5000:
            name = queue.popleft()
            pv = result.assignment.get(name)
            if pv is None:
                continue
            for dep in pv.dependencies:
                seen_edges += 1
                new_level = levels[name] + 1
                if dep.package not in levels or new_level > levels[dep.package]:
                    levels[dep.package] = new_level
                    queue.append(dep.package)
        return levels

    def _render_graph(self, universe, result):
        levels = self._compute_levels(universe, result)
        edges = []
        for name, pv in result.assignment.items():
            for dep in pv.dependencies:
                edges.append((name, dep.package))

        by_level = {}
        for name, lvl in levels.items():
            by_level.setdefault(lvl, []).append(name)
        for names in by_level.values():
            names.sort()

        col_w, row_h = 190, 70
        node_w, node_h = 150, 44
        positions = {}
        for lvl, names in sorted(by_level.items()):
            for i, name in enumerate(names):
                x = 30 + lvl * col_w
                y = 30 + i * row_h
                positions[name] = (x, y)

        # edges first, so nodes draw on top
        for src, dst in edges:
            if src not in positions or dst not in positions:
                continue
            x1, y1 = positions[src]
            x2, y2 = positions[dst]
            self.graph_canvas.create_line(
                x1 + node_w, y1 + node_h / 2, x2, y2 + node_h / 2,
                fill=MUTED, width=2, arrow="last", smooth=True,
            )

        for name, (x, y) in positions.items():
            pv = result.assignment[name]
            self.graph_canvas.create_rectangle(
                x, y, x + node_w, y + node_h,
                fill="#33364a", outline=ACCENT, width=2,
            )
            self.graph_canvas.create_text(
                x + node_w / 2, y + node_h / 2,
                text=f"{name}\n{pv.version}", fill=FG, font=("Helvetica", 10, "bold"),
                justify="center",
            )

        bbox = self.graph_canvas.bbox("all")
        if bbox:
            self.graph_canvas.configure(scrollregion=bbox)


def main():
    app = ResolverApp()
    app.mainloop()


if __name__ == "__main__":
    main()
