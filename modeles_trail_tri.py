"""
Modèles de référence Trail et Triathlon, transcrits des plans fournis par le coach.

* Trail 50 km : « Plan trail des Légendes » (11 semaines). Trois phases (A développement général,
  B travail spécifique, C relâchement), 3 séances obligatoires + 1 optionnelle par semaine. Chaque
  séance a son jour, son étiquette (VMA, Côtes, SL, VTT, Fartlek, M/D, Footing), sa description et
  son statut. La note technique du parcours « triangle » est rattachée aux séances M/D.
  Dans le document, les semaines 11 et 12 portent les mêmes dates (semaine du 7 septembre, course
  le dimanche 13) : elles forment une seule semaine de course, la 11e, comme l'annonce l'introduction.
* Triathlon L (Half Iron Man) : 10 semaines, transcrites des images du document (une discipline par
  jour, durée, description). S6 et S8 se terminent par une course intermédiaire (triathlon sprint,
  puis distance olympique), S10 par le Half Iron Man (JOUR J). Les semaines informelles d'avant le
  plan et les tableaux de chiffres de la fin du document ne sont pas repris.
"""

from __future__ import annotations

from .config import RACE_DAY_LABEL

OBL, OPT = "obligatoire", "optionnel"


def _t(jour: str, tag: str, contenu: str, statut: str = OBL, note: str = "", duree: str = "") -> dict:
    return {"jour": jour, "tag": tag, "contenu": contenu, "statut": statut, "note": note, "duree_env": duree}


TRIANGLE = ("Le parcours en « triangle » :\n"
            "• un côté du triangle correspond à la montée (100 à 150 m) ;\n"
            "• un autre côté correspond à la descente (150 à 200 m) ;\n"
            "• la base du triangle (200 à 250 m) correspond à la distance de récupération. L'idéal est de "
            "trouver une portion à peu près plane pour récupérer.")

PHASE_A = "A - Phase de développement général"
PHASE_B = "B - Phase de travail spécifique"
PHASE_C = "C - Phase de relâchement"

TRAIL_50_INTRO = (
    "Bien respecter les récupérations incluses dans le plan (en particulier les semaines « allégées » 4 et 7).\n\n"
    "Caractéristiques du plan d'entraînement trail long : il s'agit d'un plan de 11 semaines, comprenant :\n"
    "• une période de développement général de 4 semaines (S1-S2-S3-S4) ;\n"
    "• une période de travail spécifique de 5 semaines (S5-S6-S7-S8-S9) ;\n"
    "• une période de relâchement de 2 semaines (S10-S11) ;\n"
    "• 3 séances par semaine + 1 optionnelle.\n\n"
    "Avant le début du plan : à ta guise, sur 3 séances par semaine.")

