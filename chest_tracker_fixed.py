"""
Chest Tracker for Fortnite - Windows desktop app.

Counts the chests you (and, optionally, your teammates) loot in Fortnite by reading the replays (.replay)
the game saves after each match. Every chest in a replay records which player opened it, so chests opened
by enemies or other teams are never counted.
It never touches the game or its memory: it only reads files Fortnite already writes to your PC.
"""

import ctypes
import datetime as dt
import io
import json
import math
import os
import queue
import random
import re
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
import zipfile
from tkinter import ttk, messagebox, colorchooser

APP_VERSION = "1.5"

# ---------------------------------------------------------------- paths & constants

LOCAL = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
ROAMING = os.environ.get("APPDATA") or os.path.expanduser("~")
DATA_DIR = os.path.join(ROAMING, "ChestTracker")
DATA_FILE = os.path.join(DATA_DIR, "data.json")
TOOLS = os.path.join(LOCAL, "ChestTracker")
SRC_DIR = os.path.join(TOOLS, "reader_src")
LOG_FILE = os.path.join(TOOLS, "setup.log")
DEMOS = os.path.join(LOCAL, "FortniteGame", "Saved", "Demos")


DOTNET_INSTALL = "https://dot.net/v1/dotnet-install.ps1"
# Source of the replay reader library (was referenced but not defined in the file you sent).
REPO_ZIP = "https://github.com/Shiqan/FortniteReplayDecompressor/archive/refs/heads/master.zip"

READER_VERSION = 9
BIN_DIR = os.path.join(TOOLS, f"reader_v{READER_VERSION}")
READER_DLL = os.path.join(BIN_DIR, "ChestReplayReader.dll")

DEFAULT_TYPES = [
    "/Game/Building/ActorBlueprints/Containers/Tiered_Chest_Athena.Tiered_Chest_Athena_C",
    "/Game/Building/ActorBlueprints/Containers/Tiered_Chest_Athena_FactionChest_NoLocks.Tiered_Chest_Athena_FactionChest_NoLocks_C",
]

NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
QUIET_SECONDS = 90
READ_TIMEOUT = 600

SKIN_DIR = os.path.join(TOOLS, "skins")
SKIN_API = "https://fortnite-api.com/v2/cosmetics/br/"

# update checker
REPO_URL = "https://github.com/Hmr-Abood/tokenqol"
RAW_SCRIPT = "https://raw.githubusercontent.com/Hmr-Abood/tokenqol/main/chest_tracker_fixed.py"
RELEASE_API = "https://api.github.com/repos/Hmr-Abood/tokenqol/releases/latest"

# ---------------------------------------------------------------- theme

BG = "#0e1014"
SURFACE = "#161a21"
SURFACE2 = "#1d222b"
BORDER = "#2a303b"
TEXT = "#e9ecf3"
MUTED = "#8a93a6"
ACCENT = "#36d6c8"
ACCENT_DIM = "#1d7f78"
VIOLET = "#9d8cff"
GOOD = "#4ade80"
WARN = "#fbbf24"
BAD = "#f87171"
HOVER = "#6ff0e4"
ON_ACCENT = "#06201e"
LOGO = "\u25C6"

FONT_FAMILY = "Segoe UI"
FONT_SCALE = 1.0

THEMES = {
    "classic": dict(BG="#0e1014", SURFACE="#161a21", SURFACE2="#1d222b", BORDER="#2a303b", TEXT="#e9ecf3",
                    MUTED="#8a93a6", ACCENT="#36d6c8", ACCENT_DIM="#1d7f78", VIOLET="#9d8cff", GOOD="#4ade80",
                    WARN="#fbbf24", BAD="#f87171", HOVER="#6ff0e4", ON_ACCENT="#06201e", LOGO="\u25C6"),
    "pirate": dict(BG="#0a1420", SURFACE="#112131", SURFACE2="#1a2e43", BORDER="#2d4560", TEXT="#f4ead5",
                   MUTED="#9fb0bd", ACCENT="#e9b440", ACCENT_DIM="#8f6b1c", VIOLET="#e4604f", GOOD="#5fd39a",
                   WARN="#f2a33a", BAD="#f2705f", HOVER="#f7cd6e", ON_ACCENT="#2a1b04", LOGO="\u2620"),
    "ocean": dict(BG="#08121c", SURFACE="#0f1e2d", SURFACE2="#162b3f", BORDER="#25405a", TEXT="#e6f1fa",
                  MUTED="#8aa3b8", ACCENT="#3fa9f5", ACCENT_DIM="#1f5f94", VIOLET="#7aa2ff", GOOD="#4ade80",
                  WARN="#fbbf24", BAD="#f87171", HOVER="#7cc4fa", ON_ACCENT="#04121f", LOGO="\u25C6"),
    "crimson": dict(BG="#120a0d", SURFACE="#1c1116", SURFACE2="#27181f", BORDER="#43262f", TEXT="#f3e8ea",
                    MUTED="#a8909a", ACCENT="#ff4d6d", ACCENT_DIM="#8f2a3d", VIOLET="#ff9e7a", GOOD="#4ade80",
                    WARN="#fbbf24", BAD="#ff8a8a", HOVER="#ff8099", ON_ACCENT="#2a0710", LOGO="\u25C6"),
    "forest": dict(BG="#0b130e", SURFACE="#121d16", SURFACE2="#1a2a20", BORDER="#2b4533", TEXT="#e8f2ea",
                   MUTED="#8fa898", ACCENT="#6fdc8c", ACCENT_DIM="#357a4a", VIOLET="#c3e88d", GOOD="#4ade80",
                   WARN="#fbbf24", BAD="#f87171", HOVER="#9bf0b1", ON_ACCENT="#05200d", LOGO="\u25C6"),
    "light": dict(BG="#f3f5f9", SURFACE="#ffffff", SURFACE2="#e8ecf3", BORDER="#cfd6e2", TEXT="#1b2230",
                  MUTED="#667087", ACCENT="#0e9f94", ACCENT_DIM="#7fd0c9", VIOLET="#6b57e6", GOOD="#16a34a",
                  WARN="#d98a04", BAD="#dc2626", HOVER="#12bfb2", ON_ACCENT="#ffffff", LOGO="\u25C6"),
}

# colors the user can override one by one (key, label)
COLOR_LABELS = (
    ("BG", "Background"), ("SURFACE", "Cards"), ("SURFACE2", "Buttons and inputs"), ("BORDER", "Borders"),
    ("TEXT", "Main text"), ("MUTED", "Secondary text"), ("ACCENT", "Accent"),
    ("VIOLET", "Highlight (token chance)"), ("GOOD", "Success"), ("WARN", "Warning"), ("BAD", "Error"),
)
COLOR_KEYS = tuple(k for k, _ in COLOR_LABELS)

FONT_CHOICES = ("Segoe UI", "Arial", "Verdana", "Trebuchet MS", "Tahoma", "Calibri", "Georgia", "Consolas",
                "Comic Sans MS")
LOGO_CHOICES = ("Default", "\u25C6", "\u2620", "\u2605", "\u2665", "\u2693", "\u26A1", "\u2618", "\u25CF")


def valid_hex(v):
    return isinstance(v, str) and len(v) == 7 and v[0] == "#" and all(c in "0123456789abcdefABCDEF" for c in v[1:])


def _rgb(h):
    return int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)


def mix(a, b, t):
    """Blend color a toward color b by fraction t (0..1)."""
    ra, ga, ba = _rgb(a)
    rb, gb, bb = _rgb(b)
    return "#%02x%02x%02x" % (round(ra + (rb - ra) * t), round(ga + (gb - ga) * t), round(ba + (bb - ba) * t))


def luminance(h):
    r, g, b = _rgb(h)
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255


def build_theme(name, custom=None):
    t = dict(THEMES.get(name) or THEMES["classic"])
    custom = custom or {}
    for k in COLOR_KEYS:
        if valid_hex(custom.get(k)):
            t[k] = custom[k].lower()
    # derived colors follow the accent / background when the user changed those
    if valid_hex(custom.get("ACCENT")) or valid_hex(custom.get("BG")):
        t["ACCENT_DIM"] = mix(t["ACCENT"], t["BG"], 0.5)
    if valid_hex(custom.get("ACCENT")):
        t["HOVER"] = mix(t["ACCENT"], "#ffffff", 0.35)
        t["ON_ACCENT"] = "#06201e" if luminance(t["ACCENT"]) > 0.5 else "#ffffff"
    return t


def apply_theme(name, custom=None):
    globals().update(build_theme(name, custom))


def apply_fonts(family, pct):
    global FONT_FAMILY, FONT_SCALE
    FONT_FAMILY = family or "Segoe UI"
    try:
        FONT_SCALE = max(0.8, min(1.5, int(pct) / 100))
    except (TypeError, ValueError):
        FONT_SCALE = 1.0


SCALE = 1.0
TOKEN_ODDS = 137_500


def token_chance(chests):
    return 1 - (1 - 1 / TOKEN_ODDS) ** chests


MILESTONES = (0.25, 0.50, 0.75, 0.90, 0.95, 0.99)


def chests_for_chance(p):
    return math.ceil(math.log(1 - p) / math.log(1 - 1 / TOKEN_ODDS))


def fmt_pct(x):
    if 0 < x < 1e-4:
        return "<0.01%"
    return f"{x * 100:.2f}%"


def px(n):
    return int(round(n * SCALE))


def font(size, weight="normal"):
    return (FONT_FAMILY, max(6, int(round(size * FONT_SCALE))), weight)


# ---------------------------------------------------------------- token roll simulator

MAX_ROLLS = 1_000_000
MAX_LINES = 5000

SPEEDS = {
    "Slow (1 per 0.15 s)": (1, 150),
    "Normal": (5, 40),
    "Fast": (50, 20),
    "Max": (2000, 1),
}


class TokenSimulator(tk.Toplevel):
    def __init__(self, parent, odds, default_rolls, theme, scale=1.0):
        super().__init__(parent)
        self.odds = odds
        self.t = theme
        self.scale = scale
        self.rng = random.SystemRandom()
        self.running = False
        self.target = 0
        self.done = 0
        self.hits = 0
        self.job = None

        self.title("Token roll simulator")
        self.configure(bg=theme["BG"])
        self.geometry(f"{self.px(640)}x{self.px(680)}")
        self.minsize(self.px(520), self.px(520))
        self._build(default_rolls)
        self.protocol("WM_DELETE_WINDOW", self._close)

    def px(self, n):
        return int(round(n * self.scale))

    def f(self, size, weight="normal"):
        return font(size, weight)

    def _btn(self, parent, text, command, primary=False):
        t = self.t
        bg, fg = (t["ACCENT"], t.get("ON_ACCENT", "#06201e")) if primary else (t["SURFACE2"], t["TEXT"])
        hover = t.get("HOVER", "#6ff0e4") if primary else t["BORDER"]
        b = tk.Label(parent, text=text, bg=bg, fg=fg, font=self.f(10, "bold" if primary else "normal"),
                     padx=self.px(14), pady=self.px(7), cursor="hand2")
        b.bind("<Button-1>", lambda e: command())
        b.bind("<Enter>", lambda e: b.config(bg=hover))
        b.bind("<Leave>", lambda e: b.config(bg=bg))
        return b

    def _build(self, default_rolls):
        t = self.t
        top = tk.Frame(self, bg=t["BG"])
        top.pack(fill="x", padx=self.px(18), pady=(self.px(16), self.px(8)))

        tk.Label(top, text=f"Each roll is a 1 in {self.odds:,} chance", bg=t["BG"], fg=t["TEXT"],
                 font=self.f(12, "bold")).pack(anchor="w")

        row = tk.Frame(top, bg=t["BG"])
        row.pack(fill="x", pady=(self.px(10), 0))
        tk.Label(row, text="Rolls", bg=t["BG"], fg=t["MUTED"], font=self.f(10)).pack(side="left")
        self.v_rolls = tk.StringVar(value=str(max(1, default_rolls)))
        ttk.Spinbox(row, from_=1, to=MAX_ROLLS, width=9, textvariable=self.v_rolls).pack(side="left", padx=self.px(8))
        tk.Label(row, text="Speed", bg=t["BG"], fg=t["MUTED"], font=self.f(10)).pack(side="left", padx=(self.px(8), 0))
        self.v_speed = tk.StringVar(value="Fast")
        ttk.Combobox(row, values=list(SPEEDS), textvariable=self.v_speed, state="readonly",
                     width=18).pack(side="left", padx=self.px(8))

        row2 = tk.Frame(top, bg=t["BG"])
        row2.pack(fill="x", pady=(self.px(10), 0))
        self.btn_start = self._btn(row2, "Roll", self.start, primary=True)
        self.btn_start.pack(side="left")
        self._btn(row2, "Stop", self.stop).pack(side="left", padx=self.px(8))
        self._btn(row2, "Clear", self.clear).pack(side="left")

        stats = tk.Frame(self, bg=t["SURFACE"], highlightthickness=1, highlightbackground=t["BORDER"])
        stats.pack(fill="x", padx=self.px(18), pady=(self.px(6), self.px(8)))
        self.lbl_stats = tk.Label(stats, text="", bg=t["SURFACE"], fg=t["TEXT"], font=self.f(10),
                                  justify="left", anchor="w")
        self.lbl_stats.pack(fill="x", padx=self.px(14), pady=self.px(10))

        hits_box = tk.Frame(self, bg=t["BG"])
        hits_box.pack(fill="x", padx=self.px(18))
        tk.Label(hits_box, text="TOKENS WON", bg=t["BG"], fg=t["MUTED"], font=self.f(8, "bold")).pack(anchor="w")
        self.hits_list = tk.Text(hits_box, height=3, bg=t["SURFACE"], fg=t["GOOD"], bd=0, highlightthickness=1,
                                 highlightbackground=t["BORDER"], font=self.f(10), state="disabled")
        self.hits_list.pack(fill="x", pady=(self.px(2), self.px(8)))

        log_box = tk.Frame(self, bg=t["BG"])
        log_box.pack(fill="both", expand=True, padx=self.px(18), pady=(0, self.px(16)))
        tk.Label(log_box, text="EVERY ROLL", bg=t["BG"], fg=t["MUTED"], font=self.f(8, "bold")).pack(anchor="w")
        inner = tk.Frame(log_box, bg=t["SURFACE"], highlightthickness=1, highlightbackground=t["BORDER"])
        inner.pack(fill="both", expand=True, pady=(self.px(2), 0))
        sb = ttk.Scrollbar(inner, orient="vertical")
        self.log = tk.Text(inner, bg=t["SURFACE"], fg=t["MUTED"], bd=0, highlightthickness=0,
                           font=("Consolas", 10), state="disabled", yscrollcommand=sb.set, wrap="none")
        sb.config(command=self.log.yview)
        sb.pack(side="right", fill="y")
        self.log.pack(side="left", fill="both", expand=True, padx=self.px(6), pady=self.px(4))
        self.log.tag_configure("hit", foreground=t["GOOD"], font=("Consolas", 10, "bold"))
        self.log.tag_configure("miss", foreground=t["MUTED"])
        self._update_stats()

    def start(self):
        if self.running:
            return
        try:
            n = int(self.v_rolls.get().replace(",", ""))
        except ValueError:
            n = 1
        n = max(1, min(MAX_ROLLS, n))
        self.v_rolls.set(str(n))
        self.target = self.done + n
        self.running = True
        self._tick()

    def stop(self):
        self.running = False
        if self.job:
            self.after_cancel(self.job)
            self.job = None

    def clear(self):
        self.stop()
        self.done = self.hits = 0
        for w in (self.log, self.hits_list):
            w.config(state="normal")
            w.delete("1.0", "end")
            w.config(state="disabled")
        self._update_stats()

    def _close(self):
        self.stop()
        self.destroy()

    def _tick(self):
        if not self.running:
            return
        per_tick, delay = SPEEDS.get(self.v_speed.get(), (50, 20))
        count = min(per_tick, self.target - self.done)
        lines = []
        new_hits = []
        for _ in range(count):
            self.done += 1
            number = self.rng.randint(1, self.odds)
            if number == 1:
                self.hits += 1
                text = f"#{self.done:,}  rolled {number:,} of {self.odds:,}  ->  TOKEN!"
                lines.append((text, "hit"))
                new_hits.append(f"Roll #{self.done:,}  (token {self.hits})")
            else:
                lines.append((f"#{self.done:,}  rolled {number:,} of {self.odds:,}  ->  no token", "miss"))
        self._append(lines, new_hits)
        self._update_stats()
        if self.done >= self.target:
            self.running = False
            self.job = None
            return
        self.job = self.after(delay, self._tick)

    def _append(self, lines, new_hits):
        self.log.config(state="normal")
        for text, tag in lines:
            self.log.insert("end", text + "\n", tag)
        extra = int(self.log.index("end-1c").split(".")[0]) - 1 - MAX_LINES
        if extra > 0:
            self.log.delete("1.0", f"{extra + 1}.0")
        self.log.see("end")
        self.log.config(state="disabled")
        if new_hits:
            self.hits_list.config(state="normal")
            for h in new_hits:
                self.hits_list.insert("end", h + "\n")
            self.hits_list.see("end")
            self.hits_list.config(state="disabled")

    def _update_stats(self):
        expected = self.done / self.odds
        chance = 1 - (1 - 1 / self.odds) ** self.done
        pct = "<0.01%" if 0 < chance < 1e-4 else f"{chance * 100:.2f}%"
        self.lbl_stats.config(
            text=f"Rolls: {self.done:,}     Tokens won: {self.hits:,}     Expected by luck: {expected:.3f}\n"
                 f"Chance of at least one token in {self.done:,} rolls: {pct}"
                 + (f"\n(Log shows the last {MAX_LINES:,} rolls; every win stays in the list above.)"
                    if self.done > MAX_LINES else ""))


# ---------------------------------------------------------------- Draggable Overlay (In-Game / Stream Overlay)

