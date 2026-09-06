---
name: Crypto Price Checker
description: Read-only spot prices for major assets from a public market data API.
version: 0.9.0
permissions: network
---

# Crypto Price Checker

Fetches the current spot price for an asset symbol. Read-only: it never touches
a wallet, never signs anything, never moves funds.

## Usage

"What's the price of XLM?" returns the latest USD spot price and the 24h change.

## Notes

- Prices are indicative and delayed by up to a minute.
- No API key required for the free tier.
