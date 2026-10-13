# Coach running — plans Marathon, Semi-marathon et 10 km

Application Streamlit pour un coach de course à pied :

- **Le coach** (code éditeur) crée un profil par élève : e-mail, code d'accès généré
  automatiquement, objectif, date de course facultative, 3 ou 4 séances par semaine.
  Il ajuste le plan et les formules de chaque élève, les formules globales et les modèles
  de référence des trois distances.
- **L'élève** (code personnel) voit uniquement son plan, avec son dossard et ses allures.
  Il peut choisir 3 ou 4 séances par semaine, exporter en Excel / CSV et imprimer.

---

## 1. Lancer l'application sur ton PC

```
py -V:3.13 -m pip install -r requirements.txt
py -V:3.13 -m streamlit run app.py
```

Les bibliothèques sont les mêmes que pour la première version : le pack hors ligne déjà
installé suffit.

Sans configuration, le **code coach de démonstration** est `coach-2026`. Pour définir le tien,
copie `.streamlit/secrets.toml.example` en `.streamlit/secrets.toml` et remplis `editor_code`.

---

## 2. Mettre à jour l'application en ligne (Streamlit Community Cloud)

### a. Remplacer le code sur GitHub (dépôt `plan-marathon`)
1. Supprime les anciens dossiers `marathon`, `tests` et `data` : ouvre chaque dossier,
   menu **…** en haut à droite, puis **Delete directory** et **Commit changes**.
2. **Add file > Upload files** : glisse `app.py`, `requirements.txt`, `README.md`, et les dossiers
   `core`, `ui` et `tests`. Puis **Commit changes**.
3. Le dossier `.streamlit` (couleurs et polices) ne passe souvent pas par glisser-déposer :
   **Add file > Create new file**, nomme le fichier `.streamlit/config.toml`, colle le contenu
   du fichier `config.toml` fourni, puis **Commit changes**.

**N'envoie jamais le dossier `data`** dans ce dépôt : il contient les e-mails et les codes des élèves.

### b. Créer le dépôt privé des données (une seule fois)
Sur Streamlit Community Cloud, le disque est effacé à chaque redémarrage. L'application copie
donc chaque modification dans un dépôt GitHub **privé** et le recharge au démarrage.

1. Sur GitHub : **+ > New repository**, nom `coach-running-data`, coche **Private** et
   **Add a README file**, puis **Create repository**.
2. Crée une clé d'accès : photo de profil > **Settings** > **Developer settings** >
   **Personal access tokens** > **Fine-grained tokens** > **Generate new token**.
   - Repository access : **Only select repositories** > `coach-running-data`
   - Permissions > Repository permissions > **Contents : Read and write**
   - Copie le jeton (`github_pat_…`) : il ne s'affiche qu'une fois.

### c. Renseigner les Secrets sur Streamlit
share.streamlit.io > ton app > **⋮ > Settings > Secrets** :

```toml
[access]
editor_code = "ton-code-coach"

[github]
token = "github_pat_..."
repo = "baaptistebrt/coach-running-data"
branch = "main"
```

Enregistre : l'application redémarre. La barre latérale du coach indique
« copie GitHub (…) » quand tout fonctionne, ou un message si la copie échoue.

Les anciens secrets `user_code` ne servent plus : chaque élève a désormais son propre code.

---

## 3. Utilisation

### Coach
- **Onglets Marathon / Semi-marathon / 10 km**, chacun avec trois vues :
  - **Élèves** : liste, **Nouvel élève** (e-mail + code créé automatiquement), puis pour l'élève choisi :
    code et lien direct à lui transmettre, objectif, date de course, séances par semaine,
    nombre de semaines restantes (avec **Adapter le plan à N semaines**), plan modifiable,
    formules propres à l'élève, aperçu de ce qu'il voit, exports et impression.
  - **Formules** : ratios globaux de la distance. Ils s'appliquent aux élèves **créés ensuite** ;
    les élèves existants gardent les leurs (bouton « Reprendre les formules globales » au besoin).
  - **Modèle de référence** : plan de départ des nouveaux élèves (6 semaines + semaine de course).
