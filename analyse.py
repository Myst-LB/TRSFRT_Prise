# -*- coding: utf-8 -*-
"""Lecture des .txt : `show running-config` et `show power inline`."""
import re

# Correspondance abrege <-> nom long, identique a celle codee dans les formules
# J et N du classeur (XLOOKUP). Toute divergence casse la resolution des blocs.
ABREGES = [
    ("Twe", "TwentyFiveGigE"),   # avant "Tw", sinon "Twe1/0/1" matche "Tw"
    ("Tw", "TwoGigabitEthernet"),
    ("Te", "TenGigabitEthernet"),
    ("Gi", "GigabitEthernet"),
    ("Fa", "FastEthernet"),
    ("Po", "Port-channel"),
    ("Ap", "AppGigabitEthernet"),
    ("Hu", "HundredGigE"),
    # Catalyst 9500 (IOS-XE) : « FortyGigabitEthernet ». L'ancienne forme
    # « FortyGigE » reste reconnue en lecture.
    ("Fo", "FortyGigabitEthernet"),
    ("Fo", "FortyGigE"),
]
LONG2ABR = {long: abr for abr, long in ABREGES}

# Interfaces physiques de brassage : celles qui aboutissent a une prise murale.
# Volontairement sans Port-channel / Vlan / Loopback / Tunnel / AppGigabitEthernet
# (interface interne du conteneur applicatif des Catalyst 9000).
PHYSIQUES = ("GigabitEthernet", "TenGigabitEthernet", "TwoGigabitEthernet",
             "TwentyFiveGigE", "FastEthernet", "HundredGigE",
             "FortyGigabitEthernet", "FortyGigE")

RE_INTERFACE = re.compile(r"^interface\s+(\S+)\s*$")
RE_HOSTNAME = re.compile(r"^hostname\s+(\S.*?)\s*$")
RE_DESCRIPTION = re.compile(r"^\s+description\s+(.*?)\s*$")
RE_TAG_AP = re.compile(r"\(\s*AP\s*\)", re.I)


def est_ap(description):
    """Vrai si la description contient le marqueur metier (AP)."""
    return bool(RE_TAG_AP.search(description or ""))

# Le numero de prise dans la description. Notations relevees sur le parc :
#   Z7-2001_P1234        Z7-2001 P1234        Z7-2001-P1234
#   Z7-2001(P1234)       Z7-2001 (P1234)      _P0089  (local vide)
# et toutes suivies, ou non, d'un commentaire libre :
#   z1-2116-03_P0123 (xxxx)      C1-5015-00_P0197 (max 4)
#   C2-2065-00_P0338 trap enable C1-1101-00_P0411  2ieme
# Les zeros de tete tombent : la colonne « Anc. Prise » est numerique et les
# VLOOKUP en dependent.
#
# On CHERCHE le motif au lieu de l'ancrer en fin de chaine : ancre, tout ce qui
# suivait le numero (un commentaire du technicien) faisait rater la prise et
# expediait le port en « hors gabarit ».
#
# Deux garde-fous, tous deux necessaires :
#
# 1. Le separateur -- espace, souligne, tiret -- ou la parenthese ouvrante
#    avant le P est OBLIGATOIRE. Sans lui, « AIR-AP2802I-A-K9 » donnerait
#    local « AIR-A » + prise 2802, un nom d'equipement pris pour une prise.
#
# 2. Le caractere qui SUIT le P doit etre un chiffre. Toute lettre entre le P
#    et le numero exclut : « PDU20A », « PA20 », « PoE12 », « Panneau3 »...
#    En revanche des lettres APRES le numero sont acceptees et ignorees, car
#    les techniciens y annotent le port (« _P0197 (max 4) », « _P0338 trap
#    enable », « _P0411  2ieme »). C'est `0*(\d+)` qui porte cette regle :
#    apres le P viennent des zeros de tete puis des chiffres.
#
# 3. UNE lettre collee au numero fait partie de la prise : « P06B » -> 6B
#    (prise B du boitier 6). Seulement une lettre isolee : « P0123AP » ou
#    « P0123abc » ne gardent que 123, ce sont des annotations.
#
# 4. On prend TOUT le code colle au P (lettres et chiffres) : « P06B » -> 6B,
#    « P12AB » -> 12AB. Les zeros de tete tombent ; un code purement
#    numerique reste un nombre.
RE_PRISE = re.compile(r"(?:[\s_\-]|\()\s*\(?\s*P0*(\d+)([A-Z0-9]*)", re.I)
# Code qui COMMENCE par une lettre : « _PABCD », « -PXY12 », « (PABC) ».
# Plus strict : separateur _ - ou ( obligatoire juste avant le P (pas une
# espace), sinon un mot du texte libre (« Poste », « PDU20A ») passerait.
RE_PRISE_ALPHA = re.compile(r"(?:[_\-]|\()\s*P([A-Z][A-Z0-9]*)", re.I)
# Texte entre parentheses APRES la prise : « _P0643 (AP) », « (imprimante) ».
# Il part en colonne VOCATION -- c'est l'usage de la prise.
RE_VOCATION = re.compile(r"\(\s*([^()]*?)\s*\)")

