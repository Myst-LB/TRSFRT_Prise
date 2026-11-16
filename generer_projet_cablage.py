# -*- coding: utf-8 -*-
"""Genere Projet_Reamenagement_Cablage_<XXXX>.xlsx a partir d'un dossier projet.

Arborescence attendue (le nom du dossier projet donne le « XXXX ») :

    Changement Cablage/
    |-- Genie/
    |   |-- Config/          un .txt par switch : « show running-config »
    |   `-- POE/             un .txt par switch : « show power inline »
    `-- Projet_Reamenagement_Cablage_Genie.xlsx      <- produit ici

Tout sous-dossier de la racine est examine. Les configs sont cherchees dans
« Config/ » si ce sous-dossier existe, sinon directement a la racine du dossier
projet. « POE/ » est optionnel.

Le nom du .txt (sans extension) est le nom du switch, tel qu'il apparait en
colonne « Switch ». Les noms de feuille en sont derives mais assainis (Excel
plafonne a 31 caracteres et interdit []:*?/\\), ce qui est sans consequence :
les formules referencent les feuilles en dur, pas via INDIRECT.

Feuilles produites, dans l'ordre :
  1. « CABLAGE <XXXX> »          -- une ligne par interface decrite (LOCAL_Pxxxx)
  2. « Changements All Switch » -- une ligne par port, tous switchs confondus
  3. « <switch> »                -- config brute, une ligne par cellule

Usage :
    python generer_projet_cablage.py                  # diff de tous les projets
    python generer_projet_cablage.py Genie            # diff du projet Genie
    python generer_projet_cablage.py Genie --force    # ecrit (sauvegarde l'ancien)
    python generer_projet_cablage.py Genie --descriptions   # diagnostic
    python generer_projet_cablage.py Genie --force --sans-sauts-page
                                     # CABLAGE imprimee d'un seul tenant
"""
import argparse
import datetime
import os
import re
import shutil
import sys
import time
import zipfile

import analyse
import formules as F
import gabarit as gab_mod
import habillage
import xlsx
from xlsx import Feuille, form, num, txt, vide

RESERVE_DEFAUT = 50          # lignes vides en fin de feuille CABLAGE
GABARIT_DEFAUT = "Template.xlsx"   # source de la presentation
LARGEUR_COL_SWITCH = "28"    # « C1-3124-9201A (Technicien) »
# Largeurs de CABLAGE, PAR NOM D'EN-TETE : les positions se deduisent de
# F.CAB_ENTETES. Les anciennes tables etaient indexees par numero de colonne ;
# chaque colonne inseree (Local Switch, Interface, Description) decalait toutes
# les largeurs d'un cran et laissait les dernieres colonnes sans largeur.
# CAB_DEPUIS_GABARIT : colonne du gabarit (9 colonnes) dont on reprend la
# largeur. CAB_LARGEURS_FIXES : largeur imposee, prioritaire.
CAB_DEPUIS_GABARIT = {"Anc. Prise": 2, "Nouv. Prise": 4, "Nouv. Interface": 5,
                      "POE": 6, "Nouv. Locale": 7, "VOCATION": 8}
CAB_LARGEURS_FIXES = {"Local Switch": "11", "Anc. Switch": LARGEUR_COL_SWITCH,
                      "Interface": "11", "Description": "30",
                      "Anc. Locale": "13", "Nouv. Switch": LARGEUR_COL_SWITCH,
                      "État": "13", "Commentaire": "40"}
assert set(CAB_DEPUIS_GABARIT) | set(CAB_LARGEURS_FIXES) == set(F.CAB_ENTETES), \
    "chaque colonne de CABLAGE doit avoir une largeur"


def _par_position(par_nom, entetes):
    """{nom d'en-tete: v} -> {numero de colonne (1 = A): v}."""
    return {entetes.index(nom) + 1: v for nom, v in par_nom.items()}


CAB_COLONNES = _par_position(
    dict({nom: 1 for nom in F.CAB_ENTETES}, **CAB_DEPUIS_GABARIT), F.CAB_ENTETES)
CAB_LARGEURS = _par_position(CAB_LARGEURS_FIXES, F.CAB_ENTETES)
# Les styles de cellule viennent de habillage.py, par nom de colonne.
HAUTEUR_ENTETE_CAB = "30"    # en-tetes sur deux lignes (« Nouv. Interface »)
HAUTEUR_LIGNE_CAB = "26"     # de la place pour annoter au crayon
HAUTEUR_GROUPE = "20"
# Impression de CABLAGE : Lettre US (paperSize 1), portrait, echelle 69 %.
# fitToHeight="0" du gabarit est retire : sans fitToPage il ne sert a rien.
MISE_EN_PAGE_CAB = '<pageSetup paperSize="1" scale="69" orientation="portrait"/>'
# Feuille Changements : 14 colonnes produites contre 15 dans le gabarit.
# « Power », « Class » et « Max » ont ete retirees ; « Description override »
# est nouvelle. Les largeurs reelles viennent de largeurs_changements() (par
# nom d'en-tete) ; le gabarit ne sert plus que de repli. Rien n'est masque : le
# gabarit masquait Admin et Device, or Device doit se lire.
HAUTEUR_LIGNE_MONO = 12.0    # points par ligne de config en Consolas 9
ETIQUETTE_HG = "— HORS GABARIT —"   # ligne de separation dans CABLAGE
MARQUE_HG = "HORS GABARIT"
MARQUE_DOUBLON = "DOUBLON"
ETIQUETTE_GROUPE = "Local technique %s"
CHG_COLONNES = {i: i for i in range(1, len(F.CHG_ENTETES) + 1)}
# Seules valeurs admises en colonne « État » (liste deroulante). Ce que le
# script signale lui-meme -- DOUBLON, HORS GABARIT -- va en « Commentaire ».
ETATS = ("Fait", "À faire", "À prog", "À désactiver", "À vérifier", "Non-fait",
         "Ne pas faire")
ETAT_DESACTIVER = "À désactiver"   # New Config -> « default interface X »
ETAT_DEFAUT = "Non-fait"
MAX_NOM_FEUILLE = 31         # limite Excel
# L'unique feuille Changements : les ports de tous les switchs, bout a bout.
# Son nom est reserve avant ceux des switchs : un homonyme recevrait ~2.
NOM_CHG_TOUS = "Changements All Switch"
NOM_IMPRESSION = "IMPRESSION"
NOM_COPIE = "Config à copier"
ETAT_COPIE = "À prog"            # lignes reprises dans « Config à copier »
# Feuilles faites uniquement de formules : ni diff, ni restauration.
SANS_DIFF = (NOM_IMPRESSION, NOM_COPIE)
ETAT_IMPRESSION = "À faire"      # seules ces lignes vont sur la feuille IMPRESSION
# Largeurs (en caracteres) calibrees pour tenir sur une Lettre US paysage ;
# fitToWidth ajuste de toute facon a une page de large.
IMP_LARGEURS = {"Local Switch": 11, "Anc. Prise": 8, "Anc. Locale": 13,
                "POE": 9, "VOCATION": 13, "Description": 22,
                "Nouv. Prise": 10, "Nouv. Locale": 13, "Nouv. Switch": 16,
                "Nouv. Interface": 11, "Commentaire": 22}
# Lettre US paysage, une page de large. La colonne « Imprimer ? » et la ligne
# de rappel sont hors de la zone d'impression (Print_Area).
MISE_EN_PAGE_IMP = ('<pageMargins left="0.25" right="0.25" top="0.6" '
                    'bottom="0.5" header="0.25" footer="0.25"/>'
                    '<pageSetup paperSize="1" orientation="landscape" '
                    'fitToWidth="1" fitToHeight="0"/>')
# Excel interdit ces caracteres dans un nom de feuille ; l'apostrophe est retiree
# en plus, parce qu'une reference 'nom'!A1 l'exigerait doublee.
RE_INTERDITS = re.compile(r"[\[\]:*?/\\']")
# Parenthese finale d'un nom de switch : « C1-3000-6984A (Julie) ». Retiree pour
# fabriquer le nom de feuille (la colonne Switch garde le nom complet), sans
# quoi « Changements C1-3000-6984A (Julie) » ferait 33 caracteres.
RE_PARENTHESE = re.compile(r"\s*\([^)]*\)\s*$")
# Local technique : les deux premiers segments du nom de switch, avant le
# modele -- « Z7-0002 » dans « Z7-0002-9200A ».
RE_LOCAL_TECH = re.compile(r"^([^-\s]+-[^-\s]+)-")


class Noms:
    """Attribue des noms de feuille uniques, valides et <= 31 caracteres."""

    def __init__(self):
        self.pris = set()
        self.renommages = []      # (nom souhaite, nom retenu)

    def attribuer(self, souhaite):
        base = RE_INTERDITS.sub("", souhaite).strip() or "Feuille"
        base = base[:MAX_NOM_FEUILLE]
        nom, n = base, 1
        while nom.lower() in self.pris:
            n += 1
            suffixe = "~%d" % n
            nom = base[:MAX_NOM_FEUILLE - len(suffixe)] + suffixe
        self.pris.add(nom.lower())
        if nom != souhaite:
            self.renommages.append((souhaite, nom))
        return nom


def nom_court(sw_nom):
    """Nom de switch debarrasse de sa parenthese finale, pour les onglets."""
    return RE_PARENTHESE.sub("", sw_nom).strip() or sw_nom