class StatsOverlay(tk.Toplevel):
    def __init__(self, parent, store):
        super().__init__(parent)
        self.store = store
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.set_opacity(store.setting("overlay_opacity"))
        self.configure(bg=BORDER)

        self._x = 0
        self._y = 0

        container = tk.Frame(self, bg=SURFACE)
        container.pack(fill="both", expand=True, padx=1, pady=1)

        # Header / Drag handle bar
        header = tk.Frame(container, bg=SURFACE2, cursor="fleur")
        header.pack(fill="x", padx=4, pady=4)
        tk.Label(header, text=f"{LOGO} CHEST TRACKER OVERLAY", bg=SURFACE2, fg=ACCENT,
                 font=font(8, "bold")).pack(side="left", padx=6, pady=4)

        # Lock / Unlock Click-Through Toggle Button
        self.is_interactive = True
        self.header = header
        self.lock_btn = tk.Label(header, text="\U0001F513", bg=SURFACE2, fg=MUTED, font=font(9, "bold"), cursor="hand2")
        self.lock_btn.pack(side="right", padx=(2, 6))
        self.lock_btn.bind("<Button-1>", lambda e: self.toggle_click_through())
        self.lock_btn.bind("<Enter>", lambda e: self.lock_btn.config(fg=TEXT))
        self.lock_btn.bind("<Leave>", lambda e: self.lock_btn.config(fg=MUTED))

        close_btn = tk.Label(header, text="\u00d7", bg=SURFACE2, fg=MUTED, font=font(10, "bold"), cursor="hand2")
        close_btn.pack(side="right", padx=6)
        close_btn.bind("<Button-1>", lambda e: self.destroy())
        close_btn.bind("<Enter>", lambda e: close_btn.config(fg=BAD))
        close_btn.bind("<Leave>", lambda e: close_btn.config(fg=MUTED))

        for w in (header, header.winfo_children()[0]):
            w.bind("<Button-1>", self._start_move)
            w.bind("<B1-Motion>", self._do_move)

        # Stats Content Body
        body = tk.Frame(container, bg=SURFACE)
        body.pack(fill="both", expand=True, padx=12, pady=(2, 12))

        tk.Label(body, text="TOTAL CHESTS", bg=SURFACE, fg=MUTED, font=font(7, "bold")).pack(anchor="w")
        self.lbl_total = tk.Label(body, text="0", bg=SURFACE, fg=ACCENT, font=font(24, "bold"))
        self.lbl_total.pack(anchor="w")

        self.lbl_today = tk.Label(body, text="Today: 0", bg=SURFACE, fg=TEXT, font=font(9))
        self.lbl_today.pack(anchor="w", pady=(1, 0))

        self.lbl_token = tk.Label(body, text="Token Chance: -", bg=SURFACE, fg=VIOLET, font=font(9, "bold"))
        self.lbl_token.pack(anchor="w", pady=(1, 4))

        tk.Frame(body, bg=BORDER, height=1).pack(fill="x", pady=4)

        tk.Label(body, text="CURRENT SESSION & LAST MATCH", bg=SURFACE, fg=MUTED, font=font(7, "bold")).pack(anchor="w", pady=(2, 0))
        self.lbl_session = tk.Label(body, text="Session Matches: 0", bg=SURFACE, fg=TEXT, font=font(9))
        self.lbl_session.pack(anchor="w", pady=(1, 0))

        self.lbl_last_match = tk.Label(body, text="Last Match: None", bg=SURFACE, fg=MUTED, font=font(8),
                                       wraplength=210, justify="left")
        self.lbl_last_match.pack(anchor="w", pady=(2, 0))

        self.update_idletasks()
        w_w = max(230, int(230 * FONT_SCALE))
        w_h = max(210, int(210 * FONT_SCALE))
        x = self.winfo_screenwidth() - w_w - 40
        y = 40
        self.geometry(f"{w_w}x{w_h}+{x}+{y}")
        self.update_stats()

    def set_opacity(self, pct):
        try:
            v = max(30, min(100, int(pct))) / 100
        except (TypeError, ValueError):
            v = 0.9
        self.attributes("-alpha", v)

    def toggle_click_through(self):
        """Toggle the window between interactive (movable/closable) and click-through (gameplay mode)."""
        try:
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            ex_style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)  # GWL_EXSTYLE

            if self.is_interactive:
                # Enable click-through: Add WS_EX_TRANSPARENT (0x00000020) and keep WS_EX_LAYERED
                ctypes.windll.user32.SetWindowLongW(hwnd, -20, ex_style | 0x00000020 | 0x00080000)
                self.is_interactive = False
                self.lock_btn.config(text="\U0001F512", fg=WARN)
                self.header.config(cursor="")
            else:
                # Disable click-through: Remove WS_EX_TRANSPARENT
                ctypes.windll.user32.SetWindowLongW(hwnd, -20, ex_style & ~0x00000020)
                self.is_interactive = True
                self.lock_btn.config(text="\U0001F513", fg=MUTED)
                self.header.config(cursor="fleur")
        except Exception:
            pass

    def _start_move(self, event):
        if not self.is_interactive:
            return
        self._x = event.x
        self._y = event.y

    def _do_move(self, event):
        if not self.is_interactive:
            return
        x = self.winfo_x() + (event.x - self._x)
        y = self.winfo_y() + (event.y - self._y)
        self.geometry(f"+{x}+{y}")

    def update_stats(self):
        if not self.winfo_exists():
            return
        days = self.store.days()
        total = sum(days.values())
        today = days.get(today_key(), 0)
        matches_count = self.store.matches_counted()

        self.lbl_total.config(text=f"{total:,}")
        self.lbl_today.config(text=f"Today: {today:,}")
        self.lbl_token.config(text=f"Token Chance: {fmt_pct(token_chance(total))}" if total > 0 else "Token Chance: -")
        self.lbl_session.config(text=f"Session Matches Counted: {matches_count}")

        items = sorted(self.store.replay_list().items(), key=lambda kv: kv[1].get("mtime", 0), reverse=True)
        if items:
            _, r = items[0]
            if r.get("ok"):
                n = self.store.replay_count(r)
                time_str = r.get('time', '')
                detail = f"{r.get('opened', 0)}op, {r.get('destroyed', 0)}dst"
                team = self.store.replay_team(r)
                if team:
                    detail += f", +{team} team"
                self.lbl_last_match.config(text=f"Last ({time_str}): {n} chests ({detail})", fg=TEXT)
            else:
                self.lbl_last_match.config(text="Last Match: Error reading", fg=BAD)
        else:
            self.lbl_last_match.config(text="Last Match: None yet", fg=MUTED)

# ---------------------------------------------------------------- C# replay reader

CSPROJ = """<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>Exe</OutputType>
    <AssemblyName>ChestReplayReader</AssemblyName>
    <RootNamespace>ChestReplayReader</RootNamespace>
    <TreatWarningsAsErrors>false</TreatWarningsAsErrors>
    <NoWarn>$(NoWarn);CS8632;CS8618;CS8600;CS8602;CS8604</NoWarn>
    <InvariantGlobalization>true</InvariantGlobalization>
  </PropertyGroup>
  <ItemGroup>
    <ProjectReference Include="..\\FortniteReplayReader\\FortniteReplayReader.csproj" />
  </ItemGroup>
</Project>
"""

