# CLAUDE.md : TRSFRT_Prise (Changement Câblage)

Méthode commune : dépôt **`Myst-LB/methode-de-travail`** (`METHODE.md`). Ce fichier ne la recopie pas ; il dit ce
qui est propre à ce projet et l'emporte sur elle pour ces points.

## Le projet

Génère `Projet_Réaménagement_Câblage_<XXXX>.xlsx` depuis les `show running-config` / `show power inline` d'un lot
de switchs. Explications : wiki [`docs/WIKI.md`](docs/WIKI.md) → `docs/wiki.html` (partie 3 = le classeur et les
règles métier, partie 4 = développement). Pas de plan ni de passation séparés : passation dans la partie 6 du wiki.

## Fichiers

| Fichier | Rôle |
| --- | --- |
| `generer_projet_cablage.py` | point d'entrée : projets, feuilles, diff, restauration, écriture |
| `analyse.py` | lecture des `.txt`, prise / local / vocation, règle POE |
| `formules.py` | formules Excel, **disposition des colonnes** (`CAB_ENTETES`, `CHG_ENTETES`) |
| `habillage.py` / `gabarit.py` / `xlsx.py` | styles par nom d'en-tête / lecture de `Template.xlsx` / écrivain XLSX maison |
| `tests/` | `test_poe.py`, `test_generation.py` (données fictives) |
| `.claude/skills/` | copies de `Myst-skills` : `catalyst-center`, `donnees-sensibles`, `tests-fiables` |

## Contraintes (non négociables)

- Python 3, **bibliothèque standard uniquement**, aucun build ; pas d'`openpyxl` (wiki 1, « Contexte et décisions »).
- Le classeur se calcule dans **Excel M365 / Online** seulement (`LET`, `TEXTSPLIT`) ; Excel 2019 LTSC affiche `#NOM?`.
- **Ne pas toucher à la structure des feuilles** (feuilles, ordre, colonnes, en-têtes) sans accord de l'utilisateur.

## Branche et livraison

- Branche : celle que fixe la session ; sinon une branche par sujet, fusion dans `master` (branche par défaut ; pas de `main`).
- Tests : `python -m unittest discover -s tests -v` → compter (27 tests, 27 passés, 0 sauté au 2026-11-16).
- Bilan des tests dans chaque message de commit ; wiki régénéré (`python docs/wiki/gen.py`, zéro « ATTENTION »).

## Compléments des skills

- `donnees-sensibles` : chemins interdits = tout dossier projet (`Génie/`, `<XXXX>/Config/`, `<XXXX>/POE/`), tout
  `*.txt` hors `tests/`, tout `Projet_Réaménagement_Câblage_*.xlsx`. Fixtures : `LAB-0101-9300A`, `LAB-0101-00_P0001`.
  Les mesures du parc citées dans le wiki viennent de l'utilisateur : ne pas les refaire en ouvrant les fichiers.
- `tests-fiables` : harnais `unittest` ; fixtures en CRLF + BOM dans un dossier temporaire accentué ; parité
  `analyse.ABREGES` ↔ `CHG_J` / `CHG_N` (`PariteAbreges`).
- `catalyst-center` : § « Prise depuis la description de port » = la convention de `analyse.RE_PRISE`.

## Pièges propres au projet

Détail et raisons : wiki partie 4.

- `_xlfn.` / `_xlpm.` obligatoires dans `formules.py` ; cellules matricielles `cm="1"` + `xl/metadata.xml`.
- **Aucune lettre de colonne en dur** : tout vient de `CAB` / `CHG`. Une colonne = en-tête + famille dans
  `habillage.py` + largeur **par nom** (`CAB_DEPUIS_GABARIT` / `CAB_LARGEURS_FIXES`, `largeurs_changements()`).
- `construire()` et `feuille_changements()` parcourent les switchs dans le **même ordre** (plages de la formule POE).
- Configs : ne jamais normaliser indentation ni `!` (`CHG_J` fait un `MATCH` exact).
- Table d'abréviations en deux copies (Python / formules) : les modifier ensemble.
- Références de feuille **en dur**, jamais d'`INDIRECT` ; noms d'onglets assainis (31 car., parenthèse retirée).
- Toutes les cellules sont émises, même vides (le quadrillage vient des styles) : `resume()` teste `.valeur`.
- L'équipe **trie et filtre** CÂBLAGE : aucune formule ne doit dépendre de la position d'une ligne (pas de
  référence directe à « la ligne du port »), et pas de protection qui bloquerait le tri.
- Règle POE = consigne de brassage (`NON-POE` / `POE` / `POE+`) : pas d'état « inconnu » (wiki 3, « La colonne POE »).

## Prochaines étapes

(Même liste que la partie 6 du wiki : mettre à jour les deux.)

- [ ] Vérification croisée des références de feuille dans `tests/test_generation.py` (paire piégeuse `…-6984` / `…-6984A` en fictif).
- [ ] Ouvrir un classeur produit dans Excel M365 : colonne POE, aperçu d'impression de CÂBLAGE (échelle 69 %, sauts par local), contrôles de saisie, mises en forme.
- [ ] Décider : protection des cellules à formule (incompatible avec un tri qui touche une cellule verrouillée), nom défini `LAMBDA`, mesure de `ca="1"`.
- [ ] Ajouter le projet à `Hub/projets.json` (dépôt `Myst-LB/Hub`).

<!-- docs-wiki -->
## Documentation (skill docs-wiki)

- **Un seul wiki** : `docs/WIKI.md` (source Markdown, lisible partout) → `docs/wiki.html` (page autonome, recherche
  Ctrl K, thème sombre), régénéré par `python docs/wiki/gen.py`. Ne jamais créer d'autre fichier de doc pour les
  humains (README court qui renvoie au wiki, pas plus).
- **Fichiers de travail des agents** (`CLAUDE.md`, `plan.md`, notes de lot, listes à cocher…) : conservés,
  jamais supprimés ni fondus dans le wiki ; courts, structurés, liés au wiki dans les deux sens. Les lire avant
  le wiki : ils coûtent moins de jetons.
- **Règle permanente** : toute modification du code, des outils, des décisions ou de l'état du projet met à jour
  `docs/WIKI.md` et les fichiers de travail touchés **dans le même commit** (chapitre concerné, extraits, schémas,
  points « à valider », dernière partie « Passation » et « Prochaines étapes »), puis régénère `docs/wiki.html` :
  **zéro « ATTENTION »** attendu.
- Méthode et syntaxe (parties, blocs `extrait` / `valider` / `fichiers` / `bloc`, captures, procédures
  manuelles) : skill **docs-wiki** ; schémas à main levée (`%% étape`, `%% survol`) et pictogrammes
  (`%% icône`, `%% échange`) : skill **schemas-main-levee**. Les deux : dépôt **`Myst-skills`**.
- Les outils de `docs/wiki/` (`gen.py`, `modele.html`, `couleurs.py`, `schemas.*`, `icones.json`) viennent des
  skills : les corriger dans `Myst-skills`, puis `python <Myst-skills>/skills/docs-wiki/scripts/installer_wiki.py .` ;
  réglages du projet dans `docs/wiki/wiki.json`.
<!-- /docs-wiki -->
