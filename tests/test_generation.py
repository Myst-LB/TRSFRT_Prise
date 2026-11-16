# -*- coding: utf-8 -*-
"""De bout en bout : projet FICTIF -> generer_projet_cablage.py --force -> .xlsx.

Vérifie ce qui est vérifiable sans Excel : le script écrit le classeur, les
feuilles attendues existent dans l'ordre, chaque colonne de CÂBLAGE et de
Changements a une largeur, la colonne POE contient les valeurs de la règle.
Le CALCUL des formules (LET, TEXTSPLIT...) n'est pas vérifiable ici.

Données fictives uniquement (skill donnees-sensibles).
"""
import os
import re
import subprocess
import sys
import tempfile
import unittest
import zipfile

ICI = os.path.dirname(os.path.abspath(__file__))
RACINE_DEPOT = os.path.dirname(ICI)
sys.path.insert(0, RACINE_DEPOT)

import formules as F  # noqa: E402

CONFIG = """﻿hostname LAB-0101-9300A
!
interface GigabitEthernet1/0/1
 description LAB-0101-00_P0001
!
interface GigabitEthernet1/0/2
 description LAB-0101-00_P0002
!
interface GigabitEthernet1/0/3
 description LAB-0101-00_P0003 (AP)
!
interface GigabitEthernet1/0/4
 description LAB-0101-00_P0004
!
interface GigabitEthernet1/0/5
 description Lien vers LAB-0101-9300B
!
interface GigabitEthernet1/0/6   
 description LAB-0101-00_P0006
!
end
"""

POE = """Interface Admin  Oper       Power   Device              Class Max
                            (Watts)
--------- ------ ---------- ------- ------------------- ----- ----
Gi1/0/1   auto   off        0.0     n/a                 n/a   30.0
Gi1/0/2   auto   on         6.5     IP Phone 8845       2     30.0
Gi1/0/3   auto   on         9.2     Ieee PD             3     30.0
Gi1/0/4   auto   on         17.6    Ieee PD             4     30.0
Gi1/0/5   auto   off        0.0     n/a                 n/a   30.0
Gi1/0/6   auto   off        0.0     n/a                 n/a   30.0
"""


def ecrire(chemin, texte):
    os.makedirs(os.path.dirname(chemin), exist_ok=True)
    with open(chemin, "w", encoding="utf-8", newline="\r\n") as f:
        f.write(texte)


