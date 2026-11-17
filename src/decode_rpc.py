#!/usr/bin/env python3
"""Decode the agent's --debug-log-rpc-data hexdump (RECV/SEND blocks) into msgpack-RPC messages. stdlib only."""
import re, struct, sys, json
def dec(b, i=0):
    t = b[i]; i += 1
    if t <= 0x7f: return t, i
    if t >= 0xe0: return t - 256, i
    if 0xa0 <= t <= 0xbf: n = t & 0x1f; return b[i:i+n].decode("utf8", "replace"), i + n
    if 0x90 <= t <= 0x9f: return arr(b, i, t & 0xf)
    if 0x80 <= t <= 0x8f: return mp(b, i, t & 0xf)
    if t == 0xc0: return None, i
    if t == 0xc2: return False, i
    if t == 0xc3: return True, i
    if t in (0xc4, 0xd9): n = b[i]; i += 1; return (b[i:i+n].decode("utf8", "replace") if t == 0xd9 else b[i:i+n].hex()), i + n
    if t in (0xc5, 0xda): n = struct.unpack(">H", b[i:i+2])[0]; i += 2; return (b[i:i+n].decode("utf8", "replace") if t == 0xda else b[i:i+n].hex()), i + n
    if t in (0xc6, 0xdb): n = struct.unpack(">I", b[i:i+4])[0]; i += 4; return (b[i:i+n].decode("utf8", "replace") if t == 0xdb else b[i:i+n].hex()), i + n
    fm = {0xcc: ">B", 0xcd: ">H", 0xce: ">I", 0xcf: ">Q", 0xd0: ">b", 0xd1: ">h", 0xd2: ">i", 0xd3: ">q", 0xca: ">f", 0xcb: ">d"}
    if t in fm: n = struct.calcsize(fm[t]); return struct.unpack(fm[t], b[i:i+n])[0], i + n
    if t == 0xdc: n = struct.unpack(">H", b[i:i+2])[0]; return arr(b, i + 2, n)
    if t == 0xdd: n = struct.unpack(">I", b[i:i+4])[0]; return arr(b, i + 4, n)
    if t == 0xde: n = struct.unpack(">H", b[i:i+2])[0]; return mp(b, i + 2, n)
    if t == 0xdf: n = struct.unpack(">I", b[i:i+4])[0]; return mp(b, i + 4, n)
    raise ValueError(f"unsupported msgpack type {t:#x}")
def arr(b, i, n):
    o = []
    for _ in range(n): v, i = dec(b, i); o.append(v)
    return o, i
def mp(b, i, n):
    o = {}
    for _ in range(n): k, i = dec(b, i); v, i = dec(b, i); o[k if isinstance(k, str) else str(k)] = v
    return o, i
hdr = re.compile(r"^(\d{4}/\d\d/\d\d \d\d:\d\d:\d\d\.\d+) (RECV|SEND|\S+) .*?\[(\d+)\]:")
def blocks(text):
    cur = None
    for line in text.splitlines():
        m = hdr.match(line)
        if m:
            if cur: yield cur
            cur = [m.group(1), m.group(2), m.group(3), bytearray()]
        elif cur and (h := re.match(r"^[0-9a-f]{8}  ([0-9a-f ]+?)\s*\|", line)):
            cur[3] += bytes.fromhex(h.group(1).replace(" ", ""))
    if cur: yield cur
def main(path):
    for ts, d, n, b in blocks(open(path, errors="replace").read()):
        try:
            msg, _ = dec(bytes(b))
        except Exception as e:
            print(json.dumps({"ts": ts, "dir": d, "len": n, "decode_error": str(e)})); continue
        o = {"ts": ts, "dir": d, "len": int(n)}
        if isinstance(msg, list) and msg and msg[0] == 0: o.update(type="request", msgid=msg[1], method=msg[2], params=msg[3])
        elif isinstance(msg, list) and msg and msg[0] == 1: o.update(type="response", msgid=msg[1], error=msg[2], result=msg[3])
        else: o["raw"] = msg
        print(json.dumps(o, default=str))
main(sys.argv[1])
