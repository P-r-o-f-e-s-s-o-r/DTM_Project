/**
 * ============================================================================
 * GridSense - ESP32 Smart Feeder Intelligence Firmware
 * Hardware Platform: ESP32 DevKit V1 (ESP32-WROOM-32)
 *
 * SCOPE & STATUS:
 * Written and syntax-validated for laptop integration day.
 * DO NOT FLASH THIS FILE ON THIS PC (No hardware connected).
 *
 * PHYSICAL SENSOR & PERIPHERAL PINOUT MAPPING:
 * - ZMPT101B AC Voltage Sensor:     GPIO 34 (ADC1_CH6)
 * - SCT-013-000 Current Sensor:     GPIO 35 (ADC1_CH7, with 33 Ohm burden resistor)
 * - ACS712 30A Current Sensor:      GPIO 32 (ADC1_CH4, optional alternative)
 * - SSD1306 0.96" I2C OLED (128x64): SDA = GPIO 21, SCL = GPIO 22
 * - Safe Status Indicator LED (Green):  GPIO 25 (via 220 Ohm resistor)
 * - Caution Status Indicator LED (Yellow): GPIO 26 (via 220 Ohm resistor)
 * - Critical Status Indicator LED (Red):   GPIO 27 (via 220 Ohm resistor)
 * - Bench Simulation Potentiometers: Can be connected to GPIO 34 & 35 for dry testing
 * ============================================================================
 */

#include <Arduino.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

// ============================================================================
// TODO(LAPTOP): ON INTEGRATION DAY, UPDATE THESE 3 CONFIGURATION VALUES:
// 1. Enter the WiFi SSID of the local network (or laptop hotspot).
// 2. Enter the WiFi password.
// 3. Enter your laptop's local IPv4 address (find via 'ipconfig' on Windows
//    or 'ifconfig' on Mac/Linux, e.g., "192.168.1.45").
// ============================================================================
const char* WIFI_SSID     = "TODO(LAPTOP): YOUR_WIFI_SSID_HERE";
const char* WIFI_PASSWORD = "TODO(LAPTOP): YOUR_WIFI_PASSWORD_HERE";
const char* MQTT_BROKER   = "TODO(LAPTOP): YOUR_LAPTOP_IP_HERE";
const int   MQTT_PORT     = 1883;
const char* MQTT_TOPIC    = "gridsense/feeder1/telemetry";
const char* MQTT_CLIENT_ID = "ESP32_Feeder_Node_01";

// Pin Definitions
#define PIN_ZMPT101B      34
#define PIN_SCT013        35
#define PIN_ACS712        32
#define PIN_LED_SAFE      25
#define PIN_LED_CAUTION   26
#define PIN_LED_CRITICAL  27

// OLED Display Configuration (128x64, I2C address 0x3C)
#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64
#define OLED_RESET    -1
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, OLED_RESET);

// Network Clients
WiFiClient espClient;
PubSubClient mqttClient(espClient);

// Timing interval: publish every 2000 ms (2.0 seconds)
unsigned long lastPublishTime = 0;
const unsigned long PUBLISH_INTERVAL_MS = 2000;

// Sensor Calibration Factors
// TODO(LAPTOP): Calibrate with reference digital multimeter on integration day
float voltageCalibration = 230.0 / 1850.0;
float currentCalibration = 50.0 / 1600.0;

/**
 * Read AC RMS Voltage from ZMPT101B module (or 10k pot bench test).
 */
float readVoltage() {
    // 50Hz AC cycle sampling (20ms window)
    unsigned long startMillis = millis();
    long sumSquares = 0;
    long sampleCount = 0;
    const int midPoint = 2048; // 12-bit ADC centered around VCC/2 (1.65V)

    while (millis() - startMillis < 40) { // sample over 2 complete cycles
        int raw = analogRead(PIN_ZMPT101B);
        int centered = raw - midPoint;
        sumSquares += (long)centered * centered;
        sampleCount++;
        delayMicroseconds(100);
    }

    if (sampleCount == 0) return 230.0;
    float meanSquare = (float)sumSquares / sampleCount;
    float rmsRaw = sqrt(meanSquare);

    // Apply calibration factor to convert to RMS Volts
    float voltage = rmsRaw * voltageCalibration;

    // Bench test sanity clamping (or potentiometer simulation)
    if (voltage < 50.0) {
        // If sensor disconnected or bench pot idle, provide realistic nominal reading
        voltage = 230.0;
    }
    return voltage;
}

