"""Visuele opmaak van de Cashflowprognose sheets.

Eenmalig draaien om bold headers, gele achtergrond voor bewerkbare cellen,
en euro-formattering toe te passen. Idempotent — opnieuw draaien is veilig.
"""
from __future__ import annotations

import logging
import sys

from google.oauth2 import service_account
from googleapiclient.discovery import build

from .config import load_config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("format_sheets")


SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# Kleuren (RGB 0-1)
YELLOW_EDITABLE = {"red": 1.0, "green": 0.95, "blue": 0.6}
GRAY_HEADER = {"red": 0.92, "green": 0.92, "blue": 0.92}
GREEN_BG = {"red": 0.85, "green": 0.95, "blue": 0.85}
RED_BG = {"red": 1.0, "green": 0.85, "blue": 0.85}
ORANGE_BG = {"red": 1.0, "green": 0.92, "blue": 0.75}
WHITE = {"red": 1.0, "green": 1.0, "blue": 1.0}


def grid_range(sheet_id: int, start_row: int, end_row: int, start_col: int, end_col: int) -> dict:
    """0-indexed, end exclusive."""
    return {
        "sheetId": sheet_id,
        "startRowIndex": start_row,
        "endRowIndex": end_row,
        "startColumnIndex": start_col,
        "endColumnIndex": end_col,
    }


def repeat_cell(rng: dict, fmt: dict, fields: str) -> dict:
    return {
        "repeatCell": {
            "range": rng,
            "cell": {"userEnteredFormat": fmt},
            "fields": fields,
        }
    }