TRAIL_50: list[dict] = [
    {"phase": PHASE_A, "sessions": [                                                     # S1
        _t("mar", "VMA", "Footing de 25' + 2 x 8 x 30\"-30\" à 105 % VMA avec R = 3' + 10' de récup"),
        _t("mer", "Footing", "Footing de 1h", OPT),
        _t("jeu", "Côtes", "Footing de 45' + 2 x 5 x 1'30 en côtes avec r = descente et R = 3'"),
        _t("dim", "SL", "SL de 1h30 terrain vallonné"),
    ]},
    {"phase": PHASE_A, "sessions": [                                                     # S2
        _t("mar", "VMA", "Footing de 25' + 2 x 8 x 200 m à 105 % VMA avec r = 100 m et R = 3' + 10' de récup"),
        _t("mer", "Footing", "Footing de 1h", OPT),
        _t("jeu", "Côtes", "Footing de 45' + 2 x 6 x 1'30 en côtes avec r = descente et R = 3'"),
        _t("dim", "SL", "SL de 1h45 terrain vallonné"),
    ]},
    {"phase": PHASE_A, "sessions": [                                                     # S3
        _t("lun", "VMA", "Footing de 25' + 2 x 6 x 45\"-45\" à 100 % VMA avec R = 3' + 10' de récup"),
        _t("mer", "Footing", "Footing de 1h", OPT),
        _t("jeu", "Côtes", "Footing de 45' + 2 x 5 x 2' en côtes avec r = descente et R = 3'"),
        _t("dim", "SL", "SL de 2h00 terrain vallonné"),
    ]},
    {"phase": PHASE_A, "sessions": [                                                     # S4 (allégée)
        _t("lun", "Footing", "Footing de 45'"),
        _t("mer", "VTT", "1h30 de VTT sur terrain vallonné"),
        _t("ven", "Footing", "Footing de 45' - 1h", OPT),
        _t("dim", "VTT", "2h00 en VTT sur terrain vallonné"),
    ]},
    {"phase": PHASE_B, "sessions": [                                                     # S5
        _t("lun", "Footing", "Footing de 1h"),
        _t("jeu", "Côtes", "Footing de 45' + 2 x 5 x 2' en côtes avec r = descente et R = 3'"),
        _t("sam", "Footing", "Footing en nature 1h15", OPT),
        _t("dim", "SL", "SL de 2h00 terrain vallonné"),
    ]},
    {"phase": PHASE_B, "sessions": [                                                     # S6
        _t("mar", "VTT", "VTT 1h20 avec 6 x 4' en danseuse (en côte ou gros braquet)"),
        _t("mer", "Footing", "Footing de 1h15"),
        _t("sam", "Footing", "Footing en nature de 1h30", OPT),
        _t("dim", "SL", "SL de 2h30 terrain vallonné"),
    ]},
    {"phase": PHASE_B, "sessions": [                                                     # S7
        _t("mar", "Fartlek", "Fartlek (terrain vallonné) : footing de 25' + 6 x 3' avec R = 1' + 10' cool"),
        _t("mer", "Footing", "Footing nature de 1h"),
        _t("ven", "Footing", "Footing de 45'", OPT),
        _t("dim", "SL", "SL de 3h00 terrain vallonné ou trail de 25 à 30 km"),
    ]},
    {"phase": PHASE_B, "sessions": [                                                     # S8
        _t("lun", "Footing", "Footing en nature de 1h"),
        _t("jeu", "Côtes", "Footing de 45' + 2 x 5 x 1'30\" en côtes avec r = descente et R = 3'"),
        _t("sam", "Footing", "Footing en nature de 1h30", OPT),
        _t("dim", "SL", "SL de 2h30 terrain vallonné ou semi Cancale - Saint-Malo (si semi : 30 min de footing "
                        "avant et 30 min de footing après la course)"),
    ]},
    {"phase": PHASE_B, "sessions": [                                                     # S9
        _t("lun", "Footing", "Footing en nature de 1h15"),
        _t("jeu", "M/D", "M/D (montée/descente) : footing de 20' + 2 x 5 x parcours en « triangle » avec R = 3' "
                         "+ 10' de récup", note=TRIANGLE),
        _t("sam", "Footing", "Footing en nature de 1h30", OPT),
        _t("dim", "SL", "SL de 2h00 terrain vallonné"),
    ]},
    {"phase": PHASE_C, "sessions": [                                                     # S10
        _t("lun", "Fartlek", "Fartlek (terrain vallonné) : footing de 25' + 3' - 4' - 5' - 4' - 3' avec R = 1' "
                             "(et 2' après les 5') + 10' de récup"),
        _t("mer", "Footing", "Footing nature de 1h", OPT),
        _t("jeu", "M/D", "M/D : footing de 20' + 2 x 6 x parcours en « triangle » avec R = 3' + 10' de récup",
           note=TRIANGLE),
        _t("dim", "SL", "SL de 1h30 terrain vallonné"),
    ]},
    {"phase": PHASE_C, "sessions": [                                                     # S11 : semaine de course
        _t("lun", "Footing", "Footing de 50'"),
        _t("jeu", "Footing", "Footing de 40'"),
        {"seance": RACE_DAY_LABEL, "jour": "dim", "contenu": "Compétition", "km_env": "50", "statut": OBL},
    ]},
]

