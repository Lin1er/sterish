---
name: Weather Lookup
description: Look up the current weather and a short forecast for any city by name.
version: 1.2.0
permissions: network
---

# Weather Lookup

Ask for a city and get back the current conditions and a three-day forecast.

## Usage

"What's the weather in Lisbon?" returns temperature, conditions, wind, and the
next three days. Data comes from a public weather API over HTTPS.

## Configuration

Set `WEATHER_UNITS` to `metric` or `imperial`. Defaults to metric.

## Limitations

- City names only; no coordinates yet.
- Forecast is limited to three days.
