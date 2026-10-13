"""
Modèles de référence (6 semaines d'entraînement + semaine de course) pour chaque distance.

* Marathon : transcription du fichier Excel (semaines S1 à S7 ; la S0 vide n'est pas reprise).
  La colonne « tps k » de l'Excel donne le type d'allure : =N5 Endurance, =N6/F4 A1, =N7 A2,
  =N8 A3, =N9 A4, =N10 Sprint.
* Semi-marathon et 10 km : propositions construites dans le même esprit (mêmes notations,
  mêmes allures), à ajuster par le coach dans l'onglet « Modèle de référence ».

Fréquence : chaque séance est marquée « 3-4 » (faite dans tous les cas) ou « 4 » (faite
seulement quand l'élève s'entraîne 4 fois par semaine). Avec 3 séances, on garde la qualité
et la sortie longue, et on retire en priorité le footing d'endurance.
"""

from __future__ import annotations

from .config import FREQ_ALWAYS, FREQ_ONLY_4, RACE_DAY_LABEL

TAPER = "Affûtage : assimilation / récupération / refaire du jus !"


def _s(seance, km_env="", duree_env="", contenu="", allure=None, km_spe=None,
       frequence=FREQ_ALWAYS, remarque=""):
    return {"seance": seance, "km_env": km_env, "duree_env": duree_env, "contenu": contenu,
            "km_spe": km_spe, "allure": allure, "frequence": frequence, "remarque": remarque}


ONLY4 = FREQ_ONLY_4

# --------------------------------------------------------------------------- Marathon (Excel)
MARATHON: list[dict] = [
    {"phase": "", "sessions": [                                            # S01 (31/08)
        _s("s1", "13", "1:10", '2x(6x30"/30")', "Sprint"),
        _s("s2", "10", "1:00", "2x1000 A2", "A2", frequence=ONLY4),
        _s("s3", "12", "1:10", "2x2000 A1 r=1000", "A1"),
        _s("s4", "22", "2:00", "endurance dont 2x1000 A1 r=2", "A1"),
    ]},
    {"phase": "", "sessions": [                                            # S02 (07/09)
        _s("s1", "13", "1:15", '8x30"/30"', "Sprint"),
        _s("s2", "14", "1:20", "2x2000 A1 r=1000", "A1"),
        _s("s3", "10", "1:00", "end", "Endurance", frequence=ONLY4),
        _s("s4", "25", "2:20", "end dont 2x20' A2", "A2"),
    ]},
    {"phase": "Endurance", "sessions": [                                   # S03 (14/09)
        _s("s1", "16", "1:35", "2000 A2", "A2"),
        _s("s2", "16", "1:30", "3x2000 A1", "A1"),
        _s("s3", frequence=ONLY4),
        _s("s4", "25 à 27", "2:30", "end dont 2x30' A1", "A1"),
    ]},
    {"phase": "", "sessions": [                                            # S04 (21/09)
        _s("s1", "12", "1:10", "endurance", "Endurance", frequence=ONLY4),
        _s("s2", "12", "1:10", "2x2000 A1", "A1"),
        _s("s3", "14", "1:20", "2x2000 A2 (r1500)", "A2"),
        _s("s4", "27 à 30", "2:45", "end dont 1h à 1h15 A1", "A1"),
    ]},
    {"phase": "", "sessions": [                                            # S05 (28/09)
        _s("s1", "16", "1:30", "2000 A1+1000 A2+2000 A1", "A3",
           remarque="Formule Excel sur A3 (réf. : 2000 m A1 + 1000 m A3 + 2000 m A1)"),
        _s("s2", "12", "1:10", "end", "Endurance", frequence=ONLY4),
        _s("s3", "12", "1:05", "8000 A1", "A1"),
        _s("s4", "25 à 30", "2:45", "end dont 2 ou 3x30 A1 (selon forme)", "A1"),
    ]},
    {"phase": TAPER, "sessions": [                                         # S6 (05/10)
        _s("s1", allure="A1"),
        _s("s2", allure="A1"),
        _s("s3", frequence=ONLY4),
        _s("s4", "20 à 25", "2:00", "end dont 2x30 A1", "A1"),
    ]},
    {"phase": TAPER, "sessions": [                                         # S7 (12/10) course
        _s("s1", "10", "1:00", "dont 4 km A1", "A1", km_spe=4.0),
        _s("s2", "5", "0:30", "dont 2 km A1", "A1", km_spe=2.0),
        _s(RACE_DAY_LABEL, "42.2", "", "Marathon", "A1", km_spe=42.2,
           remarque="Durée = objectif (calculée automatiquement)"),
    ]},
]