def local_technique(sw_nom):
    """« Z7-0002-9200A (Julie) » -> « Z7-0002 ».

    Ne sert qu'a regrouper les lignes de CABLAGE (et a couper les pages a
    l'impression) : aucune formule ni aucun nom de feuille n'en depend. Un nom
    qui ne suit pas la forme <batiment>-<local>-<modele> forme donc simplement
    un groupe a lui seul, sans rien casser.
    """
    court = nom_court(sw_nom)
    m = RE_LOCAL_TECH.match(court)
    return m.group(1) if m else court


# --- Localisation des projets ------------------------------------------------

def sous_dossier(dossier, nom):
    """Sous-dossier au nom donne, insensible a la casse. None si absent."""
    try:
        for e in os.scandir(dossier):
            if e.is_dir() and e.name.lower() == nom.lower():
                return e.path
    except OSError:
        pass
    return None


def txt_de(dossier):
    try:
        return sorted((e.path for e in os.scandir(dossier)
                       if e.is_file() and e.name.lower().endswith(".txt")),
                      key=lambda p: os.path.basename(p).lower())
    except OSError:
        return []


def dossier_configs(dossier):
    """« Config/ » s'il existe, sinon la racine du projet si elle a des .txt."""
    d = sous_dossier(dossier, "Config")
    if d and txt_de(d):
        return d
    return dossier if txt_de(dossier) else None


def trouver_projets(racine):
    """Tout sous-dossier contenant des .txt (a sa racine ou dans Config/)."""
    projets = []
    try:
        entrees = sorted(os.scandir(racine), key=lambda x: x.name.lower())
    except OSError as exc:
        sys.exit("ERREUR : impossible de lire %s (%s)" % (racine, exc))
    for e in entrees:
        if not e.is_dir() or e.name.startswith((".", "_", "~", "$")):
            continue
        if e.name.lower() in ("poe", "config"):      # sous-dossiers d'un projet
            continue
        if dossier_configs(e.path):
            projets.append(e.path)
    return projets


def charger_projet(dossier):
    """-> (nom_projet, [Switch])."""
    nom = os.path.basename(os.path.normpath(dossier))
    d_config = dossier_configs(dossier)
    if not d_config:
        sys.exit("ERREUR : aucun .txt de config dans %s (ni a la racine, ni "
                 "dans un sous-dossier « Config »)" % dossier)
    d_poe = sous_dossier(dossier, "POE")
    if d_config == dossier:
        print("  note : configs lues a la racine du projet (pas de « Config/ »)")

    switchs = []
    for chemin in txt_de(d_config):
        sw_nom = os.path.splitext(os.path.basename(chemin))[0]
        sw = analyse.Switch(sw_nom, analyse.lire_config(chemin))
        if d_poe:
            f_poe = os.path.join(d_poe, os.path.basename(chemin))
            if os.path.isfile(f_poe):
                sw.poe, entete = analyse.lire_poe(f_poe)
                if not sw.poe and entete:
                    sw.sans_poe = True     # tableau vide : switch sans PoE
                elif not sw.poe:
                    sw.avertissements.append(
                        "POE/%s : pas d'entete « Interface Admin Oper Power » "
                        "-- ce n'est pas une sortie « show power inline »"
                        % os.path.basename(chemin))
            else:
                sw.avertissements.append("pas de fichier POE correspondant")
        # Le nom de fichier fait foi partout dans le classeur ; si la config
        # qu'il contient annonce un autre hostname, c'est que la collecte a
        # verse le mauvais fichier -- silencieusement indetectable autrement.
        if sw.hostname and sw.hostname != nom_court(sw_nom) and sw.hostname != sw_nom:
            sw.avertissements.append(
                "le fichier s'appelle « %s » mais la config dit "
                "« hostname %s » -- fichier mal nomme ou mauvaise collecte ?"
                % (sw_nom, sw.hostname))
        switchs.append(sw)
    if not d_poe:
        print("  note : pas de sous-dossier « POE », colonnes POE laissees vides")
    return nom, switchs


# --- Construction des feuilles ----------------------------------------------

def ports_du_switch(sw):
    """Ports listes dans « Changements ».

    Le show power inline fait foi quand il est la (il enumere les ports
    physiques du chassis, y compris ceux absents de la config). A defaut on
    retombe sur les interfaces physiques de la config.
    """
    if sw.poe:
        ports = list(sw.poe.keys())
        # Le show power inline ne liste que les ports PoE : les uplinks
        # (Te1/1/x...) en sont absents. Or ce sont justement eux qui portent
        # le plus souvent une description sans prise (HORS GABARIT) -- sans
        # cet ajout, ils n'apparaissaient jamais dans « Changements All
        # Switch ». On complete donc avec les interfaces physiques DECRITES
        # de la config que le tableau PoE ne connait pas.
        connus = set(ports)
        ports += [it.abrege for it in sw.interfaces
                  if it.physique and it.description
                  and it.abrege not in connus]
        return ports
    return [it.abrege for it in sw.interfaces if it.physique]


def cle_doublon(type_port, e):
    """Cle de regroupement des doublons ; unique par port pour une prise a 0."""
    local, prise, sw, it = e[:4]
    if it.prise_tri[0] == 0 and not it.prise_tri[1]:
        return (type_port, local, "#0", sw.nom, it.abrege)
    return (type_port, local, prise)


def lignes_cablage(switchs):
    """-> (entrees, doublons, hors_gabarit).

    C'est la description qui porte la prise murale, et c'est sur ce numero que
    tout le classeur s'apparie (colonne « Anc. Prise », puis les VLOOKUP et la
    formule POE). `hors_gabarit` recueille les ports decrits dont la
    description ne livre aucun numero de prise.
    """
    brutes, hors_gabarit = [], []
    for sw in switchs:
        for it in sw.interfaces:
            if not it.physique:
                continue
            if it.prise is not None:
                brutes.append((it.local, it.prise, sw, it))
            elif it.description:
                # Description presente mais sans numero de prise exploitable :
                # uplink, lien inter-switch, tunnel... Ces ports etaient
                # purement ignores ; ils vont maintenant dans une section a
                # part, en fin de feuille.
                hors_gabarit.append((sw, it))

    # Une prise murale n'est brassee que sur un seul port. Deux ports qui la
    # revendiquent, c'est une description restee en place sur un port
    # re-brasse ailleurs. On garde TOUTES les lignes -- ecarter la seconde
    # faisait disparaitre un port reel du plan, et le choix de « la premiere »
    # ne tenait qu'a l'ordre alphabetique des fichiers. Le conflit est ecrit
    # dans la colonne Commentaire, donc visible dans le classeur et pas seulement
    # dans la console.
    # Les ports AP et les prises ordinaires ont des espaces de numerotation
    # distincts. AP X n'est pas un doublon de PRISE X ; deux AP X restent un
    # vrai doublon, tout comme deux prises ordinaires X.
    par_prise = {}
    # Une prise a zero (« P0000 », numero jamais rempli) n'identifie aucune
    # prise murale : deux ports en P0000 ne sont pas un doublon. Chacun a donc
    # son propre groupe (cle unique par port).
    for e in brutes:
        type_port = "AP" if analyse.est_ap(e[3].description) else "PRISE"
        par_prise.setdefault(cle_doublon(type_port, e), []).append(e)

    entrees, doublons = [], []
    for e in brutes:
        type_port = "AP" if analyse.est_ap(e[3].description) else "PRISE"
        groupe = par_prise[cle_doublon(type_port, e)]
        # Le ou les AUTRES ports qui revendiquent la meme prise. C'est cette
        # liste qui part en colonne Commentaire : savoir qu'il y a un doublon ne sert
        # a rien, savoir lequel permet d'aller trancher sur l'equipement.
        autres = ["%s %s" % (g[2].nom, g[3].abrege)
                  for g in groupe if g is not e]
        entrees.append(e + (autres,))
    for cle, groupe in sorted(par_prise.items(),
                              # prise_tri, pas la prise : 643 (nombre) et
                              # « 6B » (texte) ne se comparent pas en Python.
                              key=lambda kv: (kv[0][1] or "",
                                              kv[1][0][3].prise_tri, kv[0][0])):
        if len(groupe) > 1:
            type_port, local = cle[0], cle[1]
            doublons.append(
                "%s %s_%s revendiquee par %d ports : %s"
                % (type_port, local, analyse.code_prise(groupe[0][3].prise_tri),
                   len(groupe),
                   ", ".join("%s %s" % (g[2].nom, g[3].abrege) for g in groupe)))

    # Ordre de lecture : local technique (les groupes de la feuille), puis
    # ancienne switch, ancienne locale, prise.
    entrees.sort(key=lambda e: (local_technique(e[2].nom), e[2].nom,
                                e[0] or "", e[3].prise_tri))
    hors_gabarit.sort(key=lambda x: (x[0].nom, x[1].abrege))
    return entrees, doublons, hors_gabarit


def suspectes(entrees):
    """Entrees dont le LOCAL n'a manifestement pas ete rempli sur le switch.

    Forme normale, mesuree sur le parc reel (2325 occurrences sur ~2400) :
    « <batiment>-<local>-<sous-numero> », p.ex. « C1-2063-00 ». Le « -00 » final
    est donc PARFAITEMENT normal et ne doit surtout pas etre signale -- une
    version anterieure de cette fonction rejetait tout segment a zero et
    noyait le rapport sous des centaines de faux positifs.

    Ce qui est reellement casse, c'est le 2e segment (le numero de local)
    quand il est absent, a zero (« C1-0000-00 ») ou non numerique
    (« C1-xxxx-01 », « C1-TUNNEL »), ou un segment vide (« C1-- »).
    On ne corrige rien : les lignes restent dans le classeur, la donnee fausse
    est sur l'equipement.
    """
    douteuses = []
    for local, prise, sw, it, _ in entrees:
        loc = (local or "").strip()
        motif = None
        if not loc:
            motif = "local vide"
        else:
            segments = loc.split("-")
            if any(s == "" for s in segments):
                motif = "segment vide"
            elif len(segments) >= 2:
                salle = segments[1]
                if re.fullmatch(r"0+", salle):
                    motif = "numero de local a zero (gabarit non rempli)"
                elif not salle.isdigit():
                    motif = "numero de local non numerique"
        if motif:
            douteuses.append((motif, sw.nom, it.abrege, it.description))
    return douteuses


