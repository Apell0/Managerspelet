# Klubbgrafik och matchställ

Genereringen av botklubbar letar automatiskt efter grafik i katalogen `data/graphics/`.
Skapa katalogerna om de inte redan finns:

```bash
mkdir -p data/graphics/emblems data/graphics/kits
```

- Placera klubbemblem i `data/graphics/emblems/`. Alla filformat som stöds av ditt terminalprogram fungerar (t.ex. `.png`, `.svg`).
- Placera tröj-/matchställbilder i `data/graphics/kits/`.

När du kör `manager-cli new ...` kopplas filerna i bokstavsordning till de genererade klubbarna. Om du har färre bilder än klubbar återanvänds de i rundgång.

Du kan när som helst byta ut bilderna i katalogerna. Vid nästa generering plockas de nya filerna upp automatiskt.

På lagsidan (`manager-cli club-view <klubb>`) visas relativa sökvägarna till emblem och matchställ, så att du enkelt kan öppna eller byta ut filerna.
