# MMO Python - Version Complète avec Tour et Marchands

## 📝 Description

Jeu MMO 2D en Python avec système de tour à 100 étages, village de départ, marchands, système de quêtes et éditeur de cartes intégré.

## 🚀 Installation et Lancement

### Prérequis
- Python 3.x
- pygame (installé automatiquement)

### Lancement
```bash
# Démarrer le serveur
python3 server_game.py

# Démarrer le client (dans un autre terminal)
python3 client.py

# Lancer l'éditeur de cartes (optionnel)
python3 map_painter.py
```

## 🎮 Nouvelles Fonctionnalités

### 🏰 Village de Départ
- **Village central** placé au spawn (chunk 0,0)
- **Forge** avec le marchand d'armes Thorek
- **Alchimiste** Zelda avec potions et consommables
- **Maître des Quêtes** pour obtenir des missions
- **Tour Mystérieuse** au centre du village

### 💰 Système de Marchands
- **Forgeron Thorek** : Armes, armures, boucliers
- **Alchimiste Zelda** : Potions, consommables, bombes
- Inventaires définis dans `merchants.json`
- Interaction avec la touche **E**

### 🗼 Tour Centrale (100 Étages)
- **100 étages** de difficulté croissante
- **Boss intermédiaires** tous les 5 étages
- **Gros boss** tous les 10 étages
- **Monstres thématiques** par tranches d'étages :
  - 1-20 : Slimes, Gobelins
  - 21-40 : + Loups
  - 41-60 : + Orcs
  - 61-80 : + Ours
  - 81-100 : Dragons, Golems, Démons

### 🎯 Système de Quêtes
- Quêtes définies dans `quests.json`
- **Quêtes de démarrage** dans le village
- **Quêtes de tour** pour les étages
- Progression sauvegardée par joueur

### 👹 Monstres Améliorés
- **Noms et niveaux** affichés au-dessus des mobs
- **Scaling de difficulté** basé sur l'étage
- **Boss spéciaux** avec attaques renforcées
- **Sprites différents** par type de monstre

### 🎨 Sprites et Visuels
- **Spritesheets 8 directions** pour tous les personnages
- **Sprites de monstres** : slime, gobelin, orc, loup, ours, dragon
- **Sprites de boss** : chefs gobelins, golems, démons
- **Sprites de PNJ** : marchands, alchimiste, maître des quêtes
- **Bâtiments** : forge, maisons, tour

### 🛠️ Éditeur de Cartes (Map Painter)
- **Interface graphique** dédiée
- **Palette de tiles** : herbe, mur, eau, sable, route, plancher
- **Contrôles** :
  - Clic gauche : Peindre
  - Clic droit : Pipette
  - Flèches : Déplacer caméra
  - 0-5 : Sélectionner type de tile
  - Ctrl+S : Sauvegarder
  - Ctrl+L : Charger
  - Ctrl+N : Nouvelle carte

## 🎮 Contrôles Modifiés

### Touches Principales
- **ZQSD** : Déplacement
- **E** : Interaction/Ramasser (NPCs, objets, entrées)
- **C** : Créer un personnage (au lieu de N)
- **I** : Inventaire
- **P** : Statistiques
- **M** : Carte
- **1-4** : Sorts de classe
- **Échap** : Fermer dialogues/Options

### Interactions
- **Approchez-vous des NPCs** et appuyez sur **E** pour parler
- **Approchez-vous de la tour** et appuyez sur **E** pour entrer
- **Dialogues interactifs** avec marchands et donneurs de quêtes

## 📁 Structure des Fichiers

```
/workspace/
├── server_game.py          # Serveur principal
├── client.py               # Client du jeu
├── map_painter.py          # Éditeur de cartes
├── merchants.json          # Inventaires des marchands
├── quests.json            # Définitions des quêtes
├── sprites/               # Dossier des sprites
│   ├── player_*.png       # Sprites des joueurs
│   ├── slime.png          # Sprites des monstres
│   ├── goblin.png
│   ├── orc.png
│   ├── wolf.png
│   ├── bear.png
│   ├── dragon.png
│   ├── *_chief.png        # Sprites des boss
│   ├── merchant.png       # Sprites des NPCs
│   ├── alchemist.png
│   ├── quest_giver.png
│   ├── tower.png          # Sprites des bâtiments
│   ├── house.png
│   └── forge.png
├── accounts.json          # Comptes utilisateurs (auto-généré)
├── config.json           # Configuration client (auto-généré)
└── README.md             # Ce fichier
```

## 🎯 Guide de Jeu

### 1. Premiers Pas
1. Créez un compte et un personnage
2. Explorez le village de départ
3. Parlez aux marchands (Forgeron et Alchimiste)
4. Acceptez les premières quêtes du Maître des Quêtes

### 2. Préparation pour la Tour
1. Achetez des équipements chez le Forgeron
2. Stockez des potions chez l'Alchimiste
3. Montez de niveau en combattant les monstres du monde
4. Complétez les quêtes d'introduction

### 3. Exploration de la Tour
1. Approchez-vous de la Tour Mystérieuse
2. Appuyez sur **E** pour entrer dans l'étage 1
3. Combattez les monstres de l'étage
4. Trouvez l'escalier pour monter à l'étage suivant
5. Affrontez les boss tous les 5 étages

### 4. Progression
- Les **monstres deviennent plus forts** à chaque étage
- Les **boss** ont des attaques spéciales
- Les **récompenses** augmentent avec la difficulté
- Retournez au village pour vous réapprovisionner

## 🔧 Configuration

### Modification des Marchands
Éditez `merchants.json` pour changer les inventaires :
```json
{
  "weapon_merchant": {
    "name": "Forgeron Thorek",
    "inventory": [
      {"name": "Épée de fer", "price": 50, "stock": 10}
    ]
  }
}
```

### Modification des Quêtes
Éditez `quests.json` pour ajouter des quêtes :
```json
{
  "starter_quests": [
    {
      "id": "nouvelle_quete",
      "name": "Titre de la quête",
      "description": "Description...",
      "objectives": [...],
      "rewards": {"gold": 100, "xp": 200}
    }
  ]
}
```

## 🐛 Dépannage

### Problèmes Courants
1. **"Module pygame non trouvé"** : Installer avec `sudo apt install python3-pygame`
2. **Sprites manquants** : Exécuter `python3 sprites/create_sprites.py`
3. **Connexion impossible** : Vérifier que le serveur est lancé en premier
4. **Lag** : Réduire le nombre de monstres dans le code

### Logs
- Le serveur affiche les connexions et actions dans la console
- Les erreurs de chargement des fichiers JSON sont affichées

## 🎮 Fonctionnalités Conservées

Toutes les fonctionnalités originales sont conservées :
- **Système de classes** (Guerrier, Mage, Voleur)
- **Sorts et magie** par classe
- **Système d'expérience et de niveau**
- **Inventaire et équipement**
- **Chat multi-joueur**
- **Monde procédural** par chunks
- **Persistance des personnages**
- **Configuration des touches**

Bon jeu ! 🎮