"""Centrale config: laadt env vars en valideert dat alle vereiste secrets aanwezig zijn."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass


REQUIRED_VARS = [
    "BOL_CLIENT_ID",
    "BOL_CLIENT_SECRET",
    "GOOGLE_SERVICE_ACCOUNT_JSON",
    "SLACK_WEBHOOK_URL",
    "CASHFLOW_SHEET_ID",
]


@dataclass(frozen=True)
class Config:
    bol_client_id: str
    bol_client_secret: str
    google_service_account: dict
    slack_webhook_url: str
    cashflow_sheet_id: str

    # Sheet-configuratie (deze hoeft niet in secrets)
    inkomsten_tab: str = "Inkomsten"
    inkomsten_data_start_row: int = 5
    inkomsten_data_end_row: int = 52
    instellingen_cell_banksaldo: str = "Instellingen!B4"


def load_config() -> Config:
    """Laad config uit env vars. Raised ValueError als iets ontbreekt."""
    missing = [v for v in REQUIRED_VARS if not os.environ.get(v)]
    if missing:
        raise ValueError(
            f"Ontbrekende environment variables: {', '.join(missing)}. "
            "Zet ze als GitHub Secrets of lokaal via export."
        )

    raw_sa = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]
    try:
        service_account = json.loads(raw_sa)
    except json.JSONDecodeError as e:
        raise ValueError(
            "GOOGLE_SERVICE_ACCOUNT_JSON is geen geldige JSON. "
            "Plak de volledige inhoud van het keybestand."
        ) from e

    return Config(
        bol_client_id=os.environ["BOL_CLIENT_ID"],
        bol_client_secret=os.environ["BOL_CLIENT_SECRET"],
        google_service_account=service_account,
        slack_webhook_url=os.environ["SLACK_WEBHOOK_URL"],
        cashflow_sheet_id=os.environ["CASHFLOW_SHEET_ID"],
    )
