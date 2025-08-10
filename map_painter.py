#!/usr/bin/env python3
"""
Map Painter - Outil d'édition de cartes pour le MMO
Usage: python3 map_painter.py
"""

import pygame
import json
import os
import math

# Initialiser pygame
pygame.init()

# Constantes
WINDOW_WIDTH = 1200
WINDOW_HEIGHT = 800
TILE_SIZE = 20
GRID_WIDTH = 50
GRID_HEIGHT = 40

# Types de tiles
TILE_TYPES = {
    0: {"name": "Herbe", "color": (34, 139, 34)},
    1: {"name": "Mur", "color": (105, 105, 105)},
    2: {"name": "Eau", "color": (30, 144, 255)},
    3: {"name": "Sable", "color": (238, 203, 173)},
    4: {"name": "Route", "color": (139, 69, 19)},
    5: {"name": "Plancher", "color": (160, 82, 45)},
}

class MapPainter:
    def __init__(self):
        self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        pygame.display.set_caption("Map Painter - Éditeur de cartes")
        
        self.clock = pygame.time.Clock()
        self.font = pygame.font.Font(None, 24)
        self.big_font = pygame.font.Font(None, 36)
        
        # État de l'éditeur
        self.current_tile = 0
        self.grid = [[0 for _ in range(GRID_WIDTH)] for _ in range(GRID_HEIGHT)]
        self.painting = False
        self.camera_x = 0
        self.camera_y = 0
        
        # Interface
        self.sidebar_width = 200
        self.map_area_x = self.sidebar_width
        self.map_area_width = WINDOW_WIDTH - self.sidebar_width
        
        # Charger une carte existante si disponible
        self.load_map("village_map.json")
    
    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_s and pygame.key.get_pressed()[pygame.K_LCTRL]:
                    self.save_map("village_map.json")
                elif event.key == pygame.K_l and pygame.key.get_pressed()[pygame.K_LCTRL]:
                    self.load_map("village_map.json")
                elif event.key == pygame.K_n and pygame.key.get_pressed()[pygame.K_LCTRL]:
                    self.new_map()
                elif pygame.K_0 <= event.key <= pygame.K_5:
                    self.current_tile = event.key - pygame.K_0
                elif event.key == pygame.K_LEFT:
                    self.camera_x -= TILE_SIZE
                elif event.key == pygame.K_RIGHT:
                    self.camera_x += TILE_SIZE
                elif event.key == pygame.K_UP:
                    self.camera_y -= TILE_SIZE
                elif event.key == pygame.K_DOWN:
                    self.camera_y += TILE_SIZE
            
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:  # Clic gauche
                    self.painting = True
                    self.paint_tile(event.pos)
                elif event.button == 3:  # Clic droit - pipette
                    self.pick_tile(event.pos)
            
            elif event.type == pygame.MOUSEBUTTONUP:
                if event.button == 1:
                    self.painting = False
            
            elif event.type == pygame.MOUSEMOTION:
                if self.painting:
                    self.paint_tile(event.pos)
        
        return True
    
    def paint_tile(self, mouse_pos):
        x, y = mouse_pos
        if x < self.map_area_x:
            return
        
        # Convertir position souris en coordonnées de grille
        map_x = (x - self.map_area_x + self.camera_x) // TILE_SIZE
        map_y = (y + self.camera_y) // TILE_SIZE
        
        if 0 <= map_x < GRID_WIDTH and 0 <= map_y < GRID_HEIGHT:
            self.grid[map_y][map_x] = self.current_tile
    
    def pick_tile(self, mouse_pos):
        x, y = mouse_pos
        if x < self.map_area_x:
            return
        
        # Convertir position souris en coordonnées de grille
        map_x = (x - self.map_area_x + self.camera_x) // TILE_SIZE
        map_y = (y + self.camera_y) // TILE_SIZE
        
        if 0 <= map_x < GRID_WIDTH and 0 <= map_y < GRID_HEIGHT:
            self.current_tile = self.grid[map_y][map_x]
    
    def draw_sidebar(self):
        # Fond de la sidebar
        pygame.draw.rect(self.screen, (40, 40, 40), (0, 0, self.sidebar_width, WINDOW_HEIGHT))
        pygame.draw.line(self.screen, (100, 100, 100), 
                        (self.sidebar_width, 0), (self.sidebar_width, WINDOW_HEIGHT), 2)
        
        # Titre
        title = self.big_font.render("Map Painter", True, (255, 255, 255))
        self.screen.blit(title, (10, 10))
        
        # Palette de tiles
        y_offset = 60
        self.screen.blit(self.font.render("Tiles (0-5):", True, (200, 200, 200)), (10, y_offset))
        
        for tile_id, tile_info in TILE_TYPES.items():
            y_pos = y_offset + 30 + tile_id * 35
            
            # Couleur de fond si sélectionné
            if tile_id == self.current_tile:
                pygame.draw.rect(self.screen, (100, 100, 150), (5, y_pos - 2, 190, 30))
            
            # Échantillon de couleur
            pygame.draw.rect(self.screen, tile_info["color"], (10, y_pos + 2, 25, 25))
            pygame.draw.rect(self.screen, (255, 255, 255), (10, y_pos + 2, 25, 25), 1)
            
            # Nom
            text = self.font.render(f"{tile_id}: {tile_info['name']}", True, (255, 255, 255))
            self.screen.blit(text, (45, y_pos + 5))
        
        # Instructions
        instructions = [
            "",
            "CONTRÔLES:",
            "Clic gauche: Peindre",
            "Clic droit: Pipette",
            "Flèches: Caméra",
            "0-5: Sélectionner tile",
            "",
            "FICHIER:",
            "Ctrl+S: Sauvegarder",
            "Ctrl+L: Charger",
            "Ctrl+N: Nouveau"
        ]
        
        y_start = 300
        for i, instruction in enumerate(instructions):
            color = (255, 255, 255) if instruction.startswith("CTRL") or not instruction else (180, 180, 180)
            text = self.font.render(instruction, True, color)
            self.screen.blit(text, (10, y_start + i * 20))
    
    def draw_grid(self):
        # Zone de carte
        map_rect = pygame.Rect(self.map_area_x, 0, self.map_area_width, WINDOW_HEIGHT)
        pygame.draw.rect(self.screen, (20, 20, 20), map_rect)
        
        # Dessiner les tiles
        for y in range(GRID_HEIGHT):
            for x in range(GRID_WIDTH):
                screen_x = self.map_area_x + x * TILE_SIZE - self.camera_x
                screen_y = y * TILE_SIZE - self.camera_y
                
                # Ne dessiner que les tiles visibles
                if (screen_x + TILE_SIZE >= self.map_area_x and screen_x < WINDOW_WIDTH and
                    screen_y + TILE_SIZE >= 0 and screen_y < WINDOW_HEIGHT):
                    
                    tile_type = self.grid[y][x]
                    color = TILE_TYPES.get(tile_type, {"color": (255, 0, 255)})["color"]
                    
                    tile_rect = pygame.Rect(screen_x, screen_y, TILE_SIZE, TILE_SIZE)
                    pygame.draw.rect(self.screen, color, tile_rect)
                    pygame.draw.rect(self.screen, (100, 100, 100), tile_rect, 1)
        
        # Grille de guidage
        for x in range(0, self.map_area_width + TILE_SIZE, TILE_SIZE):
            screen_x = self.map_area_x + x - (self.camera_x % TILE_SIZE)
            if self.map_area_x <= screen_x < WINDOW_WIDTH:
                pygame.draw.line(self.screen, (60, 60, 60), 
                               (screen_x, 0), (screen_x, WINDOW_HEIGHT))
        
        for y in range(0, WINDOW_HEIGHT + TILE_SIZE, TILE_SIZE):
            screen_y = y - (self.camera_y % TILE_SIZE)
            if 0 <= screen_y < WINDOW_HEIGHT:
                pygame.draw.line(self.screen, (60, 60, 60), 
                               (self.map_area_x, screen_y), (WINDOW_WIDTH, screen_y))
    
    def draw_status(self):
        # Barre de statut en bas
        status_height = 30
        status_rect = pygame.Rect(0, WINDOW_HEIGHT - status_height, WINDOW_WIDTH, status_height)
        pygame.draw.rect(self.screen, (30, 30, 30), status_rect)
        pygame.draw.line(self.screen, (100, 100, 100), 
                        (0, WINDOW_HEIGHT - status_height), (WINDOW_WIDTH, WINDOW_HEIGHT - status_height))
        
        # Informations
        mouse_x, mouse_y = pygame.mouse.get_pos()
        if mouse_x >= self.map_area_x:
            grid_x = (mouse_x - self.map_area_x + self.camera_x) // TILE_SIZE
            grid_y = (mouse_y + self.camera_y) // TILE_SIZE
            status_text = f"Position: ({grid_x}, {grid_y}) | Tile actuel: {self.current_tile} | Caméra: ({self.camera_x//TILE_SIZE}, {self.camera_y//TILE_SIZE})"
        else:
            status_text = f"Tile actuel: {self.current_tile} | Caméra: ({self.camera_x//TILE_SIZE}, {self.camera_y//TILE_SIZE})"
        
        text = self.font.render(status_text, True, (200, 200, 200))
        self.screen.blit(text, (10, WINDOW_HEIGHT - 25))
    
    def save_map(self, filename):
        """Sauvegarde la carte dans un fichier JSON"""
        map_data = {
            "width": GRID_WIDTH,
            "height": GRID_HEIGHT,
            "tiles": self.grid,
            "tile_types": TILE_TYPES
        }
        
        try:
            with open(filename, 'w') as f:
                json.dump(map_data, f, indent=2)
            print(f"Carte sauvegardée: {filename}")
        except Exception as e:
            print(f"Erreur lors de la sauvegarde: {e}")
    
    def load_map(self, filename):
        """Charge une carte depuis un fichier JSON"""
        try:
            if os.path.exists(filename):
                with open(filename, 'r') as f:
                    map_data = json.load(f)
                
                self.grid = map_data.get("tiles", self.grid)
                print(f"Carte chargée: {filename}")
            else:
                print(f"Fichier non trouvé: {filename}")
        except Exception as e:
            print(f"Erreur lors du chargement: {e}")
    
    def new_map(self):
        """Crée une nouvelle carte vide"""
        self.grid = [[0 for _ in range(GRID_WIDTH)] for _ in range(GRID_HEIGHT)]
        self.camera_x = 0
        self.camera_y = 0
        print("Nouvelle carte créée")
    
    def run(self):
        """Boucle principale"""
        running = True
        
        while running:
            running = self.handle_events()
            
            # Rendu
            self.screen.fill((0, 0, 0))
            self.draw_grid()
            self.draw_sidebar()
            self.draw_status()
            
            pygame.display.flip()
            self.clock.tick(60)
        
        pygame.quit()

if __name__ == "__main__":
    painter = MapPainter()
    painter.run()