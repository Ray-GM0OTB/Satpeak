"""Connect to a running SatPeak server like the phone does and print stream statistics.

    python ws_client.py http://100.101.102.103:8765 [seconds]
"""
import asyncio, json, sys, time
import aiohttp

URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765"
SECS = float(sys.argv[2]) if len(sys.argv) > 2 else 6


async def main():
    async with aiohttp.ClientSession() as s:
        r = await s.get(URL + "/")
        print("index:", r.status, len(await r.text()), "bytes")
        async with s.ws_connect(URL + "/ws") as ws:
            t0 = time.time(); n = 0; snr = []; rtt = []; last = {}
            await ws.send_json({"type": "ping", "t": time.perf_counter() * 1000})
            async for m in ws:
                d = json.loads(m.data)
                if d["type"] == "m":
                    n += 1; snr.append(d["snr"]); last = d
                elif d["type"] == "pong":
                    rtt.append(time.perf_counter() * 1000 - d["t"])
                elif d["type"] == "hello":
                    print("demo mode:", d["demo"])
                elif d["type"] == "err":
                    print("SDR error:", d["msg"])
                if time.time() - t0 > SECS:
                    break
            print(f"mode {last.get('mode')}  updates/s {n / (time.time() - t0):.1f}  "
                  f"snr {min(snr):.1f}..{max(snr):.1f} dB  beacon {last.get('off_khz')} kHz  "
                  f"adc {last.get('clip', 0) * 100:.0f}%  rtt {rtt[0] if rtt else -1:.1f} ms")

asyncio.run(main())
