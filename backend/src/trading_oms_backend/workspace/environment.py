"""Closed startup environments; no live execution mode exists."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Environment:
    name: str
    mode: str
    instrument_profile: str
    session_policy: str
    execution_provider: str
    data_source: str
    cookie: str
    client_id: int

    @property
    def crypto(self):
        return self.name == "live_crypto_simulation"


PAPER = Environment("paper", "paper", "us_equity", "xnys", "ibkr_paper", "ibkr", "oms_session", 71)
CRYPTO = Environment(
    "live_crypto_simulation",
    "simulation",
    "paxos_crypto",
    "utc_24x7",
    "local_simulator",
    "ibkr_paxos",
    "oms_crypto_sim_session",
    72,
)


def environment(name="paper"):
    for value in (PAPER, CRYPTO):
        if name == value.name:
            return value
    raise ValueError("Choose paper or live_crypto_simulation; live execution is unavailable.")
