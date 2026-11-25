"""Small AVM2 (ABC) editor for SWF files.

It reads a SWF, finds the DoABC tags, and records the byte positions of the
constant pools and the method bodies. It can:
  - add strings, namespaces and multinames to the end of the constant pools,
  - replace the code of a method body (and set its max_stack),
  - write the SWF again with correct tag lengths and file length.

Existing pool indexes do not change, because new entries go at the end.
"""
import struct
import zlib


def u30(v):
    out = bytearray()
    while True:
        b = v & 0x7f
        v >>= 7
        if v:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


class Reader:
    def __init__(self, b, p=0):
        self.b, self.p = b, p

    def u8(self):
        v = self.b[self.p]
        self.p += 1
        return v

    def u16(self):
        v = struct.unpack_from('<H', self.b, self.p)[0]
        self.p += 2
        return v

    def u30(self):
        r = sh = 0
        while True:
            c = self.u8()
            r |= (c & 0x7f) << sh
            if not c & 0x80:
                return r
            sh += 7

    def skip(self, n):
        self.p += n


class ABC:
    """One ABC block. Positions are relative to the start of the ABC bytes."""

    def __init__(self, b):
        self.b = b
        r = Reader(b)
        r.u16(); r.u16()
        self.pool_pos = {}

        def pool(name, read_one):
            start = r.p
            n = r.u30()
            items = [None]
            for _ in range(max(0, n - 1)):
                items.append(read_one())
            self.pool_pos[name] = (start, r.p - start, n)
            return items

        pool('int', lambda: r.u30())
        pool('uint', lambda: r.u30())
        pool('double', lambda: r.skip(8))

        def rstr():
            n = r.u30()
            s = b[r.p:r.p + n].decode('utf8', 'replace')
            r.p += n
            return s
        self.strs = pool('string', rstr)
        self.strs[0] = ''
        self.ns = pool('namespace', lambda: (r.u8(), r.u30()))
        self.ns[0] = (0, 0)
        pool('ns_set', lambda: [r.u30() for _ in range(r.u30())])

        def rmn():
            k = r.u8()
            if k in (0x07, 0x0d):
                return ('Q', r.u30(), r.u30())
            if k in (0x0f, 0x10):
                return ('RTQ', r.u30())
            if k in (0x11, 0x12):
                return ('RTQL',)
            if k in (0x09, 0x0e):
                n = r.u30()
                return ('M', n, r.u30())
            if k in (0x1b, 0x1c):
                return ('ML', r.u30())
            if k == 0x1d:
                t = r.u30()
                return ('T', t, [r.u30() for _ in range(r.u30())])
            raise ValueError('multiname kind %x' % k)
        self.mn = pool('multiname', rmn)

        # method_info
        self.method_names = []
        for _ in range(r.u30()):
            pc = r.u30(); r.u30()
            for _ in range(pc):
                r.u30()
            self.method_names.append(r.u30())
            fl = r.u8()
            if fl & 0x08:
                for _ in range(r.u30()):
                    r.u30(); r.u8()
            if fl & 0x80:
                for _ in range(pc):
                    r.u30()
        # metadata
        for _ in range(r.u30()):
            r.u30()
            for _ in range(2 * r.u30()):
                r.u30()
        nc = r.u30()
        self.inst = []
        for _ in range(nc):
            name = r.u30(); r.u30(); fl = r.u8()
            if fl & 0x08:
                r.u30()
            for _ in range(r.u30()):
                r.u30()
            iinit = r.u30()
            self.inst.append((name, iinit, self._traits(r)))
        self.cls = [(r.u30(), self._traits(r)) for _ in range(nc)]
        for _ in range(r.u30()):
            r.u30(); self._traits(r)
        # method bodies: method -> dict of positions
        self.bodies = {}
        for _ in range(r.u30()):
            start = r.p
            m = r.u30()
            ms_pos = r.p; r.u30()
            r.u30(); r.u30(); r.u30()
            cl_pos = r.p
            n = r.u30()
            code_pos = r.p
            r.p += n
            ex_pos = r.p
            for _ in range(r.u30()):
                for _ in range(5):
                    r.u30()
            ex_end = r.p
            self._traits(r)
            self.bodies[m] = dict(start=start, ms_pos=ms_pos, cl_pos=cl_pos, code_pos=code_pos,
                                  code_len=n, ex_pos=ex_pos, ex_end=ex_end)
        self.edits = []  # (pos, old_len, new_bytes)
        self.added = {'string': [], 'namespace': [], 'multiname': []}

    def _traits(self, r):
        out = []
        for _ in range(r.u30()):
            name = r.u30(); k = r.u8(); kind = k & 0x0f
            if kind in (0, 6):
                r.u30(); r.u30()
                if r.u30():
                    r.u8()
                out.append((name, 'slot', None))
            elif kind in (1, 2, 3):
                r.u30(); out.append((name, 'method', r.u30()))
            elif kind == 4:
                r.u30(); out.append((name, 'class', r.u30()))
            elif kind == 5:
                r.u30(); out.append((name, 'func', r.u30()))
            if k & 0x40:
                for _ in range(r.u30()):
                    r.u30()
        return out

    # ---- names ----
    def name(self, i):
        m = self.mn[i] if 0 < i < len(self.mn) else None
        if not m:
            return '*'
        if m[0] == 'Q':
            ns = self.strs[self.ns[m[1]][1]]
            return (ns + ':' if ns else '') + self.strs[m[2]]
        if m[0] in ('M', 'RTQ'):
            return self.strs[m[1] if m[0] == 'RTQ' else m[1]]
        return '<%s>' % m[0]

    def class_index(self, suffix):
        for i, (n, _, _) in enumerate(self.inst):
            if self.name(n).endswith(suffix):
                return i
        raise KeyError(suffix)

    def method(self, cls_suffix, meth):
        """Method index of an instance method ('CTOR' for the constructor)."""
        n, iinit, traits = self.inst[self.class_index(cls_suffix)]
        if meth == 'CTOR':
            return iinit
        for (tn, kind, mi) in traits:
            if kind == 'method' and self.name(tn).split(':')[-1] == meth:
                return mi
        raise KeyError(meth)

    def trait_name(self, cls_suffix, meth):
        _, _, traits = self.inst[self.class_index(cls_suffix)]
        for (tn, kind, mi) in traits:
            if self.name(tn).split(':')[-1] == meth:
                return tn
        raise KeyError(meth)

    def code(self, mi):
        d = self.bodies[mi]
        return self.b[d['code_pos']:d['code_pos'] + d['code_len']]

    # ---- pool additions ----
    def _add(self, pool, item):
        lst = {'string': self.strs, 'namespace': self.ns, 'multiname': self.mn}[pool]
        if item in lst[1:]:
            return lst.index(item, 1)
        lst.append(item)
        self.added[pool].append(item)
        return len(lst) - 1

    def string(self, s):
        return self._add('string', s)

    def namespace(self, kind, s):
        return self._add('namespace', (kind, self.string(s)))

    def qname(self, ns_name, local, kind=0x16):
        return self._add('multiname', ('Q', self.namespace(kind, ns_name), self.string(local)))

    # ---- body edits ----
    def set_code(self, mi, code, max_stack=None, clear_exceptions=False):
        d = self.bodies[mi]
        if max_stack is not None:
            old = Reader(self.b, d['ms_pos']); old.u30()
            self.edits.append((d['ms_pos'], old.p - d['ms_pos'], u30(max_stack)))
        old = Reader(self.b, d['cl_pos']); old.u30()
        self.edits.append((d['cl_pos'], d['code_pos'] - d['cl_pos'] + d['code_len'], u30(len(code)) + bytes(code)))
        if clear_exceptions:
            self.edits.append((d['ex_pos'], d['ex_end'] - d['ex_pos'], u30(0)))

    def patch_bytes(self, mi, at, new):
        """Same-length overwrite inside a method body."""
        d = self.bodies[mi]
        assert at + len(new) <= d['code_len']
        self.edits.append((d['code_pos'] + at, len(new), bytes(new)))

    def build(self):
        edits = list(self.edits)
        for pool in ('string', 'namespace', 'multiname'):
            if not self.added[pool]:
                continue
            start, ln, n = self.pool_pos[pool]
            r = Reader(self.b, start); r.u30(); cnt_len = r.p - start
            body = bytearray()
            for it in self.added[pool]:
                if pool == 'string':
                    e = it.encode('utf8'); body += u30(len(e)) + e
                elif pool == 'namespace':
                    body += bytes([it[0]]) + u30(it[1])
                else:
                    body += b'\x07' + u30(it[1]) + u30(it[2])
            newn = max(n, 1) + len(self.added[pool])
            edits.append((start, cnt_len, u30(newn)))
            edits.append((start + ln, 0, bytes(body)))
        out = bytearray(self.b)
        # Apply from the end so earlier positions stay valid. At the same
        # position, apply the replace first and the insert after it, so the
        # inserted bytes come before the replaced bytes (end of one pool is the
        # start of the next pool).
        for pos, old_len, new in sorted(edits, key=lambda e: (e[0], e[1] != 0), reverse=True):
            out[pos:pos + old_len] = new
        return bytes(out)


