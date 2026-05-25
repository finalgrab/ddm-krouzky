# DDM Kroužky – Plánovač

Monitor a plánovač kroužků DDM Karlínské Spektrum pro tři děti: Vojta (11), Kryštof (10), Eli (7).

## Struktura

- `scraper.py` – stáhne aktuální kroužky z webu DDM
- `monitor.py` – porovná s předchozím stavem, detekuje nové/odstraněné kroužky
- `index.html` – webová aplikace s filtry a týdenním kalendářem
- `data/courses.json` – aktuální data kroužků
- `.github/workflows/monitor.yml` – GitHub Actions: automatický monitoring od 1.6.2026

## Použití

```bash
# Stáhnout aktuální kroužky
python3 scraper.py

# Spustit monitor (detekce nových)
python3 monitor.py

# Otevřít web
open index.html
# nebo spustit lokální server:
python3 -m http.server 8000
```

## GitHub Pages

1. Push repo na GitHub
2. Settings → Pages → Source: Deploy from branch `main`, folder `/ (root)`
3. Web bude na `https://<user>.github.io/ddm-krouzky/`
