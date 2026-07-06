# OMS State Machine

## Goal

Represent every order lifecycle transition explicitly and auditably.

## Initial conceptual states

- CREATED
- RISK_REJECTED
- PENDING_APPROVAL
- APPROVAL_REJECTED
- APPROVED
- SUBMITTED
- ACKNOWLEDGED
- PARTIALLY_FILLED
- FILLED
- CANCEL_REQUESTED
- CANCELLED
- REJECTED
- FAILED
- UNKNOWN_REQUIRES_RECONCILIATION

## Rule

Unknown state must block new risk-increasing trading decisions until reconciliation completes.