# Cas particulier (~20 % du parc) : un local suivi d'un nom entre parentheses,
# SANS numero de prise : « C1-4030-01 (ALPHA) ». Le nom tient lieu de prise.
# Le local : « C1-4030 » ou « C1-4030-01 » (sous-numero de 1 ou 2 chiffres).
# Un nom de switch (« C1-3000-9200B (Julie) ») ne passe pas : son 3e segment
# est trop long, la parenthese n'arrive pas juste apres le local.
# Le mot « Local » peut s'intercaler : « C1-4030-01_Local(ABC) » -> ABC.
# Sans parentheses (« C1-4030-01_Local ») : local connu, prise vide.
RE_LOCAL_SEUL = re.compile(
    r"^\s*([A-Z]\d+-[A-Z0-9]+(?:-\d{1,2})?)\s*[_\-\s]\s*local\b", re.I)
RE_LOCAL_NOM = re.compile(
    r"^\s*([A-Z]\d+-[A-Z0-9]+(?:-\d{1,2})?)\s*[_\-]?\s*(?:local\s*)?"
    r"\(\s*([^()]*?\S)\s*\)", re.I)


def extraire_local_prise(description):
    """« C1-5015-00_P0197 (max 4) » -> ("C1-5015-00", 197, (197, ""), "max 4").

    -> (local, prise, tri, vocation). `prise` est un entier, ou un texte
    quand une lettre suit le numero (« P06B » -> "6B"), ou le texte entre
    parentheses quand le numero est 0 (« P0000 (AP) » -> "AP") ou absent
    (« C1-4030-01 (ALPHA) » -> local "C1-4030-01", prise "ALPHA"). `tri` = (numero,
    lettre) pour ordonner les deux sortes ensemble. `vocation` : le premier
    texte entre parentheses qui suit la prise, ou None.
    (None, None, None, None) si la description ne porte aucun numero de prise.
    """
    m = RE_PRISE.search(description)
    if m:
        n, lettre = int(m.group(1)), (m.group(2) or "").upper()
    else:
        m = RE_PRISE_ALPHA.search(description)
        if m:
            n, lettre = 0, m.group(1).upper()
    if not m:
        m = RE_LOCAL_NOM.match(description)
        if m:
            # Traite comme une prise a zero : pas de numero, le nom identifie.
            return m.group(1), m.group(2), (0, ""), m.group(2)
        m = RE_LOCAL_SEUL.match(description)
        if m:
            # Local sans prise : la ligne reste dans son local technique,
            # Prise vide ("" et non None, qui voudrait dire hors gabarit).
            return m.group(1), "", (0, ""), None
        return None, None, None, None
    if lettre:
        prise = ("%d%s" % (n, lettre)) if n else lettre
    else:
        prise = n
    vocation = next((v.group(1) for v in
                     RE_VOCATION.finditer(description, m.end())
                     if v.group(1)), None)
    # Prise a zero (« _P0000 (AP) ») : pas de vrai numero, c'est le texte entre
    # parentheses qui identifie le port -> il va AUSSI dans Prise.
    if n == 0 and not lettre and vocation:
        prise = vocation
    return (description[:m.start()].strip(" _-("), prise, (n, lettre),
            vocation)


def code_prise(tri):
    """(643, "") -> "P0643" ; (6, "B") -> "P006B" ; (0, "ABCD") -> "PABCD"."""
    n, lettre = tri
    if not lettre:
        return "P%04d" % n
    if len(lettre) == 1:
        return "P%03d%s" % (n, lettre)
    return "P%s%s" % (n or "", lettre)


def abreger(nom):
    """GigabitEthernet1/0/1 -> Gi1/0/1 (format attendu par la formule J)."""
    for long_, abr in sorted(LONG2ABR.items(), key=lambda kv: -len(kv[0])):
        if nom.startswith(long_):
            return abr + nom[len(long_):]
    return nom


class Interface:
    __slots__ = ("nom", "abrege", "lignes", "description", "local", "prise",
                 "prise_tri", "vocation")

    def __init__(self, nom, lignes):
        self.nom = nom
        self.abrege = abreger(nom)
        self.lignes = lignes          # bloc complet, « interface X » inclus
        self.description = None
        self.local = None
        self.prise = None
        self.prise_tri = None         # (numero, lettre), pour trier
        self.vocation = None          # texte entre parentheses apres la prise
        for l in lignes:
            m = RE_DESCRIPTION.match(l)
            if m:
                self.description = m.group(1)
                (self.local, self.prise, self.prise_tri,
                 self.vocation) = extraire_local_prise(self.description)
                break

    @property
    def physique(self):
        return self.nom.startswith(PHYSIQUES)


