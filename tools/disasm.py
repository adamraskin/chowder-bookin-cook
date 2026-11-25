"""AVM2 disassembler. Usage: python tools/disasm.py <file.swf> <Class.method substring>...
Use an empty string to print all methods."""
import sys, struct

class R:
    def __init__(s, b, p=0): s.b, s.p = b, p
    def u8(s): v = s.b[s.p]; s.p += 1; return v
    def u16(s): v = struct.unpack_from('<H', s.b, s.p)[0]; s.p += 2; return v
    def s24(s):
        v = s.b[s.p] | s.b[s.p+1] << 8 | s.b[s.p+2] << 16; s.p += 3
        return v - (1 << 24) if v & 0x800000 else v
    def u30(s):
        r = 0; sh = 0
        while True:
            c = s.u8(); r |= (c & 0x7f) << sh
            if not c & 0x80: return r
            sh += 7
    def s32(s):
        r = 0; sh = 0
        while True:
            c = s.u8(); r |= (c & 0x7f) << sh; sh += 7
            if not c & 0x80: break
        if r & (1 << (sh - 1)) and sh < 35: r -= 1 << sh
        return r & 0xffffffff if r >= 0 else r
    def d64(s): v = struct.unpack_from('<d', s.b, s.p)[0]; s.p += 8; return v
    def str(s): n = s.u30(); v = s.b[s.p:s.p+n].decode('utf8', 'replace'); s.p += n; return v

def tags(raw):
    r = R(raw, 8)
    nbits = raw[8] >> 3
    r.p = 8 + (5 + 4 * nbits + 7) // 8 + 4
    while r.p < len(raw):
        h = r.u16(); code, ln = h >> 6, h & 0x3f
        if ln == 0x3f: ln = struct.unpack_from('<I', raw, r.p)[0]; r.p += 4
        yield code, raw[r.p:r.p+ln], r.p; r.p += ln