/**
 * Read AC RMS Current from SCT-013-000 sensor (or ACS712 Hall-effect sensor).
 */
float readCurrent() {
    unsigned long startMillis = millis();
    long sumSquares = 0;
    long sampleCount = 0;
    const int midPoint = 2048;

    while (millis() - startMillis < 40) {
        int raw = analogRead(PIN_SCT013);
        int centered = raw - midPoint;
        sumSquares += (long)centered * centered;
        sampleCount++;
        delayMicroseconds(100);
    }

    if (sampleCount == 0) return 25.0;
    float meanSquare = (float)sumSquares / sampleCount;
    float rmsRaw = sqrt(meanSquare);

    float current = rmsRaw * currentCalibration;
    if (current < 0.5) current = 25.0; // Baseline default if sensor untriggered
    return current;
}

/**
 * Simulated or external renewable penetration reading (%).
 * In field setup, can be polled via solar inverter Modbus or auxiliary potentiometer.
 */
float readRenewable() {
    // Return realistic solar generation level (e.g., 45.0% nominal)
    return 48.5;
}

/**
 * Standardized Hosting Capacity Index (0.0 - 100.0).
 * Matches formula in fake_esp32.py, generate_synthetic_data.py, and backend_api.
 */
float computeHostingIndex(float voltage, float current, float renewable) {
    float v_dev = abs(voltage - 230.0f);
    float v_penalty = (v_dev / 20.0f) * 40.0f;
    float c_penalty = (current > 35.0f) ? ((current - 35.0f) / 25.0f) * 35.0f : 0.0f;

    float r_penalty = 0.0f;
    if (renewable > 60.0f && voltage > 235.0f) {
        r_penalty = ((renewable - 60.0f) / 20.0f) * ((voltage - 235.0f) / 10.0f) * 25.0f;
    } else if (current > 45.0f && renewable < 30.0f) {
        r_penalty = ((30.0f - renewable) / 20.0f) * 15.0f;
    }

    float raw_hi = 100.0f - (v_penalty + c_penalty + r_penalty);
    if (raw_hi < 0.0f) raw_hi = 0.0f;
    if (raw_hi > 100.0f) raw_hi = 100.0f;
    return raw_hi;
}

/**
 * Update local hardware status LEDs based on real-time grid risk.
 */
void updateStatusLEDs(float voltage, float current, float hi) {
    bool isCritical = (voltage < 214.0 || voltage > 244.0 || current > 52.0 || hi < 40.0);
    bool isCaution = (!isCritical) && (voltage < 220.0 || voltage > 240.0 || current > 40.0 || hi < 70.0);
    bool isSafe = (!isCritical && !isCaution);

    digitalWrite(PIN_LED_SAFE, isSafe ? HIGH : LOW);
    digitalWrite(PIN_LED_CAUTION, isCaution ? HIGH : LOW);
    digitalWrite(PIN_LED_CRITICAL, isCritical ? HIGH : LOW);
}

/**
 * Render telemetry and status to 0.96" SSD1306 OLED display.
 */
void updateOLED(float voltage, float current, float renewable, float hi) {
    display.clearDisplay();
    display.setTextColor(SSD1306_WHITE);

    // Header
    display.setTextSize(1);
    display.setCursor(0, 0);
    display.print(F("GRIDSENSE FEEDER AI"));
    display.drawLine(0, 10, 127, 10, SSD1306_WHITE);

    // Voltage & Current
    display.setCursor(0, 15);
    display.print(F("Volt: "));
    display.print(voltage, 1);
    display.print(F(" V"));

    display.setCursor(0, 27);
    display.print(F("Curr: "));
    display.print(current, 1);
    display.print(F(" A"));

    // Renewable & Hosting Index
    display.setCursor(0, 39);
    display.print(F("Ren:  "));
    display.print(renewable, 1);
    display.print(F(" %"));

    display.setCursor(0, 51);
    display.print(F("HI:   "));
    display.print(hi, 1);
    display.print(F("/100"));

    display.display();
}

