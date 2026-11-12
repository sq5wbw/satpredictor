# SAT° Predictor

**Amateur radio satellite pass predictor that runs entirely in your browser.**

👉 **Live:** [sq5wbw.github.io/satpredictor](https://sq5wbw.github.io/satpredictor/)

SAT° Predictor shows the upcoming passes of amateur radio satellites over your grid locator for the next 24 hours: when each satellite rises, how high it climbs, where to point your antenna and which frequencies to use. On desktop it can also keep **SDR++** tuned to the satellite and correct the **Doppler shift** for the whole pass.

It is a single HTML file – no account, no installation, nothing to build.

## Features

### Pass list
- **Next 24 hours** of passes: AOS time, duration, maximum elevation and azimuth path (AOS → max → LOS). The nearest passes come first (20 on desktop, 10 on mobile); **Show next 10 passes** loads more.
- **Countdown** to AOS for every pass, down to the second in the last minute.
- **Live passes** are marked **QRV**, pulse gently, show the live elevation and azimuth (with arrows showing whether they are rising or setting) and have a progress bar that drains from AOS to LOS.
- **Mode filters** – SSB (linear transponders), FM and DIG (packet, APRS, SSTV, telemetry). At least one mode always stays on.
- **Minimum elevation** slider (0–45°) hides low passes that are hard to work.

### Pass details
- Click a pass to see its **AOS / MAX / LOS** times, **downlink, uplink, beacon, mode and notes** (for example SO-50’s 74.4 Hz arming tone) and the age of its orbital data.
- **Sky plot** with the track, AOS / max / LOS marks and the satellite’s current position (pulsing while it is up).
- On desktop you can **drag the sky plot** to match the way you are facing; double-click puts north back on top.
- **Phone compass** – on a phone turn on **N°** and the sky plot follows the phone’s magnetometer, so the plot matches the real sky. Magnetic declination is calculated for your locator with the World Magnetic Model (WMM2025).

### Start screen
- Enter your **Maidenhead locator** (4 or 6 characters, e.g. `KO02` or `KO02OC`) or use **Use my location (GPS)** – the locator is calculated and the pass list opens straight away.
- Open the start screen again at any time with the **S°** logo or the **Grid** field.

### More
- **ISS ticker** – next ISS pass, or only “ISS is above your sky now!” while it is passing, mixed with a few ISS facts.
- **Satellites** tab – choose which satellites to watch (◯ on, ✕ off). At least one satellite always stays on.
- **Light and dark mode**, **English and Polish** – all remembered in your browser.
- Works on desktop, tablet and phone.

Your locator and settings are stored only in your own browser.

## SDR++ Doppler tuning (desktop)

**Tune** in an expanded pass sets SDR++ to the satellite’s downlink frequency and corrects the Doppler shift for the whole pass, from AOS to LOS. For **FM satellites** the frequency is known. For **linear transponders** SDR++ starts in the middle of the passband – click a QSO on the SDR++ waterfall and SAT° Predictor will hold that station for the rest of the pass, correcting the Doppler shift as the satellite moves.

The browser cannot talk to SDR++ directly, so a tiny bridge runs on your computer:

```
SAT° Predictor (browser)  ⇄  WebSocket ws://127.0.0.1:4533  ⇄  sdrpp-bridge.py  ⇄  TCP 4532  ⇄  SDR++ Rigctl server
```

### What you need
- A desktop computer (Windows, macOS or Linux) with **SDR++** installed.
- **Python 3.8 or newer** – on macOS and Linux it is usually already installed; on Windows get it from [python.org](https://www.python.org/downloads/) (tick *Add Python to PATH* in the installer). No extra Python packages are needed.
- **Chrome, Edge or Firefox.** The browser may ask once for permission to access devices on your local network – allow it.

### Step 1 – enable the Rigctl server in SDR++
1. Start SDR++ and open **Module Manager** (in the menu on the left).
2. In the field at the bottom choose the module type **`rigctl_server`**, give it a name (e.g. `Rigctl Server`) and click **+**.
3. A **Rigctl Server** panel appears in the menu. Leave the address `localhost` and port **`4532`**.
4. Tick **Tuning** – without it SDR++ will not accept frequency changes from outside.
5. Optionally tick **Listen on startup**, so you do not have to start the server every time.
6. Click **Start**. The status changes to **Listening**.

### Step 2 – download and run the bridge
1. Download **[`sdrpp-bridge.py`](https://sq5wbw.github.io/satpredictor/sdrpp-bridge.py)** (also in the **SDR++ Rigctl** tab at the bottom of the page) and save it, for example, in your Downloads folder.
2. Open a terminal:
   - **macOS:** Terminal (Applications → Utilities),
   - **Windows:** Command Prompt or PowerShell,
   - **Linux:** any terminal.
3. Go to the folder with the file and run the bridge:
   ```
   cd Downloads
   python3 sdrpp-bridge.py
   ```
   On Windows use `python sdrpp-bridge.py` if `python3` is not found.
4. You should see:
   ```
   SAT° Predictor ⇄ SDR++ bridge running: page connects to ws://127.0.0.1:4533, SDR++ Rigctl at 127.0.0.1:4532. Stop: Ctrl+C.
   Connected to SDR++ (Rigctl 127.0.0.1:4532).
   ```
   If it says *Waiting for SDR++*, go back to step 1 – the Rigctl server is not listening yet. The bridge keeps trying by itself.
5. Leave the terminal window open while you operate. Stop the bridge with **Ctrl+C**.

### Step 3 – tune a pass
1. Open [SAT° Predictor](https://sq5wbw.github.io/satpredictor/) on the same computer. Within a few seconds the terminal shows *SAT° Predictor page connected*.
2. Expand a pass and click **Tune** once the satellite is above the horizon. Before AOS the button only shakes and shows *Available from AOS …*.
3. The button changes to **Tuning** and SDR++ follows the satellite. Set the demodulator mode (FM, USB, …) in SDR++ yourself – the bridge only changes the frequency.
4. Linear transponder: click the QSO you want on the SDR++ waterfall – the bridge notices the change and keeps that station in tune.
5. Tuning stops by itself at LOS, or click **Tuning** again to stop.

The terminal shows everything that happens, for example:
```
▶ Tune AO-91: 145.960000 MHz (fixed frequency), pass 20:39–20:50.
  AOS AO-91 – Doppler correction running.
  AO-91: SDR++ → 145.962490 MHz  (Doppler +2.490 kHz)
  Retuned in SDR++ to 145.901234 MHz – holding this station (145.898689 MHz on the satellite).
■ Stopped tuning AO-91 (LOS).
```

The Doppler correction runs in the bridge, so it keeps working when the browser tab is in the background or the window is small. It stops when the page is closed.

### Bridge options
```
python3 sdrpp-bridge.py --help
  --rig-host 127.0.0.1   SDR++ Rigctl server address
  --rig-port 4532        SDR++ Rigctl server port
  --port 4533            WebSocket port the page connects to
  --allow-origin URL     allow another copy of SAT° Predictor (can be given several times)
  --quiet                do not print every frequency correction
```
The bridge only accepts connections from this computer and only from `sq5wbw.github.io` (or a copy opened from disk). Use `--allow-origin` if you host your own copy.

### Troubleshooting
- **“SDRPP-Bridge must be running.”** next to Tune – start the bridge (step 2) and wait a few seconds.
- **“Start the Rigctl server in SDR++.”** – the bridge runs, but SDR++ is not listening (step 1).
- **The frequency does not change** – tick **Tuning** in the Rigctl Server panel; the terminal then reports that SDR++ rejected the change.
- **Cannot start the bridge on port 4533** – the bridge is already running in another window.
- **Tune is not shown on a tablet or phone** – this feature is desktop only.

## Orbital data (TLE)

Orbital data comes from [CelesTrak](https://celestrak.org/) (the *amateur* group plus individual satellites by NORAD number) and [AMSAT](https://www.amsat.org/tle/current/nasabare.txt).

To respect CelesTrak’s [usage policy](https://celestrak.org/usage-policy.php), visitors do not download from CelesTrak themselves. A GitHub Action (`.github/workflows/tle.yml` running `scripts/update-tle.mjs`) downloads the data **four times a day** and saves it as `tle.txt` next to `index.html`; the page reads that file from its own server. The list of satellites is taken from `index.html`, so adding a satellite there is enough. If CelesTrak refuses a download, the action stops asking, keeps the previous data and GitHub sends an e-mail.

CelesTrak is used directly by the page only as a fallback when `tle.txt` is not available (for example when the page is opened from disk) – with a single request and a 2-hour pause after any refusal.

In the **TLE data** tab you can see the age of the data, refresh it, download the AMSAT file or load your own TLE file.

## Satellites and frequencies

The satellite list (42 satellites) and NORAD numbers were checked against the AMSAT TLE distribution. Frequencies come from the [AMSAT frequency lists](https://www.amsat.org/live-fm-satellites/) and the [JE9PEL satellite list](https://www.ne.jp/asahi/hamradio/je9pel/satslist.htm). Satellite status changes often, so check [AMSAT Live OSCAR Satellite Status](https://www.amsat.org/status/) before operating. Each NORAD number links to the satellite’s page on [N2YO](https://www.n2yo.com/).

To add or change a satellite, edit the `SATS` list near the top of the second `<script>` block in `index.html` – one line per satellite with its name, NORAD number, mode and frequencies. After pushing the change, the TLE action updates `tle.txt` automatically.

## Repository

| File | Purpose |
|---|---|
| `index.html` | the whole application |
| `sdrpp-bridge.py` | SDR++ Doppler bridge (run on your computer) |
| `tle.txt` | orbital data, updated by the GitHub Action – do not edit by hand |
| `.github/workflows/tle.yml` | schedule of the TLE update (every 6 hours, on changes to `index.html`, or manually: **Actions → Aktualizacja danych TLE → Run workflow**) |
| `scripts/update-tle.mjs` | downloads the TLE data for the action |

The action needs **Settings → Actions → General → Workflow permissions → Read and write permissions** to save `tle.txt`.

## Running locally

Download `index.html` and open it in a browser. Without `tle.txt` next to it the page downloads the data from CelesTrak (see above). The phone compass and GPS need the page to be served over **https** (such as GitHub Pages); on iPhone and iPad the browser asks for permission each time the compass is turned on.

## Technology

- One self-contained HTML file: HTML, CSS and plain JavaScript, no build step.
- Orbit propagation with [satellite.js](https://github.com/shashwatak/satellite-js) (SGP4, MIT license), embedded in the file.
- Magnetic declination from the [World Magnetic Model WMM2025](https://www.ncei.noaa.gov/products/world-magnetic-model) (NOAA/NGA, public domain), valid until the end of 2029.
- Font: [Recursive](https://www.recursive.design/) from Google Fonts, with a system font fallback.
- SDR++ bridge: Python 3 standard library only.

## Credits

SAT° Predictor was written from scratch as a browser-only tool by SQ5WBW, with the help of AI (Claude by Anthropic).

Thanks to CelesTrak, AMSAT, JE9PEL and N2YO for the data that makes this possible.

---

© SAT° Predictor by SQ5WBW · 73!
