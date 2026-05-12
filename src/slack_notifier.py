"""Slack notifier — V1: incoming webhook met directe link naar Vercel cashflow dashboard.

Roep `send_banksaldo_reminder` aan na een succesvolle Bol-update om de
gebruiker eraan te herinneren zijn banksaldo bij te werken.
"""
from __future__ import annotations

import logging
from datetime import date

import requests

logger = logging.getLogger(__name__)

DASHBOARD_URL = "https://delgoods-bol-dashboard.vercel.app/cashflow"


def build_sheet_link(sheet_id: str, range_a1: str) -> str:
    """Fallback: URL naar een specifiek bereik in de sheet.

    Wordt momenteel niet gebruikt — we linken direct naar het Vercel dashboard
    waar banksaldo via UI ingevoerd én opgeslagen kan worden. Behouden voor
    backwards compatibiliteit als we ooit toch naar de sheet willen linken.
    """
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit?range={range_a1}"


def send_banksaldo_reminder(
    webhook_url: str,
    sheet_id: str,
    banksaldo_cell: str = "Instellingen!B4",
    rolling_avg_payout: float | None = None,
    actuals_written: int = 0,
) -> None:
    """Verstuur de wekelijkse banksaldo-reminder naar Slack.

    Block Kit-formaat: header + intro + actie-knop naar dashboard + context-info.
    De `sheet_id` en `banksaldo_cell` parameters blijven aanwezig voor backwards
    compatibility, maar de knop linkt nu naar het Vercel dashboard.
    """
    link = DASHBOARD_URL
    del sheet_id, banksaldo_cell  # niet meer gebruikt sinds switch naar dashboard
    _DUTCH_MONTHS = {
        1: "januari", 2: "februari", 3: "maart", 4: "april",
        5: "mei", 6: "juni", 7: "juli", 8: "augustus",
        9: "september", 10: "oktober", 11: "november", 12: "december",
    }
    _today = date.today()
    today = f"{_today.day} {_DUTCH_MONTHS[_today.month]} {_today.year}"

    context_lines: list[str] = []
    if actuals_written > 0:
        context_lines.append(f"{actuals_written} werkelijke Bol-uitbetalingen bijgewerkt")
    if rolling_avg_payout is not None and rolling_avg_payout > 0:
        context_lines.append(
            f"Rollend gemiddelde laatste 12 uitbetalingen: €{rolling_avg_payout:,.0f}".replace(",", ".")
        )
    context_text = " · ".join(context_lines) if context_lines else "Eerste run, geen historie"

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "Cashflowprognose — banksaldo update"},
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"Goedemorgen, het is {today}. "
                    "Tijd om je banksaldo bij te werken voor de cashflowprognose. "
                    "Klik op de knop hieronder om direct in het cashflow-dashboard "
                    "je actuele saldo in te voeren en op te slaan."
                ),
            },
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Open cashflow dashboard"},
                    "url": link,
                    "style": "primary",
                }
            ],
        },
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": context_text}],
        },
    ]

    payload = {"blocks": blocks, "text": "Tijd om je banksaldo bij te werken"}

    response = requests.post(webhook_url, json=payload, timeout=15)
    response.raise_for_status()
    logger.info("Slack: banksaldo-reminder verstuurd")
