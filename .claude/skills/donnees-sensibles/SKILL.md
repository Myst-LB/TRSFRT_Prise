---
name: donnees-sensibles
description: >-
  Règles pour ne jamais exposer de données réelles d'entreprise (journaux, exports CSV, configs d'équipements,
  photos de locaux, secrets) : ce qu'on n'ouvre pas, ce qu'on ne commite pas, les valeurs fictives à utiliser
  (example.org, plages IP de documentation, lab*.lab.example), comment mesurer sans voir (agrégats), et les secrets
  hors de argv et des fichiers. À lire avant de lire un fichier de données, d'écrire une fixture, un exemple de
  doc, un message de commit ou un test, ou de manipuler un mot de passe.
---

# Données sensibles

Les projets réseau manipulent des noms de switches, IP, MAC, comptes, configs et journaux réels. Rien de tout cela
ne doit sortir du poste ni entrer dans un dépôt, une doc, un artifact ou une réponse.

## 1. Ne pas ouvrir

- Les **données de production ne s'ouvrent pas**, même en lecture pour mesurer : journaux suivis (`*.log`),
  exports (`*.csv`, `*.xlsx`), `show running-config`, rapports de diagnostic, fichiers de configuration
  d'accès. Le `CLAUDE.md` du projet liste ses chemins interdits.
- Pour mesurer : un **corpus synthétique** écrit pour l'occasion, `tests/fixtures/`, ou un **instrument** que
  l'utilisateur lance chez lui et qui **n'imprime que des agrégats** (comptes, pourcentages ; aucun nom, port, IP,
  MAC ni compte). L'instrument s'arrête net sur une entrée inattendue plutôt que d'annoncer « 0 % ».
- Photos de locaux techniques, captures d'écran internes : ne pas les demander sans raison ; elles restent sur la
  machine de l'utilisateur.
- Mod associé : `garde-donnees` (dépôt `outils-mods`) refuse la lecture des chemins interdits ; en panne, il refuse.

## 2. Ne pas commiter, ne pas citer

Jamais dans un dépôt, une doc, un commit, une issue, un artifact ou une réponse : nom d'hôte réel, IP, MAC, adresse
de courriel réelle, compte, chemin interne non générique, sortie brute d'un serveur, extrait de journal réel. Si
une donnée réelle a été vue par erreur, n'en citer aucun identifiant.

Les vrais fichiers de configuration (`.ini`, `.env`, `catalyst.env`) restent sur le serveur ou le poste ; le dépôt
porte un `*.exemple` et un `.gitignore` qui exclut les vrais.

## 3. Valeurs fictives à utiliser

| Donnée | Valeur fictive |
| --- | --- |
| Domaine, courriel | `example.org`, `example.com`, `lab.example` ; `noreply@example.org` |
| Hôtes | `lab1-sw01.lab.example`, `labA1-9200a` (préfixe `lab` : impossible à confondre) |
| IPv4 | plages de documentation RFC 5737 : `192.0.2.0/24`, `198.51.100.0/24`, `203.0.113.0/24` |
| IPv6 | `2001:db8::/32` (RFC 3849) |
| MAC | `0011.2233.4455`, `02:00:00:…` (bit « administré localement ») |
| Comptes | `user1001`, `svc-exemple` |
| Chemins | `/backups/...`, `/chemin/distant/logs.log`, `C:\Projet\...` générique |
| Identifiants | `UUID_01`, `AuditSessionID 0000…` |

## 4. Secrets

- Un mot de passe ne touche **jamais** `argv` (visible dans la liste des processus), un fichier d'état, un journal
  ni un dépôt. Il vient du coffre du système (Gestionnaire d'identifiants Windows), d'une variable de processus
  injectée au lancement, ou d'un secret Docker monté en fichier.
- Vérifier l'existence d'un secret sans le décoder (fonction « existe » distincte de « lire ») : décoder à chaque
  frappe recopie le secret en clair en mémoire.
- « Se souvenir de moi » décoché par défaut : un secret conservé doit être choisi.
- Une sortie destinée à l'humain (commande à copier, ticket) ne contient jamais le secret.

## 5. Dans les tests

- Fixtures fictives seulement, avec les valeurs du § 3 ; un test peut vérifier qu'aucune IP hors plages de
  documentation n'apparaît dans `tests/fixtures/`.
- Un test vérifie qu'aucun secret n'atteint `argv`, le fichier d'état ni l'environnement d'un sous-processus.
