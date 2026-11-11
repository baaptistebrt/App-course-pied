"""
Récap du dimanche soir : séances de la semaine à venir pour chaque élève, bilan pour le coach.

Lancé chaque dimanche par GitHub (fichier `.github/workflows/recap.yml` du dépôt des DONNÉES,
voir le README, partie « Récap du dimanche »). Peut aussi être lancé à la main :

    python tools/recap_hebdo.py --data chemin/vers/data            # envoie les e-mails
    python tools/recap_hebdo.py --data chemin/vers/data --essai    # affiche sans rien envoyer
    python tools/recap_hebdo.py --data ... --apercu moi@exemple.fr # tout envoyer à une seule adresse

Configuration e-mail par variables d'environnement (secrets GitHub) :
    PLAN_EMAIL_USER, PLAN_EMAIL_PASSWORD, PLAN_EMAIL_APP_URL, PLAN_EMAIL_SENDER_NAME (facultatif)
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.emails import load_email_config  # noqa: E402
from core.recap import run_weekly  # noqa: E402
from core.stockage import Store  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Récap du dimanche par e-mail")
    parser.add_argument("--data", required=True, help="dossier des données (celui qui contient eleves/ et suivi/)")
    parser.add_argument("--essai", action="store_true", help="n'envoie rien, affiche ce qui serait envoyé")
    parser.add_argument("--apercu", default="", help="envoie le bilan du coach et un récap élève à cette adresse")
    parser.add_argument("--date", default="", help="date du jour (AAAA-MM-JJ), pour les essais")
    args = parser.parse_args(argv)

    data = Path(args.data)
    if not (data / "eleves").exists():
        print(f"Dossier de données introuvable ou vide : {data.resolve()}")
        return 1
    config = load_email_config()
    if config is None:
        print("E-mails non configurés : ajoute PLAN_EMAIL_USER et PLAN_EMAIL_PASSWORD (secrets GitHub).")
        return 1
    today = date.fromisoformat(args.date) if args.date else date.today()
    results = run_weekly(Store(data), config, config.app_url, today, dry_run=args.essai,
                         preview_to=args.apercu or None)
    for r in results:
        print(f"{'OK ' if r.ok else 'ÉCHEC'} {r.to} — {r.subject} — {r.message}")
    print(f"{sum(r.ok for r in results)} e-mail(s) sur {len(results)}.")
    return 0 if all(r.ok for r in results) else 2


if __name__ == "__main__":
    sys.exit(main())
