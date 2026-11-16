# -*- coding: utf-8 -*-
"""
Formules Excel du gabarit, reprises de
Projet_Reamenagement_Cablage_Genie.xlsx (feuilles « CABLAGE Genie » et
« Changements Z7-0002 »).

NE PAS REFORMATER. Ces formules utilisent LET / LAMBDA / MAP / TEXTSPLIT /
XLOOKUP, donc les prefixes `_xlfn.` (fonction moderne) et `_xlpm.` (parametre
de LET) sont **obligatoires** dans le XML : c'est ainsi qu'Excel les stocke.
Ecrire `LET(` au lieu de `_xlfn.LET(` produit un classeur corrompu.

Les cellules marquees ARRAY doivent etre ecrites avec <f t="array" ref="..."/>.

AUCUNE LETTRE DE COLONNE N'EST ECRITE EN DUR. Elles arrivent toutes par
substitution depuis CAB / CHG ci-dessous, qui sont la seule source de verite
sur la disposition des feuilles. Les colonnes ont deja bouge trois fois ; a
chaque fois, une lettre oubliee dans une formule donnait un classeur qui
s'ouvre sans erreur et affiche des valeurs fausses. Pour deplacer, ajouter ou
retirer une colonne : editer CAB_ENTETES / CHG_ENTETES et le dictionnaire
correspondant, et rien d'autre.

Substitutions appliquees par generer_projet_cablage.py :
  * {r}          -> numero de ligne courant
  * {cab}/{last} -> feuille CABLAGE et sa derniere ligne (VLOOKUP)
  * {chg}/{prem}/{fin} -> feuille Changements et les lignes du switch
  * {cfg}/{nlig} -> feuille de config du switch et son nombre de lignes
  * les autres champs nommes -> lettres de colonne (voir CAB / CHG)
"""

# --- Disposition des feuilles ------------------------------------------------
# Feuille « CABLAGE <XXXX> ». « Nouv. Switch » est le repere qui dit quelle
# switch reprend l'ancienne prise. « État » ne porte que l'avancement (liste
# ETATS du generateur) ; ce que le script a a dire sur la ligne -- DOUBLON,
# HORS GABARIT -- va dans « Commentaire ».
CAB_ENTETES = ["Local Switch", "Anc. Switch", "Interface", "Description",
               "Anc. Prise", "Anc. Locale", "Nouv. Prise", "Nouv. Switch",
               "Nouv. Interface", "POE", "Nouv. Locale", "VOCATION",
               "État", "Commentaire"]

# Feuille « Changements <switch> ». « Power », « Class » et « Max » ont ete
# retires : le PoE se lit dans la colonne POE, et l'equipement dans Device.
CHG_ENTETES = ["Switch", "Interface", "Admin", "Anc. Prise", "POE", "Device",
               "Config", "Nouv. Interface", "Local", "Nouv. Prise",
               "Description override", "New Config", "État", "Commentaire"]


def _lettres(entetes):
    """{nom d'entete: lettre de colonne}, pour ne jamais compter a la main."""
    return {nom: chr(ord("A") + i) for i, nom in enumerate(entetes)}


CAB = _lettres(CAB_ENTETES)
CHG = _lettres(CHG_ENTETES)

# Index (1 = 1re colonne de la plage) utilises par les VLOOKUP, qui comptent a
# partir de la colonne « Anc. Prise » de CABLAGE.
_base = CAB_ENTETES.index("Anc. Prise")
CAB_IDX = {nom: CAB_ENTETES.index(nom) - _base + 1 for nom in CAB_ENTETES}
CAB_DERNIERE = CAB_ENTETES[-1]          # borne droite des plages de VLOOKUP