class Switch:
    def __init__(self, nom, lignes_config):
        self.nom = nom
        self.lignes = lignes_config       # config brute, telle qu'ecrite en col. A
        self.interfaces = []              # [Interface] dans l'ordre du fichier
        self.poe = {}                     # abrege -> dict(admin, power, ...)
        self.sans_poe = False             # tableau POE present mais vide
        self.avertissements = []
        self.hostname = next((m.group(1) for m in
                              (RE_HOSTNAME.match(l) for l in lignes_config) if m),
                             None)
        self._decouper()

    def _decouper(self):
        """Decoupe la config en blocs « interface X ... ! »."""
        courant, nom = None, None
        for l in self.lignes:
            m = RE_INTERFACE.match(l)
            if m:
                if courant is not None:
                    self.interfaces.append(Interface(nom, courant))
                nom, courant = m.group(1), [l]
            elif courant is not None:
                if l.strip() == "!":
                    self.interfaces.append(Interface(nom, courant))
                    courant, nom = None, None
                else:
                    courant.append(l)
        if courant is not None:
            self.interfaces.append(Interface(nom, courant))


def lire_config(chemin):
    """Lit un .txt de config. Ne normalise que les fins de ligne.

    Le reste est laisse strictement intact : la formule J fait un
    MATCH("interface " & ..., plage, 0) exact et cherche le « ! » de fin de
    bloc, donc toucher a l'indentation ou supprimer les « ! » casserait tout.
    """
    with open(chemin, "r", encoding="utf-8", errors="replace") as f:
        brut = f.read()
    if brut.startswith("﻿"):
        brut = brut[1:]
    return [l.rstrip("\r\n") for l in brut.split("\n")]


# --- show power inline -------------------------------------------------------
# Interface Admin  Oper       Power   Device              Class Max
#                             (Watts)
# --------- ------ ---------- ------- ------------------- ----- ----
# Gi1/0/1   auto   off        0.0     n/a                 n/a   30.0
RE_POE = re.compile(
    r"^\s*([A-Za-z]{2,3}\d+(?:/\d+)*)"      # Interface
    r"\s+(auto|off|static|on|never)"        # Admin
    r"\s+(\S+)"                             # Oper
    r"\s+([\d.]+)"                          # Power (Watts)
    r"\s+(.+?)"                             # Device (peut contenir des espaces)
    r"\s+(n/a|\d+(?:\.\d+)?)"               # Class
    r"\s+([\d.]+)\s*$"                      # Max
)


RE_ENTETE_POE = re.compile(r"^\s*Interface\s+Admin\s+Oper\s+Power", re.I)


def lire_poe(chemin):
    """-> ({abrege: {admin, oper, power, device, classe, max}}, entete_vue).

    `entete_vue` distingue les deux facons d'obtenir zero ligne :
      - entete presente, tableau vide  -> le switch n'a tout simplement pas de
        PoE (les 2960/2961/2962 du parc sortent « Module 1 : n/a n/a n/a »),
        c'est normal et il ne faut pas crier au fichier illisible ;
      - pas d'entete du tout           -> le fichier n'est pas un « show power
        inline », la, il y a un vrai probleme.
    """
    res, entete = {}, False
    with open(chemin, "r", encoding="utf-8", errors="replace") as f:
        for ligne in f:
            if RE_ENTETE_POE.match(ligne):
                entete = True
                continue
            m = RE_POE.match(ligne.rstrip())
            if not m:
                continue
            iface, admin, oper, power, device, classe, maxi = m.groups()
            res[iface] = {"admin": admin, "oper": oper, "power": float(power),
                          "device": device.strip(), "classe": classe.strip(),
                          "max": float(maxi)}
    return res, entete


def etat_poe(info, description=None):
    """Colonne POE du classeur : POE si le port debite du courant, sinon NON-POE.

    C'est une CONSIGNE DE BRASSAGE, pas une propriete de la prise. Elle dit au
    technicien sur quel type de port rebrancher : pas de jus sur l'ancien port
    -> pas besoin de PoE sur le nouveau. C'est pour ca que « Power = 0 » donne
    NON-POE meme quand le port est capable de PoE (Max = 30 W) : la question
    n'est pas « ce port supporte-t-il le PoE », mais « faut-il du PoE ici ».

    Ne pas la transformer en trois etats sous pretexte que « Power = 0 » ne
    distingue pas « rien de branche » de « equipement non-PoE » : cette
    distinction n'interesse pas le technicien qui brasse.

    Verification sur le classeur d'origine : « Changements Z7-0002 » suit cette
    regle sur ses 384 lignes sans une exception (260 NON-POE a 0 W, 124 POE au-
    dessus). « Changements Z7-1920 » ne la suit pas du tout -- 98 ports y tirent
    du courant en etant marques NON-POE et 89 ports a 0 W sont marques POE --
    parce que sa colonne a ete remplie a la main avec un autre sens (le besoin
    futur). Elle ne fait donc pas foi ici.
    """
    if not info or info["power"] <= 0:
        return "NON-POE"
    return "POE (AP)" if est_ap(description) else "POE"
