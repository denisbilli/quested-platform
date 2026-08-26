"""Create a demo course that exercises every part of the interface.

Useful for a fresh container or a new checkout: without data the app is a
sequence of empty states. The seed covers all four exercise types, both a
graded verifica and an ungraded esercitazione, and a statement containing a
Mermaid flowchart, so every node shape and both answer modes are visible.

Idempotent: re-running updates the same objects instead of duplicating them.
"""

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from studenttest.models import Choice, Course, Enrollment, Exercise, Test

DEMO_STUDENT = "studente.demo"


class Command(BaseCommand):
    help = "Create (or refresh) a demo course with exercises of every type."

    def add_arguments(self, parser):
        parser.add_argument(
            "--owner",
            default=None,
            help="Username to own the demo content. Defaults to the first superuser.",
        )
        parser.add_argument(
            "--student-password",
            default=None,
            help=(
                "Password for the demo student. Without it the student is created "
                "with an unusable password and cannot log in."
            ),
        )

    @transaction.atomic
    def handle(self, *args, **options):
        owner = self._resolve_owner(options["owner"])

        course, _ = Course.objects.update_or_create(
            name="Introduzione alla programmazione",
            defaults={
                "description": (
                    "Corso dimostrativo: variabili, condizioni, cicli e diagrammi "
                    "di flusso. Contiene un esempio di ogni tipo di esercizio."
                ),
                "enabled": True,
                "creator": owner,
            },
        )

        practice = self._practice_test(course, owner)
        graded = self._graded_test(course, owner)

        student = self._demo_student(course, options["student_password"])

        self.stdout.write(self.style.SUCCESS("Demo pronta."))
        self.stdout.write(f"  corso        {course.name}")
        self.stdout.write(f"  esercitazione {practice.name} ({practice.exercises.count()} esercizi)")
        self.stdout.write(f"  verifica      {graded.name} ({graded.exercises.count()} esercizi)")
        self.stdout.write(f"  docente       {owner.username}")
        if student:
            self.stdout.write(f"  studente      {student.username}")

    # -- helpers ----------------------------------------------------------

    def _resolve_owner(self, username):
        if username:
            owner = User.objects.filter(username=username).first()
            if not owner:
                raise SystemExit(f"Nessun utente '{username}'.")
            return owner
        owner = User.objects.filter(is_superuser=True).order_by("pk").first()
        if not owner:
            raise SystemExit(
                "Nessun superuser. Crealo con `manage.py createsuperuser`, "
                "oppure passa --owner."
            )
        return owner

    def _exercise(self, test, owner, title, **defaults):
        defaults["creator"] = owner
        defaults.setdefault("enabled", True)
        exercise, _ = Exercise.objects.update_or_create(
            test=test, title=title, defaults=defaults
        )
        return exercise

    def _practice_test(self, course, owner):
        test, _ = Test.objects.update_or_create(
            name="Esercitazione: basi e diagrammi",
            course=course,
            defaults={
                "description": (
                    "Prova a risolverli da solo, poi rivela la soluzione e segna "
                    "quelli che hai completato."
                ),
                "enabled": True,
                "is_graded": False,
                "creator": owner,
            },
        )

        # Domanda aperta — terminator shape.
        self._exercise(
            test,
            owner,
            "Variabile locale e globale",
            description=(
                "<p>Spiega con parole tue la differenza fra una variabile "
                "<strong>locale</strong> e una <strong>globale</strong>, e di' cosa "
                "succede quando hanno lo stesso nome.</p>"
            ),
            type="O",
            expected_answer=(
                "Una variabile locale esiste solo dentro il blocco in cui è "
                "dichiarata e sparisce quando il blocco finisce. Una globale è "
                "visibile in tutto il file. Se hanno lo stesso nome, dentro il "
                "blocco la locale nasconde la globale (shadowing): la globale "
                "esiste ancora, ma non è raggiungibile per nome."
            ),
        )

        # Scelta multipla — decision shape.
        multiple = self._exercise(
            test,
            owner,
            "Quante volte stampa?",
            description=(
                "<p>Dato il ciclo:</p>"
                "<pre><code>for (int i = 0; i &lt; 5; i += 2) {\n"
                "    std::cout &lt;&lt; i &lt;&lt; \"\\n\";\n"
                "}</code></pre>"
                "<p>Quante righe vengono stampate?</p>"
            ),
            type="M",
        )
        self._choices(multiple, [("2", False), ("3", True), ("5", False), ("6", False)])

        # Diagramma di flusso — data shape, with a real Mermaid graph.
        self._exercise(
            test,
            owner,
            "Il numero è positivo?",
            description=(
                "<p>Leggi il diagramma di flusso e scrivi cosa stampa il programma "
                "se l'utente inserisce <strong>-3</strong>.</p>"
                '<div class="mermaid">\n'
                "graph TD\n"
                "    A[Inizio]\n"
                "    B[Leggi N]\n"
                "    C{N > 0?}\n"
                "    D[Stampa positivo]\n"
                "    E[Stampa non positivo]\n"
                "    F[Fine]\n"
                "    A --> B\n"
                "    B --> C\n"
                "    C -- Sì --> D\n"
                "    C -- No --> E\n"
                "    D --> F\n"
                "    E --> F\n"
                "</div>"
            ),
            type="D",
            expected_answer=(
                "Stampa \"non positivo\": -3 non è maggiore di zero, quindi il "
                "controllo prende il ramo No."
            ),
        )

        # Codice — process shape.
        self._exercise(
            test,
            owner,
            "Somma dei primi N numeri",
            description=(
                "<p>Scrivi un programma che legge un intero <code>N</code> e stampa "
                "la somma dei numeri da 1 a N.</p>"
            ),
            type="C",
            expected_answer=(
                "#include <iostream>\n\n"
                "int main() {\n"
                "    int n = 0;\n"
                "    std::cin >> n;\n\n"
                "    int somma = 0;\n"
                "    for (int i = 1; i <= n; ++i) {\n"
                "        somma += i;\n"
                "    }\n\n"
                "    std::cout << somma << \"\\n\";\n"
                "    return 0;\n"
                "}"
            ),
        )

        return test

    def _graded_test(self, course, owner):
        test, _ = Test.objects.update_or_create(
            name="Verifica: condizioni e cicli",
            course=course,
            defaults={
                "description": "Consegna entro la data indicata. Ogni esercizio ha un punteggio.",
                "enabled": True,
                "is_graded": True,
                "due_date": timezone.now() + timezone.timedelta(days=14),
                "creator": owner,
            },
        )

        self._exercise(
            test,
            owner,
            "Numero pari o dispari",
            description=(
                "<p>Scrivi un programma che legge un intero e stampa "
                "<code>pari</code> oppure <code>dispari</code>.</p>"
            ),
            type="C",
            score=10,
        )

        self._exercise(
            test,
            owner,
            "Tabellina",
            description=(
                "<p>Scrivi un programma che legge un intero <code>N</code> e stampa "
                "la sua tabellina da 1 a 10, una riga per riga.</p>"
            ),
            type="C",
            score=15,
        )

        self._exercise(
            test,
            owner,
            "Cosa fa questo codice?",
            description=(
                "<p>Descrivi in due righe cosa calcola questo frammento.</p>"
                "<pre><code>int r = 1;\n"
                "for (int i = 2; i &lt;= n; ++i) {\n"
                "    r *= i;\n"
                "}</code></pre>"
            ),
            type="O",
            score=5,
        )

        return test

    def _choices(self, exercise, options):
        exercise.choices.all().delete()
        Choice.objects.bulk_create(
            [Choice(exercise=exercise, text=text, is_correct=correct) for text, correct in options]
        )

    def _demo_student(self, course, password):
        student, created = User.objects.get_or_create(
            username=DEMO_STUDENT,
            defaults={"first_name": "Studente", "last_name": "Demo"},
        )
        if created:
            # No usable password unless one was asked for: a seeded account with
            # a known password is a liability if the seed ever runs in production.
            student.set_unusable_password()
        if password:
            student.set_password(password)
        student.save()

        Enrollment.objects.get_or_create(student=student, course=course)
        return student
