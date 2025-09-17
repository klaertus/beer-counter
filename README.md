# Graphique participatif

## Description
Cette application web permet aux utilisateurs de suivre et de visualiser en temps réel le nombre de verres consommés. Elle propose une interface simple pour incrémenter le nombre de verres et un graphique dynamique qui se met à jour pour refléter les derniers comptages.

## Fonctionnement
- **Page d'Incrémentation (`increment.html`)** : Les utilisateurs peuvent augmenter le compteur de verres en entrant leur nom d'utilisateur et en cliquant sur le bouton '+1'.
- **Page du Graphique (`chart.html`)** : Affiche un graphique en ligne en temps réel qui montre les comptes de verres au fil du temps pour chaque utilisateur.

## Installation et Configuration

### Prérequis
- Un navigateur web moderne avec JavaScript activé.
- Configuration du backend qui supporte les requêtes POST pour l'incrémentation et les requêtes GET pour la récupération des données (non fournie ici).

### Lancement de l'Application
1. Assurez-vous que votre backend de serveur est en fonctionnement et correctement connecté pour servir les fichiers `.html`.
2. Ouvrez `increment.html` pour incrémenter le compteur de verres.
3. Ouvrez `chart.html` pour voir le graphique en direct des comptes de verres.
4. Pour démarrer facilement l'application, double-cliquez sur `run.bat` ou exécutez-le depuis l'invite de commande pour lancer le serveur web localement.

## Fichiers Inclus
- `increment.html` : Page web pour les utilisateurs pour incrémenter le compteur de verres.
- `chart.html` : Page web qui affiche le graphique en direct des comptes de verres.
- `style.css` : Contient les styles CSS pour l'application.
- `increment.css` : Styles spécifiques pour la page d'incrémentation.
- `run.bat` : Script Batch pour lancer facilement le serveur web.

## Informations Complémentaires
- Assurez-vous que les politiques CORS sont correctement configurées pour permettre le partage de ressources si votre backend et votre frontend sont servis depuis des origines différentes.
- Cette application utilise Chart.js pour les graphiques et Axios pour les requêtes HTTP.

## Support
Pour toute aide supplémentaire ou pour signaler des problèmes, veuillez ouvrir un problème dans le dépôt ou contacter l'administrateur.

## Licence
Ce projet est sous licence MIT - voir le fichier LICENSE.md pour les détails.