class ABC:
    def __init__(a, b):
        r = R(b); r.u16(); r.u16()
        a.ints = [0] + [r.s32() for _ in range(max(0, r.u30() - 1))]
        a.uints = [0] + [r.s32() for _ in range(max(0, r.u30() - 1))]
        a.dbls = [0] + [r.d64() for _ in range(max(0, r.u30() - 1))]
        a.strs = [''] + [r.str() for _ in range(max(0, r.u30() - 1))]
        a.ns = [('', '')]
        for _ in range(max(0, r.u30() - 1)): k = r.u8(); a.ns.append((k, a.strs[r.u30()]))
        a.nss = [[]]
        for _ in range(max(0, r.u30() - 1)): a.nss.append([r.u30() for _ in range(r.u30())])
        a.mn = [None]
        for _ in range(max(0, r.u30() - 1)):
            k = r.u8()
            if k in (7, 0xd): ns = r.u30(); n = r.u30(); a.mn.append(('Q', ns, n))
            elif k in (0xf, 0x10): a.mn.append(('RTQ', None, r.u30()))
            elif k in (0x11, 0x12): a.mn.append(('RTQL', None, None))
            elif k in (9, 0xe): n = r.u30(); s = r.u30(); a.mn.append(('M', s, n))
            elif k in (0x1b, 0x1c): a.mn.append(('ML', r.u30(), None))
            elif k == 0x1d:
                t = r.u30(); ps = [r.u30() for _ in range(r.u30())]; a.mn.append(('T', t, ps))
        a.methods = []
        for _ in range(r.u30()):
            pc = r.u30(); r.u30(); [r.u30() for _ in range(pc)]; name = r.u30(); fl = r.u8()
            if fl & 8:
                for _ in range(r.u30()): r.u30(); r.u8()
            if fl & 0x80: [r.u30() for _ in range(pc)]
            a.methods.append(name)
        for _ in range(r.u30()):
            r.u30()
            n = r.u30(); [r.u30() for _ in range(2 * n)]
        nc = r.u30()
        a.inst = []
        for _ in range(nc):
            name = r.u30(); sup = r.u30(); fl = r.u8()
            if fl & 8: r.u30()
            [r.u30() for _ in range(r.u30())]
            iinit = r.u30(); tr = a.traits(r)
            a.inst.append((name, sup, iinit, tr))
        a.cls = [(r.u30(), a.traits(r)) for _ in range(nc)]
        a.scripts = [(r.u30(), a.traits(r)) for _ in range(r.u30())]
        a.bodies = {}
        for _ in range(r.u30()):
            m = r.u30(); r.u30(); r.u30(); r.u30(); r.u30()
            n = r.u30(); code = r.b[r.p:r.p+n]; r.p += n
            for _ in range(r.u30()): [r.u30() for _ in range(5)]
            a.traits(r)
            a.bodies[m] = code
    def traits(a, r):
        out = []
        for _ in range(r.u30()):
            name = r.u30(); k = r.u8(); kind = k & 0xf
            if kind in (0, 6):
                r.u30(); r.u30(); vi = r.u30()
                if vi: r.u8()
                out.append((name, 'slot', None))
            elif kind in (1, 2, 3):
                r.u30(); m = r.u30(); out.append((name, 'method', m))
            elif kind == 4: r.u30(); c = r.u30(); out.append((name, 'class', c))
            elif kind == 5: r.u30(); m = r.u30(); out.append((name, 'func', m))
            if k & 0x40: [r.u30() for _ in range(r.u30())]
        return out
    def name(a, i):
        if not i or i >= len(a.mn): return '*'
        m = a.mn[i]
        if m[0] == 'Q': return a.strs[a.ns[m[1]][1] and 0 or 0] and '' or (a.ns[m[1]][1] + ':' if a.ns[m[1]][1] else '') + a.strs[m[2]]
        if m[0] in ('M', 'RTQ'): return a.strs[m[2]]
        if m[0] == 'T': return a.name(m[1]) + '.<' + ','.join(a.name(p) for p in m[2]) + '>'
        return '<' + m[0] + '>'

