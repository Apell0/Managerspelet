# Managerspelet JSON CLI

Detta gränssnitt exponerar spelets funktioner som JSON-data via `python -m manager.tools.cli`.
Alla kommandon accepterar flaggorna `--file` (väg till sparfil), `--saves` (katalog för sparfiler)
och `--data` (JSON-payload för muterande kommandon). Utdata skrivs alltid som JSON.

## Karriärhantering

```bash
python -m manager.tools.cli career list
```

## Skapa och hantera karriär

```bash
python -m manager.tools.cli game new --data '{"league_structure":"pyramid","divisions":2,"teams_per_division":12}'
python -m manager.tools.cli game dump
python -m manager.tools.cli game save --name "backup"
python -m manager.tools.cli game load --career c-backup
```

## Inställningar

```bash
python -m manager.tools.cli options set --data '{"graphics":{"quality":"high"}}'
```

## Liga- och matchdata

```bash
python -m manager.tools.cli table get --scope total
python -m manager.tools.cli fixtures list --type league --round 5
python -m manager.tools.cli match get --id l-01-t-home-t-away
python -m manager.tools.cli match simulate --id l-01-t-home-t-away --mode viewer
python -m manager.tools.cli match set-result --id l-01-t-home-t-away --data '{"home_goals":2,"away_goals":1}'
```

## Lag, trupper och spelare

```bash
python -m manager.tools.cli team get --id t-0001
python -m manager.tools.cli squad get --team t-0001
python -m manager.tools.cli player get --id p-101
python -m manager.tools.cli tactics set --team t-0001 --data '{"tactic":{"attacking":true}}'
```

## Statistik

```bash
python -m manager.tools.cli stats get --scope players_current
```

## Ungdomssektion

```bash
python -m manager.tools.cli youth get
python -m manager.tools.cli youth set-preference --preference FW
python -m manager.tools.cli youth accept --club "Example FC" --index 0
```

## Transfer och ekonomi

```bash
python -m manager.tools.cli transfers market
python -m manager.tools.cli transfers buy --club "Example FC" --index 0
python -m manager.tools.cli transfers bid --data '{"buyer":"Example FC","seller":"Rival FC","player_id":42,"price":2500000}'
python -m manager.tools.cli economy get
python -m manager.tools.cli economy sponsor --club "Example FC" --amount 2000000
```

## Mail, cup och säsong

```bash
python -m manager.tools.cli mail list
python -m manager.tools.cli mail read --id mail-1
python -m manager.tools.cli cup get
python -m manager.tools.cli season start
python -m manager.tools.cli season end
python -m manager.tools.cli calendar next-week
```

Alla kommandon returnerar `{ "ok": true, ... }` eller `{ "ok": false, "error": {...} }` vid fel.

## Mock-läge och feature flags

- Sätt miljövariabeln `MANAGER_FEATURES=mock` eller skapa `FeatureFlags(mock_mode=True)` i Python för att starta ett demo-
  läge utan att skriva sparfiler.
- Ange `MANAGER_MOCK_PATH=/sökväg/till/mock.json` om du vill ladda/skriva ett specifikt mock-state.
- Använd `GameService.transaction()` eller `GameService.apply()` för att återanvända domänlogiken direkt i egen kod utan att gå
  via CLI-kommandon.
