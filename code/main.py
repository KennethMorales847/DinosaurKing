from settings import *
from game_data import *
from pytmx.util_pygame import load_pygame
from os.path import join
from random import randint

from sprites import Sprite, AnimatedSprite, MonsterPatchSprite, BorderSprite, CollidableSprite, TransitionSprite
from entities import Player, Character
from groups import AllSprites
from dialog import DialogTree
from monster_index import MonsterIndex
from battle import Battle
from timer import Timer
from evolution import Evolution

from support import *
from monster import Monster

class Game:
    # inicialización general del juego
    def __init__(self):
        pygame.init()
        self.display_surface = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        pygame.display.set_caption('Dinosaur King - Early Alpha')
        self.clock = pygame.time.Clock()
        self.encounter_timer = Timer(2000, func = self.monster_encounter)

        # monstruos del jugador (party/banco)
        self.player_monsters = {
            0: Monster('BabyParasaurolophus', 15),
            1: Monster('BabyCarnotaurus', 13),
            2: Monster('BabyTriceratops', 16),
            3: Monster('Tyrannosaurus', 17),
            4: Monster('BabySpinosaurus', 15),
            5: Monster('BabySaichania', 16)
        }
        for monster in self.player_monsters.values():
            monster.xp += randint(0,monster.level * 100)
        

        # grupos principales de sprites
        self.all_sprites = AllSprites()
        self.collision_sprites = pygame.sprite.Group()
        self.character_sprites = pygame.sprite.Group()
        self.transition_sprites = pygame.sprite.Group()
        self.monster_sprites = pygame.sprite.Group()

        # transición / tintado de pantalla
        self.transition_target = None
        self.tint_surf = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT))
        self.tint_mode = 'untint'
        self.tint_progress = 0
        self.tint_direction = -1
        self.tint_speed = 600

        self.import_assets()
        # cargar mapa inicial 'world' y posicionar jugador en 'house' por defecto
        self.setup(self.tmx_maps['world'], 'house')
        self.audio['overworld'].play(-1)

        # overlays y estado de UI
        self.dialog_tree = None
        self.monster_index = MonsterIndex(self.player_monsters, self.fonts, self.monster_frames)
        self.index_open = False
        self.battle = None
        self.evolution = None

        # overlay de derrota (usado al enviar al hospital)
        self.defeat_overlay = None

        # overlay de intro: espera una tecla o click para desaparecer
        self.intro_overlay = {
            'lines': [
                'Proyecto - Programación II',
                'Dinosaur King - Early Alpha',
                'Presiona una tecla para empezar (Excepto Enter)'
            ],
            'fade_time': 1.0,   # duración del fade-out en segundos después de pulsar
            'alpha': 255,
            'state': 'wait'     # 'wait' -> 'fade' -> None (removido)
        }
        # bloquear al jugador mientras está el intro (seguro si player no existe aún)
        try:
            self.player.block()
        except Exception:
            # el player puede no existir todavía en el constructor; run() lo desbloqueará después del intro
            pass


    def import_assets(self):
        # importar mapas TMX y assets gráficos / audio
        self.tmx_maps = tmx_importer('data', 'maps')

        self.overworld_frames = {
            'water': import_folder('graphics', 'tilesets', 'water'),
            'coast': coast_importer(24, 12,'graphics', 'tilesets', 'coast'),
            'characters': all_character_import('graphics', 'characters')
        }

        self.monster_frames = {
            'icons': import_folder_dict('graphics', 'icons'),
            'monsters': monster_importer(4,2,'graphics', 'monsters'),
            'ui': import_folder_dict('graphics', 'ui'),
            'attacks': attack_importer('graphics', 'attacks')
        }
        self.monster_frames['outlines'] = outline_creator(self.monster_frames['monsters'], 4)

        self.fonts = {
            'dialog': pygame.font.Font(join('graphics', 'fonts', 'PixeloidSans.ttf'), 30),
            'regular': pygame.font.Font(join('graphics', 'fonts', 'PixeloidSans.ttf'), 18),
            'small': pygame.font.Font(join('graphics', 'fonts', 'PixeloidSans.ttf'), 14),
            'bold': pygame.font.Font(join('graphics', 'fonts', 'dogicapixelbold.otf'), 20),
        }
        self.bg_frames = import_folder_dict('graphics', 'backgrounds')
        self.start_animation_frames = import_folder('graphics', 'other', 'star animation')
    
        self.audio = audio_importer('audio')

    def setup(self, tmx_map, player_start_pos):
        # limpiar capas del mapa anterior
        for group in (self.all_sprites, self.collision_sprites, self.transition_sprites, self.character_sprites):
            group.empty()

        # determinar la clave (key) del mapa que estamos cargando (búsqueda inversa)
        self.current_map = None
        for key, m in self.tmx_maps.items():
            if m is tmx_map:
                self.current_map = key
                break

        # dibujar terreno (tiles) para las capas especificadas
        for layer in ['Terrain', 'Terrain Top']:
            for x, y, surf in tmx_map.get_layer_by_name(layer).tiles():
                Sprite((x * TILE_SIZE, y * TILE_SIZE), surf, self.all_sprites, WORLD_LAYERS['bg'])

        # agua (animada)
        for obj in tmx_map.get_layer_by_name('Water'):
            for x in range(int(obj.x), int(obj.x + obj.width), TILE_SIZE):
                for y in range(int(obj.y), int(obj.y + obj.height), TILE_SIZE):
                    AnimatedSprite((x,y), self.overworld_frames['water'], self.all_sprites, WORLD_LAYERS['water'])

        # costa (coast) usando importer especializado
        for obj in tmx_map.get_layer_by_name('Coast'):
            terrain = obj.properties['terrain']
            side = obj.properties['side']
            AnimatedSprite((obj.x, obj.y), self.overworld_frames['coast'][terrain][side], self.all_sprites, WORLD_LAYERS['bg'])
        
        # objetos (colisionables o "top")
        for obj in tmx_map.get_layer_by_name('Objects'):
            if obj.name == 'top':
                Sprite((obj.x, obj.y), obj.image, self.all_sprites, WORLD_LAYERS['top'])
            else:
                CollidableSprite((obj.x, obj.y), obj.image, (self.all_sprites, self.collision_sprites))

        # objetos de transición entre mapas (almacenan target y pos)
        for obj in tmx_map.get_layer_by_name('Transition'):
            TransitionSprite((obj.x, obj.y), (obj.width, obj.height), (obj.properties['target'], obj.properties['pos']), self.transition_sprites)

        # colisiones definidas por objetos rectangulares
        for obj in tmx_map.get_layer_by_name('Collisions'):
            BorderSprite((obj.x, obj.y), pygame.Surface((obj.width, obj.height)), self.collision_sprites)

        # parches de hierba/monstruos
        for obj in tmx_map.get_layer_by_name('Monsters'):
            MonsterPatchSprite((obj.x, obj.y), obj.image, (self.all_sprites, self.monster_sprites), obj.properties['biome'], obj.properties['monsters'], obj.properties['level'])

        # entidades (jugador y NPCs)
        for obj in tmx_map.get_layer_by_name('Entities'):
            # objetos Player tratados especialmente: coincidir por propiedad 'pos'
            if obj.name == 'Player':
                if obj.properties.get('pos') == player_start_pos:
                    self.player = Player(
                        pos = (obj.x, obj.y), 
                        frames = self.overworld_frames['characters']['player'], 
                        groups = self.all_sprites,
                        facing_direction = obj.properties.get('direction', 'down'), 
                        collision_sprites = self.collision_sprites)
                continue

            # objetos no-player: crear Character defensivamente
            props = getattr(obj, 'properties', {}) or {}

            # debe existir character_id en TRAINER_DATA para crear el Character
            char_id = props.get('character_id')
            if not char_id:
                # no todos los objetos en Entities son NPCs; saltar y loggear para debug
                print(f"[setup] Skipping Entities object without character_id at ({obj.x},{obj.y}) on map {getattr(self, 'current_map', '?')}")
                continue

            if char_id not in TRAINER_DATA:
                # referencia inválida en el mapa; avisar y saltar en vez de dar KeyError
                print(f"[setup] Warning: character_id '{char_id}' not defined in TRAINER_DATA; skipping object at ({obj.x},{obj.y}) on map {getattr(self, 'current_map', '?')}")
                continue

            # valores por defecto seguros para propiedades opcionales
            graphic_key = props.get('graphic', None)
            # fallback a frames sensatos preferiblemente no 'player'
            frames_for_graphic = self.overworld_frames['characters'].get(graphic_key) if graphic_key else None
            if not frames_for_graphic:
                for k, v in self.overworld_frames['characters'].items():
                    if k != 'player':
                        frames_for_graphic = v
                        break
                if not frames_for_graphic:
                    frames_for_graphic = self.overworld_frames['characters']['player']

            direction = props.get('direction', 'down')
            radius = int(props.get('radius', 100))
            nurse_flag = (char_id == 'Nurse')

            # crear Character con datos validados (logear errores y continuar)
            try:
                Character(
                    pos = (obj.x, obj.y), 
                    frames = frames_for_graphic, 
                    groups = (self.all_sprites, self.collision_sprites, self.character_sprites),
                    facing_direction = direction,
                    character_data = TRAINER_DATA[char_id],
                    player = getattr(self, 'player', None),
                    create_dialog = self.create_dialog,
                    collision_sprites = self.collision_sprites,
                    radius = radius,
                    nurse = nurse_flag,
                    notice_sound = self.audio.get('notice'))
            except Exception as e:
                print(f"[setup] Error creating Character '{char_id}' at ({obj.x},{obj.y}) on map {getattr(self, 'current_map', '?')}: {e}")
                continue
        # Asegurar que exista un objeto Player en el mapa cargado; si no, crear uno por fallback
        try:
            player_present = hasattr(self, 'player') and self.player in self.all_sprites
        except Exception:
            player_present = False

        if not player_present:
            # buscar cualquier objeto Player en el TMX e instanciarlo
            found_obj = None
            try:
                for obj in tmx_map.get_layer_by_name('Entities'):
                    if obj.name == 'Player':
                        found_obj = obj
                        break
            except Exception:
                found_obj = None

            if found_obj:
                # crear jugador en la ubicación encontrada
                self.player = Player(
                    pos = (found_obj.x, found_obj.y),
                    frames = self.overworld_frames['characters']['player'],
                    groups = self.all_sprites,
                    facing_direction = found_obj.properties.get('direction', 'down'),
                    collision_sprites = self.collision_sprites
                )
            else:
                # fallback: colocar jugador en coordenadas seguras
                self.player = Player(
                    pos = (TILE_SIZE * 2, TILE_SIZE * 2),
                    frames = self.overworld_frames['characters']['player'],
                    groups = self.all_sprites,
                    facing_direction = 'down',
                    collision_sprites = self.collision_sprites
                )

    # sistema de diálogo (entrada del jugador)
    def input(self):
        if not self.dialog_tree and not self.battle:
            keys = pygame.key.get_just_pressed()
            if keys[pygame.K_SPACE]:
                for character in self.character_sprites:
                    if check_connections(100, self.player, character):
                        self.player.block()
                        character.change_facing_direction(self.player.rect.center)
                        self.create_dialog(character)
                        character.can_rotate = False

            if keys[pygame.K_RETURN]:
                # alternar índice de monstruos (abrir / cerrar)
                self.index_open = not self.index_open
                self.player.blocked = not self.player.blocked

    def create_dialog(self, character):
        if not self.dialog_tree:
            self.dialog_tree = DialogTree(character, self.player, self.all_sprites, self.fonts['dialog'], self.end_dialog)

    def end_dialog(self, character):
        self.dialog_tree = None
        if character.nurse:
            for monster in self.player_monsters.values():
                monster.health = monster.get_stat('max_health')
                monster.energy = monster.get_stat('max_energy')

            self.player.unblock()
        elif not character.character_data['defeated']:
            self.audio['overworld'].stop()
            self.audio['battle'].play(-1)
            self.transition_target = Battle(
                player_monsters = self.player_monsters, 
                opponent_monsters = character.monsters, 
                monster_frames = self.monster_frames, 
                bg_surf = self.bg_frames[character.character_data['biome']], 
                fonts = self.fonts, 
                end_battle = self.end_battle,
                character = character, 
                sounds = self.audio)
            self.tint_mode = 'tint'
        else:
            self.player.unblock()
            self.check_evolution()

    # sistema de transiciones (buscar colisiones con TransitionSprite)
    def transition_check(self):
        sprites = [sprite for sprite in self.transition_sprites if sprite.rect.colliderect(self.player.hitbox)]
        if sprites:
            self.player.block()

            # usar la clave del mapa origen como posición de entrada en el mapa destino
            target = sprites[0].target
            target_map = target[0] if isinstance(target, tuple) else target

            origin_pos = getattr(self, 'current_map', None)
            if not origin_pos and isinstance(target, tuple) and len(target) > 1:
                origin_pos = target[1]

            self.transition_target = (target_map, origin_pos)
            self.tint_mode = 'tint'

    def tint_screen(self, dt):
        if self.tint_mode == 'untint':
            self.tint_progress -= self.tint_speed * dt

        if self.tint_mode == 'tint':
            self.tint_progress += self.tint_speed * dt
            if self.tint_progress >= 255:
                if type(self.transition_target) == Battle:
                    self.battle = self.transition_target
                elif self.transition_target == 'level':
                    self.battle = None
                else:
                    self.setup(self.tmx_maps[self.transition_target[0]], self.transition_target[1])
                self.tint_mode = 'untint'
                self.transition_target = None

        self.tint_progress = max(0, min(self.tint_progress, 255))
        self.tint_surf.set_alpha(self.tint_progress)
        self.display_surface.blit(self.tint_surf, (0,0))
    
    def end_battle(self, character):
        # detener música de batalla
        self.audio['battle'].stop()

        # caso 'hospital' (derrota en batalla salvaje)
        if character == 'hospital':
            # limpiar objeto Battle activo para evitar actualización continua
            self.battle = None

            # curar monstruos
            for monster in self.player_monsters.values():
                monster.health = monster.get_stat('max_health')
                monster.energy = monster.get_stat('max_energy')
                monster.initiative = 0

            # programar transición al hospital
            self.transition_target = ('hospital', 'hospital')
            self.tint_mode = 'tint'

            # overlay de derrota
            self.defeat_overlay = {'text': 'You were defeated and rushed to the hospital.', 'timer': 3.5}

            try:
                self.player.unblock()
            except Exception:
                pass

            try:
                self.audio['overworld'].play(-1)
            except Exception:
                pass

            return

        # resto del flujo para peleas de entrenador
        self.transition_target = 'level'
        self.tint_mode = 'tint'
        if character:
            character.character_data['defeated'] = True
            self.create_dialog(character)
        elif not self.evolution:
            self.player.unblock()
            self.check_evolution()

    def check_evolution(self):
        for index, monster in self.player_monsters.items():
            if monster.evolution:
                if monster.level == monster.evolution[1]:
                    self.audio['evolution'].play()
                    self.player.block()
                    self.evolution = Evolution(self.monster_frames['monsters'], monster.name, monster.evolution[0], self.fonts['bold'], self.end_evolution, self.start_animation_frames)
                    self.player_monsters[index] = Monster(monster.evolution[0], monster.level)
        if not self.evolution:
            self.audio['overworld'].play(-1)

    def end_evolution(self):
        self.evolution = None
        self.player.unblock()
        self.audio['evolution'].stop()
        self.audio['overworld'].play(-1)

    # encuentros con monstruos en hierba
    def check_monster(self):
        if [sprite for sprite in self.monster_sprites if sprite.rect.colliderect(self.player.hitbox)] and not self.battle and self.player.direction:
            if not self.encounter_timer.active:
                self.encounter_timer.activate()

    def monster_encounter(self):
        sprites = [sprite for sprite in self.monster_sprites if sprite.rect.colliderect(self.player.hitbox)]
        if sprites and self.player.direction:
            self.encounter_timer.duration = randint(800, 2500)
            self.player.block()
            self.audio['overworld'].stop()
            self.audio['battle'].play(-1)
            self.transition_target = Battle(
                player_monsters = self.player_monsters, 
                opponent_monsters = {index:Monster(monster, sprites[0].level + randint(-3,3)) for index, monster in enumerate(sprites[0].monsters)}, 
                monster_frames = self.monster_frames, 
                bg_surf = self.bg_frames[sprites[0].biome], 
                fonts = self.fonts, 
                end_battle = self.end_battle,
                character = None, 
                sounds = self.audio)
            self.tint_mode = 'tint'

    def run(self):
        while True:
            dt = self.clock.tick() / 1000
            self.display_surface.fill('black')

            # bucle de eventos
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    exit()

                # Mientras el intro esté activo, manejar sólo eventos de intro
                if self.intro_overlay:
                    if event.type == pygame.MOUSEBUTTONDOWN:
                        if self.intro_overlay.get('state') == 'wait':
                            self.intro_overlay['state'] = 'fade'
                    elif event.type == pygame.KEYDOWN:
                        # ignorar Enter para evitar abrir MonsterIndex involuntariamente
                        if event.key not in (pygame.K_RETURN, pygame.K_KP_ENTER) and self.intro_overlay.get('state') == 'wait':
                            self.intro_overlay['state'] = 'fade'
                    continue

            # actualizaciones
            self.encounter_timer.update()
            if not self.intro_overlay:
                self.input()
                self.transition_check()
                self.check_monster()
            else:
                # mientras intro activo, asegurar que jugador esté bloqueado
                try:
                    self.player.block()
                except Exception:
                    pass

            self.all_sprites.update(dt)
            
            # dibujo principal
            self.all_sprites.draw(self.player)
            
            # overlays
            if self.dialog_tree: self.dialog_tree.update()
            if self.index_open:  self.monster_index.update(dt)
            if self.battle:      self.battle.update(dt)
            if self.evolution:   self.evolution.update(dt)

            # overlay de derrota
            if self.defeat_overlay:
                overlay_surf = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
                overlay_surf.fill((0, 0, 0, 150))
                self.display_surface.blit(overlay_surf, (0, 0))

                text = self.fonts['regular'].render(self.defeat_overlay['text'], False, COLORS['white'])
                text_rect = text.get_rect(center = (WINDOW_WIDTH/2, WINDOW_HEIGHT/2))
                self.display_surface.blit(text, text_rect)

                self.defeat_overlay['timer'] -= dt
                if self.defeat_overlay['timer'] <= 0:
                    self.defeat_overlay = None

            # overlay de intro (pantalla negra con texto)
            if self.intro_overlay:
                intro_surf = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT))
                intro_surf.fill((0,0,0))
                alpha = self.intro_overlay.get('alpha', 255)
                intro_surf.set_alpha(int(max(0, min(255, alpha))))
                self.display_surface.blit(intro_surf, (0,0))

                lines = self.intro_overlay['lines']
                title_surf = self.fonts.get('bold', self.fonts['regular']).render(lines[0], False, COLORS['white'])
                sub_surf = self.fonts['regular'].render(lines[1], False, COLORS['white'])
                prompt_surf = self.fonts['small'].render(lines[2], False, COLORS['white'])

                center_x = WINDOW_WIDTH / 2
                center_y = WINDOW_HEIGHT / 2
                title_rect = title_surf.get_rect(center = (center_x, center_y - 28))
                sub_rect = sub_surf.get_rect(center = (center_x, center_y))
                prompt_rect = prompt_surf.get_rect(center = (center_x, center_y + 32))

                self.display_surface.blit(title_surf, title_rect)
                self.display_surface.blit(sub_surf, sub_rect)
                self.display_surface.blit(prompt_surf, prompt_rect)

                # fade del intro cuando se solicita
                if self.intro_overlay['state'] == 'fade':
                    fade_time = max(0.0001, self.intro_overlay.get('fade_time', 1.0))
                    decrement = 255.0 * (dt / fade_time)
                    self.intro_overlay['alpha'] = self.intro_overlay.get('alpha', 255) - decrement
                    if self.intro_overlay['alpha'] <= 0:
                        # fin del intro: eliminar overlay y desbloquear jugador
                        self.intro_overlay = None
                        try:
                            self.player.unblock()
                        except Exception:
                            pass

            self.tint_screen(dt)
            pygame.display.update()

if __name__ == '__main__':
    game = Game()
    game.run()