PROGRAM_CS = r'''
using System.Reflection;
using System.Reflection.Emit;
using System.Text.Json;
using FortniteReplayReader;
using FortniteReplayReader.Models.NetFieldExports;
using FortniteReplayReader.Models.NetFieldExports.RPC;
using Unreal.Core.Attributes;
using Unreal.Core.Contracts;
using Unreal.Core.Models;
using Unreal.Core.Models.Enums;

namespace ChestReplayReader;

public class Chest : INetFieldExportGroup
{
    [NetFieldExport("bAlreadySearched", RepLayoutCmdType.PropertyBool)]
    public bool? bAlreadySearched { get; set; }

    [NetFieldExport("SearchingPawn", RepLayoutCmdType.PropertyObject)]
    public uint? SearchingPawn { get; set; }

    [NetFieldExport("bDestroyed", RepLayoutCmdType.PropertyBool)]
    public bool? bDestroyed { get; set; }

    [NetFieldExport("ReplicatedLootTier", RepLayoutCmdType.PropertyInt)]
    public int? ReplicatedLootTier { get; set; }

    [NetFieldExport("Health", RepLayoutCmdType.PropertyUInt16)]
    public ushort? Health { get; set; }
}

public class ChestInfo
{
    public uint Actor { get; set; }
    public string Type { get; set; } = "";
    public uint LastSearcher { get; set; }
    public uint SearcherAtOpen { get; set; }
    public uint Owner { get; set; }
    public bool Opened { get; set; }
    public bool Destroyed { get; set; }
    public float TOpened { get; set; } = -1;
    public float TDestroyed { get; set; } = -1;
    public uint LastHitter { get; set; }
    public float TLastHit { get; set; } = -999;
    public float Time { get; set; }
    public string Method { get; set; } = "";
    public double[]? Loc { get; set; }
    public double DistMine { get; set; } = -1;
    public bool Duplicate { get; set; }
    public bool DuplicateTeam { get; set; }
    public bool AsDestroyed { get; set; }
    public bool Far { get; set; }
}

public class ChestReader : ReplayReader
{
    private static bool LooksLikeChest(string g)
    {
        if (string.IsNullOrWhiteSpace(g) || !g.StartsWith("/", StringComparison.Ordinal)) return false;
        if (g.Contains(':') ||
            g.Contains("ClassNetCache", StringComparison.OrdinalIgnoreCase) ||
            g.Contains("Ammo", StringComparison.OrdinalIgnoreCase) ||
            g.Contains("Creative", StringComparison.OrdinalIgnoreCase)) return false;

        return g.Contains("Chest", StringComparison.OrdinalIgnoreCase)
            || g.Contains("Container", StringComparison.OrdinalIgnoreCase)
            || g.Contains("Treasure", StringComparison.OrdinalIgnoreCase)
            || g.Contains("LootCache", StringComparison.OrdinalIgnoreCase);
    }
    public ChestReader() : base(null, ParseMode.Full) { RelaxSettings(); }

    public readonly Dictionary<string, int> ExportCounts = new();
    public readonly Dictionary<string, List<string>> GroupProps = new();
    public readonly List<string> SettingsLog = new();
    public int ChestExports, ChestNoActor;
    private readonly Dictionary<uint, int> _gen = new();

    private void RelaxSettings()
    {
        try
        {
            var flags = BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.DeclaredOnly;
            for (var t = GetType(); t != null; t = t.BaseType)
            {
                foreach (var f in t.GetFields(flags)) FixSettings(f.GetValue(this), t.Name + "." + f.Name);
                foreach (var p in t.GetProperties(flags))
                {
                    if (p.GetIndexParameters().Length != 0 || !p.CanRead) continue;
                    try { FixSettings(p.GetValue(this), t.Name + "." + p.Name); } catch { }
                }
            }
        }
        catch (Exception e) { SettingsLog.Add("error: " + e.Message); }
    }

    private void FixSettings(object? obj, string where)
    {
        if (obj == null || !obj.GetType().Name.Contains("Settings", StringComparison.OrdinalIgnoreCase)) return;
        foreach (var p in obj.GetType().GetProperties(BindingFlags.Instance | BindingFlags.Public))
        {
            if (p.PropertyType != typeof(bool) || !p.CanRead || !p.CanWrite || !p.Name.StartsWith("Ignore")) continue;
            var old = (bool)p.GetValue(obj)!;
            SettingsLog.Add(where + "." + p.Name + "=" + old);
            if (old) { p.SetValue(obj, false); SettingsLog.Add("  set to false"); }
        }
    }

    private uint KeyFor(uint channelIndex) =>
        0x80000000u | (((uint)_gen.GetValueOrDefault(channelIndex) & 0x1FFFF) << 14) | (channelIndex & 0x3FFF);

    private readonly Dictionary<uint, uint> _channelActor = new();
    private readonly Dictionary<uint, (float T, double[] L)> _spawn = new();
    private readonly HashSet<uint> _lootSeen = new();
    public readonly Dictionary<uint, uint> PawnToState = new();
    public readonly Dictionary<uint, int> StateTeam = new();
    public readonly Dictionary<string, List<string>> PlayerStateProps = new();
    public int PlayerStateExports;
    public readonly Dictionary<uint, Dictionary<string, string>> StateInfo = new();
    public List<string> PlayerDataProps = new();
    public List<string> PlayerDump = new();
    public int PlayerDataCount;
    public int? MyTeamIndex;
    public readonly Dictionary<uint, ChestInfo> Chests = new();
    public readonly List<(uint Pawn, float T)> Searches = new();
    public readonly Dictionary<uint, List<(float T, double X, double Y, double Z)>> Positions = new();
    public readonly List<(float T, double[] L)> Loot = new();
    public readonly HashSet<string> Groups = new();
    public readonly HashSet<uint> ExtraMyPawns = new();
    public uint? Recorder;

    protected override void Cleanup()
    {
        foreach (var rawKey in _netGuidCache.NetFieldExportGroupMap.Keys)
        {
            var k = rawKey?.ToString();
            if (!string.IsNullOrWhiteSpace(k)) Groups.Add(k);
        }
        try
        {
            dynamic map = _netGuidCache.NetFieldExportGroupMap;
            foreach (var key in map.Keys)
            {
                var k = key?.ToString();
                if (string.IsNullOrWhiteSpace(k) || !LooksLikeChest(k)) continue;
                var names = new List<string>();
                try
                {
                    dynamic g = map[key];
                    foreach (var e in g.NetFieldExports) if (e != null) names.Add((string)e.Name);
                }
                catch { }
                GroupProps[k] = names;
            }
        }
        catch (Exception e) { SettingsLog.Add("props error: " + e.Message); }
        base.Cleanup();
    }

    protected override void OnChannelOpened(uint channelIndex, NetworkGUID? actor)
    {
        base.OnChannelOpened(channelIndex, actor);
        _gen[channelIndex] = _gen.GetValueOrDefault(channelIndex) + 1;
        if (actor == null) return;
        _channelActor[channelIndex] = actor.Value;
        try
        {
            var loc = Channels[channelIndex]?.Actor?.Location;
            if (loc != null && (loc.X != 0 || loc.Y != 0 || loc.Z != 0))
                _spawn[actor.Value] = (CurrentTimeSeconds, new[] { loc.X, loc.Y, loc.Z });
        }
        catch { }
    }

    private void SavePos(uint pawn, double x, double y, double z)
    {
        if (x == 0 && y == 0 && z == 0) return;
        if (!Positions.TryGetValue(pawn, out var l))
            Positions[pawn] = l = new List<(float, double, double, double)>();
        l.Add((CurrentTimeSeconds, x, y, z));
    }

    public double[]? Pos(uint pawn, float t)
    {
        if (!Positions.TryGetValue(pawn, out var l)) return null;
        for (var i = l.Count - 1; i >= 0; i--)
            if (l[i].T <= t + 0.3f)
                return l[i].T >= t - 5f ? new[] { l[i].X, l[i].Y, l[i].Z } : null;
        return null;
    }

    public static double Dist(double[] a, double[] b)
    {
        var dx = a[0] - b[0]; var dy = a[1] - b[1]; var dz = a[2] - b[2];
        return Math.Sqrt(dx * dx + dy * dy + dz * dz);
    }

    private ChestInfo Info(uint id, Chest c, string? typeName)
    {
        if (!Chests.TryGetValue(id, out var info))
        {
            var path = typeName ?? c.GetType().GetCustomAttribute<NetFieldExportGroupAttribute>()?.Path ?? c.GetType().Name;
            info = new ChestInfo { Type = path.Substring(path.LastIndexOf('.') + 1), Actor = id };
            if (_spawn.TryGetValue(id, out var sp)) info.Loc = sp.L;
            Chests[id] = info;
        }
        return info;
    }

    protected override void OnExportRead(uint channelIndex, INetFieldExportGroup? exportGroup)
    {
        base.OnExportRead(channelIndex, exportGroup);
        if (exportGroup != null)
        {
            var tn = exportGroup.GetType().Name;
            ExportCounts[tn] = ExportCounts.GetValueOrDefault(tn) + 1;
        }
        switch (exportGroup)
        {
            case GameState gs:
                if (gs.RecorderPlayerState != null && gs.RecorderPlayerState.Value > 0)
                    Recorder ??= gs.RecorderPlayerState.Value;
                break;

            case PlayerPawn pawn:
                if (!_channelActor.TryGetValue(channelIndex, out var pawnId)) break;
                if (pawn.PlayerState.HasValue) PawnToState[pawnId] = pawn.PlayerState.Value;
                if (pawn.bStartedInteractSearch == true) Searches.Add((pawnId, CurrentTimeSeconds));
                var mov = pawn.ReplicatedMovement?.Location;
                if (mov != null) SavePos(pawnId, mov.X, mov.Y, mov.Z);
                else if (!Positions.ContainsKey(pawnId) && _spawn.TryGetValue(pawnId, out var sp))
                    SavePos(pawnId, sp.L[0], sp.L[1], sp.L[2]);
                break;

            case FortPickup pickup:
                if (_channelActor.TryGetValue(channelIndex, out var pk) && _lootSeen.Add(pk))
                {
                    if (_spawn.TryGetValue(pk, out var ap)) Loot.Add((ap.T, ap.L));
                    else if (pickup.ReplicatedMovement?.Location is { } lb)
                        Loot.Add((CurrentTimeSeconds, new[] { lb.X, lb.Y, lb.Z }));
                }
                break;

            case BatchedDamageCues hit:
                if (_channelActor.TryGetValue(channelIndex, out var attacker))
                {
                    var target = hit.NonPlayerHitActor is > 0 ? hit.NonPlayerHitActor.Value
                               : hit.HitActor is > 0 ? hit.HitActor.Value : 0u;
                    if (target != 0 && Chests.TryGetValue(target, out var struck))
                    {
                        struck.LastHitter = attacker;
                        struck.TLastHit = CurrentTimeSeconds;
                    }
                }
                break;

            case Chest c:
                HandleChest(channelIndex, c, null);
                break;

            case INetFieldExportGroup ps when IsPlayerStateLike(ps.GetType()):
                ReadTeam(channelIndex, ps);
                break;

            case INetFieldExportGroup other when IsChestLike(other.GetType()):
                var adapted = AdaptChest(other, out var adaptedType);
                if (adapted != null)
                {
                    AdaptedExports++;
                    HandleChest(channelIndex, adapted, adaptedType);
                }
                break;
        }
    }

    public int AdaptedExports;
    public bool UsedPawnFallback, FarFilterSkipped;
    public int FarDiscarded;
    private readonly Dictionary<Type, string?> _chestPathByType = new();

    private static bool IsPlayerStateLike(Type t) =>
        t.Name.Contains("PlayerState", StringComparison.OrdinalIgnoreCase) &&
        !t.Name.Contains("Pawn", StringComparison.OrdinalIgnoreCase);

    // Remember which team each player state belongs to (read by reflection so it works with any reader version).
    private void ReadTeam(uint channelIndex, INetFieldExportGroup g)
    {
        PlayerStateExports++;
        var t = g.GetType();
        if (!PlayerStateProps.ContainsKey(t.Name))
        {
            try { PlayerStateProps[t.Name] = t.GetProperties(BindingFlags.Instance | BindingFlags.Public).Select(p => p.Name).Take(60).ToList(); }
            catch { }
        }
        if (!_channelActor.TryGetValue(channelIndex, out var id)) return;
        foreach (var p in t.GetProperties(BindingFlags.Instance | BindingFlags.Public))
        {
            if (!p.CanRead || p.GetIndexParameters().Length != 0) continue;
            var isTeam = p.Name.Equals("TeamIndex", StringComparison.OrdinalIgnoreCase);
            if (!isTeam && !InfoProps.Contains(p.Name) && !LooksLikeInfo(p.Name)) continue;
            object? v;
            try { v = p.GetValue(g); } catch { continue; }
            if (v == null) continue;
            if (isTeam) { try { StateTeam[id] = Convert.ToInt32(v); } catch { } continue; }
            if (v is string || v.GetType().IsPrimitive)
            {
                var sv = Convert.ToString(v, System.Globalization.CultureInfo.InvariantCulture);
                if (string.IsNullOrWhiteSpace(sv)) continue;
                if (!StateInfo.TryGetValue(id, out var d)) StateInfo[id] = d = new Dictionary<string, string>();
                d[p.Name] = sv;
            }
        }
    }

    // Any property that looks like a name or an id is remembered, so players can still be matched
    // when the library calls the name something unexpected.
    private static bool LooksLikeInfo(string n) =>
        n.Contains("Name", StringComparison.OrdinalIgnoreCase) ||
        n.Contains("UniqueId", StringComparison.OrdinalIgnoreCase) ||
        n.Contains("EpicId", StringComparison.OrdinalIgnoreCase) ||
        n.Contains("PlayerId", StringComparison.OrdinalIgnoreCase);

    private static string? AnyName(object x)
    {
        foreach (var p in x.GetType().GetProperties())
        {
            if (p.PropertyType != typeof(string) || !p.Name.Contains("Name", StringComparison.OrdinalIgnoreCase)) continue;
            try { var s = Str(p.GetValue(x)); if (s != null) return s; } catch { }
        }
        return null;
    }

    private bool StateHasId(uint state, string id) =>
        StateInfo.TryGetValue(state, out var d) &&
        d.Any(kv => kv.Key.Contains("Id", StringComparison.OrdinalIgnoreCase) &&
                    (kv.Value.Equals(id, StringComparison.OrdinalIgnoreCase) ||
                     (id.Length >= 8 && kv.Value.Contains(id, StringComparison.OrdinalIgnoreCase))));

    private static readonly HashSet<string> InfoProps = new(StringComparer.OrdinalIgnoreCase)
    { "PlayerNamePrivate", "PlayerNameCustomOverride", "PlayerName", "PlayerID", "bIsABot", "bIsBot" };

    private static object? GetProp(object? o, string name)
    {
        if (o == null) return null;
        try
        {
            return o.GetType().GetProperty(name, BindingFlags.Instance | BindingFlags.Public | BindingFlags.IgnoreCase)?.GetValue(o);
        }
        catch { return null; }
    }

    private static string? Str(object? o)
    {
        var s = o?.ToString();
        return string.IsNullOrWhiteSpace(s) ? null : s;
    }

    // The character can be a plain string or an item object; turn either into text.
    // Numeric-only values (network GUIDs) are skipped because they cannot name a skin.
    private static string? Flat(object? o)
    {
        if (o == null) return null;
        if (o is string s) return Str(s);
        foreach (var n in new[] { "Name", "AssetName", "Path", "PathName", "Value" })
        {
            var t = Str(GetProp(o, n));
            if (t != null && !t.All(char.IsDigit)) return t;
        }
        var whole = Str(o);
        return whole != null && !whole.All(char.IsDigit) ? whole : null;
    }

    private static string CosmeticId(string? raw)
    {
        if (string.IsNullOrWhiteSpace(raw)) return "";
        var i = raw.IndexOf("CID_", StringComparison.OrdinalIgnoreCase);
        if (i >= 0)
        {
            var j = i;
            while (j < raw.Length && (char.IsLetterOrDigit(raw[j]) || raw[j] == '_')) j++;
            return raw.Substring(i, j - i);
        }
        return raw.Split(new[] { '/', '.', (char)39 }).LastOrDefault(x => x.Length > 0) ?? "";
    }

    private sealed class PlayerRow
    {
        public uint State;
        public bool Me, Bot;
        public string Name = "", Skin = "";
        public int Opened, Destroyed;
    }

    private sealed class PdRow
    {
        public string Name = "", Skin = "", Id = "", Raw = "";
        public int? Team;
        public bool Bot, Used;
    }

    private string StateName(uint state)
    {
        if (!StateInfo.TryGetValue(state, out var d)) return "";
        foreach (var k in new[] { "PlayerNameCustomOverride", "PlayerNamePrivate", "PlayerName" })
            if (d.TryGetValue(k, out var v) && !string.IsNullOrWhiteSpace(v)) return v;
        foreach (var kv in d)
            if (kv.Key.Contains("Name", StringComparison.OrdinalIgnoreCase) && !string.IsNullOrWhiteSpace(kv.Value))
                return kv.Value;
        return "";
    }

    // One entry for me and one for every teammate: name, skin id and how many chests each of us opened/broke.
    public List<object> BuildPlayers(object? replay, List<ChestInfo> mine, List<ChestInfo> team)
    {
        var data = new List<PdRow>();
        try
        {
            if (GetProp(replay, "PlayerData") is System.Collections.IEnumerable en)
                foreach (var x in en)
                {
                    if (x == null) continue;
                    if (PlayerDataProps.Count == 0)
                        PlayerDataProps = x.GetType().GetProperties().Select(p => p.Name).Take(40).ToList();
                    PlayerDataCount++;
                    var raw = Flat(GetProp(GetProp(x, "Cosmetics"), "Character"));
                    var row = new PdRow
                    {
                        Name = Str(GetProp(x, "PlayerNameCustomOverride")) ?? Str(GetProp(x, "PlayerName"))
                               ?? Str(GetProp(x, "PlayerNamePrivate")) ?? AnyName(x) ?? "",
                        Id = Str(GetProp(x, "EpicId")) ?? Str(GetProp(x, "PlayerId"))
                             ?? Str(GetProp(x, "PlatformUniqueId")) ?? "",
                        Raw = raw ?? "",
                        Skin = CosmeticId(raw),
                        Bot = GetProp(x, "IsBot") is bool b && b,
                    };
                    try { var tv = GetProp(x, "TeamIndex"); if (tv != null) row.Team = Convert.ToInt32(tv); } catch { }
                    data.Add(row);
                }
        }
        catch (Exception e) { SettingsLog.Add("player data error: " + e.Message); }

        // Raw dump so a failed match can be diagnosed from "Save diagnostics".
        PlayerDump.Clear();
        foreach (var d in data.Take(40))
            PlayerDump.Add($"data name='{d.Name}' id='{d.Id}' team={d.Team?.ToString() ?? "?"} char='{d.Raw}' skin='{d.Skin}'");
        foreach (var kv in StateInfo.Take(40))
            PlayerDump.Add($"state {kv.Key} team={(StateTeam.TryGetValue(kv.Key, out var tt) ? tt.ToString() : "?")} "
                           + string.Join(", ", kv.Value.Select(p => p.Key + "=" + p.Value)));

        var rows = new Dictionary<uint, PlayerRow>();
        if (MyTeamIndex.HasValue)
            foreach (var kv in StateTeam.Where(kv => kv.Value == MyTeamIndex.Value))
                rows[kv.Key] = new PlayerRow { State = kv.Key, Me = Recorder.HasValue && Recorder.Value == kv.Key };
        if (!rows.Values.Any(r => r.Me))
        {
            var meRow = new PlayerRow { Me = true };
            if (Recorder.HasValue) { meRow.State = Recorder.Value; rows[Recorder.Value] = meRow; }
            else rows[0] = meRow;
        }
        foreach (var r in rows.Values) r.Name = StateName(r.State);

        var me = rows.Values.First(r => r.Me);
        foreach (var c in mine) { if (c.AsDestroyed) me.Destroyed++; else me.Opened++; }
        foreach (var c in team)
            if (PawnToState.TryGetValue(c.Owner, out var st) && rows.TryGetValue(st, out var row2))
            {
                if (c.AsDestroyed) row2.Destroyed++; else row2.Opened++;
            }

        var matched = 0;
        var unmatched = new List<PlayerRow>();
        foreach (var r in rows.Values)
        {
            PdRow? d = null;
            if (r.Name.Length > 0)
                d = data.FirstOrDefault(x => !x.Used && x.Name.Equals(r.Name, StringComparison.OrdinalIgnoreCase));
            if (d == null && r.State != 0)
                d = data.FirstOrDefault(x => !x.Used && x.Id.Length > 0 && StateHasId(r.State, x.Id));
            if (d == null) { unmatched.Add(r); continue; }
            d.Used = true; r.Skin = d.Skin; r.Bot = d.Bot; matched++;
            if (r.Name.Length == 0) r.Name = d.Name;
        }

        // Last resort: exactly one player left without a match and exactly one unused entry on my team.
        if (MyTeamIndex.HasValue && unmatched.Count == 1)
        {
            var left = data.Where(x => !x.Used && x.Team == MyTeamIndex.Value).ToList();
            if (left.Count == 1)
            {
                left[0].Used = true;
                unmatched[0].Skin = left[0].Skin; unmatched[0].Bot = left[0].Bot;
                if (unmatched[0].Name.Length == 0) unmatched[0].Name = left[0].Name;
                matched++; unmatched.Clear();
            }
        }

        var extra = new List<PlayerRow>();
        if (matched > 0 && unmatched.Count == 0 && MyTeamIndex.HasValue)
            foreach (var d in data.Where(x => !x.Used && x.Team == MyTeamIndex.Value))
                extra.Add(new PlayerRow { Name = d.Name, Skin = d.Skin, Bot = d.Bot });

        return rows.Values.Concat(extra)
            .OrderByDescending(r => r.Me).ThenByDescending(r => r.Opened + r.Destroyed).ThenBy(r => r.Name)
            .Select(r => (object)new
            {
                name = r.Name, me = r.Me, skin = r.Skin, bot = r.Bot,
                opened = r.Opened, destroyed = r.Destroyed, chests = r.Opened + r.Destroyed,
            }).ToList();
    }

    private void HandleChest(uint channelIndex, Chest c, string? typeName)
    {
        ChestExports++;
        if (!_channelActor.TryGetValue(channelIndex, out var id))
        {
            ChestNoActor++;
            id = KeyFor(channelIndex);
        }
        var info = Info(id, c, typeName);
        if (c.SearchingPawn.HasValue && c.SearchingPawn.Value != 0) info.LastSearcher = c.SearchingPawn.Value;
        if (c.bAlreadySearched == true && !info.Opened)
        {
            info.Opened = true;
            info.TOpened = CurrentTimeSeconds;
            info.SearcherAtOpen = info.LastSearcher;
        }
        if (c.bDestroyed == true && !info.Destroyed)
        {
            info.Destroyed = true;
            info.TDestroyed = CurrentTimeSeconds;
        }
    }

    private bool IsChestLike(Type t)
    {
        if (!_chestPathByType.TryGetValue(t, out var path))
        {
            path = null;
            try
            {
                foreach (var a in t.GetCustomAttributes<NetFieldExportGroupAttribute>(false))
                    if (LooksLikeChest(a.Path)) { path = a.Path; break; }
            }
            catch { }
            _chestPathByType[t] = path;
        }
        return path != null;
    }

    private Chest? AdaptChest(INetFieldExportGroup g, out string typeName)
    {
        var t = g.GetType();
        _chestPathByType.TryGetValue(t, out var path);
        var p0 = path ?? t.Name;
        typeName = p0.Substring(p0.LastIndexOf('.') + 1);
        var c = new Chest();
        var any = false;
        foreach (var p in t.GetProperties(BindingFlags.Instance | BindingFlags.Public))
        {
            if (!p.CanRead || p.GetIndexParameters().Length != 0) continue;
            var n = p.Name.ToLowerInvariant();
            var isSearcher = n.Contains("searchingpawn");
            var isSearched = n.Contains("alreadysearched") || n == "bsearched" || n == "bhasbeensearched";
            var isDestroyed = n == "bdestroyed";
            if (!isSearcher && !isSearched && !isDestroyed) continue;
            object? v;
            try { v = p.GetValue(g); } catch { continue; }
            if (v == null) continue;
            if (isSearched && v is bool sb) { c.bAlreadySearched = sb; any = true; }
            else if (isDestroyed && v is bool db) { c.bDestroyed = db; any = true; }
            else if (isSearcher)
            {
                var u = ToGuid(v);
                if (u != 0) { c.SearchingPawn = u; any = true; }
            }
        }
        return any ? c : null;
    }

    private static uint ToGuid(object v)
    {
        if (v is uint u) return u;
        if (v is int i && i > 0) return (uint)i;
        if (v is ulong ul) return (uint)ul;
        if (v is long l && l > 0) return (uint)l;
        try
        {
            var inner = v.GetType().GetProperty("Value")?.GetValue(v);
            if (inner is uint iu) return iu;
        }
        catch { }
        return 0;
    }

    private void Locate(ChestInfo c)
    {
        if (c.Loc != null) return;
        var near = Loot.Where(b => b.T >= c.Time - 0.5f && b.T <= c.Time + 1.5f).OrderBy(b => b.T).ToList();
        if (near.Count == 0) return;
        var first = near[0].L;
        var group = near.Where(b => Dist(b.L, first) < 400).ToList();
        c.Loc = new[] { group.Average(b => b.L[0]), group.Average(b => b.L[1]), group.Average(b => b.L[2]) };
    }

    private uint Closest(ChestInfo c, double maxDist)
    {
        if (c.Loc == null) return 0;
        uint best = 0;
        var bestD = maxDist;
        foreach (var p in Positions.Keys)
        {
            var pos = Pos(p, c.Time);
            if (pos == null) continue;
            var d = Dist(pos, c.Loc);
            if (d < bestD) { bestD = d; best = p; }
        }
        return best;
    }

    private const double MaxDistOpen = 1000;
    private const double MaxDistBreak = 800;

    public bool IsMine(uint pawn) =>
        (Recorder.HasValue && PawnToState.TryGetValue(pawn, out var s) && s == Recorder.Value) || ExtraMyPawns.Contains(pawn);

    // A teammate is any pawn that is not mine but whose player state is on my team.
    public bool IsTeammate(uint pawn)
    {
        if (MyTeamIndex == null || IsMine(pawn)) return false;
        return PawnToState.TryGetValue(pawn, out var s) && StateTeam.TryGetValue(s, out var t) && t == MyTeamIndex.Value;
    }

    private int? ComputeMyTeam()
    {
        if (Recorder.HasValue && StateTeam.TryGetValue(Recorder.Value, out var t)) return t;
        foreach (var p in Positions.Keys.Where(IsMine))
            if (PawnToState.TryGetValue(p, out var s) && StateTeam.TryGetValue(s, out var t2)) return t2;
        return null;
    }

    // Proximity guesses are too unreliable to credit a chest to a teammate, so they are left out.
    public bool CountsForTeam(ChestInfo c) =>
        (c.Opened || c.AsDestroyed) && c.Owner != 0 && IsTeammate(c.Owner) && c.Method != "proximity" && !c.DuplicateTeam;

    private void DetectMyPawns()
    {
        foreach (var kv in Positions)
        {
            if (PawnToState.TryGetValue(kv.Key, out var st) && st != 0) continue;
            var l = kv.Value;
            if (l.Count < 500) continue;
            var dur = l[^1].T - l[0].T;
            if (dur >= 10f && l.Count / dur >= 25f) ExtraMyPawns.Add(kv.Key);
        }

        if (!Positions.Keys.Any(IsMine))
        {
            var ranked = Positions.OrderByDescending(kv => kv.Value.Count).Take(2).ToList();
            if (ranked.Count > 0 && ranked[0].Value.Count >= 200 &&
                (ranked.Count == 1 || ranked[0].Value.Count >= 2 * ranked[1].Value.Count))
            {
                ExtraMyPawns.Add(ranked[0].Key);
                UsedPawnFallback = true;
            }
        }
    }

    private bool HasMySearch(ChestInfo c) =>
        Searches.Any(s => IsMine(s.Pawn) && s.T <= c.Time + 0.3f && s.T >= c.Time - 3.5f);

    private void Dedupe(List<ChestInfo> list, Func<ChestInfo, bool> isDup, Action<ChestInfo> setDup)
    {
        for (var i = 0; i < list.Count; i++)
        {
            if (isDup(list[i])) continue;
            for (var j = i + 1; j < list.Count; j++)
            {
                var a = list[i]; var b = list[j];
                if (isDup(b)) continue;
                if (b.Time - a.Time > 10f) break;
                var sameSpot = a.Loc != null && b.Loc != null && Dist(a.Loc, b.Loc) < 350;
                var sameMoment = (a.Loc == null || b.Loc == null) && a.Type == b.Type && b.Time - a.Time < 1.5f;
                if (sameSpot || sameMoment) setDup(b);
            }
        }
    }

    public void Resolve()
    {
        DetectMyPawns();
        MyTeamIndex = ComputeMyTeam();

        foreach (var c in Chests.Values)
        {
            if (c.Opened && c.SearcherAtOpen != 0)
            {
                c.Owner = c.SearcherAtOpen; c.Method = "author"; c.Time = c.TOpened;
            }
            else if (c.Destroyed && (!c.Opened || Math.Abs(c.TDestroyed - c.TOpened) < 3f))
            {
                c.AsDestroyed = true;
                c.Time = c.Opened ? Math.Min(c.TOpened, c.TDestroyed) : c.TDestroyed;
            }
            else if (c.Opened) c.Time = c.TOpened;
        }

        var used = new HashSet<int>();
        foreach (var c in Chests.Values.Where(x => x.Method == "author"))
            for (var i = Searches.Count - 1; i >= 0; i--)
            {
                var s = Searches[i];
                if (!used.Contains(i) && s.Pawn == c.Owner && s.T <= c.Time + 0.3f && s.T >= c.Time - 3.5f)
                { used.Add(i); break; }
            }
        foreach (var c in Chests.Values.Where(x => x.Opened && !x.AsDestroyed && x.Owner == 0).OrderBy(x => x.Time))
        {
            var best = -1;
            for (var i = 0; i < Searches.Count; i++)
            {
                var s = Searches[i];
                if (used.Contains(i) || s.T > c.Time + 0.3f || s.T < c.Time - 3.5f) continue;
                if (best < 0 || s.T > Searches[best].T) best = i;
            }
            if (best >= 0) { used.Add(best); c.Owner = Searches[best].Pawn; c.Method = "search"; }
        }

        var mine = Positions.Keys.Where(IsMine).ToList();
        foreach (var c in Chests.Values.Where(x => x.Opened || x.Destroyed))
        {
            Locate(c);
            if (c.Loc == null) continue;
            foreach (var p in mine)
            {
                var pos = Pos(p, c.Time);
                if (pos == null) continue;
                var d = Dist(pos, c.Loc);
                if (c.DistMine < 0 || d < c.DistMine) c.DistMine = d;
            }
        }

        var mineOwned = Chests.Values.Count(x => x.Owner != 0 && IsMine(x.Owner));
        var farList = Chests.Values.Where(x => x.Owner != 0 && IsMine(x.Owner) && x.DistMine > MaxDistOpen
                                               && !HasMySearch(x)).ToList();
        if (farList.Count * 2 <= mineOwned)
        {
            foreach (var c in farList) { c.Owner = 0; c.Far = true; }
            FarDiscarded = farList.Count;
        }
        else FarFilterSkipped = true;

        foreach (var c in Chests.Values.Where(x => (x.AsDestroyed || x.Opened) && x.Owner == 0 && !x.Far))
        {
            if (c.LastHitter != 0 && c.Time - c.TLastHit <= 10f && c.Time >= c.TLastHit - 0.5f)
            { c.Owner = c.LastHitter; c.Method = "hit"; continue; }
            var near = Closest(c, MaxDistBreak);
            if (near != 0) { c.Owner = near; c.Method = "proximity"; }
        }

        Dedupe(Chests.Values.Where(x => x.Owner != 0 && IsMine(x.Owner)).OrderBy(x => x.Time).ToList(),
               x => x.Duplicate, x => x.Duplicate = true);

        foreach (var g in Chests.Values.Where(x => x.Owner != 0 && IsTeammate(x.Owner)).GroupBy(x => x.Owner))
            Dedupe(g.OrderBy(x => x.Time).ToList(), x => x.DuplicateTeam, x => x.DuplicateTeam = true);
    }
}

public static class Program
{
    private static readonly string[] Defaults =
    {
        "/Game/Building/ActorBlueprints/Containers/Tiered_Chest_Athena.Tiered_Chest_Athena_C",
        "/Game/Building/ActorBlueprints/Containers/Tiered_Chest_Athena_FactionChest_NoLocks.Tiered_Chest_Athena_FactionChest_NoLocks_C",
    };

    private static void RegisterChests(IEnumerable<string> paths)
    {
        var ab = AssemblyBuilder.DefineDynamicAssembly(new AssemblyName("DynamicChests"), AssemblyBuilderAccess.Run);
        var mb = ab.DefineDynamicModule("Chests");
        var ctor = typeof(NetFieldExportGroupAttribute).GetConstructor(new[] { typeof(string), typeof(ParseMode) })!;
        var i = 0;
        foreach (var path in paths.Where(LooksLikeChest).Distinct(StringComparer.OrdinalIgnoreCase))
        {
            var tb = mb.DefineType("DynChest" + i++, TypeAttributes.Public | TypeAttributes.Class, typeof(Chest));
            tb.SetCustomAttribute(new CustomAttributeBuilder(ctor, new object[] { path, ParseMode.Minimal }));
            tb.DefineDefaultConstructor(MethodAttributes.Public);
            tb.CreateType();
        }
    }

    private static bool LooksLikeChest(string g)
    {
        if (string.IsNullOrWhiteSpace(g) || !g.StartsWith("/", StringComparison.Ordinal)) return false;
        if (g.Contains(':') ||
            g.Contains("ClassNetCache", StringComparison.OrdinalIgnoreCase) ||
            g.Contains("Ammo", StringComparison.OrdinalIgnoreCase) ||
            g.Contains("Creative", StringComparison.OrdinalIgnoreCase)) return false;

        return g.Contains("Chest", StringComparison.OrdinalIgnoreCase)
            || g.Contains("Container", StringComparison.OrdinalIgnoreCase)
            || g.Contains("Treasure", StringComparison.OrdinalIgnoreCase)
            || g.Contains("LootCache", StringComparison.OrdinalIgnoreCase);
    }

    private static List<string> LibraryChestTypes()
    {
        var list = new List<string>();
        foreach (var asm in AppDomain.CurrentDomain.GetAssemblies())
        {
            if (asm.IsDynamic) continue;
            Type[] types;
            try { types = asm.GetTypes(); }
            catch (ReflectionTypeLoadException e) { types = e.Types.Where(t => t != null).ToArray()!; }
            catch { continue; }
            foreach (var t in types)
            {
                try
                {
                    foreach (var a in t.GetCustomAttributes<NetFieldExportGroupAttribute>(false))
                        if (LooksLikeChest(a.Path))
                            list.Add(t.Name + " <- " + a.Path);
                }
                catch { }
            }
        }
        return list.Distinct().Take(40).ToList();
    }

    private static List<string> Members(object obj)
    {
        var l = new List<string>();
        foreach (var p in obj.GetType().GetProperties())
        {
            try
            {
                var v = p.GetValue(obj);
                var n = v is System.Collections.ICollection c ? "[" + c.Count + "]" : v == null ? "=null" : "";
                l.Add(p.Name + ":" + p.PropertyType.Name + n);
            }
            catch { }
        }
        return l.Take(60).ToList();
    }

    private static string Line(ChestReader r, ChestInfo c)
    {
        var t = (int)c.Time;
        var who = c.Owner == 0 ? "none" : r.IsMine(c.Owner) ? "ME" : r.IsTeammate(c.Owner) ? "TEAM" : "other";
        var state = c.AsDestroyed ? "destroyed" : c.Opened ? "opened" : "-";
        return $"{t / 60:00}:{t % 60:00} {c.Type} {state} by={who} via={(c.Method == "" ? "-" : c.Method)} " +
               $"dist={(c.DistMine < 0 ? "?" : ((int)c.DistMine).ToString())}" + (c.Duplicate ? " DUP" : "") + (c.Far ? " FAR" : "");
    }

    private static object Analyze(string path)
    {
        var reader = new ChestReader();
        var replay = reader.ReadReplay(path);
        reader.Resolve();

        var mine = reader.Chests.Values
            .Where(c => (c.Opened || c.AsDestroyed) && c.Owner != 0 && reader.IsMine(c.Owner) && !c.Duplicate)
            .ToList();
        var team = reader.Chests.Values.Where(reader.CountsForTeam).ToList();
        var players = reader.BuildPlayers(replay, mine, team);

        return new
        {
            file = Path.GetFileName(path),
            ok = true,
            duration_sec = (replay.Info?.LengthInMs ?? 0) / 1000,
            mine = mine.Count,
            opened = mine.Count(c => !c.AsDestroyed),
            destroyed = mine.Count(c => c.AsDestroyed),
            team = team.Count,
            team_opened = team.Count(c => !c.AsDestroyed),
            team_destroyed = team.Count(c => c.AsDestroyed),
            team_known = reader.MyTeamIndex.HasValue,
            players,
            by_type = mine.GroupBy(c => c.Type).ToDictionary(g => g.Key, g => g.Count()),
            chest_groups = reader.Groups.Where(LooksLikeChest).OrderBy(g => g).ToList(),
            recorder_found = reader.Recorder.HasValue,
            diag = new
            {
                chest_actors = reader.Chests.Count,
                opened_any = reader.Chests.Values.Count(c => c.Opened),
                destroyed_any = reader.Chests.Values.Count(c => c.Destroyed),
                no_owner = reader.Chests.Values.Count(c => (c.Opened || c.Destroyed) && c.Owner == 0),
                far = reader.Chests.Values.Count(c => c.Far),
                far_filter_skipped = reader.FarFilterSkipped,
                adapted_exports = reader.AdaptedExports,
                chest_exports = reader.ChestExports,
                pawn_fallback = reader.UsedPawnFallback,
                opened_no_owner = reader.Chests.Values.Count(c => c.Opened && c.Owner == 0),
                duplicates = reader.Chests.Values.Count(c => c.Duplicate),
                pawns_tracked = reader.Positions.Count,
                my_pawns = reader.Positions.Keys.Count(reader.IsMine),
                extra_my_pawns = reader.ExtraMyPawns.Count,
                searches = reader.Searches.Count,
                loot = reader.Loot.Count,
                chest_groups = reader.Groups.Count(LooksLikeChest),
                player_state_exports = reader.PlayerStateExports,
                states_with_team = reader.StateTeam.Count,
                my_team_index = reader.MyTeamIndex,
                team_pawns = reader.Positions.Keys.Count(reader.IsTeammate),
            },
            detail = reader.Chests.Values.Where(c => c.Opened || c.Destroyed).OrderBy(c => c.Time)
                         .Take(30).Select(c => Line(reader, c)).ToList(),
            extra = new
            {
                chest_exports = reader.ChestExports,
                chest_exports_no_actor = reader.ChestNoActor,
                settings = reader.SettingsLog,
                export_counts = reader.ExportCounts.OrderByDescending(kv => kv.Value).Take(30)
                                      .ToDictionary(kv => kv.Key, kv => kv.Value),
                chest_group_props = reader.GroupProps.Take(14).ToDictionary(kv => kv.Key.Substring(kv.Key.LastIndexOf('/') + 1),
                                                                            kv => kv.Value.Take(40).ToList()),
                player_state_props = reader.PlayerStateProps,
                player_data_props = reader.PlayerDataProps,
                player_data_count = reader.PlayerDataCount,
                player_dump = reader.PlayerDump,
                library_chest_types = LibraryChestTypes(),
                replay_members = Members(replay),
            },
        };
    }

    public static int Main(string[] args)
    {
        Console.OutputEncoding = System.Text.Encoding.UTF8;
        var known = Path.Combine(AppContext.BaseDirectory, "known_chests.txt");
        var paths = new List<string>(Defaults);
        if (File.Exists(known))
            paths.AddRange(File.ReadAllLines(known).Select(l => l.Trim()).Where(l => l.StartsWith("/")));

        var opts = new JsonSerializerOptions { WriteIndented = false };
        foreach (var path in args)
        {
            object result;
            try { result = Analyze(path); }
            catch (Exception e)
            {
                result = new { file = Path.GetFileName(path), ok = false, error = e.GetType().Name + ": " + e.Message };
            }
            Console.WriteLine(JsonSerializer.Serialize(result, opts));
        }
        return 0;
    }
}
'''


