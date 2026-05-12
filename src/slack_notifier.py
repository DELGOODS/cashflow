"""Slack notifier — V1: incoming webhook met directe link naar banksaldo-cel.

Roep `send_banksaldo_reminder` aan na een succesvolle Bol-update om de
gebruiker eraan te herinneren zijn banksaldo bij te werken.
"""
from __future__ import annotations

import logging
from datetime import date

import requests

logger = logging.getLogger(__name__)


def build_sheet_link(sheet_id: str, range_a1: str) -> str:
    """URL die opent op een specifiek bereik in de sheet.

    Gebruik gid=0 als algemene fallback; de range-parameter zorgt dat
    de juiste cel geselecteerd wordt nadat de gebruiker naar het tabblad
    is genavigeerd.
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

    Block Kit-formaat: header + intro + actie-knop + context-info met laatste update.
    """
    link = build_sheet_link(sheet_id, banksaldo_cell)
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
                    "Klik op de knop hieronder, je springt direct naar de juiste cel."
                ),
            },
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Banksaldo invullen"},
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
