# DELGOODS Cashflow Automation

Wekelijkse update van de [Cashflowprognose Google Sheet](https://docs.google.com/spreadsheets/d/1fpjAQ6GjzeNQ1eOKqr3pI-97Ll-xRGUNajXGZHYyEK4/edit) via GitHub Actions.

**Wat doet dit elke maandag om 06:00 CEST:**
1. Haalt via de Bol Retailer API alle uitbetaalfacturen + adverteerfacturen op van de afgelopen 6 maanden.
2. Schrijft per uitbetaling het netto bedrag (verkoop - adverteren) naar de "Werkelijk bedrag"-kolom in tab Inkomsten.
3. Berekent het rollend gemiddelde van de laatste 12 uitbetalingen en logt dit voor forecast-kalibratie.
4. Stuurt een Slack-bericht in `#cashflow` met een directe link om je banksaldo bij te werken.

## Eenmalige setup

### 1. Repository klonen / forken
```bash
git clone https://github.com/DELGOODS/cashflow.git
cd cashflow
```

### 2. Secrets toevoegen in GitHub
Ga naar **Settings → Secrets and variables → Actions → New repository secret**. Voeg deze 5 secrets toe:

| Secret naam                      | Waarde                                                                                                       |
|----------------------------------|--------------------------------------------------------------------------------------------------------------|
| `BOL_CLIENT_ID`                  | Client ID uit Bol seller dashboard → Instellingen → API (de "Claude" credentials)                            |
| `BOL_CLIENT_SECRET`              | Client secret uit dezelfde Bol API-pagina (alleen zichtbaar bij aanmaken — kopieer direct)                   |
| `GOOGLE_SERVICE_ACCOUNT_JSON`    | Volledige inhoud van het JSON-keybestand (download via Google Cloud Console → IAM → Service Accounts → Keys) |
| `SLACK_WEBHOOK_URL`              | Incoming webhook URL voor het #cashflow kanaal — zie stap 3 hieronder                                        |
| `CASHFLOW_SHEET_ID`              | `1fpjAQ6GjzeNQ1eOKqr3pI-97Ll-xRGUNajXGZHYyEK4` (deze waarde is hardcoded oké, maar als secret iets schoner)  |

### 3. Slack incoming webhook aanmaken
1. Ga naar https://api.slack.com/apps → Create New App → From scratch
2. App naam: "Cashflow Reminder", workspace: DELGOODS
3. In het app-menu links: **Incoming Webhooks** → toggle aan
4. Klik **Add New Webhook to Workspace**, kies kanaal `#cashflow` (`C0B2VFA2N10`)
5. Kopieer de gegenereerde URL (begint met `https://hooks.slack.com/services/T.../B.../...`)
6. Plak als `SLACK_WEBHOOK_URL` secret in GitHub

### 4. Workflow inschakelen
- GitHub Actions staat standaard aan voor nieuwe repos. Check **Actions tab** of `Weekly Cashflow Update` zichtbaar is.
- Eerste handmatige test: **Actions → Weekly Cashflow Update → Run workflow** (knop rechtsboven).

## Schedule
- Wekelijks, maandagen 04:00 UTC = **06:00 CEST** (zomer) / **05:00 CET** (winter)
- Cron: `0 4 * * 1` in `.github/workflows/weekly_update.yml`
- Wil je in winter ook 06:00 lokaal? Voeg een tweede schedule `0 5 * * 1` toe (en zorg dat het script idempotent is — wat het is, herhaalde runs schrijven dezelfde waardes).

## Lokaal testen (optioneel)
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Stel env vars lokaal in (NIET committen):
export BOL_CLIENT_ID="..."
export BOL_CLIENT_SECRET="..."
export GOOGLE_SERVICE_ACCOUNT_JSON="$(cat path/to/service-account.json)"
export SLACK_WEBHOOK_URL="..."
export CASHFLOW_SHEET_ID="1fpjAQ6GjzeNQ1eOKqr3pI-97Ll-xRGUNajXGZHYyEK4"

python -m src.main
```

## Wat als er iets misgaat
- Workflow logs: GitHub Actions tab → klik laatste run → bekijk stappen
- Bol API auth fail: check of credentials nog geldig zijn (na rotatie nieuwe waardes in Secrets zetten)
- Sheets write fail: check of `claude-sheets@delgoods-sheets-api.iam.gserviceaccount.com` editor-rechten heeft op de sheet
- Slack delivery fail: webhook URL is geldig zolang de Slack app bestaat; bij Slack workspace-wijziging opnieuw genereren

## Architectuur
```
src/
├── config.py          # Env vars laden + valideren
├── bol_api.py         # OAuth2 + invoice endpoints
├── sheets_writer.py   # Google Sheets API (service account)
├── slack_notifier.py  # Incoming webhook poster
└── main.py            # Orchestrator
```
