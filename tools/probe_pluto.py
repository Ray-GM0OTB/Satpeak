"""Check that libiio sees the Pluto and measure both beacons once.  python probe_pluto.py"""
import os, sys, time, types
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "server"))
import iio
import qo100_peaker as q

print("python", sys.version.split()[0], " libiio", iio.version)
uri = q.find_pluto_uri("auto")
print("using", uri)
src = q.PlutoSource(uri)
args = types.SimpleNamespace(mode="wb", gain=40, lo=9750.0, smooth=1.0, rate=25, demo=False)
m = q.Meter(args, src, lambda x: None)
for mode in ("nb", "wb"):
    m.mode = mode
    m.setup()
    t = time.time(); res = [m.analyse(src.read()) for _ in range(25)]; dt = (time.time() - t) / 25
    snr = [r["snr"] for r in res]
    print(f"{mode}: snr mean {sum(snr) / len(snr):.1f} dB (min {min(snr):.1f} max {max(snr):.1f})  "
          f"adc {res[-1]['clip'] * 100:.0f}%  {1 / dt:.1f} reads/s  beacon offset {res[-1].get('off_khz')} kHz")
print("PROBE PASS")
