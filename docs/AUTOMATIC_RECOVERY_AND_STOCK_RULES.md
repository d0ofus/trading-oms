# Automatic recovery and stock preparation

Current monitoring and recovery behavior is defined in [Current operational monitoring](CURRENT_OPERATIONAL_MONITORING.md). It supersedes the historical recovery intervals and acknowledgment workflow described below.

Start the normal paper workspace with `scripts/start-workspace.ps1` after updating.
The launcher uses `.venv/Scripts/python.exe` automatically. Build the frontend before
using `-SkipBuild`. No broker login is required to browse the application.

## Routine recovery

Recognized watchdog, connectivity, market-data/history and broker-service incidents
now release automatically after current verified paper context, fresh watchdog health,
post-failure reconciliation and 30 continuously healthy seconds. Restart alone does
not release a restriction. Open positions, orders, protection and account uncertainty,
unknown engine faults and emergency stop retain dedicated review. A release never
arms a run, restores an old authorization or clears emergency stop.

Activity's **Routine recovery status** shows progress without acknowledgment boxes.
Historical records and investigations remain inspectable. Repeated callbacks for one
uninterrupted service failure remain observations rather than new incidents. After a
new connection, verified current dependencies can establish recovery without a message
from a farm no longer used by the connection.

An unsubscribed contract's unused feed restriction retires after current post-failure
reconciliation proves no current preparation, authorization, owned exposure, reservation,
unresolved order or exit/protection dependency. It does not require a healthy-feed countdown.
Paused flat runs and virtual FX-pair positions alone are not dependencies. The journal labels
this **dependency retired**, not a healthy feed. Reuse requires fresh data readiness.
See [broker credit and quiet FX](BROKER_CREDIT_AND_QUIET_FX.md) for the narrow corrected-fault
auto-recovery policy and the new authorization terms.

## Preparing stocks

Choose the published reusable stock strategy, exact contract, sizing limits, session
and protection. Contract rules are read-only and automatically derived; there are no
manual contract-rule fields or capability checkboxes. Unsupported requirements and
budget conflicts appear beside Prepare bound run. Preparation never authorizes orders.

The automatic policy covers ordinary supported USD listings on NASDAQ/NYSE/ARCA with
whole-share execution and supported SEHK/HKD stock listings with corroborated board
lots. Other combinations explain missing policy/evidence. Stock permissions or quotes
alone do not establish strategy, order or protective-exit compatibility.

For Xiaomi, use **1810 HK - Paper Test (stock copy) v1**, schema 7. The original
**1810 HK - Paper Test v2** remains a legacy crypto definition. Published hashes and
definitions are unchanged; conversion and publication remain explicit.

Xiaomi metadata and the HKEX reference report **200 shares per board lot**. The
automatic SEHK policy uses board-lot entry and exit quantities; it does not promise
odd-lot stop support. Existing legacy runs retain their pinned exit rules. Unexpected
quantities require protection/reconciliation handling; closing never rounds ownership
upward. Short/OCA capabilities and shortability remain separate checks.

The stock copy still has its published **USD 25 ceiling**. The dialog shows the minimum
lot's native notional, USD value and fee reserve when fresh prices/FX are available.
Increase a ceiling only by deliberately editing and publishing within existing risk
limits. The application never enlarges a budget, changes a route or chooses another
protection method to overcome rejection.

## Reference, funding and operational limits

The HKEX public securities list is downloaded by one bounded background worker, with
no account information sent. Downloads have a 15-second overall deadline, a 4 MB
compressed limit and a 32 MB expanded limit. A normalized reference cache is refreshed
per Hong Kong business day and retried no faster than once per minute. Missing,
conflicting or stale required reference data blocks new automatic-policy authorization;
existing protection keeps its pinned plan.

Broker metadata is refreshed for the current connection/schedule; price rules are
requested for the selected route. Runtime observations are not part of the semantic
strategy hash. Automatic rules cannot be changed by the retained legacy rule-write API.

Fees are **conservative round-trip funding reserves**, not exact commissions. Policy v2
uses the larger fixed/tiered published base charge without volume discounts or rebates.
HK estimates include stamp duty, exchange, clearing and regulatory charges; US estimates
include a conservative exchange/transaction buffer and do not apply commission caps.
Actual fee reports remain informational execution records. Estimates refresh during
sizing; existing run fee policies are unchanged. Settled native funding, fresh USD
valuation and all published/account-wide limits still apply. There is no automatic FX
trade, borrowing permission or live-account execution.

Sources reviewed 23 September 2026:

- [IBKR contract fields](https://www.interactivebrokers.com/docs/tws-api/ref/contract-details)
- [IBKR lot limitations](https://www.interactivebrokers.com/docs/tws-api/doc/orders/minimum-price-increment/introduction)
- [HKEX securities list](https://www.hkex.com.hk/eng/services/trading/securities/securitieslists/ListOfSecurities.xlsx)
- [HKEX board/odd-lot trading](https://www.hkex.com.hk/Global/Exchange/FAQ/Securities-Market/Trading?sc_lang=en)
- [IBKR commissions](https://investors.interactivebrokers.com/en/pricing/commissions-stocks.php)
- [IBKR Hong Kong external fees](https://investors.interactivebrokers.com/en/index.php?f=1315)

## Compatibility and rollback

Compatibility responses include `resolution_status`, `refresh_status`, provenance and
`minimum_lot`. `GET /api/incidents/recovery-status` is bounded to the current 200-summary
page. Legacy batch review endpoints remain available. Policy migration backs up state
and audits classification changes without releasing anything at migration time.

`OMS_DISABLE_AUTOMATIC_RECOVERY=1` retains explicit recovery via incident review and
legacy batch APIs. `OMS_DISABLE_AUTOMATIC_STOCK_ARM=1` prevents new automatic-policy
arming while preserving management of existing positions. Database restoration requires
a stopped engine and reconciled broker exposure. No production state is migrated by
the offline verification fixtures.
