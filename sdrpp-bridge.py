#!/usr/bin/env python3
"""
SAT° Predictor ⇄ SDR++ bridge – Doppler correction through the SDR++ Rigctl server.

The SAT° Predictor page (in the browser) connects to this bridge over a WebSocket on localhost,
and the bridge forwards commands to the SDR++ Rigctl server (TCP, 127.0.0.1:4532 by default).
All messages are shown here, in the terminal – the web page stays clean.

Run (Python 3.8+, no extra packages):
    python3 sdrpp-bridge.py

Options:
    --rig-host 127.0.0.1   SDR++ Rigctl server address
    --rig-port 4532        SDR++ Rigctl server port (SDR++ default)
    --port 4533            WebSocket port the page connects to
    --allow-origin URL     additional allowed web page (can be given several times)
    --quiet                do not print every frequency correction

In SDR++: Module Manager → add "rigctl_server", tick "Tuning" in its panel and click "Start".
Stop the bridge with Ctrl+C.
"""
import argparse
import asyncio
import base64
import hashlib
import json
import signal
import struct
import sys
import time

VERSION = 2
WS_GUID = '258EAFA5-E914-47DA-95CA-C5AB0DC85B11'
DEFAULT_ORIGINS = {'https://sq5wbw.github.io', 'null'}   # 'null' = page opened from disk (file://)

# ---------- terminal ----------
USE_COLOR = sys.stdout.isatty()
def c(code, s): return f'\033[{code}m{s}\033[0m' if USE_COLOR else s
def log(msg, kind='info'):
    color = {'info': '0', 'ok': '32', 'warn': '33', 'err': '31', 'dim': '2', 'track': '36'}.get(kind, '0')
    print(f"{c('2', time.strftime('%H:%M:%S'))}  {c(color, msg)}", flush=True)
def mhz(hz): return f'{hz / 1e6:.6f} MHz'


# ---------- Rigctl (SDR++) ----------
class Rig:
    def __init__(self, host, port):
        self.host, self.port = host, port
        self.reader = self.writer = None
        self.lock = asyncio.Lock()
        self.ok = False
        self.listeners = set()      # callbacks for connection state changes

    def _set(self, ok):
        if ok != self.ok:
            self.ok = ok
            for fn in list(self.listeners): fn(ok)

    async def keep_connected(self):
        warned = False
        while True:
            if not self.ok:
                try:
                    self.reader, self.writer = await asyncio.wait_for(asyncio.open_connection(self.host, self.port), 3)
                    log(f'Connected to SDR++ (Rigctl {self.host}:{self.port}).', 'ok')
                    warned = False
                    self._set(True)
                except (OSError, asyncio.TimeoutError):
                    if not warned:
                        log(f'Waiting for SDR++: Rigctl server {self.host}:{self.port} is not responding. '
                            'In SDR++ enable the rigctl_server module, tick "Tuning" and click "Start".', 'warn')
                        warned = True
            await asyncio.sleep(2)

    def _drop(self, why):
        if self.ok: log(f'Lost connection to SDR++ ({why}).', 'err')
        try:
            if self.writer: self.writer.close()
        except Exception: pass
        self.reader = self.writer = None
        self._set(False)

    async def _cmd(self, line):
        if not self.ok: raise ConnectionError('SDR++ not connected')
        try:
            self.writer.write((line + '\n').encode())
            await self.writer.drain()
            resp = await asyncio.wait_for(self.reader.readline(), 2)
            if not resp: raise ConnectionError('SDR++ closed the connection')
            return resp.decode(errors='replace').strip()
        except (OSError, asyncio.TimeoutError, ConnectionError) as e:
            self._drop(str(e) or e.__class__.__name__)
            raise ConnectionError(str(e))

    async def get_freq(self):
        async with self.lock:
            r = await self._cmd('f')
        return int(float(r))

    async def set_freq(self, hz):
        async with self.lock:
            r = await self._cmd(f'F {int(hz)}')
            if r.startswith('RPRT') and r != 'RPRT 0':
                raise RuntimeError(f'SDR++ rejected the frequency change ({r}) – is "Tuning" ticked in the Rigctl panel?')
            return int(float(await self._cmd('f')))       # actual value after setting

    async def track(self, expect, target, tol):
        """Doppler correction that never overrides the user's tuning: read and write under one lock.
        If the frequency differs from the last one we set by more than tol, the user retuned SDR++."""
        async with self.lock:
            cur = int(float(await self._cmd('f')))
            if abs(cur - expect) > tol:
                return 'retuned', cur
            if abs(cur - target) < 1:
                return 'set', cur
            r = await self._cmd(f'F {int(target)}')
            if r.startswith('RPRT') and r != 'RPRT 0':
                raise RuntimeError(f'SDR++ rejected the frequency change ({r}) – is "Tuning" ticked in the Rigctl panel?')
            return 'set', int(float(await self._cmd('f')))