def mef_suivi(f, hab, lettres, premiere):
    """Couleurs d'avancement et d'alerte, communes a CABLAGE et Changements.

    Etat « Fait » en vert gras, « À faire » en orange gras, « À prog » en
    violet gras, « À vérifier » en bleu gras, « Ne pas faire »
    en gris italique ; un
    Commentaire qui signale un DOUBLON ou un port HORS GABARIT en rouge.
    """
    derniere = len(f.lignes)
    e, c = lettres["État"], lettres["Commentaire"]
    plage = lambda col: "%s%d:%s%d" % (col, premiere, col, derniere)
    f.mef += [
        (plage(e), hab.dxf_fait, '$%s%d="%s"' % (e, premiere, "Fait")),
        (plage(e), hab.dxf_a_faire, '$%s%d="%s"' % (e, premiere, "À faire")),
        (plage(e), hab.dxf_a_prog, '$%s%d="%s"' % (e, premiere, "À prog")),
        (plage(e), hab.dxf_a_desactiver, '$%s%d="%s"' % (e, premiere,
                                                          ETAT_DESACTIVER)),
        (plage(e), hab.dxf_a_verifier, '$%s%d="%s"' % (e, premiere,
                                                        "À vérifier")),
        (plage(e), hab.dxf_ne_pas_faire, '$%s%d="%s"' % (e, premiere,
                                                          "Ne pas faire")),
        (plage(c), hab.dxf_alerte, 'OR(LEFT($%s%d,%d)="%s",$%s%d="%s")'
         % (c, premiere, len(MARQUE_DOUBLON), MARQUE_DOUBLON,
            c, premiere, MARQUE_HG)),
    ]


def feuille_cablage(nom_feuille, entrees, reserve, chg_de_switch, modele,
                    queue_xml, hab, hors_gabarit=(), sauts=True):
    """Feuille 1. Ligne 1 entetes, ligne 2 vide, donnees a partir de la 3.

    Ce decalage vient du gabarit d'origine (les VLOOKUP y demarrent en $B$3).
    Chaque formule POE pointe la feuille Changements du switch de SA ligne.

    Les prises sont regroupees par local technique, chaque groupe ouvert par
    une ligne « Local technique Z7-0002 » dont la colonne « Anc. Prise » est
    vide : les VLOOKUP, le diff et la formule POE (qui ne vise que sa propre
    ligne) l'ignorent. `sauts` coupe la page imprimee avant chaque groupe.
    """
    f = Feuille(nom_feuille,
                cols_xml=modele.cols_depuis(CAB_COLONNES, CAB_LARGEURS),
                sheetpr_xml=sans_ajuster(modele.sheetpr_xml),
                queue_xml=queue_xml,
                # Local Switch, Anc. Switch et Interface restent visibles
                # quand on defile vers la planification, a droite.
                fige_colonnes=F.CAB_ENTETES.index("Interface") + 1)
    f.titres = "$1:$1"
    f.ajouter([txt(e, hab.cab_entete[e]) for e in F.CAB_ENTETES],
              hauteur=HAUTEUR_ENTETE_CAB)
    f.ajouter([])
    i_etat = F.CAB_ENTETES.index("État")
    i_comm = F.CAB_ENTETES.index("Commentaire")
    st = [hab.cab_donnee[e] for e in F.CAB_ENTETES]

    def bandeau(texte, style):
        return [txt(texte, style)] + [vide(style)] * (len(F.CAB_ENTETES) - 1)

    groupe = None
    for local, prise, sw, it, autres in entrees:
        if local_technique(sw.nom) != groupe:
            if groupe is not None and sauts:
                f.sauts.append(len(f.lignes))
            groupe = local_technique(sw.nom)
            f.ajouter(bandeau(ETIQUETTE_GROUPE % groupe, hab.groupe),
                      hauteur=HAUTEUR_GROUPE)
        r = len(f.lignes) + 1
        chg, prem, fin = chg_de_switch[sw.nom]
        # Toutes les cellules sont ecrites, meme vides, pour porter la bordure
        # et le fond de leur style : les colonnes de planification (D, E, F,
        # H, I) seraient sinon sans quadrillage.
        ligne = [vide(s) for s in st]
        # A = nom complet de l'ANCIENNE switch ; C = local de la PRISE.
        # D (nouvelle prise), E (nouvelle switch), F (nouvelle interface),
        # H (nouveau local), I et J relevent de la planification : le
        # script ne peut pas les deviner et les laisse vides.
        valeurs = {
            "Local Switch": local_technique(sw.nom),
            "Anc. Switch": sw.nom,
            "Interface": it.abrege,
            "Description": it.description,
            # Pre-rempli avec le texte entre parentheses de la description
            # (« (AP) », « (imprimante) »). Une vocation saisie a la main
            # dans le classeur reste prioritaire (restauration --force).
            "VOCATION": it.vocation,
        }
        for entete, valeur in valeurs.items():
            if valeur:
                i = F.CAB_ENTETES.index(entete)
                ligne[i] = txt(valeur, st[i])
        i = F.CAB_ENTETES.index("Anc. Prise")
        # « 6B » reste du texte ; un numero simple reste un nombre ; une
        # prise vide (« C1-4030-01_Local ») reste une case vide.
        if prise != "":
            ligne[i] = (num(prise, st[i]) if isinstance(prise, int)
                        else txt(prise, st[i]))
        # Un local vide reste une cellule vide, pas une chaine vide.
        if local:
            i = F.CAB_ENTETES.index("Anc. Locale")
            ligne[i] = txt(local, st[i])
        i = F.CAB_ENTETES.index("POE")
        ligne[i] = form(F.CAB_F.format(r=r, **F.champs_cab(chg, prem, fin)),
                        array=True, style=st[i])
        ligne[i_etat] = txt(ETAT_DEFAUT, st[i_etat])
        if autres:
            # Commentaire : on y nomme l'autre port qui revendique cette
            # prise. Ca remonte aussi dans les feuilles Changements via
            # CHG_P, donc depuis le port en doublon on lit directement
            # avec qui il est en conflit.
            ligne[i_comm] = txt(MARQUE_DOUBLON + " " + ", ".join(autres),
                                st[i_comm])
        f.ajouter(ligne, hauteur=HAUTEUR_LIGNE_CAB)
    for _ in range(reserve):
        # Ligne de reserve : cellules vides mais quadrillees.
        f.ajouter([vide(s) for s in st], hauteur=HAUTEUR_LIGNE_CAB)
    derniere = len(f.lignes)

    # Case de planification encore vide sur une ligne de port : surlignee,
    # pour que ce qui reste a decider se voie. Le critere est le switch
    # (colonne Anc. Switch) et non plus la prise, qui peut etre du texte
    # (« 6B », « ABCD ») ou vide (« C1-4030-01_Local »). Les bandeaux et la
    # reserve n'ont pas de switch ; la section hors gabarit commence apres
    # `derniere`, donc hors de la plage.
    b = F.CAB["Anc. Switch"]
    # Pas de jaune sur une ligne « Ne pas faire » ou « À désactiver » : rien
    # n'y reste a planifier.
    et = F.CAB["État"]
    for e in F.CAB_ENTETES:
        if habillage.CAB_FAMILLE[e] == "nouv":
            col = F.CAB[e]
            f.mef.append(("%s3:%s%d" % (col, col, derniere), hab.dxf_a_saisir,
                          'AND($%s3<>"",%s3="",$%s3<>"Ne pas faire",$%s3<>"%s")'
                          % (b, col, et, et, ETAT_DESACTIVER)))
    controles_saisie(f, derniere)
    # POE « N/C » : le port n'a pas ete trouve dans Changements.
    p = F.CAB["POE"]
    f.mef.append(("%s3:%s%d" % (p, p, derniere), hab.dxf_alerte,
                  '$%s3="N/C"' % p))

    if hors_gabarit:
        if sauts:
            f.sauts.append(len(f.lignes))
        f.ajouter(bandeau(ETIQUETTE_HG, hab.separateur), hauteur=HAUTEUR_GROUPE)
        for sw, it in hors_gabarit:
            ligne = [vide(s) for s in st]
            valeurs = {
                "Local Switch": local_technique(sw.nom),
                "Anc. Switch": sw.nom,
                "Interface": it.abrege,
                "Description": it.description,
            }
            for entete, valeur in valeurs.items():
                if valeur:
                    i = F.CAB_ENTETES.index(entete)
                    ligne[i] = txt(valeur, st[i])
            ligne[i_etat] = txt(ETAT_DEFAUT, st[i_etat])
            ligne[i_comm] = txt(MARQUE_HG, st[i_comm])
            f.ajouter(ligne, hauteur=HAUTEUR_LIGNE_CAB)
    mef_suivi(f, hab, F.CAB, 3)
    # Liste deroulante sur toute la colonne Etat, reserve et hors gabarit
    # compris -- bandeaux et separation aussi, sans consequence.
    f.listes.append(("%s3:%s%d" % (F.CAB["État"], F.CAB["État"],
                                   len(f.lignes)), ETATS))
    # Borne des XLOOKUP de Changements : la VRAIE derniere ligne, section hors
    # gabarit comprise. Renvoyer `derniere` (calcule avant cette section)
    # coupait la plage juste au-dessus des lignes HORS GABARIT : Etat et
    # Commentaire restaient vides pour ces ports dans « Changements All Switch ».
    return f, len(f.lignes)


