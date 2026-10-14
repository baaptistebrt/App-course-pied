"""
Modèles de référence (6 semaines d'entraînement + semaine de course) pour chaque distance.

* Marathon : transcription du fichier Excel (semaines S1 à S7 ; la S0 vide n'est pas reprise).
  La colonne « tps k » de l'Excel donne le type d'allure : =N5 Endurance, =N6/F4 A1, =N7 A2,
  =N8 A3, =N9 A4, =N10 Sprint.
* 10 km : transcription du fichier « Maud_plan_10k_29_11_26.xlsx » (12 semaines, 3 séances,
  allures en % de VMA). Colonnes : km env. (D), durée (E), contenu (F), allure(s) (G, ex. « A2 A3 »,
  « sprint »), temps spécifique saisi (H, ex. « 27'30 »). Quand la colonne G est vide mais que le
  contenu nomme une allure (S10 à S12), l'allure est reprise du contenu.
* Semi-marathon : proposition construite dans le même esprit, à ajuster par le coach.

Fréquence : chaque séance est marquée « 3-4 » (faite dans tous les cas) ou « 4 » (faite
seulement quand l'élève s'entraîne 4 fois par semaine). Avec 3 séances, on garde la qualité
et la sortie longue, et on retire en priorité le footing d'endurance.
"""

from __future__ import annotations

from .config import FREQ_ALWAYS, FREQ_ONLY_4, RACE_DAY_LABEL

TAPER = "Affûtage : assimilation / récupération / refaire du jus !"


def _s(seance, km_env="", duree_env="", contenu="", allure=None, km_spe=None,
       frequence=FREQ_ALWAYS, remarque="", temps_spe="", jour=""):
    return {"seance": seance, "km_env": km_env, "duree_env": duree_env, "contenu": contenu,
            "km_spe": km_spe, "temps_spe": temps_spe, "allure": allure, "frequence": frequence,
            "remarque": remarque, "jour": jour}


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

# --------------------------------------------------------------------------- 10 km (Excel de référence)
def _t(seance, km, duree, contenu, allure, temps, remarque=""):
    """Séance du plan 10 km : temps spécifique saisi (colonne H de l'Excel)."""
    return _s(seance, km, duree, contenu, allure, temps_spe=temps, remarque=remarque)


TEN_K: list[dict] = [
    {"phase": "", "sessions": [                                            # S1 (13/07), lignes 54-56
        _t("s1", "8", "0:50", '6x30"/30"', "Sprint", "6'"),
        _t("s2", "8", "0:50", "2x1000 (r=500m)", "A2", "12'30"),
        _t("s3", "9", "1:00", "5000", "A1", "32'"),
    ]},
    {"phase": "", "sessions": [                                            # S2 (20/07), lignes 50-52
        _t("s1", "8", "0:50", '8x30"/30"', "Sprint", "8'"),
        _t("s2", "8", "0:50", "2x1500 (r=600m)", "A2", "19'"),
        _t("s3", "", "1:00", "5000", "A1", "32'"),
    ]},
    {"phase": "", "sessions": [                                            # S3 (27/07), lignes 46-48
        _t("s1", "8", "0:50", '10x30"/30"', "Sprint", "10'"),
        _t("s2", "9", "0:55", "3x1000 (le 3è kilo A3)", "A2,A3", "18'"),
        _t("s3", "9.5", "1:00", "5000 dont 1000A2", "A1,A2", "32'"),
    ]},
    {"phase": "", "sessions": [                                            # S4 (03/08), lignes 42-44
        _t("s1", "8", "0:50", '2x(6x30"/30") r=3\'', "Sprint", "16'"),
        _t("s2", "9", "0:55", "3x1000 (le 2è & 3è kilo A3)", "A2,A3", "17'"),
        _t("s3", "9.5", "1:00", "5000 dont 2x1000 A2", "A1,A2", "31'"),
    ]},
    {"phase": "", "sessions": [                                            # S5 (10/08), lignes 38-40
        _t("s1", "8", "0:50", '2x(8x30"/30") r=3\'', "Sprint", "16'"),
        _t("s2", "9", "0:55", "2000 A2 + 2000 A3 (r=1000)", "A2,A3", "30'"),
        _t("s3", "", "1:10", "2x1000 r=4'", "A3", "16'"),
    ]},
    {"phase": "", "sessions": [                                            # S6 (17/08), lignes 34-36
        _t("s1", "8.5", "0:50", '2x(10x30"/30") r=3\'', "Sprint", "20'"),
        _t("s2", "10", "1:00", "2000 A2 + 2000 A3 +1000 A2 r=4'", "A2,A3", "30'"),
        _t("s3", "11", "1:10", "30' progressif 6'15 à 5'45", "A2,A3", "30'"),
    ]},
    {"phase": "", "sessions": [                                            # S7 (24/08), lignes 30-32
        _t("s1", "9", "0:50", "3x3' A3 r=2'", "A3", "9'"),
        _t("s2", "10", "1:00", "2x3000 en 17' (r=4')", "A3", "34'"),
        _t("s3", "11", "1:10", "45' a1 a2 dont 10' A3", "A3", "10'"),
    ]},
    {"phase": "Endurance", "sessions": [                                   # S8 (31/08), lignes 26-28
        _t("s1", "9", "0:50", "3x3' A3 r=2'", "A3", "9'"),
        _t("s2", "10", "", "40' progressives de 6'30 à 5'45\"", "A2,A3", "40'",
           remarque="Si difficile, endurance seulement"),
        _t("s3", "11", "", "5000 A3", "A3", "27'30"),
    ]},
    {"phase": "Endurance", "sessions": [                                   # S9 (07/09), lignes 22-24
        _t("s1", "8", "0:50", "30' A1", "A1", "30'"),
        _t("s2", "8", "0:50", "20' A1 + 10' A2", "A1,A2", "30'"),
        _t("s3", "8", "0:50", "15' A1 + 15' A2", "A1,A2", "30'"),
    ]},
    {"phase": "Endurance", "sessions": [                                   # S10 (14/09), lignes 17-20
        _t("s1", "", "", "5x3'", None, ""),
        _t("s2", "", "", "8x4'", None, ""),
        _t("s3", "", "", "1h dt 20' A3", "A3", ""),
    ]},
    {"phase": TAPER, "sessions": [                                         # S11 (21/09), lignes 13-15
        _t("s1", "", "", "6x3'", None, ""),
        _t("s2", "", "", "A1", "A1", ""),
        _t("s3", "", "", "60' progressives A1 à A3", "A1,A3", ""),
    ]},
    {"phase": TAPER, "sessions": [                                         # S12 (28/09) course, lignes 9-11
        _t("s1", "", "0:45", "A1 + étirements", "A1", ""),
        _t("s2", "", "", "", None, ""),
        _s(RACE_DAY_LABEL, "10", "", "10 km", "A3", km_spe=10.0,
           remarque="Durée = objectif (calculée automatiquement)"),
    ]},
]

DEFAULT_TEMPLATES: dict[str, list[dict]] = {"marathon": MARATHON, "semi": SEMI, "10k": TEN_K}