# opcode -> (name, operand spec) ; u=u30, s=s24, b=byte, m=multiname, S=string, I=int, D=double
OPS = {0x02:('nop',''),0x03:('throw',''),0x04:('getsuper','m'),0x05:('setsuper','m'),0x08:('kill','u'),0x09:('label',''),
0x0c:('ifnlt','s'),0x0d:('ifnle','s'),0x0e:('ifngt','s'),0x0f:('ifnge','s'),0x10:('jump','s'),0x11:('iftrue','s'),0x12:('iffalse','s'),
0x13:('ifeq','s'),0x14:('ifne','s'),0x15:('iflt','s'),0x16:('ifle','s'),0x17:('ifgt','s'),0x18:('ifge','s'),0x19:('ifstricteq','s'),0x1a:('ifstrictne','s'),
0x1d:('popscope',''),0x1e:('nextname',''),0x1f:('hasnext',''),0x20:('pushnull',''),0x21:('pushundefined',''),0x23:('nextvalue',''),
0x24:('pushbyte','b'),0x25:('pushshort','u'),0x26:('pushtrue',''),0x27:('pushfalse',''),0x28:('pushnan',''),0x29:('pop',''),0x2a:('dup',''),0x2b:('swap',''),
0x2c:('pushstring','S'),0x2d:('pushint','I'),0x2e:('pushuint','u'),0x2f:('pushdouble','D'),0x30:('pushscope',''),0x31:('pushnamespace','u'),0x32:('hasnext2','uu'),
0x40:('newfunction','u'),0x41:('call','u'),0x42:('construct','u'),0x43:('callmethod','uu'),0x44:('callstatic','uu'),0x45:('callsuper','mu'),0x46:('callproperty','mu'),
0x47:('returnvoid',''),0x48:('returnvalue',''),0x49:('constructsuper','u'),0x4a:('constructprop','mu'),0x4c:('callproplex','mu'),0x4e:('callsupervoid','mu'),0x4f:('callpropvoid','mu'),
0x55:('newobject','u'),0x56:('newarray','u'),0x57:('newactivation',''),0x58:('newclass','u'),0x59:('getdescendants','m'),0x5a:('newcatch','u'),
0x5d:('findpropstrict','m'),0x5e:('findproperty','m'),0x60:('getlex','m'),0x61:('setproperty','m'),0x62:('getlocal','u'),0x63:('setlocal','u'),
0x64:('getglobalscope',''),0x65:('getscopeobject','u'),0x66:('getproperty','m'),0x68:('initproperty','m'),0x6a:('deleteproperty','m'),
0x6c:('getslot','u'),0x6d:('setslot','u'),0x70:('convert_s',''),0x73:('convert_i',''),0x74:('convert_u',''),0x75:('convert_d',''),0x76:('convert_b',''),0x78:('checkfilter',''),
0x80:('coerce','m'),0x82:('coerce_a',''),0x85:('coerce_s',''),0x86:('astype','m'),0x87:('astypelate',''),0x90:('negate',''),0x91:('increment',''),0x93:('decrement',''),
0x95:('typeof',''),0x96:('not',''),0xa0:('add',''),0xa1:('subtract',''),0xa2:('multiply',''),0xa3:('divide',''),0xab:('equals',''),0xac:('strictequals',''),
0xad:('lessthan',''),0xaf:('greaterthan',''),0xb1:('instanceof',''),0xb2:('istype','m'),0xb3:('istypelate',''),0xb4:('in',''),
0xc0:('increment_i',''),0xc2:('inclocal_i','u'),0xd0:('getlocal0',''),0xd1:('getlocal1',''),0xd2:('getlocal2',''),0xd3:('getlocal3',''),
0xd4:('setlocal0',''),0xd5:('setlocal1',''),0xd6:('setlocal2',''),0xd7:('setlocal3',''),0xef:('debug','bubu'),0xf0:('debugline','u'),0xf1:('debugfile','S')}

def dis(a, code):
    r = R(code); out = []
    while r.p < len(code):
        at = r.p; op = r.u8()
        if op == 0x1b:
            d = r.s24(); n = r.u30(); [r.s24() for _ in range(n + 1)]; out.append(f'{at:4} lookupswitch'); continue
        nm, spec = OPS.get(op, (f'op_{op:02x}', ''))
        args = []
        for c in spec:
            if c == 'u': args.append(str(r.u30()))
            elif c == 'b': args.append(str(r.u8()))
            elif c == 's': args.append('->' + str(r.p + 3 + r.s24()))
            elif c == 'm': args.append(a.name(r.u30()))
            elif c == 'S': args.append(repr(a.strs[r.u30()]))
            elif c == 'I': args.append(str(a.ints[r.u30()]))
            elif c == 'D': args.append(str(a.dbls[r.u30()]))
        out.append(f'{at:4} {nm} ' + ' '.join(args))
    return out

if __name__ == '__main__':
    import zlib
    raw = open(sys.argv[1], 'rb').read()
    if raw[:3] == b'CWS':
        raw = b'FWS' + raw[3:8] + zlib.decompress(raw[8:])
    want = sys.argv[2:]
    for code, body, off in tags(raw):
        if code in (72, 82):
            b = body
            if code == 82:
                p = 4; p = b.index(0, p) + 1; b = b[p:]
            a = ABC(b)
            for (iname, sup, iinit, tr) in a.inst:
                cn = a.name(iname)
                for (n, k, m) in tr + [(0, 'ctor', iinit)]:
                    mn = a.name(n) if n else 'CONSTRUCTOR'
                    if m is not None and any(w in cn + '.' + mn for w in want):
                        print(f'=== {cn}.{mn} ({k})')
                        print('\n'.join(dis(a, a.bodies.get(m, b''))))
