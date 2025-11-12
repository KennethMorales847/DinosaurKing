from settings import * 
from sprites import MonsterSprite, MonsterNameSprite, MonsterLevelSprite, MonsterStatsSprite, MonsterOutlineSprite, AttackSprite, TimedSprite
from groups import BattleSprites
from game_data import ATTACK_DATA
from support import draw_bar
from timer import Timer
from random import choice, random
import pygame

class Battle:
    # principal
    def __init__(self, player_monsters, opponent_monsters, monster_frames, bg_surf, fonts, end_battle, character, sounds):
        # generales
        self.display_surface = pygame.display.get_surface()
        self.bg_surf = bg_surf
        self.monster_frames = monster_frames
        self.fonts = fonts
        self.monster_data = {'player': player_monsters, 'opponent': opponent_monsters}
        self.battle_over = False
        self.end_battle = end_battle
        self.character = character
        self.sounds = sounds

        # temporizadores
        self.timers = {
            'opponent delay': Timer(600, func = self.opponent_attack)
        }

        # grupos de sprites para batalla
        self.battle_sprites   = BattleSprites()
        self.player_sprites   = pygame.sprite.Group()
        self.opponent_sprites = pygame.sprite.Group()

        # control de selección/estado
        self.current_monster = None
        self.selection_mode  = None
        self.selected_attack = None
        self.selection_side  = 'player'
        self.indexes = {
            'general': 0,
            'monster': 0,
            'attacks': 0,
            'switch' : 0,
            'target' : 0,
        }

        # rect del botón "flee" (se define en draw_flee_button)
        self.flee_rect = None

        self.setup()

    def setup(self):
        for entity, monster in self.monster_data.items():
            for index, monster in {k:v for k,v in monster.items() if k <= 2}.items():
                self.create_monster(monster, index, index, entity)

            # eliminar datos de oponentes iniciales (ya están en sprites)
            for i in range(len(self.opponent_sprites)):
                del self.monster_data['opponent'][i]

    def create_monster(self, monster, index, pos_index, entity):
        monster.paused = False
        frames = self.monster_frames['monsters'][monster.name]
        outline_frames = self.monster_frames['outlines'][monster.name]
        if entity == 'player':
            pos = list(BATTLE_POSITIONS['left'].values())[pos_index]
            groups = (self.battle_sprites, self.player_sprites)
            frames = {state: [pygame.transform.flip(frame, True, False) for frame in frames] for state, frames in frames.items()}
            outline_frames = {state: [pygame.transform.flip(frame, True, False) for frame in frames] for state, frames in outline_frames.items()}
        else:
            pos = list(BATTLE_POSITIONS['right'].values())[pos_index]
            groups = (self.battle_sprites, self.opponent_sprites)

        monster_sprite = MonsterSprite(pos, frames, groups, monster, index, pos_index, entity, self.apply_attack, self.create_monster)
        MonsterOutlineSprite(monster_sprite, self.battle_sprites, outline_frames)

        # UI: nombre, nivel, barras
        name_pos = monster_sprite.rect.midleft + vector(16,-70) if entity == 'player' else monster_sprite.rect.midright + vector(-40,-70)
        name_sprite = MonsterNameSprite(name_pos, monster_sprite, self.battle_sprites, self.fonts['regular'])
        level_pos = name_sprite.rect.bottomleft if entity == 'player' else name_sprite.rect.bottomright 
        MonsterLevelSprite(entity, level_pos, monster_sprite, self.battle_sprites, self.fonts['small'])
        MonsterStatsSprite(monster_sprite.rect.midbottom + vector(0,20), monster_sprite, (150,48), self.battle_sprites, self.fonts['small'])

        return monster_sprite

    def input(self):
        if self.selection_mode and self.current_monster:
            keys = pygame.key.get_just_pressed()
            # estado del ratón
            mouse_pressed = pygame.mouse.get_pressed()[0]
            mouse_pos = pygame.mouse.get_pos()

            match self.selection_mode:
                case 'general': limiter = len(BATTLE_CHOICES['full'])
                case 'attacks': limiter = len(self.current_monster.monster.get_abilities(all = False))
                case 'switch': limiter = len(self.available_monsters)
                case 'target': limiter = len(self.opponent_sprites) if self.selection_side == 'opponent' else len(self.player_sprites)

            if keys[pygame.K_DOWN]:
                self.indexes[self.selection_mode] = (self.indexes[self.selection_mode] + 1) % limiter
            if keys[pygame.K_UP]:
                self.indexes[self.selection_mode] = (self.indexes[self.selection_mode] - 1) % limiter

            # Si se presiona F o se hace click en el botón flee mientras está el menú general -> intentar huir
            flee_clicked = mouse_pressed and self.flee_rect and self.flee_rect.collidepoint(mouse_pos)
            if (keys[pygame.K_f] or flee_clicked) and self.selection_mode == 'general':
                self.attempt_flee()
                # resetear índices por seguridad
                self.indexes = {k:0 for k in self.indexes}
                return

            # Manejo de selección con SPACE (o clicks gestionados por UI)
            if keys[pygame.K_SPACE]:
                
                if self.selection_mode == 'switch':
                    index, new_monster = list(self.available_monsters.items())[self.indexes['switch']]
                    self.current_monster.kill()
                    self.create_monster(new_monster, index, self.current_monster.pos_index, 'player')
                    self.selection_mode = None
                    self.update_all_monsters('resume')

                if self.selection_mode == 'target':
                    sprite_group = self.opponent_sprites if self.selection_side == 'opponent' else self.player_sprites
                    sprites = {sprite.pos_index: sprite for sprite in sprite_group}
                    monster_sprite = sprites[list(sprites.keys())[self.indexes['target']]]

                    if self.selected_attack:
                        # ruta normal de ataque
                        self.current_monster.activate_attack(monster_sprite, self.selected_attack)
                        self.selected_attack, self.current_monster, self.selection_mode = None, None, None
                    else:
                        # ruta captura / mover a banco (sin ataque seleccionado)
                        if monster_sprite.monster.health < monster_sprite.monster.get_stat('max_health') * 0.9:
                            # añadir al banco del jugador
                            self.monster_data['player'][len(self.monster_data['player'])] = monster_sprite.monster

                            # eliminar el sprite enemigo inmediatamente (usar destroy para limpieza)
                            try:
                                monster_sprite.destroy()
                            except Exception:
                                # fallback si destroy falla
                                monster_sprite.kill()

                            # resetear estado de selección/UI para evitar menús huérfanos
                            self.current_monster = None
                            self.selection_mode = None
                            self.selected_attack = None
                            self.indexes = {k: 0 for k in self.indexes}

                            # reanudar iniciativa de monstruos
                            self.update_all_monsters('resume')

                            # verificar y terminar batalla si no quedan oponentes
                            if len(self.opponent_sprites) == 0:
                                self.battle_over = True
                                self.end_battle(self.character)
                        else:
                            # captura fallida -> mostrar cruz y reanudar batalla (limpiar UI)
                            TimedSprite(monster_sprite.rect.center, self.monster_frames['ui']['cross'], self.battle_sprites, 1000)

                            # limpiar estado de selección y reanudar
                            self.current_monster = None
                            self.selection_mode = None
                            self.selected_attack = None
                            self.indexes = {k: 0 for k in self.indexes}
                            self.update_all_monsters('resume')

                if self.selection_mode == 'attacks':
                    self.selection_mode = 'target'
                    self.selected_attack = self.current_monster.monster.get_abilities(all = False)[self.indexes['attacks']]
                    self.selection_side = ATTACK_DATA[self.selected_attack]['target']

                if self.selection_mode == 'general':
                    if self.indexes['general'] == 0:
                        self.selection_mode = 'attacks'
                    
                    if self.indexes['general'] == 1:
                        # defender: entra en modo defensa, reanuda y limpia selección
                        self.current_monster.monster.defending = True
                        self.update_all_monsters('resume')
                        self.current_monster, self.selection_mode = None, None
                        self.indexes['general'] = 0
                    
                    if self.indexes['general'] == 2:
                        # cambiar (switch) de monstruo
                        self.selection_mode = 'switch'

                    if self.indexes['general'] == 3:
                        # objetivo / captura (comportamiento original para entrenadores)
                        # (añadimos un botón de huida separado, así que el índice 3 se mantiene)
                        self.selection_mode = 'target'
                        self.selection_side = 'opponent'
                self.indexes = {k: 0 for k in self.indexes}

            if keys[pygame.K_ESCAPE]:
                if self.selection_mode in ('attacks', 'switch', 'target'):
                    self.selection_mode = 'general'

    def update_timers(self):
        for timer in self.timers.values():
            timer.update()


    # sistema de batalla
    def check_active(self):
        for monster_sprite in self.player_sprites.sprites() + self.opponent_sprites.sprites():
            if monster_sprite.monster.initiative >= 100:
                monster_sprite.monster.defending = False
                self.update_all_monsters('pause')
                monster_sprite.monster.initiative = 0
                monster_sprite.set_highlight(True)
                self.current_monster = monster_sprite
                if self.player_sprites in monster_sprite.groups():
                    # monstruo controlado por jugador -> permitir entrada
                    self.selection_mode = 'general'
                else:
                    # monstruo oponente -> desactivar entrada de jugador
                    # limpiar selección para que el jugador no actúe sobre el oponente
                    self.selection_mode = None
                    # resetear índices de selección
                    self.indexes = {k: 0 for k in self.indexes}
                    # dejar que el oponente actúe tras un pequeño retraso
                    self.timers['opponent delay'].activate()

    def update_all_monsters(self, option):
        for monster_sprite in self.player_sprites.sprites() + self.opponent_sprites.sprites():
            monster_sprite.monster.paused = True if option == 'pause' else False

    def apply_attack(self, target_sprite, attack, amount):
        AttackSprite(target_sprite.rect.center, self.monster_frames['attacks'][ATTACK_DATA[attack]['animation']], self.battle_sprites)
        self.sounds[ATTACK_DATA[attack]['animation']].play()

        # calcular daño correcto según defensa y elementos
        attack_element = ATTACK_DATA[attack]['element']
        target_element = target_sprite.monster.element

        # ataque doble (ventaja elemental)
        if attack_element == 'fire'  and target_element == 'plant' or \
           attack_element == 'water' and target_element == 'fire'  or \
           attack_element == 'plant' and target_element == 'water':
            amount *= 2

        # ataque reducido (desventaja elemental)
        if attack_element == 'fire'  and target_element == 'water' or \
           attack_element == 'water' and target_element == 'plant' or \
           attack_element == 'plant' and target_element == 'fire':
            amount *= 0.5

        target_defense = 1 - target_sprite.monster.get_stat('defense') / 2000
        if target_sprite.monster.defending:
            target_defense -= 0.2
        target_defense = max(0, min(1, target_defense))

        # actualizar salud del monstruo objetivo
        target_sprite.monster.health -= amount * target_defense
        self.check_death()

        # reanudar monstruos
        self.update_all_monsters('resume')

    def check_death(self):
        for monster_sprite in self.opponent_sprites.sprites() + self.player_sprites.sprites():
            if monster_sprite.monster.health <= 0:
                # muerte del jugador: elegir reemplazo del banco evitando índices activos
                if self.player_sprites in monster_sprite.groups():  # jugador
                    # crear conjunto de índices activos en batalla
                    active_indices = {sprite.index for sprite in self.player_sprites.sprites()}

                    # encontrar monstruos en banco disponibles (salud > 0 y no activos)
                    available = [(idx, m) for idx, m in self.monster_data['player'].items() if m.health > 0 and idx not in active_indices]

                    if available:
                        # elegir el primero disponible (comportamiento determinista)
                        idx, monster = available[0]
                        new_monster_data = (monster, idx, monster_sprite.pos_index, 'player')
                    else:
                        new_monster_data = None

                # muerte del oponente: tomar el siguiente oponente si existe
                else:
                    if self.monster_data['opponent']:
                        # elegir clave consistente (la menor) y eliminarla del pool
                        pick_key = min(self.monster_data['opponent'].keys())
                        new_opponent = self.monster_data['opponent'][pick_key]
                        del self.monster_data['opponent'][pick_key]
                        new_monster_data = (new_opponent, monster_sprite.index, monster_sprite.pos_index, 'opponent')
                    else:
                        new_monster_data = None

                    # xp: sólo repartir si hay monstruos de jugador vivos
                    if len(self.player_sprites) > 0:
                        xp_amount = monster_sprite.monster.level * 100 / len(self.player_sprites)
                        for player_sprite in self.player_sprites:
                            player_sprite.monster.update_xp(xp_amount)

                monster_sprite.delayed_kill(new_monster_data)

    def opponent_attack(self):
        """
        Opponent AI:
        - choose a usable ability (prefer those the opponent can pay for)
        - map the attack's 'target' (which is defined relative to the player)
          to the actor's actual target side
        - pick the weakest valid target (health ratio) and attack it
        """
        if not self.current_monster:
            return

        # prefer habilidades que el actor puede pagar
        abilities = self.current_monster.monster.get_abilities(all=False)
        if not abilities:
            abilities = self.current_monster.monster.get_abilities(all=True)
        if not abilities:
            return

        ability = choice(abilities)
        declared_target = ATTACK_DATA[ability]['target']  # 'player' or 'opponent' (relativo al jugador)

        # Determinar el lado real objetivo relativo al actor
        # ATTACK_DATA está definido desde la perspectiva del jugador; invertir si el actor es enemigo
        actor_entity = getattr(self.current_monster, 'entity', 'opponent')
        if actor_entity == 'player':
            actual_target = declared_target
        else:
            actual_target = 'player' if declared_target == 'opponent' else 'opponent'

        # candidatos en el lado real objetivo, excluyendo al actor
        if actual_target == 'player':
            candidates = [s for s in self.player_sprites.sprites() if s is not self.current_monster]
        else:
            candidates = [s for s in self.opponent_sprites.sprites() if s is not self.current_monster]

        # fallback: si no hay candidatos en el lado previsto, intentar el otro lado
        if not candidates:
            if actual_target == 'player':
                candidates = [s for s in self.opponent_sprites.sprites() if s is not self.current_monster]
            else:
                candidates = [s for s in self.player_sprites.sprites() if s is not self.current_monster]
        if not candidates:
            return

        # elegir objetivo con menor ratio de salud (más débil relativo)
        def health_ratio(sprite):
            max_hp = sprite.monster.get_stat('max_health')
            return (sprite.monster.health / max_hp) if max_hp > 0 else 1.0

        target = min(candidates, key=health_ratio)

        # ejecutar ataque
        self.current_monster.activate_attack(target, ability)

    def attempt_flee(self):
        """
        Attempt to flee. Works for wild battles (self.character is None).
        On success: end the battle (call end_battle).
        On failure: show a cross and let an opponent attack immediately.
        """
        # Los entrenadores no permiten huir (character no es None)
        if self.character is not None:
            TimedSprite(self.current_monster.rect.center, self.monster_frames['ui']['cross'], self.battle_sprites, 800)
            return

        # Calcular probabilidad de huida en base a velocidad
        player_speed = self.current_monster.monster.get_stat('speed')
        opponent_speeds = [s.monster.get_stat('speed') for s in self.opponent_sprites.sprites()]

        if not opponent_speeds:
            success = True
        else:
            opp_speed = sum(opponent_speeds) / len(opponent_speeds)
            base = 0.5
            diff = (player_speed - opp_speed) / max(1, opp_speed)
            chance = max(0.05, min(0.95, base + diff * 0.25))
            success = random() < chance

        if success:
            # terminar batalla (huida en encuentro salvaje)
            self.battle_over = True
            self.end_battle(self.character)
        else:
            # huida fallida -> mostrar indicador y respuesta inmediata del oponente
            TimedSprite(self.current_monster.rect.center, self.monster_frames['ui']['cross'], self.battle_sprites, 800)
            if len(self.opponent_sprites.sprites()) > 0:
                opponent = choice(self.opponent_sprites.sprites())
                self.current_monster = opponent
                self.opponent_attack()

    def check_end_battle(self):
        # los oponentes han sido derrotados
        if len(self.opponent_sprites) == 0 and not self.battle_over:
            self.battle_over = True
            self.end_battle(self.character)
            for monster in self. monster_data['player'].values():
                monster.initiative = 0

        # el jugador ha sido derrotado
        if len(self.player_sprites) == 0:
            # marcar batalla finalizada y notificar a main: enviar al hospital
            self.battle_over = True
            # llamar main.end_battle con un valor centinela para indicar derrota/hospital
            self.end_battle('hospital')


    # UI
    def draw_ui(self):
        if self.current_monster:
            if self.selection_mode == 'general':
                self.draw_general()
            if self.selection_mode == 'attacks':
                self.draw_attacks()
            if self.selection_mode == 'switch':
                self.draw_switch()

        # dibujar botón huir (visible en encuentros salvajes y menú general abierto)
        self.draw_flee_button()

    def draw_general(self):
        for index, (option, data_dict) in enumerate(BATTLE_CHOICES['full'].items()):
            if index == self.indexes['general']:
                surf = self.monster_frames['ui'][f"{data_dict['icon']}_highlight"]
            else:
                surf = pygame.transform.grayscale(self.monster_frames['ui'][data_dict['icon']])
            rect = surf.get_frect(center = self.current_monster.rect.midright + data_dict['pos'])
            self.display_surface.blit(surf, rect)

    def draw_attacks(self):
        # datos
        abilities = self.current_monster.monster.get_abilities(all = False)
        width, height = 150, 200
        visible_attacks = 4
        item_height = height / visible_attacks
        v_offset = 0 if self.indexes['attacks'] < visible_attacks else -(self.indexes['attacks'] - visible_attacks + 1) * item_height

        # fondo
        bg_rect = pygame.FRect((0,0), (width,height)).move_to(midleft = self.current_monster.rect.midright + vector(20,0))
        pygame.draw.rect(self.display_surface, COLORS['white'], bg_rect, 0, 5)

        for index, ability in enumerate(abilities):
            selected = index == self.indexes['attacks']

            # texto
            if selected:
                element = ATTACK_DATA[ability]['element']
                text_color = COLORS[element] if element!= 'normal' else COLORS['black']
            else:
                text_color = COLORS['light']
            text_surf  = self.fonts['regular'].render(ability, False, text_color)

            # rectángulo
            text_rect = text_surf.get_frect(center = bg_rect.midtop + vector(0, item_height / 2 + index * item_height + v_offset))
            text_bg_rect = pygame.FRect((0,0), (width, item_height)).move_to(center = text_rect.center)

            # dibujo
            if bg_rect.collidepoint(text_rect.center):
                if selected:
                    if text_bg_rect.collidepoint(bg_rect.topleft):
                        pygame.draw.rect(self.display_surface, COLORS['dark white'], text_bg_rect,0,0,5,5)
                    elif text_bg_rect.collidepoint(bg_rect.midbottom + vector(0,-1)):
                        pygame.draw.rect(self.display_surface, COLORS['dark white'], text_bg_rect,0,0,0,0,5,5)
                    else:
                        pygame.draw.rect(self.display_surface, COLORS['dark white'], text_bg_rect)

                self.display_surface.blit(text_surf, text_rect)

    def draw_switch(self):
        # datos para el menú de cambio de monstruos
        width, height = 300, 320
        visible_monsters = 4
        item_height = height / visible_monsters
        v_offset = 0 if self.indexes['switch'] < visible_monsters else -(self.indexes['switch'] - visible_monsters + 1) * item_height
        bg_rect = pygame.FRect((0,0), (width, height)).move_to(midleft = self.current_monster.rect.midright + vector(20,0))
        pygame.draw.rect(self.display_surface, COLORS['white'], bg_rect, 0, 5)

        # mostrar monstruos disponibles en banco
        active_monsters = [(monster_sprite.index, monster_sprite.monster) for monster_sprite in self.player_sprites]
        self.available_monsters = {index: monster for index, monster in self.monster_data['player'].items() if (index, monster) not in active_monsters and monster.health > 0}

        for index, monster in enumerate(self.available_monsters.values()):
            selected = index == self.indexes['switch']
            item_bg_rect = pygame.FRect((0,0), (width, item_height)).move_to(midleft = (bg_rect.left, bg_rect.top + item_height / 2 + index * item_height + v_offset))

            icon_surf = self.monster_frames['icons'][monster.name]
            icon_rect = icon_surf.get_frect(midleft = bg_rect.topleft + vector(10,item_height / 2 + index * item_height + v_offset))
            text_surf = self.fonts['regular'].render(f'{monster.name} ({monster.level})', False, COLORS['red'] if selected else COLORS['black'])
            text_rect = text_surf.get_frect(topleft = (bg_rect.left + 90, icon_rect.top))

            # fondo de selección
            if selected:
                if item_bg_rect.collidepoint(bg_rect.topleft):
                    pygame.draw.rect(self.display_surface, COLORS['dark white'], item_bg_rect, 0, 0, 5, 5)
                elif item_bg_rect.collidepoint(bg_rect.midbottom + vector(0,-1)):
                    pygame.draw.rect(self.display_surface, COLORS['dark white'], item_bg_rect, 0, 0, 0, 0, 5, 5)
                else:
                    pygame.draw.rect(self.display_surface, COLORS['dark white'], item_bg_rect)

            if bg_rect.collidepoint(item_bg_rect.center):
                for surf, rect in ((icon_surf, icon_rect), (text_surf, text_rect)):
                    self.display_surface.blit(surf, rect)
                health_rect = pygame.FRect((text_rect.bottomleft + vector(0,4)), (100,4))
                energy_rect = pygame.FRect((health_rect.bottomleft + vector(0,2)), (80,4))
                draw_bar(self.display_surface, health_rect, monster.health, monster.get_stat('max_health'), COLORS['red'], COLORS['black'])
                draw_bar(self.display_surface, energy_rect, monster.energy, monster.get_stat('max_energy'), COLORS['blue'], COLORS['black'])

    def draw_flee_button(self):
        """Dibuja un botón simple de huida en pantalla cuando es encuentro salvaje y menú general."""
        # mostrar sólo para encuentros salvajes
        if not self.current_monster or self.character is not None or self.selection_mode != 'general':
            self.flee_rect = None
            return

        # posicionar el botón cerca del área derecha de UI del monstruo actual
        pos = self.current_monster.rect.midright + vector(140, 80)
        width, height = 100, 40
        rect = pygame.FRect(0, 0, width, height).move_to(center = pos)
        self.flee_rect = rect  # almacenar para colisiones de entrada

        # dibujar fondo y borde
        pygame.draw.rect(self.display_surface, COLORS['white'], rect, 0, 6)
        pygame.draw.rect(self.display_surface, COLORS['black'], rect, 2, 6)

        # dibujar etiqueta
        label = self.fonts['regular'].render('Flee (F)', False, COLORS['black'])
        label_rect = label.get_rect(center = rect.center)
        self.display_surface.blit(label, label_rect)

    def end_battle(self, character):
        # detener música de batalla
        self.audio['battle'].stop()

        # caso especial: jugador perdió -> enviar al hospital
        if character == 'hospital':
            # curar monstruos del jugador antes de la llegada (hospital es cosmético)
            for monster in self.player_monsters.values():
                monster.health = monster.get_stat('max_health')
                monster.energy = monster.get_stat('max_energy')
                monster.initiative = 0

            # programar transición al mapa hospital
            self.transition_target = ('hospital', 'hospital')
            self.tint_mode = 'tint'

            # overlay corto para mostrar mensaje después de la transición
            self.defeat_overlay = {'text': 'You were defeated and rushed to the hospital.', 'timer': 3.5}

            # asegurar que el jugador quede desbloqueado al llegar
            try:
                self.player.unblock()
            except Exception:
                pass

            return

        # flujo existente para finalizar pelea contra entrenador (character es NPC)
        self.transition_target = 'level'
        self.tint_mode = 'tint'
        if character:
            character.character_data['defeated'] = True
            self.create_dialog(character)
        elif not self.evolution:
            self.player.unblock()
            self.check_evolution()

    def update(self, dt):
        self.check_end_battle()
        
        # actualizaciones
        self.input()
        self.update_timers()
        self.battle_sprites.update(dt)
        self.check_active()

        # dibujo
        self.display_surface.blit(self.bg_surf, (0,0))
        self.battle_sprites.draw(self.current_monster, self.selection_side, self.selection_mode, self.indexes['target'], self.player_sprites, self.opponent_sprites)
        self.draw_ui()