# --------------------------------------------------------------------------- Triathlon L (Half Iron Man)
TRI_L_INTRO = (
    "Plan Half Iron Man (triathlon L) de 10 semaines : 1,9 km de natation, 90 km de vélo et 21,1 km de course "
    "à pied le jour J.\n\n"
    "• Chaque jour a sa discipline : sortie natation, sortie vélo, course à pied, ou enchaînement (vélo puis "
    "course à pied dans la foulée).\n"
    "• Deux courses intermédiaires servent de répétition : un triathlon sprint (S6) et un triathlon distance "
    "olympique (S8). Note ton temps pour chacune.\n"
    "• Allure Half Iron Man en course à pied : en théorie, celle que tu tiens sur un marathon (compte tenu de la "
    "fatigue du vélo).\n"
    "• Chaque semaine, choisis les séances que tu feras réellement (« Choisir mes séances ») : celles que tu "
    "écartes ne comptent pas comme manquées.")


def _d(jour: str, discipline: str, duree: str, *lines: str) -> dict:
    return {"jour": jour, "tag": discipline, "duree_env": duree, "contenu": "\n".join(f"• {x}" for x in lines)}


TRI_L: list[dict] = [
    {"phase": "", "sessions": [                                                          # S1 : 6h30
        _d("lun", "natation", "0h45",
           "2 x 250 m récupération 30 s : 100 m crawl / 25 m dos / 100 m crawl / 25 m brasse.",
           "10 x 100 m récupération 20 s en alternant un 100 m pull buoy et 100 m nage complète (sans pull buoy).",
           "Total 1 500 m."),
        _d("mer", "cap", "1h00",
           "15mn échauffement progressif.",
           "2 x 15mn allure semi marathon, récupération 5mn entre les séries.",
           "Retour au calme 10mn."),
        _d("jeu", "velo", "2h00",
           "Echauffement 20mn.",
           "Corps de séance : 6 blocs de 10mn sur un grand développement et à une cadence de pédalage de l'ordre de "
           "40 à 50 tpm, sans chercher à rouler vite.",
           "Récupération 5mn en vélocité entre les blocs.",
           "Retour au calme 10mn."),
        _d("sam", "natation", "0h45",
           "4 x 500 m : le premier avec pull buoy ; le second en 75 m crawl / 25 m dos ; le troisième avec pull "
           "buoy ; le quatrième en 75 m crawl / 25 m brasse.",
           "Total 2 000 m."),
        _d("dim", "velo", "2h00",
           "2h dont 20mn allure Half Iron Man au centre de chaque heure."),
    ]},
    {"phase": "", "sessions": [                                                          # S2 : 7h15
        _d("lun", "natation", "0h45",
           "4 x 200 m avec pull buoy récupération 30 s.",
           "4 x 100 m avec plaquettes récupération 20 s.",
           "4 x 50 m nage complète souple récupération 15 s.",
           "4 x 25 m nage complète rapide récupération 30 s.",
           "200 m souple en 50 m dos / 50 m crawl.",
           "Total 1 700 m."),
        _d("mer", "cap", "1h00",
           "20mn échauffement progressif.",
           "2 x 10mn en accélération progressive. Par tranche de 2mn : 1 km/h supplémentaire en débutant allure "
           "marathon pour terminer à VMA.",
           "Récupération 5mn entre les séquences. Retour au calme 15mn."),
        _d("jeu", "velo", "2h00",
           "2h sur un parcours vallonné en passant toutes les côtes en alternant position assis et en danseuse, en "
           "force, à une cadence de pédalage de l'ordre de 40 à 50 tpm, sans faire monter les pulsations, sans tirer "
           "sur le cintre, sans se déhancher.",
           "Cadence de pédalage de 90 à 95 tpm sur le plat."),
        _d("sam", "natation", "1h00",
           "(100 m + 200 m + 300 m + 400 m) avec pull buoy.",
           "(100 m + 200 m + 300 m + 400 m) en nage complète.",
           "Récupération de 15 s entre les séquences.",
           "Récupération de 1mn entre les deux séries.",
           "300 m souple en 50 m dos / 50 m crawl.",
           "Total 2 300 m."),
        _d("dim", "velo", "2h30",
           "Sortie longue 2h30, quelques accélérations au gré du dénivelé ou sortie en groupe."),
    ]},
    {"phase": "", "sessions": [                                                          # S3 : 9h15
        _d("lun", "natation", "0h45",
           "3 x (300 m avec pull buoy + 200 m en nage complète et 100 m en insistant sur les battements de jambes).",
           "100 m souple.",
           "Total 1 900 m."),
        _d("mar", "velo", "2h00",
           "Echauffement 15mn.",
           "Corps de séance : 1h30 en alternant 10mn en hyperforce à 40/50 tpm sur un gros développement et 10mn en "
           "hypervélocité à 100/110 tpm sur un petit développement.",
           "Retour au calme 15mn."),
        _d("mer", "cap", "1h00",
           "Echauffement 20mn progressives et gammes de course puis 3 x 60 à 80 m tonique.",
           "4 x 1 000 m à l'allure 5 000 m.",
           "Récupération 2mn trot lent.",
           "Retour au calme 10mn."),
        _d("ven", "natation", "1h00",
           "5 x 500 m récupération 45 s : le premier avec pull buoy ; le second avec pull buoy et plaquettes ; le "
           "troisième avec plaquettes ; le quatrième en nage complète ; le 5e en 50 m dos / 50 m crawl."),
        _d("sam", "velo", "1h30",
           "1h30 souple avec, dans l'heure centrale, une décomposition du mouvement :",
           "5mn en insistant sur la phase de poussée.",
           "5mn en insistant sur la phase de tirage, de remontée de la pédale.",
           "5mn en essayant d'associer les deux phases."),
        _d("dim", "enchainement", "3h00",
           "1h30 de vélo dont la demi-heure centrale allure Half Iron Man et 1h30 de course à pied dans la foulée "
           "dont la demi-heure centrale allure Half Iron Man. En théorie cette allure correspond à l'allure que vous "
           "soutenez lors d'un marathon (compte tenu de la fatigue issue du vélo)."),
    ]},
    {"phase": "", "sessions": [                                                          # S4 : 9h
        _d("lun", "natation", "0h45",
           "200 m avec pull buoy.",
           "200 m éducatif (nager 25 m bras droit en laissant le bras gauche le long du corps puis 25 m bras gauche "
           "en laissant le bras droit le long du corps).",
           "4 x 50 m en recherchant une bonne amplitude.",
           "10 x 100 m récupération 15 s : 5 avec pull buoy et plaquettes ; 5 avec plaquettes.",
           "100 m souple.",
           "Total 1 700 m."),
        _d("mar", "cap", "1h00",
           "1h avec au centre : 1mn vite / 5mn souple / 1mn vite / 4mn souple / 1mn vite / 3mn souple / 1mn vite / "
           "2mn souple / 1mn vite / 1mn souple / 1mn vite / 1mn souple / 1mn vite / 2mn souple / 1mn vite / 3mn "
           "souple / 1mn vite / 4mn souple / 1mn vite / 5mn souple.",
           "Note : 1mn vite = à VMA."),
        _d("mer", "velo", "2h00",
           "Echauffement 15mn.",
           "Corps de séance : 1h30 dont 2 blocs de 25mn à répartir librement, en force (cadence de pédalage 60 tpm "
           "environ) et allure Half Iron Man. Si possible réaliser les blocs en côte ou face au vent.",
           "Retour au calme 15mn."),
        _d("ven", "natation", "1h15",
           "3 x (150 m crawl + 100 m dos + 50 m brasse).",
           "2 séries de 9 x 100 m : 3 avec pull buoy et plaquettes ; 3 avec plaquettes ; 3 nage complète.",
           "100 m souple.",
           "Total 2 800 m."),
        _d("sam", "cap", "1h00",
           "15mn échauffement progressif + gammes de course.",
           "5mn + 7mn + 10mn allure semi marathon. Récup. 5mn entre les séquences. Retour au calme 10mn."),
        _d("dim", "velo", "3h00",
           "Sortie longue, pas de contenus spécifiques, quelques accélérations au gré du dénivelé ou sortie en "
           "groupe."),
    ]},
    {"phase": "", "sessions": [                                                          # S5 : 11h45
        _d("lun", "natation", "1h00",
           "300 m avec pull buoy.",
           "200 m éducatif (nager alternativement avec un seul bras).",
           "100 m en insistant sur les battements de jambes.",
           "3 x 400 m avec pull buoy et plaquettes : 2 en amplitude, le dernier plus rapide, récupération 1mn.",
           "4 x 50 m sprint soutenus récupération 20 s.",
           "200 m souple.",
           "Total 2 200 m."),
        _d("mar", "velo", "2h30",
           "Echauffement 1h30.",
           "2 séries de 6 x (1mn vite / 1mn souple).",
           "Récupération de 5mn entre les deux séries.",
           "Retour au calme 30mn."),
        _d("mer", "cap", "1h00",
           "Echauffement 20mn progressif et gammes de course.",
           "3mn + 4mn + 5mn + 4mn + 3mn allure semi marathon, récupération 1mn entre les séquences.",
           "Retour au calme 10mn."),
        _d("ven", "natation", "1h15",
           "2 séries :",
           "(5 x 100 m avec pull buoy ; 200 m éducatif (nager alternativement avec un seul bras) ; 8 x 50 m nage "
           "complète recherche d'amplitude ; 100 m en insistant sur les battements de jambes ; 8 x 25 m appuyé ; "
           "100 m souple.",
           "Total 3 000 m."),
        _d("sam", "velo", "2h00",
           "Echauffement 20mn.",
           "Corps de séance : répartir 8 blocs de 6mn sur un petit développement et à une cadence de pédalage "
           "supérieure à 105 tpm.",
           "Récupération de 4mn entre les blocs.",
           "Retour au calme 20mn."),
        _d("dim", "enchainement", "4h00",
           "3h de vélo avec au sein de chaque heure 25mn à allure Half Iron Man et 1h de course à pied souple sur "
           "terrain vallonné."),
    ]},
    {"phase": "", "sessions": [                                                          # S6 : 5h30
        _d("lun", "natation", "1h00",
           "400 m avec pull buoy ;",
           "300 m dos/crawl par 50 m ;",
           "4 x 50 m en insistant sur les battements de jambes ;",
           "4 x 25 m appuyé ;",
           "10 x 100 m avec pull buoy (50 m amplitude / 50 m plus rapide sans se désunir) ;",
           "200 m souple recherche d'appui et d'efficacité.",
           "Total 2 200 m."),
        _d("mer", "velo", "2h00",
           "20mn échauffement progressif.",
           "1h30 de corps de séance avec un sprint grand plateau sur 30.",
           "Toutes les 6mn.",
           "Retour au calme 10mn."),
        _d("ven", "cap", "0h45",
           "Séance souple avec 10 x (30 s vite / 30 s souple) en milieu de séance."),
        _d("dim", "course_inter", "1h45",
           "Triathlon sprint, en préparation, total 1h45 environ, échauffement compris."),
    ]},
    {"phase": "", "sessions": [                                                          # S7 : 10h
        _d("lun", "natation", "0h45",
           "2 x (100 m crawl + 50 m brasse ; 100 m crawl et 50 m dos) avec une série avec pull buoy, une série en "
           "nage complète ; 10 x 50 m récupération 15 s en 25 m amplitude / 25 m souple.",
           "10 x 50 m récupération 15 s en 25 m amplitude / 25 m vite.",
           "100 m souple.",
           "Total 1 700 m."),
        _d("mar", "velo", "2h00",
           "2h avec 6 séquences de 10mn en milieu de séance :",
           "(4mn en hyperforce grand plateau 40-50 tpm + 4mn en hypervélocité petit plateau 100-110 tpm + 1mn en "
           "accélération progressive grand plateau + 1mn souple)."),
        _d("mer", "cap", "1h00",
           "1h souple avec 10 x 20 s vite / 20 s souple."),
        _d("ven", "natation", "1h15",
           "2 fois la série : (300 m avec pull buoy ; 2 x 150 m en nage complète récup 15 s ; 3 x 100 m en nage "
           "complète 50 m vite / 50 m souple récup 15 s ; 300 m avec pull et plaquettes ; 3 x 100 m avec plaquettes "
           "récup 15 s).",
           "200 m souple.",
           "Total 3 200 m."),
        _d("sam", "velo", "3h30",
           "Sortie longue, pas de contenus spécifiques, quelques accélérations au gré du dénivelé ou sortie en "
           "groupe."),
        _d("dim", "cap", "1h30",
           "Séance souple avec 20mn allure marathon en milieu de séance."),
    ]},
    {"phase": "", "sessions": [                                                          # S8 : 6h30
        _d("lun", "natation", "1h00",
           "2 fois la série : (200 m avec pull buoy ; 150 m 3 nages dos/brasse/crawl ; 100 m éducatif : garder le "
           "bras tendu tout au long du cycle ; 50 m en insistant sur le battement de jambes ; 8 x 25 m sprint / "
           "25 m brasse souple ; 100 m souple).",
           "Total 2 000 m."),
        _d("mer", "velo", "1h30",
           "Séance souple, en récupération, avec 2 à 3 accélérations progressives grand plateau sur 1mn à répartir "
           "dans la demi-heure centrale."),
        _d("ven", "cap", "0h45",
           "45mn souple avec 2 x 1 000 m allure 10 km, récupération de 5mn en milieu de séance."),
        _d("dim", "course_inter", "3h15",
           "Triathlon distance olympique, en préparation, total 3h15 environ, échauffement compris."),
    ]},
    {"phase": "", "sessions": [                                                          # S9 : 9h45
        _d("lun", "natation", "0h45",
           "1 500 m non stop avec pull buoy en recherchant l'amplitude, très souple."),
        _d("mar", "velo", "2h00",
           "Séance souple, sans intensité, parcours vallonné éventuellement pour faire varier les rythmes, sans "
           "forcer."),
        _d("mer", "cap", "0h45",
           "Footing très souple, en terminant sur 10mn allure marathon."),
        _d("ven", "natation", "1h15",
           "3 x 300 m avec pull buoy ;",
           "3 x 150 m nage complète : lent / moyen / vite par 50 m ;",
           "3 x 300 m avec pull buoy et plaquettes ;",
           "3 x 150 m nage complète en 25 m vite / 25 m souple ;",
           "100 m souple.",
           "Total 2 800 m."),
        _d("sam", "cap", "1h00",
           "20mn échauffement progressif.",
           "2 x 10mn en accélération progressive. Par tranche de 2mn : 1 km/h supplémentaire en débutant allure "
           "marathon pour terminer à VMA.",
           "Récupération 5mn entre les séquences.",
           "Retour au calme 15mn."),
        _d("dim", "velo", "4h00",
           "Sortie longue 4h, pas de contenus spécifiques, quelques accélérations au gré du dénivelé ou sortie en "
           "groupe."),
    ]},
    {"phase": "", "sessions": [                                                          # S10 : 3h + triathlon
        _d("lun", "natation", "0h45",
           "300 m avec pull buoy.",
           "8 x 50 m en 25 m vite / 25 m souple récupération 15 s.",
           "300 m en nage complète.",
           "8 x 25 m sprint récupération 30 s.",
           "300 m souple.",
           "Total 1 500 m."),
        _d("mer", "velo", "1h30",
           "45mn échauffement progressif.",
           "2 séries de (8 x 30 m vite / 30 m souple).",
           "Récup. 3mn entre les deux séries.",
           "30mn de retour au calme."),
        _d("ven", "cap", "0h45",
           "45mn souple avec 8 x 15 s vite / 15 s souple en milieu de séance."),
        {"seance": RACE_DAY_LABEL, "jour": "dim", "contenu": "Votre triathlon Half Iron Man",
         "km_env": "113", "remarque": "1,9 km de natation, 90 km de vélo, 21,1 km de course à pied"},
    ]},
]

TRAIL_TRI_TEMPLATES: dict[str, list[dict]] = {"trail50": TRAIL_50, "triL": TRI_L}
TRAIL_TRI_INTROS: dict[str, str] = {"trail50": TRAIL_50_INTRO, "triL": TRI_L_INTRO}
