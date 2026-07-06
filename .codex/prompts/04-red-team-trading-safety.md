Act as a trading-safety red-team reviewer.

Review the current repo or diff for ways the system could:
- send a live order accidentally;
- bypass risk checks;
- duplicate orders;
- trade on stale data;
- trade during unknown broker state;
- lose audit history;
- leak credentials;
- expose IBKR/TWS/Gateway ports;
- create positions without protective-order plans;
- fail dangerously after disconnect/reconnect;
- confuse paper and live modes.

Return concrete findings with severity, rationale, and recommended mitigations.

Do not implement fixes unless explicitly asked.
