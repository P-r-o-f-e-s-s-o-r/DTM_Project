# GridSense: Laptop Day Hardware Integration Checklist (HANDOFF.md)

This document provides the exact, step-by-step field integration checklist for transitioning from the simulated data source (`fake_esp32.py`) to the physical ESP32 hardware node and real sensors.

> [!IMPORTANT]
> **Zero Downstream Code Changes**: The wire protocol (`voltage,current,renewable,hosting_index`), database schema, backend endpoints, and frontend dashboard are 100% frozen. When physical hardware is introduced, only the data **source** changes — everything else in the software stack runs untouched.

---

## 1. Physical Hardware Components Inventory

Ensure the following components from your kit are on hand:
- [x] **1 × ESP32 DevKit V1 (ESP32-WROOM-32)**
- [x] **1 × ZMPT101B AC Voltage Sensor Module**
- [x] **1 × SCT-013-000 100A/50mA Non-invasive AC Current Transformer**
- [x] **1 × 33 Ω, 1/4 W Burden Resistor** (converts 50mA secondary current to ~1.65V peak)
- [x] **1 × ACS712 30A Hall-Effect Current Sensor** (optional alternative)
- [x] **1 × 0.96" SSD1306 OLED Display (128×64, 4-pin I²C)**
- [x] **3 × 5 mm LEDs** (1 Green, 1 Yellow, 1 Red) + **3 × 220 Ω Resistors**
- [x] **4 × 10 kΩ Linear Potentiometers** (for dry bench testing before high-voltage AC connection)
- [x] **1 × 18650 Li-ion Battery + Holder + TP4056 Boost Module** (or 5V USB power adapter)
- [x] **Breadboard + Jumper Wires** (M-M, M-F, F-F)

---

## 2. Hardware Wiring Diagram & Pinouts

### 2.1 Complete Pin Mapping
| Component | Component Pin | ESP32 Pin | Notes |
|---|---|---|---|
| **ZMPT101B** | VCC | 5V (VIN) | Powered by 5V |
| | GND | GND | Common ground |
| | OUT | **GPIO 34** | ADC1_CH6 (Analog input) |
| **SCT-013-000** | Lead 1 | **GPIO 35** | ADC1_CH7 |
| | Lead 2 | GND (via 1.65V bias) | 33 Ω burden resistor across leads 1 & 2 |
| **ACS712 (Optional)** | OUT | **GPIO 32** | ADC1_CH4 |
| **SSD1306 OLED** | VCC | 3.3V or 5V | |
| | GND | GND | |
| | SDA | **GPIO 21** | ESP32 I2C Data |
| | SCL | **GPIO 22** | ESP32 I2C Clock |
| **Green LED (Safe)** | Anode (+) | **GPIO 25** | In series with 220 Ω resistor to GND |
| **Yellow LED (Caution)** | Anode (+) | **GPIO 26** | In series with 220 Ω resistor to GND |
| **Red LED (Critical)** | Anode (+) | **GPIO 27** | In series with 220 Ω resistor to GND |

### 2.2 SCT-013-000 Burden & Bias Circuit
The SCT-013-000 outputs a 50mA AC current. To read this on an ESP32 ADC:
1. Connect the **33 Ω burden resistor** across the two output wires of the 3.5mm jack.
2. Build a voltage divider with two equal 10k resistors from 3.3V to GND to create a **1.65V DC virtual ground** bias.
3. Connect one side of the burden resistor to this 1.65V point (with a 10µF stabilizing capacitor to GND).
4. Connect the other side of the burden resistor directly to **GPIO 35**.

---

## 3. Step-by-Step Laptop Integration Procedure

### Step 1: Find the Laptop's Local IP Address
1. Ensure the laptop and the ESP32 will be connected to the **same WiFi network** (or laptop mobile hotspot).
2. Open a terminal on the laptop:
   - **Windows**: Run `ipconfig` and note the `IPv4 Address` (e.g. `192.168.1.105`).
   - **macOS / Linux**: Run `ifconfig` or `ip a` (e.g. `192.168.1.105`).

### Step 2: Configure `firmware/main.cpp`
Open `gridsense/firmware/main.cpp` and update the three `TODO(LAPTOP):` placeholders near line 40:
```cpp
// UPDATE THESE THREE VALUES:
const char* WIFI_SSID     = "Your_WiFi_Network_Name";
const char* WIFI_PASSWORD = "Your_WiFi_Password";
const char* MQTT_BROKER   = "192.168.1.105"; // Your laptop's IP from Step 1
```

### Step 3: Flash Firmware to ESP32
Using **Arduino IDE** or **PlatformIO**:
1. Select Board: **ESP32 Dev Module** (or **DOIT ESP32 DEVKIT V1**).
2. Select COM Port corresponding to the plugged-in ESP32.
3. Install required libraries via Library Manager:
   - `PubSubClient` by Nick O'Leary
   - `Adafruit SSD1306` by Adafruit
   - `Adafruit GFX Library` by Adafruit
4. Click **Compile and Upload**.
5. Open the Serial Monitor at **115200 baud**.
6. Verify WiFi connects and shows:
   ```
   Connecting to WiFi: [SSID] ...
   WiFi connected! IP Address: 192.168.1.xxx
   Attempting MQTT connection to 192.168.1.105... Connected to broker.
   ```

### Step 4: Stop the Fake Simulator
On your laptop, terminate the simulator:
- If running `run_all.ps1`, simply stop `fake_esp32.py` or close its terminal window:
  ```powershell
  Get-Process -Name python | Where-Object { $_.CommandLine -like "*fake_esp32*" } | Stop-Process
  ```

### Step 5: Power On ESP32 & Verify End-to-End
1. Power the ESP32 via 5V USB or TP4056 battery module.
2. Observe the OLED display showing live Voltage, Current, Renewable %, and Hosting Index.
3. Observe the physical status LEDs (Green = Safe, Yellow = Caution, Red = Critical).
4. Check the laptop terminal running `mqtt_to_mysql.py`:
   ```
   [INFO] [mqtt_bridge] Saved to MySQL -> V: 231.40V | I: 28.50A | Ren: 48.50% | HI: 92.10
   ```
5. Open your browser dashboard at `http://localhost:5173`:
   - Notice the live numerical cards reflect the real hardware sensor readings.
   - The rolling chart plots real physical waveform measurements.
   - The AI Risk card displays live OpenRouter LLM risk assessments.

---

## 4. Bench Testing & Calibration (Safety First)

> [!WARNING]
> **High Voltage Safety**: Never connect the ZMPT101B directly to raw 230V mains without appropriate isolation, fuses, and electrical safety supervision.

### Safe Bench Calibration (Using the 10k Potentiometers):
1. Connect a 10k potentiometer between 3.3V and GND on the breadboard.
2. Connect the wiper to **GPIO 34** (Voltage simulation).
3. Connect a second potentiometer wiper to **GPIO 35** (Current simulation).
4. Turning the knobs allows full bench testing of:
   - Voltage swing from undervoltage (<214V) to overvoltage (>244V)
   - Current overload (>52A)
   - Visual verification of OLED readouts and LED transitions (Safe Green → Caution Yellow → Critical Red)
   - Live dashboard alert triggers on the laptop screen!
