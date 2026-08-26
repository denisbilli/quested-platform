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
.venv/bin/pip install -r quizmaker/requirements-dev.txt

cp quizmaker/.env.example quizmaker/.env
# genera una SECRET_KEY e incollala nel .env:
.venv/bin/python -c "from django.core.management.utils import get_random_secret_key as g; print(g())"

cd quizmaker
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
`quizmaker/static/css/app.css`.

## Test e lint

```bash
.venv/bin/python -m pytest        # test sulle regole di accesso
.venv/bin/ruff check .
```

## Configurazione

Tutto passa da variabili d'ambiente, lette da `quizmaker/.env` (mai
versionato). L'elenco completo con i valori di default è in
`quizmaker/.env.example`.

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
PyQuizMakerAdvanced/
├── frontend/app.css          # sorgente Tailwind + design tokens
├── quizmaker/
│   ├── manage.py
│   ├── .env.example
│   ├── quizmaker/            # settings, urls, wsgi
│   ├── studenttest/          # modelli, view, admin, test
│   ├── templates/
│   ├── static/
│   └── locale/               # traduzioni gettext dell'interfaccia
└── pyproject.toml            # configurazione ruff e pytest
```

## Traduzioni

Due meccanismi distinti, non intercambiabili:

- **Interfaccia** — gettext. Dopo aver aggiunto stringhe:
  `manage.py makemessages -l en -l fr -l es` e poi `manage.py compilemessages`.
- **Contenuti** (titoli e testi degli esercizi) — `django-modeltranslation`,
  che crea le colonne `titolo_it`, `titolo_en`… I docenti le compilano
  dall'admin.