# --- Feuille « CABLAGE XXXX », colonne POE -- ARRAY --------------------------
# Remonte l'etat PoE depuis la feuille Changements du switch de cette ligne, en
# appariant le numero de prise avec le « _Pxxxx » lu dans la description de la
# config (colonne Config de Changements).
#
# RECHERCHE PAR PORT (Anc. Switch + Interface), plus par numero de prise : la
# version precedente re-extrayait les chiffres derriere « _P » dans la config,
# ce qui confondait « P0006 » et « P0006B » et ratait « P0411  2ieme ».
#
# ECART ASSUME AVEC L'ORIGINAL. La version d'origine deduisait la feuille cible
# du CONTENU de la colonne A : troncature au 1er point, position du 2e tiret,
# UPPER, puis INDIRECT sur "Changements <ZONE>". Ce calcul ne tient que si la
# colonne A porte un nom de switch en trois segments (« Z7-0002-9200A »). Il
# tombe a cote pour un suffixe de lettre absent (« C1-3000-6984 ») et pour un
# nom parenthese (« C1-3000-6984A (Julie) ») : la feuille visee n'existe pas,
# et TOUTE la colonne POE ressort en « N/C ».
# Le coeur de la formule (MAP + extraction du « _P ») est inchange ; seules les
# deux lignes INDIRECT deviennent des references directes.
#
# Le dernier IF neutralise le 0 que rend INDEX quand la cellule visee est vide
# -- c'est ce qui faisait apparaitre « 0 » au lieu de « NON-POE ». Les trois
# VLOOKUP (CHG_K/M/O) portent deja la meme protection dans l'original ; elle
# manquait ici.
CAB_F = '''IF({c_sw}{r}="", "",
_xlfn.LET(
  _xlpm.v, IFERROR(_xlfn.XLOOKUP(
    {c_sw}{r}&"|"&{c_int}{r},
    '{chg}'!${c_chg_switch}${prem}:${c_chg_switch}${fin}&"|"&'{chg}'!${c_chg_int}${prem}:${c_chg_int}${fin},
    '{chg}'!${c_chg_poe}${prem}:${c_chg_poe}${fin}), "N/C"),
  IF(_xlpm.v=0, "", _xlpm.v)))'''

# --- Feuille « Changements <switch> » ----------------------------------------
# « Config » -- va chercher le bloc de config de l'interface dans la feuille de
# config du switch, entre la ligne « interface X » et le « ! » suivant.
#
# ECART ASSUME AVEC L'ORIGINAL, meme raison que CAB_F : l'original faisait
# INDIRECT("'" & A{r} & "'!$A$1:$A$20000"), ce qui imposait que le nom de
# feuille soit exactement le contenu de la colonne Switch -- impossible des que
# ce nom depasse 31 caracteres ou contient un caractere interdit. Ici la plage
# est ecrite en dur ({cfg}, {nlig}). Tout le reste est identique.
CHG_J = '''_xlfn.SINGLE(_xlfn.LET(_xlpm.abr, LEFT({c_int}{r}, MIN(FIND({{"0";"1";"2";"3";"4";"5";"6";"7";"8";"9"}}, {c_int}{r} & "0123456789")) - 1), _xlpm.reste, MID({c_int}{r}, LEN(_xlfn.SINGLE(_xlpm.abr)) + 1, 99), _xlpm.long, _xlfn.XLOOKUP(_xlfn.SINGLE(_xlpm.abr), {{"Gi";"Te";"Tw";"Twe";"Fa";"Po";"Ap";"Hu";"Fo"}}, {{"GigabitEthernet";"TenGigabitEthernet";"TwoGigabitEthernet";"TwentyFiveGigE";"FastEthernet";"Port-channel";"AppGigabitEthernet";"HundredGigE";"FortyGigabitEthernet"}}, _xlpm.abr), _xlpm.rng, '{cfg}'!$A$1:$A${nlig}, _xlpm.s, MATCH("interface " & _xlfn.SINGLE(_xlpm.long) & _xlfn.SINGLE(_xlpm.reste), _xlpm.rng, 0), _xlpm.e, MATCH("!", _xlfn.DROP(_xlpm.rng, _xlpm.s), 0), IFERROR(_xlfn.TEXTJOIN(CHAR(10), TRUE, _xlfn.TAKE(_xlfn.DROP(_xlpm.rng, _xlfn.SINGLE(_xlpm.s) - 1), _xlpm.e)), "interface introuvable")))'''