def controles_saisie(f, derniere):
    """Controles de saisie (avertissement) et aides sur la planification.

    Une faute de frappe ne donnait aucun signal : « Gx1/0/5 » ressortait tel
    quel dans New Config (« interface Gx1/0/5 »), une prise « 12AB » en
    « P12AB ». Mode avertissement : on peut passer outre apres confirmation.

    Interface : les 2 premieres lettres sont celles d'un abrege connu (elles
    couvrent aussi les noms longs : « GigabitEthernet » commence par « Gi »),
    ou un chiffre (CHG_N met alors GigabitEthernet). La liste vient de
    analyse.ABREGES : pas de troisieme copie de la table. Excel refuse les
    constantes matricielles dans une validation, d'ou le OR(...).
    """
    def plage(nom):
        col = F.CAB[nom]
        return "%s3:%s%d" % (col, col, derniere)

    i = F.CAB["Nouv. Interface"] + "3"
    prefixes = sorted({abr[:2] for abr, _ in analyse.ABREGES})
    f.controles.append((
        plage("Nouv. Interface"),
        'OR(%s="",ISNUMBER(-LEFT(%s,1)),%s)'
        % (i, i, ",".join('LEFT(%s,2)="%s"' % (i, p) for p in prefixes)),
        "Nouvelle interface",
        "Abrégé + numéro : Gi1/0/5, Te1/1/1, Tw2/0/3... Abrégés reconnus : "
        + ", ".join(dict.fromkeys(abr for abr, _ in analyse.ABREGES)) + "."))
    n = F.CAB["Nouv. Prise"] + "3"
    f.controles.append((
        plage("Nouv. Prise"), 'OR(%s="",LEN(%s)<=4)' % (n, n),
        "Nouvelle prise",
        "4 caractères au plus : 643, 0643 ou 6B (3 chiffres + 1 lettre). "
        "New Config l'écrit P0643 / P006B."))
    f.controles.append((
        plage("Nouv. Locale"), None, "Nouveau local",
        "Local de la prise, forme habituelle C1-1234-00. Reporté dans la "
        "description (Local_P0000)."))
    f.controles.append((
        plage("Nouv. Switch"), None, "Nouveau switch",
        "Nom du switch qui reprend la prise (information de planification)."))


def largeur(textes, mini=8.0, maxi=40.0):
    """Largeur de colonne ajustee au contenu le plus long."""
    n = max((len(t) for t in textes if t), default=0)
    return "%.2f" % max(mini, min(maxi, n + 2.5))


def largeurs_changements(sw, ports, blocs):
    """Largeurs ajustees au contenu reel de CETTE feuille Changements.

    Les colonnes de formule sont dimensionnees sur ce que la formule va
    produire (bloc de config, nom d'interface), pas sur la formule elle-meme.
    Config et New Config sont mesurees sur la ligne la plus longue du bloc et
    plafonnees : au-dela, c'est le retour a la ligne + la hauteur de ligne qui
    rendent le contenu lisible.
    """
    lignes_cfg = [l for bloc in blocs.values() for l in bloc]
    poe = [sw.poe.get(p) for p in ports]
    return _par_position({
        "Switch": largeur([sw.nom]),
        "Interface": largeur(ports),
        "Admin": largeur([p["admin"] for p in poe if p] + ["Admin"]),
        "Anc. Prise": largeur(["Anc. Prise"]),
        "POE": largeur(["NON-POE", "POE+", "POE"]),
        "Device": largeur([p["device"] for p in poe if p] + ["Device"]),
        "Config": largeur(lignes_cfg, mini=20.0, maxi=48.0),
        "Nouv. Interface": largeur(["Nouv. Interface"]),
        "Local": largeur(["Local", "C1-0000-00"]),
        "Nouv. Prise": largeur(["Nouv. Prise"]),
        "Description override": largeur(["Description override",
                                         "C1-0000-00_P0000 (xxxx)"]),
        "New Config": largeur(lignes_cfg, mini=20.0, maxi=48.0),
        "État": largeur(["État"] + list(ETATS)),
        "Commentaire": largeur(["Commentaire", "DOUBLON C1-0000-9200A Gi1/0/48"],
                    maxi=34.0),
    }, F.CHG_ENTETES)


def hauteur_bloc(bloc):
    """Hauteur de ligne (en points) pour afficher un bloc de config entier.

    Excel n'ajuste pas la hauteur a l'ouverture : sans `ht` explicite il
    applique defaultRowHeight, et un bloc de 15 lignes reste ecrase sur une
    seule. On la calcule donc ici, a partir du nombre de lignes du bloc (+1
    pour la ligne « description » que New Config peut inserer).
    """
    if not bloc:
        return None
    lignes = len(bloc) + 1
    return "%.2f" % min(409.0, max(15.0, lignes * HAUTEUR_LIGNE_MONO))


def feuille_changements(nom, switchs, cfg_de_switch, cab, dernier_cab, modele,
                        hab):
    """Une seule feuille Changements : les ports de tous les switchs, a la suite.

    Chaque ligne vise la feuille de config de SON switch, et les switchs se
    suivent dans l'ordre de `switchs` -- celui que construire() utilise pour
    calculer la plage de chacun, que la formule POE de CABLAGE vise.
    Une feuille par switch obligeait a passer d'onglet en onglet ; regrouper
    par « zone » obligeait a deduire une zone du nom de switch, ce qui ne
    survit pas aux noms reels du parc.
    """
    largeurs = {}
    for sw in switchs:
        ports = ports_du_switch(sw)
        blocs = {it.abrege: it.lignes for it in sw.interfaces}
        for col, l in largeurs_changements(sw, ports, blocs).items():
            largeurs[col] = max(largeurs.get(col, l), l, key=float)

    f = Feuille(nom,
                cols_xml=modele.cols_depuis(CHG_COLONNES, largeurs,
                                            masquees=set()),
                sheetpr_xml=modele.sheetpr_xml, queue_xml=modele.queue_xml,
                fige_colonnes=2)        # Switch + Interface restent visibles
    f.ajouter([txt(e, hab.chg_entete[e]) for e in F.CHG_ENTETES])
    r = 1
    for sw in switchs:
        # Les ports hors gabarit n'ont rien de particulier ici : la recherche
        # se fait par port (switch + interface), pas par numero de prise, donc
        # leurs Etat et Commentaire remontent de CABLAGE comme les autres.
        r = ajouter_ports(f, sw, cfg_de_switch[sw.nom], cab, dernier_cab,
                          hab, r)
    mef_suivi(f, hab, F.CHG, 2)
    fin = len(f.lignes)
    cfg, nv = F.CHG["Config"], F.CHG["New Config"]
    # Bloc introuvable dans la feuille de config : en rouge.
    f.mef.append(("%s2:%s%d" % (cfg, cfg, fin), hab.dxf_alerte,
                  '$%s2="interface introuvable"' % cfg))
    # New Config differente de Config : ce que le transfert changera.
    f.mef.append(("%s2:%s%d" % (nv, nv, fin), hab.dxf_modifie,
                  'AND($%s2<>"",$%s2<>$%s2)' % (nv, nv, cfg)))
    return f


def anc_prise(interface, style):
    """Cellule « Anc. Prise » d'une interface (vide si pas de prise)."""
    p = interface.prise if interface else None
    if p is None or p == "":
        return vide(style)
    return num(p, style) if isinstance(p, int) else txt(p, style)


def ajouter_ports(f, sw, nom_cfg, cab, dernier_cab, hab, r=1):
    """Ajoute a `f` une ligne par port de `sw`, a la suite de la ligne `r`.

    Renvoie le numero de la derniere ligne ecrite.
    """
    st = lambda gen: hab.chg_donnee[F.CHG_ENTETES[gen - 1]]
    ports = ports_du_switch(sw)
    blocs = {it.abrege: it.lignes for it in sw.interfaces}
    interfaces = {it.abrege: it for it in sw.interfaces}
    nlig = max(len(sw.lignes), 1)
    champs = F.champs_chg(cab, dernier_cab, nom_cfg, nlig)
    for port in ports:
        r += 1
        p = sw.poe.get(port)
        interface = interfaces.get(port)
        description = interface.description if interface else None
        # Toutes les cellules sont ecrites, meme vides, pour porter la bordure
        # de leur style (un switch sans PoE laisserait Admin, POE et Device
        # sans quadrillage).
        f.ajouter([txt(sw.nom, st(1)),
                   txt(port, st(2)),
                   txt(p["admin"], st(3)) if p else vide(st(3)),
                   # Anc. Prise : lue par le script, comme dans CABLAGE
                   # (la formule d'origine ne gardait que les chiffres :
                   # « P06B » donnait 6, « P0411  2ieme » donnait 4112).
                   anc_prise(interface, st(4)),
                   # Toujours une valeur, jamais une cellule vide : la formule
                   # POE de CABLAGE fait un INDEX ici, et INDEX sur une cellule
                   # vide renvoie 0 -- d'ou des « 0 » a la place de NON-POE
                   # pour les switchs sans donnees PoE. etat_poe(None) rend
                   # NON-POE, ce qui est la consigne juste : pas de jus releve,
                   # donc pas de PoE a prevoir.
                   txt(analyse.etat_poe(p, description), st(5)),
                   txt(p["device"], st(6)) if p else vide(st(6)),
                   form(F.CHG_J.format(r=r, **champs), array=True, style=st(7)),
                   form(F.CHG_K.format(r=r, **champs), array=True, style=st(8)),
                   # « Local » : Nouv. Locale de CABLAGE (n'etait pas relie).
                   form(F.CHG_I.format(r=r, **champs), array=True, style=st(9)),
                   form(F.CHG_M.format(r=r, **champs), array=True, style=st(10)),
                   # « Description override » : saisie manuelle, conservee
                   # par --force (voir restaurer_changements).
                   vide(st(11)),
                   form(F.CHG_N.format(r=r, **champs), array=True, style=st(12)),
                   form(F.CHG_O.format(r=r, **champs), array=True, style=st(13)),
                   form(F.CHG_P.format(r=r, **champs), array=True, style=st(14))],
                  hauteur=hauteur_bloc(blocs.get(port)))
    return r


