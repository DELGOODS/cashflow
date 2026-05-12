"""Orchestrator — wekelijkse cashflow update.

Stappen:
1. Config laden uit env vars
2. Bol API: laatste 6 maanden uitbetalingen ophalen
3. Sheets: werkelijke bedragen schrijven naar Inkomsten kolom D
4. Bereken rollend gemiddelde voor forecast-kalibratie (alleen log voor nu)
5. Slack: stuur banksaldo-reminder met statistieken

Faalveiligheid: elk onderdeel kan falen zonder de rest te blokkeren.
Slack-bericht wordt verstuurd ook als Bol-stap mislukt — dan met error-melding,
zodat de gebruiker weet dat hij handmatig moet kijken.
"""
from __future__ import annotations

import logging
import sys
from datetime import date, timedelta

from .bol_api import BolAPIClient, NetPayout, rolling_average
from .config import Config, load_config
from .sheets_writer import SheetsWriter
from .slack_notifier import send_banksaldo_reminder


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("cashflow")


def fetch_bol_payouts(config: Config, lookback_days: int = 180) -> list[NetPayout]:
    client = BolAPIClient(config.bol_client_id, config.bol_client_secret)
    end = date.today()
    start = end - timedelta(days=lookback_days)
    return client.get_net_payouts(start, end)


def run() -> int:
    """Hoofdroutine. Returns exit code (0 = success, 1 = partial failure)."""
    try:
        config = load_config()
    except ValueError as e:
        logger.error(f"Config-fout: {e}")
        return 1

    payouts: list[NetPayout] = []
    actuals_written = 0
    rolling_avg: float | None = None
    bol_error: str | None = None

    # Stap 1: Bol API
    try:
        payouts = fetch_bol_payouts(config)
        logger.info(f"Bol: {len(payouts)} uitbetalingen verzameld")
    except Exception as e:
        bol_error = f"Bol API fout: {type(e).__name__}: {e}"
        logger.exception(bol_error)

    # Stap 2: Sheets update (alleen als Bol-stap lukte)
    if payouts:
        try:
            writer = SheetsWriter(config.google_service_account, config.cashflow_sheet_id)
            actuals_written = writer.write_actuals(
                tab=config.inkomsten_tab,
                start_row=config.inkomsten_data_start_row,
                end_row=config.inkomsten_data_end_row,
                payouts=payouts,
                match_window_days=5,  # Bol invoicedatum (1e/15e) vs sheet (3e/18e)
            )
            rolling_avg = rolling_average(payouts, window=12)
            logger.info(f"Rollend gemiddelde laatste 12 uitbetalingen: €{rolling_avg:.2f}")
        except Exception as e:
            logger.exception(f"Sheets-fout: {e}")

    # Stap 3: Slack reminder (altijd versturen)
    try:
        send_banksaldo_reminder(
            webhook_url=config.slack_webhook_url,
            sheet_id=config.cashflow_sheet_id,
            banksaldo_cell=config.instellingen_cell_banksaldo,
            rolling_avg_payout=rolling_avg,
            actuals_written=actuals_written,
        )
    except Exception as e:
        logger.exception(f"Slack-fout: {e}")
        return 1

    if bol_error:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(run())
