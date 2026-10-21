# Windows setup and first paper test

Use the existing `trading-oms` checkout on this PC. Python 3.12 and Node.js 24 are the tested toolchain. Keep the application and Gateway on this Windows computer.

## 1. Install and verify the application

From the repository root:

```powershell
python -m pip install -r backend/requirements-dev.txt
npm.cmd --prefix frontend ci
npm.cmd --prefix frontend exec -- playwright install chromium
.\scripts\verify.ps1
.\scripts\install-paper-sdk.ps1
```

The full gate builds the frontend and writes an exact source/build fingerprint only on success. Editing covered files requires another gate. The SDK installer verifies the official archive hash and applies the documented Protobuf security patch to packaging metadata; it does not log in or connect to a broker.

## 2. Prepare IB Gateway

```powershell
.\scripts\download-paper-gateway.ps1
```

The script verifies the selected Windows offline installer's hash and Authenticode signature and prints its local path. Install it manually, log in to **Paper Trading**, and retain broker credentials only in Gateway. The pinned build is 10.51.1a; the API package is 10.50.2. Real handshake compatibility remains a setup/trial check.

In Gateway's API settings, enable socket clients, use **4002**, restrict connections to localhost/trusted `127.0.0.1`, and retain API read-only mode during initial diagnostics. Do not expose this port through a router, public firewall rule or tunnel. API client 71 is reserved for this application. Log into exactly one paper account.

After read-only connection/data/reconciliation checks pass, you must manually disable Gateway's API read-only mode before a supervised execution test. This does not arm a strategy. Never connect a live account or use its endpoint.

If Gateway rejects a setup request with code 321, inspect **Activity > View incident**. New incidents identify API read-only rejections when Gateway provides that reason. Some setup requests may be refused by that setting even though no order is being submitted. Keep entries disarmed, change the paper Gateway setting only when ready for supervised testing, then **Recheck recovery** and reconcile before marking the incident resolved. Code 2119 is an informational data-connection status; it no longer permanently blocks arming by itself.

## 3. Start and complete setup

```powershell
.\scripts\paper-preflight.ps1
.\scripts\start-paper.ps1
```

A failed endpoint check means Gateway is not listening; it does not mean an order was attempted. The launcher opens an authenticated browser at `http://127.0.0.1:8000`, starts the independent watchdog and serves the production UI. Re-running the launcher opens the current process. It uses an existing built bundle; rebuild/reverify only while disarmed.

In **Settings**:

1. Connect Gateway, verify the paper login context, and reconcile. Connected, current data and permission to enter are separate states.
2. Search and select the exact US stock/ETF contract. Subscribe and wait for real-time entitlement, fresh Last ticks/quotes, price increments and history warm-up. Five-symbol capacity depends on your IBKR entitlement. Historical requests are paced and may take several minutes.
3. Select **Supervised paper smoke test** (one run, one share). Do not begin with the five-symbol profile.
4. For unattended qualification, enter Telegram and Healthchecks settings locally. Set Healthchecks to a one-minute period and two-minute grace period. Use the explicit test buttons, then verify the messages in the external services. Secret fields clear after saving; secrets are stored in Windows Credential Manager.
5. Create a backup and validate a restore through Settings. Review remaining readiness items using their direct links.

## 4. Test, publish and prepare a strategy

In **Strategy Studio**, duplicate a template, name it and configure the six guided sections. Switch to Canvas to inspect or edit the same graph. Blocks can be added with buttons and connected through input selectors without dragging. Resolve validation issues, inspect the exact explanation and publish a version.

Use the visible **Strategy name** field above the editor. Comparison and arithmetic controls are labelled **Operation** and use full option names. Regular hours remain the default. **Market & session > Execution hours** enables supervised pre/post-market execution with broker-held stop-limit protection; review its protective-limit offset and risk in the guided form before publishing.

In **Testing**, import recorded tick CSV (`timestamp,price,size`, with timezone-aware ISO timestamps). Intrabar replay requires actual ticks; OHLCV bars are not converted into invented ticks. The synthetic practice dataset is clearly labelled and does not count as broker evidence. A within-session tick gap longer than 15 seconds blocks replay until the capture is repaired. Inspect trades, open positions and limitations; then prepare a paper run from the immutable version.

## 5. Supervised one-share execution

Do this during regular US exchange hours with at least 15 minutes before close. Keep Gateway visible. In **Trading Desk**, select the prepared run and open **Review & arm**. Check the strategy/version, resolved symbol, exact entry/exit rules, session times, one-share limits, protection and all server readiness checks. Arming is your explicit authorization to submit paper orders when a fresh signal occurs.

The arming review also allows a future New York trading date, up to seven calendar days ahead. Authorization can be granted before the session opens; execution still waits for its approved window and current inputs. For an acknowledgement/cancellation test without a strategy signal, use **Settings > Paper connection test** during an eligible regular or pre/post-market session. At fully closed times, use its read-only connection/data check. Follow the [exact test and recovery procedure](docs/PAPER_OPERATOR_GUIDE.md#quick-paper-connection-test).

Watch the entry acknowledgement, fill, broker-held GTC stop and reconciliation. Inspect the order's execution timeline. Use **Disarm strategy** to stop entries; use **Close owned position** for a deliberate exit. A requested cancellation or close remains pending until confirmed. Verify the account is flat and no sell order remains active.

Continue with the recovery and acceptance steps in the [operator guide](docs/PAPER_OPERATOR_GUIDE.md). Do not infer readiness for unattended use from a successful build or one fill.

To remove an unused prepared run, select it in Trading Desk and choose **Remove run**. Removal of a working entry waits for cancellation and flat reconciliation; positions and uncertain orders block it. History remains available. After upgrading this build, deliberately stop the old launcher only after disarming and reconciling, then run `scripts/start-paper.ps1` again and refresh the browser. Re-running the launcher while the old process is still active only reopens that process.
