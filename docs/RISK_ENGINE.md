# Risk Engine

## Goal

Every risk-increasing order intent must pass risk checks before approval or submission.

## Initial checks

- App mode is paper/simulation.
- Live trading disabled.
- Market data is fresh.
- Symbol is allowed.
- Quantity is within configured limits.
- Duplicate order intent is not present.
- Position limit is respected.
- Protective-order plan exists or explicit approved exception exists.

## Rule

Risk checks must return structured allow/deny decisions with reasons.