RAPPEL_COPIE = ("Pour copier SANS guillemets : sélectionner les lignes d'une "
                "section, de « configure terminal » à « end », Ctrl+C, puis "
                "coller dans la session SSH du switch. Seules les lignes « %s » et "
                "« %s » sont listées.")


def feuille_copie(nom, switchs, chg_de_switch, hab, style_mono):
    """Feuille « Config à copier » : une section par switch, une ligne de
    config par cellule (voir formules.COPIE)."""
    cols = ('<cols><col min="1" max="1" width="95" customWidth="1" '
            'style="%d"/></cols>' % style_mono)
    f = Feuille(nom, cols_xml=cols, autofiltre=False,
                couleur_onglet="FF7030A0")
    f.lignes_figees = 2
    f.quadrillage = False
    f.ajouter([txt(RAPPEL_COPIE % (ETAT_COPIE, ETAT_DESACTIVER),
                   hab.imp_rappel)], hauteur="30")
    f.ajouter([txt("Config à pousser — lignes « %s » et « %s »"
                   % (ETAT_COPIE, ETAT_DESACTIVER),
                   hab.imp_entete["Nouv. Switch"])], hauteur="22")
    nom_chg = chg_de_switch[switchs[0].nom][0] if switchs else ""
    derniere = max((fin for _, _, fin in chg_de_switch.values()), default=2)
    f.ajouter([form(F.formule_copie(nom_chg, derniere, ETAT_COPIE,
                                    ETAT_DESACTIVER),
                    array=True, style=style_mono)])
    # Titres de section (« !===== switch ===== ») en bandeau.
    # Colonne entiere (A3 a la derniere ligne Excel) : la sortie deborde sur
    # un nombre de lignes inconnu ici, et une MEF n'est evaluee que sur les
    # cellules affichees. L'ancienne borne A20000 laissait sans couleur la
    # fin d'un gros projet.
    f.mef.append(("A3:A1048576", hab.dxf_section, 'LEFT($A3,6)="!====="'))
    f.mef.append(("A3:A1048576", hab.dxf_cmd,
                  'OR($A3="configure terminal",$A3="end")'))
    return f


def feuille_config(sw, nom_cfg, style_mono):
    """Config brute : une ligne du .txt par cellule de la colonne A."""
    f = Feuille(nom_cfg, cols=[(1, 1, "110", False)], fige_entete=False,
                autofiltre=False, couleur_onglet="FFD9D9D9")
    for l in sw.lignes:
        # Seule retouche : les espaces de fin d'une ligne « interface X ».
        # analyse.RE_INTERFACE les tolere, mais CHG_J fait un MATCH exact sur
        # « interface X » : avec l'espace, Python trouvait le port et Excel
        # affichait « interface introuvable ». Indentation et « ! » intacts.
        if analyse.RE_INTERFACE.match(l):
            l = l.rstrip()
        f.ajouter([txt(l, style_mono)] if l else [])
    return f


RAPPEL_IMPRESSION = ("⚠ AVANT D'IMPRIMER : Données > Réappliquer (Ctrl+Alt+L). "
                     "Si un local n'a plus aucune ligne « %s », relancez le "
                     "script (--force) pour éviter une page vide. "
                     "Cette ligne ne s'imprime pas.")
COL_AIDE = "Imprimer ?"          # colonne de filtre, hors zone d'impression


def feuille_impression(nom, f_cab, cab, hab, nom_projet):
    """Feuille « IMPRESSION » : CABLAGE ligne pour ligne, filtree sur « À faire ».

    La ligne r d'IMPRESSION reprend la ligne r de CABLAGE (memes bandeaux
    « Local technique », meme section hors gabarit, memes sauts de page) :
    chaque local technique commence donc une nouvelle page. Toutes les
    cellules sont des formules vers CABLAGE ; rien n'est recopie.

    La colonne « Imprimer ? » (OUI/NON, hors zone d'impression) porte le
    filtre automatique. Un bandeau dit OUI si au moins une ligne de son
    groupe est « À faire », sinon il disparait avec son groupe. Excel ne
    rejoue pas un filtre tout seul : la ligne 1 (non imprimee) le rappelle.
    """
    assert ETAT_IMPRESSION in ETATS
    n_imp = len(F.IMP_COLONNES)
    aide = xlsx.col_lettre(n_imp + 1)
    der_imp = xlsx.col_lettre(n_imp)
    larg = [(i, i, str(IMP_LARGEURS[c]), False)
            for i, c in enumerate(F.IMP_COLONNES, 1)]
    f = Feuille(nom, cols=larg + [(n_imp + 1, n_imp + 1, "11", False)],
                sheetpr_xml='<sheetPr><tabColor rgb="FFC65911"/>'
                            '<pageSetUpPr fitToPage="1"/></sheetPr>',
                autofiltre=False,
                queue_xml=MISE_EN_PAGE_IMP + (
                    '<headerFooter><oddHeader>&amp;L&amp;14&amp;B%s&amp;B&amp;10 — lignes '
                    '« %s »&amp;RImprimé le &amp;D</oddHeader><oddFooter>'
                    '&amp;CPage &amp;P / &amp;N</oddFooter></headerFooter>'
                    % (xlsx.esc(re.sub(r"[&<>]", "", nom_projet)),
                       ETAT_IMPRESSION)))
    f.lignes_figees = 2
    # Ligne 1 : le rappel. Hors zone d'impression, donc jamais imprime.
    f.ajouter([txt(RAPPEL_IMPRESSION % ETAT_IMPRESSION, hab.imp_rappel)]
              + [vide(hab.imp_rappel)] * n_imp, hauteur="24")
    # Ligne 2 : en-tetes (repetes en haut de chaque page).
    f.ajouter([txt(F.IMP_TITRES[c], hab.imp_entete[c]) for c in F.IMP_COLONNES]
              + [txt(COL_AIDE, hab.imp_entete["Commentaire"])], hauteur="30")
    f.quadrillage = False

    ref = lambda col, r: "'%s'!$%s$%d" % (cab, col, r)
    c_etat = F.CAB["État"]
    derniere = len(f_cab.lignes)
    # Bandeaux de CABLAGE (local technique, hors gabarit) : reperes par leur
    # style, celui que feuille_cablage leur donne.
    bandeaux = [r for r in range(3, derniere + 1)
                if f_cab.lignes[r - 1] and f_cab.lignes[r - 1][0] is not None
                and f_cab.lignes[r - 1][0].style in (hab.groupe, hab.separateur)]
    f.imp_meta = {}               # ligne -> (ligne CABLAGE, plage d'etats)
    for r in range(3, derniere + 1):
        if r in bandeaux:
            fin = next((b - 1 for b in bandeaux if b > r), derniere)
            style = (hab.imp_bande_hg if f_cab.lignes[r - 1][0].style
                     == hab.separateur else hab.imp_bande)
            # « Local technique C1-3000 · 7 à faire »
            compte = ('COUNTIF(%s:$%s$%d,"%s")'
                      % (ref(c_etat, r + 1) if r < fin else ref(c_etat, r),
                         c_etat, max(fin, r), ETAT_IMPRESSION))
            f.ajouter([form('%s&"   ·   "&%s&" %s"'
                            % (ref(xlsx.col_lettre(1), r), compte, ETAT_IMPRESSION.lower()),
                            style=style)]
                      + [vide(style)] * (n_imp - 1)
                      + [form('IF(COUNTIF(%s:$%s$%d,"%s")>0,"OUI","NON")'
                              % (ref(c_etat, r + 1) if r < fin else ref(c_etat, r),
                                 c_etat, max(fin, r), ETAT_IMPRESSION),
                              style=hab.imp_aide)], hauteur=HAUTEUR_GROUPE)
            f.imp_meta[r] = (r + 1, max(fin, r)) if r < fin else (None, None)
            continue
        cellules = []
        for c in F.IMP_COLONNES:
            cible = ref(F.CAB[c], r)
            cellules.append(form('IF(%s="","",%s)' % (cible, cible),
                                 style=hab.imp_donnee[c]))
        cellules.append(form('IF(%s="%s","OUI","NON")'
                             % (ref(c_etat, r), ETAT_IMPRESSION),
                             style=hab.imp_aide))
        f.ajouter(cellules, hauteur=HAUTEUR_LIGNE_CAB)
        f.imp_meta[r] = (r, r)
    der = len(f.lignes)
    # Une page par local technique -- sauts poses par maj_filtre_impression,
    # devant les seuls locaux qui ont des lignes a imprimer.
    f.imp_sauts = bool(f_cab.sauts)
    f.titres = "$2:$2"
    # La zone demarre SOUS l'en-tete (repete via Print_Titles) : une page dont
    # toutes les lignes sont filtrees ne contient alors plus rien, et n'est
    # pas imprimee -- sinon un local sans « À faire » laissait une page
    # blanche, avec juste les titres.
    f.zone_impression = "$A$3:$%s$%d" % (der_imp, der)
    f.filtre = ("A2:%s%d" % (aide, der), n_imp, ["OUI"])
    # Commentaire en rouge gras pour DOUBLON / HORS GABARIT, comme CABLAGE.
    c_comm = xlsx.col_lettre(F.IMP_COLONNES.index("Commentaire") + 1)
    f.mef.append(("%s3:%s%d" % (c_comm, c_comm, der), hab.dxf_alerte,
                  'OR(LEFT($%s3,%d)="%s",$%s3="%s")'
                  % (c_comm, len(MARQUE_DOUBLON), MARQUE_DOUBLON,
                     c_comm, MARQUE_HG)))
    maj_filtre_impression([f_cab, f])
    return f


