# QuestEd

Piattaforma Django per i corsi di programmazione: corsi, verifiche, esercizi e
consegne degli studenti.

Un docente crea corsi e verifiche dall'admin; gli studenti si iscrivono, aprono
gli esercizi e consegnano. Gli esercizi sono di quattro tipi — domanda aperta,
scelta multipla, codice, diagramma di flusso — e l'interfaccia li marca con il
simbolo ISO del diagramma di flusso corrispondente, la stessa notazione che i
corsi insegnano.

## Stack

- Python 3.13, Django 5.2 LTS
- SQLite di default, PostgreSQL via `DATABASE_URL`
- Tailwind CSS v4, font self-hosted, nessuna CDN
- Mermaid per i diagrammi nelle consegne, Prism per il codice
- `django-modeltranslation` per i contenuti multilingua nel database,
  gettext (`locale/*.po`) per le stringhe dell'interfaccia

## Avvio locale

```bash
python -m venv .venv
.venv/bin/pip install -r quested/requirements-dev.txt

cp quested/.env.example quested/.env
# genera una SECRET_KEY e incollala nel .env:
.venv/bin/python -c "from django.core.management.utils import get_random_secret_key as g; print(g())"

cd quested
../.venv/bin/python manage.py migrate
../.venv/bin/python manage.py createsuperuser
../.venv/bin/python manage.py runserver
```

L'app risponde su http://127.0.0.1:8000/it/ — l'admin su `/it/admin/`.

## Front-end

Il CSS compilato è versionato, quindi per far girare l'app **non serve Node**.
Serve solo per modificare gli stili o aggiornare le librerie:

```bash
npm install
npm run watch:css     # ricompila mentre modifichi i template
npm run build         # CSS minificato + copia dei file vendor
```

I sorgenti stanno in `frontend/app.css`; l'output in
`quested/static/css/app.css`.

## Docker

```bash
cp .env.example.docker .env      # oppure crea .env con almeno SECRET_KEY
docker compose up -d
```

L'app risponde su http://localhost:8000/it/ — le migrazioni girano da sole
all'avvio. Il primo utente si crea con:

```bash
docker compose exec app python manage.py createsuperuser
```

Per avere qualcosa da guardare invece di una sequenza di schermate vuote:

```bash
docker compose exec app python manage.py seed_demo
```

Crea un corso dimostrativo con un esercizio di ogni tipo, una verifica valutata
e un'esercitazione con soluzioni rivelabili. È idempotente. Aggiungi
`--student-password <pw>` se vuoi entrare anche come studente; senza, l'account
`studente.demo` nasce senza password utilizzabile.

L'immagine è single-stage: il CSS compilato e i cataloghi `.mo` sono
versionati, quindi non serve Node né `compilemessages` in fase di build.
`collectstatic` gira al build con una `SECRET_KEY` usa-e-getta, perché
`settings.py` non ha un fallback per quella vera — l'assenza della chiave
deve essere un errore rumoroso, non un default silenzioso.

### Volumi

Due, entrambi necessari:

| Volume | Percorso | Contenuto |
|---|---|---|
| `quested-media` | `/app/quested/media` | file consegnati dagli studenti |
| `quested-data` | `/app/data` | database SQLite |

`quested-media` è il più delicato: il report PDF rilegge da disco i file
consegnati, quindi perdere quel volume significa perdere le consegne.

### SQLite o Postgres

Di default SQLite su volume, con `transaction_mode: IMMEDIATE` già impostato.
Con più worker gunicorn le scritture si serializzano: per una classe alla volta
va bene, ma è il tetto. Per superarlo basta decommentare il servizio `db` in
`docker-compose.yml` e impostare `DATABASE_URL` — il codice non cambia.

### Dietro un reverse proxy

Il proxy termina TLS e passa `X-Forwarded-Proto` (già atteso da
`SECURE_PROXY_SSL_HEADER`). Nel `.env`:

```bash
ALLOWED_HOSTS=quiz.esempio.it
CSRF_TRUSTED_ORIGINS=https://quiz.esempio.it
SECURE_SSL_REDIRECT=True
SECURE_HSTS_SECONDS=31536000
```

## Test e lint

```bash
.venv/bin/python -m pytest        # test sulle regole di accesso
.venv/bin/ruff check .
```

## Configurazione

Tutto passa da variabili d'ambiente, lette da `quested/.env` (mai
versionato). L'elenco completo con i valori di default è in
`quested/.env.example`.

In produzione servono almeno:

```bash
DEBUG=False
SECRET_KEY=<chiave generata>
ALLOWED_HOSTS=quiz.esempio.it
CSRF_TRUSTED_ORIGINS=https://quiz.esempio.it
SECURE_SSL_REDIRECT=True
SECURE_HSTS_SECONDS=31536000
```

Poi `manage.py collectstatic` (WhiteNoise serve i file con hash e compressione)
e `manage.py check --deploy` per verificare.

## Struttura

```text
quested-platform/
├── frontend/app.css      # sorgente Tailwind + design tokens
├── quested/
│   ├── manage.py
│   ├── .env.example
│   ├── quested/          # settings, urls, wsgi
│   ├── studenttest/      # modelli, view, admin, test
│   ├── templates/
│   ├── static/
│   └── locale/           # traduzioni gettext dell'interfaccia
├── Dockerfile
├── docker-compose.yml
└── pyproject.toml        # configurazione ruff e pytest
```

## Traduzioni

Due meccanismi distinti, non intercambiabili:

- **Interfaccia** — gettext. Dopo aver aggiunto stringhe:
  `manage.py makemessages -l en -l fr -l es` e poi `manage.py compilemessages`.
- **Contenuti** (titoli e testi degli esercizi) — `django-modeltranslation`,
  che crea le colonne `titolo_it`, `titolo_en`… I docenti le compilano
  dall'admin.
