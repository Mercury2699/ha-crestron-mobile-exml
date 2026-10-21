# Crestron Mobile EXML Integration for Home Assistant

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2024.1.0+-brightgreen.svg)](https://www.home-assistant.io)
[![Crestron 2-Series / 3-Series / 4-Series](https://img.shields.io/badge/Crestron-2--Series%20%7C%203--Series%20%7C%204--Series-blueviolet.svg)](https://www.crestron.com)

[中文说明文档 (Chinese Documentation)](README_zh.md)

A native, zero-recompilation Home Assistant custom integration for legacy and modern Crestron control systems (2-Series like PAC2/PAC2M/CP2E, 3-Series like CP3/MC3, and 4-Series) using the standard **Crestron Mobile EXML protocol** over TCP port **41790**.

---

## 🌟 Why This Integration?

Existing Home Assistant Crestron integrations (such as XSIG-based integrations) require Crestron SIMPL Windows programming software, proprietary Crestron dealer database licenses, and modifying + re-flashing the processor's `.spz` program file. For homeowners who bought a home with an existing Crestron system, or where the original integrator is unavailable, modifying the SIMPL project is virtually impossible. Modern Crestron Home (OS3/OS4) integrations do not work with classic 2-Series/3-Series processors.

**Crestron Mobile EXML solves this entirely:**
- **Zero Firmware Recompilation:** Works with your Crestron processor *as-is*. If your home had an iPad/iPhone running the classic "Crestron Mobile" app, the EXML interface is already running on port 41790.
- **Real-Time Push (`local_push`):** Persistent TCP connection with immediate bidirectional state updates (<50ms latency), no slow polling.
- **Simulated Smooth Dimming:** Many legacy D3Pro/SIMPL programs only expose Up/Down digital ramp joins instead of direct analog brightness levels. This integration provides real-time timed ramp control, enabling native Home Assistant and Apple HomeKit 0–100% brightness sliders!
- **Motorized Covers & Shades:** Supports 16-bit Crestron analog joins (0–65535 mapped to 0–100%) as well as open/close/stop digital joins.
- **Automated Configuration Tool:** Includes `tools/extract_crestron_config.py` to extract all join assignments from your processor's Mobile XML files into ready-to-paste Home Assistant YAML.

---

## 📋 Features

- [x] **Switches & Dimmer Lights**: Supports On/Off toggles, Up/Down dimming, and companion multi-gang joins.
- [x] **Fade-Out Anti-Bounce Guard**: Prevents HomeKit and Home Assistant UI flickering during Crestron hardware fade ramps.
- [x] **Motorized Shades / Drapes / Blinds**: Bi-directional position feedback and percentage adjustments.
- [x] **Auto Reconnection & Heartbeat**: Robust background watchdog ensures seamless recovery from network drops.
- [x] **HomeKit & Voice Assistant Ready**: Fully exposes entities to Apple Home (via HomeKit integration), Google Assistant, and Alexa.

---

## 📥 Installation

### Method 1: HACS (Recommended)

1. Open **Home Assistant** -> **HACS** -> **Integrations**.
2. Click the top-right three dots menu `⋮` and select **Custom repositories**.
3. Enter `https://github.com/Mercury2699/ha-crestron-mobile-exml` in the repository field, select category **Integration**, and click **Add**.
4. Search for **Crestron Mobile EXML**, click **Download**, and restart Home Assistant.

### Method 2: Manual Installation

1. Download the latest release `.zip` from GitHub.
2. Copy the `custom_components/crestron_mobile_exml` folder into your Home Assistant `<config_dir>/custom_components/` directory.
   ```
   config/
   └── custom_components/
       └── crestron_mobile_exml/
           ├── __init__.py
           ├── const.py
           ├── light.py
           ├── cover.py
           └── manifest.json
   ```
3. Restart Home Assistant.

---

## ⚙️ Configuration

Add the `crestron_mobile_exml` configuration block to your Home Assistant `configuration.yaml`:

```yaml
crestron_mobile_exml:
  host: 192.168.1.50         # IP address of your Crestron processor
  port: 41790                # Default Crestron Mobile EXML port
  passcode: "1234"           # Passcode set in Crestron Mobile configuration (often "1234")

  lights:
    # 1. Dimmable light with toggle and up/down ramp joins
    - name: "Living Room Chandelier"
      unique_id: "crestron_living_room_chandelier"
      toggle_join: 21
      up_join: 22
      down_join: 23
      ramp_time: 5.0           # Seconds to ramp from 0% to 100% (default: 5.0)

    # 2. Multi-gang / 3-way lighting load (with companion joins)
    - name: "Kitchen Main Light"
      unique_id: "crestron_kitchen_main"
      toggle_join: 31
      up_join: 32
      down_join: 33
      companion_toggle_joins: [34, 37]
      companion_up_joins: [35, 38]
      companion_down_joins: [36, 39]

    # 3. Simple On/Off switch (no dimming joins)
    - name: "Porch Accent Light"
      unique_id: "crestron_porch_accent"
      toggle_join: 50

  covers:
    # Motorized shade with analog position and optional digital commands
    - name: "Master Bedroom Shade"
      unique_id: "crestron_mbr_shade"
      analog_join: 10          # 16-bit analog join (0..65535)
      open_join: 101           # Optional digital pulse join to open
      close_join: 102          # Optional digital pulse join to close
      stop_join: 103           # Optional digital pulse join to stop
```

### Configuration Parameters

#### Main Hub Options

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `host` | string | **Yes** | — | IP address or hostname of the Crestron processor. |
| `port` | integer | No | `41790` | TCP port for Crestron Mobile EXML protocol. |
| `passcode` | string | No | `"1234"` | Crestron Mobile connection passcode. |
| `lights` | list | No | `[]` | List of light entities to configure. |
| `covers` | list | No | `[]` | List of cover/shade entities to configure. |

#### Light Options (`lights`)

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `name` | string | **Yes** | — | Friendly name of the light. |
| `toggle_join` | integer | **Yes** | — | Primary digital join used to toggle the light and observe state feedback. |
| `unique_id` | string | No | auto | Unique ID for Home Assistant entity registry. |
| `up_join` | integer | No | `None` | Digital join held to ramp brightness UP. |
| `down_join` | integer | No | `None` | Digital join held to ramp brightness DOWN. |
| `ramp_time` | float | No | `5.0` | Time (in seconds) for a full 0% to 100% brightness transition. |
| `companion_toggle_joins` | list[int] | No | `[]` | Additional digital joins linked to this load's state (e.g. multi-way keypads). |
| `companion_up_joins` | list[int] | No | `[]` | Companion up-ramp joins held together with `up_join`. |
| `companion_down_joins` | list[int] | No | `[]` | Companion down-ramp joins held together with `down_join`. |
| `linked_off_joins` | list[int] | No | `[]` | Additional joins pulsed when turning off this load (e.g. master room-off signals). |

#### Cover Options (`covers`)

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `name` | string | **Yes** | — | Friendly name of the cover/shade. |
| `analog_join` | integer | **Yes** | — | 16-bit analog join (0–65535) representing 0–100% position. |
| `unique_id` | string | No | auto | Unique ID for Home Assistant entity registry. |
| `open_join` | integer | No | `None` | Digital pulse join to open shade. |
| `close_join` | integer | No | `None` | Digital pulse join to close shade. |
| `stop_join` | integer | No | `None` | Digital pulse join to stop movement. |

---

## 🛠️ Extracting Joins from Your Crestron System

If you do not know which joins correspond to your lights and shades, you can extract them directly from the Crestron Mobile project files stored on your processor!

### Step 1: Download project files from processor via FTP

Most Crestron processors (PAC2, PAC2M, CP2E, CP3, etc.) run an embedded FTP server:

```bash
# Connect to your processor (default user: crestron or anonymous, empty password unless protected)
ftp 192.168.1.50
```

Navigate to the project directory:
- On 2-Series processors: `/HTML/iPad/` or `/HTML/iPhone/` (or `/SIMPL/HTML/...`)
- Download all `.xml` files or the project archive.

### Step 2: Run the extraction utility

Run the included extractor script:

```bash
# Analyze an extracted folder of XML files
python3 tools/extract_crestron_config.py --dir /path/to/extracted/ipad_project/

# Or analyze a downloaded project zip file directly
python3 tools/extract_crestron_config.py --zip /path/to/Crestron_iPad_Project.zip
```

The script will parse all subpages, detect light switches, dimmers, and motorized shades, and print a formatted YAML block ready to paste into your `configuration.yaml`.

---

## 🔍 Testing Connectivity

Before setting up Home Assistant, you can verify network connectivity to the Crestron EXML port from your terminal:

```bash
# Test if port 41790 is accessible
nc -zv 192.168.1.50 41790
```

Expected output:
```
Connection to 192.168.1.50 port 41790 [tcp] succeeded!
```

---

## ❓ Frequently Asked Questions (FAQ)

### 1. Does this work alongside the original Crestron touchscreens and keypads?
**Yes.** Crestron's control architecture handles multiple simultaneous clients. Wall keypads, Crestron touchscreens, the Crestron Mobile app, and Home Assistant will all stay in real-time sync with two-way feedback.

### 2. Can I use Apple Home / Siri with this?
**Yes.** Once entities appear in Home Assistant, add the native [HomeKit Bridge](https://www.home-assistant.io/integrations/homekit/) integration in Home Assistant. All your Crestron lights and shades will appear instantly in the Apple Home app on iPhone, iPad, Mac, and Apple Watch.

### 3. What if my dimmers use direct analog joins instead of Up/Down joins?
If your Crestron SIMPL project exposes analog joins for lighting levels, you can configure them or contribute an analog light platform PR. Most residential D3Pro setups utilize Up/Down ramp buttons for mobile interfaces.

---

## 🛡️ Security Best Practices

- Always keep your Crestron processor on an isolated, local IoT VLAN or subnet.
- **Never expose port 41790 or port 21 (FTP) to the public Internet.** If remote access is needed, use Home Assistant Cloud (Nabu Casa), WireGuard, or Apple HomeKit Home Hub.

---

## 📄 License

This project is licensed under the [Apache License 2.0](LICENSE).

---

## ⚠️ Disclaimer

This project is an independent community open-source project and is **not** affiliated with, endorsed by, or associated with **Crestron Electronics, Inc.** *Crestron*, *SIMPL*, *D3Pro*, *Cresnet*, and *Crestron Mobile* are trademarks or registered trademarks of Crestron Electronics, Inc.