# Les VLOOKUP vers CABLAGE. {i_xxx} sont les index de colonne comptes
# depuis « Anc. Prise » ; ils viennent de CAB_IDX, donc ils suivent
# automatiquement tout deplacement de colonne dans CABLAGE.
# Recherche par port exact (Anc. Switch + Interface), y compris HORS GABARIT.
def _chg_lookup(cible):
    return '''_xlfn.LET(
  _xlpm.v, IFERROR(_xlfn.XLOOKUP(
    {c_switch}{r}&"|"&{c_int}{r},
    '{cab}'!${c_cab_switch}$3:${c_cab_switch}${last}&"|"&'{cab}'!${c_cab_interface}$3:${c_cab_interface}${last},
    '{cab}'!${%s}$3:${%s}${last}), ""),
  IF(_xlpm.v=0, "", _xlpm.v)
)''' % (cible, cible)

# ARRAY obligatoire : la plage de recherche est une concatenation de deux
# plages. Ecrite en formule « classique », Excel y applique l'intersection
# implicite (@) -- la recherche ne voit plus qu'une cellule et rend "".
CHG_K = _chg_lookup("c_cab_nvint")
CHG_I = _chg_lookup("c_cab_nvlocale")
CHG_M = _chg_lookup("c_cab_nvprise")
CHG_O = _chg_lookup("c_cab_etat")
CHG_P = _chg_lookup("c_cab_comm")

# Format de prise : toujours 4 caracteres apres le P -- « P0643 » pour un
# numero simple, « P006B » (3 chiffres + lettre) quand une lettre suit.
#
# Etat « À désactiver » : New Config devient « default interface <X> » (X =
# l'interface ACTUELLE, 1re ligne du bloc Config) -- le port est remis a sa
# configuration d'usine. Le reste (Nouv. Interface, override...) est ignore.
#
# « Description override » : saisie libre. Remplie, elle REMPLACE le texte de
# la ligne « description » (au lieu de <Local>_P<Nouv. Prise>) -- pour une
# nomenclature particuliere. Vide, rien ne change.
#
# « New Config » -- reecrit le bloc : renomme l'interface (Nouv. Interface) et
# reconstruit la ligne « description <LOCAL>_P<NNNN> » a partir de Local et
# Nouv. Prise. ARRAY
CHG_N = '''_xlfn.LET(
  _xlpm.bloc, {c_config}{r},
  _xlpm.lignes, _xlfn.TEXTSPLIT(_xlpm.bloc, , CHAR(10)),
  _xlpm.abr, IF({c_nvint}{r}="", "", LEFT({c_nvint}{r}, MIN(FIND({{"0";"1";"2";"3";"4";"5";"6";"7";"8";"9"}}, {c_nvint}{r}&"0123456789"))-1)),
  _xlpm.long, IF({c_nvint}{r}="", "", IF(_xlpm.abr="", "GigabitEthernet", _xlfn.XLOOKUP(_xlpm.abr,
        {{"Gi";"Te";"Tw";"Twe";"Fa";"Po";"Ap";"Hu";"Fo"}},
        {{"GigabitEthernet";"TenGigabitEthernet";"TwoGigabitEthernet";"TwentyFiveGigE";"FastEthernet";"Port-channel";"AppGigabitEthernet";"HundredGigE";"FortyGigabitEthernet"}},
        _xlpm.abr))),
  _xlpm.lignesInt, IF(OR({c_nvint}{r}="",{c_nvint}{r}=0), _xlpm.lignes, _xlfn.VSTACK("interface " & _xlpm.long & MID({c_nvint}{r}, LEN(_xlpm.abr)+1, 50), _xlfn.DROP(_xlpm.lignes, 1))),
  _xlpm.posD, IFERROR(MATCH(TRUE, ISNUMBER(SEARCH(" description ", _xlpm.lignesInt)), 0), NA()),
  _xlpm.ancienne, IF(ISNA(_xlpm.posD), "", TRIM(SUBSTITUTE(INDEX(_xlpm.lignesInt, _xlpm.posD), " description ", ""))),
  _xlpm.posP, IFERROR(SEARCH("_P", _xlpm.ancienne), NA()),
  _xlpm.vieuxLocal, IF(ISNA(_xlpm.posP), _xlpm.ancienne, LEFT(_xlpm.ancienne, _xlpm.posP-1)),
  _xlpm.vieuxNum, IF(ISNA(_xlpm.posP), "", MID(_xlpm.ancienne, _xlpm.posP+1, 50)),
  _xlpm.partLocal, IF({c_local}{r}<>"", {c_local}{r}, _xlpm.vieuxLocal),
  _xlpm.np, {c_nvprise}{r}&"",
  _xlpm.partNum, IF(_xlpm.np<>"", "P" & IFERROR(TEXT(VALUE(_xlpm.np), "0000"), IFERROR(TEXT(VALUE(LEFT(_xlpm.np, LEN(_xlpm.np)-1)), "000") & UPPER(RIGHT(_xlpm.np, 1)), _xlpm.np)), _xlpm.vieuxNum),
  _xlpm.sep, IF(AND(_xlpm.partLocal<>"", _xlpm.partNum<>""), "_", ""),
  _xlpm.desctxt, " description " & IF({c_override}{r}<>"", TRIM({c_override}{r}), _xlpm.partLocal & _xlpm.sep & _xlpm.partNum),
  _xlpm.lignesMaj, IF(ISNUMBER(SEARCH("description", _xlpm.lignesInt)), _xlpm.desctxt, _xlpm.lignesInt),
  _xlpm.avecDesc, IF(OR({c_local}{r}<>"", {c_nvprise}{r}<>"", {c_override}{r}<>""),
      IF(ISNA(_xlpm.posD), _xlfn.VSTACK(_xlfn.TAKE(_xlpm.lignesMaj,1), _xlpm.desctxt, _xlfn.DROP(_xlpm.lignesMaj,1)), _xlpm.lignesMaj),
      _xlpm.lignesInt),
  IF({c_etat_l}{r}="{desactiver}", "default " & TRIM(INDEX(_xlpm.lignes, 1)),
  IF(AND({c_nvint}{r}="", {c_local}{r}="", {c_nvprise}{r}="", {c_override}{r}=""), _xlpm.bloc, _xlfn.TEXTJOIN(CHAR(10), TRUE, _xlpm.avecDesc)))
)'''


