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
from .modeles_trail_tri import TRAIL_TRI_INTROS, TRAIL_TRI_TEMPLATES

TAPER = "Affûtage : assimilation / récupération / refaire du jus !"


def _s(seance, km_env="", duree_env="", contenu="", allure=None, km_spe=None,
       frequence=FREQ_ALWAYS, remarque="", temps_spe="", jour="", intensite=""):
    return {"seance": seance, "km_env": km_env, "duree_env": duree_env, "contenu": contenu,
            "km_spe": km_spe, "temps_spe": temps_spe, "allure": allure, "frequence": frequence,
            "remarque": remarque, "jour": jour, "intensite": intensite}


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

# --------------------------------------------------------------------------- 10 km bis (Préparation sur 11 semaines)
CYCLE_PPG = "Cycle de travail - PPG"
CYCLE_VMA = "Cycle de travail en VMA"
CYCLE_SPE = "Cycle de travail spécifique"

TEN_K_BIS: list[dict] = [
    {"phase": CYCLE_PPG, "sessions": [                                     # Sem 1
        _s("s1", "7", "0:55",
           "Footing 40' + 15' de gainage : Pompe (3x 15), abdos (3x15), [chaise, position latéral, et ventral : "
           "maintien de 30\"] à faire 3 fois avec 1' de récupération.",
           "Endurance", intensite="1 - Endurance / Gainage"),
        _s("s2", "6", "0:45",
           "Footing 30' + 15' de PPG : montée de genou, talon fesse, pas chassé, pointe tendue, montée "
           "d'escalier [30 m récup entre] = à faire 3 fois",
           "Endurance", intensite="2 - Endurance / PPG"),
        _s("s3", "7", "0:40", "Footing 40' VMA 60%", "Endurance", intensite="3 - Endurance"),
    ]},
    {"phase": CYCLE_PPG, "sessions": [                                     # Sem 2
        _s("s1", "7", "1:00",
           "Footing 40' + 20' de gainage : Pompe (3x 20), abdos (3x20), [chaise, position latéral, et ventral : "
           "maintien de 45\"] à faire 4 fois avec 1' de récupération.",
           "Endurance", intensite="1 - Endurance / Gainage"),
        _s("s2", "5", "0:50",
           "Footing 20' + 30' de PPG : montée de genou, talon fesse, pas chassé, pointe tendue, montée "
           "d'escalier [30 m récup entre] = à faire 5 fois",
           "Endurance", intensite="2 - Endurance / PPG"),
        _s("s3", "8.5", "0:50", "Footing 50' VMA 60%", "Endurance", intensite="3 - Endurance"),
    ]},
    {"phase": CYCLE_PPG, "sessions": [                                     # Sem 3
        _s("s1", "5.5", "0:55",
           "Footing 30' + 25' de gainage : Pompe (3x 25), abdos (3x25), [chaise, position latéral, et ventral : "
           "maintien de 50\"] à faire 4 fois avec 1' de récupération.",
           "Endurance", intensite="1 - Endurance / Gainage"),
        _s("s2", "7.5", "0:45", "Ech 20' + [10 côtes en 20\" r 1' dans la descente, VMA 105%] R 10'",
           "Sprint", intensite="2 - Endurance / PPG"),
        _s("s3", "10", "1:00", "Footing 1 h 00 VMA 60%", "Endurance", intensite="3 - Endurance"),
    ]},
    {"phase": CYCLE_VMA, "sessions": [                                     # Sem 4
        _s("s1", "8", "0:50", "Ech 20' + [10 côtes en 30\" r 1'30 dans la descente, VMA 105%] R 10'",
           "Sprint", intensite="1 - VMA courte"),
        _s("s2", "8.5", "0:50", "50' VMA 65%", "Endurance", frequence=ONLY4, intensite="2 - Endurance"),
        _s("s3", "10", "1:00", "Ech 20' + 6 x 600 m VMA 95% r1'30 R 15'",
           "A4", km_spe=3.6, intensite="3 - VMA longue"),
        _s("s4", "10", "1:00", "SL de 1h [30' VMA 60% - 30' VMA 65%]", "Endurance", intensite="4 - SL"),
    ]},
    {"phase": CYCLE_VMA, "sessions": [                                     # Sem 5
        _s("s1", "8", "0:45", "Ech 20' + [10 x 200 m à 100% de la VMA, r tps d'effort] R 10'",
           "Sprint", km_spe=2.0, intensite="1 - VMA courte"),
        _s("s2", "10", "1:00", "1 h 00 à 65% VMA", "Endurance", frequence=ONLY4, intensite="2 - Endurance"),
        _s("s3", "9.5", "0:55", "Ech 20' + 4 x 800 m VMA 95% r1'15 R 15'",
           "A4", km_spe=3.2, intensite="3 - VMA longue"),
        _s("s4", "10", "1:00", "SL de 1h 00 [20' VMA 60% - 20' VMA 65% - 10' VMA 70%]",
           "Endurance", intensite="4 - SL"),
    ]},
    {"phase": CYCLE_VMA, "sessions": [                                     # Sem 6
        _s("s1", "8", "0:45", "Ech 20' + [8 x 300 m à 100% de la VMA, r Tps d'effort - 10\"] R 10'",
           "Sprint", km_spe=2.4, intensite="1 - VMA courte"),
        _s("s2", "11", "1:05", "45' à 65% VMA + 20' à 70% VMA",
           "Endurance", frequence=ONLY4, intensite="2 - Endurance"),
        _s("s3", "10.5", "1:00", "Ech 20' + 5 x 1000 VMA 95% r1'30 R 10'",
           "A4", km_spe=5.0, intensite="3 - VMA longue"),
        _s("s4", "13", "1:15", "SL de 1h 15 [30' VMA 65% - 30' VMA 70% - 15' VMA 75%]",
           "Endurance,A1", intensite="4 - SL"),
    ]},
    {"phase": CYCLE_VMA, "sessions": [                                     # Sem 7
        _s("s1", "8.5", "0:50", "Ech 20' + 2 x 8 x 30\"/30\" à 105% VMA R10'",
           "Sprint", temps_spe="16'", intensite="1 - VMA"),
        _s("s2", "10", "1:00", "1 h 00 à 65% VMA", "Endurance", intensite="2 - Endurance"),
        _s("s3", "11.5", "1:10", "SL de 1h 10 VMA 60%", "Endurance", intensite="3 - SL"),
    ]},
    {"phase": CYCLE_SPE, "sessions": [                                     # Sem 8
        _s("s1", "8.5", "0:50", "Ech 20' + [200/300/400/500/400/300/200 r tps d'effort - 10\" VMA 95%] R 10'",
           "A4", km_spe=2.3, intensite="1 - VMA"),
        _s("s2", "7", "0:40", "40' à VMA 65%", "Endurance", frequence=ONLY4, intensite="2 - Endurance"),
        _s("s3", "11.5", "1:05", "Ech 20' + 1500(r1'30) /1000(r1'15)/800(r1')/1000(r1'15)/1500(r1'30) VMA 90% R 10'",
           "A3", km_spe=5.8, intensite="3 - Spécifique"),
        _s("s4", "11.5", "1:05",
           "SL de 1h 05 [20' VMA 60% - 10' VMA 80% - 10' VMA 85% - 25' VMA 65%] ou 5 Km en compétition",
           "Endurance,A2,A3", temps_spe="20'", intensite="4 - SL", remarque="Ou 5 km en compétition"),
    ]},
    {"phase": CYCLE_SPE, "sessions": [                                     # Sem 9
        _s("s1", "9", "0:55", "Ech 20' + [800/600/400/600/800 r tps d'effort - 15\" VMA 95%] R 10'",
           "A4", km_spe=3.2, intensite="1 - VMA"),
        _s("s2", "8", "0:45", "45' à VMA 65%", "Endurance", frequence=ONLY4, intensite="2 - Endurance"),
        _s("s3", "11", "1:00", "Ech 20' + 2000(r2'30\") /1500(r1'30)/2000 VMA 90% R 10'",
           "A3", km_spe=5.5, intensite="3 - Spécifique"),
        _s("s4", "13", "1:15", "SL de 1h 15 [25' VMA 60% - 15' VMA 80% - 10' VMA 85% - 25' VMA 65%]",
           "Endurance,A2,A3", temps_spe="25'", intensite="4 - SL"),
    ]},
    {"phase": CYCLE_SPE, "sessions": [                                     # Sem 10
        _s("s1", "9.5", "0:55", "Ech 20' + [800/1000/800/1000 -r 1'15/1'30/1'15/ VMA 90%] R 10'",
           "A3", km_spe=3.6, intensite="1 - VMA"),
        _s("s2", "8.5", "0:50", "50' à VMA 65%", "Endurance", frequence=ONLY4, intensite="2 - Endurance"),
        _s("s3", "11.5", "1:05", "Ech 20' + 3000(r 3') /2000(r2'30)/1000 VMA 90% R 10'",
           "A3", km_spe=6.0, intensite="3 - Spécifique"),
        _s("s4", "12.5", "1:10", "SL de 1h 10 [20' VMA 60% - 20' VMA 80% - 15' VMA 85% - 15' VMA 65%]",
           "Endurance,A2,A3", temps_spe="35'", intensite="4 - SL"),
    ]},
    {"phase": CYCLE_SPE, "sessions": [                                     # Sem 11 (compétition)
        _s("s1", "9", "0:55", "Ech 20' + 3 x 1000 VMA 85% r1'30 + 2 x 300 à 90% VMA r tps d'effort R 10'",
           "A3", km_spe=3.6, intensite="1 - VMA"),
        _s("s2", "7", "0:45", "40' à 65% VMA + 5 longueurs", "Endurance", intensite="2 - Endurance"),
        _s(RACE_DAY_LABEL, "10", "", "Compétition", "A3", km_spe=10.0, intensite="3 - Compétition",
           remarque="Durée = objectif (calculée automatiquement)"),
    ]},
]

DEFAULT_TEMPLATES: dict[str, list[dict]] = {
    "marathon": MARATHON, "semi": SEMI, "10k": TEN_K, "10k_bis": TEN_K_BIS, **TRAIL_TRI_TEMPLATES,
}
# Note d'introduction des modèles (vide pour la route : le coach peut en écrire une).
DEFAULT_INTROS: dict[str, str] = dict(TRAIL_TRI_INTROS)