# ---------- minimal WebSocket server (RFC 6455, text frames only) ----------
async def ws_handshake(reader, writer, origins):
    head = await asyncio.wait_for(reader.readuntil(b'\r\n\r\n'), 5)
    lines = head.decode(errors='replace').split('\r\n')
    hdr = {}
    for l in lines[1:]:
        if ':' in l:
            k, v = l.split(':', 1); hdr[k.strip().lower()] = v.strip()
    origin = hdr.get('origin', '')
    allowed = origin in origins or origin.startswith(('http://localhost', 'http://127.0.0.1', 'https://localhost'))
    if 'websocket' not in hdr.get('upgrade', '').lower() or 'sec-websocket-key' not in hdr:
        writer.write(b'HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\n\r\n'); await writer.drain(); return None
    if not allowed:
        log(f'Rejected connection from {origin or "(unknown page)"} – add it with --allow-origin if it is your copy of SAT° Predictor.', 'warn')
        writer.write(b'HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n'); await writer.drain(); return None
    accept = base64.b64encode(hashlib.sha1((hdr['sec-websocket-key'] + WS_GUID).encode()).digest()).decode()
    writer.write(('HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n'
                  f'Sec-WebSocket-Accept: {accept}\r\n\r\n').encode())
    await writer.drain()
    return origin

async def ws_recv(reader):
    while True:
        b1, b2 = await reader.readexactly(2)
        op, masked, n = b1 & 0x0F, b2 & 0x80, b2 & 0x7F
        if n == 126: n = struct.unpack('>H', await reader.readexactly(2))[0]
        elif n == 127: n = struct.unpack('>Q', await reader.readexactly(8))[0]
        mask = await reader.readexactly(4) if masked else b'\0\0\0\0'
        data = bytes(x ^ mask[i % 4] for i, x in enumerate(await reader.readexactly(n)))
        if op == 8: return                            # close
        if op == 9: yield ('ping', data); continue
        if op in (1, 2): yield ('msg', data.decode(errors='replace'))

def ws_frame(text, op=1):
    data = text.encode() if isinstance(text, str) else text
    n = len(data)
    if n < 126: head = struct.pack('>BB', 0x80 | op, n)
    elif n < 65536: head = struct.pack('>BBH', 0x80 | op, 126, n)
    else: head = struct.pack('>BBQ', 0x80 | op, 127, n)
    return head + data


# ---------- tuning job (runs in the bridge, so a background tab or a small window does not matter) ----------
C_KMS = 299792.458

class Tuner:
    """One satellite at a time. The page sends the radial velocity of the satellite for the whole pass
    (one sample per second); the bridge applies the Doppler correction every 0.5 s from AOS to LOS."""
    def __init__(self, rig, quiet):
        self.rig, self.quiet = rig, quiet
        self.job = None
        self.clients = set()
        self.last_log = 0

    def public(self):
        j = self.job
        return None if not j else {'sat': j['sat'], 'start': j['start'], 'end': j['end'], 'state': j['state']}

    def broadcast(self):
        for cl in list(self.clients): cl.send({'type': 'tuning', 'tuning': self.public()})

    def rr_at(self, t):
        s = self.job['samples']
        if not s: return 0.0
        if t <= s[0][0]: return s[0][1]
        if t >= s[-1][0]: return s[-1][1]
        lo, hi = 0, len(s) - 1
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if s[mid][0] <= t: lo = mid
            else: hi = mid
        (t0, v0), (t1, v1) = s[lo], s[hi]
        return v0 + (v1 - v0) * (t - t0) / (t1 - t0)

    def start(self, msg):
        prev = self.job
        self.job = {'sat': msg['sat'], 'f0': float(msg['f0']), 'linear': bool(msg.get('linear')),
                    'start': int(msg['start']), 'end': int(msg['end']), 'samples': msg.get('samples') or [],
                    'aos': msg.get('aos', ''), 'los': msg.get('los', ''), 'last': None, 'state': 'waiting'}
        if prev and prev['sat'] != self.job['sat']: log(f"■ Stopped tuning {prev['sat']}.", 'ok')
        kind = 'linear transponder – click a QSO on the SDR++ waterfall' if self.job['linear'] else 'fixed frequency'
        log(f"▶ Tune {self.job['sat']}: {mhz(self.job['f0'])} ({kind}), pass {self.job['aos']}–{self.job['los']}.", 'ok')
        if time.time() * 1000 < self.job['start']:
            log(f"  Waiting for AOS at {self.job['aos']} – Doppler correction starts then.", 'dim')
        self.broadcast()

    def stop(self, why):
        if self.job:
            log(f"■ Stopped tuning {self.job['sat']} ({why}).", 'ok')
            self.job = None
            self.broadcast()

    async def run(self):
        while True:
            await asyncio.sleep(0.5)
            j = self.job
            if not j: continue
            now = time.time() * 1000
            if now >= j['end']: self.stop('LOS'); continue
            if now < j['start']: continue
            if j['state'] != 'active':
                j['state'] = 'active'
                log(f"  AOS {j['sat']} – Doppler correction running.", 'ok')
                self.broadcast()
            if not self.rig.ok: continue
            rr = self.rr_at(now)
            target = round(j['f0'] * (1 - rr / C_KMS))
            dop = target - j['f0']
            try:
                if j['last'] is None:
                    j['last'] = await self.rig.set_freq(target)
                    log(f"  {j['sat']}: SDR++ → {mhz(j['last'])}  (Doppler {dop / 1000:+.3f} kHz)", 'track')
                    continue
                res, f = await self.rig.track(j['last'], target, 30)
                if self.job is not j: continue
                if res == 'retuned':
                    j['f0'] = f / (1 - rr / C_KMS)
                    j['last'] = f
                    log(f"  Retuned in SDR++ to {mhz(f)} – holding this station ({mhz(j['f0'])} on the satellite).", 'ok')
                else:
                    j['last'] = f
                    if not self.quiet and time.time() - self.last_log >= 1:
                        self.last_log = time.time()
                        log(f"  {j['sat']}: SDR++ → {mhz(f)}  (Doppler {dop / 1000:+.3f} kHz)", 'track')
            except (ConnectionError, RuntimeError) as e:
                if isinstance(e, RuntimeError): log(str(e), 'err')
            except Exception as e:                       # never let the loop die
                log(f'Unexpected error: {e!r}', 'err')


