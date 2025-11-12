import math
from settings import * 
from random import uniform
from support import draw_bar
from timer import Timer

# overworld sprites
class Sprite(pygame.sprite.Sprite):
	def __init__(self, pos, surf, groups, z = WORLD_LAYERS['main']):
		super().__init__(groups)
		self.image = surf 
		self.rect = self.image.get_frect(topleft = pos)
		self.z = z
		# valor para ordenar por Y al dibujar (profundidad)
		self.y_sort = self.rect.centery
		self.hitbox = self.rect.copy()

class BorderSprite(Sprite):
	def __init__(self, pos, surf, groups):
		super().__init__(pos, surf, groups)
		# hitbox igual que rect (usado para colisiones estáticas)
		self.hitbox = self.rect.copy()

class TransitionSprite(Sprite):
	def __init__(self, pos, size, target, groups):
		surf = pygame.Surface(size)
		super().__init__(pos, surf, groups)
		# target guarda (map_key, pos) o similar para transición entre mapas
		self.target = target

class CollidableSprite(Sprite):
	def __init__(self, pos, surf, groups):
		super().__init__(pos, surf, groups)
		# hitbox ajustada verticalmente para mejor colisión de personajes
		self.hitbox = self.rect.inflate(0, -self.rect.height * 0.6)

class MonsterPatchSprite(Sprite):
	def __init__(self, pos, surf, groups, biome, monsters, level):
		self.biome = biome
		super().__init__(pos, surf, groups, WORLD_LAYERS['main' if biome != 'sand' else 'bg'])
		# ajustar orden Y para que se dibuje ligeramente detrás
		self.y_sort -= 40
		self.biome = biome
		self.monsters = monsters.split(',')
		self.level = level

class AnimatedSprite(Sprite):
	def __init__(self, pos, frames, groups, z = WORLD_LAYERS['main']):
		self.frame_index, self.frames = 0, frames
		super().__init__(pos, frames[self.frame_index], groups, z)

	def animate(self, dt):
		self.frame_index += ANIMATION_SPEED * dt
		self.image = self.frames[int(self.frame_index % len(self.frames))]

	def update(self, dt):
		self.animate(dt)

# battle sprites 
class MonsterSprite(pygame.sprite.Sprite):
		def __init__(self, pos, frames, groups, monster, index, pos_index, entity, apply_attack, create_monster):
			# datos del sprite y referencia al objeto Monster lógico
			self.index = index
			self.pos_index = pos_index
			self.entity = entity
			self.monster = monster
			self.frame_index, self.frames, self.state = 0, frames, 'idle'
			self.animation_speed = ANIMATION_SPEED + uniform(-1, 1)
			self.z = BATTLE_LAYERS['monster']
			self.highlight = False
			self.target_sprite = None
			self.current_attack = None
			self.apply_attack = apply_attack
			self.create_monster = create_monster

			# setup del sprite (imagen/rect)
			super().__init__(groups)
			# frames[state] debe ser lista; el importer garantiza al menos un frame por estado
			self.image = self.frames[self.state][0]
			self.rect = self.image.get_frect(center = pos)

			# posición base estable para bobbing y posicionamiento
			self.base_pos = pygame.Vector2(self.rect.center)

			# timers internos (quitar highlight, destruir, bob)
			self.timers = {
				'remove highlight': Timer(300, func = lambda: self.set_highlight(False)),
				'kill': Timer(600, func = self.destroy)
			}

			# bobbing: activo por un corto período tras creación
			self.timers['bob'] = Timer(2000, func = lambda: self._stop_bob(), autostart = True)
			self.bobbing = True

		def _stop_bob(self):
			# llamado por temporizador al terminar el bobbing
			self.bobbing = False
			# asegurar posición base exacta
			self.rect.center = (int(self.base_pos.x), int(self.base_pos.y))

		def animate(self, dt):
			# avanzar tiempo de animación interno
			self.frame_index += ANIMATION_SPEED * dt

			# si la animación de ataque terminó, aplicar efecto (daño)
			if self.state == 'attack' and self.frame_index >= len(self.frames['attack']):
				self.apply_attack(self.target_sprite, self.current_attack, self.monster.get_base_damage(self.current_attack))
				self.state = 'idle'
				self.frame_index = 0

			# seleccionar imagen según estado
			state = self.state
			frames_for_state = self.frames.get(state, [])
			if frames_for_state:
				self.adjusted_frame_index = int(self.frame_index % len(frames_for_state))
				self.image = frames_for_state[self.adjusted_frame_index]

			# aplicar efecto highlight si corresponde
			if self.highlight:
				setcolor = (*HIGHLIGHT_COLOR, 255) if 'HIGHLIGHT_COLOR' in globals() else (255,255,255,255)
				colored_surf = pygame.mask.from_surface(self.image).to_surface(setcolor=setcolor, unsetcolor=(0,0,0,0))
				self.image = colored_surf

			# bob lateral mientras esté activo
			if self.bobbing:
				bob_amplitude = 8  # pixeles
				bob_speed = 3.0    # frecuencia
				bob_offset = math.sin(self.frame_index * bob_speed) * bob_amplitude
				self.rect.centerx = int(self.base_pos.x + bob_offset)
				self.rect.centery = int(self.base_pos.y)
			else:
				# asegurar posición base exacta
				self.rect.center = (int(self.base_pos.x), int(self.base_pos.y))

		def set_highlight(self, value):
			self.highlight = value
			if value:
				self.timers['remove highlight'].activate()

		def activate_attack(self, target_sprite, attack):
			# iniciar animación de ataque y consumir energía del monstruo
			self.state = 'attack'
			self.frame_index = 0
			self.target_sprite = target_sprite
			self.current_attack = attack
			self.monster.reduce_energy(attack)

		def delayed_kill(self, new_monster):
			# marcar reemplazo y activar temporizador de 'kill' para limpieza animada
			if not self.timers['kill'].active:
				self.next_monster_data = new_monster
				self.timers['kill'].activate()

		def destroy(self):
			# si hay datos de siguiente monstruo, crear sprite de reemplazo
			if self.next_monster_data:
				try:
					new_sprite = self.create_monster(*self.next_monster_data)
				except Exception:
					new_sprite = None

				# si la batalla tenía este sprite seleccionado, actualizar la referencia
				try:
					battle = self.create_monster.__self__
					if getattr(battle, 'current_monster', None) is self:
						battle.current_monster = new_sprite
				except Exception:
					# fallback gracioso: no romper si introspección falla
					pass

			self.kill()

		def update(self, dt):
			# actualizar timers y animación; también actualizar lógica del Monster
			for timer in self.timers.values():
				timer.update()
			self.animate(dt)
			self.monster.update(dt)