def maj_filtre_impression(feuilles):
    """Masque, dans IMPRESSION, les lignes qui ne sont pas « À faire ».

    C'est l'etat initial du filtre a l'ouverture du classeur. Appele a la
    construction, puis de nouveau apres la restauration des saisies (les
    Etats restaures changent ce qu'il faut montrer).
    """
    f_cab = next((f for f in feuilles if f.nom.startswith("CÂBLAGE ")), None)
    f_imp = next((f for f in feuilles if f.nom == NOM_IMPRESSION), None)
    if f_cab is None or f_imp is None:
        return
    i_etat = F.CAB_ENTETES.index("État")

    def etat(r):
        ligne = f_cab.lignes[r - 1] if r - 1 < len(f_cab.lignes) else None
        c = ligne[i_etat] if ligne and len(ligne) > i_etat else None
        return "" if c is None or c.valeur is None else str(c.valeur).strip()

    f_imp.cachees = set()
    for r, (prem, fin) in f_imp.imp_meta.items():
        if prem is None or not any(etat(k) == ETAT_IMPRESSION
                                   for k in range(prem, fin + 1)):
            f_imp.cachees.add(r)

    # Sauts de page. Excel GARDE un saut manuel meme quand le filtre masque
    # tout son groupe, et imprime alors une page vide (seuls les sauts
    # automatiques sont recalcules). On ne pose donc un saut que devant un
    # bandeau visible, et jamais devant le premier : avant lui, tout ce qui
    # precede est masque, ce serait encore une page vide.
    # Limite : l'etat retenu est celui de la generation. Si, apres coup, un
    # local se vide dans Excel, son saut reste -> relancer avec --force.
    f_imp.sauts = []
    if getattr(f_imp, "imp_sauts", False):
        visibles = [r for r, (prem, fin) in sorted(f_imp.imp_meta.items())
                    if prem is not None and prem != r          # bandeaux
                    and r not in f_imp.cachees]
        # brk id = nombre de lignes avant le bandeau (meme convention que
        # feuille_cablage : f.sauts.append(len(f.lignes)) avant le bandeau).
        f_imp.sauts = [r - 1 for r in visibles[1:]]


def sans_ajuster(sheetpr_xml):
    """Retire « Ajuster a la page » (<pageSetUpPr fitToPage="1"/>) du sheetPr.

    Le gabarit le porte sur sa feuille CABLAGE. Combine a MISE_EN_PAGE_CAB,
    qui n'a ni fitToWidth ni fitToHeight (valeur 1 par defaut dans la norme),
    il demandait « toute la feuille sur UNE page » : l'echelle 69 % et les
    sauts de page par local technique etaient ignores.
    """
    return re.sub(r"<pageSetUpPr\b[^>]*/>", "", sheetpr_xml)


def queue_impression(gab, nom_projet):
    """Mise en page de la feuille CABLAGE, en-tete d'impression reecrit.

    Le gabarit porte en dur « Projet Réaménagement Câblage Z7 - Imprimé le
    21 juillet 2026 par MM » : recopie tel quel, chaque projet s'imprimerait
    sous le nom d'un autre. On garde les marges (etroites), on remplace le
    texte de l'en-tete et on impose la mise en page retenue pour
    l'entrepreneur : Lettre US, portrait, echelle 69 %.
    """
    queue = re.sub(r"<pageSetup[^>]*/>", MISE_EN_PAGE_CAB, gab.cablage.queue_xml)
    debut = queue.find("<headerFooter>")
    if debut != -1:
        queue = queue[:debut]
    return queue + gab.entete_impression(nom_projet)


def construire(nom_projet, switchs, reserve, gab, sauts=True):
    noms = Noms()
    cab = noms.attribuer("CÂBLAGE " + nom_projet)
    chg_tous = noms.attribuer(NOM_CHG_TOUS)
    imp = noms.attribuer(NOM_IMPRESSION)
    copie = noms.attribuer(NOM_COPIE)

    # Les noms et plages d'abord : la formule POE de CABLAGE doit connaitre,
    # pour chaque switch, les lignes de Changements qui sont les siennes --
    # (feuille, premiere, derniere), dans l'ordre ou feuille_changements les
    # ecrit.
    chg_de_switch, cfg_de_switch = {}, {}
    r = 1
    for sw in switchs:
        court = nom_court(sw.nom)
        if court != sw.nom:
            # La parenthese est retiree du nom d'onglet, pas de la colonne
            # Switch : l'onglet de config reste court et lisible.
            noms.renommages.append((sw.nom, court))
        n = len(ports_du_switch(sw))
        chg_de_switch[sw.nom] = (chg_tous, r + 1, r + n)
        r += n
        cfg_de_switch[sw.nom] = noms.attribuer(court)

    entrees, doublons, hors_gabarit = lignes_cablage(switchs)
    f_cab, dernier_cab = feuille_cablage(
        cab, entrees, reserve, chg_de_switch, gab.cablage,
        queue_impression(gab, nom_projet), gab.habillage, hors_gabarit, sauts)

    feuilles = [f_cab, feuille_impression(imp, f_cab, cab, gab.habillage,
                                          nom_projet),
                feuille_changements(
        chg_tous, switchs, cfg_de_switch, cab, dernier_cab, gab.changements,
        gab.habillage),
                feuille_copie(copie, switchs, chg_de_switch, gab.habillage,
                              gab.mono)]
    for sw in switchs:
        feuilles.append(feuille_config(sw, cfg_de_switch[sw.nom], gab.mono))
    return feuilles, entrees, doublons, noms, hors_gabarit


# --- Diff --------------------------------------------------------------------

def _cle_cablage(switch, prise):
    """Cle de diff d'une ligne de CABLAGE.

    Une ligne normale s'identifie par son numero de prise seul : c'est la
    prise murale qui est l'identite, quel que soit le switch qui la sert.
    Une ligne hors gabarit n'a pas de numero -- sa colonne « Anc. Prise »
    porte un nom d'interface -- et deux switchs ont tres bien chacun leur
    « Gi1/1/1 » : il faut donc y joindre le switch.
    """
    return (prise,) if prise.replace(".", "").isdigit() else (switch, prise)


def _cle_libre(deja, cle):
    """Cle unique pour le diff quand une prise apparait sur plusieurs lignes.

    Les prises en conflit ont volontairement deux lignes identiques ; sans ca
    elles se confondraient en une seule entree et la disparition de l'une
    passerait inapercue. La numerotation suit l'ordre des lignes, donc elle est
    la meme a la generation et a la relecture.
    """
    if cle not in deja:
        return cle
    n = 2
    while cle + ("#%d" % n,) in deja:
        n += 1
    # Suffixe texte, pas un entier : les cles sont affichees telles quelles
    # par afficher_diff, et « #2 » se lit comme « 2e ligne de cette prise ».
    return cle + ("#%d" % n,)


def resume(feuilles):
    """Empreinte comparable : uniquement les donnees issues des .txt.

    Les colonnes calculees et les colonnes de saisie manuelle sont exclues, de
    sorte qu'un diff signale ce que les .txt ont change -- pas le travail fait
    a la main dans le classeur.
    """
    res = {}
    for f in feuilles:
        if f.nom in SANS_DIFF:
            continue                  # une formule seule : rien a comparer
        if f.nom.startswith("Changements "):
            cle = {}
            for ligne in f.lignes[1:]:
                def val(j):
                    c = ligne[j] if j < len(ligne) else None
                    return "" if c is None or c.valeur is None else str(c.valeur)
                # C Admin, E POE, F Device : les seules colonnes de donnees.
                cle[(val(0), val(1))] = "|".join(val(j) for j in (2, 4, 5))
            res[f.nom] = ("changements", cle)
        elif f.nom.startswith("CÂBLAGE "):
            # Cle sur la PRISE, pas sur le local : une prise dont le local est
            # vide reste une ligne a comparer (sinon elle sort du diff d'un
            # cote et pas de l'autre).
            paires = {}
            for ligne in f.lignes[2:]:
                def val(j):
                    c = ligne[j] if ligne and len(ligne) > j else None
                    return "" if c is None or c.valeur is None else str(c.valeur)
                if not val(1):
                    continue          # ligne de reserve ou separateur
                paires[_cle_libre(paires, _cle_cablage(val(0), val(1)))] = val(2)
            res[f.nom] = ("cablage", paires)
        else:
            res[f.nom] = ("config", "\n".join(
                l[0].valeur if l else "" for l in f.lignes))
    return res


