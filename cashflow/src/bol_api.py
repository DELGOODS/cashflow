"""Bol Retailer API client.

Gebruikt OAuth2 client_credentials flow voor authenticatie en haalt
verkoopfacturen + adverteerfacturen op voor cashflow-analyse.

API docs: https://api.bol.com/retailer/public/Retailer-API/v10/functional/invoices.html
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Iterable

import requests

logger = logging.getLogger(__name__)

TOKEN_URL = "https://login.bol.com/token"
API_BASE = "https://api.bol.com/retailer"
ACCEPT_HEADER = "application/vnd.retailer.v10+json"


@dataclass
class Invoice:
    """Eén factuur uit de Bol API.

    Bij Bol bestaan twee relevante typen:
    - 'verkoopfactuur' (te ontvangen): wat Bol uitkeert voor verkopen
    - 'adverteren' (te betalen): wat user aan Bol betaalt voor ads
    Het netto uitbetaalde bedrag = som verkoopfacturen - som adverteerfacturen
    over dezelfde datum (Bol verrekent onderling).
    """
    invoice_id: str
    invoice_date: date
    invoice_type: str  # 'verkoopfactuur', 'adverteren', etc.
    period_start: date | None
    period_end: date | None
    total_amount: float  # Positief = te ontvangen, negatief mogelijk

    @property
    def is_verkoopfactuur(self) -> bool:
        return "verkoop" in self.invoice_type.lower()

    @property
    def is_adverteerfactuur(self) -> bool:
        return "adverteren" in self.invoice_type.lower() or "ads" in self.invoice_type.lower()


@dataclass
class NetPayout:
    """Netto Bol uitbetaling op één datum (verkoop - adverteren)."""
    payout_date: date
    verkoop_total: float
    adverteren_total: float

    @property
    def net_amount(self) -> float:
        return self.verkoop_total - self.adverteren_total


class BolAPIClient:
    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self._token: str | None = None
        self._token_expires_at: datetime | None = None
        self._session = requests.Session()

    def _get_token(self) -> str:
        """OAuth2 client credentials flow. Token cachen tot ~5 min voor expiry."""
        if self._token and self._token_expires_at and datetime.utcnow() < self._token_expires_at:
            return self._token

        logger.info("Bol API: nieuwe access token aanvragen")
        response = self._session.post(
            TOKEN_URL,
            auth=(self.client_id, self.client_secret),
            data={"grant_type": "client_credentials"},
            headers={"Accept": "application/json"},
            timeout=30,
        )
        response.raise_for_status()
        body = response.json()
        self._token = body["access_token"]
        # 'expires_in' is in seconden; ververs 5 min eerder als buffer
        self._token_expires_at = datetime.utcnow() + timedelta(seconds=body.get("expires_in", 300) - 300)
        return self._token

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._get_token()}",
            "Accept": ACCEPT_HEADER,
        }

    def list_invoices(self, period_start: date, period_end: date) -> list[Invoice]:
        """Haal alle facturen op binnen een periode.

        Bol API endpoint: GET /retailer/invoices?period-start-date=YYYY-MM-DD&period-end-date=YYYY-MM-DD
        """
        logger.info(f"Bol API: facturen ophalen {period_start} t/m {period_end}")
        response = self._session.get(
            f"{API_BASE}/invoices",
            headers=self._headers(),
            params={
                "period-start-date": period_start.isoformat(),
                "period-end-date": period_end.isoformat(),
            },
            timeout=30,
        )
        response.raise_for_status()
        body = response.json()

        invoices: list[Invoice] = []
        for raw in body.get("invoiceListItems", []):
            try:
                invoices.append(self._parse_invoice(raw))
            except (KeyError, ValueError) as e:
                logger.warning(f"Kon factuur niet parsen: {raw}, error: {e}")
        logger.info(f"Bol API: {len(invoices)} facturen ontvangen")
        return invoices

    def _parse_invoice(self, raw: dict) -> Invoice:
        """Vertaal Bol API JSON naar Invoice dataclass.

        Het exacte veldnamen in de Bol API kunnen variëren — in geval van mismatch
        loggen we en slaan we deze factuur over.
        """
        return Invoice(
            invoice_id=str(raw.get("invoiceId", raw.get("invoice-id", ""))),
            invoice_date=date.fromisoformat(raw["invoiceDate"]) if "invoiceDate" in raw else date.fromisoformat(raw["invoice-date"]),
            invoice_type=raw.get("invoiceType", raw.get("invoice-type", raw.get("type", "unknown"))),
            period_start=date.fromisoformat(raw["periodStartDate"]) if raw.get("periodStartDate") else None,
            period_end=date.fromisoformat(raw["periodEndDate"]) if raw.get("periodEndDate") else None,
            total_amount=float(raw.get("totalAmount", raw.get("total-amount", 0))),
        )

    def get_net_payouts(self, period_start: date, period_end: date) -> list[NetPayout]:
        """Geef per uitbetaaldatum het netto uitbetaalde bedrag (verkoop - adverteren).

        Bol betaalt rond de 3e en 18e van iedere maand uit. Verkoop- en adverteerfacturen
        van dezelfde uitbetaaldatum worden gecombineerd tot één NetPayout.
        """
        invoices = self.list_invoices(period_start, period_end)

        # Groepeer per invoice_date
        grouped: dict[date, dict] = {}
        for inv in invoices:
            entry = grouped.setdefault(
                inv.invoice_date, {"verkoop": 0.0, "adverteren": 0.0, "other": 0.0}
            )
            if inv.is_verkoopfactuur:
                entry["verkoop"] += inv.total_amount
            elif inv.is_adverteerfactuur:
                entry["adverteren"] += inv.total_amount
            else:
                entry["other"] += inv.total_amount
                logger.debug(f"Onbekend factuurtype '{inv.invoice_type}' op {inv.invoice_date}")

        payouts = [
            NetPayout(
                payout_date=d,
                verkoop_total=v["verkoop"],
                adverteren_total=v["adverteren"],
            )
            for d, v in sorted(grouped.items())
        ]
        return payouts


def rolling_average(payouts: Iterable[NetPayout], window: int = 12) -> float:
    """Gemiddelde netto uitbetaling over de laatste `window` uitbetalingen."""
    sorted_payouts = sorted(payouts, key=lambda p: p.payout_date, reverse=True)
    recent = sorted_payouts[:window]
    if not recent:
        return 0.0
    return sum(p.net_amount for p in recent) / len(recent)
