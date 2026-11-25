"""Build the patched game files from the original files.

Usage: python tools/build.py

Input (original files, not changed):
  game/main.orig.swf         original main.swf
  game/MusicAS2Library.swf   AS2 music library (3 MP3 sounds)

Output:
  game/main.swf              patched main.swf
  game/music/<id>.mp3        music tracks, played by the page (index.html)

Why the patch is necessary:
  The game plays its music through an AS2 helper (MgrMusicAS2.swf). The AS3
  game talks to it over LocalConnection (gskinner SWFBridge). Ruffle does not
  complete this AS3 <-> AS2 handshake. The AS2 side then retries in a tight
  loop and freezes the page, and the game never gets BRIDGE_CONNECTED, so it
  does not start.

What the patch does:
  1. SoundAS3Bridge constructor: do not load MgrMusicAS2.swf. Register two
     JavaScript callbacks on the player instead:
       chowderMusicConnect()            -> SWFBridgeAS3.init (fires CONNECT)
       chowderMusicReceive(name, args)  -> SWFBridgeAS3.receive (calls
                                           SoundAS3Bridge.<name>(...args))
     Then call window.chowderMusic("register").
  2. SWFBridgeAS3.init: remove the LocalConnection send.
  3. SWFBridgeAS3.send(method, ...args): call
     window.chowderMusic(method, ...args) through ExternalInterface.
  The page (index.html) plays the music with Web Audio and does the same
  work as the AS2 helper (start, stop, mix, fade, volume, pause, mute).
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from abcedit import SWF, u30  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GAME = os.path.join(ROOT, 'game')

GETLEX, GETPROPERTY, PUSHSTRING, CALLPROPVOID = 0x60, 0x66, 0x2c, 0x4f
NOP, RETURNVOID, GETLOCAL2, IFNE = 0x02, 0x47, 0xd2, 0x14


def op(code, *args):
    return bytes([code]) + b''.join(u30(a) for a in args)


def expect(code, at, opcode):
    if code[at] != opcode:
        raise SystemExit('unexpected bytecode at %d: %02x (expected %02x)' % (at, code[at], opcode))


def patch_main():
    swf = SWF(os.path.join(GAME, 'main.orig.swf'))
    done = False
    for tag, a in swf.abcs():
        try:
            a.class_index('tools:SoundAS3Bridge')
        except KeyError:
            continue
        ei = a.qname('flash.external', 'ExternalInterface')
        m_call = a.qname('', 'call')
        m_add = a.qname('', 'addCallback')
        s = a.string

        # --- 3. SWFBridgeAS3.send ---
        mi = a.method('tools:SWFBridgeAS3', 'send')
        c = a.code(mi)
        for at, o in ((20, GETLOCAL2), (22, CALLPROPVOID), (30, CALLPROPVOID), (51, CALLPROPVOID), (55, RETURNVOID)):
            expect(c, at, o)
        new = (c[0:2]                                   # getlocal0, pushscope
               + c[20:26]                               # args.unshift(method)
               + bytes([GETLOCAL2]) + op(PUSHSTRING, s('chowderMusic'))
               + c[30:34]                               # args.unshift("chowderMusic")
               + op(GETLEX, ei) + op(GETPROPERTY, m_call)
               + op(GETLEX, ei) + bytes([GETLOCAL2])
               + c[51:55]                               # call.apply(ExternalInterface, args)
               + bytes([RETURNVOID]))
        a.set_code(mi, new, max_stack=6)

        # --- 2. SWFBridgeAS3.init: remove "if (host) lc.send(...)" (offsets 32..50) ---
        mi = a.method('tools:SWFBridgeAS3', 'com_gskinner_utils_SWFBridge_init')
        c = a.code(mi)
        expect(c, 32, GETLEX); expect(c, 48, CALLPROPVOID); expect(c, 51, 0x5e)
        a.patch_bytes(mi, 32, bytes([NOP]) * 19)

        # --- 1. SoundAS3Bridge constructor ---
        mi = a.method('tools:SoundAS3Bridge', 'CTOR')
        c = bytearray(a.code(mi))
        # 118..130: loader.load(new URLRequest(url))  -> replaced
        expect(c, 118, GETLEX); expect(c, 127, CALLPROPVOID); expect(c, 131, GETLEX)
        expect(c, 149, GETLEX)                     # getlex sb1
        expect(c, 41, IFNE)                        # ifne ->168 (jumps over the replaced range)
        getlex_sb1 = bytes(c[149:152])
        m_receive = a.trait_name('tools:SWFBridgeAS3', 'com_gskinner_utils_SWFBridge_receive')
        m_init = a.trait_name('tools:SWFBridgeAS3', 'com_gskinner_utils_SWFBridge_init')
        ins = (op(GETLEX, ei) + op(PUSHSTRING, s('chowderMusicReceive'))
               + getlex_sb1 + op(GETPROPERTY, m_receive) + op(CALLPROPVOID, m_add, 2)
               + op(GETLEX, ei) + op(PUSHSTRING, s('chowderMusicConnect'))
               + getlex_sb1 + op(GETPROPERTY, m_init) + op(CALLPROPVOID, m_add, 2)
               + op(GETLEX, ei) + op(PUSHSTRING, s('chowderMusic')) + op(PUSHSTRING, s('register'))
               + op(CALLPROPVOID, m_call, 2))
        delta = len(ins) - 13
        new = c[:118] + ins + c[131:]
        off = struct.unpack('<i', bytes(new[42:45]) + (b'\xff' if new[44] & 0x80 else b'\0'))[0]
        assert 45 + off == 168, off
        new[42:45] = struct.pack('<i', off + delta)[:3]
        a.set_code(mi, bytes(new), max_stack=6)

        swf.set_abc(tag, a)
        done = True
    if not done:
        raise SystemExit('SoundAS3Bridge not found in main.orig.swf')
    swf.save(os.path.join(GAME, 'main.swf'))
    print('wrote game/main.swf')


def extract_music():
    swf = SWF(os.path.join(GAME, 'MusicAS2Library.swf'))
    sounds, names = {}, {}
    for code, body in swf.tags:
        if code == 14:  # DefineSound
            sid, flags = struct.unpack_from('<HB', body)
            if flags >> 4 != 2:
                raise SystemExit('sound %d is not MP3' % sid)
            sounds[sid] = body[9:]  # skip id, flags, sample count, seek samples
        elif code == 56:  # ExportAssets
            n = struct.unpack_from('<H', body)[0]
            p = 2
            for _ in range(n):
                cid = struct.unpack_from('<H', body, p)[0]
                e = body.index(0, p + 2)
                names[cid] = body[p + 2:e].decode()
                p = e + 1
    out = os.path.join(GAME, 'music')
    os.makedirs(out, exist_ok=True)
    for sid, data in sounds.items():
        path = os.path.join(out, names[sid] + '.mp3')
        open(path, 'wb').write(data)
        print('wrote game/music/%s.mp3 (%d bytes)' % (names[sid], len(data)))


if __name__ == '__main__':
    patch_main()
    extract_music()
