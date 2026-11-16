# CLAUDE.md : TRSFRT_Prise (Changement Câblage)

Méthode commune : dépôt **`Myst-LB/methode-de-travail`** (`METHODE.md`). Ce fichier ne la recopie pas ; il dit ce
qui est propre à ce projet et l'emporte sur elle pour ces points.

## Le projet

Génère `Projet_Réaménagement_Câblage_<XXXX>.xlsx` à partir des sorties brutes d'un lot de switchs
(`show running-config`, `show power inline`). Pour deux publics : l'**entrepreneur** qui brasse (feuilles
`CÂBLAGE` / `IMPRESSION`, imprimées) et le **tech** qui transfère les configs (`Changements All Switch`,
`Config à copier`, à l'écran). Pas encore de wiki ni de plan : voir « Prochaines étapes ».

```
python generer_projet_cablage.py                      # diff de tous les projets (n'écrit rien)
python generer_projet_cablage.py Genie                # diff du seul projet Genie
python generer_projet_cablage.py Genie --force        # écrit (sauvegarde .bak horodatée, saisies restaurées)
python generer_projet_cablage.py Genie --descriptions # diagnostic des descriptions lues
python generer_projet_cablage.py Genie --gabarit X.xlsx           # autre gabarit de présentation
python generer_projet_cablage.py Genie --force --sans-sauts-page  # CÂBLAGE imprimée d'un seul tenant
# aussi : --racine DOSSIER (défaut : dossier du script), --sortie FICHIER.xlsx, --reserve N (lignes vides, défaut 50)
```

## Fichiers

| Fichier | Rôle |
| --- | --- |
| `generer_projet_cablage.py` | Point d'entrée : localisation des projets, construction des feuilles, diff, restauration, écriture |
| `analyse.py` | Lecture des `.txt` : blocs `interface`, prise / local / vocation depuis la description, `show power inline`, règle POE |
| `formules.py` | Formules Excel (LET / LAMBDA / MAP / XLOOKUP) et **disposition des colonnes** (`CAB_ENTETES`, `CHG_ENTETES`) |
| `habillage.py` | Styles de cellule « Avant / Après », déclarés par nom d'en-tête |
| `gabarit.py` | Lecture de `Template.xlsx` : styles.xml, thème, largeurs, mise en page |
| `xlsx.py` | Écrivain / lecteur XLSX maison |
| `Template.xlsx` | Gabarit de présentation, **obligatoire** |
| `tests/` | Suite `unittest`, données fictives |
| `.claude/skills/` | Copies de `Myst-skills` : `catalyst-center`, `donnees-sensibles`, `tests-fiables` |

## Contraintes (non négociables)

- Python 3, **bibliothèque standard uniquement**, aucun build. `openpyxl` n'est pas installé et ne doit pas le
  devenir : voir « Pourquoi un écrivain XLSX maison ».
- Les configs et sorties PoE réelles (`*.txt`, dossiers projet comme `Génie/`) et les classeurs produits (`*.xlsx`
  sauf le gabarit) **ne sont jamais commités** (`.gitignore`) **ni ouverts par un agent**.

## Branche et livraison

- Branche de travail : celle que fixe la session ; sinon une branche par sujet, fusion dans `main`.
- Tests : `python -m unittest discover -s tests -v` (compter : X tests, X passés, 0 sauté).
- Bilan des tests dans chaque message de commit.

## Compléments des skills

- `donnees-sensibles` : chemins interdits = tout dossier projet (`Génie/`, `<XXXX>/Config/`, `<XXXX>/POE/`), tout
  `*.txt` hors `tests/`, tout `Projet_Réaménagement_Câblage_*.xlsx`. Les mesures du parc citées plus bas viennent de
  l'utilisateur ; ne pas les refaire en ouvrant les fichiers. Fixtures : noms `LAB-0101-9300A`, locaux `LAB-0101-00`.
- `tests-fiables` : harnais = `unittest` ; fixtures écrites dans un dossier temporaire **accentué**, en CRLF avec
  BOM ; test de parité `analyse.ABREGES` ↔ tables `XLOOKUP` de `CHG_J` / `CHG_N`.
- `catalyst-center` : § « Prise depuis la description de port » = la même convention que `analyse.RE_PRISE`.

## Arborescence attendue

```
Changement Cablage/
├── Genie/                                  <- le nom du dossier donne le « XXXX »
│   ├── Config/  Z7-0002-9200A.txt          « show running-config » par switch
│   └── POE/     Z7-0002-9200A.txt          « show power inline » par switch
└── Projet_Réaménagement_Câblage_Genie.xlsx <- produit ici
```

Tout sous-dossier de la racine est examiné (sauf ceux qui commencent par `.` `_` `~` `$`, et `Config` / `POE`
eux-mêmes). Les configs sont lues dans `Config/` s'il existe, sinon à la racine du dossier projet. `POE/` est
optionnel : sans lui la colonne POE ressort `NON-POE`. Le nom du `.txt` (sans extension) est le nom du switch.

## Feuilles produites (dans cet ordre)

| Feuille | Contenu |
| --- | --- |
| `CÂBLAGE <XXXX>` | une ligne par interface décrite, groupée par local technique, + section « hors gabarit » en fin |
| `IMPRESSION` | `CÂBLAGE` ligne pour ligne, filtrée sur `État` = `À faire` (formules seulement) |
| `Changements All Switch` | **l'unique** feuille Changements : une ligne par port, tous switchs à la suite |
| `Config à copier` | une section par switch (`configure terminal` … `end`), lignes `À prog` et `À désactiver` |
| `<switch>` | la config brute, une ligne du `.txt` par cellule de la colonne A (une feuille par switch) |

`IMPRESSION` et `Config à copier` ne contiennent que des formules : ni diff, ni restauration (`SANS_DIFF`).

La formule POE de `CÂBLAGE` ne cherche que dans les lignes de **son** switch : `construire()` calcule pour chacun
`(feuille, première, dernière)` (`chg_de_switch`) dans le même ordre que `feuille_changements()` les écrit. Changer
l'un sans l'autre fait viser les lignes d'un autre switch. Le nom `Changements All Switch` est réservé avant ceux
des switchs (un switch homonyme reçoit `~2`). Jamais de regroupement des configs par « zone » : déduire une zone du
nom de switch ne survit pas aux noms réels du parc.

`Config à copier` : une seule formule `REDUCE` de longueur fixe. L'ancienne version répétait un bloc par switch et
dépassait la limite Excel de 8 192 caractères vers 15 switchs (formule supprimée à l'ouverture). Une ligne de config
par cellule : copier une cellule multi-ligne ajoute des guillemets dans le CLI.

### Colonnes de `CÂBLAGE`

Seule source de vérité : `formules.CAB_ENTETES`. Lignes 1 = en-têtes, 2 = vide, données dès la 3.

| Colonne | Sens | Rempli par |
| --- | --- | --- |
| `Local Switch` | local technique = deux premiers segments du nom de switch (`Z7-0002`) | générateur |
| `Anc. Switch` | nom **complet** de l'ancienne switch, parenthèse comprise | générateur |
| `Interface` | interface abrégée (`Gi1/0/6`) | générateur |
| `Description` | description brute du port | générateur |
| `Anc. Prise` | code après le `P` de la description (`643`, `6B`) | générateur |
| `Anc. Locale` | le local **de la prise** | générateur, depuis la description |
| `Nouv. Prise` / `Nouv. Switch` / `Nouv. Interface` | planification | à la main |
| `POE` | `NON-POE` / `POE` / `POE+` | formule (remonte `Changements`) |
| `Nouv. Locale` | planification | à la main |
| `VOCATION` | usage de la prise | pré-rempli avec le texte entre parenthèses de la description (`AP`, `imprimante`), modifiable |
| `État` | avancement seulement | liste : `Fait`, `À faire`, `À prog`, `À désactiver`, `À vérifier`, `Non-fait`, `Ne pas faire` ; défaut `Non-fait` |
| `Commentaire` | `DOUBLON <switch> <int>`, `HORS GABARIT`, sinon libre | générateur / à la main |

`Anc. Switch` porte une **switch**, `Anc. Locale` un **local** : deux choses différentes. Une version antérieure
mettait le local de la prise à la place du switch, ce qui cassait la lecture de toute la feuille.
Tout ce que le script signale (`DOUBLON`, `HORS GABARIT`) va en `Commentaire`, jamais en `État`.

### Colonnes de `Changements All Switch`

Seule source de vérité : `formules.CHG_ENTETES` (14 colonnes) :
`Switch | Interface | Admin | Anc. Prise | POE | Device | Config | Nouv. Interface | Local | Nouv. Prise |
Description override | New Config | État | Commentaire`.

- `Config` : bloc de l'interface pris dans la feuille du switch (formule `CHG_J`).
- `Nouv. Interface`, `Local`, `Nouv. Prise`, `État`, `Commentaire` : relus dans `CÂBLAGE` par `XLOOKUP` sur le
  **port** (`Anc. Switch` + `Interface`), hors gabarit compris. C'est dans `CÂBLAGE` qu'on saisit.
- `Description override` : saisie libre ; remplie, elle **remplace** le texte de la ligne `description`.
- `New Config` (`CHG_N`) : renomme l'interface, reconstruit `description <Local>_P<NNNN>` (toujours 4 caractères
  après le `P` : `P0643`, `P006B`). `État` = `À désactiver` → `default interface <X>`.
- `Power`, `Class` et `Max` ont été retirés. **Aucune colonne masquée** : le gabarit masquait `Admin` et `Device`,
  or `Device` doit se lire (`masquees=set()` passé à `cols_depuis()`).
- Largeurs ajustées au contenu réel (`largeurs_changements`). `Config` / `New Config` plafonnées à 48 caractères.
- Hauteur de ligne **calculée** (`hauteur_bloc()`, 12 pt par ligne, plafond 409) : Excel ne l'ajuste pas à
  l'ouverture, un bloc de 15 lignes resterait écrasé sur une seule.

### Numéro de prise dans la description

Toutes ces notations, relevées sur le parc, suivies ou non d'une annotation libre :

```
D1-3001_P0560    D1-3001 P560    D1-3001-P560    D1-3001(P560)    D1-3001 (P560)
z1-2116-03_P0123 (xxxx)      C1-5015-00_P0197 (max 4)      C2-2065-00_P0338 trap enable
```

Garde-fous (`analyse.RE_PRISE`, `RE_PRISE_ALPHA`) :

1. **Séparateur obligatoire** avant le `P` (espace, `_`, `-`, `(`). Sans lui, `AIR-AP2802I-A-K9` donnerait le local
   `AIR-A` et la prise 2802.
2. **Chiffre juste après le `P`** pour un code numérique : `PDU20A`, `PA20`, `PoE12`, `Panneau3` sont exclus.
3. Le code collé au `P` est gardé entier : `P06B` → `6B`, `P12AB` → `12AB` ; zéros de tête retirés ; un code
   purement numérique reste un nombre. Les annotations séparées par une espace (`2ieme`, `trap enable`) sont ignorées.
4. Code alphabétique (`_PABCD`) accepté seulement derrière `_`, `-` ou `(`, pour qu'un mot du texte libre (`Poste`)
   ne passe pas.

Le motif est **cherché**, pas ancré en fin de chaîne : ancré, toute annotation expédiait le port en hors gabarit.

### Section « hors gabarit »

Ports décrits dont la description ne livre **aucun** numéro (uplinks, inter-switch, trunks, tunnels). Listés en fin
de `CÂBLAGE` sous `— HORS GABARIT —` : `Anc. Switch`, `Interface`, `Description` remplis, `Anc. Prise` vide,
`État` = `Non-fait`, `Commentaire` = `HORS GABARIT`. La recherche se faisant par port, `Changements` les relie comme
les autres. Côté diff, `_cle_cablage()` indexe une ligne normale sur sa **prise** seule et une ligne hors gabarit sur
**(switch, interface)**.

### Prises revendiquées par deux ports

Une description restée en place sur un port re-brassé. **Les deux lignes sont conservées** et le `Commentaire` de
chacune **nomme l'autre port** (`DOUBLON Z7-1920-2962B Gi1/0/1`). Écarter la seconde faisait disparaître un port réel.

- AP et prises ordinaires ont des **numérotations distinctes** : AP 12 n'est pas un doublon de la prise 12.
- Une prise `P0000` (jamais remplie) n'est le doublon de personne.
- Le diff numérote les lignes identiques (`_cle_libre()`) pour que la disparition de l'une se voie.

### Habillage « Avant / Après » (`habillage.py`)

- **Bleu = existant**, **vert = nouveau**, gris pour `POE` / `État` / `Commentaire` ; double trait devant la
  première colonne « nouveau ».
- `CÂBLAGE` : lignes de 26 pt (annotation au crayon), numéros de prise en gras 13 pt, ligne 1 répétée à
  l'impression ; groupes par local technique avec bandeau et saut de page (retiré par `--sans-sauts-page`) ; Lettre
  US portrait, échelle 69 % (`MISE_EN_PAGE_CAB`). `IMPRESSION` : Lettre US paysage, une page de large.
- Mise en forme conditionnelle : case de planification vide sur une ligne de port → jaune ; `Fait` vert gras,
  `Ne pas faire` gris italique ; `DOUBLON…` / `HORS GABARIT` en rouge.
- Familles déclarées **par nom d'en-tête** : une colonne ajoutée sans y être déclarée fait échouer l'import.
  Styles **ajoutés en fin** du `styles.xml` du gabarit : aucun index existant ne bouge.
- Le quadrillage vient des **bordures des styles de cellule** : toutes les cellules sont émises, même vides
  (`xlsx.vide(style)`). Conséquence : `resume()` teste `ligne[1].valeur is not None`, pas `ligne[1] is not None`.

## Deux règles métier déduites, pas inventées

- **Colonne `POE`** : consigne de brassage, pas propriété de la prise (« faut-il du PoE ici ? »).
  - `NON-POE` si `Power` = 0 (ou pas de donnée), même sur un port capable de 30 W.
  - `POE+` si l'équipement consomme ou peut consommer en pointe plus que le PoE classique : `Power` > 15,4 W, **ou**
    classe 4 à 8, **ou** marqueur `(AP)` dans la description, **ou** modèle reconnu dans `Device` (AP Cisco /
    Meraki, `AP`, PTZ ; `RE_DEVICE_POE_PLUS`). L'ancien libellé `POE (AP)` n'existe plus.
  - `POE` sinon.
  - Ne pas en faire un état « inconnu » : « rien de branché » vs « équipement non-PoE » n'intéresse pas le
    technicien qui brasse. La colonne de `Changements` n'est **jamais vide** (un `INDEX` sur une cellule vide rend
    `0`) ; la formule de `CÂBLAGE` porte en plus un `IF(…=0,"",…)`.
  - Mesure fournie par l'utilisateur sur le classeur d'origine (avant POE+) : `Z7-0002` suit la règle `Power > 0`
    sur ses 384 lignes ; `Z7-1920` ne la suit pas (colonne remplie à la main avec le besoin *futur*) et ne fait pas foi.
