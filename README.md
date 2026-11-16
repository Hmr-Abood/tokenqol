# TokenQOL
### Fortnite Chest Tracker — all you need for the Pirate Shop grind.

Track every chest, understand your Pirate Shop odds, and keep your progress visible while you play or stream.

[![Download](https://img.shields.io/badge/Download-Latest%20Release-36d6c8?style=for-the-badge)](https://github.com/Hmr-Abood/tokenqol/releases/latest)
[![Platform](https://img.shields.io/badge/Platform-Windows-0078D4?style=for-the-badge&logo=windows)](https://www.microsoft.com/windows)
[![License](https://img.shields.io/badge/License-See%20Repository-lightgrey?style=for-the-badge)](LICENSE)

<img width="950" alt="TokenQOL application preview" src="https://github.com/user-attachments/assets/db258723-4120-49c6-b02f-0d265e4535e5" />

---

## What is TokenQOL?

**TokenQOL** is a Windows desktop companion for Fortnite players working toward Pirate Shop rewards. It reads your locally saved match replays and turns your chest openings into useful stats, probability estimates, and stream-ready overlays.

No more manually counting chests after every match.

## Features

### Chest tracking
- Automatically scans Fortnite replay files saved on your PC.
- Counts chests opened by you and tracks teammate chest activity.
- Separates chest totals by type: Normal, Rare, and Sprite.
- Keeps match history and cumulative statistics.
- View daily and weekly progress, matches counted, and playtime.
- Identifies match information such as game mode when available.

<img width="939" alt="Replay scanning and chest tracking" src="https://github.com/user-attachments/assets/077f88b3-619c-4fbe-ba56-7ea4fd0df4c1" />

<img width="910" alt="Chest count overview" src="https://github.com/user-attachments/assets/56d59895-dbe8-49d2-93b8-a214f1788c91" />

<img width="598" alt="Team chest statistics" src="https://github.com/user-attachments/assets/a9e3d4bd-8c1e-4bf8-a3a3-847a1db26015" />

### Pirate Shop odds & simulator
- Estimate your chance of receiving Pirate Shop Access.
- Simulate chest rolls and see the outcomes.
- Check how many rolls it takes to reach probability milestones.
- Track your progress toward your next milestone.
- Explore Treasure Hour information.

<img width="920" alt="Pirate Shop probability calculator" src="https://github.com/user-attachments/assets/f24aab25-6030-49cd-86e7-f20037be41d5" />

<img width="620" alt="Chest roll simulator" src="https://github.com/user-attachments/assets/57bdbefc-5790-4342-aa45-0d46f5a1efee" />

<img width="626" alt="Roll and reward results" src="https://github.com/user-attachments/assets/b9c294c4-82a1-4e94-9d03-722fb6ac5618" />

<img width="900" alt="Progress milestones" src="https://github.com/user-attachments/assets/96c90658-9f16-4241-a5c2-6f022dfcacb5" />

### Stream & game overlays
- Display live chest statistics in a separate overlay.
- Use the stream window with OBS Window Capture.
- Choose which statistics appear, including total chests, token chance, recent activity, and more.
- Adjust overlay appearance and background options.

<img width="918" alt="Customizable stream overlay" src="https://github.com/user-attachments/assets/969298d6-d30b-4588-a4ed-94ada35f83dc" />

<img width="261" alt="Overlay preview" src="https://github.com/user-attachments/assets/c6866821-c836-42d2-85e5-27f024caa3bf" />

### Make it yours
- Multiple built-in themes.
- Custom colors, fonts, and interface sizing.
- Personalize the look of your tracker and overlays.

<img width="890" alt="Application themes" src="https://github.com/user-attachments/assets/4194edd8-4412-49f6-9116-dadfc302f63c" />

---

## Getting started

### 1. Download
Head to the [**latest release**](https://github.com/Hmr-Abood/tokenqol/releases/latest) and download the available Windows release.

### 2. Extract and launch
Extract the downloaded ZIP file, then follow the included launch/setup instructions.

### 3. Save Fortnite replays
Make sure Fortnite match replays are being saved. The tracker reads the replay files stored locally on your PC.

### 4. Scan your matches
Open TokenQOL and scan your replay files. Your chest counts and match statistics will appear in the tracker.

### 5. Track your progress
Use the probability tools, milestones, simulator, and overlays to follow your Pirate Shop grind.

> **Tip:** New matches can only be analyzed when a replay file is available for that match.

## Pirate Shop probability

The probability calculator currently uses an estimated rate of:

**1 in 137,500 chests per roll**

The chance of receiving at least one reward across multiple rolls is calculated using:

`1 - (1 - 1 / 137500)^n`

where `n` is the number of chests.

This is a probability estimate, not a guarantee. Random outcomes can vary, and opening a certain number of chests does not guarantee a reward. Drop rates and reward availability may change.

## Safety & privacy

TokenQOL analyzes replay files that Fortnite has already saved on your computer.

It does **not**:
- Inject code into Fortnite.
- Read or modify Fortnite's game memory.
- Automate gameplay or player inputs.
- Modify Fortnite game files.

Your replay analysis is performed locally by the desktop application.

## Requirements

- Windows.
- Fortnite replay files saved locally.
- The files and dependencies provided with the release.

## Issues & feedback

Found a bug or have an idea? [Open an issue](https://github.com/Hmr-Abood/tokenqol/issues) and include as much detail as possible.

## Disclaimer

TokenQOL is an independent, community-made project. It is not affiliated with, endorsed by, or sponsored by Epic Games. Fortnite is a trademark of Epic Games, Inc.

---

<p align="center">
  Made for the Pirate Shop grind.
  <br />
  <a href="https://github.com/Hmr-Abood/tokenqol/releases/latest">Download TokenQOL</a>
  ·
  <a href="https://github.com/Hmr-Abood/tokenqol/issues">Report an issue</a>
</p>
