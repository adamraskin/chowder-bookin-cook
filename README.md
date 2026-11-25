# Chowder: Bookin' Cook (offline build)

Play the Cartoon Network Flash game *Chowder: Bookin' Cook* offline, in your
browser, with [Ruffle](https://ruffle.rs). All files are in this folder.
No internet connection is necessary.

## Play

1. Double-click `Play.bat`.
2. A console window starts a small local web server, and your browser opens
   <http://localhost:8642>.
3. Click once in the game to start the sound (browsers need a click first).
4. Close the console window to stop.

Requirements: Windows (PowerShell is part of Windows) and a modern browser.

## Why this build is necessary

1. **Preloader.** Current Ruffle (0.9.x) never binds the config component of
   the preloader (`game.swf`), so loading stops at 0%. The Ruffle 2024-06-01
   nightly does not have this problem, so this folder uses that build.
2. **Music bridge.** The game plays its music through an AS2 helper
   (`MgrMusicAS2.swf`) over `LocalConnection`. Ruffle cannot complete this
   AS3 <-> AS2 connection. The AS2 helper then retries in a loop that freezes
   the page, and the game does not start.

   `tools/build.py` patches `main.swf`: the game sends its music commands to
   the page through `ExternalInterface`, and `index.html` plays the music with
   Web Audio. The helper `MgrMusicAS2.swf` is not used and is not included.

## Files

| Path | Purpose |
|------|---------|
| `Play.bat` | Launcher |
| `serve.ps1` | Local web server (port 8642). `-NoBrowser` does not open the browser. |
| `index.html` | Runs the game in Ruffle and plays the music |
| `ruffle/` | Ruffle web build, nightly 2024-06-01 (MIT / Apache-2.0) |
| `game/main.orig.swf` | Original `main.swf` (input of the patch) |
| `game/main.swf` | Patched `main.swf` (made by `tools/build.py`) |
| `game/music/*.mp3` | Music, extracted from `MusicAS2Library.swf` |
| `tools/build.py` | Makes `game/main.swf` and `game/music/` from the original files |
| `tools/check.py` | Builds again and checks the result (CI runs this) |
| `tools/abcedit.py` | Small AVM2 bytecode editor used by `build.py` |
| `tools/disasm.py` | AVM2 disassembler, for debugging |
| `docs/PLAYING.md` | How to play, and notes for AI agents that play the game |

## Development

Python 3.9 or newer. No packages are necessary.

```sh
python tools/build.py   # rebuild game/main.swf and game/music/
python tools/check.py   # same checks as CI
```

Debug: open <http://localhost:8642/?debug>. The console output of the page
goes to `ruffle-log.txt` in this folder.

## Legal

The game files in `game/` are the property of their owners (Cartoon Network).
They are here only for preservation and personal play. The Ruffle files are
under the MIT and Apache-2.0 licenses (see `ruffle/LICENSE_*`). The code in
`tools/`, `index.html`, `serve.ps1` and `Play.bat` is under the MIT license
(see `LICENSE`).
