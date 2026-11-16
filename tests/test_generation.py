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
                         ["POE", "NON-POE", "POE", "POE+", "POE+", "NON-POE"])

    def test_hors_gabarit_liste(self):
        self.assertIn("HORS GABARIT", self.parties()["CÂBLAGE Labo"])


if __name__ == "__main__":
    unittest.main()
