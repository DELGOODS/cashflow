"""Google Sheets writer.

Schrijft werkelijke Bol uitbetalingen naar de 'Werkelijk bedrag (override)'-kolom
in tab Inkomsten van de Cashflowprognose sheet.

Match-logica: voor elke NetPayout zoeken we de rij waar:
- kolom B (Bron) = 'Bol uitbetaling'
- kolom A (Datum) ligt binnen ±2 dagen van payout_date

Bol kan 1 dag later/eerder uitbetalen dan onze geseede 3e/18e — daarom een marge.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Iterable

from google.oauth2 import service_account
from googleapiclient.discovery import build

from .bol_api import NetPayout

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


class SheetsWriter:
    def __init__(self, service_account_info: dict, sheet_id: str):
        creds = service_account.Credentials.from_service_account_info(
            service_account_info, scopes=SCOPES
        )
        self._service = build("sheets", "v4", credentials=creds, cache_discovery=False)
        self.sheet_id = sheet_id

    def _values(self):
        return self._service.spreadsheets().values()

    def read_inkomsten_dates(
        self, tab: str, start_row: int, end_row: int
    ) -> list[tuple[int, date | None, str]]:
        """Lees datum (kolom A) en bron (kolom B) per rij.

        Returns list van (row_number, date_or_none, bron).
        """
        rng = f"{tab}!A{start_row}:B{end_row}"
        result = self._values().get(
            spreadsheetId=self.sheet_id,
            range=rng,
            valueRenderOption="UNFORMATTED_VALUE",
            dateTimeRenderOption="SERIAL_NUMBER",
        ).execute()

        rows = result.get("values", [])
        out: list[tuple[int, date | None, str]] = []
        for i, row in enumerate(rows):
            row_num = start_row + i
            datum = self._parse_serial_date(row[0]) if row and row[0] != "" else None
            bron = row[1] if len(row) > 1 else ""
            out.append((row_num, datum, bron))
        return out

    @staticmethod
    def _parse_serial_date(value) -> date | None:
        """Google Sheets serial number → Python date (epoch 30 dec 1899)."""
        try:
            serial = int(float(value))
        except (TypeError, ValueError):
            return None
        epoch = date(1899, 12, 30)
        return epoch + timedelta(days=serial)

    def write_actuals(
        self,
        tab: str,
        start_row: int,
        end_row: int,
        payouts: Iterable[NetPayout],
        match_window_days: int = 2,
    ) -> int:
        """Voor elke NetPayout: zoek matching Bol-rij en schrijf netto bedrag in kolom D.

        Returns aantal rijen dat werd geupdate.
        """
        rows = self.read_inkomsten_dates(tab, start_row, end_row)
        bol_rows = [(r, d) for r, d, b in rows if b == "Bol uitbetaling" and d is not None]

        updates: list[dict] = []
        for payout in payouts:
            best_match = self._find_closest(payout.payout_date, bol_rows, match_window_days)
            if best_match is None:
                logger.info(
                    f"Geen match in sheet voor uitbetaling {payout.payout_date} "
                    f"(€{payout.net_amount:.2f}) — toegevoegd aan log voor handmatig nakijken"
                )
                continue
            updates.append({
                "range": f"{tab}!D{best_match}",
                "values": [[round(payout.net_amount, 2)]],
            })

        if not updates:
            logger.info("Geen werkelijke uitbetalingen om te schrijven")
            return 0

        body = {"valueInputOption": "USER_ENTERED", "data": updates}
        self._values().batchUpdate(
            spreadsheetId=self.sheet_id, body=body
        ).execute()
        logger.info(f"Sheets: {len(updates)} werkelijke uitbetalingen geschreven")
        return len(updates)

    def write_value(self, cell_a1: str, value) -> None:
        """Schrijf één waarde naar een cel via batchUpdate."""
        self._values().update(
            spreadsheetId=self.sheet_id,
            range=cell_a1,
            valueInputOption="USER_ENTERED",
            body={"values": [[value]]},
        ).execute()
        logger.info(f"Sheets: cel {cell_a1} bijgewerkt met {value}")

    @staticmethod
    def _find_closest(
        target: date, candidates: list[tuple[int, date]], window_days: int
    ) -> int | None:
        """Vind de rij met datum dichtst bij target, binnen window_days."""
        in_window = [
            (r, d) for r, d in candidates if abs((d - target).days) <= window_days
        ]
        if not in_window:
            return None
        # Sorteer op afstand, kies dichtste
        in_window.sort(key=lambda x: abs((x[1] - target).days))
        return in_window[0][0]
