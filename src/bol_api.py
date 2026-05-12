"""Bol Retailer API client.

Gebruikt OAuth2 client_credentials flow voor authenticatie en haalt
verkoopfacturen + adverteerfacturen op voor cashflow-analyse.

API docs: https://api.bol.com/retailer/public/Retailer-API/v10/functional/invoices.html
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
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
        # In Bol v10 wordt verkoopfactuur 'ALL_IN_ONE' genoemd
        return self.invoice_type.upper() == "ALL_IN_ONE"

    @property
    def is_adverteerfactuur(self) -> bool:
        return self.invoice_type.upper() == "ADVERTISING_VIA_BOL"


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

    def list_invoices_for_month(self, year: int, month: int) -> list[Invoice]:
        """Haal alle facturen op voor één kalendermaand.

        Bol API endpoint: GET /retailer/invoices?period=YYYY-MM
        """
        period = f"{year:04d}-{month:02d}"
        logger.info(f"Bol API: facturen ophalen voor periode {period}")
        response = self._session.get(
            f"{API_BASE}/invoices",
            headers=self._headers(),
            params={"period": period},
            timeout=30,
        )
        if response.status_code == 404:
            # Geen facturen voor deze maand
            logger.info(f"Bol API: geen facturen gevonden voor {period}")
            return []
        response.raise_for_status()
        body = response.json()

        invoices: list[Invoice] = []
        for raw in body.get("invoiceListItems", body.get("invoices", [])):
            try:
                invoices.append(self._parse_invoice(raw))
            except (KeyError, ValueError) as e:
                logger.warning(f"Kon factuur niet parsen: {raw}, error: {e}")
        logger.info(f"Bol API: {len(invoices)} facturen ontvangen voor {period}")
        return invoices

    def list_invoices(self, period_start: date, period_end: date) -> list[Invoice]:
        """Haal facturen op over een datumbereik door per maand te queryen.

        Bol's ?period=YYYY-MM filter is in praktijk onbetrouwbaar; we dedupliceren
        daarom op invoice_id om dubbele facturen te voorkomen.
        """
        all_invoices: list[Invoice] = []
        seen_ids: set[str] = set()
        current_year, current_month = period_start.year, period_start.month
        end_year, end_month = period_end.year, period_end.month
        while (current_year, current_month) <= (end_year, end_month):
            for inv in self.list_invoices_for_month(current_year, current_month):
                if inv.invoice_id and inv.invoice_id not in seen_ids:
                    seen_ids.add(inv.invoice_id)
                    all_invoices.append(inv)
            if current_month == 12:
                current_year += 1
                current_month = 1
            else:
                current_month += 1
        # Filter ook op datum-bereik client-side
        filtered = [
            inv for inv in all_invoices
            if inv.invoice_date and period_start <= inv.invoice_date <= period_end
        ]
        logger.info(f"Bol API: {len(filtered)} unieke facturen in periode {period_start} t/m {period_end}")
        return filtered

    def _parse_invoice(self, raw: dict) -> Invoice:
        """Vertaal Bol API JSON naar Invoice dataclass.

        Bol Retailer v10 levert:
        - issueDate: Unix timestamp in milliseconden
        - invoiceType: 'ALL_IN_ONE' (verkoopfactuur) of 'ADVERTISING_VIA_BOL'
        - legalMonetaryTotal.payableAmount.amount: bedrag (negatief = jij ontvangt, positief = jij betaalt)
        - invoicePeriod.startDate / endDate: periode-grenzen als Unix ms timestamps
        """
        def ms_to_date(ms_val) -> date | None:
            if not ms_val:
                return None
            return datetime.fromtimestamp(int(ms_val) / 1000, tz=timezone.utc).date()

        invoice_type = raw.get("invoiceType", "unknown")
        legal = raw.get("legalMonetaryTotal", {}) or {}
        payable = legal.get("payableAmount", {}) or {}
        raw_amount = float(payable.get("amount", 0))

        # Voor ALL_IN_ONE: bedrag is negatief in API → flip naar positief (= te ontvangen)
        # Voor ADVERTISING_VIA_BOL: bedrag is positief in API → laat zo (= te betalen)
        if invoice_type.upper() == "ALL_IN_ONE":
            total_amount = -raw_amount
        else:
            total_amount = raw_amount

        period = raw.get("invoicePeriod", {}) or {}
        return Invoice(
            invoice_id=str(raw.get("invoiceId", "")),
            invoice_date=ms_to_date(raw.get("issueDate")) or date.today(),
            invoice_type=invoice_type,
            period_start=ms_to_date(period.get("startDate")),
            period_end=ms_to_date(period.get("endDate")),
            total_amount=total_amount,
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