class SWF:
    def __init__(self, path):
        src = open(path, 'rb').read()
        sig = src[:3]
        body = zlib.decompress(src[8:]) if sig == b'CWS' else src[8:]
        self.version = src[3]
        self.raw = bytearray(b'FWS' + src[3:8] + body)
        nbits = self.raw[8] >> 3
        p = 8 + (5 + 4 * nbits + 7) // 8 + 4
        self.tags = []  # [code, header_bytes, body]
        self.head = bytes(self.raw[:p])
        while p < len(self.raw):
            h = struct.unpack_from('<H', self.raw, p)[0]
            code, ln = h >> 6, h & 0x3f
            hp = p
            p += 2
            if ln == 0x3f:
                ln = struct.unpack_from('<I', self.raw, p)[0]; p += 4
            self.tags.append([code, bytes(self.raw[p:p + ln])])
            p += ln
            if code == 0:
                break

    def abcs(self):
        """Yield (tag, ABC) for each DoABC tag."""
        for t in self.tags:
            if t[0] == 82:
                p = t[1].index(0, 4) + 1
                yield t, ABC(t[1][p:])

    def set_abc(self, tag, abc):
        p = tag[1].index(0, 4) + 1
        tag[1] = tag[1][:p] + abc.build()

    def save(self, path):
        out = bytearray(self.head)
        for code, body in self.tags:
            if len(body) >= 0x3f or code in (82, 14, 20, 36, 21, 35, 90):
                out += struct.pack('<HI', code << 6 | 0x3f, len(body))
            else:
                out += struct.pack('<H', code << 6 | len(body))
            out += body
        struct.pack_into('<I', out, 4, len(out))
        open(path, 'wb').write(b'CWS' + bytes(out[3:8]) + zlib.compress(bytes(out[8:]), 9))