# ---------------------------------------------------------------- helpers

def today_key():
    return dt.date.today().isoformat()


def open_path(path):
    try:
        if sys.platform == "win32":
            os.startfile(path)
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception:
        pass


def dotnet_paths():
    for d in (os.path.join(TOOLS, "dotnet"), os.path.join(LOCAL, "ChestCounter", "dotnet")):
        exe = os.path.join(d, "dotnet.exe")
        if os.path.exists(exe):
            return d, exe
    d = os.path.join(TOOLS, "dotnet")
    return d, os.path.join(d, "dotnet.exe")


# ---------------------------------------------------------------- update checker

def parse_version(v):
    nums = [int(n) for n in re.findall(r"\d+", str(v or ""))[:4]]
    return tuple(nums + [0] * (4 - len(nums)))


def _http_get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "ChestTracker"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read().decode("utf-8", errors="replace")


def fetch_latest_version():
    """Newest version published on GitHub -> (version, url), or None if nothing is published.

    Looks at APP_VERSION in the script on the main branch and at the latest GitHub Release (if any)."""
    found, errors = [], []
    try:
        m = re.search(r'^APP_VERSION\s*=\s*"([^"]+)"', _http_get(RAW_SCRIPT), re.M)
        if m:
            found.append((m.group(1), REPO_URL))
    except Exception as e:
        errors.append(e)
    try:
        d = json.loads(_http_get(RELEASE_API))
        if d.get("tag_name"):
            found.append((d["tag_name"], d.get("html_url") or REPO_URL))
    except urllib.error.HTTPError as e:
        if e.code != 404:
            errors.append(e)
    except Exception as e:
        errors.append(e)
    if found:
        return max(found, key=lambda f: parse_version(f[0]))
    if errors:
        raise errors[0]
    return None


# ---------------------------------------------------------------- data store

class Store:
    def __init__(self):
        self.lock = threading.Lock()
        self.manual, self.replays = {}, {}
        self.reader_version = 0
        self.settings = {"count_destroyed": True, "count_team": True, "delete_days": 3, "chest_types": [],
                         "help_seen": False, "theme": "pirate", "notify": True,
                         "custom_colors": {}, "font_family": "Segoe UI", "font_pct": 100,
                         "logo": "Default", "overlay_opacity": 90, "check_updates": True}
        try:
            with open(DATA_FILE, encoding="utf-8") as f:
                d = json.load(f)
            self.manual = {k: int(v) for k, v in d.get("manual", {}).items()}
            self.replays = d.get("replays", {})
            self.reader_version = int(d.get("reader_version", 0))
            self.settings.update(d.get("settings", {}))
        except Exception:
            pass

    def _save(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        tmp = DATA_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"app_version": APP_VERSION, "manual": self.manual, "replays": self.replays,
                       "reader_version": self.reader_version, "settings": self.settings},
                      f, ensure_ascii=False, indent=2)
        os.replace(tmp, DATA_FILE)

    def setting(self, key):
        with self.lock:
            return self.settings.get(key)

    def set_setting(self, key, value):
        with self.lock:
            self.settings[key] = value
            self._save()

    def add_manual(self, n):
        with self.lock:
            k = today_key()
            self.manual[k] = self.manual.get(k, 0) + n
            self._save()

    def manual_today(self):
        with self.lock:
            return self.manual.get(today_key(), 0)

    def set_replay(self, name, info):
        with self.lock:
            self.replays[name] = info
            self._save()

    def mark_all_pending(self):
        with self.lock:
            for v in self.replays.values():
                v["pending"] = True
            self._save()

    def set_reader_version(self, v):
        with self.lock:
            self.reader_version = v
            self._save()

    def replay_list(self):
        with self.lock:
            return {k: dict(v) for k, v in self.replays.items()}

    def replay_mine(self, r):
        """Chests the recording player opened/broke in this match."""
        if not r.get("ok"):
            return 0
        return int(r.get("chests", 0)) if self.settings.get("count_destroyed", True) else int(r.get("opened", 0))

    def replay_team_raw(self, r):
        """Teammates' chests in this match, whether or not they are being added to the total."""
        if not r.get("ok"):
            return 0
        if self.settings.get("count_destroyed", True):
            return int(r.get("team", 0))
        return int(r.get("team_opened", 0))

    def replay_team(self, r):
        """Teammates' chests that are actually added to the total (0 when the setting is off)."""
        return self.replay_team_raw(r) if self.settings.get("count_team", True) else 0

    def replay_count(self, r):
        return self.replay_mine(r) + self.replay_team(r)

    def days(self):
        with self.lock:
            out = dict(self.manual)
            for r in self.replays.values():
                if r.get("ok") and r.get("day"):
                    out[r["day"]] = out.get(r["day"], 0) + self.replay_count(r)
            return {k: v for k, v in out.items() if v > 0}

    def match_stats(self):
        with self.lock:
            counts = [(self.replay_count(r), r.get("day", "")) for r in self.replays.values() if r.get("ok")]
        if not counts:
            return 0, 0, 0, ""
        best = max(counts, key=lambda c: c[0])
        return len(counts), sum(c[0] for c in counts), best[0], best[1]

    def matches_counted(self):
        with self.lock:
            return sum(1 for r in self.replays.values() if r.get("ok"))


# ---------------------------------------------------------------- reader setup

class SetupError(Exception):
    pass