# --------------------------------------------------------------------------- Semi-marathon
SEMI: list[dict] = [
    {"phase": "Développement", "sessions": [
        _s("s1", "10", "1:00", '2x(6x30"/30")', "Sprint"),
        _s("s2", "10", "0:55", "3x2000 A3 r=2'", "A3"),
        _s("s3", "8", "0:50", "end", "Endurance", frequence=ONLY4),
        _s("s4", "15", "1:30", "end dont 2x3000 A1", "A1"),
    ]},
    {"phase": "Développement", "sessions": [
        _s("s1", "11", "1:00", "10x400 A4 r=1'30", "A4"),
        _s("s2", "12", "1:05", "3x3000 A2 r=2'", "A2"),
        _s("s3", "8", "0:50", "end", "Endurance", frequence=ONLY4),
        _s("s4", "16", "1:35", "end dont 2x4000 A1", "A1"),
    ]},
    {"phase": "Spécifique", "sessions": [
        _s("s1", "11", "1:00", "4x1000 A3 r=1'30", "A3"),
        _s("s2", "13", "1:10", "2x5000 A2 r=3'", "A2"),
        _s("s3", "9", "0:55", "end", "Endurance", frequence=ONLY4),
        _s("s4", "18", "1:45", "end dont 3x3000 A2 r=2'", "A2"),
    ]},
    {"phase": "Spécifique", "sessions": [
        _s("s1", "12", "1:05", "6x1000 A3 r=1'30", "A3"),
        _s("s2", "13", "1:10", "3x4000 A2 r=2'", "A2"),
        _s("s3", "10", "1:00", "end", "Endurance", frequence=ONLY4),
        _s("s4", "19", "1:50", "end dont 8000 A2", "A2"),
    ]},
    {"phase": "Spécifique", "sessions": [
        _s("s1", "10", "0:55", '2x(6x30"/30")', "Sprint"),
        _s("s2", "12", "1:05", "2x6000 A2 r=3'", "A2"),
        _s("s3", "8", "0:50", "end", "Endurance", frequence=ONLY4),
        _s("s4", "16", "1:35", "end dont 2x3000 A2", "A2"),
    ]},
    {"phase": TAPER, "sessions": [
        _s("s1", "9", "0:50", "5x1000 A3 r=1'30", "A3"),
        _s("s2", "10", "0:55", "3000 A2 + 2000 A2 r=2'", "A2"),
        _s("s3", "7", "0:45", "end", "Endurance", frequence=ONLY4),
        _s("s4", "12", "1:10", "end dont 4000 A2", "A2"),
    ]},
    {"phase": TAPER, "sessions": [
        _s("s1", "8", "0:45", "end dont 3x1000 A2", "A2", km_spe=3.0),
        _s("s2", "5", "0:30", "end + 4 lignes droites", "Endurance", frequence=ONLY4),
        _s(RACE_DAY_LABEL, "21.1", "", "Semi-marathon", "A2", km_spe=21.1,
           remarque="Durée = objectif (calculée automatiquement)"),
    ]},
]

# --------------------------------------------------------------------------- 10 km
TEN_K: list[dict] = [
    {"phase": "Développement", "sessions": [
        _s("s1", "8", "0:50", '2x(8x30"/30")', "Sprint"),
        _s("s2", "9", "0:50", "5x1000 A3 r=1'30", "A3"),
        _s("s3", "7", "0:45", "end", "Endurance", frequence=ONLY4),
        _s("s4", "12", "1:10", "end dont 2x2000 A1", "A1"),
    ]},
    {"phase": "Développement", "sessions": [
        _s("s1", "9", "0:55", "10x400 A4 r=1'", "A4"),
        _s("s2", "10", "0:55", "3x2000 A3 r=2'", "A3"),
        _s("s3", "7", "0:45", "end", "Endurance", frequence=ONLY4),
        _s("s4", "13", "1:15", "end dont 3000 A2", "A2"),
    ]},
    {"phase": "Spécifique", "sessions": [
        _s("s1", "9", "0:55", '3x(6x30"/30")', "Sprint"),
        _s("s2", "10", "0:55", "6x1000 A3 r=1'", "A3"),
        _s("s3", "8", "0:50", "end", "Endurance", frequence=ONLY4),
        _s("s4", "14", "1:20", "end dont 2x3000 A2", "A2"),
    ]},
    {"phase": "Spécifique", "sessions": [
        _s("s1", "10", "1:00", "12x400 A4 r=1'", "A4"),
        _s("s2", "11", "1:00", "2x3000 A3 r=3'", "A3"),
        _s("s3", "8", "0:50", "end", "Endurance", frequence=ONLY4),
        _s("s4", "15", "1:25", "end dont 4000 A2", "A2"),
    ]},
    {"phase": "Spécifique", "sessions": [
        _s("s1", "9", "0:55", "8x500 A4 r=1'", "A4"),
        _s("s2", "10", "0:55", "5x1000 A3 r=1'", "A3"),
        _s("s3", "7", "0:45", "end", "Endurance", frequence=ONLY4),
        _s("s4", "13", "1:15", "end dont 2x2000 A2", "A2"),
    ]},
    {"phase": TAPER, "sessions": [
        _s("s1", "8", "0:45", '2x(6x30"/30")', "Sprint"),
        _s("s2", "8", "0:45", "3x1000 A3 r=1'30", "A3"),
        _s("s3", "6", "0:40", "end", "Endurance", frequence=ONLY4),
        _s("s4", "10", "1:00", "end", "Endurance"),
    ]},
    {"phase": TAPER, "sessions": [
        _s("s1", "7", "0:40", "end dont 3x500 A3", "A3", km_spe=1.5),
        _s("s2", "5", "0:30", "end + 4 lignes droites", "Endurance", frequence=ONLY4),
        _s(RACE_DAY_LABEL, "10", "", "10 km", "A3", km_spe=10.0,
           remarque="Durée = objectif (calculée automatiquement)"),
    ]},
]

DEFAULT_TEMPLATES: dict[str, list[dict]] = {"marathon": MARATHON, "semi": SEMI, "10k": TEN_K}