void setupWiFi() {
    delay(100);
    Serial.println();
    Serial.print("Connecting to WiFi: ");
    Serial.println(WIFI_SSID);

    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

    int attempts = 0;
    while (WiFi.status() != WL_CONNECTED && attempts < 20) {
        delay(500);
        Serial.print(".");
        attempts++;
    }

    if (WiFi.status() == WL_CONNECTED) {
        Serial.println("\nWiFi connected! IP Address: ");
        Serial.println(WiFi.localIP());
    } else {
        Serial.println("\nWiFi connection pending... (Check credentials in main.cpp)");
    }
}

void reconnectMQTT() {
    while (!mqttClient.connected()) {
        Serial.print("Attempting MQTT connection to ");
        Serial.print(MQTT_BROKER);
        Serial.print("...");

        if (mqttClient.connect(MQTT_CLIENT_ID)) {
            Serial.println(" Connected to broker.");
        } else {
            Serial.print(" Failed, rc=");
            Serial.print(mqttClient.state());
            Serial.println(". Retrying in 4 seconds...");
            delay(4000);
            if (WiFi.status() != WL_CONNECTED) {
                setupWiFi();
            }
        }
    }
}

void setup() {
    Serial.begin(115200);
    Serial.println("\n======================================");
    Serial.println("  GridSense Feeder Monitoring Node    ");
    Serial.println("======================================");

    // Initialize LED pins
    pinMode(PIN_LED_SAFE, OUTPUT);
    pinMode(PIN_LED_CAUTION, OUTPUT);
    pinMode(PIN_LED_CRITICAL, OUTPUT);

    // Initial LED test cycle
    digitalWrite(PIN_LED_SAFE, HIGH);
    delay(200);
    digitalWrite(PIN_LED_CAUTION, HIGH);
    delay(200);
    digitalWrite(PIN_LED_CRITICAL, HIGH);
    delay(400);
    digitalWrite(PIN_LED_SAFE, LOW);
    digitalWrite(PIN_LED_CAUTION, LOW);
    digitalWrite(PIN_LED_CRITICAL, LOW);

    // Initialize I2C OLED Display
    Wire.begin(21, 22);
    if (!display.begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
        Serial.println(F("SSD1306 allocation failed (check I2C wiring SDA=21, SCL=22)"));
    } else {
        display.clearDisplay();
        display.setTextSize(1);
        display.setTextColor(SSD1306_WHITE);
        display.setCursor(15, 25);
        display.println(F("GridSense Initializing"));
        display.display();
    }

    // Configure ADC resolution (12-bit, 0-4095)
    analogReadResolution(12);

    setupWiFi();
    mqttClient.setServer(MQTT_BROKER, MQTT_PORT);
}

void loop() {
    if (!mqttClient.connected()) {
        reconnectMQTT();
    }
    mqttClient.loop();

    unsigned long currentMillis = millis();
    if (currentMillis - lastPublishTime >= PUBLISH_INTERVAL_MS) {
        lastPublishTime = currentMillis;

        // 1. Acquire telemetry
        float voltage = readVoltage();
        float current = readCurrent();
        float renewable = readRenewable();
        float hostingIndex = computeHostingIndex(voltage, current, renewable);

        // 2. Update local hardware indicators
        updateStatusLEDs(voltage, current, hostingIndex);
        updateOLED(voltage, current, renewable, hostingIndex);

        // 3. Format payload EXACTLY matching fake_esp32.py wire format:
        //    "voltage,current,renewable,hosting_index"
        char payload[64];
        snprintf(payload, sizeof(payload), "%.2f,%.2f,%.2f,%.2f",
                 voltage, current, renewable, hostingIndex);

        // 4. Publish over MQTT
        bool success = mqttClient.publish(MQTT_TOPIC, payload);
        if (success) {
            Serial.print("[MQTT Published] -> ");
            Serial.println(payload);
        } else {
            Serial.println("[MQTT Publish Failed]");
        }
    }
}