def build_format_requests(sheet_ids: dict[str, int]) -> list[dict]:
    """Bouw alle formatting requests op voor de 4 tabbladen."""
    reqs: list[dict] = []

    dashboard = sheet_ids["Dashboard"]
    inkomsten = sheet_ids["Inkomsten"]
    uitgaven = sheet_ids["Uitgaven"]
    instellingen = sheet_ids["Instellingen"]

    # === DASHBOARD ===
    # A1 title: bold, fontSize 14
    reqs.append(repeat_cell(
        grid_range(dashboard, 0, 1, 0, 8),
        {"textFormat": {"bold": True, "fontSize": 14}},
        "userEnteredFormat.textFormat",
    ))
    # A4:A6 labels: bold
    reqs.append(repeat_cell(
        grid_range(dashboard, 3, 6, 0, 1),
        {"textFormat": {"bold": True}},
        "userEnteredFormat.textFormat",
    ))
    # A8:H8 headers: bold + gray bg
    reqs.append(repeat_cell(
        grid_range(dashboard, 7, 8, 0, 8),
        {"textFormat": {"bold": True}, "backgroundColor": GRAY_HEADER},
        "userEnteredFormat(textFormat,backgroundColor)",
    ))
    # D9:G21 bedragen: currency
    reqs.append(repeat_cell(
        grid_range(dashboard, 8, 21, 3, 7),
        {"numberFormat": {"type": "CURRENCY", "pattern": "[$€-nl-NL] #,##0"}},
        "userEnteredFormat.numberFormat",
    ))
    # A23 KPI header: bold, fontSize 12
    reqs.append(repeat_cell(
        grid_range(dashboard, 22, 23, 0, 8),
        {"textFormat": {"bold": True, "fontSize": 12}},
        "userEnteredFormat.textFormat",
    ))
    # B24:B30 KPI values (some currency, some count) — apply currency to first 4
    reqs.append(repeat_cell(
        grid_range(dashboard, 23, 26, 1, 2),
        {"numberFormat": {"type": "CURRENCY", "pattern": "[$€-nl-NL] #,##0"}},
        "userEnteredFormat.numberFormat",
    ))
    reqs.append(repeat_cell(
        grid_range(dashboard, 27, 30, 1, 2),
        {"numberFormat": {"type": "CURRENCY", "pattern": "[$€-nl-NL] #,##0"}},
        "userEnteredFormat.numberFormat",
    ))
    # A32 toelichting header: bold
    reqs.append(repeat_cell(
        grid_range(dashboard, 31, 32, 0, 1),
        {"textFormat": {"bold": True}},
        "userEnteredFormat.textFormat",
    ))

    # === INKOMSTEN ===
    reqs.append(repeat_cell(
        grid_range(inkomsten, 0, 1, 0, 6),
        {"textFormat": {"bold": True, "fontSize": 14}},
        "userEnteredFormat.textFormat",
    ))
    # A4:F4 headers: bold + gray bg
    reqs.append(repeat_cell(
        grid_range(inkomsten, 3, 4, 0, 6),
        {"textFormat": {"bold": True}, "backgroundColor": GRAY_HEADER},
        "userEnteredFormat(textFormat,backgroundColor)",
    ))
    # D5:D52 werkelijk bedrag override: yellow bg
    reqs.append(repeat_cell(
        grid_range(inkomsten, 4, 52, 3, 4),
        {"backgroundColor": YELLOW_EDITABLE},
        "userEnteredFormat.backgroundColor",
    ))
    # C5:E54 bedragen: currency
    reqs.append(repeat_cell(
        grid_range(inkomsten, 4, 54, 2, 5),
        {"numberFormat": {"type": "CURRENCY", "pattern": "[$€-nl-NL] #,##0.00"}},
        "userEnteredFormat.numberFormat",
    ))
    # B54 totaal label: bold
    reqs.append(repeat_cell(
        grid_range(inkomsten, 53, 54, 1, 2),
        {"textFormat": {"bold": True}},
        "userEnteredFormat.textFormat",
    ))

    # === UITGAVEN ===
    reqs.append(repeat_cell(
        grid_range(uitgaven, 0, 1, 0, 5),
        {"textFormat": {"bold": True, "fontSize": 14}},
        "userEnteredFormat.textFormat",
    ))
    # A2 subtitel: italic, kleiner
    reqs.append(repeat_cell(
        grid_range(uitgaven, 1, 2, 0, 5),
        {"textFormat": {"italic": True, "fontSize": 9}},
        "userEnteredFormat.textFormat",
    ))
    # A4:E4 headers
    reqs.append(repeat_cell(
        grid_range(uitgaven, 3, 4, 0, 5),
        {"textFormat": {"bold": True}, "backgroundColor": GRAY_HEADER},
        "userEnteredFormat(textFormat,backgroundColor)",
    ))
    # D5:D208 bedragen: currency
    reqs.append(repeat_cell(
        grid_range(uitgaven, 4, 208, 3, 4),
        {"numberFormat": {"type": "CURRENCY", "pattern": "[$€-nl-NL] #,##0.00"}},
        "userEnteredFormat.numberFormat",
    ))
    # D211 totaal: currency + bold
    reqs.append(repeat_cell(
        grid_range(uitgaven, 210, 211, 2, 4),
        {"textFormat": {"bold": True},
         "numberFormat": {"type": "CURRENCY", "pattern": "[$€-nl-NL] #,##0.00"}},
        "userEnteredFormat(textFormat,numberFormat)",
    ))

    # === INSTELLINGEN ===
    reqs.append(repeat_cell(
        grid_range(instellingen, 0, 1, 0, 3),
        {"textFormat": {"bold": True, "fontSize": 14}},
        "userEnteredFormat.textFormat",
    ))
    # Section headers: A3, A7, A11, A15, A22, A36 → rows 2, 6, 10, 14, 21, 35
    # (BOL OMZETVERWACHTING op rij 22 nu, met blanco rij 21 ervoor)
    for row in [2, 6, 10, 14, 21, 35]:
        reqs.append(repeat_cell(
            grid_range(instellingen, row, row + 1, 0, 3),
            {"textFormat": {"bold": True, "fontSize": 11}, "backgroundColor": GRAY_HEADER},
            "userEnteredFormat(textFormat,backgroundColor)",
        ))
    # Headers van Bol omzet tabel A23:B23 → row 22
    reqs.append(repeat_cell(
        grid_range(instellingen, 22, 23, 0, 2),
        {"textFormat": {"bold": True}},
        "userEnteredFormat.textFormat",
    ))
    # Yellow editable cells:
    # B4 (banksaldo), B16-B19 (forecast params), B24:B35 (Bol omzetverwachting per maand)
    reqs.append(repeat_cell(
        grid_range(instellingen, 3, 4, 1, 2),
        {"backgroundColor": YELLOW_EDITABLE},
        "userEnteredFormat.backgroundColor",
    ))
    reqs.append(repeat_cell(
        grid_range(instellingen, 15, 19, 1, 2),
        {"backgroundColor": YELLOW_EDITABLE},
        "userEnteredFormat.backgroundColor",
    ))
    reqs.append(repeat_cell(
        grid_range(instellingen, 23, 35, 1, 2),
        {"backgroundColor": YELLOW_EDITABLE},
        "userEnteredFormat.backgroundColor",
    ))
    # Witte achtergrond op blanco rij 21 (om eerdere yellow/gray styling op te ruimen)
    reqs.append(repeat_cell(
        grid_range(instellingen, 20, 21, 0, 3),
        {"backgroundColor": WHITE, "textFormat": {"bold": False, "fontSize": 10}},
        "userEnteredFormat(backgroundColor,textFormat)",
    ))
    # B20 rolling avg (auto, NOT editable, so light green to onderscheiden)
    reqs.append(repeat_cell(
        grid_range(instellingen, 19, 20, 1, 2),
        {"backgroundColor": GREEN_BG,
         "numberFormat": {"type": "CURRENCY", "pattern": "[$€-nl-NL] #,##0.00"}},
        "userEnteredFormat(backgroundColor,numberFormat)",
    ))
    # B4 banksaldo: currency
    reqs.append(repeat_cell(
        grid_range(instellingen, 3, 4, 1, 2),
        {"numberFormat": {"type": "CURRENCY", "pattern": "[$€-nl-NL] #,##0.00"}},
        "userEnteredFormat.numberFormat",
    ))
    # B16 conversie: percent
    reqs.append(repeat_cell(
        grid_range(instellingen, 15, 16, 1, 2),
        {"numberFormat": {"type": "PERCENT", "pattern": "0%"}},
        "userEnteredFormat.numberFormat",
    ))
    # B18, B19 Amazon/Webshops: currency
    reqs.append(repeat_cell(
        grid_range(instellingen, 17, 19, 1, 2),
        {"numberFormat": {"type": "CURRENCY", "pattern": "[$€-nl-NL] #,##0"}},
        "userEnteredFormat.numberFormat",
    ))
    # B24:B35 Bol omzet: currency
    reqs.append(repeat_cell(
        grid_range(instellingen, 23, 35, 1, 2),
        {"numberFormat": {"type": "CURRENCY", "pattern": "[$€-nl-NL] #,##0"}},
        "userEnteredFormat.numberFormat",
    ))

    return reqs