class MonsterOutlineSprite(pygame.sprite.Sprite):
	def __init__(self, monster_sprite, groups, frames):
		super().__init__(groups)
		self.z = BATTLE_LAYERS['outline']
		self.monster_sprite = monster_sprite
		self.frames = frames

		self.image = self.frames[self.monster_sprite.state][self.monster_sprite.frame_index]
		self.rect = self.image.get_frect(center = self.monster_sprite.rect.center)

	def update(self, _):
		self.image = self.frames[self.monster_sprite.state][self.monster_sprite.adjusted_frame_index]
		if not self.monster_sprite.groups():
			self.kill()

class MonsterNameSprite(pygame.sprite.Sprite):
	def __init__(self, pos, monster_sprite, groups, font):
		super().__init__(groups)
		self.monster_sprite = monster_sprite
		self.z = BATTLE_LAYERS['name']

		text_surf = font.render(monster_sprite.monster.name, False, COLORS['black'])
		padding = 10

		self.image = pygame.Surface((text_surf.get_width() + 2 * padding, text_surf.get_height() + 2 * padding)) 
		self.image.fill(COLORS['white'])
		self.image.blit(text_surf, (padding, padding))
		self.rect = self.image.get_frect(midtop = pos)

	def update(self, _):
		if not self.monster_sprite.groups():
			self.kill()

class MonsterLevelSprite(pygame.sprite.Sprite):
	def __init__(self, entity, pos, monster_sprite, groups, font):
		super().__init__(groups)
		self.monster_sprite = monster_sprite
		self.font = font
		self.z = BATTLE_LAYERS['name']

		self.image = pygame.Surface((60,26))
		self.rect = self.image.get_frect(topleft = pos) if entity == 'player' else self.image.get_frect(topright = pos)
		self.xp_rect = pygame.FRect(0,self.rect.height - 2,self.rect.width,2)

	def update(self, _):
		self.image.fill(COLORS['white'])

		text_surf = self.font.render(f'Lvl {self.monster_sprite.monster.level}', False, COLORS['black'])
		text_rect = text_surf.get_frect(center = (self.rect.width / 2, self.rect.height / 2))
		self.image.blit(text_surf, text_rect)

		draw_bar(self.image, self.xp_rect, self.monster_sprite.monster.xp, self.monster_sprite.monster.level_up, COLORS['black'], COLORS['white'], 0)

		if not self.monster_sprite.groups():
			self.kill()

class MonsterStatsSprite(pygame.sprite.Sprite):
	def __init__(self, pos, monster_sprite, size, groups, font):
		super().__init__(groups)
		self.monster_sprite = monster_sprite
		self.image = pygame.Surface(size) 
		self.rect = self.image.get_frect(midbottom = pos)
		self.font = font
		self.z = BATTLE_LAYERS['overlay']

	def update(self, _):
		self.image.fill(COLORS['white'])

		for index, (value, max_value) in enumerate(self.monster_sprite.monster.get_info()):
			color = (COLORS['red'], COLORS['blue'], COLORS['gray'])[index]
			if index < 2: # health and energy 
				text_surf = self.font.render(f'{int(value)}/{max_value}', False, COLORS['black'])
				text_rect = text_surf.get_frect(topleft = (self.rect.width * 0.05,index * self.rect.height / 2))
				bar_rect = pygame.FRect(text_rect.bottomleft + vector(0,-2), (self.rect.width * 0.9, 4))

				self.image.blit(text_surf, text_rect)
				draw_bar(self.image, bar_rect, value, max_value, color, COLORS['black'], 2)
			else: # initiative
				init_rect = pygame.FRect((0, self.rect.height - 2), (self.rect.width, 2)) 
				draw_bar(self.image, init_rect, value, max_value, color, COLORS['white'], 0)

		if not self.monster_sprite.groups():
			self.kill()

class AttackSprite(AnimatedSprite):
	def __init__(self, pos, frames, groups):
		super().__init__(pos, frames, groups, BATTLE_LAYERS['overlay'])
		self.rect.center = pos

	def animate(self, dt):
		self.frame_index += ANIMATION_SPEED * dt
		if self.frame_index < len(self.frames):
			self.image = self.frames[int(self.frame_index)]
		else:
			self.kill()

	def update(self, dt):
		self.animate(dt)

class TimedSprite(Sprite):
	def __init__(self, pos, surf, groups, duration):
		super().__init__(pos, surf, groups, z = BATTLE_LAYERS['overlay'])
		self.rect.center = pos
		self.death_timer = Timer(duration, autostart = True, func = self.kill)

	def update(self, _):
		self.death_timer.update()