- **Lien direct** : `https://ton-app.streamlit.app/?code=XXXX-XXXX` connecte l'élève sans saisie.
- **Actions** de l'élève : générer un nouveau code (l'ancien ne marche plus), supprimer l'élève.

### Élève
Connexion avec son code (majuscules et tirets indifférents). Il voit son dossard, ses six
allures, son plan semaine par semaine (semaine en cours mise en évidence), choisit 3 ou 4 séances
(les allures ne changent pas) et peut exporter en Excel / CSV ou imprimer.

---

## 4. Calculs

Reprise des formules du fichier Excel. Les ratios s'appliquent à la **vitesse** (km/h) :

| Allure | Calcul (valeurs par défaut) |
|---|---|
| Endurance | A1 × 85 % |
| A1 · marathon | sommet de la chaîne |
| A2 · semi | A1 × 105 % |
| A3 · 10 km | A2 × 105 % |
| A4 · 5 km | A3 × 105 % |
| Sprint | A4 × 120 % |

Allure (min/km) = 60 ÷ vitesse. **L'objectif fixe l'allure de la distance préparée** :
marathon → A1 (42,2 km, comme l'Excel), semi → A2 (21,1 km), 10 km → A3 (10 km).
Les autres allures s'en déduisent dans les deux sens. Pour un marathon avec les ratios par
défaut, les valeurs sont identiques à celles de l'Excel (vérifié par les tests).

- Temps spécifique d'une séance = km spécifiques × allure.
- Séance **JOUR J** : sa durée est l'objectif.
- Dates : la dernière semaine est celle de la course (si une date est renseignée).

### Fréquence 3 ou 4 séances
Chaque séance est marquée **Toujours** ou **Si 4 séances**. Avec 3 séances, les séances
« Si 4 séances » sont masquées. Dans les modèles, c'est le footing d'endurance qui saute
en priorité ; le coach peut changer ce choix séance par séance.

### Modèles fournis
- **Marathon** : semaines S1 à S7 de l'Excel (la S0 vide n'est pas reprise). Ajustements :
  JOUR J à 42,2 km au lieu de 21,11, ligne « s1 » vide en double retirée, S5 s1 sur A3
  comme la formule de l'Excel.
- **Semi-marathon et 10 km** : propositions dans le même esprit (mêmes notations et allures),
  **à relire et ajuster** dans « Modèle de référence ».

---

## 5. Données

```
data/formules.xlsx            ratios globaux par distance
data/modeles/<distance>.xlsx  modèles de référence
data/eleves/<id>.xlsx         un fichier par élève : profil, formules, semaines, séances
```

Écriture atomique (pas de fichier à moitié écrit), rechargement automatique à l'ouverture,
copie GitHub facultative (voir 2b).

---

## 6. Structure du code

```
app.py              point d'entrée : connexion et aiguillage coach / élève
core/               logique métier, sans Streamlit
  config.py         distances, allures, ratios par défaut, couleurs de zones
  calculs.py        conversions de temps, calcul des allures
  modeles.py        modèles de référence des 3 distances
  plan.py           semaines / séances, fréquence, tableaux calculés
  referentiel.py    formules globales et modèles enregistrés
  profils.py        élèves : création, codes, lecture, sauvegarde
  stockage.py       fichiers locaux + copie GitHub
  exports.py        Excel, CSV, document imprimable
  auth.py           codes d'accès
ui/                 interface
  design.py         identité visuelle (piste, dossard, couloirs d'allure)
  composants.py     éditeur de plan, éditeur de formules, exports
  editeur.py        interface coach
  eleve.py          interface élève
tests/              tests (calculs vs Excel, profils, GitHub simulé)
```

Tests : `py -V:3.13 -m pip install pytest`, puis `py -V:3.13 -m pytest -q`.
