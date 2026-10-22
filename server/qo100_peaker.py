#!/usr/bin/env python3
"""
QO-100 Dish Peaker
==================
PlutoSDR  ->  FFT beacon SNR  ->  WebSocket  ->  phone browser (over Tailscale)

  python qo100_peaker.py                 # finds the Pluto automatically (USB or network)
  python qo100_peaker.py --uri ip:192.168.2.1
  python qo100_peaker.py --demo          # simulated signal, to test the phone UI

Then on your phone (Tailscale connected):  http://<pc-tailscale-name>:8765
"""
import argparse
import asyncio
import json
import math
import os
import pathlib
import queue
import subprocess
import sys
import threading
import time

import numpy as np
from aiohttp import web

FROZEN = getattr(sys, "frozen", False)
if FROZEN:  # PyInstaller build: index.html and the libiio DLLs sit next to SatPeak.exe
    HERE = pathlib.Path(getattr(sys, "_MEIPASS", os.path.dirname(sys.executable)))
    os.environ["PATH"] = str(HERE) + os.pathsep + os.environ.get("PATH", "")
    try:
        os.add_dll_directory(str(HERE))
    except Exception:
        pass
else:
    HERE = pathlib.Path(__file__).resolve().parent
VERSION = "1.0.0"

# --------------------------------------------------------------------------
# Beacon definitions (downlink RF, Hz)
# --------------------------------------------------------------------------
MODES = {
    # DVB-S2 2 MS/s wideband beacon: ~2.7 MHz wide, strong, tolerant of LNB drift.
    # Best for finding the satellite and coarse peaking.
    "wb": dict(
        label="WB beacon 10491.500",
        beacon=10491.500e6,
        centre_offset=0.0,
        fs=5.0e6, rf_bw=5.0e6, fft=4096, frames=4,
        sig_half=0.9e6,        # integrate |f - beacon| < 0.9 MHz
        beacon_half=1.45e6,    # noise floor taken from bins outside this
    ),
    # Lower CW beacon of the narrowband transponder: precise final peaking/skew.
    "nb": dict(
        label="NB CW beacon 10489.500",
        beacon=10489.500e6,
        centre_offset=+250e3,  # tune to NB transponder centre (10489.750)
        fs=2.5e6, rf_bw=2.0e6, fft=16384, frames=2,
        search=150e3,          # hunt for the CW peak within +/-150 kHz (LNB error)
    ),
}

FULL_SCALE = 2048.0   # Pluto 12-bit ADC
DISPLAY_POINTS = 300


# --------------------------------------------------------------------------
# Sample sources
# --------------------------------------------------------------------------
def find_pluto_uri(uri):
    """'auto' -> first PlutoSDR found by libiio (USB preferred), else the network default."""
    if uri != "auto":
        return uri
    import iio
    try:
        ctxs = iio.scan_contexts()
    except Exception as e:
        print("libiio scan failed:", e)
        ctxs = {}
    found = [u for u, d in ctxs.items() if "pluto" in (d or "").lower()
             or "0456:b673" in (d or "").lower()]
    found.sort(key=lambda u: not u.startswith("usb:"))
    for u in ctxs:
        print("  found:", u, "-", ctxs[u])
    return found[0] if found else "ip:192.168.2.1"


class PlutoSource:
    def __init__(self, uri):
        import adi  # pyadi-iio
        uri = find_pluto_uri(uri)
        print("Opening Pluto at", uri)
        self.sdr = adi.Pluto(uri)
        self.sdr.gain_control_mode_chan0 = "manual"   # AGC would hide the peak!

    def configure(self, if_hz, fs, rf_bw, nsamp, gain, **_):
        s = self.sdr
        try:
            s.rx_destroy_buffer()
        except Exception:
            pass
        s.sample_rate = int(fs)
        s.rx_rf_bandwidth = int(rf_bw)
        s.rx_lo = int(round(if_hz))
        s.rx_buffer_size = int(nsamp)
        s.gain_control_mode_chan0 = "manual"
        s.rx_hardwaregain_chan0 = float(gain)
        try:
            # One kernel buffer = freshest samples, minimal latency
            s._rxadc.set_kernel_buffers_count(1)
        except Exception:
            pass
        for _ in range(3):        # let LO/filters settle
            s.rx()

    def set_gain(self, gain):
        self.sdr.rx_hardwaregain_chan0 = float(gain)

    def read(self):
        return np.asarray(self.sdr.rx())


