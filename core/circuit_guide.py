"""Validated DHT11-to-Pro-Mini wiring and example; code is never flashed."""
from __future__ import annotations


def guide(board_voltage: str, sensor_form: str, board_variant: str):
    board_voltage = str(board_voltage or "").strip()
    sensor_form = str(sensor_form or "").strip().lower()
    board_variant = str(board_variant or "").strip()
    if board_voltage not in ("3.3V", "5V"):
        raise ValueError("Confirm whether this Pro Mini is 3.3V or 5V")
    if sensor_form not in ("module", "bare"):
        raise ValueError("Confirm whether the DHT11 is a 3-pin module or bare 4-pin sensor")
    variants = {"Pro Mini 3.3V/8MHz": "3.3V", "Pro Mini 5V/16MHz": "5V"}
    if board_variant not in variants:
        raise ValueError("Identify the exact Pro Mini as 3.3V/8MHz or 5V/16MHz first")
    if variants[board_variant] != board_voltage:
        raise ValueError("Board variant and selected voltage do not match")
    wires = (["DHT11 VCC → Pro Mini VCC", "DHT11 DATA → D4", "DHT11 GND → GND"]
             if sensor_form == "module" else
             ["DHT11 pin 1 (VCC) → Pro Mini VCC", "DHT11 pin 2 (DATA) → D4",
              "DHT11 pin 3 → no connection", "DHT11 pin 4 (GND) → GND",
              "Add 4.7–10 kΩ pull-up from DATA to VCC if the bare sensor board lacks one"])
    code = '''# Install the Adafruit DHT sensor library through Arduino Library Manager.
# Confirm the exact board voltage and sensor pin order before powering.
# Never connect an FTDI 5 V TX signal to a 3.3 V Pro Mini RX pin.
#include <DHT.h>
#define DHTPIN 4
#define DHTTYPE DHT11
DHT dht(DHTPIN, DHTTYPE);
void setup() { Serial.begin(9600); dht.begin(); }
void loop() {
  float h = dht.readHumidity();
  float c = dht.readTemperature();
  if (isnan(h) || isnan(c)) { Serial.println("DHT read failed"); delay(2000); return; }
  Serial.print("Humidity: "); Serial.print(h); Serial.print(" %  Temperature: ");
  Serial.print(c); Serial.println(" C"); delay(2000);
}
'''
    return {"board": board_variant, "voltage": board_voltage, "sensor": sensor_form,
            "wires": wires, "code": code,
            "warning": "Check the pin labels, module pull-up, and logic levels for the exact board before connecting power. No firmware was written to hardware."}
