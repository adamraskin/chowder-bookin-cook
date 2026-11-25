"""Checks for CI and local use. Usage: python tools/check.py

1. Build again (tools/build.py) and make sure that the output is the same as
   the files in game/ (the build is deterministic).
2. Make sure that the patched main.swf parses and contains the patch.
3. Make sure that all files that the game loads are present.
"""
import hashlib
import os
import subprocess
import sys
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from abcedit import SWF  # noqa: E402

OUTPUTS = ['game/main.swf', 'game/music/id_theme.mp3', 'game/music/id_game1.mp3', 'game/music/id_transition1.mp3']
REQUIRED = ['index.html', 'serve.ps1', 'Play.bat', 'ruffle/ruffle.js',
            'game/game.swf', 'game/config.xml', 'game/sound.xml', 'game/main.orig.swf',
            'game/gamecontent.swf', 'game/sprites.swf', 'game/sound_Chowder.swf',
            'game/MusicAS2Library.swf'] + OUTPUTS


def digest(rel):
    with open(os.path.join(ROOT, rel), 'rb') as f:
        data = f.read()
    if data[:3] == b'CWS':
        # Compare the uncompressed content: zlib builds can compress differently.
        data = b'FWS' + data[3:8] + zlib.decompress(data[8:])
    return hashlib.sha256(data).hexdigest()


def main():
    missing = [f for f in REQUIRED if not os.path.isfile(os.path.join(ROOT, f))]
    if missing:
        sys.exit('missing files: ' + ', '.join(missing))

    before = {f: digest(f) for f in OUTPUTS}
    subprocess.check_call([sys.executable, os.path.join(ROOT, 'tools', 'build.py')])
    changed = [f for f in OUTPUTS if digest(f) != before[f]]
    if changed:
        sys.exit('build output differs from the files in the repo: ' + ', '.join(changed)
                 + '\nRun python tools/build.py and keep the new files.')

    swf = SWF(os.path.join(ROOT, 'game', 'main.swf'))
    ok = False
    for _, a in swf.abcs():
        if 'chowderMusic' in a.strs and 'chowderMusicConnect' in a.strs:
            code = a.code(a.method('tools:SWFBridgeAS3', 'send'))
            ok = len(code) == 31
    if not ok:
        sys.exit('game/main.swf does not contain the music bridge patch')

    with open(os.path.join(ROOT, 'index.html'), encoding='utf8') as f:
        page = f.read()
    for needle in ('window.chowderMusic', 'chowderMusicConnect', 'chowderMusicReceive', 'allowScriptAccess: true'):
        if needle not in page:
            sys.exit('index.html does not contain ' + needle)
    print('all checks passed')


if __name__ == '__main__':
    main()