class DemoSource:
    """Fake signal: the 'dish' sweeps across the satellite every ~25 s."""

    def __init__(self):
        self.rng = np.random.default_rng()
        self.t0 = time.monotonic()

    def configure(self, if_hz, fs, rf_bw, nsamp, gain, mode, centre_offset, **_):
        self.fs, self.n, self.gain, self.mode = fs, int(nsamp), gain, mode
        self.co = centre_offset
        self.ph = 0.0

    def set_gain(self, gain):
        self.gain = gain

    def read(self):
        n, fs = self.n, self.fs
        t = time.monotonic() - self.t0
        point = math.exp(-(2.2 * math.sin(2 * math.pi * t / 25)) ** 2)  # 0..1
        lvl = 10 ** ((self.gain - 40) / 20) * 25
        x = lvl * (self.rng.standard_normal(n) + 1j * self.rng.standard_normal(n))
        f = np.fft.fftfreq(n, 1 / fs)
        if self.mode == "wb":
            band = (np.abs(f + self.co) < 1.35e6).astype(float)
            w = np.fft.ifft(np.fft.fft(self.rng.standard_normal(n)
                                       + 1j * self.rng.standard_normal(n)) * band)
            x += w * lvl * 4.5 * point
            cw_f = -2.0e6 - self.co
        else:
            cw_f = -self.co + 3.2e3          # pretend LNB is 3.2 kHz off
        k = np.arange(n)
        cw_amp = 3.0 if self.mode == "nb" else 60.0
        x += lvl * cw_amp * point * np.exp(1j * (self.ph + 2 * np.pi * cw_f * k / fs))
        self.ph += 2 * np.pi * cw_f * n / fs
        time.sleep(n / fs)
        return np.clip(x.real, -2047, 2047) + 1j * np.clip(x.imag, -2047, 2047)


