---
name: catalyst-center
description: >-
  Faits vérifiés sur Cisco Catalyst Center (ex-DNA Center), son SDK Python catalystcentersdk et les switches
  IOS-XE qu'il gère : API utiles (templates, aperçu, déploiement, tâches, Command Runner, release), ce qu'un template
  peut et ne peut pas faire, ce qu'il ne faut jamais retirer d'une config, noms d'hôtes en FQDN, comptes, exports
  CSV, lecture d'une prise depuis la description de port. À lire avant d'écrire du code ou un outil qui parle à
  Catalyst Center ou lit ses exports, ou de proposer une config à pousser.
---

# Catalyst Center : faits vérifiés

Rassemblés depuis NetBox-POC, WatchDog et Pannel-DB. Un fait marqué « à vérifier » ne l'a pas été contre un vrai
Catalyst Center. Ne rien inventer au-delà : vérifier dans la doc de la version installée.

## API et SDK

- **`catalystcentersdk` 3.2.x** (versions d'API 2.3.7.x à 3.2.3). Le SDK 3.2.3 utilise par défaut l'API 3.1.6.0 :
  poser la version (`CC_SDK_VERSION` / paramètre `version`) = version du Catalyst Center.
- Version du serveur : `/dna/intent/api/v1/dnac-release` (`cc.release()`) — à vérifier sur le vrai serveur.
- Fonctions utiles : `configuration_templates.get_templates_details`, `preview_template` (rend `cliPreview`,
  `validationErrors`), `deploy_template_v2` (targetInfo `MANAGED_DEVICE_UUID`), `task.get_task_by_id`,
  `command_runner.run_read_only_commands_on_devices`.
- Command Runner : `show running-config` via `/dna/intent/api/v1/network-device-poller/cli/read-request`, attente
  ≈ 30 s au plus.
- Métadonnées d'un template (`templateParams`) : `parameterName`, `dataType`, `required`, `defaultValue`,
  `selection`, `binding`, `notParam` → base d'un formulaire ou d'un script de déploiement générique.
- Authentification utilisateur / mot de passe ; jeton de ≈ 1 h, à mettre en cache et renouveler sur 401.
- Une tâche de déploiement terminée ≠ config forcément appliquée : vérifié une fois sur un cas réel ; sur un échec
  de commande côté switch, interroger `get_template_deployment_status` (à confirmer).
- Ansible : `cisco.dnac` annoncé retiré, successeur `cisco.catalystcenter`.
- Sandbox DevNet en reconstruction (retour visé début 2027) : pas de labo public de secours.

## Templates et configs

- Un template **ne fait qu'ajouter** des lignes. Retirer = `no …` / `default interface …` explicites, idéalement
  calculés (état voulu − état réel).
- **Ne jamais retirer** : AAA, VTY, SSH, la gestion, ni ce que Catalyst Center a posé lui-même (NETCONF, VTY
  `0 4` / `5 15`, discriminateur de logging).
- Catalyst Center impose de remplir **tous** les champs obligatoires d'un template : un template d'interface à
  plusieurs modes oblige à saisir des VLAN pour changer une description. Réponse : une variable de mode + blocs
  `{% if mode == '…' %}`, et un formulaire qui n'affiche que les champs du mode (champs masqués remplis depuis la
  source de vérité).
- Toujours un **aperçu** avant déploiement ; déploiement confirmé par le nom du switch ; suivre la tâche ; journal
  du déploiement.
- Les templates « data » (Jinja de variables par bâtiment) contiennent souvent tous les VLAN du campus : c'est une
  source à lire (`jinja2 … .module`), pas à réécrire à la main.

## Inventaire

- Les hostnames sont souvent en **FQDN** : chercher par IP de gestion, puis hostname, puis `hostname.*`.
- Type d'appareil : `platformId` correspond au `part_number` de la devicetype-library.
- Les stacks sont des appareils uniques à plusieurs membres (interfaces `Gi1/0/x`, `Gi2/0/x`).

## Exports CSV (rapports)

- Le rapport de ports et le rapport Client Detail se fusionnent par interface ; la colonne `MAC Address` change de
  nature selon le rapport (MAC d'interface ou MAC du client) : savoir lequel on lit avant d'afficher.
- `Device Type` du rapport client vaut souvent un **médium** (« Wired ») : le traiter comme vide ; sur un téléphone
  Cisco, seule `OS` (`IP_PHONE`) dit ce qu'est l'appareil.
- Ne jamais écrire dans un export : le relire quand il change, en repérant l'en-tête par son contenu.
- Les exports sont des données sensibles : skill `donnees-sensibles`.

## Prise depuis la description de port

Convention de l'établissement : la description porte le local et la prise (`B6-1045_P0028`, `…_P0101`).
- Garder l'étiquette telle qu'écrite (`P0101`) pour l'affichage ; comparer sur le **numéro normalisé** (sans `#` ni
  zéros de tête). Deux outils qui affichent la même prise doivent l'écrire pareil.
- Refuser les faux amis : modèles d'AP (`AIR-AP2802I-A-K9`), `PDU20A`, `PoE12`, `Panneau3`, chiffres non ASCII.
- Uplinks `_UP` / `_UPLINK`, mais pas `_UPS` ni `_UPDATE`.

## Comptes

- Un compte de service local peut être refusé (401) si l'authentification passe par ISE : à régler avec l'admin
  (local ou ISE, expiration, droits Command Runner et provisioning).
- Le compte de sondage de Catalyst Center ouvre des sessions en boucle sur les switches : l'exclure des
  corrélations « qui était connecté » (nom propre à l'établissement → option, jamais en dur).