def run(cmd, log, cwd=None, timeout=1800):
    ddir, _ = dotnet_paths()
    env = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT="1", DOTNET_NOLOGO="1",
               DOTNET_SKIP_FIRST_TIME_EXPERIENCE="1", DOTNET_ROOT=ddir)
    p = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=timeout, creationflags=NO_WINDOW)
    log.write(f"\n$ {' '.join(cmd)}\n{p.stdout}\n{p.stderr}\n")
    log.flush()
    return p


GEN_HEADER = """using Unreal.Core.Attributes;
using Unreal.Core.Contracts;
using Unreal.Core.Models;
using Unreal.Core.Models.Enums;

namespace ChestReplayReader;
"""

GEN_CLASS = """
[NetFieldExportGroup("{path}", ParseMode.Minimal)]
public class GenChest{i} : INetFieldExportGroup
{{
    [NetFieldExport("bAlreadySearched", RepLayoutCmdType.PropertyBool)]
    public bool? bAlreadySearched {{ get; set; }}

    [NetFieldExport("SearchingPawn", RepLayoutCmdType.PropertyObject)]
    public uint? SearchingPawn {{ get; set; }}

    [NetFieldExport("bDestroyed", RepLayoutCmdType.PropertyBool)]
    public bool? bDestroyed {{ get; set; }}
}}
"""


def generated_chests_cs(types):
    out = [GEN_HEADER]
    paths = sorted({t for t in types if t.startswith("/") and '"' not in t and "\\" not in t and "\n" not in t})
    for i, path in enumerate(paths):
        out.append(GEN_CLASS.format(path=path, i=i))
    return "".join(out)


def install_reader(progress, types=()):
    os.makedirs(TOOLS, exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as log:
        log.write(f"\n===== {dt.datetime.now():%Y-%m-%d %H:%M:%S}  app {APP_VERSION}  reader {READER_VERSION} =====\n")
        try:
            ddir, dexe = dotnet_paths()
            if not os.path.exists(dexe):
                progress("Downloading .NET 10 (about 200 MB, first time only)...")
                script = os.path.join(TOOLS, "dotnet-install.ps1")
                urllib.request.urlretrieve(DOTNET_INSTALL, script)
                run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script,
                     "-Channel", "10.0", "-InstallDir", ddir], log)
                ddir, dexe = dotnet_paths()
                if not os.path.exists(dexe):
                    raise SetupError("Could not install .NET. Open Settings > View log for details.")

            if not os.path.isdir(SRC_DIR):
                progress("Downloading the replay reader...")
                data = urllib.request.urlopen(REPO_ZIP, timeout=120).read()
                with zipfile.ZipFile(io.BytesIO(data)) as z:
                    z.extractall(SRC_DIR)

            roots = [os.path.join(SRC_DIR, d) for d in os.listdir(SRC_DIR)]
            root = next(r for r in roots if os.path.isdir(os.path.join(r, "src")))
            proj_dir = os.path.join(root, "src", "ChestTracker")
            os.makedirs(proj_dir, exist_ok=True)
            with open(os.path.join(proj_dir, "ChestTracker.csproj"), "w", encoding="utf-8") as f:
                f.write(CSPROJ)
            with open(os.path.join(proj_dir, "Program.cs"), "w", encoding="utf-8") as f:
                f.write(PROGRAM_CS)
            gen = generated_chests_cs(types)
            with open(os.path.join(proj_dir, "GeneratedChests.cs"), "w", encoding="utf-8") as f:
                f.write(gen)

            progress("Building the replay reader (1-3 minutes)...")
            shutil.rmtree(BIN_DIR, ignore_errors=True)
            p = run([dexe, "publish", os.path.join(proj_dir, "ChestTracker.csproj"), "-c", "Release",
                     "-o", BIN_DIR, "--nologo"], log, cwd=root)
            if p.returncode != 0 or not os.path.exists(READER_DLL):
                raise SetupError("Building the replay reader failed. Open Settings > View log for details.")
        except SetupError:
            raise
        except Exception as e:
            log.write(f"\n{type(e).__name__}: {e}\n")
            shutil.rmtree(SRC_DIR, ignore_errors=True)
            if isinstance(e, (urllib.error.URLError, TimeoutError, ConnectionError)):
                raise SetupError("Could not download files. Check your internet connection.")
            raise
    for d in os.listdir(TOOLS):
        full = os.path.join(TOOLS, d)
        if d.startswith("reader_v") and full != BIN_DIR:
            shutil.rmtree(full, ignore_errors=True)


# ---------------------------------------------------------------- background worker

class Worker(threading.Thread):
    def __init__(self, store, events):
        super().__init__(daemon=True)
        self.store, self.events = store, events
        self.proc = None
        self.stopping = False

    def msg(self, kind, data=None):
        self.events.put((kind, data))

    def stop(self):
        self.stopping = True
        p = self.proc
        if p and p.poll() is None:
            try:
                p.kill()
            except Exception:
                pass

    def run(self):
        while not self.stopping:
            try:
                missing = self.wanted_types() - set(self.store.setting("built_types") or [])
                if not os.path.exists(READER_DLL) or self.store.reader_version != READER_VERSION or missing:
                    self.build()
                    for k, v in self.store.replay_list().items():
                        if v.get("version") != READER_VERSION:
                            v["pending"] = True
                            self.store.set_replay(k, v)
                self.scan()
            except SetupError as e:
                self.msg("status", ("error", str(e)))
                time.sleep(60)
                continue
            except Exception as e:
                self.msg("status", ("error", f"{type(e).__name__}: {e}"))
                time.sleep(30)
                continue
            time.sleep(10)

    def wanted_types(self):
        return set(self.store.setting("chest_types") or []) | set(DEFAULT_TYPES)

    def build(self):
        types = self.wanted_types()
        install_reader(lambda text: self.msg("status", ("busy", text)), types)
        self.store.set_reader_version(READER_VERSION)
        self.store.set_setting("built_types", sorted(types))

    def analyze(self, path, known_types):
        ddir, dexe = dotnet_paths()
        try:
            with open(os.path.join(BIN_DIR, "known_chests.txt"), "w", encoding="utf-8") as f:
                f.write("\n".join(sorted(known_types)))
        except OSError:
            pass
        name = os.path.basename(path)
        self.proc = subprocess.Popen([dexe, READER_DLL, path], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     text=True, encoding="utf-8", errors="replace", creationflags=NO_WINDOW,
                                     env=dict(os.environ, DOTNET_ROOT=ddir, DOTNET_CLI_TELEMETRY_OPTOUT="1"))
        try:
            out, err = self.proc.communicate(timeout=READ_TIMEOUT)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.communicate()
            return {"file": name, "ok": False, "error": "Reading took too long"}
        finally:
            code = self.proc.returncode
            self.proc = None
        for line in out.splitlines():
            line = line.strip()
            if line.startswith("{"):
                try:
                    return json.loads(line)
                except Exception:
                    pass
        if self.stopping:
            return None
        return {"file": name, "ok": False, "error": "No response from reader"}

    def scan(self):
        if not os.path.isdir(DEMOS):
            self.msg("status", ("warn", "No replays folder yet. Turn on Record Replays in Fortnite."))
            return
        now = time.time()
        known = self.store.replay_list()
        ready = []
        for f in os.listdir(DEMOS):
            if not f.lower().endswith(".replay"):
                continue
            path = os.path.join(DEMOS, f)
            try:
                st = os.stat(path)
            except OSError:
                continue
            prev = known.get(f)
            if prev and prev.get("size") == st.st_size and prev.get("version") == READER_VERSION \
                    and not prev.get("pending"):
                continue
            if now - st.st_mtime < QUIET_SECONDS:
                continue
            ready.append((st.st_mtime, f, path, st))
        ready.sort()

        for i, (mtime, f, path, st) in enumerate(ready):
            if self.stopping:
                return
            self.msg("status", ("busy", f"Reading matches... {i + 1} of {len(ready)}"))
            known_types = set(self.store.setting("chest_types") or []) | set(DEFAULT_TYPES)
            r = self.analyze(path, known_types)
            if r is None:
                return
            new_types = set(r.get("chest_groups") or []) - known_types
            if new_types:
                known_types |= new_types
                self.store.set_setting("chest_types", sorted(known_types))
                self.msg("status", ("busy", f"Learned new chest types. Rebuilding reader..."))
                self.build()
                r = self.analyze(path, known_types)
                if r is None:
                    return
                for k, v in self.store.replay_list().items():
                    if k == f:
                        continue
                    seen = v.get("groups")
                    if seen is None or new_types & set(seen):
                        v["pending"] = True
                        self.store.set_replay(k, v)
            ok = bool(r.get("ok"))
            info = {
                "ok": ok,
                "chests": int(r.get("mine", 0)) if ok else 0,
                "opened": int(r.get("opened", 0)),
                "destroyed": int(r.get("destroyed", 0)),
                "team": int(r.get("team", 0)) if ok else 0,
                "team_opened": int(r.get("team_opened", 0)) if ok else 0,
                "team_destroyed": int(r.get("team_destroyed", 0)) if ok else 0,
                "team_known": bool(r.get("team_known")),
                "players": r.get("players") or [],
                "day": dt.date.fromtimestamp(mtime).isoformat(),
                "time": dt.datetime.fromtimestamp(mtime).strftime("%H:%M"),
                "mtime": mtime,
                "size": st.st_size,
                "version": READER_VERSION,
                "recorder_found": bool(r.get("recorder_found")),
                "groups": r.get("chest_groups") or [],
                "diag": r.get("diag") or {},
                "extra": r.get("extra") or {},
                "detail": (r.get("detail") or [])[:30],
                "error": r.get("error"),
                "pending": False,
            }
            self.store.set_replay(f, info)
            fresh = f not in known and (time.time() - mtime) < 1800
            self.msg("replay", dict(info, fresh=fresh))
        n = self.store.matches_counted()
        self.msg("status", ("ok", f"Up to date - {n} match{'es' if n != 1 else ''} counted."))
        self.cleanup()

    def cleanup(self):
        days = int(self.store.setting("delete_days") or 0)
        if days <= 0 or not os.path.isdir(DEMOS):
            return
        limit = time.time() - days * 86400
        known = self.store.replay_list()
        for f in os.listdir(DEMOS):
            if not f.lower().endswith(".replay"):
                continue
            info, path = known.get(f), os.path.join(DEMOS, f)
            try:
                st = os.stat(path)
            except OSError:
                continue
            if not info or not info.get("ok") or info.get("version") != READER_VERSION \
                    or info.get("size") != st.st_size or info.get("pending") or st.st_mtime > limit:
                continue
            try:
                os.remove(path)
            except OSError:
                continue


# ---------------------------------------------------------------- desktop notifications

def _toast_thread(title, text, fallback):
    ok = False
    if sys.platform == "win32":
        def esc(v):
            return v.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("'", "''")
        ps = (
            "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, "
            "ContentType = WindowsRuntime] | Out-Null;"
            "[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, "
            "ContentType = WindowsRuntime] | Out-Null;"
            "$x = New-Object Windows.Data.Xml.Dom.XmlDocument;"
            f"$x.LoadXml('<toast><visual><binding template=\"ToastGeneric\"><text>{esc(title)}</text>"
            f"<text>{esc(text)}</text></binding></visual></toast>');"
            "$t = New-Object Windows.UI.Notifications.ToastNotification $x;"
            "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("
            "'{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\WindowsPowerShell\\v1.0\\powershell.exe').Show($t)"
        )
        try:
            r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden",
                                "-Command", ps], capture_output=True, timeout=20, creationflags=NO_WINDOW)
            ok = r.returncode == 0
        except Exception:
            ok = False
    if not ok:
        fallback(title, text)


def desktop_notify(title, text, fallback):
    threading.Thread(target=_toast_thread, args=(title, text, fallback), daemon=True).start()


# ---------------------------------------------------------------- UI building blocks

def dark_titlebar(win, dark=True):
    if sys.platform != "win32":
        return
    try:
        win.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
        val = ctypes.c_int(1 if dark else 0)
        for attr in (20, 19):
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(val), ctypes.sizeof(val)) == 0:
                break
    except Exception:
        pass


def card(parent, **kw):
    return tk.Frame(parent, bg=SURFACE, highlightthickness=1, highlightbackground=BORDER, **kw)


def flat_button(parent, text, command, primary=False, width=None):
    bg, fg = (ACCENT, ON_ACCENT) if primary else (SURFACE2, TEXT)
    hover = HOVER if primary else BORDER
    b = tk.Label(parent, text=text, bg=bg, fg=fg, font=font(10, "bold" if primary else "normal"),
                 padx=px(14), pady=px(7), cursor="hand2", width=width or 0)
    b.bind("<Button-1>", lambda e: command())
    b.bind("<Enter>", lambda e: b.config(bg=hover))
    b.bind("<Leave>", lambda e: b.config(bg=bg))
    return b


class NavButton(tk.Label):
    def __init__(self, parent, text, command):
        super().__init__(parent, text=text, bg=BG, fg=MUTED, font=font(11, "bold"), padx=px(12), pady=px(8),
                         cursor="hand2")
        self.command = command
        self.active = False
        self.bind("<Button-1>", lambda e: self.command())
        self.bind("<Enter>", lambda e: self.config(fg=TEXT))
        self.bind("<Leave>", lambda e: self.config(fg=ACCENT if self.active else MUTED))

    def set_active(self, on):
        self.active = on
        self.config(fg=ACCENT if on else MUTED)


class SkinCache:
    """Looks up a skin's name and icon (cached on disk) so the match window can show it."""

    def __init__(self):
        self.mem, self.busy, self.lock = {}, {}, threading.Lock()

    def get(self, cid):
        with self.lock:
            return self.mem.get(cid)

    def fetch(self, cid, done):
        if not cid or not re.fullmatch(r"[A-Za-z0-9_\-]+", cid):
            with self.lock:
                self.mem[cid] = {"name": cid or "Unknown", "icon": None}
            done()
            return
        with self.lock:
            if cid in self.mem:
                ready = True
            elif cid in self.busy:
                self.busy[cid].append(done)
                return
            else:
                self.busy[cid] = [done]
                ready = False
        if ready:
            done()
            return
        threading.Thread(target=self._load, args=(cid,), daemon=True).start()

    def _load(self, cid):
        meta = {"name": cid, "icon": None}
        try:
            os.makedirs(SKIN_DIR, exist_ok=True)
            jpath = os.path.join(SKIN_DIR, cid + ".json")
            ipath = os.path.join(SKIN_DIR, cid + ".png")
            if os.path.exists(jpath):
                with open(jpath, encoding="utf-8") as f:
                    meta = json.load(f)
                if meta.get("icon") and not os.path.exists(meta["icon"]):
                    meta["icon"] = None
            else:
                req = urllib.request.Request(SKIN_API + urllib.parse.quote(cid), headers={"User-Agent": "ChestTracker"})
                data = json.loads(urllib.request.urlopen(req, timeout=15).read().decode("utf-8"))["data"]
                images = data.get("images") or {}
                url = images.get("smallIcon") or images.get("icon")
                icon = None
                if url:
                    png = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "ChestTracker"}),
                                                 timeout=20).read()
                    with open(ipath, "wb") as f:
                        f.write(png)
                    icon = ipath
                meta = {"name": data.get("name") or cid, "icon": icon}
                with open(jpath, "w", encoding="utf-8") as f:
                    json.dump(meta, f)
        except Exception:
            pass
        with self.lock:
            self.mem[cid] = meta
            callbacks = self.busy.pop(cid, [])
        for cb in callbacks:
            try:
                cb()
            except Exception:
                pass