class Generation(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(prefix="Changement Câblage ")
        racine = cls._tmp.name
        ecrire(os.path.join(racine, "Labo", "Config", "LAB-0101-9300A.txt"), CONFIG)
        ecrire(os.path.join(racine, "Labo", "POE", "LAB-0101-9300A.txt"), POE)
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
        cls.sortie = subprocess.run(
            [sys.executable, os.path.join(RACINE_DEPOT, "generer_projet_cablage.py"),
             "Labo", "--racine", racine, "--force"],
            capture_output=True, text=True, encoding="utf-8", env=env, timeout=120)
        cls.xlsx = os.path.join(racine, "Projet_Réaménagement_Câblage_Labo.xlsx")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def setUp(self):
        self.assertEqual(self.sortie.returncode, 0, self.sortie.stderr)
        self.assertTrue(os.path.isfile(self.xlsx), self.sortie.stdout)

    def parties(self):
        """{nom de feuille: xml de la feuille}, dans l'ordre du classeur."""
        with zipfile.ZipFile(self.xlsx) as z:
            wb = z.read("xl/workbook.xml").decode("utf-8")
            rels = z.read("xl/_rels/workbook.xml.rels").decode("utf-8")
            cible = dict(re.findall(r'Id="([^"]+)"[^>]*Target="([^"]+)"', rels))
            cible.update({i: t for t, i in
                          re.findall(r'Target="([^"]+)"[^>]*Id="([^"]+)"', rels)})
            res = {}
            for nom, rid in re.findall(r'<sheet [^>]*name="([^"]+)"[^>]*r:id="([^"]+)"', wb):
                part = cible[rid].lstrip("/")
                part = part if part.startswith("xl/") else "xl/" + part
                res[nom.replace("&amp;", "&")] = z.read(part).decode("utf-8")
            return res

    def test_feuilles_dans_l_ordre(self):
        self.assertEqual(list(self.parties()),
                         ["CÂBLAGE Labo", "IMPRESSION", "Changements All Switch",
                          "Config à copier", "LAB-0101-9300A"])

    def largeurs(self, xml):
        cols = set()
        for a, b in re.findall(r'<col min="(\d+)" max="(\d+)" width="[^"]+"', xml):
            cols.update(range(int(a), int(b) + 1))
        return cols

    def test_chaque_colonne_a_une_largeur(self):
        p = self.parties()
        self.assertEqual(self.largeurs(p["CÂBLAGE Labo"]),
                         set(range(1, len(F.CAB_ENTETES) + 1)))
        self.assertEqual(self.largeurs(p["Changements All Switch"]),
                         set(range(1, len(F.CHG_ENTETES) + 1)))

    def test_largeurs_suivent_les_noms_de_colonne(self):
        xml = self.parties()["CÂBLAGE Labo"]
        larg = {int(a): float(w) for a, w in
                re.findall(r'<col min="(\d+)" max="\d+" width="([^"]+)"', xml)}
        pos = {e: i + 1 for i, e in enumerate(F.CAB_ENTETES)}
        self.assertEqual(larg[pos["Anc. Switch"]], 28.0)
        self.assertEqual(larg[pos["Nouv. Switch"]], 28.0)
        self.assertEqual(larg[pos["Commentaire"]], 40.0)

    def test_valeurs_poe(self):
        xml = self.parties()["Changements All Switch"]
        col = F.CHG["POE"]
        valeurs = {}
        for ligne, texte in re.findall(
                r'<c r="%s(\d+)"[^>]*t="inlineStr"[^>]*><is><t[^>]*>([^<]*)</t>' % col, xml):
            valeurs[int(ligne)] = texte
        self.assertEqual([valeurs[i] for i in sorted(valeurs)],
                         ["POE", "NON-POE", "POE", "POE+", "POE+", "NON-POE",
                          "NON-POE"])

    # --- Optimisations de l'audit (2026-11-16), sans changement de structure

    def test_impression_cablage_sans_ajuster_a_la_page(self):
        # A1 : « Ajuster » annulait l'echelle 69 % et les sauts par local.
        xml = self.parties()["CÂBLAGE Labo"]
        self.assertNotIn("fitToPage", xml)
        self.assertIn('scale="69"', xml)

    def test_new_config_ne_vise_que_la_ligne_description(self):
        # A3 : plus de recherche du mot n'importe ou dans la ligne.
        self.assertIn('LEFT(TRIM(_xlpm.lignesInt), 12)="description "', F.CHG_N)
        self.assertNotIn('SEARCH("description"', F.CHG_N)
        self.assertNotIn('SEARCH(" description "', F.CHG_N)

    def test_espaces_de_fin_retires_des_lignes_interface(self):
        # A6 : CHG_J fait un MATCH exact sur « interface X ».
        xml = self.parties()["LAB-0101-9300A"]
        self.assertIn(">interface GigabitEthernet1/0/6<", xml)
        self.assertNotIn("interface GigabitEthernet1/0/6 ", xml)

    def test_mises_en_forme_ajoutees(self):
        # A5
        p = self.parties()
        self.assertIn('=&quot;N/C&quot;', p["CÂBLAGE Labo"])
        self.assertIn('Ne pas faire', p["CÂBLAGE Labo"].split("conditionalFormatting")[1])
        chg = p["Changements All Switch"]
        self.assertIn("interface introuvable", chg)
        cfg, nv = F.CHG["Config"], F.CHG["New Config"]
        self.assertIn("$%s2&lt;&gt;$%s2" % (nv, cfg), chg)
        self.assertIn('sqref="A3:A1048576"', p["Config à copier"])

    def test_controles_de_saisie(self):
        # A4 : avertissement sur Nouv. Interface et Nouv. Prise, aides ailleurs.
        xml = self.parties()["CÂBLAGE Labo"]
        val = re.findall(r'<dataValidation [^>]*sqref="([A-Z]+)3:', xml)
        for nom in ("Nouv. Interface", "Nouv. Prise", "Nouv. Locale",
                    "Nouv. Switch", "État"):
            self.assertIn(F.CAB[nom], val, nom)
        i = F.CAB["Nouv. Interface"]
        self.assertIn('LEFT(%s3,2)=&quot;Gi&quot;' % i, xml)
        self.assertIn('errorStyle="warning"', xml)

    def test_colonnes_figees_jusqu_a_interface(self):
        # A7
        xml = self.parties()["CÂBLAGE Labo"]
        n = F.CAB_ENTETES.index("Interface") + 1
        self.assertIn('<pane xSplit="%d" ySplit="1"' % n, xml)

    def test_hors_gabarit_liste(self):
        self.assertIn("HORS GABARIT", self.parties()["CÂBLAGE Labo"])


if __name__ == "__main__":
    unittest.main()
