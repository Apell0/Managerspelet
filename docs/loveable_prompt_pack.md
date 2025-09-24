# Loveable-integration för Managerspelet

Den här filen beskriver hur Loveables AI ska integrera mot spelets Python-API och
vilken prompt/dokumentation du ger modellen. Innehållet täcker **steg 3 och 4** i
arbetsplanen.

> ℹ️ **Kodbasens läge:** Alla filer och exempel som nämns här finns i
> `work`-branchen. Säkerställ att Loveable använder den branchen (inte `main`)
> när prompt-paketet byggs.

## Steg 3 – Integrationssätt (Desktop/TUI)

Loveable ska generera en **desktop/TUI-klient** (t.ex. med [Textual](https://textual.textualize.io/),
[`prompt_toolkit`](https://python-prompt-toolkit.readthedocs.io/) eller liknande). All
logik ska bo i samma Python-process som spelet – ingen HTTP-server behövs.

### Rekommenderad arkitektur

1. **Starta ett ServiceContext** i början av programmet:
   ```python
   from pathlib import Path
   from manager.api.services import ServiceContext, GameService

   ctx = ServiceContext.from_paths(Path("saves"), Path("saves/career.json"))
   services = GameService(ctx)
   ```
2. **Lagra `GameService` i en controller** som UI-komponenter kan anropa. Returnera
   alltid strukturerade dict/listor (de är JSON-säkra direkt från tjänsterna).
3. **Rendera vyer direkt från svaren** – inga extra formatteringslager krävs. Alla
   kontrakt följer `manager/api/contracts.py`.
4. **Schemalägg tunga operationer** (matchsimulering, säsongsavslut) i en bakgrunds-
   tråd eller `async`-task om TUI-biblioteket kräver det. Alla tjänster är rent
   CPU-bundna och trådsäkra så länge du kör en operation åt gången.

### Skärmar & serviceanrop

| Skärm                              | Viktiga metoder i `GameService`                            |
|------------------------------------|-----------------------------------------------------------|
| Startmeny                          | `create`, `dump`, `save_as`, `careers.list_careers()`      |
| Ligavy (tabell, schema, XI)        | `dump()["standings"]`, `dump()["fixtures"]`, `dump()["stats"]` |
| Cupsida                            | `dump()["cups"]`, `simulate_match` för cupmatcher          |
| Lagsida                            | `dump()["teams"]`, `dump()["squads"]`, `dump()["history"]`   |
| Matchdetaljer                      | `get_match_details`, `simulate_match`                      |
| Transfers & ekonomi                | `buy_from_market`, `submit_transfer_bid`, `sponsor_activity`, `dump()["economy"]` |
| Ungdom/juniorer                    | `dump()["youth"]`, `accept_junior`, `set_youth_preference` |
| Taktik, lineup & kapten            | `set_tactics`, `dump()["teams"]`                          |
| Mail                               | `dump()["mail"]`, `mark_mail_read`                        |
| Säsongsflöde                       | `start_season`, `end_season`, `next_week`                  |

> 💡 `dump()` returnerar hela GameState-kontraktet. UI:t kan cacha resultatet och
> bara uppdatera relevanta sektioner efter varje muterande anrop.

### Händelseflöde i TUI:n

1. **Initiera** – ladda befintlig sparfil via `services.dump()`. Om filen saknas,
   erbjud att skapa en ny karriär med `services.create(payload)`.
2. **Navigation** – varje vy hämtar data från cachen. När användaren gör en handling
   (t.ex. accepterar junior), anropa motsvarande metod och uppdatera cachen genom
   att köra `dump()` igen eller uppdatera det relevanta delträdet lokalt.
3. **Matchsimulering** – kalla `simulate_match(match_id, mode="viewer")`. Svaret
   innehåller `match_id` som UI:t använder för att automatiskt öppna matchdetaljer.
4. **Spara/Ladda** – `save_as("mitt_save")` för manuella saves, `careers.list_careers()`
   för att visa alla sparfiler, `load_career(career_id)` för att byta.

## Steg 4 – Prompt- & dokumentationspaket

Ge Loveable följande material innan du ber modellen generera kod.

### 4.1 Bas-prompt

```
Du är en Python-utvecklare som bygger ett Textual-baserat TUI åt managerspelet.
Använd endast tjänsterna i `manager.api.services.GameService`. Alla operationer
ska hämta och mutera data via dessa metoder och därefter uppdatera den lokala
cachen. Ingen direkt fil- eller JSON-manipulation utanför tjänsterna.
```

### 4.2 Snabbreferens (delad med modellen)

- **Init**
  ```python
  from pathlib import Path
  from manager.api.services import ServiceContext, GameService

from manager.api import FeatureFlags

flags = FeatureFlags(mock_mode=True)  # mock-läge för prototyping
ctx = ServiceContext.from_paths(Path("saves"), flags=flags)
services = GameService(ctx)
state = services.dump()
```
- **Karriärer**: `services.careers.list_careers()` → lista, `services.load_career(id)`
- **Mock-läge**: skapa `FeatureFlags(mock_mode=True)` för att få en förifylld demo-karriär utan sparfiler
- **Matcher**: `services.simulate_match(match_id, mode="viewer")`,
  `services.get_match_details(match_id)`
- **Ligadata**: `state["standings"]`, `state["fixtures"]`, `state["stats"]`
- **Lag & trupp**: `state["teams"]`, `state["squads"][team_id]`
- **Transfers/juniorer**: `services.buy_from_market`, `services.accept_junior`,
  `services.submit_transfer_bid`, `state["transfers"]`, `state["youth"]`
- **Ekonomi**: `state["economy"]`, `services.sponsor_activity`
- **Taktik**: `services.set_tactics(team_id, payload)`
- **Säsong**: `services.start_season()`, `services.end_season()`, `services.next_week()`
- **Avancerat**: använd `services.transaction()` eller `services.apply(func)` om UI:t behöver köra egen domänlogik i samma process

### 4.3 Exempelflöden

1. **Starta ny karriär och visa dashboard**
   ```python
   payload = {
       "league_structure": "pyramid",
       "divisions": 2,
       "teams_per_division": 12,
       "user_team": {"name": "Test FC"},
       "manager": {"name": "Coach"}
   }
   services.create(payload)
   state = services.dump()
   ```
   - Visa från `state["season"]`, `state["standings"]["total"]`, `state["fixtures"]`.

2. **Acceptera junior och uppdatera vy**
   ```python
   services.accept_junior("Test FC", index=0)
   state = services.dump()
   juniors = state["youth"]["accepted"]
   ```

3. **Simulera match och öppna matchdetaljer**
   ```python
   response = services.simulate_match(match_id, mode="viewer")
   details = services.get_match_details(response["match_id"])
   ```
   - Rendera lineups från `details["lineups"]`, händelser från `details["events"]`.

4. **Säsongsavslut med rapport**
   ```python
   report = services.end_season()["report"]
   ```
   - Skicka rapporttexten till en loggvy i TUI:t.

### 4.4 Datastrukturer att dela med Loveable

- **GameState-kontraktet** finns som JSON-schema i `manager/api/contracts.py`. Bifoga
  utdrag för de sektioner TUI:t behöver (t.ex. `teams`, `squads`, `fixtures`).
- **MatchDetails** byggs av `get_match_details` och innehåller lineups, händelser,
  statistik, taktikanalys, ratings per lagdel och utmärkelser.
- **Felrespons**: Alla metoder kastar `ServiceError` som bör fångas i UI:t och visas
  som dialog/flash-meddelande.

### 4.5 Tips till modellen

- Håll en central `state_store` med senaste `dump()` för att undvika upprepade disk-
  läsningar.
- Skapa komponenter per skärm (dashboard, ligavy, cupvy, match, transfers, ungdom,
  ekonomi). Varje komponent bör ha en `refresh()` som anropar rätt sektion ur `state`.
- När en mutation lyckas (`response["ok"] is True`), uppdatera cachen med en ny
  `dump()` innan du renderar.
- För textbaserade diagram (formbars, pluppar) kan du använda Unicode-block (▁▂▃▅█)
  eller färger som biblioteket erbjuder.

---

Dela den här filen tillsammans med `README_CLI.md` och relevanta JSON-exempel när
du kör Loveables UI-generering.