class MatchDetail(tk.Toplevel):
    """Shows one match: you and every teammate with their chest count and skin."""

    def __init__(self, parent, store, r, skins):
        super().__init__(parent)
        self.store, self.r, self.skins = store, r, skins
        self.alive = True
        self.q = queue.Queue()
        self.slots = {}
        self.images = {}
        self.title("Match details")
        self.configure(bg=BG)
        self.geometry(f"{px(580)}x{px(540)}")
        self.minsize(px(500), px(380))
        self.protocol("WM_DELETE_WINDOW", self._close)
        self._build()
        dark_titlebar(self, luminance(BG) < 0.5)
        self.after(250, self._poll)

    def _close(self):
        self.alive = False
        self.destroy()

    def _build(self):
        r, st = self.r, self.store
        head = tk.Frame(self, bg=BG)
        head.pack(fill="x", padx=px(18), pady=(px(16), px(8)))
        tk.Label(head, text=f"Match  {r.get('day', '')}  {r.get('time', '')}".strip(), bg=BG, fg=TEXT,
                 font=font(14, "bold")).pack(anchor="w")
        mine, team = st.replay_mine(r), st.replay_team_raw(r)
        line = f"You: {mine}    Teammates: {team}    Added to your total: {st.replay_count(r)}"
        if team and not st.setting("count_team"):
            line += "   (teammates are switched off in Settings)"
        tk.Label(head, text=line, bg=BG, fg=MUTED, font=font(10)).pack(anchor="w", pady=(2, 0))

        outer = tk.Frame(self, bg=BG)
        outer.pack(fill="both", expand=True, padx=px(18), pady=(0, px(16)))
        cv = tk.Canvas(outer, bg=BG, highlightthickness=0)
        sb = ttk.Scrollbar(outer, orient="vertical", command=cv.yview)
        inner = tk.Frame(cv, bg=BG)
        win = cv.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e: cv.configure(scrollregion=cv.bbox("all")))
        cv.bind("<Configure>", lambda e: cv.itemconfigure(win, width=e.width))
        cv.configure(yscrollcommand=sb.set)
        cv.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.bind("<MouseWheel>", lambda e: cv.yview_scroll(int(-e.delta / 120), "units"))

        players = r.get("players") or []
        if not players:
            tk.Label(inner, text="No team details were saved for this match.\n"
                                 "If the replay is still on disk, use Settings > Re-scan all.",
                     bg=BG, fg=MUTED, font=font(10), justify="left").pack(anchor="w", pady=px(8))
            return
        for p in players:
            self._player_row(inner, p)
        if not r.get("team_known"):
            tk.Label(inner, text="Your team could not be identified in this replay, so only your own chests are listed.",
                     bg=BG, fg=WARN, font=font(9), wraplength=px(480), justify="left").pack(anchor="w", pady=px(4))

    def _player_row(self, parent, p):
        st = self.store
        row = card(parent)
        row.pack(fill="x", pady=(0, px(8)))
        pname = p.get("name") or ("You" if p.get("me") else "Unknown player")
        box = tk.Frame(row, bg=SURFACE2, width=px(64), height=px(64))
        box.pack(side="left", padx=px(12), pady=px(12))
        box.pack_propagate(False)
        icon = tk.Label(box, bg=SURFACE2, fg=MUTED, text=(pname[:1].upper() or "?"), font=font(18, "bold"))
        icon.pack(fill="both", expand=True)

        mid = tk.Frame(row, bg=SURFACE)
        mid.pack(side="left", fill="x", expand=True, pady=px(12))
        top = tk.Frame(mid, bg=SURFACE)
        top.pack(anchor="w")
        tk.Label(top, text=pname, bg=SURFACE, fg=TEXT, font=font(12, "bold")).pack(side="left")
        if p.get("me"):
            tk.Label(top, text="  YOU", bg=SURFACE, fg=ACCENT, font=font(8, "bold")).pack(side="left")
        elif p.get("bot"):
            tk.Label(top, text="  BOT", bg=SURFACE, fg=MUTED, font=font(8, "bold")).pack(side="left")
        cid = p.get("skin") or ""
        skin = tk.Label(mid, text="Loading skin..." if cid else "Skin unknown", bg=SURFACE, fg=MUTED, font=font(9))
        skin.pack(anchor="w")

        opened, destroyed = int(p.get("opened", 0)), int(p.get("destroyed", 0))
        n = opened + (destroyed if st.setting("count_destroyed") else 0)
        right = tk.Frame(row, bg=SURFACE)
        right.pack(side="right", padx=px(16))
        tk.Label(right, text=f"{n:,}", bg=SURFACE, fg=ACCENT, font=font(24, "bold")).pack(anchor="e")
        tk.Label(right, text=f"{opened} opened, {destroyed} broken", bg=SURFACE, fg=MUTED,
                 font=font(8)).pack(anchor="e")
        if cid:
            self.slots.setdefault(cid, []).append((icon, skin))
            self.skins.fetch(cid, lambda c=cid: self.q.put(c))

    def _poll(self):
        if not self.alive:
            return
        try:
            while True:
                self._apply(self.q.get_nowait())
        except queue.Empty:
            pass
        self.after(250, self._poll)

    def _apply(self, cid):
        meta = self.skins.get(cid) or {}
        name = meta.get("name") or cid
        img = None
        path = meta.get("icon")
        if path and os.path.exists(path):
            try:
                img = tk.PhotoImage(file=path)
                f = max(1, round(img.width() / px(64)))
                if f > 1:
                    img = img.subsample(f)
                self.images[cid] = img
            except tk.TclError:
                img = None
        for icon, skin in self.slots.get(cid, []):
            skin.config(text=name)
            if img is not None:
                icon.config(image=img, text="")


CREDITS_NAME = "hmr_abood"
CREDITS_LINKS = (
    ("TikTok", "https://www.tiktok.com/@hmr_aboodyt"),
    ("GitHub", "https://github.com/Hmr-Abood"),
    ("Project", REPO_URL),
)

HELP_TEXT = (
    "1. In Fortnite: Settings > Game > Replays > Record Replays (Battle Royale) = On.\n\n"
    "2. Keep Chest Tracker open (minimized is fine) and play.\n\n"
    "3. About 2 minutes after each match ends, its chests are added to your total and to today.\n\n"
    "Counted: every chest you open and, if enabled, the chests you break. Chests opened by your teammates "
    "are added too (you can turn that off in Settings). Chests opened by enemies or other teams are never "
    "counted.\n\n"
    "Use the Customize tab to change the theme, colors, font and the live Stream Overlay."
)


# ---------------------------------------------------------------- application

