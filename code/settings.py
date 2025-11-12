import pygame
from pygame.math import Vector2 as vector 
from sys import exit

# tamaños y constantes principales
WINDOW_WIDTH, WINDOW_HEIGHT = 1280, 720
TILE_SIZE = 64 
ANIMATION_SPEED = 6
BATTLE_OUTLINE_WIDTH = 4

MONSTER_SPRITE_SIZE = (230, 230)

# colores utilizados en la UI y elementos
COLORS = {
    'white': '#f4fefa', 
    'pure white': '#ffffff',
    'dark': '#2b292c',
    'light': '#c8c8c8',
    'gray': '#3a373b',
    'gold': '#ffd700',
    'light-gray': '#4b484d',
    'fire':'#f8a060',
    'water':'#50b0d8',
    'plant': '#64a990', 
    'black': '#000000', 
    'red': '#f03131',
    'blue': '#66d7ee',
    'normal': "#f49fff",
    'dark white': "#e0e0e0"
}

HIGHLIGHT_COLOR = (255, 215, 0)

# capas del mundo (valores numéricos usados para orden de dibujo)
WORLD_LAYERS = {
    'water': 0,
    'bg': 1,
    'shadow': 2,
    'main': 3,
    'top': 4
}

# posiciones de batalla predefinidas para izquierda/derecha
BATTLE_POSITIONS = {
    'left': {'top': (360, 260), 'center': (190, 400), 'bottom': (410, 520)},
    'right': {'top': (900, 260), 'center': (1110, 390), 'bottom': (900, 550)}
}

# capas de batalla para organizar overlay, contornos, etc.
BATTLE_LAYERS =  {
    'outline': 0,
    'name': 1,
    'monster': 2,
    'effects': 3,
    'overlay': 4
}

# opciones disponibles en el menú de batalla
BATTLE_CHOICES = {
    'full': {
        'fight':  {'pos' : vector(30, -60), 'icon': 'sword'},
        'defend': {'pos' : vector(40, -20), 'icon': 'shield'},
        'switch': {'pos' : vector(40, 20), 'icon': 'arrows'},
        'catch':  {'pos' : vector(30, 60), 'icon': 'hand'}},
    
    'limited': {
        'fight':  {'pos' : vector(30, -40), 'icon': 'sword'},
        'defend': {'pos' : vector(40, 0), 'icon': 'shield'},
        'switch': {'pos' : vector(30, 40), 'icon': 'arrows'}}
}