# --- Feuille « IMPRESSION » -- une seule formule, qui deborde (spill) ---------
# Colonnes reprises de CABLAGE, dans l'ordre d'impression. Les noms sont ceux de
# CAB_ENTETES : les index de CHOOSECOLS en sont deduits, jamais ecrits a la main.
IMP_COLONNES = ["Local Switch", "Anc. Prise", "Anc. Locale", "POE", "VOCATION", "Description",
                "Nouv. Prise", "Nouv. Locale", "Nouv. Switch",
                "Nouv. Interface", "Commentaire"]
# En-tetes affiches (plus courts, pour tenir en largeur sur une Lettre US).
IMP_TITRES = {"Local Switch": "Local Switch", "Anc. Prise": "Prise",
              "Anc. Locale": "Anc. Local",
              "POE": "POE", "VOCATION": "Vocation",
              "Description": "Description", "Nouv. Prise": "Nouv. Prise",
              "Nouv. Locale": "Nouv. Local", "Nouv. Switch": "Nouv. SW",
              "Nouv. Interface": "Nouv. Int", "Commentaire": "Commentaire"}

# --- Feuille « Config à copier » -- une section par switch -----------------
# Excel entoure de guillemets une cellule copiee qui contient des retours a la
# ligne : copier « New Config » donnait des "..." dans le CLI. Ici chaque
# ligne de config est dans SA cellule : une plage de cellules d'une ligne se
# copie sans guillemets.
# Une section par switch (on s'y connecte un par un en SSH) :
#   !===== <switch> =====
#   configure terminal
#   <blocs des lignes a l'etat {etat}, separes par « ! »>
#   end
# Le titre commence par « ! » : copie par megarde, l'IOS l'ignore.
# UNE seule formule (A3), de longueur FIXE : REDUCE parcourt les switchs de
# Changements (UNIQUE, dans l'ordre de la feuille) et empile leurs sections.
# La version precedente repetait le bloc pour chaque switch et depassait la
# limite Excel de 8 192 caracteres par formule des ~15 switchs -- Excel
# supprimait alors la formule a l'ouverture (« Enregistrements supprimes »).
COPIE = '''_xlfn.LET(
  _xlpm.sw, '{chg}'!${c_switch}$2:${c_switch}${fin},
  _xlpm.et, '{chg}'!${c_etat}$2:${c_etat}${fin},
  _xlpm.nv, '{chg}'!${c_newcfg}$2:${c_newcfg}${fin},
  _xlpm.res, _xlfn.REDUCE("", _xlfn.UNIQUE(_xlpm.sw), _xlfn.LAMBDA(_xlpm.acc, _xlpm.s,
    _xlfn.LET(
      _xlpm.b, _xlfn._xlws.FILTER(_xlpm.nv, (_xlpm.sw=_xlpm.s)*IFERROR((_xlpm.et="{etat}")+(_xlpm.et="{etat2}"), 0), ""),
      _xlpm.x, _xlfn.TEXTJOIN(CHAR(10)&"!"&CHAR(10), TRUE, _xlpm.b),
      _xlpm.c, IF(_xlpm.x="", "! aucune ligne « {etat} » ou « {etat2} » pour ce switch",
                  "configure terminal"&CHAR(10)&_xlpm.x&CHAR(10)&"end"),
      _xlfn.VSTACK(_xlpm.acc, "", _xlfn.TEXTSPLIT("!===== "&_xlpm.s&" ====="&CHAR(10)&_xlpm.c, , CHAR(10)))))),
  _xlfn.DROP(_xlpm.res, 2)
)'''