class App:
    def __init__(self, root, start_worker=True):
        global SCALE
        self.root = root
        SCALE = max(1.0, root.winfo_fpixels("1i") / 96.0)
        self.store = Store()
        self.skins = SkinCache()
        self.match_win = None
        self._apply_look()
        self.events = queue.Queue()
        self.last = None
        self.hover = None
        self.page_key = "dashboard"
        self.status_level = None
        self.status_text = ""
        self.overlay_win = None
        self.update_info = None
        self._update_prompted = False

        root.title("Chest Tracker")
        root.geometry(f"{px(960)}x{px(780)}")
        root.minsize(px(920), px(700))
        self._build_ui()

        self.worker = Worker(self.store, self.events)
        if start_worker:
            self.worker.start()
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.refresh()
        root.after(200, self._pump)
        root.after(60000, self._minute)
        if start_worker and self.store.setting("check_updates"):
            root.after(4000, lambda: self._check_updates(False))
        dark_titlebar(root, luminance(BG) < 0.5)
        if start_worker and not self.store.setting("help_seen"):
            self.store.set_setting("help_seen", True)
            root.after(700, lambda: messagebox.showinfo("Welcome to Chest Tracker", HELP_TEXT, parent=self.root))

    def _apply_look(self):
        apply_theme(self.store.setting("theme"), self.store.setting("custom_colors"))
        logo = self.store.setting("logo")
        if logo and logo != "Default":
            globals()["LOGO"] = logo
        apply_fonts(self.store.setting("font_family"), self.store.setting("font_pct"))

    def _build_ui(self):
        self.root.configure(bg=BG)
        self._style()
        self._build_header()
        self.body = tk.Frame(self.root, bg=BG)
        self.body.pack(fill="both", expand=True, padx=px(22), pady=(0, px(18)))
        self.pages = {}
        self._build_dashboard()
        self._build_matches()
        self._build_milestones()
        self._build_settings()
        self._build_customize()
        self._build_credits()
        self.show(self.page_key)

    def _rebuild(self):
        """Re-create the whole window so a new theme / font takes effect everywhere."""
        had_overlay = bool(self.overlay_win and self.overlay_win.winfo_exists())
        if had_overlay:
            self.overlay_win.destroy()
            self.overlay_win = None
        self._apply_look()
        for w in self.root.winfo_children():
            if not isinstance(w, tk.Toplevel):
                w.destroy()
        self._build_ui()
        self.refresh()
        self._show_update_banner()
        if had_overlay:
            self.v_overlay.set(True)
            self._toggle_overlay()
        if self.status_level:
            self._set_status(self.status_level, self.status_text)
        dark_titlebar(self.root, luminance(BG) < 0.5)

    def _rebuild_soon(self):
        self.root.after(60, self._rebuild)

    def close(self):
        self.worker.stop()
        if self.overlay_win and self.overlay_win.winfo_exists():
            self.overlay_win.destroy()
        self.root.destroy()

    def _style(self):
        s = ttk.Style(self.root)
        try:
            s.theme_use("clam")
        except tk.TclError:
            pass
        s.configure("Treeview", background=SURFACE, fieldbackground=SURFACE, foreground=TEXT, rowheight=px(30),
                    borderwidth=0, font=font(10))
        s.configure("Treeview.Heading", background=SURFACE2, foreground=MUTED, relief="flat",
                    font=font(9, "bold"), padding=(px(8), px(6)))
        s.map("Treeview", background=[("selected", SURFACE2)], foreground=[("selected", ACCENT)])
        s.map("Treeview.Heading", background=[("active", BORDER)])
        s.configure("Vertical.TScrollbar", background=BORDER, troughcolor=SURFACE, bordercolor=SURFACE,
                    arrowcolor=MUTED, lightcolor=BORDER, darkcolor=BORDER, gripcount=0)
        s.configure("Dark.TCheckbutton", background=SURFACE, foreground=TEXT, font=font(10),
                    indicatorcolor=SURFACE2)
        s.map("Dark.TCheckbutton", background=[("active", SURFACE)], indicatorcolor=[("selected", ACCENT)])
        s.configure("TSpinbox", fieldbackground=SURFACE2, background=SURFACE2, foreground=TEXT,
                    arrowcolor=TEXT, bordercolor=BORDER)
        s.configure("TCombobox", fieldbackground=SURFACE2, background=SURFACE2, foreground=TEXT,
                    arrowcolor=TEXT, bordercolor=BORDER, selectbackground=SURFACE2, selectforeground=TEXT)
        s.map("TCombobox", fieldbackground=[("readonly", SURFACE2)], foreground=[("readonly", TEXT)])
        s.configure("Horizontal.TScale", background=SURFACE, troughcolor=SURFACE2, bordercolor=BORDER)
        self.root.option_add("*TCombobox*Listbox.background", SURFACE2)
        self.root.option_add("*TCombobox*Listbox.foreground", TEXT)
        self.root.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
        self.root.option_add("*TCombobox*Listbox.selectForeground", ON_ACCENT)

    def _build_header(self):
        h = tk.Frame(self.root, bg=BG)
        h.pack(fill="x", padx=px(22), pady=(px(16), px(10)))
        logo = tk.Frame(h, bg=BG)
        logo.pack(side="left")
        tk.Label(logo, text=LOGO, bg=BG, fg=ACCENT, font=font(16, "bold")).pack(side="left")
        tk.Label(logo, text=" Chest", bg=BG, fg=TEXT, font=font(16, "bold")).pack(side="left")
        tk.Label(logo, text="Tracker", bg=BG, fg=ACCENT, font=font(16, "bold")).pack(side="left")

        nav = tk.Frame(h, bg=BG)
        nav.pack(side="left", padx=px(20))
        self.nav = {}
        for key, label in (("dashboard", "Dashboard"), ("matches", "Matches"), ("milestones", "Milestones"),
                           ("settings", "Settings"), ("customize", "Customize"), ("credits", "Credits")):
            b = NavButton(nav, label, lambda k=key: self.show(k))
            b.pack(side="left")
            self.nav[key] = b

        self.pill = tk.Label(h, text="\u25CF  Starting", bg=SURFACE, fg=MUTED, font=font(9, "bold"),
                             padx=px(12), pady=px(5))
        self.pill.pack(side="right")

        # shown (packed) only when a newer version exists on GitHub
        self.update_lbl = tk.Label(h, text="", bg=ACCENT, fg=ON_ACCENT, font=font(9, "bold"),
                                   padx=px(12), pady=px(5), cursor="hand2")
        self.update_lbl.bind("<Button-1>", lambda e: self._open_update())
        self.update_lbl.bind("<Enter>", lambda e: self.update_lbl.config(bg=HOVER))
        self.update_lbl.bind("<Leave>", lambda e: self.update_lbl.config(bg=ACCENT))

    def show(self, key):
        self.page_key = key
        for k, f in self.pages.items():
            f.pack_forget()
            self.nav[k].set_active(k == key)
        self.pages[key].pack(fill="both", expand=True)
        if key == "matches":
            self.fill_matches()
        elif key == "milestones":
            self.fill_milestones()

    def _build_dashboard(self):
        page = tk.Frame(self.body, bg=BG)
        self.pages["dashboard"] = page
        page.columnconfigure(0, weight=5, uniform="c")
        page.columnconfigure(1, weight=6, uniform="c")

        hero = card(page)
        hero.grid(row=0, column=0, sticky="nsew", padx=(0, px(8)), pady=(0, px(12)))
        tk.Label(hero, text="TOTAL CHESTS", bg=SURFACE, fg=MUTED, font=font(9, "bold")).pack(pady=(px(22), 0))
        self.lbl_total = tk.Label(hero, text="0", bg=SURFACE, fg=ACCENT, font=font(64, "bold"))
        self.lbl_total.pack()
        self.lbl_matches = tk.Label(hero, text="", bg=SURFACE, fg=MUTED, font=font(10))
        self.lbl_matches.pack()
        tk.Frame(hero, bg=BORDER, height=1).pack(fill="x", padx=px(28), pady=(px(10), px(8)))
        tk.Label(hero, text="SHOP TOKEN CHANCE", bg=SURFACE, fg=MUTED, font=font(8, "bold")).pack()
        self.lbl_token = tk.Label(hero, text="-", bg=SURFACE, fg=VIOLET, font=font(24, "bold"), cursor="hand2")
        self.lbl_token.pack()
        self.lbl_token.bind("<Button-1>", lambda e: self._token_info())
        tk.Label(hero, text="click to see how this is worked out", bg=SURFACE, fg=MUTED,
                 font=font(8)).pack()
        self.lbl_next = tk.Label(hero, text="", bg=SURFACE, fg=ACCENT, font=font(9, "bold"))
        self.lbl_next.pack(pady=(px(4), 0))
        sim_btn = tk.Label(hero, text="Simulate token rolls", bg=SURFACE2, fg=TEXT, font=font(9),
                           padx=px(12), pady=px(5), cursor="hand2")
        sim_btn.pack(pady=(px(8), px(14)))
        sim_btn.bind("<Button-1>", lambda e: self._open_sim())
        sim_btn.bind("<Enter>", lambda e: sim_btn.config(bg=BORDER))
        sim_btn.bind("<Leave>", lambda e: sim_btn.config(bg=SURFACE2))

        grid = tk.Frame(page, bg=BG)
        grid.grid(row=0, column=1, sticky="nsew", padx=(px(8), 0), pady=(0, px(12)))
        for c in range(2):
            grid.columnconfigure(c, weight=1, uniform="s")
        for r in range(2):
            grid.rowconfigure(r, weight=1, uniform="s")
        self.stat = {}
        for i, (key, title) in enumerate((("today", "TODAY"), ("week", "LAST 7 DAYS"),
                                          ("avg", "DAILY AVERAGE"), ("best", "BEST DAY"))):
            c = card(grid)
            c.grid(row=i // 2, column=i % 2, sticky="nsew", padx=(0 if i % 2 == 0 else px(6), px(6) if i % 2 == 0 else 0),
                   pady=(0 if i < 2 else px(6), px(6) if i < 2 else 0))
            tk.Label(c, text=title, bg=SURFACE, fg=MUTED, font=font(8, "bold")).pack(anchor="w", padx=px(14), pady=(px(12), 0))
            v = tk.Label(c, text="0", bg=SURFACE, fg=TEXT, font=font(24, "bold"))
            v.pack(anchor="w", padx=px(14))
            sub = tk.Label(c, text="", bg=SURFACE, fg=MUTED, font=font(9))
            sub.pack(anchor="w", padx=px(14), pady=(0, px(10)))
            self.stat[key] = (v, sub)

        chart_card = card(page)
        chart_card.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(0, px(12)))
        page.rowconfigure(1, weight=1)
        head = tk.Frame(chart_card, bg=SURFACE)
        head.pack(fill="x", padx=px(16), pady=(px(12), 0))
        tk.Label(head, text="Last 14 days", bg=SURFACE, fg=TEXT, font=font(11, "bold")).pack(side="left")
        self.lbl_hover = tk.Label(head, text="", bg=SURFACE, fg=MUTED, font=font(9))
        self.lbl_hover.pack(side="right")
        self.cv = tk.Canvas(chart_card, bg=SURFACE, highlightthickness=0, height=px(150))
        self.cv.pack(fill="both", expand=True, padx=px(10), pady=(px(4), px(10)))
        self.cv.bind("<Configure>", lambda e: self.draw_chart())
        self.cv.bind("<Motion>", self._chart_hover)
        self.cv.bind("<Leave>", lambda e: self._set_hover(None))

        self.last_card = card(page)
        self.last_card.grid(row=2, column=0, columnspan=2, sticky="ew")
        self.lbl_last_title = tk.Label(self.last_card, text="LAST MATCH", bg=SURFACE, fg=MUTED, font=font(8, "bold"))
        self.lbl_last_title.pack(anchor="w", padx=px(16), pady=(px(10), 0))
        self.lbl_last = tk.Label(self.last_card, text="Nothing counted yet", bg=SURFACE, fg=TEXT, font=font(11))
        self.lbl_last.pack(anchor="w", padx=px(16), pady=(0, px(10)))

    def _build_matches(self):
        page = tk.Frame(self.body, bg=BG)
        self.pages["matches"] = page
        tk.Label(page, text="Click a match to see your teammates, their chests and their skins", bg=BG, fg=MUTED,
                 font=font(9)).pack(anchor="w", pady=(0, px(6)))
        c = card(page)
        c.pack(fill="both", expand=True)
        cols = ("when", "total", "opened", "destroyed", "team", "status")
        self.tv = ttk.Treeview(c, columns=cols, show="headings")
        spec = {"when": ("MATCH", 160, "w"), "total": ("CHESTS", 80, "e"), "opened": ("OPENED", 80, "e"),
                "destroyed": ("DESTROYED", 100, "e"), "team": ("TEAMMATES", 100, "e"),
                "status": ("STATUS", 240, "w")}
        for k, (t, w, a) in spec.items():
            self.tv.heading(k, text=t, anchor=a)
            self.tv.column(k, width=px(w), anchor=a, stretch=(k == "status"))
        sb = ttk.Scrollbar(c, orient="vertical", command=self.tv.yview)
        self.tv.configure(yscrollcommand=sb.set)
        self.tv.pack(side="left", fill="both", expand=True, padx=(px(2), 0), pady=px(2))
        sb.pack(side="right", fill="y")
        self.tv.tag_configure("bad", foreground=BAD)
        self.tv.tag_configure("wait", foreground=WARN)
        self.tv.configure(cursor="hand2")
        self.tv.bind("<ButtonRelease-1>", self._match_clicked)

    def fill_matches(self):
        self.tv.delete(*self.tv.get_children())
        items = sorted(self.store.replay_list().items(),
                       key=lambda kv: (kv[1].get("day", ""), kv[1].get("time", "")), reverse=True)
        team_on = bool(self.store.setting("count_team"))
        for rname, r in items:
            when = f"{r.get('day', '')}  {r.get('time', '')}".strip()
            tag = ""
            if r.get("pending"):
                status, tag = "Waiting to be re-read", "wait"
            elif not r.get("ok"):
                status, tag = f"Error: {r.get('error') or '?'}", "bad"
            elif not r.get("recorder_found", True):
                status, tag = "Warning: recording player not found", "wait"
            elif r.get("chests") or r.get("team"):
                status = "OK"
                if team_on and not r.get("team_known"):
                    status, tag = "OK - team not detected", "wait"
            else:
                status = self._zero_reason(r)
            if r.get("ok"):
                team = self.store.replay_team_raw(r)
                nums = (self.store.replay_count(r), r.get("opened", 0), r.get("destroyed", 0),
                        team if team_on else f"({team})")
            else:
                nums = ("-", "-", "-", "-")
            self.tv.insert("", "end", iid=rname, values=(when, *nums, status), tags=(tag,) if tag else ())

    def _match_clicked(self, e):
        if self.tv.identify_region(e.x, e.y) != "cell":
            return
        iid = self.tv.identify_row(e.y)
        if iid:
            self._open_match(iid)

    def _open_match(self, rname):
        r = self.store.replay_list().get(rname)
        if not r:
            return
        if self.match_win is not None and self.match_win.winfo_exists():
            self.match_win.destroy()
        self.match_win = MatchDetail(self.root, self.store, r, self.skins)

    @staticmethod
    def _zero_reason(r):
        d = r.get("diag") or {}
        if not d:
            return "0 chests (re-scan for details)"
        if not d.get("chest_actors"):
            return f"0 chests - no chest data delivered"
        if not d.get("my_pawns"):
            return f"0 chests - your character was not identified"
        if d.get("far"):
            return f"0 chests - {d['far']} chests ignored as too far"
        return f"0 chests - none matched you"

    def _rates(self):
        mn, mtotal, _, _ = self.store.match_stats()
        days = self.store.days()
        per_match = mtotal / mn if mn and mtotal else 0
        per_day = sum(days.values()) / len(days) if days else 0
        return per_match, per_day

    def _eta(self, left, per_match, per_day):
        m = f"~{math.ceil(left / per_match):,} matches" if per_match > 0 else "-"
        d = f"~{math.ceil(left / per_day):,} days of play" if per_day > 0 else "-"
        return m, d

    def _next_milestone(self, total):
        for p in MILESTONES:
            need = chests_for_chance(p)
            if need > total:
                return p, need, need - total
        return None

    def _build_milestones(self):
        page = tk.Frame(self.body, bg=BG)
        self.pages["milestones"] = page

        top = card(page)
        top.pack(fill="x", pady=(0, px(12)))
        tk.Label(top, text="NEXT MILESTONE", bg=SURFACE, fg=MUTED, font=font(8, "bold")).pack(
            anchor="w", padx=px(18), pady=(px(14), 0))
        self.lbl_ms_next = tk.Label(top, text="-", bg=SURFACE, fg=ACCENT, font=font(20, "bold"))
        self.lbl_ms_next.pack(anchor="w", padx=px(18))
        self.lbl_ms_eta = tk.Label(top, text="", bg=SURFACE, fg=TEXT, font=font(10))
        self.lbl_ms_eta.pack(anchor="w", padx=px(18), pady=(px(2), px(8)))
        self.ms_bar = tk.Canvas(top, bg=SURFACE2, highlightthickness=0, height=px(10))
        self.ms_bar.pack(fill="x", padx=px(18), pady=(0, px(14)))
        self.ms_bar.bind("<Configure>", lambda e: self.draw_ms_bar())
        self._ms_progress = 0.0

        c = card(page)
        c.pack(fill="both", expand=True)
        cols = ("chance", "need", "left", "matches", "days")
        self.tv_ms = ttk.Treeview(c, columns=cols, show="headings", height=len(MILESTONES))
        spec = {"chance": ("CHANCE OF A TOKEN", 150, "w"), "need": ("CHESTS NEEDED", 120, "e"),
                "left": ("STILL TO GO", 110, "e"), "matches": ("MATCHES", 120, "e"),
                "days": ("DAYS OF PLAY", 150, "e")}
        for k, (t, w, a) in spec.items():
            self.tv_ms.heading(k, text=t, anchor=a)
            self.tv_ms.column(k, width=px(w), anchor=a, stretch=(k == "days"))
        self.tv_ms.pack(fill="x", padx=px(2), pady=px(2))
        self.tv_ms.tag_configure("done", foreground=GOOD)
        tk.Label(c, text=f"Estimates use your own average chests per match and per day played.",
                 bg=SURFACE, fg=MUTED, font=font(9), justify="left", anchor="w", wraplength=px(740)).pack(
            anchor="w", padx=px(14), pady=(px(10), px(12)))

    def draw_ms_bar(self):
        cv = self.ms_bar
        cv.delete("all")
        w, h = cv.winfo_width(), cv.winfo_height()
        if w > 4:
            cv.create_rectangle(0, 0, w * self._ms_progress, h, fill=ACCENT, width=0)

    def fill_milestones(self):
        total = sum(self.store.days().values())
        per_match, per_day = self._rates()
        nxt = self._next_milestone(total)
        if nxt is None:
            self.lbl_ms_next.config(text="All milestones reached")
            self.lbl_ms_eta.config(text="")
            self._ms_progress = 1.0
        else:
            p, need, left = nxt
            m, d = self._eta(left, per_match, per_day)
            self.lbl_ms_next.config(text=f"{p:.0%} chance of a token")
            eta = "  -  ".join(x for x in (m, d) if x != "-")
            self.lbl_ms_eta.config(text=f"{left:,} more chests ({total:,} of {need:,})"
                                        + (f"   -   at your pace: {eta}" if eta else ""))
            self._ms_progress = min(1.0, total / need)
        self.draw_ms_bar()
        self.tv_ms.delete(*self.tv_ms.get_children())
        for p in MILESTONES:
            need = chests_for_chance(p)
            left = need - total
            if left <= 0:
                vals = (f"{p:.0%}", f"{need:,}", "Reached", "-", "-")
                tag = ("done",)
            else:
                m, d = self._eta(left, per_match, per_day)
                vals = (f"{p:.0%}", f"{need:,}", f"{left:,}", m, d)
                tag = ()
            self.tv_ms.insert("", "end", values=vals, tags=tag)

    def _build_credits(self):
        page = tk.Frame(self.body, bg=BG)
        self.pages["credits"] = page
        c = card(page)
        c.pack(fill="x")
        tk.Label(c, text="CREDITS", bg=SURFACE, fg=MUTED, font=font(8, "bold")).pack(
            anchor="w", padx=px(24), pady=(px(20), 0))
        tk.Label(c, text=CREDITS_NAME, bg=SURFACE, fg=ACCENT, font=font(28, "bold")).pack(
            anchor="w", padx=px(24), pady=(px(2), 0))
        tk.Label(c, text=f"Chest Tracker v{APP_VERSION}", bg=SURFACE, fg=MUTED, font=font(10)).pack(
            anchor="w", padx=px(24), pady=(0, px(14)))
        tk.Frame(c, bg=BORDER, height=1).pack(fill="x", padx=px(24))
        for label, url in CREDITS_LINKS:
            row = tk.Frame(c, bg=SURFACE)
            row.pack(fill="x", padx=px(24), pady=(px(14), 0))
            tk.Label(row, text=label.upper(), bg=SURFACE, fg=MUTED, font=font(8, "bold"), width=8,
                     anchor="w").pack(side="left")
            link = tk.Label(row, text=url, bg=SURFACE, fg=VIOLET, font=font(11, "underline"),
                            cursor="hand2")
            link.pack(side="left")
            link.bind("<Button-1>", lambda e, u=url: webbrowser.open(u))
            link.bind("<Enter>", lambda e, w=link: w.config(fg=ACCENT))
            link.bind("<Leave>", lambda e, w=link: w.config(fg=VIOLET))
        tk.Frame(c, bg=SURFACE, height=px(20)).pack()

    def _build_settings(self):
        page = tk.Frame(self.body, bg=BG)
        self.pages["settings"] = page
        page.columnconfigure(0, weight=1)

        c1 = card(page)
        c1.pack(fill="x", pady=(0, px(12)))
        tk.Label(c1, text="Counting", bg=SURFACE, fg=TEXT, font=font(12, "bold")).pack(anchor="w", padx=px(18), pady=(px(14), px(6)))
        self.v_destroyed = tk.BooleanVar(value=bool(self.store.setting("count_destroyed")))
        ttk.Checkbutton(c1, text="Count destroyed chests (broken with the pickaxe or explosives)",
                        variable=self.v_destroyed, style="Dark.TCheckbutton",
                        command=self._destroyed_changed).pack(anchor="w", padx=px(18))
        self.v_team = tk.BooleanVar(value=bool(self.store.setting("count_team")))
        ttk.Checkbutton(c1, text="Also count my teammates' chests (duos, trios, squads)",
                        variable=self.v_team, style="Dark.TCheckbutton",
                        command=self._team_changed).pack(anchor="w", padx=px(18), pady=(px(6), 0))
        row = tk.Frame(c1, bg=SURFACE)
        row.pack(anchor="w", padx=px(18), pady=(px(10), px(4)))
        tk.Label(row, text="Delete counted replays after", bg=SURFACE, fg=TEXT, font=font(10)).pack(side="left")
        self.v_days = tk.StringVar(value=str(self.store.setting("delete_days")))
        sp = ttk.Spinbox(row, from_=0, to=365, width=4, textvariable=self.v_days, command=self._days_changed)
        sp.pack(side="left", padx=px(8))
        sp.bind("<FocusOut>", lambda e: self._days_changed())
        sp.bind("<Return>", lambda e: self._days_changed())
        tk.Label(row, text="days  (0 = never)", bg=SURFACE, fg=MUTED, font=font(9)).pack(side="left")
        tk.Frame(c1, bg=SURFACE, height=px(12)).pack()

        c_ui = card(page)
        c_ui.pack(fill="x", pady=(0, px(12)))
        tk.Label(c_ui, text="Alerts", bg=SURFACE, fg=TEXT, font=font(12, "bold")).pack(
            anchor="w", padx=px(18), pady=(px(14), px(6)))
        self.v_notify = tk.BooleanVar(value=bool(self.store.setting("notify")))
        ttk.Checkbutton(c_ui, text="Show desktop notification when match is counted",
                        variable=self.v_notify, style="Dark.TCheckbutton",
                        command=self._notify_changed).pack(anchor="w", padx=px(18))
        self.v_updates = tk.BooleanVar(value=bool(self.store.setting("check_updates")))
        ttk.Checkbutton(c_ui, text="Check for a newer version when the app starts",
                        variable=self.v_updates, style="Dark.TCheckbutton",
                        command=self._updates_changed).pack(anchor="w", padx=px(18), pady=(px(6), 0))
        r_ui = tk.Frame(c_ui, bg=SURFACE)
        r_ui.pack(anchor="w", padx=px(18), pady=(px(10), px(14)))
        flat_button(r_ui, "Test notification",
                    lambda: self._notify("Chest Tracker", "Notifications are working.")).pack(side="left")

        c2 = card(page)
        c2.pack(fill="x", pady=(0, px(12)))
        tk.Label(c2, text="Manual Correction (Today)", bg=SURFACE, fg=TEXT, font=font(12, "bold")).pack(anchor="w", padx=px(18), pady=(px(14), px(6)))
        r2 = tk.Frame(c2, bg=SURFACE)
        r2.pack(anchor="w", padx=px(18), pady=(0, px(14)))
        flat_button(r2, "\u2212 1", lambda: self._correct(-1)).pack(side="left")
        flat_button(r2, "+ 1", lambda: self._correct(1)).pack(side="left", padx=px(8))
        self.lbl_manual = tk.Label(r2, text="", bg=SURFACE, fg=MUTED, font=font(9))
        self.lbl_manual.pack(side="left", padx=px(10))

        c3 = card(page)
        c3.pack(fill="x", pady=(0, px(12)))
        tk.Label(c3, text="Tools", bg=SURFACE, fg=TEXT, font=font(12, "bold")).pack(anchor="w", padx=px(18), pady=(px(14), px(8)))
        r3 = tk.Frame(c3, bg=SURFACE)
        r3.pack(anchor="w", padx=px(18), pady=(0, px(14)))
        flat_button(r3, "Replays folder", self.open_demos).pack(side="left")
        flat_button(r3, "Data folder", lambda: open_path(DATA_DIR)).pack(side="left", padx=px(8))
        flat_button(r3, "Log", lambda: open_path(LOG_FILE)).pack(side="left")
        flat_button(r3, "Re-scan all", self._rescan).pack(side="left", padx=px(8))
        flat_button(r3, "Save diagnostics", self.save_report).pack(side="left")
        flat_button(r3, "Check for updates", lambda: self._check_updates(True)).pack(side="left", padx=px(8))

        c4 = card(page)
        c4.pack(fill="x")
        tk.Label(c4, text="How it works", bg=SURFACE, fg=TEXT, font=font(12, "bold")).pack(anchor="w", padx=px(18), pady=(px(14), px(4)))
        tk.Label(c4, text=HELP_TEXT, bg=SURFACE, fg=MUTED, font=font(9), justify="left", anchor="w",
                 wraplength=px(760)).pack(anchor="w", padx=px(18), pady=(0, px(14)))

    # ------------------------------------------------------------ customize page

    def _build_customize(self):
        page = tk.Frame(self.body, bg=BG)
        self.pages["customize"] = page
        custom = self.store.setting("custom_colors") or {}

        # theme presets
        c1 = card(page)
        c1.pack(fill="x", pady=(0, px(12)))
        tk.Label(c1, text="Theme preset", bg=SURFACE, fg=TEXT, font=font(12, "bold")).pack(
            anchor="w", padx=px(18), pady=(px(14), px(8)))
        row = tk.Frame(c1, bg=SURFACE)
        row.pack(anchor="w", padx=px(18), pady=(0, px(14)))
        current = self.store.setting("theme")
        for name in THEMES:
            flat_button(row, name.capitalize(), lambda n=name: self._set_preset(n),
                        primary=(name == current and not custom)).pack(side="left", padx=(0, px(8)))

        # individual colors
        c2 = card(page)
        c2.pack(fill="x", pady=(0, px(12)))
        head = tk.Frame(c2, bg=SURFACE)
        head.pack(fill="x", padx=px(18), pady=(px(14), px(8)))
        tk.Label(head, text="Colors", bg=SURFACE, fg=TEXT, font=font(12, "bold")).pack(side="left")
        tk.Label(head, text="click a swatch to change it", bg=SURFACE, fg=MUTED, font=font(9)).pack(
            side="left", padx=px(12))
        flat_button(head, "Reset colors", self._reset_colors).pack(side="right")
        grid = tk.Frame(c2, bg=SURFACE)
        grid.pack(fill="x", padx=px(18), pady=(0, px(14)))
        grid.columnconfigure(0, weight=1, uniform="col")
        grid.columnconfigure(1, weight=1, uniform="col")
        for i, (key, label) in enumerate(COLOR_LABELS):
            cell = tk.Frame(grid, bg=SURFACE)
            cell.grid(row=i // 2, column=i % 2, sticky="w", pady=px(3))
            sw = tk.Label(cell, bg=globals()[key], width=4, cursor="hand2", highlightthickness=1,
                          highlightbackground=BORDER)
            sw.pack(side="left")
            sw.bind("<Button-1>", lambda e, k=key: self._pick_color(k))
            tk.Label(cell, text=label, bg=SURFACE, fg=TEXT, font=font(10)).pack(side="left", padx=px(10))
            tk.Label(cell, text=globals()[key] + ("  (custom)" if key in custom else ""), bg=SURFACE,
                     fg=MUTED, font=font(9)).pack(side="left")

        # font, size, logo
        c3 = card(page)
        c3.pack(fill="x", pady=(0, px(12)))
        tk.Label(c3, text="Text and logo", bg=SURFACE, fg=TEXT, font=font(12, "bold")).pack(
            anchor="w", padx=px(18), pady=(px(14), px(8)))
        r3 = tk.Frame(c3, bg=SURFACE)
        r3.pack(anchor="w", padx=px(18), pady=(0, px(14)))
        tk.Label(r3, text="Font", bg=SURFACE, fg=TEXT, font=font(10)).pack(side="left")
        self.v_font = tk.StringVar(value=self.store.setting("font_family") or "Segoe UI")
        cb = ttk.Combobox(r3, values=FONT_CHOICES, textvariable=self.v_font, state="readonly", width=14)
        cb.pack(side="left", padx=(px(8), px(18)))
        cb.bind("<<ComboboxSelected>>", lambda e: self._look_changed())
        tk.Label(r3, text="Text size", bg=SURFACE, fg=TEXT, font=font(10)).pack(side="left")
        self.v_fpct = tk.StringVar(value=str(self.store.setting("font_pct") or 100))
        sp = ttk.Spinbox(r3, from_=80, to=140, increment=5, width=5, textvariable=self.v_fpct,
                         command=self._look_changed)
        sp.pack(side="left", padx=(px(8), px(2)))
        sp.bind("<Return>", lambda e: self._look_changed())
        sp.bind("<FocusOut>", lambda e: self._look_changed())
        tk.Label(r3, text="%", bg=SURFACE, fg=MUTED, font=font(9)).pack(side="left", padx=(0, px(18)))
        tk.Label(r3, text="Logo", bg=SURFACE, fg=TEXT, font=font(10)).pack(side="left")
        self.v_logo = tk.StringVar(value=self.store.setting("logo") or "Default")
        lg = ttk.Combobox(r3, values=LOGO_CHOICES, textvariable=self.v_logo, state="readonly", width=8)
        lg.pack(side="left", padx=px(8))
        lg.bind("<<ComboboxSelected>>", lambda e: self._look_changed())

        # overlay
        c4 = card(page)
        c4.pack(fill="x")
        tk.Label(c4, text="Stream overlay", bg=SURFACE, fg=TEXT, font=font(12, "bold")).pack(
            anchor="w", padx=px(18), pady=(px(14), px(6)))
        self.v_overlay = tk.BooleanVar(value=False)
        ttk.Checkbutton(c4, text="Show In-Game / Stream Stats Overlay", variable=self.v_overlay,
                        style="Dark.TCheckbutton", command=self._toggle_overlay).pack(anchor="w", padx=px(18))
        r4 = tk.Frame(c4, bg=SURFACE)
        r4.pack(anchor="w", padx=px(18), pady=(px(10), px(14)))
        tk.Label(r4, text="Overlay opacity", bg=SURFACE, fg=TEXT, font=font(10)).pack(side="left")
        self.v_opacity = tk.IntVar(value=int(self.store.setting("overlay_opacity") or 90))
        sc = ttk.Scale(r4, from_=30, to=100, orient="horizontal", length=px(220), variable=self.v_opacity,
                       command=self._opacity_live)
        sc.pack(side="left", padx=px(10))
        sc.bind("<ButtonRelease-1>", lambda e: self.store.set_setting("overlay_opacity", int(self.v_opacity.get())))
        self.lbl_opacity = tk.Label(r4, text=f"{self.v_opacity.get()}%", bg=SURFACE, fg=MUTED, font=font(9))
        self.lbl_opacity.pack(side="left")

    def _set_preset(self, name):
        self.store.set_setting("theme", name)
        self.store.set_setting("custom_colors", {})
        self._rebuild_soon()

    def _reset_colors(self):
        self.store.set_setting("custom_colors", {})
        self._rebuild_soon()

    def _pick_color(self, key):
        rgb, hexv = colorchooser.askcolor(color=globals()[key], parent=self.root, title="Pick a color")
        if not hexv:
            return
        custom = dict(self.store.setting("custom_colors") or {})
        custom[key] = hexv.lower()
        self.store.set_setting("custom_colors", custom)
        self._rebuild_soon()

    def _look_changed(self):
        family = self.v_font.get() if self.v_font.get() in FONT_CHOICES else "Segoe UI"
        try:
            pct = max(80, min(140, int(self.v_fpct.get())))
        except ValueError:
            pct = int(self.store.setting("font_pct") or 100)
        logo = self.v_logo.get() or "Default"
        if (family, pct, logo) == (self.store.setting("font_family"), self.store.setting("font_pct"),
                                   self.store.setting("logo")):
            return
        self.store.set_setting("font_family", family)
        self.store.set_setting("font_pct", pct)
        self.store.set_setting("logo", logo)
        self._rebuild_soon()

    def _opacity_live(self, value):
        v = int(float(value))
        self.lbl_opacity.config(text=f"{v}%")
        if self.overlay_win and self.overlay_win.winfo_exists():
            self.overlay_win.set_opacity(v)

    def _toggle_overlay(self):
        if self.v_overlay.get():
            if not self.overlay_win or not self.overlay_win.winfo_exists():
                self.overlay_win = StatsOverlay(self.root, self.store)
        else:
            if self.overlay_win and self.overlay_win.winfo_exists():
                self.overlay_win.destroy()
                self.overlay_win = None

    # ------------------------------------------------------------ update checker

    def _check_updates(self, manual=False):
        def work():
            try:
                res, err = fetch_latest_version(), None
            except Exception as e:
                res, err = None, f"{type(e).__name__}: {e}"
            self.events.put(("update", (res, err, manual)))
        threading.Thread(target=work, daemon=True).start()

    def _on_update(self, res, err, manual):
        if err:
            if manual:
                messagebox.showwarning("Chest Tracker", f"Could not check for updates.\n\n{err}", parent=self.root)
            return
        if not res:
            if manual:
                messagebox.showinfo("Chest Tracker", "No published version was found on GitHub yet.",
                                    parent=self.root)
            return
        tag, url = res
        if parse_version(tag) > parse_version(APP_VERSION):
            self.update_info = (tag, url)
            self._show_update_banner()
            if manual or not self._update_prompted:
                self._update_prompted = True
                if messagebox.askyesno(
                        "Update available",
                        f"A newer version of Chest Tracker is available.\n\n"
                        f"Your version: v{APP_VERSION}\nLatest version: {tag}\n\n"
                        f"Open the download page now?", parent=self.root):
                    webbrowser.open(url)
        else:
            self.update_info = None
            self._show_update_banner()
            if manual:
                messagebox.showinfo("Chest Tracker", f"You are up to date (v{APP_VERSION}).", parent=self.root)

    def _show_update_banner(self):
        lbl = getattr(self, "update_lbl", None)
        if lbl is None or not lbl.winfo_exists():
            return
        if self.update_info:
            lbl.config(text=f"\u2B06  Update available: {self.update_info[0]}")
            if not lbl.winfo_manager():
                lbl.pack(side="right", padx=(0, px(10)), after=self.pill)
        else:
            lbl.pack_forget()

    def _open_update(self):
        if self.update_info:
            webbrowser.open(self.update_info[1])

    def _updates_changed(self):
        self.store.set_setting("check_updates", bool(self.v_updates.get()))

    # ------------------------------------------------------------ notifications

    def _notify_changed(self):
        self.store.set_setting("notify", bool(self.v_notify.get()))

    def _notify(self, title, text):
        desktop_notify(title, text, lambda t, x: self.events.put(("popup", (t, x))))

    def _popup(self, title, text):
        win = tk.Toplevel(self.root)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.configure(bg=ACCENT)
        inner = tk.Frame(win, bg=SURFACE)
        inner.pack(padx=2, pady=2)
        tk.Label(inner, text=title, bg=SURFACE, fg=ACCENT, font=font(11, "bold"), padx=px(16)).pack(
            anchor="w", pady=(px(10), 0))
        tk.Label(inner, text=text, bg=SURFACE, fg=TEXT, font=font(10), padx=px(16)).pack(
            anchor="w", pady=(0, px(10)))
        for w in (win, inner, *inner.winfo_children()):
            w.bind("<Button-1>", lambda e: win.destroy())
        win.update_idletasks()
        x = win.winfo_screenwidth() - win.winfo_reqwidth() - px(24)
        y = win.winfo_screenheight() - win.winfo_reqheight() - px(64)
        win.geometry(f"+{x}+{y}")
        win.after(8000, win.destroy)

    def _notify_match(self, r):
        n = self.store.replay_count(r)
        total = sum(self.store.days().values())
        team = self.store.replay_team(r)
        extra = f" (incl. {team} from teammates)" if team else ""
        self._notify("Match counted", f"{n} chest{'s' if n != 1 else ''} this match{extra}  -  {total:,} total  -  "
                                      f"token chance {fmt_pct(token_chance(total))}")

    def _destroyed_changed(self):
        self.store.set_setting("count_destroyed", bool(self.v_destroyed.get()))
        self.refresh()

    def _team_changed(self):
        self.store.set_setting("count_team", bool(self.v_team.get()))
        self.refresh()

    def _days_changed(self):
        try:
            v = max(0, min(365, int(self.v_days.get())))
        except ValueError:
            v = int(self.store.setting("delete_days") or 0)
        self.v_days.set(str(v))
        self.store.set_setting("delete_days", v)

    def _correct(self, n):
        self.store.add_manual(n)
        self.refresh()

    def save_report(self):
        have = os.path.isdir(DEMOS)
        n_files = len([f for f in os.listdir(DEMOS) if f.lower().endswith(".replay")]) if have else 0
        lines = [f"Chest Tracker {APP_VERSION}  reader v{READER_VERSION}  {dt.datetime.now():%Y-%m-%d %H:%M}",
                 f"Replays folder exists: {have}   .replay files on disk: {n_files}", ""]
        items = sorted(self.store.replay_list().items(), key=lambda kv: kv[1].get("mtime", 0), reverse=True)[:5]
        lines.append("---- last matches (team detection) ----")
        for name, r in items:
            d = r.get("diag") or {}
            lines.append(f"{name}: mine={r.get('chests')} team={r.get('team')} team_known={r.get('team_known')} "
                         f"player_state_exports={d.get('player_state_exports')} "
                         f"states_with_team={d.get('states_with_team')} my_team_index={d.get('my_team_index')} "
                         f"team_pawns={d.get('team_pawns')}")
            ex = r.get("extra") or {}
            lines.append(f"    player_data_count={ex.get('player_data_count')} players={[(p.get('name'), p.get('skin'), p.get('chests')) for p in (r.get('players') or [])]}")
            if ex.get("player_data_props"):
                lines.append(f"    player data properties: {ex.get('player_data_props')}")
            for dump in (ex.get("player_dump") or []):
                lines.append(f"    {dump}")
            props = (r.get("extra") or {}).get("player_state_props")
            if props:
                lines.append(f"    player state properties: {props}")
        lines.append("")
        try:
            with open(LOG_FILE, encoding="utf-8", errors="replace") as f:
                tail = f.read().splitlines()[-60:]
        except OSError:
            tail = ["(no log yet)"]
        lines += ["---- setup.log (last 60 lines) ----"] + tail
        os.makedirs(DATA_DIR, exist_ok=True)
        path = os.path.join(DATA_DIR, "diagnostics.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        open_path(path)

    def _rescan(self):
        self.store.mark_all_pending()
        self._set_status("busy", "Re-scanning every match still on disk...")

    def open_demos(self):
        if os.path.isdir(DEMOS):
            open_path(DEMOS)
        else:
            messagebox.showinfo("Chest Tracker", "The Fortnite replays folder does not exist yet.", parent=self.root)

    def _set_status(self, level, text):
        color = {"ok": GOOD, "busy": ACCENT, "warn": WARN, "error": BAD}.get(level, MUTED)
        short = {"ok": "Watching", "busy": "Working", "warn": "Waiting", "error": "Problem"}.get(level, "Starting")
        self.pill.config(text=f"\u25CF  {short}", fg=color)
        self.status_text = text
        self.status_level = level
        self.lbl_last_title.config(text="LAST MATCH" if level == "ok" else "STATUS")
        if level != "ok":
            self.lbl_last.config(text=text, fg=color if level in ("warn", "error") else TEXT)
        else:
            self._show_last()

    def _open_sim(self):
        total = sum(self.store.days().values())
        theme = dict(BG=BG, SURFACE=SURFACE, SURFACE2=SURFACE2, BORDER=BORDER, TEXT=TEXT, MUTED=MUTED,
                     ACCENT=ACCENT, GOOD=GOOD, HOVER=HOVER, ON_ACCENT=ON_ACCENT)
        win = getattr(self, "sim_win", None)
        if win is not None and win.winfo_exists():
            win.lift()
            return
        self.sim_win = TokenSimulator(self.root, TOKEN_ODDS, min(max(total, 1), MAX_ROLLS), theme, SCALE)

    def _token_info(self):
        total = sum(self.store.days().values())
        keep = (1 - 1 / TOKEN_ODDS) ** total
        half = math.ceil(math.log(0.5) / math.log(1 - 1 / TOKEN_ODDS))
        messagebox.showinfo(
            "Shop token chance",
            f"Every chest is its own roll with a 1 in {TOKEN_ODDS:,} chance.\n\n"
            f"Chance that none of your {total:,} chests dropped one: {fmt_pct(keep)}\n"
            f"Chance that at least one did: {fmt_pct(1 - keep)}\n"
            f"A 50% chance takes about {half:,} chests.",
            parent=self.root)

    def _show_last(self):
        r = self.last
        if r and r.get("ok"):
            n = self.store.replay_count(r)
            txt = f"{r['time']}  -  {n} chest{'s' if n != 1 else ''}"
            bits = []
            if self.store.setting("count_destroyed"):
                bits.append(f"{r['opened']} opened, {r['destroyed']} destroyed")
            team = self.store.replay_team(r)
            if team:
                bits.append(f"{team} from teammates")
            if bits:
                txt += "   (" + ", ".join(bits) + ")"
            self.lbl_last.config(text=txt, fg=TEXT)
        else:
            self.lbl_last.config(text=getattr(self, "status_text", "") or "Nothing counted yet", fg=MUTED)

    def _pump(self):
        try:
            while True:
                kind, data = self.events.get_nowait()
                if kind == "status":
                    self._set_status(*data)
                elif kind == "replay":
                    self.last = data
                    self.refresh()
                    if data.get("ok") and (data.get("chests") or data.get("team")):
                        self.lbl_total.config(fg=HOVER)
                        self.root.after(250, lambda: self.lbl_total.config(fg=ACCENT))
                    if data.get("fresh") and data.get("ok") and self.store.setting("notify"):
                        self._notify_match(data)
                elif kind == "popup":
                    self._popup(*data)
                elif kind == "update":
                    self._on_update(*data)
        except queue.Empty:
            pass
        self.root.after(200, self._pump)

    def _minute(self):
        self.refresh()
        self.root.after(60000, self._minute)

    def refresh(self):
        days = self.store.days()
        total = sum(days.values())
        today = dt.date.today()
        self.lbl_total.config(text=f"{total:,}")
        n = self.store.matches_counted()
        mn, mtotal, mbest, _ = self.store.match_stats()
        line = f"across {n} match{'es' if n != 1 else ''}"
        if mn:
            line += f"\n{mtotal / mn:.1f} per match  -  best match {mbest:,}"
        self.lbl_matches.config(text=line)
        self.lbl_token.config(text=fmt_pct(token_chance(total)) if total > 0 else "-")
        nxt = self._next_milestone(total)
        if nxt:
            per_match, _ = self._rates()
            m = f"  (~{math.ceil(nxt[2] / per_match):,} matches)" if per_match > 0 else ""
            self.lbl_next.config(text=f"Next: {nxt[0]:.0%} in {nxt[2]:,} chests{m}")
        else:
            self.lbl_next.config(text="All milestones reached")

        t = days.get(today_key(), 0)
        week = sum(days.get((today - dt.timedelta(days=i)).isoformat(), 0) for i in range(7))
        self.stat["today"][0].config(text=f"{t:,}")
        self.stat["today"][1].config(text="chests so far")
        self.stat["week"][0].config(text=f"{week:,}")
        self.stat["week"][1].config(text="including today")
        if days:
            best = max(days, key=days.get)
            self.stat["avg"][0].config(text=f"{total / len(days):.1f}")
            self.stat["avg"][1].config(text=f"over {len(days)} day{'s' if len(days) != 1 else ''} played")
            self.stat["best"][0].config(text=f"{days[best]:,}")
            self.stat["best"][1].config(text=dt.date.fromisoformat(best).strftime("%b %d, %Y").replace(" 0", " "))
        else:
            for k in ("avg", "best"):
                self.stat[k][0].config(text="-")
                self.stat[k][1].config(text="no data yet")
        self.lbl_manual.config(text=f"Today's manual adjustment: {self.store.manual_today():+d}")

        # Update overlay window if active
        if self.overlay_win and self.overlay_win.winfo_exists():
            self.overlay_win.update_stats()

        if self.lbl_last_title.cget("text") == "LAST MATCH":
            self._show_last()
        if "matches" in self.pages and self.pages["matches"].winfo_ismapped():
            self.fill_matches()
        if "milestones" in self.pages and self.pages["milestones"].winfo_ismapped():
            self.fill_milestones()
        self.draw_chart()

    def _series(self):
        days = self.store.days()
        today = dt.date.today()
        seq = [today - dt.timedelta(days=i) for i in range(13, -1, -1)]
        return seq, [days.get(d.isoformat(), 0) for d in seq]

    def _geometry(self, w, h):
        pad_x, top, bottom = px(8), px(22), px(22)
        slot = (w - 2 * pad_x) / 14
        return pad_x, top, bottom, slot

    def draw_chart(self):
        cv = self.cv
        cv.delete("all")
        w, h = cv.winfo_width(), cv.winfo_height()
        if w < 60 or h < 60:
            return
        seq, vals = self._series()
        mx = max(1, max(vals))
        pad_x, top, bottom, slot = self._geometry(w, h)
        bw = slot * 0.58
        for gy in (0.5, 1.0):
            y = h - bottom - (h - top - bottom) * gy
            cv.create_line(pad_x, y, w - pad_x, y, fill=SURFACE2)
        for i, (d, v) in enumerate(zip(seq, vals)):
            cx = pad_x + slot * i + slot / 2
            bh = (h - top - bottom) * v / mx
            is_today = i == 13
            color = ACCENT if is_today else (VIOLET if self.hover == i else ACCENT_DIM)
            base = h - bottom
            if v:
                cv.create_rectangle(cx - bw / 2, base - bh, cx + bw / 2, base, fill=color, width=0)
                cv.create_text(cx, base - bh - px(9), text=str(v), fill=TEXT if is_today else MUTED, font=font(8))
            else:
                cv.create_rectangle(cx - bw / 2, base - px(2), cx + bw / 2, base, fill=SURFACE2, width=0)
            cv.create_text(cx, h - px(10), text="today" if is_today else str(d.day),
                           fill=ACCENT if is_today else MUTED, font=font(8))

    def _chart_hover(self, e):
        w, h = self.cv.winfo_width(), self.cv.winfo_height()
        pad_x, _, _, slot = self._geometry(w, h)
        i = int((e.x - pad_x) // slot)
        self._set_hover(i if 0 <= i < 14 else None)

    def _set_hover(self, i):
        if i == self.hover:
            return
        self.hover = i
        if i is None:
            self.lbl_hover.config(text="")
        else:
            seq, vals = self._series()
            self.lbl_hover.config(text=f"{seq[i].strftime('%a %b %d').replace(' 0', ' ')}:  "
                                       f"{vals[i]} chest{'s' if vals[i] != 1 else ''}")
        self.draw_chart()


def main():
    if sys.platform == "win32":
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ChestTracker.App")
        except Exception:
            pass
    root = tk.Tk()
    App(root)
    root.mainloop()


def __main__():
    main()


if __name__ == "__main__":
    main()