- **Descriptions dégradées** : forme normale du local `C#-####-##` (2 325 occurrences sur ~2 400) ; le `-00` final
  est normal. Seul le **2e segment** est contrôlé : absent, à zéro, non numérique, ou segment vide. Signalées, jamais
  corrigées (la donnée fausse est sur l'équipement). `--descriptions` liste tout ce que le script lit.
- **PoE absent ≠ fichier illisible** : les 2960/2961/2962 rendent l'en-tête sans lignes ; seul un fichier *sans
  en-tête* déclenche un avertissement (`lire_poe()` renvoie `entete_vue`).
- **Nom de fichier vs `hostname`** : le nom du `.txt` fait foi ; un `hostname` différent est une erreur de collecte,
  signalée.

## Diff, `--force` et restauration

- Sans `--force`, rien n'est écrit : comparaison de ce qui vient des `.txt` seulement (PoE, configs, prises, locaux).
- Avec `--force` : copie `.<horodatage>.bak`, puis **réinjection des saisies** de l'ancien classeur par la clé
  stable (`Anc. Switch`, `Interface`) : `Nouv. Prise`, `Nouv. Switch`, `Nouv. Interface`, `Nouv. Locale`,
  `VOCATION`, `État`, `Commentaire` (sauf les marques `DOUBLON` / `HORS GABARIT`, recalculées) ; dans `Changements`,
  `Description override` par (`Switch`, `Interface`).
- **Fichier verrouillé par Excel** : détecté avant toute écriture (pas de `.bak` orphelin) ; écriture via `.tmp` +
  `os.replace`, jamais de `.xlsx` tronqué.

## Pièges propres au projet (ce à quoi il ne faut pas toucher)

- **`formules.py`** : les préfixes `_xlfn.` et `_xlpm.` sont la façon dont Excel *stocke* ces formules ; les retirer
  corrompt le classeur.
- **Aucune lettre de colonne en dur** dans une formule : tout vient de `CAB` / `CHG`, construits depuis
  `CAB_ENTETES` / `CHG_ENTETES`. Les colonnes ont bougé plusieurs fois ; une lettre oubliée donnait un classeur qui
  s'ouvre sans erreur et affiche des valeurs fausses. Déplacer une colonne = éditer la liste d'en-têtes, la
  déclarer dans `habillage.py`, revoir `CAB_COLONNES` / `CHG_COLONNES` (largeurs du gabarit).
- **Lignes `!` et indentation des configs** : `CHG_J` fait un `MATCH("interface " & …)` exact puis cherche le `!`.
  `lire_config()` ne normalise que les fins de ligne.
- **Table d'abréviations** (`Gi` → `GigabitEthernet`…) en deux copies : `analyse.ABREGES` et les `XLOOKUP` de
  `CHG_J` / `CHG_N`. Verrouillée par `tests/test_poe.py::PariteAbreges`.
- **Cellules matricielles** : `cm="1"` + `<f t="array" aca="1" ref=… ca="1">` avec `xl/metadata.xml`. Sans ce
  marquage, Excel les dégrade en matricielles héritées (CSE), où `SINGLE`, `MAP` et `TEXTSPLIT` changent de sens.
- **Formules en plage concaténée** (`A&"|"&B`) : écrites en ARRAY, sinon Excel applique l'intersection implicite et
  la recherche rend `""`.
- **Noms d'onglets** : 31 caractères max, `[ ] : * ? / \ '` retirés, parenthèse finale du nom de switch retirée
  (`C1-3000-6984A (Julie)` → `C1-3000-6984A`), collisions en `~2`. Sans danger parce que les formules
  référencent les feuilles **en dur**, jamais via `INDIRECT`.

### Le seul écart assumé avec les formules d'origine

`CAB_F` (POE) et `CHG_J` (Config) désignaient la feuille cible par `INDIRECT` reconstruit depuis le nom de switch
(`Changements <ZONE>`). Ça ne tient que pour un nom en trois segments ; sinon toute la colonne POE ressortait `N/C`
en production. Le générateur sait de quel switch vient chaque ligne : la référence est écrite en dur. `CAB_F`
cherche en outre par **port** et non plus par numéro de prise (l'ancienne extraction confondait `P0006` et `P0006B`).

## `Template.xlsx` et l'écrivain XLSX maison

- Le gabarit fournit `styles.xml` + `theme1.xml` (entiers, complétés en fin par `habillage.py` et une police
  Consolas), largeurs de `<cols>` (sans les styles de colonne), `<sheetPr>` et mise en page. Écarts voulus :
  `<sheetProtection>` écarté, `<autoFilter>` régénéré, en-tête d'impression réécrit avec le nom du projet.
- `xlsx.py` écrit le XML directement : une bibliothèque générique risquerait de réécrire ou de perdre les formules
  dynamiques. Ce qui entre ressort à l'identique.

## Limite de test connue

Excel du poste de dev : **2019 LTSC**, sans `LET` ni `TEXTSPLIT` (`#NOM?` partout, classeur d'origine compris). Le
calcul ne se valide que sur M365 / Excel Online. Validable ici : ouverture sans réparation, structure, formules
conservées mot pour mot, références de feuille vers le bon switch (paire piégeuse `C1-3000-6984` /
`C1-3000-6984A`). La suite `tests/` ne couvre aujourd'hui que la règle POE, `lire_poe()` et la parité des abréviations.

## Prochaines étapes

- [ ] Test de bout en bout du générateur sur un projet fictif (`--racine` vers un dossier temporaire) : structure
      des feuilles, valeurs POE, références de feuille. Fait à la main le 2026-11-16 (sortie correcte), pas encore
      dans la suite.
- [ ] `CAB_COLONNES` ne couvre que 11 colonnes sur 14 (largeurs du gabarit) et son commentaire parle encore de
      « 10 colonnes » ; idem le commentaire de `CHG_COLONNES` (« 12 colonnes »). À vérifier sur un classeur produit.
- [ ] Variable `marques` de `feuille_changements()` calculée mais plus utilisée depuis la recherche par port.
- [ ] Retirer `__pycache__/` du dépôt et l'ajouter au `.gitignore`.
- [ ] Wiki (`docs-wiki`) : y déplacer les explications longues de ce fichier.
- [ ] Ajouter le projet à `Hub/projets.json` (dépôt `Myst-LB/Hub`, `METHODE.md` § 4.6).