SAISIES_MANUELLES = ("Nouv. Prise", "Nouv. Switch", "Nouv. Interface",
                    "Nouv. Locale", "VOCATION", "État", "Commentaire")


def restaurer_saisies_manuelles(chemin, feuilles):
    """Reinjecte les saisies par la cle stable Anc. Switch + Interface."""
    donnees = xlsx.lire(chemin)
    ancien_nom = next((n for n in donnees if n.startswith("CÂBLAGE ")), None)
    nouveau = next((f for f in feuilles if f.nom.startswith("CÂBLAGE ")), None)
    if not ancien_nom or nouveau is None:
        return 0, 0
    cel = donnees[ancien_nom]
    entetes = {str(v).strip(): col for (lig, col), v in cel.items()
               if lig == 1 and v not in (None, "")}
    if "Anc. Switch" not in entetes or "Interface" not in entetes:
        return 0, 0
    ancien = {}
    fin = max((lig for lig, _ in cel), default=1)
    for lig in range(2, fin + 1):
        cle = tuple(str(cel.get((lig, entetes[e]), "") or "").strip()
                    for e in ("Anc. Switch", "Interface"))
        if not all(cle):
            continue
        vals = {e: cel.get((lig, entetes[e]), "") for e in SAISIES_MANUELLES
                if e in entetes and cel.get((lig, entetes[e]), "") not in (None, "")}
        if vals:
            ancien[cle] = vals
    idx = {e: F.CAB_ENTETES.index(e) for e in F.CAB_ENTETES}
    lignes = cellules = 0
    for ligne in nouveau.lignes[1:]:
        if not ligne or len(ligne) < len(F.CAB_ENTETES):
            continue
        cle = tuple("" if ligne[idx[e]].valeur is None else str(ligne[idx[e]].valeur).strip()
                    for e in ("Anc. Switch", "Interface"))
        vals = ancien.get(cle)
        if not vals:
            continue
        lignes += 1
        for e, v in vals.items():
            i, style = idx[e], ligne[idx[e]].style
            if e == "Commentaire":
                texte = str(v).strip()
                if texte.startswith(MARQUE_DOUBLON) or texte == MARQUE_HG:
                    continue
            if e == "Nouv. Prise":
                try:
                    ligne[i] = num(int(float(str(v).strip())), style)
                except ValueError:
                    ligne[i] = txt(v, style)
            else:
                ligne[i] = txt(v, style)
            cellules += 1
    l2, c2 = restaurer_changements(donnees, feuilles)
    return lignes + l2, cellules + c2


SAISIES_CHANGEMENTS = ("Description override",)


def restaurer_changements(donnees, feuilles):
    """Reinjecte les saisies de « Changements » par la cle Switch + Interface.

    Seules les colonnes de SAISIES_CHANGEMENTS sont concernees : le reste de
    la feuille est calcule (formules) ou relu dans les .txt.
    """
    ancien_nom = next((n for n in donnees if n.startswith("Changements ")), None)
    nouveau = next((f for f in feuilles if f.nom.startswith("Changements ")),
                   None)
    if not ancien_nom or nouveau is None:
        return 0, 0
    cel = donnees[ancien_nom]
    entetes = {str(v).strip(): col for (lig, col), v in cel.items()
               if lig == 1 and v not in (None, "")}
    if "Switch" not in entetes or "Interface" not in entetes:
        return 0, 0
    a_reprendre = [e for e in SAISIES_CHANGEMENTS if e in entetes]
    if not a_reprendre:
        return 0, 0          # classeur produit avant l'ajout de la colonne
    ancien = {}
    fin = max((lig for lig, _ in cel), default=1)
    for lig in range(2, fin + 1):
        cle = tuple(str(cel.get((lig, entetes[e]), "") or "").strip()
                    for e in ("Switch", "Interface"))
        vals = {e: cel[(lig, entetes[e])] for e in a_reprendre
                if cel.get((lig, entetes[e])) not in (None, "")}
        if all(cle) and vals:
            ancien[cle] = vals
    idx = {e: F.CHG_ENTETES.index(e) for e in F.CHG_ENTETES}
    lignes = cellules = 0
    for ligne in nouveau.lignes[1:]:
        if not ligne or len(ligne) < len(F.CHG_ENTETES):
            continue
        cle = tuple("" if ligne[idx[e]].valeur is None
                    else str(ligne[idx[e]].valeur).strip()
                    for e in ("Switch", "Interface"))
        vals = ancien.get(cle)
        if not vals:
            continue
        lignes += 1
        for e, v in vals.items():
            ligne[idx[e]] = txt(v, ligne[idx[e]].style)
            cellules += 1
    return lignes, cellules


def resume_existant(chemin):
    donnees = xlsx.lire(chemin)
    res = {}
    for nom, cel in donnees.items():
        if nom in SANS_DIFF:
            continue
        if nom.startswith("Changements "):
            lignes, n = {}, 2
            while (n, "A") in cel or (n, "B") in cel:
                g = lambda c: cel.get((n, c), "") or ""
                lignes[(g("A"), g("B"))] = "|".join(
                    g(c) for c in ("C", "E", "F"))
                n += 1
            res[nom] = ("changements", lignes)
        elif nom.startswith("CÂBLAGE "):
            paires = {}
            fin = max((k[0] for k in cel), default=0)
            for n in range(3, fin + 1):
                b = cel.get((n, "B"))
                if not b:
                    continue
                a = cel.get((n, "A"), "") or ""
                paires[_cle_libre(paires, _cle_cablage(a, b))] = \
                    cel.get((n, "C"), "") or ""
            res[nom] = ("cablage", paires)
        else:
            fin = max((k[0] for k in cel), default=0)
            res[nom] = ("config", "\n".join(
                cel.get((i, "A"), "") or "" for i in range(1, fin + 1)))
    return res


def _normaliser(bloc):
    """Compare les configs a l'espace de fin et aux lignes vides finales pres."""
    return [l.rstrip() for l in bloc.rstrip().splitlines()]


def afficher_diff(avant, apres):
    """-> True s'il y a une difference."""
    change = False
    for nom in sorted(set(apres) - set(avant)):
        print("  + feuille ajoutee   : %s" % nom)
        change = True
    for nom in sorted(set(avant) - set(apres)):
        print("  - feuille supprimee : %s" % nom)
        change = True
    for nom in sorted(set(avant) & set(apres)):
        genre, neuf = apres[nom]
        _, vieux = avant[nom]
        if genre == "config":
            if _normaliser(neuf) != _normaliser(vieux):
                print("  ~ %s : config modifiee (%d -> %d lignes)"
                      % (nom, len(_normaliser(vieux)), len(_normaliser(neuf))))
                change = True
        else:
            ajouts = sorted(set(neuf) - set(vieux))
            retraits = sorted(set(vieux) - set(neuf))
            modifs = [k for k in set(neuf) & set(vieux) if neuf[k] != vieux[k]]
            if ajouts or retraits or modifs:
                change = True
                print("  ~ %s : +%d ligne(s), -%d, %d modifiee(s)"
                      % (nom, len(ajouts), len(retraits), len(modifs)))
                for k in (ajouts[:5] + retraits[:5]):
                    print("      %s %s" % ("+" if k in neuf else "-",
                                           " ".join(str(x) for x in k if x)))
                for k in modifs[:5]:
                    print("      ~ %s : %s -> %s"
                          % (" ".join(str(x) for x in k if x), vieux[k], neuf[k]))
                reste = (max(0, len(ajouts) - 5) + max(0, len(retraits) - 5)
                         + max(0, len(modifs) - 5))
                if reste:
                    print("      ... et %d autre(s)" % reste)
    return change


# --- Point d'entree ----------------------------------------------------------

def lister_descriptions(switchs):
    """Diagnostic : ce que le script lit reellement dans les configs."""
    print("  switch / interface / description brute -> local | prise")
    for sw in switchs:
        for it in sw.interfaces:
            if not it.physique:
                continue
            if it.description is None:
                continue
            print("    %-24s %-12s %-40r -> %-16s | %s"
                  % (sw.nom, it.abrege, it.description,
                     it.local if it.local is not None else "(non reconnu)",
                     it.prise if it.prise is not None else "-"))


ESSAIS_ECRITURE = 5          # tentatives sur un fichier verrouille
PAUSE_ECRITURE = 2.0         # secondes entre deux tentatives


def poser(source, cible):
    """Met le contenu de `source` dans `cible`, en conservant le fichier cible.

    Cible absente : simple renommage. Cible presente : reecriture sur place
    (ouverture r+b, ecriture, troncature), ce qui garde le meme fichier pour
    Windows et pour OneDrive -- donc le meme lien de partage. Reessaie
    ESSAIS_ECRITURE fois avant de lever la derniere erreur.
    """
    if not os.path.exists(cible):
        os.replace(source, cible)
        return
    with open(source, "rb") as f:
        contenu = f.read()
    derniere = None
    for essai in range(ESSAIS_ECRITURE):
        if essai:
            print("    fichier occupe, nouvel essai dans %.0f s (%d/%d)..."
                  % (PAUSE_ECRITURE, essai + 1, ESSAIS_ECRITURE))
            time.sleep(PAUSE_ECRITURE)
        try:
            with open(cible, "r+b") as f:
                f.seek(0)
                f.write(contenu)
                f.truncate()
                f.flush()
                os.fsync(f.fileno())
            return
        except OSError as exc:
            derniere = exc
    raise derniere