# ---------- web page client ----------
class Client:
    def __init__(self, writer, rig, tuner):
        self.w, self.rig, self.tuner = writer, rig, tuner

    def send(self, obj):
        try: self.w.write(ws_frame(json.dumps(obj)))
        except Exception: pass

    def on_rig(self, ok): self.send({'type': 'status', 'rig': ok})

    async def handle(self, msg):
        t = msg.get('type')
        try:
            if t == 'hello':
                self.send({'type': 'status', 'rig': self.rig.ok, 'version': VERSION, 'tuning': self.tuner.public()})
            elif t == 'tune':
                self.tuner.start(msg)
            elif t == 'untune':
                self.tuner.stop('stopped on the page')
        except (KeyError, ValueError, TypeError) as e:
            log(f'Ignored a malformed message from the page: {e!r}', 'warn')


async def keepalive(rig, tuner):
    """Keeps idle connections alive: a WebSocket ping to the page every 20 s and a frequency query to SDR++
    every 10 s while not tuning (detects a closed SDR++ early)."""
    n = 0
    while True:
        await asyncio.sleep(10)
        n += 1
        if rig.ok and not tuner.job:
            try: await rig.get_freq()
            except Exception: pass
        if n % 2 == 0:
            for cl in list(tuner.clients):
                try: cl.w.write(ws_frame(b'', 9))
                except Exception: pass


async def serve(args):
    rig = Rig(args.rig_host, args.rig_port)
    tuner = Tuner(rig, args.quiet)
    origins = DEFAULT_ORIGINS | set(args.allow_origin or [])

    async def on_client(reader, writer):
        try:
            origin = await ws_handshake(reader, writer, origins)
        except Exception:
            writer.close(); return
        if origin is None:
            writer.close(); return
        cl = Client(writer, rig, tuner)
        rig.listeners.add(cl.on_rig)
        tuner.clients.add(cl)
        log(f'SAT° Predictor page connected ({origin}).', 'ok')
        try:
            async for kind, data in ws_recv(reader):
                if kind == 'ping': writer.write(ws_frame(data, 10)); continue
                try: msg = json.loads(data)
                except ValueError: continue
                await cl.handle(msg)
                await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError, OSError):
            pass
        finally:
            rig.listeners.discard(cl.on_rig)
            tuner.clients.discard(cl)
            if not tuner.clients: tuner.stop('page closed')
            log('SAT° Predictor page disconnected.', 'dim')
            try: writer.close()
            except Exception: pass

    try:
        server = await asyncio.start_server(on_client, '127.0.0.1', args.port)
    except OSError as e:
        log(f'Cannot start the bridge on port {args.port}: {e}. Is the bridge already running in another window?', 'err')
        return
    log(f'SAT° Predictor ⇄ SDR++ bridge running: page connects to ws://127.0.0.1:{args.port}, '
        f'SDR++ Rigctl at {args.rig_host}:{args.rig_port}. Stop: Ctrl+C.', 'ok')
    asyncio.ensure_future(rig.keep_connected())
    asyncio.ensure_future(tuner.run())
    asyncio.ensure_future(keepalive(rig, tuner))
    async with server:
        await server.serve_forever()


def main():
    ap = argparse.ArgumentParser(description='SAT° Predictor ⇄ SDR++ (Rigctl) – Doppler correction')
    ap.add_argument('--rig-host', default='127.0.0.1')
    ap.add_argument('--rig-port', type=int, default=4532)
    ap.add_argument('--port', type=int, default=4533)
    ap.add_argument('--allow-origin', action='append')
    ap.add_argument('--quiet', action='store_true')
    args = ap.parse_args()
    try:
        asyncio.run(serve(args))
    except KeyboardInterrupt:
        print(); log('Bridge stopped.', 'dim')

if __name__ == '__main__':
    # SIGPIPE stays ignored: writing to a socket closed by the browser or SDR++ must raise an error,
    # not terminate the bridge (the previous version could silently exit after a while of inactivity)
    if hasattr(signal, 'SIGPIPE'): signal.signal(signal.SIGPIPE, signal.SIG_IGN)
    main()
