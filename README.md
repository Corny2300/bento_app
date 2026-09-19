# Hobby Bento 🍱 — Python edition

En lille mobil-first webapp til at oprette, rate og genbesøge bentos.

Denne version bruger **Python + Flask + Jinja + Supabase**. Næsten al app-logik ligger i Python. Der er kun en lille vanilla-JavaScript-fil til at tilføje/fjerne komponentfelter og vise et lokalt billedpreview, fordi de interaktioner sker direkte i browseren.

## Stack

- **Flask** — routes, formularer og app-logik
- **Jinja** — HTML templates
- **Supabase** — PostgreSQL-database + Storage
- **Pillow** — billedrotation/nedskalering/komprimering på serveren
- **HTML/CSS** — brugerfladen
- **Minimal JavaScript** — dynamiske komponentrækker + billedpreview

Der kræves **ingen Node/npm/Vite**.

## 1. Opret Supabase

1. Opret et Supabase-projekt.
2. Åbn **SQL Editor**.
3. Kopiér hele `supabase-setup.sql` ind og kør det.
4. Scriptet opretter tabeller, constraints, indexes, RLS/policies, Storage-bucket og lidt idempotent testdata.
5. Find projektets **Project URL** og browser-safe **Publishable/anon key** i projektets API-indstillinger.

> `supabase-setup.sql` er stadig prototype-opsætning: anonymous read/write er tilladt. Det gør appen nem at dele mellem jer, men enhver med app-adgang kan i princippet ændre data. Brug aldrig Supabase service-role key her.

## 2. Kør lokalt

### Windows PowerShell

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

### macOS/Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Udfyld derefter `.env`:

```env
SUPABASE_URL=https://YOUR_PROJECT.supabase.co
SUPABASE_PUBLISHABLE_KEY=YOUR_KEY
SUPABASE_IMAGE_BUCKET=bento-images
FLASK_SECRET_KEY=lav-en-lang-tilfældig-streng
FLASK_DEBUG=1
```

Start appen:

```bash
flask --app app run --debug
```

Åbn derefter normalt `http://127.0.0.1:5000`.

Du kan også køre:

```bash
python app.py
```

## 3. Hvad Python nu håndterer

`app.py` står for:

- hentning af bentos fra Supabase
- server-side rendering af sider
- oprettelse af bentos og komponenter
- case-insensitiv genbrug af komponenter
- ratings og opdatering af eksisterende rating fra samme navn
- favorites
- historik
- al analytics
- "Lav igen"
- billedvalidering
- EXIF-rotation
- nedskalering til max 1800 × 1800
- JPEG/WebP-komprimering
- upload til Supabase Storage
- fejlmeddelelser via Flask `flash()`

`static/app.js` gør kun to små browserting:

1. tilføjer/fjerner inputfelter til Bento-komponenter
2. viser billedpreview før formularen sendes

Alt, der vedrører database/data, ligger altså i Python.

## 4. Routes

```text
GET  /                       Dagens/seneste bento
GET  /bento/<id>             Åbn en bestemt bento
POST /bento/<id>/favorite    Slå favorit til/fra
POST /bento/<id>/rate        Gem/opdater rating
GET  /history                Historik
GET  /analytics              Analytics
GET  /new                    Ny Bento
POST /new                    Opret Bento
GET  /new?remake=<id>        Lav igen
```

## 5. Billeder

Tilladte uploadtyper:

- JPEG
- PNG
- WebP

Original upload må højst være **5 MB**. Flask/Pillow retter kameraets EXIF-orientering og nedskalerer derefter billedet til højst 1800 px på længste led. Almindelige billeder gemmes som optimeret JPEG; billeder med alpha gemmes som WebP.

Bento-rækken bliver oprettet før billed-upload. Hvis Storage-uploaden fejler, beholdes bentoen derfor stadig uden billede.

## 6. Deploy

Fordi dette nu er en Python-webserver, skal den hostes et sted, der kan køre Flask. En enkel mulighed er Render/Railway/Fly.io eller en anden Python-host.

Production start command:

```bash
gunicorn app:app
```

Sæt disse environment variables hos hosten:

```text
SUPABASE_URL
SUPABASE_PUBLISHABLE_KEY
SUPABASE_IMAGE_BUCKET
FLASK_SECRET_KEY
FLASK_DEBUG=0
```

Supabase er fortsat den fælles database, så begge telefoner ser samme bentos.

## 7. Projektstruktur

```text
hobby-bento-python/
├── app.py
├── requirements.txt
├── Procfile
├── .env.example
├── .gitignore
├── README.md
├── supabase-setup.sql
├── templates/
│   ├── base.html
│   ├── today.html
│   ├── history.html
│   ├── analytics.html
│   └── new.html
└── static/
    ├── style.css
    ├── app.js
    └── manifest.webmanifest
```

## 8. Datamodel

Datamodellen er den samme som før:

- `bentos`
- `components`
- `bento_components`
- `bento_ratings`
- `component_ratings`

Det betyder, at hvis du allerede har kørt `supabase-setup.sql` fra JavaScript-versionen, behøver databasen **ikke** at blive lavet om.
