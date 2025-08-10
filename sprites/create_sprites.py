#!/usr/bin/env python3
import pygame
import os

# Initialiser pygame pour créer des sprites
pygame.init()

# Tailles des sprites
SPRITE_SIZE = 32
SHEET_WIDTH = 8  # 8 directions
SHEET_HEIGHT = 4  # 4 frames d'animation par direction

def create_sprite_sheet(color, name, special_features=None):
    """Crée une spritesheet 8x4 (8 directions x 4 frames)"""
    surface = pygame.Surface((SPRITE_SIZE * SHEET_WIDTH, SPRITE_SIZE * SHEET_HEIGHT))
    surface.fill((0, 0, 0, 0))  # Transparent
    
    for direction in range(SHEET_WIDTH):
        for frame in range(SHEET_HEIGHT):
            x = direction * SPRITE_SIZE
            y = frame * SPRITE_SIZE
            
            # Corps principal
            pygame.draw.circle(surface, color, 
                             (x + SPRITE_SIZE//2, y + SPRITE_SIZE//2), 
                             SPRITE_SIZE//3)
            
            # Animation simple: variation de taille
            size_variation = 2 if frame % 2 == 0 else 0
            pygame.draw.circle(surface, tuple(min(255, c+20) for c in color), 
                             (x + SPRITE_SIZE//2, y + SPRITE_SIZE//2), 
                             SPRITE_SIZE//4 + size_variation)
            
            # Caractéristiques spéciales
            if special_features:
                if 'eyes' in special_features:
                    # Yeux
                    pygame.draw.circle(surface, (255, 255, 255), 
                                     (x + SPRITE_SIZE//2 - 4, y + SPRITE_SIZE//2 - 2), 2)
                    pygame.draw.circle(surface, (255, 255, 255), 
                                     (x + SPRITE_SIZE//2 + 4, y + SPRITE_SIZE//2 - 2), 2)
                    pygame.draw.circle(surface, (0, 0, 0), 
                                     (x + SPRITE_SIZE//2 - 4, y + SPRITE_SIZE//2 - 2), 1)
                    pygame.draw.circle(surface, (0, 0, 0), 
                                     (x + SPRITE_SIZE//2 + 4, y + SPRITE_SIZE//2 - 2), 1)
                
                if 'weapon' in special_features:
                    # Arme simple
                    weapon_color = special_features['weapon']
                    pygame.draw.rect(surface, weapon_color, 
                                   (x + SPRITE_SIZE//2 + 8, y + SPRITE_SIZE//2 - 2, 6, 2))
    
    pygame.image.save(surface, f"sprites/{name}.png")
    print(f"Créé: sprites/{name}.png")

def create_tower_sprite():
    """Crée un sprite de tour"""
    surface = pygame.Surface((SPRITE_SIZE * 2, SPRITE_SIZE * 3))
    surface.fill((0, 0, 0, 0))
    
    # Base de la tour
    pygame.draw.rect(surface, (100, 100, 100), (8, SPRITE_SIZE * 2, SPRITE_SIZE + 16, SPRITE_SIZE))
    # Corps de la tour
    pygame.draw.rect(surface, (120, 120, 120), (12, SPRITE_SIZE, SPRITE_SIZE + 8, SPRITE_SIZE))
    # Sommet de la tour
    pygame.draw.rect(surface, (140, 140, 140), (16, 4, SPRITE_SIZE, SPRITE_SIZE - 4))
    # Porte
    pygame.draw.rect(surface, (60, 30, 0), (20, SPRITE_SIZE * 2 + 8, 12, 16))
    
    pygame.image.save(surface, "sprites/tower.png")
    print("Créé: sprites/tower.png")

def create_village_buildings():
    """Crée des sprites de bâtiments de village"""
    # Maison simple
    surface = pygame.Surface((SPRITE_SIZE * 2, SPRITE_SIZE * 2))
    surface.fill((0, 0, 0, 0))
    
    # Murs
    pygame.draw.rect(surface, (139, 69, 19), (8, 24, 48, 32))
    # Toit
    pygame.draw.polygon(surface, (160, 82, 45), [(8, 24), (32, 8), (56, 24)])
    # Porte
    pygame.draw.rect(surface, (101, 67, 33), (28, 40, 8, 16))
    # Fenêtre
    pygame.draw.rect(surface, (135, 206, 235), (16, 32, 6, 6))
    pygame.draw.rect(surface, (135, 206, 235), (42, 32, 6, 6))
    
    pygame.image.save(surface, "sprites/house.png")
    print("Créé: sprites/house.png")
    
    # Forge
    surface = pygame.Surface((SPRITE_SIZE * 2, SPRITE_SIZE * 2))
    surface.fill((0, 0, 0, 0))
    
    # Murs de forge
    pygame.draw.rect(surface, (105, 105, 105), (8, 24, 48, 32))
    # Toit de métal
    pygame.draw.polygon(surface, (128, 128, 128), [(8, 24), (32, 8), (56, 24)])
    # Porte de forge
    pygame.draw.rect(surface, (64, 64, 64), (28, 40, 8, 16))
    # Cheminée avec fumée
    pygame.draw.rect(surface, (64, 64, 64), (38, 4, 4, 20))
    pygame.draw.circle(surface, (128, 128, 128), (40, 4), 3)
    
    pygame.image.save(surface, "sprites/forge.png")
    print("Créé: sprites/forge.png")

# Créer tous les sprites
os.makedirs("sprites", exist_ok=True)

# Sprites de joueurs (3 classes)
create_sprite_sheet((100, 150, 200), "player_warrior", {'eyes': True, 'weapon': (150, 150, 150)})
create_sprite_sheet((150, 100, 200), "player_mage", {'eyes': True, 'weapon': (200, 150, 100)})
create_sprite_sheet((150, 200, 100), "player_rogue", {'eyes': True, 'weapon': (100, 100, 100)})

# Sprites de monstres
create_sprite_sheet((100, 200, 100), "slime", {'eyes': True})
create_sprite_sheet((150, 100, 50), "goblin", {'eyes': True, 'weapon': (100, 50, 50)})
create_sprite_sheet((120, 80, 40), "orc", {'eyes': True, 'weapon': (80, 80, 80)})
create_sprite_sheet((139, 69, 19), "wolf", {'eyes': True})
create_sprite_sheet((101, 67, 33), "bear", {'eyes': True})
create_sprite_sheet((200, 50, 50), "dragon", {'eyes': True, 'weapon': (255, 100, 100)})

# Sprites de boss
create_sprite_sheet((200, 100, 100), "goblin_chief", {'eyes': True, 'weapon': (200, 200, 100)})
create_sprite_sheet((150, 150, 200), "ice_golem", {'eyes': True})
create_sprite_sheet((255, 100, 100), "fire_demon", {'eyes': True, 'weapon': (255, 150, 150)})

# Sprites de PNJ
create_sprite_sheet((200, 200, 150), "merchant", {'eyes': True})
create_sprite_sheet((150, 200, 200), "alchemist", {'eyes': True})
create_sprite_sheet((100, 150, 150), "quest_giver", {'eyes': True})

# Sprites de bâtiments
create_tower_sprite()
create_village_buildings()

print("Tous les sprites ont été créés avec succès!")