"""Wideband sweep of the LNB IF (690-810 MHz) to find the QO-100 beacons.

    python sweep.py [gain_dB]      -> writes sweep.csv (IF MHz, dB) and prints the strongest peaks
"""
import os, sys
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "server"))
import adi
import qo100_peaker as q

uri = q.find_pluto_uri("auto")
sdr = adi.Pluto(uri)
sdr.gain_control_mode_chan0 = "manual"
sdr.rx_hardwaregain_chan0 = float(sys.argv[1]) if len(sys.argv) > 1 else 40
fs, n = 20e6, 8192
sdr.sample_rate = int(fs); sdr.rx_rf_bandwidth = int(18e6); sdr.rx_buffer_size = n * 8
rows = []
for fc in np.arange(690e6, 811e6, 12e6):
    sdr.rx_lo = int(fc)
    for _ in range(2):
        sdr.rx()
    x = np.asarray(sdr.rx()).reshape(8, n) * np.hanning(n)
    p = np.fft.fftshift((np.abs(np.fft.fft(x, axis=1)) ** 2).mean(0))
    idx = np.arange(n) - n // 2
    keep = (np.abs(idx) < 0.4 * n) & (np.abs(idx) > 8)
    f = idx * fs / n + fc
    rows += list(zip(f[keep] / 1e6, 10 * np.log10(p[keep] + 1e-20)))
a = np.array(rows)
np.savetxt("sweep.csv", a, delimiter=",", fmt="%.4f", header=f"uri={uri}")
floor = np.median(a[:, 1])
top = a[np.argsort(a[:, 1])[::-1]]
shown = []
for f, db in top:
    if all(abs(f - s) > 0.05 for s in shown):
        shown.append(f)
        print(f"  {f:9.4f} MHz  {db - floor:5.1f} dB above floor")
    if len(shown) >= 8:
        break
print("expected with LO 9750: NB CW beacon 739.500, WB beacon 741.500 MHz")
