# Coach running — plans Marathon, Semi-marathon et 10 km

Application Streamlit pour un coach de course à pied.

- **Page d'accueil publique** : un logo, un titre, un champ « code d'accès ». Rien d'autre n'est
  visible sans code (pas d'accès direct au plan par un lien).
- **Le coach** (code éditeur) crée un profil par élève avec son e-mail : le code d'accès est
  généré et **envoyé automatiquement par e-mail**. Il calcule les allures **par objectif de temps
  ou par VMA** (ou les deux, pour comparer), ajuste le plan, les formules, et **supervise** les
  séances réalisées et le temps de course de chaque élève.
- **L'élève** (son code) voit sa **prochaine séance** et sa progression sur un **tour de piste**,
  coche chaque séance réalisée, note son **ressenti** et un commentaire, saisit son **temps de
  course** et raconte sa course le jour J, choisit 2, 3 ou 4 séances par semaine, exporte et imprime.
- Le coach voit **exactement ce que voit l'élève** (onglet « Vue élève » de sa fiche, en lecture seule).
- Un élève peut avoir **plusieurs programmes** (un par course, avec son **nom de course**), sous le
  même code ; les **courses terminées** sont gardées dans un historique (export Excel).
- **Mon Planning** (élève) : semaine par semaine, les séances en cartes par jour, avec case à cocher,
  ressenti, **intensité** saisie par le coach, allures en couleur et chrono du jour J ; l'élève choisit
  2, 3 ou 4 séances par semaine, ou **pour une semaine donnée** (« Modifier ma semaine »).
- **Analyse de progression** (graphiques Plotly) côté élève et dans la Supervision du coach ;
  **Découverte de parcours** : les parcours existants autour d'une ville, trouvés dans OpenStreetMap.

---

## 1. Mettre à jour l'application en ligne

Ton application est déjà déployée depuis le dépôt GitHub `App-course-pied`.

1. **Code** : dans le dépôt `App-course-pied`, **Add file > Upload files**, glisse tout le contenu
   du dossier (`app.py`, `README.md`, `requirements.txt`, dossiers `core`, `ui`, `tests`), puis
   **Commit changes**. Les fichiers existants sont remplacés ; Streamlit redémarre tout seul.
   Le dossier `ui/assets` (illustration et logo) doit bien partir avec `ui`.
   `requirements.txt` contient Plotly (graphiques de progression) : Streamlit l'installe tout seul
   au redémarrage, qui prend alors une ou deux minutes.
2. **E-mails** (facultatif mais conseillé) : voir la partie 3, puis ajoute la section `[email]`
   dans **share.streamlit.io > ⋮ > Settings > Secrets**, sous les sections existantes.
3. **Données existantes** : elles sont reprises telles quelles. Le modèle 10 km est remplacé
   automatiquement par celui du fichier Excel de référence (l'ancien est gardé en
   `modeles/10k_v2.xlsx` dans le dépôt des données).

## 2. Lancer sur ton PC

```
py -V:3.13 -m pip install -r requirements.txt
py -V:3.13 -m streamlit run app.py
```

Sans Secrets, le code coach de démonstration est `coach-2026`.

## 3. Envoi des codes par e-mail (Gmail)

1. Sur ton compte Google : **Sécurité > Validation en deux étapes**, à activer.
2. Puis https://myaccount.google.com/apppasswords : crée un mot de passe d'application
   (nom : « Coach running »). Google affiche 16 lettres : copie-les.
3. Ajoute dans les Secrets :

```toml
[email]
user = "ton.adresse@gmail.com"
password = "abcd efgh ijkl mnop"
sender_name = "Baptiste, ton coach"
app_url = "https://ton-app.streamlit.app"
```

Le serveur utilisé est `smtp.gmail.com`, port 587. Pour un autre fournisseur, ajoute `host` et
`port`. L'onglet **Réglages** permet d'envoyer un e-mail de test. Sans cette section, les codes
s'affichent dans la fiche de l'élève et tu les transmets toi-même.

---

## 4. Calcul des allures

### Méthode « objectif de temps » (fichier marathon)
Les ratios s'appliquent à la **vitesse** : Endurance = A1 × 85 %, A2 = A1 × 105 %,
A3 = A2 × 105 %, A4 = A3 × 105 %, Sprint = A4 × 120 %. L'objectif fixe l'allure de la distance
préparée : marathon → A1 (42,2 km), semi → A2 (21,1 km), 10 km → A3 (10 km).

### Méthode « VMA » (fichier 10 km)
Vitesse = VMA × % : Endurance 68 %, A1 75 %, A2 80 à 85 %, A3 85 à 90 % (valeurs de l'Excel),
A4 90 à 95 % et Sprint 100 à 105 % (valeurs usuelles, absentes de l'Excel). Chaque allure est une
plage ; comme l'Excel, l'allure de référence est le **bas de la plage** (A2 = VMA × 80 %).
Avec une VMA de 16 : 5'31", 5'00", 4'25"–4'41", 4'10"–4'25" (identique à l'Excel).

### Comparer et choisir
Dans la fiche d'un élève, renseigne l'objectif **et** la VMA : un tableau compare les deux
méthodes allure par allure, puis tu choisis la **méthode retenue** pour son plan. Sans objectif,
le temps de course est estimé à partir de la VMA.

### Formules modifiables
Onglet de la distance > **Formules** : ratios et % de VMA globaux, appliqués aux élèves créés
ensuite. Chaque élève a sa propre copie, modifiable dans sa fiche (« Formules de l'élève »).

---

## 5. Plans

- **Marathon** : semaines S1 à S7 du fichier marathon (temps spécifique calculé : km × allure).
- **10 km** : 12 semaines du fichier « Maud_plan_10k », 3 séances par semaine, allures multiples
  par séance (« A2 A3 »), temps spécifique saisi (« 27'30 »), JOUR J le jour de la course.
  Quand l'Excel ne précise pas l'allure mais que le contenu la nomme (S10 à S12), elle est reprise.
- **Semi-marathon** : proposition dans le même esprit, à ajuster.

Dates : la dernière semaine est celle de la course ; chaque séance peut avoir un **jour**
(lundi… dimanche) qui donne sa date réelle. Fréquence : chaque séance est « Toujours » ou
« Si 4 séances ». Le coach fixe la fréquence par défaut (**2, 3 ou 4 séances**), l'élève peut la
changer. À 3 séances, les séances « Si 4 séances » sont retirées ; à 2 séances, on garde en plus la
première et la dernière séance de chaque semaine (et toujours le jour de course).

---

## 6. Élèves, programmes et historique

- **Nom de la course** (facultatif, ex. « Marathon de Paris 2027 ») : à la création ou dans la fiche.
  Il apparaît dans la liste des élèves, sur le dossard, dans les exports et dans l'e-mail.
- **Plusieurs programmes pour un même élève** : crée un programme avec le même e-mail (dans l'onglet de
  la distance voulue). Il garde son code d'accès ; à la connexion, il arrive sur sa prochaine course et
  passe d'un programme à l'autre en haut de son espace.
- **Courses terminées** : un programme est terminé quand l'élève a saisi son temps, ou après la date de
  la course. Rien n'est effacé : l'historique (chrono, écart à l'objectif, part du plan réalisée, km,
  ressenti, récit) est dans l'onglet **Supervision** (avec export Excel, temps en secondes pour tes
  calculs), dans l'onglet **Suivi** de la fiche, et dans l'onglet **Mes courses** de l'élève.
- **Corriger le prénom ou l'e-mail** : fiche de l'élève, bouton « Modifier le prénom ou l'e-mail ».
  La correction s'applique à tous ses programmes, le code ne change pas ; renvoie-lui ensuite son code.

## 7. Mon Planning, séances par semaine, progression, parcours

- **Intensité** : nouvelle colonne du plan (onglet « Plan de l'élève » et modèles), en texte libre,
  ex. « Facile, en aisance respiratoire ». Elle est reprise telle quelle dans Mon Planning.
- **Mon Planning** (élève) : il réunit l'ancien onglet « Mon plan » et le planning. En haut : nombre de
  séances par semaine (2, 3 ou 4) et « Imprimer ou exporter ». Puis les semaines en onglets soulignés
  (« 5 oct-11 oct », « Cette semaine »…, ✓ quand la semaine est bouclée), l'en-tête de la semaine
  (dates, volume, séances faites, phase, barre de progression) et les séances en cartes groupées par
  jour (« AUJOURD'HUI », « MARDI 13 »…) : icône selon le type (footing, fractionné, seuil, allure,
  progressif, sortie longue, course), **case à cocher**, bouton **Ressenti**, « Intensité : … », km,
  durée, temps à l'allure, remarque et pastilles d'allure en couleur. Séance faite en vert, séance du
  jour mise en avant, jour J en jaune avec « Mon chrono ». « Modifier ma semaine » en bas. Le jour vient
  de la colonne « Jour » du plan ; sans jour, la séance est placée à titre indicatif.
- **Modifier ma semaine** : 2, 3 ou 4 séances pour la semaine affichée uniquement. En réduisant, les
  séances du milieu sont masquées (la première et la dernière restent, le jour de course aussi) ; elles
  réapparaissent intactes, avec leurs cases cochées et ressentis, si l'élève en remet. Le choix est rangé
  dans le fichier de suivi de l'élève ; le plan du coach n'est jamais modifié.
- **Ma progression** (élève) et **Analyse de progression** (Supervision du coach, consolidée par élève) :
  assiduité, séances faites / manquées / à venir par semaine, volume hebdomadaire prévu / couru,
  ressentis, écart à l'objectif et allure moyenne des courses passées. Chaque graphique a sa table.
- **Découverte de parcours** : l'élève saisit sa ville (rayon 5, 10 ou 20 km) et l'appli trouve
  **automatiquement les parcours existants** dans OpenStreetMap, la carte libre (gratuite, sans compte
  ni clé) : parcours de course et parcours sportifs balisés, sentiers balisés (PR…), tours de parcs,
  pistes d'athlétisme. Pour chacun : distance réelle du tracé, boucle ou aller simple, distance au
  centre, lien « Ouvrir la carte » et tracé affiché sur une carte ; filtre par distance. Les très longs
  itinéraires (GR nationaux) sont écartés. Les résultats sont gardés 7 jours en mémoire.
  **Services utilisés** (gratuits, sans clé) : la ville est située par le géocodage de l'**IGN**
  (Géoplateforme), ou par Nominatim pour une ville hors de France ; les parcours viennent d'**Overpass**
  et, en secours, de **Postpass** (Geofabrik) et d'autres serveurs Overpass. Ces serveurs publics sont
  parfois saturés : l'appli passe au suivant, met de côté 5 minutes celui qui vient d'échouer et
  affiche un message clair (avec un « détail technique » à me transmettre si besoin). Chaque échec
  est noté dans les journaux de l'appli (share.streamlit.io > ton app > **Manage app**).
  Les parcours **conseillés par le coach** s'affichent en premier : onglet **Parcours**, depuis la
  recherche (« Ajouter la sélection à ma liste ») ou à la main. Fichier `data/parcours.xlsx`.
  La qualité dépend de ce qui est cartographié dans OpenStreetMap pour chaque ville.

## 8. Espace élève

- **Dossard** (en haut à gauche) : distance sur la bande jaune, objectif, prénom, date de la course et
  jours restants, puis le temps réalisé.
- **Tour de piste** : toute la préparation est un tour de piste ; le tracé jaune avance à chaque
  séance cochée jusqu'à la ligne d'arrivée (au centre : le % du plan réalisé, « Jour J », puis
  « Arrivée »). En dessous : la semaine en cours, les km courus, les séances faites, celles de la semaine.
- **Ta prochaine séance** : contenu, km, durée, allures en grand, bouton « C'est fait ! ». Les séances
  oubliées des semaines passées ne bloquent pas : on passe à la semaine en cours.
- **Ressenti** : après une séance cochée, une carte demande « comment tu l'as sentie ? »
  (5 niveaux, de 😣 Très dur à 😄 Excellent) et un mot pour le coach. Chaque séance du plan a aussi
  son bouton « Ressenti ».
- **Jour J** : carte dédiée avec le temps réalisé, le ressenti et « Raconte ta course ».
- Onglets **Mon Planning** (voir partie 7), **Mes allures**, **Mon carnet** (toutes les séances faites
  avec ressentis et commentaires), **Mes courses** (ses courses terminées), **Ma progression** et
  **Découverte de parcours**. S'il a plusieurs programmes, il choisit le programme en haut de la page.

## 9. Suivi et supervision

- Cases cochées, ressentis, commentaires et temps de course sont rangés dans
  `data/suivi/<id>.xlsx`, un fichier que **seul l'élève modifie** : le coach ne peut ni les
  changer ni les effacer en modifiant le plan.
- Fiche de l'élève, onglet **Suivi** : chiffres clés, puis **Réglages de l'élève** (séances par
  semaine qu'il a choisies, semaines qu'il a modifiées, date de sa dernière action), puis quatre
  onglets : **Semaine par semaine** (même présentation que son planning, avec pour chaque séance
  « ✓ Faite le 13/10 », « Non cochée » ou « À venir », son ressenti et son commentaire),
  **Carnet**, **Graphiques** (assiduité, volume, ressentis) et **Courses terminées**.
  Onglet **Vue élève** : son espace exactement comme il le voit, en lecture seule.
- Dans la fiche, si l'élève a choisi un autre nombre de séances que ton réglage, c'est indiqué sous
  « Séances par semaine (défaut) » : c'est son choix qui s'affiche chez lui.
- Onglet **Supervision** : tous les programmes en cours (progression, séances par semaine vues par
  l'élève et semaines modifiées, dernière séance), l'historique des courses, l'analyse de progression
  et les derniers ressentis.
- Les exports Excel / CSV / impression de l'élève contiennent ses ressentis et commentaires.

## 10. Visuels

Par défaut, une illustration de virage de piste d'athlétisme. Onglet **Réglages** : importe tes
photos pour la page d'accueil et pour les bandeaux (redimensionnées automatiquement, copiées sur
GitHub avec les données).

---

## 11. Données

```
data/formules.xlsx            ratios et % VMA globaux par distance
data/modeles/<distance>.xlsx  modèles de référence
data/eleves/<id>.xlsx         un programme : élève, nom de course, méthode, formules, plan (coach)
data/suivi/<id>.xlsx          séances réalisées, ressentis, commentaires, temps de course, fréquence (élève)
data/medias/                  photos de l'accueil et des bandeaux
data/parcours.xlsx            parcours proposés aux élèves (onglet Parcours)
```

## 12. Structure du code

```
app.py                page d'accueil publique et aiguillage coach / élève
core/                 logique métier, sans Streamlit
  calculs.py          conversions, allures par objectif et par VMA
  moteur.py           calcul double d'un élève, comparaison, méthode retenue
  plan.py             semaines / séances (jour, allures multiples), tableaux calculés
  modeles.py          modèles des 3 distances (dont le 10 km de l'Excel)
  referentiel.py      formules globales, modèles enregistrés, mises à jour
  profils.py          élèves et programmes, codes d'accès, correction de l'e-mail
  suivi.py            séances réalisées, ressentis, prochaine séance, carnet (côté élève)
  historique.py       état d'un programme, courses terminées, export de l'historique
  analyse.py          chiffres de progression (semaines, ressentis, courses)
  parcours.py         parcours conseillés par le coach
  decouverte.py       parcours existants (OpenStreetMap) : géocodage IGN / Nominatim, Overpass / Postpass
  emails.py           envoi du code par e-mail (SMTP)
  stockage.py         fichiers locaux + copie GitHub
  exports.py          Excel, CSV, document imprimable
  auth.py             codes d'accès
ui/                   interface
  design.py           identité visuelle, accueil, tour de piste, couloirs, semaines, carnet
  composants.py       éditeur de plan, éditeurs de formules, exports
  editeur.py          interface coach (distances, réglages)
  supervision.py      supervision et onglet Suivi de la fiche (lecture seule)
  planning.py         « Mon Planning » (élève), « Modifier ma semaine », suivi semaine par semaine (coach)
  progression.py      graphiques de progression (Plotly)
  parcours.py         découverte de parcours (élève) et onglet Parcours (coach)
  eleve.py            espace élève (aussi affiché au coach, en lecture seule)
  assets/             illustration de piste et logo
tests/                tests automatiques (calculs vs les deux Excel, suivi, e-mails, GitHub simulé,
                      services de cartes simulés : tests/fake_osm.py)
```

Tests : `py -V:3.13 -m pip install pytest aiosmtpd`, puis `py -V:3.13 -m pytest -q`.
