Chowder: Bookin' Cook - offline local build
==========================================

PLAY
  Double-click Play.bat. A console window starts a small local web server and
  your browser opens http://localhost:8642. Close the console window to stop.
  No internet connection is necessary. All files are in this folder.
  Click once in the game to start the sound (browsers need a click first).

REQUIREMENTS
  Windows (PowerShell is part of Windows) and a modern browser.

FILES
  Play.bat      launcher
  serve.ps1     local web server (port 8642)
  index.html    page that runs the game in Ruffle, and plays the music
  ruffle\       Ruffle web build, nightly 2024-06-01 (MIT / Apache-2.0)
  game\         game files
    main.orig.swf        original main.swf (input of the patch)
    main.swf             patched main.swf (made by tools\build.py)
    music\*.mp3          music, extracted from MusicAS2Library.swf
  tools\        Python scripts (no packages necessary)
    build.py    makes game\main.swf and game\music\ from the original files
    check.py    builds again and checks the result (CI runs this)
    abcedit.py  small AVM2 bytecode editor used by build.py
    disasm.py   AVM2 disassembler, for debugging

WHY THIS BUILD IS NECESSARY
  1. Preloader. Current Ruffle (0.9.x) never binds the config component of
     the preloader (game.swf), so loading stops at 0%. The Ruffle 2024-06-01
     nightly does not have this problem, so this folder uses that build.
  2. Music bridge. The game plays its music through an AS2 helper
     (MgrMusicAS2.swf) over LocalConnection. Ruffle cannot complete this
     AS3 <-> AS2 connection. The AS2 helper then retries in a loop that
     freezes the page, and the game does not start.
     tools\build.py patches main.swf: the game sends its music commands to
     the page through ExternalInterface, and index.html plays the music with
     Web Audio. The helper MgrMusicAS2.swf is not used and is not included.

DEBUG
  Open http://localhost:8642/?debug. The console output of the page goes to
  ruffle-log.txt in this folder.

REBUILD
  python tools\build.py     (Python 3.9 or newer)
  python tools\check.py
