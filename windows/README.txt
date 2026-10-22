SatPeak 1.0 - QO-100 dish peaking meter
=======================================

PlutoSDR on this PC measures the QO-100 beacon; your phone shows it live
(~25 updates/s) over Tailscale.

ON THE PC
  Start menu / desktop:  "SatPeak"            - real Pluto (found automatically on USB)
                         "SatPeak (demo mode)" - simulated signal, no Pluto needed
  The window shows the address for your phone, e.g.  100.101.102.103:8765
  First run: if Windows Firewall asks, click "Allow" (Private networks is enough
  for Tailscale) or the phone cannot connect.
  Only one program can use the Pluto at a time - close SDR Console, SATSAGEN,
  Linkbox etc. first.

ON THE PHONE (Android)
  Copy "Android app\SatPeak.apk" (in the SatPeak install folder, or Start menu >
  "SatPeak Android app (APK)") to the phone and open it. Allow "install unknown
  apps" for your file manager when asked. Then open SatPeak, tap the address
  button at the top and enter the PC address (e.g. 100.101.102.103:8765).
  Tailscale must be ON on the phone. The app keeps the screen on while open.
  Any phone (incl. iPhone) can also just use the browser:  http://<address>

PEAKING
  1. NB mode (CW beacon 10489.500) is the default; WB (DVB-S2 beacon 10491.500)
     is useful when that beacon is on air.
  2. Tap "Tone" - pitch rises with signal, so you can peak by ear.
  3. Sweep azimuth, then elevation, then LNB skew. "From best" goes green within
     0.5 dB of the best so far. "Reset best" after a big move.
  4. Use gain -/+ so the ADC badge never says CLIPPING.

OPTIONS (run SatPeak.exe from a command prompt)
  --lo 9739.0      LNB LO in MHz (default 9750)
  --uri ip:192.168.2.1   force a Pluto address (default: auto)
  --mode wb        start on the wideband beacon
  --gain 30        start gain in dB
  --port 8765      web port
  --smooth 1       no averaging (fastest response)
