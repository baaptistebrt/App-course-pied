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
  course** et raconte sa course le jour J, choisit 3 ou 4 séances par semaine, exporte et imprime.
- Le coach voit **exactement ce que voit l'élève** (onglet « Vue élève » de sa fiche, en lecture seule).

---

## 1. Mettre à jour l'application en ligne

Ton application est déjà déployée depuis le dépôt GitHub `App-course-pied`.

1. **Code** : dans le dépôt `App-course-pied`, **Add file > Upload files**, glisse tout le contenu
   du dossier (`app.py`, `README.md`, `requirements.txt`, dossiers `core`, `ui`, `tests`), puis
   **Commit changes**. Les fichiers existants sont remplacés ; Streamlit redémarre tout seul.
   Le dossier `ui/assets` (illustration et logo) doit bien partir avec `ui`.
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
« Si 4 séances ». Le coach fixe la fréquence par défaut, l'élève peut la changer.

---

## 6. Espace élève

- **Tour de piste** : toute la préparation est un tour de piste ; le tracé jaune avance à chaque
  séance cochée jusqu'à la ligne d'arrivée. Au centre, le compte à rebours (J-46), puis « Jour J »,
  puis le chrono réalisé. À côté : la semaine en cours, l'objectif, les km courus, les séances faites.
- **Ta prochaine séance** : contenu, km, durée, allures en grand, bouton « C'est fait ! ». Les séances
  oubliées des semaines passées ne bloquent pas : on passe à la semaine en cours.
- **Ressenti** : après une séance cochée, une carte demande « comment tu l'as sentie ? »
  (5 niveaux, de 😣 Très dur à 😄 Excellent) et un mot pour le coach. Chaque séance du plan a aussi
  son bouton « Ressenti ».
- **Jour J** : carte dédiée avec le temps réalisé, le ressenti et « Raconte ta course ».
- Onglets **Mon plan** (semaine en cours ouverte, autres semaines repliées), **Mes allures**,
  **Mon carnet** (toutes les séances faites avec ressentis et commentaires).

## 7. Suivi et supervision

- Cases cochées, ressentis, commentaires et temps de course sont rangés dans
  `data/suivi/<id>.xlsx`, un fichier que **seul l'élève modifie** : le coach ne peut ni les
  changer ni les effacer en modifiant le plan.
- Fiche de l'élève, onglet **Suivi** : chiffres clés, carnet de l'élève, semaines avec ✅ et ressentis.
  Onglet **Vue élève** : son espace exactement comme il le voit, en lecture seule.
- Onglet **Supervision** : tous les élèves (progression, dernière séance, temps réalisé, écart à
  l'objectif, dernier ressenti).
- Les exports Excel / CSV / impression de l'élève contiennent ses ressentis et commentaires.

## 8. Visuels

Par défaut, une illustration de virage de piste d'athlétisme. Onglet **Réglages** : importe tes
photos pour la page d'accueil et pour les bandeaux (redimensionnées automatiquement, copiées sur
GitHub avec les données).

---

## 9. Données

```
data/formules.xlsx            ratios et % VMA globaux par distance
data/modeles/<distance>.xlsx  modèles de référence
data/eleves/<id>.xlsx         profil, méthode, formules et plan de l'élève (écrit par le coach)
data/suivi/<id>.xlsx          séances réalisées, ressentis, commentaires, temps de course, fréquence (élève)
data/medias/                  photos de l'accueil et des bandeaux
```

## 10. Structure du code

```
app.py                page d'accueil publique et aiguillage coach / élève
core/                 logique métier, sans Streamlit
  calculs.py          conversions, allures par objectif et par VMA
  moteur.py           calcul double d'un élève, comparaison, méthode retenue
  plan.py             semaines / séances (jour, allures multiples), tableaux calculés
  modeles.py          modèles des 3 distances (dont le 10 km de l'Excel)
  referentiel.py      formules globales, modèles enregistrés, mises à jour
  profils.py          élèves, codes d'accès
  suivi.py            séances réalisées, ressentis, prochaine séance, carnet (côté élève)
  emails.py           envoi du code par e-mail (SMTP)
  stockage.py         fichiers locaux + copie GitHub
  exports.py          Excel, CSV, document imprimable
  auth.py             codes d'accès
ui/                   interface
  design.py           identité visuelle, accueil, tour de piste, couloirs, semaines, carnet
  composants.py       éditeur de plan, éditeurs de formules, exports
  editeur.py          interface coach (distances, réglages)
  supervision.py      supervision (lecture seule)
  eleve.py            espace élève (aussi affiché au coach, en lecture seule)
  assets/             illustration de piste et logo
tests/                tests automatiques (calculs vs les deux Excel, suivi, e-mails, GitHub simulé)
```

Tests : `py -V:3.13 -m pip install pytest aiosmtpd`, puis `py -V:3.13 -m pytest -q`.
