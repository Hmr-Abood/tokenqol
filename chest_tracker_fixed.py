"""
Chest Tracker for Fortnite - Windows desktop app.

Counts the chests you loot in Fortnite by reading the replays (.replay) the game saves after each match.
Every chest in a replay records which player opened it, so only YOUR chests are counted.
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
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
import urllib.error
import urllib.request
import webbrowser
import zipfile
from tkinter import ttk, messagebox

APP_VERSION = "1.3"

# ---------------------------------------------------------------- paths & constants

LOCAL = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
ROAMING = os.environ.get("APPDATA") or os.path.expanduser("~")
DATA_DIR = os.path.join(ROAMING, "ChestTracker")
DATA_FILE = os.path.join(DATA_DIR, "data.json")
TOOLS = os.path.join(LOCAL, "ChestTracker")
SRC_DIR = os.path.join(TOOLS, "reader_src")
LOG_FILE = os.path.join(TOOLS, "setup.log")
DEMOS = os.path.join(LOCAL, "FortniteGame", "Saved", "Demos")

REPO_SHA = "59515cf4781e60d2c14ba39d8dcab1d7fb986f17"
REPO_ZIP = f"https://codeload.github.com/Cristiano3120/MoreFortniteReplayDecompression/zip/{REPO_SHA}"
DOTNET_INSTALL = "https://dot.net/v1/dotnet-install.ps1"

READER_VERSION = 6
BIN_DIR = os.path.join(TOOLS, f"reader_v{READER_VERSION}")
READER_DLL = os.path.join(BIN_DIR, "ChestReplayReader.dll")

DEFAULT_TYPES = [
    "/Game/Building/ActorBlueprints/Containers/Tiered_Chest_Athena.Tiered_Chest_Athena_C",
    "/Game/Building/ActorBlueprints/Containers/Tiered_Chest_Athena_FactionChest_NoLocks.Tiered_Chest_Athena_FactionChest_NoLocks_C",
]

NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
QUIET_SECONDS = 90
READ_TIMEOUT = 600

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

THEMES = {
    "classic": dict(BG="#0e1014", SURFACE="#161a21", SURFACE2="#1d222b", BORDER="#2a303b", TEXT="#e9ecf3",
                    MUTED="#8a93a6", ACCENT="#36d6c8", ACCENT_DIM="#1d7f78", VIOLET="#9d8cff", GOOD="#4ade80",
                    WARN="#fbbf24", BAD="#f87171", HOVER="#6ff0e4", ON_ACCENT="#06201e", LOGO="\u25C6"),
    "pirate": dict(BG="#0a1420", SURFACE="#112131", SURFACE2="#1a2e43", BORDER="#2d4560", TEXT="#f4ead5",
                   MUTED="#9fb0bd", ACCENT="#e9b440", ACCENT_DIM="#8f6b1c", VIOLET="#e4604f", GOOD="#5fd39a",
                   WARN="#f2a33a", BAD="#f2705f", HOVER="#f7cd6e", ON_ACCENT="#2a1b04", LOGO="\u2620"),
}


def apply_theme(name):
    globals().update(THEMES.get(name) or THEMES["classic"])


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
    return ("Segoe UI", size, weight)


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
        return ("Segoe UI", size, weight)

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
        self.attributes("-alpha", 0.90)
        self.configure(bg=BORDER)
        
        self._x = 0
        self._y = 0
        
        container = tk.Frame(self, bg=SURFACE)
        container.pack(fill="both", expand=True, padx=1, pady=1)
        
        # Header / Drag handle bar
        header = tk.Frame(container, bg=SURFACE2, cursor="fleur")
        header.pack(fill="x", padx=4, pady=4)
        tk.Label(header, text="◆ CHEST TRACKER OVERLAY", bg=SURFACE2, fg=ACCENT, font=font(8, "bold")).pack(side="left", padx=6, pady=4)
        close_btn = tk.Label(header, text="×", bg=SURFACE2, fg=MUTED, font=font(10, "bold"), cursor="hand2")
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
        
        # Overall Stats
        tk.Label(body, text="TOTAL CHESTS", bg=SURFACE, fg=MUTED, font=font(7, "bold")).pack(anchor="w")
        self.lbl_total = tk.Label(body, text="0", bg=SURFACE, fg=ACCENT, font=font(24, "bold"))
        self.lbl_total.pack(anchor="w")
        
        self.lbl_today = tk.Label(body, text="Today: 0", bg=SURFACE, fg=TEXT, font=font(9))
        self.lbl_today.pack(anchor="w", pady=(1, 0))
        
        self.lbl_token = tk.Label(body, text="Token Chance: -", bg=SURFACE, fg=VIOLET, font=font(9, "bold"))
        self.lbl_token.pack(anchor="w", pady=(1, 4))

        # Divider line
        tk.Frame(body, bg=BORDER, height=1).pack(fill="x", pady=4)

        # Session & Last Match Section
        tk.Label(body, text="CURRENT SESSION & LAST MATCH", bg=SURFACE, fg=MUTED, font=font(7, "bold")).pack(anchor="w", pady=(2, 0))
        self.lbl_session = tk.Label(body, text="Session Matches: 0", bg=SURFACE, fg=TEXT, font=font(9))
        self.lbl_session.pack(anchor="w", pady=(1, 0))

        self.lbl_last_match = tk.Label(body, text="Last Match: None", bg=SURFACE, fg=MUTED, font=font(8), wraplength=200, justify="left")
        self.lbl_last_match.pack(anchor="w", pady=(2, 0))

        # Initial geometry position (top-right corner of screen)
        self.update_idletasks()
        w_w = 230
        w_h = 210
        x = self.winfo_screenwidth() - w_w - 40
        y = 40
        self.geometry(f"{w_w}x{w_h}+{x}+{y}")
        self.update_stats()

    def _start_move(self, event):
        self._x = event.x
        self._y = event.y

    def _do_move(self, event):
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

        # Fetch last match info from store if available
        items = sorted(self.store.replay_list().items(), key=lambda kv: kv[1].get("mtime", 0), reverse=True)
        if items:
            _, r = items[0]
            if r.get("ok"):
                n = self.store.replay_count(r)
                time_str = r.get('time', '')
                self.lbl_last_match.config(text=f"Last ({time_str}): {n} chests ({r.get('opened',0)}op, {r.get('destroyed',0)}dst)", fg=TEXT)
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

    public void Resolve()
    {
        DetectMyPawns();

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

        var list = Chests.Values.Where(x => x.Owner != 0 && IsMine(x.Owner)).OrderBy(x => x.Time).ToList();
        for (var i = 0; i < list.Count; i++)
        {
            if (list[i].Duplicate) continue;
            for (var j = i + 1; j < list.Count; j++)
            {
                var a = list[i]; var b = list[j];
                if (b.Duplicate) continue;
                if (b.Time - a.Time > 10f) break;
                var sameSpot = a.Loc != null && b.Loc != null && Dist(a.Loc, b.Loc) < 350;
                var sameMoment = (a.Loc == null || b.Loc == null) && a.Type == b.Type && b.Time - a.Time < 1.5f;
                if (sameSpot || sameMoment) b.Duplicate = true;
            }
        }
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
        var who = c.Owner == 0 ? "none" : r.IsMine(c.Owner) ? "ME" : "other";
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

        return new
        {
            file = Path.GetFileName(path),
            ok = true,
            duration_sec = (replay.Info?.LengthInMs ?? 0) / 1000,
            mine = mine.Count,
            opened = mine.Count(c => !c.AsDestroyed),
            destroyed = mine.Count(c => c.AsDestroyed),
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


# ---------------------------------------------------------------- data store

class Store:
    def __init__(self):
        self.lock = threading.Lock()
        self.manual, self.replays = {}, {}
        self.reader_version = 0
        self.settings = {"count_destroyed": True, "delete_days": 3, "chest_types": [], "help_seen": False,
                         "theme": "pirate", "notify": True}
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

    def replay_count(self, r):
        if not r.get("ok"):
            return 0
        return int(r.get("chests", 0)) if self.settings.get("count_destroyed", True) else int(r.get("opened", 0))

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
            info = {
                "ok": bool(r.get("ok")),
                "chests": int(r.get("mine", 0)) if r.get("ok") else 0,
                "opened": int(r.get("opened", 0)),
                "destroyed": int(r.get("destroyed", 0)),
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

def dark_titlebar(win):
    if sys.platform != "win32":
        return
    try:
        win.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
        val = ctypes.c_int(1)
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
        super().__init__(parent, text=text, bg=BG, fg=MUTED, font=font(11, "bold"), padx=px(14), pady=px(8),
                         cursor="hand2")
        self.command = command
        self.active = False
        self.bind("<Button-1>", lambda e: self.command())
        self.bind("<Enter>", lambda e: self.config(fg=TEXT))
        self.bind("<Leave>", lambda e: self.config(fg=ACCENT if self.active else MUTED))

    def set_active(self, on):
        self.active = on
        self.config(fg=ACCENT if on else MUTED)


CREDITS_NAME = "hmr_abood"
CREDITS_LINKS = (
    ("TikTok", "https://www.tiktok.com/@hmr_aboodyt"),
    ("GitHub", "https://github.com/Hmr-Abood"),
)

HELP_TEXT = (
    "1. In Fortnite: Settings > Game > Replays > Record Replays (Battle Royale) = On.\n\n"
    "2. Keep Chest Tracker open (minimized is fine) and play.\n\n"
    "3. About 2 minutes after each match ends, its chests are added to your total and to today.\n\n"
    "Counted: every chest you open and, if enabled, the chests you break. Chests opened by other "
    "players are never counted.\n\n"
    "Use the Stream Overlay feature in Settings to display live floating stats on top of your game!"
)


# ---------------------------------------------------------------- application

class App:
    def __init__(self, root, start_worker=True):
        global SCALE
        self.root = root
        SCALE = max(1.0, root.winfo_fpixels("1i") / 96.0)
        self.store = Store()
        apply_theme(self.store.setting("theme"))
        self.events = queue.Queue()
        self.last = None
        self.hover = None
        self.page_key = "dashboard"
        self.status_level = None
        self.overlay_win = None

        root.title("Chest Tracker")
        root.geometry(f"{px(900)}x{px(760)}")
        root.minsize(px(820), px(690))
        self._build_ui()

        self.worker = Worker(self.store, self.events)
        if start_worker:
            self.worker.start()
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.refresh()
        root.after(200, self._pump)
        root.after(60000, self._minute)
        dark_titlebar(root)
        if start_worker and not self.store.setting("help_seen"):
            self.store.set_setting("help_seen", True)
            root.after(700, lambda: messagebox.showinfo("Welcome to Chest Tracker", HELP_TEXT, parent=self.root))

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
        self._build_credits()
        self.show(self.page_key)

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

    def _build_header(self):
        h = tk.Frame(self.root, bg=BG)
        h.pack(fill="x", padx=px(22), pady=(px(16), px(10)))
        logo = tk.Frame(h, bg=BG)
        logo.pack(side="left")
        tk.Label(logo, text=LOGO, bg=BG, fg=ACCENT, font=font(16, "bold")).pack(side="left")
        tk.Label(logo, text=" Chest", bg=BG, fg=TEXT, font=font(16, "bold")).pack(side="left")
        tk.Label(logo, text="Tracker", bg=BG, fg=ACCENT, font=font(16, "bold")).pack(side="left")

        nav = tk.Frame(h, bg=BG)
        nav.pack(side="left", padx=px(26))
        self.nav = {}
        for key, label in (("dashboard", "Dashboard"), ("matches", "Matches"), ("milestones", "Milestones"),
                           ("settings", "Settings"), ("credits", "Credits")):
            b = NavButton(nav, label, lambda k=key: self.show(k))
            b.pack(side="left")
            self.nav[key] = b

        self.pill = tk.Label(h, text="\u25CF  Starting", bg=SURFACE, fg=MUTED, font=font(9, "bold"),
                             padx=px(12), pady=px(5))
        self.pill.pack(side="right")

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
        c = card(page)
        c.pack(fill="both", expand=True)
        cols = ("when", "total", "opened", "destroyed", "status")
        self.tv = ttk.Treeview(c, columns=cols, show="headings")
        spec = {"when": ("MATCH", 170, "w"), "total": ("CHESTS", 90, "e"), "opened": ("OPENED", 90, "e"),
                "destroyed": ("DESTROYED", 110, "e"), "status": ("STATUS", 260, "w")}
        for k, (t, w, a) in spec.items():
            self.tv.heading(k, text=t, anchor=a)
            self.tv.column(k, width=px(w), anchor=a, stretch=(k == "status"))
        sb = ttk.Scrollbar(c, orient="vertical", command=self.tv.yview)
        self.tv.configure(yscrollcommand=sb.set)
        self.tv.pack(side="left", fill="both", expand=True, padx=(px(2), 0), pady=px(2))
        sb.pack(side="right", fill="y")
        self.tv.tag_configure("bad", foreground=BAD)
        self.tv.tag_configure("wait", foreground=WARN)

    def fill_matches(self):
        self.tv.delete(*self.tv.get_children())
        items = sorted(self.store.replay_list().items(),
                       key=lambda kv: (kv[1].get("day", ""), kv[1].get("time", "")), reverse=True)
        for _, r in items:
            when = f"{r.get('day', '')}  {r.get('time', '')}".strip()
            tag = ""
            if r.get("pending"):
                status, tag = "Waiting to be re-read", "wait"
            elif not r.get("ok"):
                status, tag = f"Error: {r.get('error') or '?'}", "bad"
            elif not r.get("recorder_found", True):
                status, tag = "Warning: recording player not found", "wait"
            else:
                status = "OK" if r.get("chests") else self._zero_reason(r)
            if r.get("ok"):
                nums = (self.store.replay_count(r), r.get("opened", 0), r.get("destroyed", 0))
            else:
                nums = ("-", "-", "-")
            self.tv.insert("", "end", values=(when, *nums, status), tags=(tag,) if tag else ())

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
            link = tk.Label(row, text=url, bg=SURFACE, fg=VIOLET, font=("Segoe UI", 11, "underline"),
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
        tk.Label(c_ui, text="Look and Alerts", bg=SURFACE, fg=TEXT, font=font(12, "bold")).pack(
            anchor="w", padx=px(18), pady=(px(14), px(6)))
        self.v_pirate = tk.BooleanVar(value=self.store.setting("theme") == "pirate")
        ttk.Checkbutton(c_ui, text="Pirate theme", variable=self.v_pirate, style="Dark.TCheckbutton",
                        command=self._theme_changed).pack(anchor="w", padx=px(18))
        
        # --- OVERLAY TOGGLE ---
        self.v_overlay = tk.BooleanVar(value=False)
        ttk.Checkbutton(c_ui, text="Show In-Game / Stream Stats Overlay", variable=self.v_overlay,
                        style="Dark.TCheckbutton", command=self._toggle_overlay).pack(anchor="w", padx=px(18), pady=(px(6), 0))

        self.v_notify = tk.BooleanVar(value=bool(self.store.setting("notify")))
        ttk.Checkbutton(c_ui, text="Show desktop notification when match is counted",
                        variable=self.v_notify, style="Dark.TCheckbutton",
                        command=self._notify_changed).pack(anchor="w", padx=px(18), pady=(px(6), 0))
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

        c4 = card(page)
        c4.pack(fill="x")
        tk.Label(c4, text="How it works", bg=SURFACE, fg=TEXT, font=font(12, "bold")).pack(anchor="w", padx=px(18), pady=(px(14), px(4)))
        tk.Label(c4, text=HELP_TEXT, bg=SURFACE, fg=MUTED, font=font(9), justify="left", anchor="w",
                 wraplength=px(720)).pack(anchor="w", padx=px(18), pady=(0, px(14)))

    def _toggle_overlay(self):
        if self.v_overlay.get():
            if not self.overlay_win or not self.overlay_win.winfo_exists():
                self.overlay_win = StatsOverlay(self.root, self.store)
        else:
            if self.overlay_win and self.overlay_win.winfo_exists():
                self.overlay_win.destroy()
                self.overlay_win = None

    def _theme_changed(self):
        self.store.set_setting("theme", "pirate" if self.v_pirate.get() else "classic")
        apply_theme(self.store.setting("theme"))
        for w in self.root.winfo_children():
            w.destroy()
        self._build_ui()
        self.refresh()
        if self.status_level:
            self._set_status(self.status_level, self.status_text)

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
        self._notify("Match counted", f"{n} chest{'s' if n != 1 else ''} this match  -  {total:,} total  -  "
                                      f"token chance {fmt_pct(token_chance(total))}")

    def _destroyed_changed(self):
        self.store.set_setting("count_destroyed", bool(self.v_destroyed.get()))
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
            if self.store.setting("count_destroyed"):
                txt += f"   ({r['opened']} opened, {r['destroyed']} destroyed)"
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
                    if data.get("ok") and data.get("chests"):
                        self.lbl_total.config(fg="#ffffff")
                        self.root.after(250, lambda: self.lbl_total.config(fg=ACCENT))
                    if data.get("fresh") and data.get("ok") and self.store.setting("notify"):
                        self._notify_match(data)
                elif kind == "popup":
                    self._popup(*data)
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