def traiter(dossier, racine, args):
    nom_projet, switchs = charger_projet(dossier)
    print("\n=== Projet « %s » ===" % nom_projet)

    feuilles, entrees, doublons, noms, hors_gabarit = construire(
        nom_projet, switchs, args.reserve, args.gabarit,
        not args.sans_sauts_page)
    for sw in switchs:
        n_desc = sum(1 for i in sw.interfaces
                     if i.physique and i.prise is not None)
        print("  %-24s %4d lignes, %3d ports, %3d prise(s) decrite(s), POE : %s"
              % (sw.nom, len(sw.lignes), len(ports_du_switch(sw)), n_desc,
                 "%d ports" % len(sw.poe) if sw.poe
                 else ("aucun (switch sans PoE)" if sw.sans_poe else "-")))
        for a in sw.avertissements:
            print("    ! %s" % a)
    for d in doublons:
        print("    ! %s" % d)
    if doublons:
        print("  ! %d prise(s) en doublon -- toutes les lignes sont "
              "conservees ; la colonne Commentaire nomme l'autre port" % len(doublons))
    for souhaite, retenu in noms.renommages:
        print("    onglet : « %s » -> « %s »" % (souhaite, retenu))

    print("  -> %d feuille(s) : 1 CABLAGE (%d prises) + 1 Changements + "
          "%d config(s)" % (len(feuilles), len(entrees), len(switchs)))

    if hors_gabarit:
        print("  ! %d port(s) decrit(s) sans numero de prise -- listes en fin "
              "de CABLAGE, section « hors gabarit » :" % len(hors_gabarit))
        for sw_hg, it in hors_gabarit[:8]:
            print("      %-28s %-12s %r" % (sw_hg.nom, it.abrege, it.description))
        if len(hors_gabarit) > 8:
            print("      ... et %d autre(s)" % (len(hors_gabarit) - 8))

    douteuses = suspectes(entrees)
    if douteuses:
        print("  ! %d description(s) de port sans local exploitable "
              "(a corriger sur le switch, pas ici) :" % len(douteuses))
        for motif, sw_nom, iface, desc in douteuses[:10]:
            print("      %-28s %-12s %-30r  [%s]"
                  % (sw_nom, iface, desc, motif))
        if len(douteuses) > 10:
            print("      ... et %d autre(s) -- « --descriptions » les liste "
                  "toutes" % (len(douteuses) - 10))

    if args.descriptions:
        lister_descriptions(switchs)

    sortie = args.sortie or os.path.join(
        racine, "Projet_Réaménagement_Câblage_%s.xlsx" % nom_projet)

    if os.path.exists(sortie) and not args.force:
        print("  Le fichier existe deja : %s" % os.path.basename(sortie))
        print("  Differences (rien n'est ecrit -- utiliser --force) :")
        try:
            avant = resume_existant(sortie)
        except Exception as exc:                       # classeur illisible
            print("    (impossible de relire l'existant : %s)" % exc)
            print("    --force le remplacera integralement.")
            return
        if not afficher_diff(avant, resume(feuilles)):
            print("    aucune difference.")
        return

    # Verifier AVANT de sauvegarder : Excel verrouille le fichier qu'il a
    # ouvert, et echouer apres la copie laissait un .bak orphelin derriere.
    def verrouille():
        sys.exit("ERREUR : %s est verrouille (ouvert dans Excel ?).\n"
                 "         Fermez-le puis relancez -- rien n'a ete modifie."
                 % os.path.basename(sortie))

    if os.path.exists(sortie):
        # Deux filets : le test d'ouverture attrape le verrou de partage pose
        # par Excel, le try/except attrape les verrous partiels que ce test
        # laisse passer. Les deux avant la copie, pour ne pas laisser un .bak
        # orphelin derriere une ecriture qui echoue.
        try:
            with open(sortie, "r+b"):
                pass
        except OSError:
            verrouille()
        horo = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        sauvegarde = "%s.%s.bak" % (sortie, horo)
        try:
            shutil.copy2(sortie, sauvegarde)
        except OSError:
            verrouille()
        print("  Sauvegarde : %s" % os.path.basename(sauvegarde))
        try:
            lr, cr = restaurer_saisies_manuelles(sortie, feuilles)
        except Exception as exc:
            sys.exit("ERREUR : restauration des saisies impossible (%s). "
                     "Rien n'a ete remplace." % exc)
        print("  Saisies restaurees : %d ligne(s), %d cellule(s)" % (lr, cr))
        maj_filtre_impression(feuilles)     # les Etats restaures comptent

    # On construit a cote (.tmp), puis on pose le contenu sur la cible.
    #
    # Si la cible existe, on la REECRIT SUR PLACE (meme fichier, octets
    # remplaces) au lieu de la remplacer par renommage (os.replace) :
    #   - le renommage echoue en « [WinError 5] Acces refuse » des que
    #     OneDrive/SharePoint ou Excel garde un handle sur le fichier ;
    #   - surtout, un fichier remplace peut devenir un NOUVEL element pour
    #     OneDrive, et le lien partage avec les collegues ne le suit pas.
    # Reecrit sur place, le fichier garde son identite : le lien reste bon.
    # Un verrou OneDrive est souvent passager : on reessaie quelques fois.
    # En dernier recours seulement, le classeur part sous un nom _NOUVEAU.
    base, ext = os.path.splitext(sortie)
    temporaire = base + ".tmp" + (ext or ".xlsx")
    ecrit = sortie
    try:
        xlsx.ecrire(temporaire, feuilles, args.gabarit.styles_xml,
                    args.gabarit.theme_xml)
        try:
            poser(temporaire, sortie)
        except OSError as exc:
            horo = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
            secours = "%s_NOUVEAU_%s%s" % (base, horo, ext or ".xlsx")
            try:
                os.replace(temporaire, secours)
            except OSError as exc2:
                sys.exit("ERREUR : impossible d'ecrire la cible (%s) ni le "
                         "fichier de secours (%s)" % (exc, exc2))
            ecrit = secours
            print("  ! Ecriture refusee sur l'original (%s)." % exc)
            print("  ! Cause probable : classeur ouvert (chez vous ou chez un "
                  "collegue, Excel en ligne compris).")
            print("  ! Nouveau classeur ecrit a cote : %s"
                  % os.path.basename(secours))
            print("  ! Faites fermer le classeur et relancez avec --force pour "
                  "mettre a jour l'original (et garder le lien partage).")
    finally:
        if os.path.exists(temporaire):
            try:
                os.remove(temporaire)
            except OSError:
                pass
    print("  Ecrit : %s" % ecrit)


def main(argv=None):
    p = argparse.ArgumentParser(
        description="Genere le classeur de reamenagement de cablage a partir "
                    "des configs et des sorties POE d'un projet.")
    p.add_argument("projet", nargs="?",
                   help="dossier projet (defaut : tous ceux contenant des .txt)")
    p.add_argument("--racine", default=os.path.dirname(os.path.abspath(__file__)),
                   help="dossier ou chercher les projets et ecrire le classeur")
    p.add_argument("--force", action="store_true",
                   help="ecrire meme si le classeur existe (l'ancien est sauvegarde)")
    p.add_argument("--sortie", help="chemin du .xlsx a produire")
    p.add_argument("--descriptions", action="store_true",
                   help="diagnostic : liste chaque description lue et ce que le "
                        "script en tire (local | prise)")
    p.add_argument("--reserve", type=int, default=RESERVE_DEFAUT,
                   help="lignes vides ajoutees en fin de feuille CABLAGE "
                        "(defaut %d)" % RESERVE_DEFAUT)
    p.add_argument("--sans-sauts-page", action="store_true",
                   help="impression de CABLAGE : ne pas commencer chaque local "
                        "technique (« Z7-0002 » dans « Z7-0002-9200A ») sur "
                        "une nouvelle page, comme c'est le cas par defaut")
    p.add_argument("--gabarit", default=None,
                   help="classeur dont reprendre la presentation "
                        "(defaut : %s a cote du script)" % GABARIT_DEFAUT)
    args = p.parse_args(argv)

    chemin_gab = args.gabarit or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), GABARIT_DEFAUT)
    if not os.path.isfile(chemin_gab):
        sys.exit("ERREUR : gabarit introuvable : %s\n"
                 "         C'est lui qui fournit polices, couleurs, largeurs "
                 "de colonnes et mise en page." % chemin_gab)
    try:
        args.gabarit = gab_mod.Gabarit(chemin_gab)
    except PermissionError:
        sys.exit("ERREUR : %s est verrouille (ouvert dans Excel ?). Fermez-le "
                 "puis relancez." % os.path.basename(chemin_gab))
    except (ValueError, KeyError, zipfile.BadZipFile) as exc:
        sys.exit("ERREUR : gabarit inutilisable (%s)" % exc)

    racine = os.path.abspath(args.racine)
    if args.projet:
        dossier = args.projet if os.path.isdir(args.projet) \
            else os.path.join(racine, args.projet)
        if not os.path.isdir(dossier):
            sys.exit("ERREUR : dossier projet introuvable : %s" % args.projet)
        dossiers = [dossier]
    else:
        dossiers = trouver_projets(racine)
        if not dossiers:
            sys.exit("Aucun dossier projet trouve dans %s\n"
                     "Un projet = un sous-dossier contenant des .txt de config "
                     "(a sa racine ou dans « Config/»)." % racine)
    if args.sortie and len(dossiers) > 1:
        sys.exit("ERREUR : --sortie ne peut viser qu'un seul projet.")
    for d in dossiers:
        traiter(d, racine, args)


if __name__ == "__main__":
    main()