# --------------------------------------------------------------------------
# Measurement thread
# --------------------------------------------------------------------------
class Meter(threading.Thread):
    def __init__(self, args, src, publish):
        super().__init__(daemon=True)
        self.args, self.src, self.publish = args, src, publish
        self.cmds = queue.Queue()
        self.mode, self.gain = args.mode, float(args.gain)
        self.lo = args.lo * 1e6

    # -- setup ------------------------------------------------------------
    def setup(self):
        m = self.m = MODES[self.mode]
        n, fs = m["fft"], m["fs"]
        self.nsamp = n * m["frames"]
        self.win = np.hanning(n).astype(np.float32)
        idx = np.arange(n) - n // 2
        self.fb = idx * fs / n + m["centre_offset"]          # Hz from nominal beacon
        dc = np.abs(idx) <= 4
        valid = ~dc & (np.abs(idx) < 0.45 * n)                # drop DC + filter skirts
        if self.mode == "wb":
            self.sig_mask = valid & (np.abs(self.fb) < m["sig_half"])
            self.noise_mask = valid & (np.abs(self.fb) > m["beacon_half"])
            lo_, hi_ = self.fb[valid].min(), self.fb[valid].max()
            self.shade = [-m["sig_half"] / 1e3, m["sig_half"] / 1e3]
        else:
            self.sig_mask = valid & (np.abs(self.fb) <= m["search"])
            self.noise_mask = valid
            lo_, hi_ = -m["search"], m["search"]
            self.shade = None
        self.disp_mask = valid & (self.fb >= lo_) & (self.fb <= hi_)
        self.disp_x = [lo_ / 1e3, hi_ / 1e3]
        self.noise_cal = self._calibrate()
        self.ema = None
        if_hz = m["beacon"] + m["centre_offset"] - self.lo
        self.src.configure(if_hz=if_hz, fs=fs, rf_bw=m["rf_bw"], nsamp=self.nsamp,
                           gain=self.gain, mode=self.mode,
                           centre_offset=m["centre_offset"])
        print(f"[{self.mode}] {m['label']}  IF {if_hz/1e6:.4f} MHz  "
              f"fs {fs/1e6:g} MS/s  gain {self.gain:g} dB")

    def _spectrum(self, iq):
        n = self.m["fft"]
        k = len(iq) // n
        x = iq[: k * n].reshape(k, n) * self.win
        return np.fft.fftshift(np.abs(np.fft.fft(x, axis=1)) ** 2, axes=1).mean(axis=0)

    def _noise_floor(self, spec):
        return np.percentile(spec[self.noise_mask], 25)

    def _calibrate(self):
        """Correct the 25th-percentile noise estimate back to the true mean."""
        rng = np.random.default_rng(1)
        r = []
        for _ in range(8):
            z = rng.standard_normal(self.nsamp) + 1j * rng.standard_normal(self.nsamp)
            s = self._spectrum(z)
            r.append(s[self.noise_mask].mean() / self._noise_floor(s))
        return float(np.mean(r))

    # -- analysis ---------------------------------------------------------
    def analyse(self, iq):
        spec = self._spectrum(iq)
        noise = self._noise_floor(spec) * self.noise_cal
        out = {}
        if self.mode == "wb":
            sig = spec[self.sig_mask].mean()
        else:
            sub = np.where(self.sig_mask)[0]
            i = sub[np.argmax(spec[sub])]
            sig = spec[i]
            # parabolic interpolation for the beacon frequency
            a, b, c = np.log(spec[i - 1:i + 2] + 1e-30)
            d = 0.5 * (a - c) / (a - 2 * b + c) if (a - 2 * b + c) != 0 else 0.0
            df = self.m["fs"] / self.m["fft"]
            out["off_khz"] = round((self.fb[i] + d * df) / 1e3, 2)
        snr = 10 * math.log10(max(sig / noise, 1e-3))
        a = self.args.smooth
        self.ema = snr if self.ema is None else a * snr + (1 - a) * self.ema

        db = 10 * np.log10(spec[self.disp_mask] / noise + 1e-12)
        pts = DISPLAY_POINTS
        if len(db) > pts:
            db = db[: len(db) // pts * pts].reshape(pts, -1).max(axis=1)
        clip = float(max(np.abs(iq.real).max(), np.abs(iq.imag).max()) / FULL_SCALE)

        out.update(type="m", mode=self.mode, gain=self.gain,
                   snr=round(self.ema, 2), raw=round(snr, 2),
                   clip=round(clip, 3), spec=np.round(db, 1).tolist(),
                   x=self.disp_x, shade=self.shade)
        return out

    # -- commands from phone ----------------------------------------------
    def _handle_cmds(self):
        reconf = False
        while not self.cmds.empty():
            c = self.cmds.get_nowait()
            if "gain" in c:
                self.gain = float(min(70, max(0, self.gain + float(c["gain"]))))
                self.src.set_gain(self.gain)
            if c.get("mode") in MODES and c["mode"] != self.mode:
                self.mode, reconf = c["mode"], True
        if reconf:
            self.setup()

    def run(self):
        self.setup()
        period = 1.0 / self.args.rate
        while True:
            t0 = time.monotonic()
            try:
                self._handle_cmds()
                msg = self.analyse(self.src.read())
            except Exception as e:  # keep the server alive, tell the phone
                self.publish({"type": "err", "msg": str(e)})
                time.sleep(1)
                continue
            self.publish(msg)
            dt = time.monotonic() - t0
            if dt < period:
                time.sleep(period - dt)


# --------------------------------------------------------------------------
# Web server: latest-value-only push, so a slow link never builds a backlog
# --------------------------------------------------------------------------
class Hub:
    def __init__(self):
        self.latest = None
        self.clients = {}

    def update(self, text):
        self.latest = text
        for ev in self.clients.values():
            ev.set()


def build_app(args, meter, hub):
    async def index(_):
        return web.FileResponse(HERE / "index.html",
                                headers={"Cache-Control": "no-store"})

    async def ws_handler(request):
        ws = web.WebSocketResponse(heartbeat=10, compress=False)
        await ws.prepare(request)
        ev = asyncio.Event()
        hub.clients[ws] = ev
        await ws.send_json({"type": "hello", "demo": args.demo, "lo": args.lo,
                            "rate": args.rate,
                            "modes": {k: v["label"] for k, v in MODES.items()}})

        async def sender():
            while not ws.closed:
                await ev.wait()
                ev.clear()
                if hub.latest:
                    await ws.send_str(hub.latest)

        task = asyncio.create_task(sender())
        try:
            async for msg in ws:
                if msg.type != web.WSMsgType.TEXT:
                    continue
                d = json.loads(msg.data)
                if d.get("type") == "ping":
                    await ws.send_json({"type": "pong", "t": d.get("t")})
                elif d.get("type") == "cmd":
                    meter.cmds.put(d)
        finally:
            task.cancel()
            hub.clients.pop(ws, None)
        return ws

    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_get("/ws", ws_handler)
    return app


def tailscale_ip():
    for exe in (r"C:\Program Files\Tailscale\tailscale.exe", "tailscale"):
        try:
            r = subprocess.run([exe, "ip", "-4"], capture_output=True, text=True, timeout=4,
                               creationflags=0x08000000 if os.name == "nt" else 0)
            ip = r.stdout.strip().splitlines()
            if ip:
                return ip[0].strip()
        except Exception:
            pass
    return None


def main():
    p = argparse.ArgumentParser(description="QO-100 dish peaking meter")
    p.add_argument("--uri", default="auto", help="Pluto URI: auto (default), usb:x.y.z or ip:192.168.2.1")
    p.add_argument("--lo", type=float, default=9750.0, help="LNB LO in MHz (default 9750)")
    p.add_argument("--gain", type=float, default=40, help="Pluto RX gain dB (manual)")
    p.add_argument("--mode", choices=MODES, default="nb", help="start beacon (nb = CW beacon, wb = DVB-S2 beacon)")
    p.add_argument("--rate", type=float, default=25, help="updates per second")
    p.add_argument("--smooth", type=float, default=0.35,
                   help="EMA factor 0-1 (1 = no smoothing, faster but jumpier)")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--demo", action="store_true", help="simulated signal, no Pluto")
    args = p.parse_args()

    if args.demo:
        src = DemoSource()
    else:
        try:
            src = PlutoSource(args.uri)
        except Exception as e:
            raise SystemExit(f"Could not open the Pluto ({args.uri}): {e}\n"
                             "  - Is the Pluto plugged in?\n"
                             "  - Close other SDR programs using it (SDR Console, SATSAGEN, Linkbox...)\n"
                             "  - Or start 'SatPeak (demo mode)' to test without the Pluto.")

    hub = Hub()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def publish(obj):
        text = json.dumps(obj, separators=(",", ":"))
        loop.call_soon_threadsafe(hub.update, text)

    meter = Meter(args, src, publish)
    app = build_app(args, meter, hub)
    runner = web.AppRunner(app)
    loop.run_until_complete(runner.setup())
    try:
        loop.run_until_complete(web.TCPSite(runner, args.host, args.port).start())
    except OSError as e:
        raise SystemExit(f"Port {args.port} is already in use - is SatPeak already running? ({e})")
    meter.start()
    ts = tailscale_ip()
    print()
    print(f"  SatPeak {VERSION}  -  QO-100 dish peaker" + ("   [DEMO MODE]" if args.demo else ""))
    print("  ---------------------------------------------------")
    if ts:
        print(f"  Phone app / browser address:  {ts}:{args.port}")
        print(f"  (browser: http://{ts}:{args.port})")
    else:
        print(f"  Tailscale not found - use this PC's IP, port {args.port}")
    print("  Close this window (or Ctrl+C) to stop.")
    print()
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    if FROZEN:
        try:
            main()
        except SystemExit as e:
            if e.code not in (0, None):
                print("\nERROR:", e.code)
                input("\nPress Enter to close...")
        except Exception as e:
            import traceback
            traceback.print_exc()
            input("\nPress Enter to close...")
    else:
        main()