def build_conditional_format_requests(dashboard_sheet_id: int) -> list[dict]:
    """Status-kolom kleuren op basis van tekst: NEGATIEF rood, KRAP oranje, OK groen."""
    reqs: list[dict] = []
    base_range = grid_range(dashboard_sheet_id, 8, 21, 7, 8)  # H9:H21

    # NEGATIEF → rood
    reqs.append({
        "addConditionalFormatRule": {
            "rule": {
                "ranges": [base_range],
                "booleanRule": {
                    "condition": {"type": "TEXT_EQ", "values": [{"userEnteredValue": "NEGATIEF"}]},
                    "format": {"backgroundColor": RED_BG, "textFormat": {"bold": True}},
                },
            },
            "index": 0,
        }
    })
    # KRAP → oranje
    reqs.append({
        "addConditionalFormatRule": {
            "rule": {
                "ranges": [base_range],
                "booleanRule": {
                    "condition": {"type": "TEXT_EQ", "values": [{"userEnteredValue": "KRAP"}]},
                    "format": {"backgroundColor": ORANGE_BG, "textFormat": {"bold": True}},
                },
            },
            "index": 0,
        }
    })
    # OK → groen
    reqs.append({
        "addConditionalFormatRule": {
            "rule": {
                "ranges": [base_range],
                "booleanRule": {
                    "condition": {"type": "TEXT_EQ", "values": [{"userEnteredValue": "OK"}]},
                    "format": {"backgroundColor": GREEN_BG},
                },
            },
            "index": 0,
        }
    })
    return reqs


def run() -> int:
    try:
        config = load_config()
    except ValueError as e:
        logger.error(f"Config-fout: {e}")
        return 1

    creds = service_account.Credentials.from_service_account_info(
        config.google_service_account, scopes=SCOPES
    )
    service = build("sheets", "v4", credentials=creds, cache_discovery=False)

    # Haal sheet IDs op
    meta = service.spreadsheets().get(spreadsheetId=config.cashflow_sheet_id).execute()
    sheet_ids = {s["properties"]["title"]: s["properties"]["sheetId"] for s in meta["sheets"]}
    logger.info(f"Sheet IDs: {sheet_ids}")

    requests = build_format_requests(sheet_ids)
    requests.extend(build_conditional_format_requests(sheet_ids["Dashboard"]))
    logger.info(f"Verstuur {len(requests)} formatting requests")

    service.spreadsheets().batchUpdate(
        spreadsheetId=config.cashflow_sheet_id,
        body={"requests": requests},
    ).execute()
    logger.info("Formatting toegepast")
    return 0


if __name__ == "__main__":
    sys.exit(run())
