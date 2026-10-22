"""Self-test: start qo100_peaker.py --demo on a spare port, connect like the phone does, check the stream."""
import asyncio, json, os, subprocess, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
PORT = 8799


async def client():
    import aiohttp
    async with aiohttp.ClientSession() as s:
        for _ in range(40):
            try:
                r = await s.get(f"http://127.0.0.1:{PORT}/")
                page = await r.text()
                break
            except Exception:
                await asyncio.sleep(0.5)
        else:
            raise SystemExit("server never came up")
        print("index.html:", r.status, len(page), "bytes")
        async with s.ws_connect(f"http://127.0.0.1:{PORT}/ws") as ws:
            t0 = time.time(); n = 0; snr = []; rtts = []; d = {}
            await ws.send_json({"type": "ping", "t": time.perf_counter() * 1000})
            async for m in ws:
                d = json.loads(m.data)
                if d["type"] == "m":
                    n += 1; snr.append(d["snr"])
                    if n == 50:
                        await ws.send_json({"type": "cmd", "mode": "wb"})
                elif d["type"] == "pong":
                    rtts.append(time.perf_counter() * 1000 - d["t"])
                elif d["type"] == "err":
                    print("server error:", d["msg"])
                if time.time() - t0 > 8:
                    break
            rate = n / (time.time() - t0)
            print(f"updates/s: {rate:.1f}  snr range {min(snr):.1f}..{max(snr):.1f} dB  "
                  f"local rtt {rtts[0] if rtts else -1:.1f} ms  last mode {d.get('mode')}")
            return rate > 10 and r.status == 200


p = subprocess.Popen([sys.executable, os.path.join(HERE, "qo100_peaker.py"), "--demo", "--port", str(PORT),
                      "--host", "127.0.0.1"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
ok = False
try:
    ok = asyncio.run(client())
finally:
    p.terminate()
    try:
        out = p.communicate(timeout=5)[0]
    except Exception:
        out = ""
    print("--- server output ---\n" + (out or "").strip())
print("SELFTEST", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