def formule_copie(chg_nom, derniere, etat, etat2="À désactiver"):
    """Formule A3 de « Config à copier » ; `derniere` = derniere ligne de
    Changements."""
    return COPIE.format(chg=chg_nom, fin=max(derniere, 2), etat=etat,
                        etat2=etat2,
                        c_switch=CHG["Switch"], c_etat=CHG["État"],
                        c_newcfg=CHG["New Config"])


def champs_cab(chg_nom, prem, fin):
    """Champs de substitution pour la formule PoE de CABLAGE.

    `prem`/`fin` : lignes du switch dans la feuille Changements, qui regroupe
    tous les switchs -- la formule ne doit chercher que dans les siennes.
    """
    return {"c_prise": CAB["Anc. Prise"], "chg": chg_nom, "prem": prem,
            "fin": fin, "c_sw": CAB["Anc. Switch"], "c_int": CAB["Interface"],
            "c_chg_switch": CHG["Switch"], "c_chg_int": CHG["Interface"],
            "c_chg_config": CHG["Config"], "c_chg_poe": CHG["POE"]}


def champs_chg(cab_nom, last, cfg_nom=None, nlig=None):
    """Champs de substitution pour toutes les formules de Changements."""
    return {"c_config": CHG["Config"], "c_switch": CHG["Switch"],
            "c_int": CHG["Interface"], "c_ancprise": CHG["Anc. Prise"],
            "c_nvint": CHG["Nouv. Interface"], "c_local": CHG["Local"],
            "c_nvprise": CHG["Nouv. Prise"], "cab": cab_nom, "last": last,
            "c_override": CHG["Description override"],
            "c_etat_l": CHG["État"], "desactiver": "À désactiver",
            "c_cab_switch": CAB["Anc. Switch"],
            "c_cab_interface": CAB["Interface"],
            "c_cab_nvint": CAB["Nouv. Interface"],
            "c_cab_nvprise": CAB["Nouv. Prise"],
            "c_cab_nvlocale": CAB["Nouv. Locale"],
            "c_cab_etat": CAB["État"], "c_cab_comm": CAB["Commentaire"],
            "cfg": cfg_nom, "nlig": nlig}
