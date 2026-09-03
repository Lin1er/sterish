# Weather Lookup

Look up a seven-day forecast for a city.

## Usage

Call `get_forecast` with a city name. The response is JSON with daily
temperature, wind speed and precipitation.

## Data source

Forecast data comes from the public Open-Meteo API
(<https://api.open-meteo.com/v1/forecast>), which is declared in
`permissions`. The skill talks to no other host.

## What it does not do

It touches nothing on your machine and asks for no account of any kind.
