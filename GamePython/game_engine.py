# Game Engine - Moteur de jeu RPG
from game_config import (
    GAME_CONFIG, LOCATIONS, ENEMIES, NPCS_DIALOGUE, ITEMS, SHOPS,
    DIFFICULTY_SETTINGS, LOOT_BY_RARITY, CLASSES,
    SKILLS, BOSSES, BOSS_EQUIPMENT_CONFIG, PROGRESSIVE_SKILLS,
    RUNES, RUNE_RECIPES, RUNE_RARITIES, RUNE_DROP_CHANCE,
    CARDS, CARD_DROP_CHANCE, CARD_BOSS_MULTIPLIER, LOCATION_BOSS_MAPPING,
    DYNAMIC_QUEST_TEMPLATES, DYNAMIC_QUESTS_CONFIG
)
import random
from datetime import datetime
from translations import t


class GameEngine:
    """Moteur de jeu principal pour le RPG text-based."""
    
    def __init__(self):
        """Initialise le jeu avec tous les attributs de base."""
        self.player_stats = GAME_CONFIG["player_stats"].copy()
        self.base_stats = GAME_CONFIG["player_stats"].copy()
        self.player_class = None
        self.inventory = {}
        self.equipped = {
            "weapon": None,
            "armor": None,
            "accessory": None
        }
        self.current_location = GAME_CONFIG["starting_location"]
        self.in_combat = False
        self.current_enemy = None
        self.combat_turn = 0
        self.visited_locations = set()
        self.visited_locations.add(self.current_location)
        self.current_shop = None
        self.skills_learned = {}
        self.active_buffs = []
        self.boss_defeated = {}
        self.game_started = datetime.now()
        self.difficulty = "moyen"
        self.total_enemies_defeated = 0
        self.total_damage_dealt = 0
        self.total_damage_taken = 0
        self.boss_spawn_chance = 0.15
        self.game_over = False
        self.game_won = False
        self.show_options = False
        self.show_inventory = False
        self.show_quests = False
        self.show_skills = False
        self.show_map = False
        self.unlocked_skills = {}
        self.skill_notifications = []
        self.is_boss_fight = False
        self.current_boss = None
        
        # Système de quêtes dynamiques
        self.dynamic_quests = {}
        self.dynamic_quest_progress = {}
        self.last_quest_reset = None
        self.dynamic_quests_completed = []
        
        # Générer les premières quêtes dynamiques si le joueur a un niveau suffisant
        self.check_dynamic_quests_auto_reset()

        # Attributs spécifiques Pilleur
        self.innate_crit_chance = 0.0
        self.loot_quality_bonus = 1.0
        self.double_or_nothing_active = False
        self.fouille_accrue_active = False
        self.gold_multiplier_next_kill = 1
        self.pacte_fievre_turns = 0
        self.pacte_crit_bonus = 0.0
        self.pacte_loot_bonus = 0.0

        self.temporary_buffs = {}
        self.enemy_health = 0
        self.enemy_max_health = 0
        self.enemy_level = 1
        self.enemy_attack = 0
        self.enemy_defense = 0

        # Système de runes
        self.rune_inventory = {}  # {"Rune de Feu|mineure": 2, ...}
        self.active_rune_buffs = []  # [{"name": ..., "effect": ..., "value": ..., "turns_left": ...}, ...]
        self.show_runes = False

        # Boost de loot (Colporteur Mystique)
        self.loot_boost_count = 0

        # Cartes permanentes
        self.card_inventory = {}  # {"Carte de Force": 2, ...}
        self.cards_used = []  # Historique des cartes utilisées pour les bonus

        # Système de Prestige / Réincarnation
        self.prestige_level = 0  # Niveau de prestige (0 = pas de prestige)
        self.reincarnation_count = 0  # Nombre total de réincarnations
        self.arena_wins = 0  # Nombre de victoires en arène
        self.arena_current_streak = 0  # Série de victoires actuelle en arène
        self.arena_enemies_defeated = 0  # Ennemis vaincus dans l'arène cette session
        self.in_arena = False  # Indique si le joueur est dans l'arène
        self.arena_enemy = None  # Ennemi actuel de l'arène
        self.arena_rewards = {"exp": 0, "gold": 0, "runes": {}, "cards": {}}  # Récompenses accumulées
        self.last_arena_message = None  # Dernier message de l'arène

        # Langue
        self.language = "fr"

    def set_class(self, class_name):
        if class_name not in CLASSES:
            return False
        self.player_class = class_name
        class_data = CLASSES[class_name]
        # Mettre à jour player_stats et base_stats avec les stats de la classe
        for stat, value in class_data["base_stats"].items():
            self.player_stats[stat] = value
            self.base_stats[stat] = value
        # Ne réinitialiser les compétences que si la classe change
        if class_name not in self.skills_learned:
            self.skills_learned[class_name] = {}
            for skill_name, skill_data in SKILLS[class_name].items():
                if skill_data.get("unlocked_at", 1) <= self.player_stats["level"]:
                    self.skills_learned[class_name][skill_name] = True
        
        # Passifs Pilleur
        if class_name == "Pilleur":
            self.innate_crit_chance = 0.20
            self.loot_quality_bonus = 1.20

        # Débloquer les compétences progressives selon le niveau
        self.unlock_progressive_skills()
        return True
    
    def reincarnate(self):
        """Réincarne le personnage - système de prestige"""
        if self.player_stats["level"] < 30:
            return False, t("Vous devez être au moins niveau 30 pour vous réincarner !", self.language)
        
        # Calculer le nombre de cartes à recevoir
        player_level = self.player_stats["level"]
        if player_level < 50:
            num_cards = 1
        elif player_level < 70:
            num_cards = 3
        elif player_level < 90:
            num_cards = 5
        else:
            num_cards = 10
        
        # Augmenter le niveau de prestige
        self.prestige_level += 1
        self.reincarnation_count += 1
        
        # Sauvegarder les cartes actuelles et les bonus permanents avant réinitialisation
        saved_cards = self.card_inventory.copy()
        saved_runes = self.rune_inventory.copy()
        saved_skills = {k: v.copy() if isinstance(v, dict) else v for k, v in self.skills_learned.items()}
        saved_unlocked = self.unlocked_skills.copy()
        saved_prestige = self.prestige_level
        saved_reincarnations = self.reincarnation_count
        
        # Calculer les bonus permanents des cartes utilisées
        card_bonuses = {"attack": 0, "defense": 0, "max_health": 0, "max_mana": 0, "loot_boost": 0}
        for card_name in self.cards_used:
            if card_name in CARDS:
                card_data = CARDS[card_name]
                stat = card_data.get("stat", "")
                value = card_data.get("value", 0)
                if stat in card_bonuses:
                    card_bonuses[stat] += value
        
        # Réinitialiser les stats de base mais garder la classe
        class_name = self.player_class
        self.player_stats = GAME_CONFIG["player_stats"].copy()
        self.base_stats = GAME_CONFIG["player_stats"].copy()
        
        # Reappliquer les stats de classe
        if class_name and class_name in CLASSES:
            class_data = CLASSES[class_name]
            for stat, value in class_data["base_stats"].items():
                self.player_stats[stat] = value
                self.base_stats[stat] = value
            self.set_class(class_name)  # Réappliquer les compétences de base
        
        # Réappliquer les bonus permanents des cartes utilisées
        self.player_stats["attack"] += card_bonuses["attack"]
        self.player_stats["defense"] += card_bonuses["defense"]
        self.player_stats["max_health"] += card_bonuses["max_health"]
        self.player_stats["health"] += card_bonuses["max_health"]  # Ajuster aussi la santé actuelle
        self.player_stats["max_mana"] += card_bonuses["max_mana"]
        self.player_stats["mana"] += card_bonuses["max_mana"]  # Ajuster aussi le mana actuel
        
        # Recalculer loot_boost_count à partir des cartes de loot_boost utilisées
        # (chaque carte ajoute int(value / 0.5) comme dans use_card())
        for card_name in self.cards_used:
            if card_name in CARDS:
                card_data = CARDS[card_name]
                if card_data.get("stat") == "loot_boost":
                    value = card_data.get("value", 0)
                    if value >= 0.5:
                        self.loot_boost_count += int(value / 0.5)
                    else:
                        self.loot_boost_count += 1
        
        # Réinitialiser l'inventaire mais garder les cartes et runes
        self.inventory = {}
        self.equipped = {"weapon": None, "armor": None, "accessory": None}
        self.card_inventory = saved_cards
        self.rune_inventory = saved_runes
        
        # Réinitialiser la position
        self.current_location = GAME_CONFIG["starting_location"]
        self.visited_locations = {self.current_location}
        self.in_combat = False
        self.in_arena = False
        self.current_enemy = None
        self.arena_enemy = None
        self.game_over = False
        
        # Réinitialiser les quêtes dynamiques
        self.dynamic_quests = {}
        self.dynamic_quest_progress = {}
        self.dynamic_quests_completed = []
        
        # Restaurer le prestige et les compétences
        self.prestige_level = saved_prestige
        self.reincarnation_count = saved_reincarnations
        self.skills_learned = saved_skills
        self.unlocked_skills = saved_unlocked
        
        # Donner les nouvelles cartes aléatoires
        for _ in range(num_cards):
            self.add_random_card()
        
        # Réinitialiser les stats de combat
        self.combat_turn = 0
        self.total_damage_dealt = 0
        self.total_damage_taken = 0
        
        # Réinitialiser l'état de l'arène
        self.arena_rewards = {"exp": 0, "gold": 0, "runes": {}, "cards": {}}
        self.arena_enemies_defeated = 0
        self.arena_current_streak = 0
        
        return True, f"{t('Réincarnation réussie !', self.language)} {t('Vous êtes maintenant Prestige', self.language)} {self.prestige_level}. {t('Vous avez reçu', self.language)} {num_cards} {t('cartes !', self.language)}"
    
    def can_enter_arena(self):
        """Vérifie si le joueur peut entrer dans l'arène (nécessite au moins 1 réincarnation)"""
        return self.reincarnation_count >= 1
    
    def add_random_card(self):
        """Ajoute une carte aléatoire à l'inventaire"""
        if not CARDS:
            return
        
        # Filtrer les cartes accessibles selon le niveau
        available_cards = [card for card, data in CARDS.items() 
                          if self.player_stats.get("level", 1) >= data.get("required_level", 1)]
        
        if not available_cards:
            return
        
        card_name = random.choice(available_cards)
        self.card_inventory[card_name] = self.card_inventory.get(card_name, 0) + 1
    
    def enter_arena(self):
        """Entrer dans l'arène de combat à mort"""
        if not self.can_enter_arena():
            return False, t("Vous devez avoir au moins 1 réincarnation pour entrer dans l'arène !", self.language)
        
        if self.in_combat:
            return False, t("Vous êtes déjà en combat !", self.language)
        
        if self.in_arena:
            return False, t("Vous êtes déjà dans l'arène !", self.language)
        
        # Réinitialiser les récompenses de l'arène
        self.arena_rewards = {"exp": 0, "gold": 0, "runes": {}, "cards": {}}
        self.arena_enemies_defeated = 0
        self.arena_current_streak = 0
        
        # Créer le premier ennemi de l'arène
        self.start_arena_fight()
        
        return True, t("Bienvenue dans l'Arène de Combat à Mort ! Combattez jusqu'à la mort pour obtenir des récompenses !", self.language)
    
    def start_arena_fight(self):
        """Démarre un combat dans l'arène"""
        if not self.in_arena and not self.can_enter_arena():
            return t("Vous ne pouvez pas commencer un combat d'arène ici.", self.language)
        
        # Créer un ennemi adapté au niveau du joueur
        player_level = self.player_stats["level"]
        
        # Sélectionner un ennemi aléatoire parmi ceux adaptés au niveau
        suitable_enemies = []
        for enemy_name, enemy_data in ENEMIES.items():
            if enemy_data["level"] >= player_level - 5 and enemy_data["level"] <= player_level + 5:
                suitable_enemies.append(enemy_name)
        
        if not suitable_enemies:
            suitable_enemies = list(ENEMIES.keys())
        
        enemy_name = random.choice(suitable_enemies)
        enemy_data = ENEMIES[enemy_name].copy()
        
        # Booster les stats pour l'arène (50% de bonus)
        enemy_data["health"] = int(enemy_data["health"] * 1.5)
        enemy_data["attack"] = int(enemy_data["attack"] * 1.5)
        enemy_data["defense"] = int(enemy_data["defense"] * 1.3)
        enemy_data["level"] = player_level
        enemy_data["exp_reward"] = int(enemy_data["exp_reward"] * 1.5)
        enemy_data["gold_reward"] = int(enemy_data["gold_reward"] * 1.5)
        
        self.current_enemy = {
            "name": enemy_name,
            "is_boss": False,
            "health": enemy_data["health"],
            "max_health": enemy_data["health"],
            "attack": enemy_data["attack"],
            "defense": enemy_data["defense"],
            "level": enemy_data["level"],
            "exp_reward": enemy_data["exp_reward"],
            "gold_reward": enemy_data["gold_reward"],
            "description": ENEMIES.get(enemy_name, {}).get("description", ""),
            "icon": ENEMIES.get(enemy_name, {}).get("icon", "👹")
        }
        
        self.arena_enemy = self.current_enemy.copy()
        self.enemy_health = self.current_enemy.get("health", 1)
        self.enemy_max_health = self.current_enemy.get("max_health", 1)
        self.enemy_level = self.current_enemy.get("level", 1)
        self.enemy_attack = self.current_enemy.get("attack", 5)
        self.enemy_defense = self.current_enemy.get("defense", 0)
        self.in_combat = True
        self.in_arena = True
        self.combat_turn = 0
        
        return t("Un combat d'arène a commencé contre", self.language) + f" {t(enemy_name, self.language)} !"
    
    def leave_arena(self):
        """Quitter l'arène (sans récompense)"""
        if not self.in_arena:
            return t("Vous n'êtes pas dans l'arène.", self.language)
        
        # Réinitialiser l'état de l'arène
        self.in_arena = False
        self.arena_rewards = {"exp": 0, "gold": 0, "runes": {}, "cards": {}}
        self.arena_enemies_defeated = 0
        self.arena_current_streak = 0
        
        if self.in_combat:
            self.in_combat = False
            self.current_enemy = None
            self.arena_enemy = None
            self.enemy_health = 0
            self.enemy_max_health = 0
        
        return t("Vous avez quitté l'arène. Vos récompenses sont perdues !", self.language)
    
    def claim_arena_rewards(self):
        """Récupérer les récompenses de l'arène (appelé à la mort)"""
        if not self.in_arena:
            return t("Vous n'êtes pas dans l'arène.", self.language)
        
        # Appliquer les récompenses accumulées
        exp_gained = self.arena_rewards["exp"]
        gold_gained = self.arena_rewards["gold"]
        self.player_stats["exp"] += exp_gained
        self.player_stats["gold"] += gold_gained
        
        # Ajouter les runes
        runes_message = ""
        for rune, qty in self.arena_rewards["runes"].items():
            self.rune_inventory[rune] = self.rune_inventory.get(rune, 0) + qty
            runes_message += f"\n🔮 {t('Rune :', self.language)} {rune} (x{qty})"
        
        # Ajouter les cartes
        cards_message = ""
        for card, qty in self.arena_rewards["cards"].items():
            self.card_inventory[card] = self.card_inventory.get(card, 0) + qty
            cards_message += f"\n🃏 {card} (x{qty})"
        
        # Sauvegarder le nombre d'ennemis vaincus avant réinitialisation
        enemies_defeated_display = self.arena_enemies_defeated
        
        # Incrémenter le compteur de victoires si au moins 1 ennemi vaincu
        if enemies_defeated_display > 0:
            self.arena_wins += 1
        
        # Réinitialiser
        self.arena_rewards = {"exp": 0, "gold": 0, "runes": {}, "cards": {}}
        self.arena_enemies_defeated = 0
        self.arena_current_streak = 0
        self.in_arena = False
        
        # Retourner un message de résumé
        message = t("Vous avez été vaincu en arène après avoir vaincu", self.language) + f" {enemies_defeated_display} " + t("ennemis !", self.language)
        message += f"\n{t('Récompenses :', self.language)}"
        message += f"\n⭐ {exp_gained} XP"
        message += f"\n💰 {gold_gained} " + t("or", self.language)
        
        # Ajouter des messages explicites si pas de runes/cartes
        if runes_message:
            message += runes_message
        else:
            message += f"\n{t('Aucune rune obtenue.', self.language)}"
        
        if cards_message:
            message += cards_message
        else:
            message += f"\n{t('Aucune carte obtenue.', self.language)}"
        
        return message
    
    def get_location_description(self):
        if self.current_location not in LOCATIONS:
            return f"<p>{t('Localisation inconnue', self.language)}</p>"
        location_data = LOCATIONS[self.current_location]
        loc_name = t(location_data.get('name', t('Localisation', self.language)), self.language)
        loc_desc = t(location_data.get('description', t('Aucune description', self.language)), self.language)
        description = f"<h2>{loc_name}</h2>"
        description += f"<p>{loc_desc}</p>"
        if location_data.get("enemies"):
            translated_enemies = [t(e, self.language) for e in location_data["enemies"]]
            description += f"<p><strong>{t('Ennemis :', self.language)}</strong> " + ", ".join(translated_enemies) + "</p>"
        if location_data.get("npcs"):
            translated_npcs = [t(n, self.language) for n in location_data["npcs"]]
            description += f"<p><strong>NPCs :</strong> " + ", ".join(translated_npcs) + "</p>"
        if location_data.get("shops"):
            translated_shops = [t(s, self.language) for s in location_data["shops"]]
            description += f"<p><strong>{t('Magasins :', self.language)}</strong> " + ", ".join(translated_shops) + "</p>"
        return description
    
    def get_available_actions(self):
        actions = []
        if self.in_combat:
            actions = [
                {"type": "attack", "text": t("Attaquer", self.language), "value": "attack"},
                {"type": "use_skill", "text": t("Utiliser compétence", self.language), "value": "use_skill"},
                {"type": "use_item", "text": t("Utiliser objet", self.language), "value": "use_item"},
                {"type": "flee", "text": t("Fuir le combat", self.language), "value": "flee"}
            ]
        else:
            if self.current_location in LOCATIONS:
                location_data = LOCATIONS[self.current_location]
                if location_data.get("exits"):
                    for direction, destination in location_data["exits"].items():
                        dest_name = LOCATIONS.get(destination, {}).get("name", destination)
                        translated_dir = t(direction.upper(), self.language)
                        actions.append({
                            "type": "move",
                            "text": f"{t('Aller', self.language)} {translated_dir} → {t(dest_name, self.language)}",
                            "value": destination
                        })
                if location_data.get("enemies"):
                    actions.append({
                        "type": "fight",
                        "text": t("Combattre un ennemi", self.language),
                        "value": ""
                    })

                actions.append({
                    "type": "explore",
                    "text": t("Explorer", self.language),
                    "value": "explore"
                })

                # Bouton portail si la location en possède un
                portal_data = location_data.get("portal")
                if portal_data:
                    actions.append({
                        "type": "use_portal",
                        "text": f"🌀 {t(portal_data['text'], self.language)}",
                        "value": portal_data["destination"]
                    })

                actions.extend([
                    {"type": "rest", "text": t("Se reposer", self.language), "value": "rest"}
                ])
        return actions
    
    def move(self, destination):
        if self.in_combat:
            return t("Vous ne pouvez pas vous déplacer pendant un combat !", self.language)
        if self.current_location not in LOCATIONS:
            return t("Localisation actuelle inconnue !", self.language)
        location_data = LOCATIONS[self.current_location]
        exits = location_data.get("exits", {})
        if destination not in exits.values():
            return t("Vous ne pouvez pas aller à", self.language) + f" {destination} " + t("depuis", self.language) + f" {self.current_location}."
        self.current_location = destination
        self.visited_locations.add(destination)
        self.close_shop()
        return t("Vous vous êtes déplacé vers", self.language) + f" {destination}."

    def use_portal(self, destination):
        if self.in_combat:
            return t("Vous ne pouvez pas utiliser le portail pendant un combat !", self.language)
        if self.current_location not in LOCATIONS:
            return t("Localisation actuelle inconnue !", self.language)
        location_data = LOCATIONS[self.current_location]
        portal_data = location_data.get("portal")
        if not portal_data:
            return t("Il n'y a pas de portail ici.", self.language)
        if portal_data["destination"] != destination:
            return t("Destination invalide.", self.language)
        self.current_location = destination
        self.visited_locations.add(destination)
        self.close_shop()
        dest_name = LOCATIONS.get(destination, {}).get("name", destination)
        return f"🌀 {t('Vous traversez le portail...', self.language)} {t('Vous arrivez à', self.language)} {t(dest_name, self.language)} !"

    def explore_location(self):
        if self.current_location not in LOCATIONS:
            return t("Localisation inconnue !", self.language)
        location_data = LOCATIONS[self.current_location]
        exploration_result = t("Vous explorez", self.language) + f" {location_data.get('name', t('la zone', self.language))}...\n"

        # 30% de chance de trouver du loot (comme avant)
        if random.random() < 0.3:
            # Utiliser get_loot() pour un loot basé sur le niveau
            loot = self.get_loot(self.player_stats.get("level", 1))
            if loot:
                for item, qty in loot.items():
                    if item in self.inventory:
                        self.inventory[item] += qty
                    else:
                        self.inventory[item] = qty
                    exploration_result += t("Vous avez trouvé :", self.language) + f" {item} (x{qty})\n"
            else:
                exploration_result += t("Vous n'avez rien trouvé d'intéressant.", self.language) + "\n"
        else:
            exploration_result += t("Vous n'avez rien trouvé d'intéressant.", self.language) + "\n"

        # 25% de chance de déclencher un combat (comme avant)
        if random.random() < 0.25 and location_data.get("enemies"):
            exploration_result += "\n" + t("Un ennemi vous barre le chemin !", self.language)
            self.start_fight()
        
        # Mettre à jour les quêtes dynamiques (exploration)
        self.update_dynamic_quest_progress("explore")
        
        return exploration_result
    
    def start_fight(self, enemy=None):
        if self.current_location not in LOCATIONS:
            return t("Pas d'ennemi ici !", self.language)
        location_data = LOCATIONS[self.current_location]
        available_enemies = location_data.get("enemies", [])

        if not available_enemies and enemy is None:
            return t("Pas d'ennemi disponible !", self.language)
        
        if random.random() < self.boss_spawn_chance and BOSSES:
            # Vérifier si la location a des boss spécifiques
            location_name = LOCATIONS.get(self.current_location, {}).get("name", self.current_location)
            possible_bosses = LOCATION_BOSS_MAPPING.get(location_name, list(BOSSES.keys()))
            
            # Filtrer pour ne garder que les boss qui existent dans BOSSES
            possible_bosses = [b for b in possible_bosses if b in BOSSES]
            
            # Si aucun boss spécifique, prendre tous les boss
            if not possible_bosses:
                possible_bosses = list(BOSSES.keys())
            
            boss_name = random.choice(possible_bosses)
            boss_data = BOSSES[boss_name].copy()
            self.current_enemy = {
                "name": boss_name,
                "is_boss": True,
                "health": boss_data.get("base_health", 250),
                "max_health": boss_data.get("base_health", 250),
                "attack": boss_data.get("base_attack", 35),
                "defense": boss_data.get("base_defense", 15),
                "level": boss_data.get("level", 15),
                "exp_reward": boss_data.get("exp_reward", 750),
                "gold_reward": boss_data.get("gold_reward", 400),
                "description": boss_data.get("description", ""),
                "icon": boss_data.get("icon", "👹")
            }
            self.is_boss_fight = True
            self.current_boss = boss_name
        else:
            enemy_name = enemy or random.choice(available_enemies)
            if enemy_name not in ENEMIES:
                return t("Ennemi", self.language) + f" {enemy_name} " + t("introuvable !", self.language)
            self.current_enemy = ENEMIES[enemy_name].copy()
            self.current_enemy["name"] = enemy_name
            self.current_enemy["is_boss"] = False
            self.current_enemy["max_health"] = self.current_enemy.get("health", 50)
            self.is_boss_fight = False
            self.current_boss = None
        
        self.enemy_health = self.current_enemy.get("health", 1)
        self.enemy_max_health = self.current_enemy.get("max_health", 1)
        self.enemy_level = self.current_enemy.get("level", 1)
        self.enemy_attack = self.current_enemy.get("attack", 5)
        self.enemy_defense = self.current_enemy.get("defense", 0)
        
        self.in_combat = True
        self.combat_turn = 0
        enemy_display = t(self.current_enemy['name'], self.language)
        return t("Un combat a commencé contre", self.language) + f" {enemy_display} !"
    
    def attack_enemy(self):
        if not self.in_combat or not self.current_enemy:
            return {"message": t("Vous n'êtes pas en combat !", self.language), "action": "none"}

        rune_log = ""

        # Rune: regen au début du tour
        regen_val = self.get_rune_buff_value("regen")
        if regen_val > 0:
            healed = self.heal(regen_val)
            if healed > 0:
                rune_log += f"\n🌿 {t('Régénération :', self.language)} +{healed} HP"

        # Rune: enemy_weaken (réduit ATK ennemi)
        weaken_val = self.get_rune_buff_value("enemy_weaken")
        enemy_atk = self.current_enemy.get("attack", 5)
        if weaken_val > 0:
            enemy_atk = max(1, enemy_atk - weaken_val)

        player_damage = self.player_stats["attack"] + random.randint(-2, 5)

        # Rune: attack_boost
        atk_boost = self.get_rune_buff_value("attack_boost")
        player_damage += atk_boost

        # Rune: berserk (+ATK -DEF)
        if self.has_rune_buff("berserk"):
            berserk_val = self.get_rune_buff_value("berserk")
            player_damage += berserk_val

        # Rune: all_boost
        all_boost_val = self.get_rune_buff_value("all_boost")
        player_damage += all_boost_val

        # Rune: bonus_damage_next (dégâts bonus à usage unique)
        bonus_dmg = self.get_rune_buff_value("bonus_damage_next")
        if bonus_dmg > 0:
            player_damage += bonus_dmg
            self.consume_rune_buff("bonus_damage_next")
            rune_log += "\n💥 " + t("Bonus de rune explosé !", self.language)

        enemy_defense = self.current_enemy.get("defense", 0)
        player_damage = max(1, player_damage - enemy_defense // 2)

        # Appliquer le multiplicateur de dégâts de l'arme équipée
        weapon_name = self.equipped.get("weapon")
        if weapon_name and weapon_name in ITEMS:
            weapon_data = ITEMS[weapon_name]
            damage_mult = weapon_data.get("damage_multiplier", 1.0)
            if damage_mult > 1.0:
                player_damage = int(player_damage * damage_mult)

        enemy_damage = enemy_atk + random.randint(-2, 3)

        # Rune: defense_boost + all_boost + berserk penalty
        player_defense = self.player_stats["defense"]
        def_boost = self.get_rune_buff_value("defense_boost") + all_boost_val
        if self.has_rune_buff("berserk"):
            berserk_penalty = RUNE_RECIPES.get("Fureur Primale", {}).get("penalty", 10)
            def_boost -= berserk_penalty
        enemy_damage = max(1, enemy_damage - (player_defense + def_boost) // 2)

        # Déterminer si c'est un coup critique
        pacte_crit = self.pacte_crit_bonus if self.pacte_fievre_turns > 0 else 0.0
        is_critical = random.random() < (0.1 + self.innate_crit_chance + pacte_crit)
        # Rune: guaranteed_crit
        if self.has_rune_buff("guaranteed_crit"):
            is_critical = True
            crit_mult = self.get_rune_buff_value("guaranteed_crit")
            player_damage = int(player_damage * crit_mult)
            self.consume_rune_buff("guaranteed_crit")
            rune_log += "\n💀 " + t("Frappe de l'Ombre : critique garanti !", self.language)
        elif is_critical:
            player_damage = int(player_damage * 1.5)
            # Pilleur passif : Cascade Critique soigne 25% des dégâts sur critique
            if self.player_class == "Pilleur" and "Cascade Critique" in self.unlocked_skills:
                heal_amount = self.heal(int(player_damage * 0.25))
                if heal_amount > 0:
                    rune_log += f"\n⚡ {t('Cascade Critique :', self.language)} +{heal_amount} HP"

        # Rune: multi_hit (chance de frapper plusieurs fois)
        extra_hits = 0
        if self.has_rune_buff("multi_hit") and random.random() < 0.4:
            extra_hits = self.get_rune_buff_value("multi_hit") - 1
            player_damage *= (extra_hits + 1)
            rune_log += f"\n🌀 {t('Vortex :', self.language)} {extra_hits + 1} {t('frappes !', self.language)}"

        self.current_enemy["health"] -= player_damage
        self.total_damage_dealt += player_damage
        self.enemy_health = self.current_enemy.get("health", 0)

        combat_log = t("Vous avez infligé", self.language) + f" {player_damage} " + t("dégâts !", self.language)
        if is_critical:
            combat_log = t("COUP CRITIQUE !", self.language) + f" {player_damage} " + t("dégâts !", self.language)
        combat_log += rune_log

        # Tick des buffs de runes
        self.tick_rune_buffs()
        
        if self.current_enemy["health"] <= 0:
            enemy_name = self.current_enemy["name"]
            exp_gain = self.current_enemy.get("exp_reward", 50)
            gold_gain = self.current_enemy.get("gold_reward", 20)
            
            # Loot spécifique pour les boss
            if self.current_enemy.get("is_boss"):
                loot = self.get_boss_loot(enemy_name)
                # Ajouter aussi du loot aléatoire normal (50% de chance)
                if random.random() < 0.50:
                    normal_loot = self.get_loot(self.current_enemy.get("level", 1))
                    for item, qty in normal_loot.items():
                        loot[item] = loot.get(item, 0) + qty
            else:
                loot = self.get_loot(self.current_enemy.get("level", 1))
            
            # Pilleur : Trésor Vivant (gold bonus passif inné)
            if self.player_class == "Pilleur":
                tresor_bonus = int(gold_gain * 0.15)
                gold_gain += tresor_bonus
                combat_log += f"\n💎 {t('Trésor Vivant :', self.language)} +{tresor_bonus} " + t("or bonus !", self.language)

            # Pilleur : multiplicateur d'or (Ruée d'Or)
            if self.gold_multiplier_next_kill > 1:
                extra_gold = gold_gain * (self.gold_multiplier_next_kill - 1)
                gold_gain += int(extra_gold)
                ruee_or_txt = t("Ruée d'Or :", self.language)
                combat_log += f"\n💰 {ruee_or_txt} x{self.gold_multiplier_next_kill} " + t("or !", self.language)
                self.gold_multiplier_next_kill = 1

            # Pilleur : Fouille Accrue or +50%
            if self.fouille_accrue_active:
                fouille_gold = int(gold_gain * 0.5)
                gold_gain += fouille_gold
                combat_log += f"\n🔍 {t('Fouille Accrue :', self.language)} +{fouille_gold} " + t("or bonus !", self.language)

            # Gestion des récompenses - Arène vs Normal
            if self.in_arena:
                # En arène : accumuler les récompenses (pas d'XP/or direct, pas de loot normal)
                self.arena_rewards["exp"] += exp_gain
                self.arena_rewards["gold"] += gold_gain
                self.arena_enemies_defeated += 1
                self.arena_current_streak += 1
                
                # Runes et cartes vont dans les récompenses de l'arène (sans les afficher dans le combat log)
                rune_drop = self.drop_rune(self.current_enemy.get("level", 1))
                if rune_drop:
                    self.arena_rewards["runes"][rune_drop] = self.arena_rewards["runes"].get(rune_drop, 0) + 1
                
                card_drop = self.drop_card(self.current_enemy.get("level", 1), self.current_enemy.get("is_boss", False))
                if card_drop:
                    self.arena_rewards["cards"][card_drop] = self.arena_rewards["cards"].get(card_drop, 0) + 1
                
                combat_log += f"\n{self.current_enemy['name']} " + t("a été vaincu !", self.language)
                combat_log += f"\n{t('Victoires en arène :', self.language)} {self.arena_current_streak}"
                
                # Passer au prochain ennemi de l'arène
                self.start_arena_fight()
                return {
                    "message": combat_log,
                    "action": "kill",
                    "enemy_defeated": True,
                    "player_damage": player_damage,
                    "enemy_damage": 0,
                    "is_critical": is_critical
                }
            else:
                # Mode normal : donner les récompenses immédiatement
                self.player_stats["gold"] += gold_gain
                self.update_dynamic_quest_progress("kill_enemies")
                self.update_dynamic_quest_progress("collect_gold", gold_gain)
                self.add_exp(exp_gain)
                self.total_enemies_defeated += 1

                if self.current_enemy.get("is_boss"):
                    self.boss_defeated[self.current_enemy["name"]] = True

                combat_log += f"\n{self.current_enemy['name']} " + t("a été vaincu !", self.language) + "\n"
                combat_log += t("Expérience gagnée :", self.language) + f" {exp_gain}\n" + t("Or gagné :", self.language) + f" {gold_gain}\n"

                # Pilleur : Double ou Rien sur le loot
                if self.double_or_nothing_active:
                    self.double_or_nothing_active = False
                    if random.random() < 0.5:
                        for item, qty in loot.items():
                            loot[item] = qty * 2
                        combat_log += f"\n🎲 {t('Double ou Rien : DOUBLE ! Loot doublé !', self.language)}\n"
                    else:
                        loot = {}
                        combat_log += f"\n🎲 {t('Double ou Rien : RIEN ! Loot perdu...', self.language)}\n"

                if loot:
                    for item, qty in loot.items():
                        self.inventory[item] = self.inventory.get(item, 0) + qty
                        combat_log += t("Butin :", self.language) + f" {item} (x{qty})\n"

                # Pilleur : Fouille Accrue — reset après kill
                if self.fouille_accrue_active:
                    self.fouille_accrue_active = False

                rune_drop = self.drop_rune(self.current_enemy.get("level", 1))
                if rune_drop:
                    combat_log += t("Rune :", self.language) + f" {rune_drop}\n"

                card_drop = self.drop_card(self.current_enemy.get("level", 1), self.current_enemy.get("is_boss", False))
                if card_drop:
                    combat_log += "CARTE : " + f"{card_drop}\n"

                # Mettre à jour les quêtes dynamiques
                if self.current_enemy.get("is_boss"):
                    self.update_dynamic_quest_progress("kill_bosses")
                else:
                    self.update_dynamic_quest_progress("kill_enemies")
                
                # Vérifier si les quêtes dynamiques doivent être reset
                self.check_dynamic_quests_auto_reset()

                self.in_combat = False
                self.current_enemy = None
                self.enemy_health = 0
                self.enemy_max_health = 0
                return {
                    "message": combat_log,
                    "action": "kill",
                    "enemy_defeated": True,
                    "player_damage": player_damage,
                    "enemy_damage": 0,
                    "is_critical": is_critical
                }
        
        # Save enemy health before potential cleanup (take_damage might set current_enemy to None)
        current_enemy_health = self.current_enemy.get("health", 0) if self.current_enemy else 0
        
        damage_taken, death_message = self.take_damage(enemy_damage)
        combat_log += "\n" + t("L'ennemi a infligé", self.language) + f" {damage_taken} " + t("dégâts !", self.language)

        combat_log += "\n" + t("Vie ennemie :", self.language) + f" {current_enemy_health}"
        combat_log += "\n" + t("Votre vie :", self.language) + f" {self.player_stats['health']}"

        if self.player_stats['health'] <= 0:
            combat_log += "\n" + t("Vous avez été vaincu !", self.language)
            
            # En arène : ajouter le message des récompenses si disponible
            if death_message:
                combat_log += "\n" + death_message
            
            self.in_combat = False
            self.current_enemy = None
            self.enemy_health = 0
            self.enemy_max_health = 0
            
            # En arène : ne pas réinitialiser la santé, récompenses déjà données dans take_damage
            if not self.in_arena:
                self.reset_health()
            
            return {
                "message": combat_log,
                "action": "attack",
                "player_damage": player_damage,
                "enemy_damage": damage_taken,
                "is_critical": is_critical,
                "player_health": self.player_stats['health'],
                "enemy_health": current_enemy_health
            }
        
        # Tick Fièvre de l'Or (Pacte Doré)
        if self.pacte_fievre_turns > 0:
            self.pacte_fievre_turns -= 1
        self.combat_turn += 1
        return {
            "message": combat_log,
            "action": "attack",
            "player_damage": player_damage,
            "enemy_damage": enemy_damage,
            "is_critical": is_critical,
            "player_health": self.player_stats['health'],
            "enemy_health": current_enemy_health
        }
    
    def take_damage(self, amount):
        armor_bonus = self.temporary_buffs.get("defense", 0)
        damage = max(1, amount - (self.player_stats.get("armor", 0) + armor_bonus) // 2)
        self.player_stats["health"] -= damage
        self.total_damage_taken += damage
        death_message = None
        if self.player_stats["health"] <= 0:
            self.player_stats["health"] = 0
            self.in_combat = False
            
            # Si mort en arène : récupérer les récompenses et NE PAS mettre game_over
            if self.in_arena:
                death_message = self.claim_arena_rewards()
                self.in_arena = False
                self.arena_enemy = None
                self.current_enemy = None
                self.enemy_health = 0
                self.enemy_max_health = 0
                self.enemy_level = 1
                self.enemy_attack = 0
                self.enemy_defense = 0
                # Ne pas mettre game_over, le joueur continue à vivre après l'arène
                # Réinitialiser la santé (sans changer de location)
                self.reset_health(reset_location=False)
                # Stocker le message pour affichage
                self.last_arena_message = death_message
            else:
                # Mort normale : game over
                self.game_over = True
            
        return damage, death_message
    
    def heal(self, amount):
        healed = min(amount, self.player_stats["max_health"] - self.player_stats["health"])
        self.player_stats["health"] += healed
        return healed
    
    def add_exp(self, amount):
        self.player_stats["exp"] += amount
        self.update_dynamic_quest_progress("gain_xp", amount)
        self.check_level_up()
    
    def check_level_up(self):
        while self.player_stats["exp"] >= self.player_stats["exp_for_next_level"]:
            self.player_stats["exp"] -= self.player_stats["exp_for_next_level"]
            self.player_stats["level"] += 1
            self.player_stats["exp_for_next_level"] = int(self.player_stats["exp_for_next_level"] * 1.1)

            if self.player_class in CLASSES:
                # Bonus de mana pour TOUTES les classes : 5 + 0.1% du mana max par niveau
                current_max_mana = self.player_stats.get("max_mana", 50)
                mana_bonus = 5 + (current_max_mana * 0.001)  # 0.1% = 0.001
                self.player_stats["mana"] += mana_bonus
                self.player_stats["max_mana"] += mana_bonus
                
                # Utilisation de match/case pour les bonus de classe
                match self.player_class:
                    case "Guerrier":
                        self.player_stats["defense"] += 2
                        self.player_stats["attack"] += 1
                        self.player_stats["health"] += 5
                        self.player_stats["max_health"] += 5
                    case "Mage":
                        self.player_stats["mana"] += 2
                        self.player_stats["max_mana"] += 2
                        self.player_stats["attack"] += 0.5
                        self.player_stats["health"] += 3
                        self.player_stats["max_health"] += 3
                    case "Archer":
                        self.player_stats["attack"] += 1.5
                        self.player_stats["mana"] += 1
                        self.player_stats["max_mana"] += 1
                        self.player_stats["health"] += 4
                        self.player_stats["max_health"] += 4
                    case "Pilleur":
                        self.player_stats["attack"] += 1
                        self.player_stats["defense"] += 1
                        self.player_stats["health"] += 3
                        self.player_stats["max_health"] += 3
                        self.innate_crit_chance += 0.005
                        self.loot_quality_bonus += 0.01

            self.unlock_progressive_skills()
    
    def get_loot(self, enemy_level):
        loot = {}
        if not LOOT_BY_RARITY:
            return loot

        base_table = {
            "commun": 0.50,
            "rare": 0.30,
            "epique": 0.15,
            "legendaire": 0.05
        }

        # Scaling : 1.5% base + 2% de la proba de base par niveau du monstre
        # Boost Colporteur : +0.5% global par achat (0.005 par boost)
        loot_boost_bonus = self.loot_boost_count * 0.005

        for rarity, base_prob in base_table.items():
            if rarity not in LOOT_BY_RARITY:
                continue
            drop_chance = 0.015 + (0.02 * base_prob * enemy_level) + loot_boost_bonus
            # Pilleur passif : qualité de loot augmentée
            drop_chance *= self.loot_quality_bonus
            # Pilleur : Fièvre de l'Or (buff Pacte Doré)
            if self.pacte_fievre_turns > 0:
                drop_chance *= (1.0 + self.pacte_loot_bonus)
            # Pilleur : Fouille Accrue double la chance de loot
            if self.fouille_accrue_active:
                drop_chance *= 2.0
            if random.random() < drop_chance:
                item = random.choice(LOOT_BY_RARITY[rarity])
                loot[item] = loot.get(item, 0) + 1

        return loot
    
    def get_boss_loot(self, boss_name):
        """Génère le loot spécifique pour un boss vaincu"""
        loot = {}
        if boss_name not in BOSSES:
            return loot
        
        boss_data = BOSSES[boss_name]
        boss_loot_config = boss_data.get("boss_loot", {})
        
        if not boss_loot_config:
            return loot
        
        # Loot garanti (toujours obtenu)
        for item in boss_loot_config.get("guaranteed", []):
            if item in ITEMS:
                loot[item] = loot.get(item, 0) + 1
        
        # Loot possible (70% de chance par item)
        for item in boss_loot_config.get("possible", []):
            if item in ITEMS and random.random() < 0.70:
                loot[item] = loot.get(item, 0) + 1
        
        # Loot rare (30% de chance par item)
        for item in boss_loot_config.get("rare", []):
            if item in ITEMS and random.random() < 0.30:
                loot[item] = loot.get(item, 0) + 1
        
        return loot
    
    def equip_item(self, item_name, item_type):
        if item_type not in self.equipped:
            return t("Type d'équipement", self.language) + f" {item_type} " + t("invalide !", self.language)
        if item_name not in ITEMS:
            return t("Objet", self.language) + f" {item_name} " + t("introuvable !", self.language)
        if item_name not in self.inventory or self.inventory[item_name] <= 0:
            return t("Vous n'avez pas", self.language) + f" {item_name} " + t("dans votre inventaire !", self.language)

        item_data = ITEMS[item_name]
        if item_data.get("type") != item_type:
            return f"{item_name} " + t("n'est pas un", self.language) + f" {item_type} !"

        required_level = item_data.get("required_level", 1)
        if self.player_stats["level"] < required_level:
            return t("Niveau insuffisant pour équiper", self.language) + f" {item_name} ! (" + t("Requis: niv", self.language) + f" {required_level}, " + t("Vous: niv", self.language) + f" {self.player_stats['level']})"
        
        if self.equipped[item_type]:
            old_item = self.equipped[item_type]
            self.inventory[old_item] = self.inventory.get(old_item, 0) + 1
            if old_item in ITEMS:
                old_data = ITEMS[old_item]
                for stat_key in ["attack_bonus", "defense_bonus", "health_bonus", "mana_bonus"]:
                    if stat_key in old_data:
                        match stat_key:
                            case "attack_bonus":
                                self.player_stats["attack"] = max(0, self.player_stats.get("attack", 0) - old_data[stat_key])
                            case "defense_bonus":
                                self.player_stats["defense"] = max(0, self.player_stats.get("defense", 0) - old_data[stat_key])
                            case "health_bonus":
                                self.player_stats["max_health"] = max(1, self.player_stats.get("max_health", 100) - old_data[stat_key])
                                self.player_stats["health"] = min(self.player_stats["health"], self.player_stats["max_health"])
                            case "mana_bonus":
                                self.player_stats["max_mana"] = max(0, self.player_stats.get("max_mana", 50) - old_data[stat_key])
                                self.player_stats["mana"] = min(self.player_stats["mana"], self.player_stats["max_mana"])
        
        self.equipped[item_type] = item_name
        self.inventory[item_name] -= 1
        
        for stat_key in ["attack_bonus", "defense_bonus", "health_bonus", "mana_bonus"]:
            if stat_key in item_data:
                match stat_key:
                    case "attack_bonus":
                        self.player_stats["attack"] = self.player_stats.get("attack", 0) + item_data[stat_key]
                    case "defense_bonus":
                        self.player_stats["defense"] = self.player_stats.get("defense", 0) + item_data[stat_key]
                    case "health_bonus":
                        self.player_stats["max_health"] = self.player_stats.get("max_health", 100) + item_data[stat_key]
                        self.player_stats["health"] = self.player_stats["max_health"]
                    case "mana_bonus":
                        self.player_stats["max_mana"] = self.player_stats.get("max_mana", 50) + item_data[stat_key]
                        self.player_stats["mana"] = self.player_stats["max_mana"]
        
        return t("Vous avez équipé", self.language) + f" {item_name} !"
    
    def unequip_item(self, item_type):
        if item_type not in self.equipped:
            return t("Type d'équipement", self.language) + f" {item_type} " + t("invalide !", self.language)
        if not self.equipped[item_type]:
            return t("Vous n'avez rien d'équipé en", self.language) + f" {item_type} !"
        
        item_name = self.equipped[item_type]
        item_data = ITEMS.get(item_name, {})
        
        for stat_key in ["attack_bonus", "defense_bonus", "health_bonus", "mana_bonus"]:
            if stat_key in item_data:
                match stat_key:
                    case "attack_bonus":
                        self.player_stats["attack"] = max(0, self.player_stats.get("attack", 0) - item_data[stat_key])
                    case "defense_bonus":
                        self.player_stats["defense"] = max(0, self.player_stats.get("defense", 0) - item_data[stat_key])
                    case "health_bonus":
                        self.player_stats["max_health"] = max(1, self.player_stats.get("max_health", 100) - item_data[stat_key])
                        self.player_stats["health"] = min(self.player_stats["health"], self.player_stats["max_health"])
                    case "mana_bonus":
                        self.player_stats["max_mana"] = max(0, self.player_stats.get("max_mana", 50) - item_data[stat_key])
                        self.player_stats["mana"] = min(self.player_stats["mana"], self.player_stats["max_mana"])
        
        self.equipped[item_type] = None
        self.inventory[item_name] = self.inventory.get(item_name, 0) + 1
        return t("Vous avez déséquipé", self.language) + f" {item_name} !"
    
    def use_item(self, item_name):
        if item_name not in self.inventory or self.inventory[item_name] <= 0:
            return t("Vous n'avez pas", self.language) + f" {item_name} !"
        if item_name not in ITEMS:
            return t("Objet", self.language) + f" {item_name} " + t("introuvable !", self.language)

        item_data = ITEMS[item_name]
        if item_data.get("type") != "consumable":
            return f"{item_name} " + t("n'est pas consommable !", self.language)

        effect_message = t("Vous avez utilisé", self.language) + f" {item_name} !\n"

        if item_data.get("heal"):
            healed = self.heal(item_data["heal"])
            effect_message += t("Santé restaurée :", self.language) + f" {healed} HP\n"

        if item_data.get("mana"):
            mana_restored = min(item_data["mana"],
                              self.player_stats["max_mana"] - self.player_stats["mana"])
            self.player_stats["mana"] += mana_restored
            effect_message += t("Mana restauré :", self.language) + f" {mana_restored} MP\n"

        if item_data.get("exp_boost"):
            effect_message += t("Bonus d'expérience :", self.language) + f" {item_data['exp_boost']}%\n"

        if item_data.get("attack_boost"):
            boost = item_data["attack_boost"]
            duration = item_data.get("duration", 3)
            self.temporary_buffs["attack"] = boost
            effect_message += t("Attaque augmentée de", self.language) + f" +{boost} " + t("pendant", self.language) + f" {duration} " + t("tours !", self.language) + "\n"

        if item_data.get("defense_boost"):
            boost = item_data["defense_boost"]
            duration = item_data.get("duration", 3)
            self.temporary_buffs["defense"] = boost
            effect_message += t("Défense augmentée de", self.language) + f" +{boost} " + t("pendant", self.language) + f" {duration} " + t("tours !", self.language) + "\n"
        
        self.inventory[item_name] -= 1
        if self.inventory[item_name] <= 0:
            del self.inventory[item_name]
        
        # Mettre à jour les quêtes dynamiques (utilisation d'item consommable)
        self.update_dynamic_quest_progress("use_items")
        
        return effect_message
    
    def visit_shop(self, shop_name):
        if shop_name not in SHOPS:
            return t("Magasin", self.language) + f" {shop_name} " + t("introuvable !", self.language)
        self.current_shop = shop_name
        shop_data = SHOPS[shop_name]
        return t("Bienvenue chez", self.language) + f" {shop_name} ! {shop_data.get('description', '')}"
    
    def buy_item(self, item_name):
        if not self.current_shop or self.current_shop not in SHOPS:
            return t("Vous n'êtes pas dans un magasin !", self.language)
        shop_data = SHOPS[self.current_shop]
        shop_items = shop_data.get("items", [])
        if item_name not in shop_items:
            return f"{item_name} " + t("n'est pas vendu ici !", self.language)
        item_data = ITEMS.get(item_name, {})
        price = item_data.get("price", 0)
        if self.player_stats["gold"] < price:
            return t("Vous n'avez pas assez d'or !", self.language) + f" (" + t("Prix:", self.language) + f" {price}, " + t("Or:", self.language) + f" {self.player_stats['gold']})"
        self.player_stats["gold"] -= price
        self.inventory[item_name] = self.inventory.get(item_name, 0) + 1
        
        # Mettre à jour les quêtes dynamiques (achat d'item)
        self.update_dynamic_quest_progress("buy_items")
        
        return t("Vous avez acheté", self.language) + f" {item_name} " + t("pour", self.language) + f" {price} " + t("or !", self.language)
    
    def sell_item(self, item_name):
        if item_name not in self.inventory or self.inventory[item_name] <= 0:
            return t("Vous n'avez pas", self.language) + f" {item_name} !"
        if item_name not in ITEMS:
            return t("Objet", self.language) + f" {item_name} " + t("introuvable !", self.language)
        for slot, equipped_item in self.equipped.items():
            if equipped_item == item_name:
                return t("Vous devez d'abord déséquiper", self.language) + f" {item_name} !"
        item_data = ITEMS[item_name]
        price = item_data.get("sell_price", item_data.get("price", 10) // 2)
        self.player_stats["gold"] += price
        self.update_dynamic_quest_progress("collect_gold", price)
        self.inventory[item_name] -= 1
        if self.inventory[item_name] <= 0:
            del self.inventory[item_name]
        return t("Vous avez vendu", self.language) + f" {item_name} " + t("pour", self.language) + f" {price} " + t("or !", self.language)
    
    def get_current_shop_items(self):
        if not self.current_shop or self.current_shop not in SHOPS:
            return []
        shop_data = SHOPS[self.current_shop]
        shop_items = []
        for item_name in shop_data.get("items", []):
            item_data = ITEMS.get(item_name, {})
            shop_items.append({
                "name": item_name,
                "price": item_data.get("price", 0),
                "required_level": item_data.get("required_level", 1)
            })
        return shop_items
    
    def get_available_skills_for_level(self):
        available_skills = {}
        if self.player_class not in SKILLS:
            return available_skills
        
        # Ajouter les compétences de base (SKILLS)
        class_skills = SKILLS[self.player_class]
        current_level = self.player_stats["level"]
        for skill_name, skill_data in class_skills.items():
            unlock_level = skill_data.get("unlocked_at", 1)
            if current_level >= unlock_level:
                available_skills[skill_name] = skill_data
        
        # Ajouter les compétences progressives déjà apprises
        if self.player_class in self.skills_learned:
            for skill_name in self.skills_learned[self.player_class]:
                # Trouver les données de la compétence dans PROGRESSIVE_SKILLS
                if self.player_class in PROGRESSIVE_SKILLS:
                    for skill in PROGRESSIVE_SKILLS[self.player_class]:
                        if skill.get("name") == skill_name:
                            available_skills[skill_name] = skill
                            break
        
        return available_skills
    
    def get_upcoming_skills(self):
        upcoming = []
        if self.player_class not in PROGRESSIVE_SKILLS:
            return upcoming
        class_skills = PROGRESSIVE_SKILLS[self.player_class]
        current_level = self.player_stats["level"]
        for skill_data in class_skills:
            unlock_level = skill_data.get("level", 1)
            if current_level < unlock_level:
                upcoming.append({
                    "name": skill_data.get("name", ""),
                    "level": unlock_level,
                    "description": skill_data.get("description", ""),
                    "mana_cost": skill_data.get("mana_cost", 0),
                    "icon": skill_data.get("icon", "✨")
                })
        return upcoming
    
    def unlock_progressive_skills(self):
        if self.player_class not in PROGRESSIVE_SKILLS:
            return
        progressive = PROGRESSIVE_SKILLS[self.player_class]
        current_level = self.player_stats["level"]
        if self.player_class not in self.skills_learned:
            self.skills_learned[self.player_class] = {}
        for skill_data in progressive:
            skill_name = skill_data.get("name", "")
            unlock_level = skill_data.get("level", 1)
            if current_level >= unlock_level and skill_name:
                # Ne pas dupliquer si déjà débloquée
                if skill_name not in self.skills_learned[self.player_class]:
                    self.skills_learned[self.player_class][skill_name] = True
                    # Synchroniser avec unlocked_skills pour compatibilité
                    self.unlocked_skills[skill_name] = skill_data
    
    def get_navigation_map(self):
        if self.current_location not in LOCATIONS:
            return {
                "current": self.current_location,
                "current_name": t("Localisation inconnue", self.language),
                "available_exits": []
            }
        location_data = LOCATIONS[self.current_location]
        exits = []
        if location_data.get("exits"):
            for direction, destination in location_data["exits"].items():
                if destination in LOCATIONS:
                    dest_data = LOCATIONS[destination]
                    exits.append({
                        "direction": direction.upper(),
                        "location_id": destination,
                        "location_name": dest_data.get("name", destination),
                        "description": dest_data.get("short_description", "")
                    })
        return {
            "current": self.current_location,
            "current_name": location_data.get("name", "Unknown"),
            "available_exits": exits
        }
    
    def get_world_map(self):
        locations_map = []
        for location_id in LOCATIONS.keys():
            location_data = LOCATIONS[location_id]
            x = location_data.get("x", 50)
            y = location_data.get("y", 50)
            locations_map.append({
                "id": location_id,
                "name": location_data.get("name", location_id),
                "visited": location_id in self.visited_locations,
                "is_current": location_id == self.current_location,
                "x": x,
                "y": y
            })
        return {
            "locations": locations_map,
            "visited_count": len(self.visited_locations),
            "total_count": len(LOCATIONS)
        }
    
    def reset_game(self):
        self.__init__()
        return t("Le jeu a été réinitialisé !", self.language)
    
    def reset_health(self, reset_location=False):
        self.player_stats["health"] = self.player_stats["max_health"]
        if reset_location:
            self.current_location = GAME_CONFIG["starting_location"]
    
    def get_player_stats(self):
        stats = {
            "level": self.player_stats["level"],
            "exp": self.player_stats["exp"],
            "exp_for_next_level": self.player_stats["exp_for_next_level"],
            "health": self.player_stats["health"],
            "max_health": self.player_stats["max_health"],
            "mana": self.player_stats["mana"],
            "max_mana": self.player_stats["max_mana"],
            "attack": self.player_stats["attack"],
            "defense": self.player_stats["defense"],
            "gold": self.player_stats["gold"],
            "weapon": self.equipped.get("weapon") or t("Mains nues", self.language),
            "armor": self.equipped.get("armor") or t("Aucune", self.language),
            "accessory": self.equipped.get("accessory") or t("Aucun", self.language)
        }
        return stats
    
    def get_player_stats_display(self):
        stats = self.get_player_stats()
        display = ""
        display += f"<strong>{t('Niveau', self.language)} {stats['level']}</strong><br>"
        display += f"{t('Santé:', self.language)} {stats['health']}/{stats['max_health']}<br>"
        display += f"{t('Mana:', self.language)} {stats['mana']}/{stats['max_mana']}<br>"
        display += f"{t('Attaque:', self.language)} {stats['attack']}<br>"
        display += f"{t('Défense:', self.language)} {stats['defense']}<br>"
        display += f"{t('Or:', self.language)} {stats['gold']}<br>"
        display += f"EXP: {stats['exp']}/{stats['exp_for_next_level']}"
        return display
    
    def get_save_stats(self):
        """Retourne toutes les stats à sauvegarder (utilisé pour la réincarnation, mort, sauvegarde manuelle)"""
        return {
            # Stats de base du joueur
            'exp': self.player_stats['exp'],
            'level': self.player_stats['level'],
            'gold': self.player_stats['gold'],
            'exp_for_next_level': self.player_stats['exp_for_next_level'],
            'health': self.player_stats['health'],
            'max_health': self.player_stats['max_health'],
            'mana': self.player_stats['mana'],
            'max_mana': self.player_stats['max_mana'],
            'attack': self.player_stats['attack'],
            'defense': self.player_stats['defense'],
            
            # Inventaire et équipement
            'inventory': self.inventory.copy(),
            'equipped': self.equipped.copy(),
            
            # Position et exploration
            'current_location': self.current_location,
            'visited_locations': list(self.visited_locations) if hasattr(self, 'visited_locations') else [],
            
            # Quêtes dynamiques
            'dynamic_quest_progress': self.dynamic_quest_progress.copy(),
            'dynamic_quests_completed': self.dynamic_quests_completed.copy(),
            
            # Compétences
            'skills_learned': {k: v.copy() if isinstance(v, dict) else v for k, v in self.skills_learned.items()},
            'unlocked_skills': self.unlocked_skills.copy(),
            
            # Runes
            'rune_inventory': self.rune_inventory.copy(),
            'loot_boost_count': self.loot_boost_count,
            
            # Cartes
            'card_inventory': self.card_inventory.copy(),
            'cards_used': self.cards_used.copy(),
            
            # Système de Prestige / Réincarnation
            'prestige_level': self.prestige_level,
            'reincarnation_count': self.reincarnation_count,
            
            # Système d'Arène
            'in_arena': self.in_arena,
            'arena_wins': self.arena_wins,
            'arena_current_streak': self.arena_current_streak,
            'arena_enemies_defeated': self.arena_enemies_defeated,
            'arena_rewards': self.arena_rewards.copy(),
            
            # Statistiques de combat
            'total_enemies_defeated': self.total_enemies_defeated,
            'total_damage_dealt': self.total_damage_dealt,
            'total_damage_taken': self.total_damage_taken,
            
            # Difficulté
            'difficulty': self.difficulty
        }
    
    def load_save_stats(self, saved_stats):
        """Restaure toutes les stats depuis un dict de sauvegarde"""
        # Stats de base du joueur
        if 'exp' in saved_stats:
            self.player_stats['exp'] = saved_stats['exp']
        if 'level' in saved_stats:
            self.player_stats['level'] = saved_stats['level']
        if 'gold' in saved_stats:
            self.player_stats['gold'] = saved_stats['gold']
        if 'exp_for_next_level' in saved_stats:
            self.player_stats['exp_for_next_level'] = saved_stats['exp_for_next_level']
        if 'health' in saved_stats:
            self.player_stats['health'] = saved_stats['health']
        if 'max_health' in saved_stats:
            self.player_stats['max_health'] = saved_stats['max_health']
        if 'mana' in saved_stats:
            self.player_stats['mana'] = saved_stats['mana']
        if 'max_mana' in saved_stats:
            self.player_stats['max_mana'] = saved_stats['max_mana']
        if 'attack' in saved_stats:
            self.player_stats['attack'] = saved_stats['attack']
        if 'defense' in saved_stats:
            self.player_stats['defense'] = saved_stats['defense']
        
        # Inventaire et équipement
        if 'inventory' in saved_stats and isinstance(saved_stats['inventory'], dict):
            self.inventory = saved_stats['inventory'].copy()
        if 'equipped' in saved_stats and isinstance(saved_stats['equipped'], dict):
            self.equipped = saved_stats['equipped'].copy()
        
        # Position et exploration
        if 'current_location' in saved_stats:
            self.current_location = saved_stats['current_location']
        if 'visited_locations' in saved_stats:
            self.visited_locations = set(saved_stats['visited_locations'])
        
        # Quêtes dynamiques
        if 'dynamic_quest_progress' in saved_stats and isinstance(saved_stats['dynamic_quest_progress'], dict):
            self.dynamic_quest_progress = saved_stats['dynamic_quest_progress'].copy()
        if 'dynamic_quests_completed' in saved_stats and isinstance(saved_stats['dynamic_quests_completed'], list):
            self.dynamic_quests_completed = saved_stats['dynamic_quests_completed'].copy()
        
        # Compétences
        if 'skills_learned' in saved_stats and isinstance(saved_stats['skills_learned'], dict):
            self.skills_learned = {k: v.copy() if isinstance(v, dict) else v for k, v in saved_stats['skills_learned'].items()}
        if 'unlocked_skills' in saved_stats and isinstance(saved_stats['unlocked_skills'], dict):
            self.unlocked_skills = saved_stats['unlocked_skills'].copy()
        
        # Runes
        if 'rune_inventory' in saved_stats and isinstance(saved_stats['rune_inventory'], dict):
            self.rune_inventory = saved_stats['rune_inventory'].copy()
        if 'loot_boost_count' in saved_stats:
            self.loot_boost_count = saved_stats['loot_boost_count']
        
        # Cartes
        if 'card_inventory' in saved_stats and isinstance(saved_stats['card_inventory'], dict):
            self.card_inventory = saved_stats['card_inventory'].copy()
        if 'cards_used' in saved_stats and isinstance(saved_stats['cards_used'], list):
            self.cards_used = saved_stats['cards_used'].copy()
        
        # Système de Prestige / Réincarnation
        if 'prestige_level' in saved_stats:
            self.prestige_level = saved_stats['prestige_level']
        if 'reincarnation_count' in saved_stats:
            self.reincarnation_count = saved_stats['reincarnation_count']
        
        # Système d'Arène
        if 'in_arena' in saved_stats:
            self.in_arena = saved_stats['in_arena']
        if 'arena_wins' in saved_stats:
            self.arena_wins = saved_stats['arena_wins']
        if 'arena_current_streak' in saved_stats:
            self.arena_current_streak = saved_stats['arena_current_streak']
        if 'arena_enemies_defeated' in saved_stats:
            self.arena_enemies_defeated = saved_stats['arena_enemies_defeated']
        if 'arena_rewards' in saved_stats and isinstance(saved_stats['arena_rewards'], dict):
            self.arena_rewards = saved_stats['arena_rewards'].copy()
        
        # Statistiques de combat
        if 'total_enemies_defeated' in saved_stats:
            self.total_enemies_defeated = saved_stats['total_enemies_defeated']
        if 'total_damage_dealt' in saved_stats:
            self.total_damage_dealt = saved_stats['total_damage_dealt']
        if 'total_damage_taken' in saved_stats:
            self.total_damage_taken = saved_stats['total_damage_taken']
        
        # Difficulté
        if 'difficulty' in saved_stats:
            self.difficulty = saved_stats['difficulty']
    
    def get_inventory_info(self):
        inventory_info = {
            "items": self.inventory.copy(),
            "equipped": self.equipped.copy(),
            "inventory_count": sum(self.inventory.values())
        }
        return inventory_info
    
    def get_quests_display(self):
        return self.get_dynamic_quests_display()
    
    def close_shop(self):
        self.current_shop = None
        return t("Magasin fermé.", self.language)
    
    def talk_to_npc(self, npc_name):
        # Cas spécial : Gardien de l'Arène permet d'entrer dans l'arène
        if npc_name in ["Gardien de l'Arène", "Arena Guardian"]:
            if not self.can_enter_arena():
                return f"<p><strong>{npc_name}:</strong> " + t("Vous devez avoir au moins 1 réincarnation pour entrer dans l'arène !", self.language) + "</p>"
            
            if self.in_combat:
                return f"<p><strong>{npc_name}:</strong> " + t("Vous êtes déjà en combat !", self.language) + "</p>"
            
            # Si on n'est pas à l'arène, s'y rendre d'abord
            if self.current_location != "arene":
                move_result = self.move("arene")
                # Si le déplacement a échoué (ex: pas de sortie vers arene), retourner l'erreur
                if "ne pouvez pas" in move_result or "Vous ne pouvez pas" in move_result:
                    return f"<p><strong>{npc_name}:</strong> {move_result}</p>"
            
            if self.in_arena:
                return f"<p><strong>{npc_name}:</strong> " + t("Vous êtes déjà dans l'arène !", self.language) + "</p>"
            
            # Entrer dans l'arène
            success, message = self.enter_arena()
            if success:
                return f"<p><strong>{npc_name}:</strong> {message}</p>"
            else:
                return f"<p><strong>{npc_name}:</strong> {message}</p>"
        
        if npc_name not in NPCS_DIALOGUE:
            return f"NPC {npc_name} " + t("non trouvé.", self.language)
        dialogue_text = NPCS_DIALOGUE[npc_name]
        return f"<p><strong>{npc_name}:</strong> {dialogue_text}</p>"

    def buy_loot_boost(self):
        """Achète un boost de chance de loot (+0.5% cumulable)."""
        cost = 1000 + (self.loot_boost_count * 500)
        if self.player_stats["gold"] < cost:
            return t("Or insuffisant !", self.language) + f" (" + t("Prix:", self.language) + f" {cost} " + t("or", self.language) + ", " + t("Vous:", self.language) + f" {self.player_stats['gold']} " + t("or", self.language) + ")"
        self.player_stats["gold"] -= cost
        self.loot_boost_count += 1
        total_bonus = self.loot_boost_count * 0.5
        next_cost = 1000 + (self.loot_boost_count * 500)
        return f"🍀 {t('Chance de loot améliorée !', self.language)} +0.5% (Total: +{total_bonus}%) — {t('Prochain boost:', self.language)} {next_cost} " + t("or", self.language)

    def get_loot_boost_info(self):
        """Retourne les infos du boost de loot pour l'affichage."""
        total_bonus = self.loot_boost_count * 0.5
        next_cost = 1000 + (self.loot_boost_count * 500)
        return {
            "count": self.loot_boost_count,
            "total_bonus": total_bonus,
            "next_cost": next_cost,
            "bonus_per_level": 0.5
        }

    def rest(self):
        if self.in_combat:
            return t("Vous ne pouvez pas vous reposer pendant un combat !", self.language)

        # 50% de chance de déclencher un combat pendant le repos
        if random.random() < 0.5:
            message = t("Vous vous reposez... mais un ennemi vous surprend !", self.language) + "\n"
            fight_msg = self.start_fight()
            return message + fight_msg

        # Pas de combat : récupération totale HP et mana
        hp_missing = self.player_stats["max_health"] - self.player_stats["health"]
        mana_missing = self.player_stats["max_mana"] - self.player_stats["mana"]
        self.player_stats["health"] = self.player_stats["max_health"]
        self.player_stats["mana"] = self.player_stats["max_mana"]
        return t("Vous vous reposez...", self.language) + " " + t("Santé restaurée :", self.language) + f" {hp_missing} HP, " + t("Mana restauré :", self.language) + f" {mana_missing} MP. " + t("Récupération totale !", self.language)
    
    def use_skill(self, skill_name):
        if not self.player_class:
            return {"message": t("Vous n'avez pas de classe!", self.language), "action": "none"}
        
        # Mettre à jour les quêtes dynamiques (utilisation de compétence)
        self.update_dynamic_quest_progress("use_skills")
        
        # Vérifier d'abord dans les compétences de base (SKILLS)
        class_skills = SKILLS.get(self.player_class, {})
        if skill_name in class_skills:
            skill_data = class_skills[skill_name]
        # Sinon vérifier dans les compétences progressives déjà apprises
        elif self.player_class in self.skills_learned and skill_name in self.skills_learned[self.player_class]:
            # Trouver la définition de la compétence dans PROGRESSIVE_SKILLS
            progressive_skills = PROGRESSIVE_SKILLS.get(self.player_class, [])
            skill_data = None
            for skill in progressive_skills:
                if skill.get("name") == skill_name:
                    skill_data = skill
                    break
            if skill_data is None:
                return {"message": t("Compétence", self.language) + f" {skill_name} " + t("non trouvée!", self.language), "action": "none"}
        else:
            return {"message": t("Compétence", self.language) + f" {skill_name} " + t("non trouvée ou non débloquée!", self.language), "action": "none"}
        
        # Extraire les données de la compétence
        mana_cost = skill_data.get("mana_cost", 0)
        if self.player_stats["mana"] < mana_cost:
            return {
                "message": t("Pas assez de mana!", self.language) + f" (" + t("Besoin:", self.language) + f" {mana_cost}, Mana: {self.player_stats['mana']})",
                "action": "none",
                "skill_type": "fail"
            }
        self.player_stats["mana"] -= mana_cost
        
        # Déterminer le type d'animation selon la compétence avec match/case
        match skill_name:
            case "Éclair" | "Boule de Feu" | "Météorite" | "Tir de Précision" | "Charge Furieuse" | "Coup Mortel" | "Coup Puissant" | "Ruée d'Or" | "Double ou Rien" | "Pacte Doré" | "Coup de Chance":
                skill_type = "magic"
            case "Soin" | "Défense Renforcée" | "Esquive" | "Glaciation" | "Téléportation" | "Fouille Accrue":
                skill_type = "heal"
            case "Tir Rapide" | "Pluie de Flèches" | "Volée Explosive":
                skill_type = "rapid"
            case _:
                skill_type = "skill"
        
        # Gestion soin
        if skill_data.get("heal"):
            healed = self.heal(skill_data["heal"])
            return {
                "message": t("Vous avez utilisé", self.language) + f" {skill_name}! " + t("Santé restaurée:", self.language) + f" {healed} HP",
                "action": "heal",
                "skill_type": skill_type,
                "heal_amount": healed
            }
        
        # Gestion défense boost
        if skill_data.get("defense_boost"):
            boost = skill_data["defense_boost"]
            duration = skill_data.get("duration", 3)
            self.temporary_buffs["defense"] = boost
            return {
                "message": t("Vous avez utilisé", self.language) + f" {skill_name}! " + t("Défense augmentée de", self.language) + f" +{boost} " + t("pendant", self.language) + f" {duration} " + t("tours!", self.language),
                "action": "defense_boost",
                "skill_type": skill_type,
                "boost_amount": boost
            }
        
        # Gestion attaque boost
        if skill_data.get("attack_multiplier"):
            boost_mult = skill_data["attack_multiplier"]
            duration = skill_data.get("duration", 2)
            bonus = int(self.player_stats["attack"] * (boost_mult - 1))
            self.temporary_buffs["attack"] = bonus
            return {
                "message": t("Vous avez utilisé", self.language) + f" {skill_name}! " + t("Attaque augmentée de", self.language) + f" +{bonus} " + t("pendant", self.language) + f" {duration} " + t("tours!", self.language),
                "action": "attack_boost",
                "skill_type": skill_type,
                "boost_amount": bonus
            }
        
        # Gestion damage reduction
        if skill_data.get("damage_reduction"):
            reduction = skill_data.get("damage_reduction", 0.5)
            duration = skill_data.get("duration", 2)
            self.temporary_buffs["defense"] = int(self.player_stats.get("defense", 0) * reduction)
            return {
                "message": t("Vous avez utilisé", self.language) + f" {skill_name}! " + t("Dégâts réduits de", self.language) + f" {int(reduction * 100)}% " + t("pendant", self.language) + f" {duration} " + t("tours!", self.language),
                "action": "damage_reduction",
                "skill_type": skill_type
            }
        
        # Pilleur : Fouille Accrue (buff non-damage)
        if skill_name == "Fouille Accrue":
            self.fouille_accrue_active = True
            return {
                "message": t("Vous avez utilisé", self.language) + f" {skill_name}! " + t("Prochain kill : loot doublé et or +50% !", self.language),
                "action": "buff",
                "skill_type": skill_type
            }

        # Pilleur : Ruée d'Or (set gold multiplier)
        if skill_data.get("gold_multiplier"):
            self.gold_multiplier_next_kill = skill_data["gold_multiplier"]

        # Pilleur : Double ou Rien (set gamble flag)
        if skill_name == "Double ou Rien":
            self.double_or_nothing_active = True

        # Pilleur : Pacte Doré — sacrifice HP pour dégâts + loot garanti
        if skill_name == "Pacte Doré":
            hp_cost = int(self.player_stats["health"] * skill_data.get("hp_cost_percent", 0.30))
            hp_cost = max(1, hp_cost)
            self.player_stats["health"] -= hp_cost
            if self.player_stats["health"] <= 1:
                self.player_stats["health"] = 1

            pacte_damage = int(hp_cost * skill_data.get("damage_per_hp_lost", 3.0))
            pacte_damage += self.player_stats["attack"]

            buff_name = skill_data.get("buff_name", "Fièvre de l'Or")
            buff_duration = skill_data.get("buff_duration", 3)
            self.pacte_fievre_turns = buff_duration
            self.pacte_crit_bonus = skill_data.get("buff_crit_bonus", 0.15)
            self.pacte_loot_bonus = skill_data.get("buff_loot_bonus", 0.25)

            pacte_result = t("Vous avez utilisé", self.language) + f" {skill_name}!\n"
            pacte_result += f"🩸 {t('Sacrifice :', self.language)} -{hp_cost} HP\n"
            pacte_result += f"💥 {t('Dégâts du pacte :', self.language)} {pacte_damage}\n"
            pacte_result += f"🔥 {buff_name} {t('activé pour', self.language)} {buff_duration} {t('tours', self.language)} (+{int(self.pacte_crit_bonus*100)}% crit, +{int(self.pacte_loot_bonus*100)}% loot)\n"

            if self.in_combat and self.current_enemy:
                self.current_enemy["health"] -= pacte_damage
                total_damage = pacte_damage
                self.enemy_health = self.current_enemy.get("health", 0)

                if self.current_enemy["health"] <= 0:
                    loot = self.get_loot(self.current_enemy.get("level", 1))
                    exp_gain = self.current_enemy.get("exp_reward", 50)
                    gold_gain = self.current_enemy.get("gold_reward", 20)
                    enemy_name = self.current_enemy["name"]

                    if self.player_class == "Pilleur":
                        tresor_bonus = int(gold_gain * 0.15)
                        gold_gain += tresor_bonus
                        pacte_result += f"\n💎 {t('Trésor Vivant :', self.language)} +{tresor_bonus} " + t("or bonus !", self.language)

                    if self.fouille_accrue_active:
                        fouille_gold = int(gold_gain * 0.5)
                        gold_gain += fouille_gold
                        pacte_result += f"\n🔍 {t('Fouille Accrue :', self.language)} +{fouille_gold} " + t("or bonus !", self.language)

                    self.player_stats["gold"] += gold_gain
                    self.update_dynamic_quest_progress("kill_enemies")
                    self.update_dynamic_quest_progress("collect_gold", gold_gain)
                    self.add_exp(exp_gain)
                    self.total_enemies_defeated += 1

                    if self.current_enemy.get("is_boss"):
                        self.boss_defeated[self.current_enemy["name"]] = True

                    pacte_result += f"\n{enemy_name} " + t("a été vaincu!", self.language) + "\n"
                    pacte_result += t("Expérience gagnée:", self.language) + f" {exp_gain}, " + t("Or gagné:", self.language) + f" {gold_gain}\n"

                    # Loot garanti selon HP restant
                    hp_percent = self.player_stats["health"] / self.player_stats["max_health"]
                    if hp_percent < 0.20:
                        guaranteed_rarity = "legendaire"
                    elif hp_percent < 0.50:
                        guaranteed_rarity = "epique"
                    else:
                        guaranteed_rarity = "rare"

                    if guaranteed_rarity in LOOT_BY_RARITY:
                        guaranteed_item = random.choice(LOOT_BY_RARITY[guaranteed_rarity])
                        loot[guaranteed_item] = loot.get(guaranteed_item, 0) + 1
                        pacte_result += f"\n🩸💰 {t('Pacte Doré :', self.language)} {guaranteed_item} ({guaranteed_rarity}) — HP: {int(hp_percent*100)}%\n"

                    if loot:
                        for item, qty in loot.items():
                            self.inventory[item] = self.inventory.get(item, 0) + qty
                            pacte_result += t("Butin:", self.language) + f" {item} (x{qty})\n"

                    if self.fouille_accrue_active:
                        self.fouille_accrue_active = False

                    rune_drop = self.drop_rune(self.current_enemy.get("level", 1))
                    if rune_drop:
                        pacte_result += t("Rune :", self.language) + f" {rune_drop}\n"

                    card_drop = self.drop_card(self.current_enemy.get("level", 1), self.current_enemy.get("is_boss", False))
                    if card_drop:
                        pacte_result += f"CARTE : {card_drop}\n"

                    self.in_combat = False
                    self.current_enemy = None
                    self.enemy_health = 0
                    self.enemy_max_health = 0
                    return {
                        "message": pacte_result,
                        "action": "kill",
                        "skill_type": skill_type,
                        "total_damage": total_damage,
                        "is_critical": False,
                        "enemy_defeated": True
                    }

                # Ennemi encore vivant — riposte
                enemy_atk = self.current_enemy.get("attack", 5)
                enemy_damage = max(1, enemy_atk + random.randint(-2, 3) - self.player_stats["defense"] // 2)
                damage_taken, death_message = self.take_damage(enemy_damage)
                pacte_result += f"\n{self.current_enemy['name']} " + t("riposte et inflige", self.language) + f" {damage_taken} " + t("dégâts !", self.language)
                pacte_result += f"\n{t('Vie ennemie :', self.language)} {self.current_enemy['health']}"
                pacte_result += f"\n{t('Votre vie :', self.language)} {self.player_stats['health']}"

                if self.player_stats["health"] <= 0:
                    pacte_result += "\n" + t("Vous avez été vaincu !", self.language)
                    if death_message:
                        pacte_result += "\n" + death_message
                    self.in_combat = False
                    self.current_enemy = None
                    # En arène : ne pas réinitialiser la santé, récompenses déjà données
                    if not self.in_arena:
                        self.reset_health()
                    return {
                        "message": pacte_result,
                        "action": "skill_attack",
                        "skill_type": skill_type,
                        "total_damage": total_damage,
                        "enemy_damage": damage_taken,
                        "is_critical": False
                    }

                self.combat_turn += 1
                return {
                    "message": pacte_result,
                    "action": "skill_attack",
                    "skill_type": skill_type,
                    "total_damage": total_damage,
                    "enemy_damage": enemy_damage,
                    "is_critical": False,
                    "player_health": self.player_stats["health"],
                    "enemy_health": self.current_enemy.get("health", 0)
                }

            return {
                "message": pacte_result + " (" + t("Hors combat", self.language) + ")",
                "action": "none",
                "skill_type": skill_type
            }

        damage_multiplier = skill_data.get("damage_multiplier", 1.0)
        hits = skill_data.get("hits", 1)
        total_damage = 0

        if self.in_combat and self.current_enemy:
            result = t("Vous avez utilisé", self.language) + f" {skill_name}!\n"
            for i in range(hits):
                if not self.current_enemy or self.current_enemy["health"] <= 0:
                    break
                hit_damage = int(self.player_stats["attack"] * damage_multiplier)
                hit_damage = max(1, hit_damage - self.current_enemy.get("defense", 0) // 2)
                # Appliquer le multiplicateur de dégâts de l'arme équipée
                weapon_name = self.equipped.get("weapon")
                if weapon_name and weapon_name in ITEMS:
                    weapon_mult = ITEMS[weapon_name].get("damage_multiplier", 1.0)
                    if weapon_mult > 1.0:
                        hit_damage = int(hit_damage * weapon_mult)
                # Rune: skill_double
                if self.has_rune_buff("skill_double"):
                    skill_mult = self.get_rune_buff_value("skill_double")
                    hit_damage = int(hit_damage * skill_mult)
                self.current_enemy["health"] -= hit_damage
                total_damage += hit_damage
                result += f"Hit {i+1}: {hit_damage} " + t("dégâts", self.language) + "\n"

            # Tick des buffs de runes
            self.tick_rune_buffs()
            self.enemy_health = self.current_enemy.get("health", 0)
            result += t("Dégâts totaux:", self.language) + f" {total_damage}\n"
            
            # Déterminer si c'est un coup critique pour les compétences
            pacte_crit_skill = self.pacte_crit_bonus if self.pacte_fievre_turns > 0 else 0.0
            is_critical = random.random() < (0.15 + self.innate_crit_chance + pacte_crit_skill)
            # Pilleur : Cascade Critique sur skill
            if is_critical and self.player_class == "Pilleur" and "Cascade Critique" in self.unlocked_skills:
                heal_amount = self.heal(int(total_damage * 0.25))
                if heal_amount > 0:
                    result += f"\n⚡ {t('Cascade Critique :', self.language)} +{heal_amount} HP"
            
            if self.current_enemy["health"] <= 0:
                loot = self.get_loot(self.current_enemy.get("level", 1))
                exp_gain = self.current_enemy.get("exp_reward", 50)
                gold_gain = self.current_enemy.get("gold_reward", 20)
                enemy_name = self.current_enemy["name"]
                
                # Pilleur : Trésor Vivant (gold bonus passif inné)
                if self.player_class == "Pilleur":
                    tresor_bonus = int(gold_gain * 0.15)
                    gold_gain += tresor_bonus
                    result += f"\n💎 {t('Trésor Vivant :', self.language)} +{tresor_bonus} " + t("or bonus !", self.language)

                # Pilleur : multiplicateur d'or (Ruée d'Or)
                if self.gold_multiplier_next_kill > 1:
                    extra_gold = gold_gain * (self.gold_multiplier_next_kill - 1)
                    gold_gain += int(extra_gold)
                    ruee_or_txt = t("Ruée d'Or :", self.language)
                    result += f"\n💰 {ruee_or_txt} x{self.gold_multiplier_next_kill} " + t("or !", self.language)
                    self.gold_multiplier_next_kill = 1

                # Pilleur : Fouille Accrue or +50%
                if self.fouille_accrue_active:
                    fouille_gold = int(gold_gain * 0.5)
                    gold_gain += fouille_gold
                    result += f"\n🔍 {t('Fouille Accrue :', self.language)} +{fouille_gold} " + t("or bonus !", self.language)

                self.player_stats["gold"] += gold_gain
                self.update_dynamic_quest_progress("kill_enemies")
                self.update_dynamic_quest_progress("collect_gold", gold_gain)
                self.add_exp(exp_gain)
                self.total_enemies_defeated += 1

                if self.current_enemy.get("is_boss"):
                    self.boss_defeated[self.current_enemy["name"]] = True

                result += f"\n{self.current_enemy['name']} " + t("a été vaincu!", self.language) + "\n"
                result += t("Expérience gagnée:", self.language) + f" {exp_gain}, " + t("Or gagné:", self.language) + f" {gold_gain}\n"

                # Pilleur : Double ou Rien sur le loot (via skill)
                if self.double_or_nothing_active:
                    self.double_or_nothing_active = False
                    if random.random() < 0.5:
                        for item, qty in loot.items():
                            loot[item] = qty * 2
                        result += f"\n🎲 {t('Double ou Rien : DOUBLE ! Loot doublé !', self.language)}\n"
                    else:
                        loot = {}
                        result += f"\n🎲 {t('Double ou Rien : RIEN ! Loot perdu...', self.language)}\n"

                if loot:
                    for item, qty in loot.items():
                        self.inventory[item] = self.inventory.get(item, 0) + qty
                        result += t("Butin:", self.language) + f" {item} (x{qty})\n"

                # Pilleur : Fouille Accrue — reset après kill
                if self.fouille_accrue_active:
                    self.fouille_accrue_active = False

                rune_drop = self.drop_rune(self.current_enemy.get("level", 1))
                if rune_drop:
                    result += t("Rune :", self.language) + f" {rune_drop}\n"

                card_drop = self.drop_card(self.current_enemy.get("level", 1), self.current_enemy.get("is_boss", False))
                if card_drop:
                    result += f"CARTE : {card_drop}\n"

                self.in_combat = False
                self.current_enemy = None
                self.enemy_health = 0
                self.enemy_max_health = 0
                return {
                    "message": result,
                    "action": "kill",
                    "skill_type": skill_type,
                    "total_damage": total_damage,
                    "is_critical": is_critical,
                    "enemy_defeated": True
                }
            # L'ennemi riposte si encore en vie
            enemy_atk = self.current_enemy.get("attack", 5)
            weaken_val = self.get_rune_buff_value("enemy_weaken")
            if weaken_val > 0:
                enemy_atk = max(1, enemy_atk - weaken_val)

            enemy_damage = enemy_atk + random.randint(-2, 3)
            player_defense = self.player_stats["defense"]
            def_boost = self.get_rune_buff_value("defense_boost") + self.get_rune_buff_value("all_boost")
            if self.has_rune_buff("berserk"):
                berserk_penalty = RUNE_RECIPES.get("Fureur Primale", {}).get("penalty", 10)
                def_boost -= berserk_penalty
            enemy_damage = max(1, enemy_damage - (player_defense + def_boost) // 2)

            damage_taken, death_message = self.take_damage(enemy_damage)
            result += f"\n{self.current_enemy['name']} " + t("riposte et inflige", self.language) + f" {damage_taken} " + t("dégâts !", self.language)

            if self.player_stats['health'] <= 0:
                result += "\n" + t("Vous avez été vaincu !", self.language)
                if death_message:
                    result += "\n" + death_message
                self.in_combat = False
                self.current_enemy = None
                self.enemy_health = 0
                self.enemy_max_health = 0
                # En arène : ne pas réinitialiser la santé
                if not self.in_arena:
                    self.reset_health()
                return {
                    "message": result,
                    "action": "skill_attack",
                    "skill_type": skill_type,
                    "total_damage": total_damage,
                    "enemy_damage": damage_taken,
                    "is_critical": is_critical,
                    "hits": hits,
                    "player_health": self.player_stats['health'],
                    "enemy_health": self.enemy_health
                }

            # Tick Fièvre de l'Or (Pacte Doré)
            if self.pacte_fievre_turns > 0:
                self.pacte_fievre_turns -= 1
            self.combat_turn += 1
            return {
                "message": result,
                "action": "skill_attack",
                "skill_type": skill_type,
                "total_damage": total_damage,
                "enemy_damage": enemy_damage,
                "is_critical": is_critical,
                "hits": hits,
                "player_health": self.player_stats['health'],
                "enemy_health": self.current_enemy.get("health", 0)
            }
        return {
            "message": t("Vous avez utilisé", self.language) + f" {skill_name}! (" + t("Hors combat", self.language) + ")",
            "action": "none",
            "skill_type": skill_type
        }
    
    def flee_combat(self):
        if not self.in_combat or not self.current_enemy:
            return t("Vous n'êtes pas en combat!", self.language)
        if random.random() < 0.5:
            self.in_combat = False
            self.current_enemy = None
            self.enemy_health = 0
            self.enemy_max_health = 0
            return t("Vous avez réussi à fuir!", self.language)
        enemy_damage = self.current_enemy.get("attack", 5) + random.randint(-2, 3)
        damage_taken, death_message = self.take_damage(enemy_damage)
        flee_message = t("Vous n'avez pas pu fuir!", self.language) + " " + t("L'ennemi vous a infligé", self.language) + f" {damage_taken} " + t("dégâts.", self.language)
        if death_message:
            flee_message += "\n" + death_message
        return flee_message
    
    def drop_item(self, item_name):
        if item_name not in self.inventory or self.inventory[item_name] <= 0:
            return False
        self.inventory[item_name] -= 1
        if self.inventory[item_name] <= 0:
            del self.inventory[item_name]
        return True
    
    def set_difficulty(self, difficulty):
        if difficulty not in DIFFICULTY_SETTINGS:
            return t("Difficulté invalide!", self.language)
        self.difficulty = difficulty

        # Utilisation de match/case pour les paramètres de difficulté
        match difficulty:
            case "facile":
                self.boss_spawn_chance = 0.05
            case "moyen":
                self.boss_spawn_chance = 0.15
            case "difficile":
                self.boss_spawn_chance = 0.30

        return t("Difficulté définie à", self.language) + f" {difficulty}!"
        

    # ==================== SYSTÈME DE QUÊTES DYNAMIQUES ====================    
    # ==================== SYSTÈME DE QUÊTES DYNAMIQUES ====================
    
    def generate_dynamic_quests(self):
        """Génère de nouvelles quêtes dynamiques adaptées au niveau du joueur"""
        if self.player_stats["level"] < DYNAMIC_QUESTS_CONFIG.get("min_level_for_reset", 5):
            return
        
        # Effacer les anciennes quêtes dynamiques
        self.dynamic_quests = {}
        self.dynamic_quest_progress = {}
        
        # Sélectionner des templates aléatoires
        from datetime import datetime
        import random
        
        player_level = self.player_stats["level"]
        max_quests = DYNAMIC_QUESTS_CONFIG.get("max_active_quests", 3)
        
        # Obtenir les templates pondérés
        templates = list(DYNAMIC_QUEST_TEMPLATES.keys())
        weights = DYNAMIC_QUESTS_CONFIG.get("template_weights", {})
        default_weight = 1
        
        # Créer une liste pondérée
        weighted_templates = []
        for template in templates:
            weight = weights.get(template, default_weight)
            weighted_templates.extend([template] * weight)
        
        # Sélectionner des templates uniques
        selected_templates = []
        while len(selected_templates) < max_quests and weighted_templates:
            template = random.choice(weighted_templates)
            if template not in selected_templates:
                selected_templates.append(template)
                weighted_templates.remove(template)
        
        # Générer les quêtes à partir des templates
        for template_name in selected_templates:
            template = DYNAMIC_QUEST_TEMPLATES[template_name]
            quest_id = f"dynamic_{template_name}_{datetime.now().timestamp()}"
            
            # Calculer les objectifs et récompenses basés sur le niveau
            target_count = template["target_count_formula"](player_level)
            reward_exp = template["reward_exp_formula"](player_level)
            reward_gold = template["reward_gold_formula"](player_level)
            reward_item = None
            if template["reward_item_formula"]:
                reward_item = template["reward_item_formula"](player_level)
            
            # Créer la quête
            self.dynamic_quests[quest_id] = {
                "template": template_name,
                "type": template["type"],
                "target_count": target_count,
                "reward_exp": reward_exp,
                "reward_gold": reward_gold,
                "reward_item": reward_item,
                "description": template["description_template"].format(count=target_count, level=player_level),
                "icon": template["icon"],
                "created_at": datetime.now()
            }
            self.dynamic_quest_progress[quest_id] = 0
        
        self.last_quest_reset = datetime.now()
    
    def reset_dynamic_quests(self):
        """Reset les quêtes dynamiques (appelé manuellement ou automatiquement)"""
        from datetime import datetime, timedelta
        
        # Vérifier si on peut reset (cooldown)
        cooldown_hours = DYNAMIC_QUESTS_CONFIG.get("cooldown_hours", 168)
        if self.last_quest_reset:
            time_since_reset = datetime.now() - self.last_quest_reset
            if time_since_reset < timedelta(hours=cooldown_hours):
                # Pas encore le temps de reset
                remaining = timedelta(hours=cooldown_hours) - time_since_reset
                hours_remaining = int(remaining.total_seconds() / 3600)
                return f"Trop tôt pour reset! Attendez encore {hours_remaining} heures."
        
        # Générer de nouvelles quêtes
        self.generate_dynamic_quests()
        return "Quêtes dynamiques réinitialisées!"
    
    def update_dynamic_quest_progress(self, action_type, value=1):
        """Met à jour la progression des quêtes dynamiques"""
        for quest_id, quest in self.dynamic_quests.items():
            if quest["type"] == action_type:
                self.dynamic_quest_progress[quest_id] = self.dynamic_quest_progress.get(quest_id, 0) + value
    
    def complete_dynamic_quest(self, quest_id):
        """Essaie de compléter une quête dynamique"""
        if quest_id not in self.dynamic_quests:
            return False, "Quête introuvable"
        
        if quest_id in self.dynamic_quests_completed:
            return False, "Quête déjà complétée"
        
        quest = self.dynamic_quests[quest_id]
        progress = self.dynamic_quest_progress.get(quest_id, 0)
        
        if progress < quest["target_count"]:
            return False, f"Il reste {quest['target_count'] - progress} à accomplir"
        
        # Marquer comme complétée
        self.dynamic_quests_completed.append(quest_id)
        
        # Donner les récompenses
        exp_reward = quest.get("reward_exp", 0)
        gold_reward = quest.get("reward_gold", 0)
        reward_item = quest.get("reward_item")
        
        self.add_exp(exp_reward)
        self.player_stats["gold"] += gold_reward
        
        if reward_item and reward_item in ITEMS:
            self.inventory[reward_item] = self.inventory.get(reward_item, 0) + 1
        
        # Supprimer la quête des actives
        del self.dynamic_quests[quest_id]
        del self.dynamic_quest_progress[quest_id]
        
        return True, f"Quête '{quest['template']}' complétée! +{exp_reward} XP, +{gold_reward} or"
    
    def get_dynamic_quests_display(self):
        """Retourne les quêtes dynamiques pour l'affichage"""
        quests_display = []
        for quest_id, quest in self.dynamic_quests.items():
            progress = self.dynamic_quest_progress.get(quest_id, 0)
            quests_display.append({
                "id": quest_id,
                "template": quest["template"],
                "description": quest["description"],
                "icon": quest["icon"],
                "progress": progress,
                "target": quest["target_count"],
                "reward_exp": quest["reward_exp"],
                "reward_gold": quest["reward_gold"],
                "reward_item": quest.get("reward_item"),
                "is_complete": progress >= quest["target_count"]
            })
        return quests_display
    
    def check_dynamic_quests_auto_reset(self):
        """Vérifie si les quêtes doivent être reset automatiquement"""
        from datetime import datetime, timedelta
        
        if self.player_stats["level"] < DYNAMIC_QUESTS_CONFIG.get("min_level_for_reset", 5):
            return
        
        if self.last_quest_reset is None:
            # Première fois, générer des quêtes
            self.generate_dynamic_quests()
            return
        
        reset_type = DYNAMIC_QUESTS_CONFIG.get("reset_type", "weekly")
        cooldown_hours = DYNAMIC_QUESTS_CONFIG.get("cooldown_hours", 168)
        
        time_since_reset = datetime.now() - self.last_quest_reset
        
        if time_since_reset >= timedelta(hours=cooldown_hours):
            self.generate_dynamic_quests()
    
    def check_win(self):
        if self.player_stats["level"] >= 50:
            self.game_won = True
        if len(self.boss_defeated) >= len(BOSSES):
            self.game_won = True
        return self.game_won

    # ==================== SYSTÈME DE RUNES ====================

    def toggle_runes(self):
        self.show_runes = not self.show_runes
        return self.show_runes

    def drop_rune(self, enemy_level):
        """Tente de faire tomber une rune après un combat."""
        if random.random() > RUNE_DROP_CHANCE:
            return None
        rune_name = random.choice(list(RUNES.keys()))
        # Rareté basée sur le niveau de l'ennemi
        weights = []
        for rarity_data in RUNE_RARITIES.values():
            weights.append(rarity_data["drop_weight"])
        # Ennemis de haut niveau = plus de chance de runes majeures/anciennes
        if enemy_level >= 15:
            weights = [40, 35, 25]
        elif enemy_level >= 8:
            weights = [50, 35, 15]
        rarity = random.choices(list(RUNE_RARITIES.keys()), weights=weights, k=1)[0]
        rune_key = f"{rune_name}|{rarity}"
        self.rune_inventory[rune_key] = self.rune_inventory.get(rune_key, 0) + 1
        rune_data = RUNES[rune_name]
        rarity_data = RUNE_RARITIES[rarity]
        return f"{rarity_data['icon']} {rune_data['icon']} {rune_name} ({rarity})"

    def craft_rune(self, recipe_name):
        """Combine 2 runes pour créer un buff temporaire."""
        if recipe_name not in RUNE_RECIPES:
            return t("Recette inconnue !", self.language)
        recipe = RUNE_RECIPES[recipe_name]
        needed_runes = recipe["runes"]
        # Vérifier que le joueur possède les runes requises (toute rareté)
        found_runes = []
        used_keys = []
        for needed in needed_runes:
            best_key = None
            best_mult = 0
            for key, qty in self.rune_inventory.items():
                rune_name = key.split("|")[0]
                rune_rarity = key.split("|")[1]
                if rune_name == needed and qty > 0:
                    mult = RUNE_RARITIES[rune_rarity]["multiplier"]
                    if mult > best_mult:
                        best_mult = mult
                        best_key = key
            if best_key:
                found_runes.append(best_key)
                used_keys.append(best_key)
            else:
                return t("Rune manquante :", self.language) + f" {needed}"
        if len(found_runes) < len(needed_runes):
            return t("Runes insuffisantes pour cette recette.", self.language)
        # Consommer les runes
        best_multiplier = 1.0
        for key in used_keys:
            rune_rarity = key.split("|")[1]
            best_multiplier = max(best_multiplier, RUNE_RARITIES[rune_rarity]["multiplier"])
            self.rune_inventory[key] -= 1
            if self.rune_inventory[key] <= 0:
                del self.rune_inventory[key]
        # Créer le buff
        buff = {
            "name": recipe_name,
            "icon": recipe["icon"],
            "effect": recipe["effect"],
            "value": int(recipe["value"] * best_multiplier),
            "duration": recipe["duration"],
            "turns_left": recipe["duration"],
            "combat_text": recipe["combat_text"]
        }
        # Remplacer ou ajouter le buff
        self.active_rune_buffs = [b for b in self.active_rune_buffs if b["name"] != recipe_name]
        self.active_rune_buffs.append(buff)
        mult_text = f" (x{best_multiplier})" if best_multiplier > 1.0 else ""
        return f"{recipe['icon']} {recipe_name} " + t("activé pour", self.language) + f" {recipe['duration']} " + t("tours", self.language) + f"{mult_text} !"

    def get_rune_buff_summary(self):
        """Retourne un résumé des buffs de runes actifs."""
        return [{"name": b["name"], "icon": b["icon"], "turns_left": b["turns_left"]}
                for b in self.active_rune_buffs]

    def tick_rune_buffs(self):
        """Réduit la durée des buffs de runes d'un tour."""
        for buff in self.active_rune_buffs:
            buff["turns_left"] -= 1
        self.active_rune_buffs = [b for b in self.active_rune_buffs if b["turns_left"] > 0]

    def get_rune_buff_value(self, effect_type):
        """Retourne la valeur cumulée d'un type d'effet de rune."""
        total = 0
        for buff in self.active_rune_buffs:
            if buff["effect"] == effect_type:
                total += buff["value"]
        return total

    def has_rune_buff(self, effect_type):
        """Vérifie si un type de buff de rune est actif."""
        return any(b["effect"] == effect_type for b in self.active_rune_buffs)

    def consume_rune_buff(self, effect_type):
        """Consomme un buff de rune à usage unique."""
        self.active_rune_buffs = [b for b in self.active_rune_buffs if b["effect"] != effect_type]

    def get_runes_display(self):
        """Retourne les données de runes pour l'affichage."""
        inventory = []
        for key, qty in self.rune_inventory.items():
            parts = key.split("|")
            rune_name = parts[0]
            rune_rarity = parts[1] if len(parts) > 1 else "mineure"
            rune_data = RUNES.get(rune_name, {})
            rarity_data = RUNE_RARITIES.get(rune_rarity, {})
            inventory.append({
                "key": key,
                "name": rune_name,
                "icon": rune_data.get("icon", "?"),
                "rarity": rune_rarity,
                "rarity_icon": rarity_data.get("icon", ""),
                "description": rune_data.get("description", ""),
                "quantity": qty
            })
        recipes = []
        for name, data in RUNE_RECIPES.items():
            can_craft = True
            for needed in data["runes"]:
                has_it = any(k.split("|")[0] == needed and v > 0 for k, v in self.rune_inventory.items())
                if not has_it:
                    can_craft = False
                    break
            recipes.append({
                "name": name,
                "icon": data["icon"],
                "description": data["description"],
                "runes": [RUNES.get(r, {}).get("icon", "?") + " " + r.replace("Rune de ", "") for r in data["runes"]],
                "effect": data["effect"],
                "value": data["value"],
                "duration": data["duration"],
                "can_craft": can_craft
            })
        return {
            "inventory": inventory,
            "recipes": recipes,
            "active_buffs": self.active_rune_buffs
        }

    # ==================== SYSTÈME DE CARTES ====================

    def drop_card(self, enemy_level, is_boss=False):
        """Tente de faire tomber une carte après un combat."""
        # Chance de base + loot boost du Colporteur + bonus légendaire
        base_chance = CARD_DROP_CHANCE
        loot_boost_bonus = self.loot_boost_count * 0.005
        # Bonus légendaire : basé sur la probabilité légendaire de base
        legendary_prob = 0.05
        legendary_bonus = 0.01 * legendary_prob * enemy_level

        drop_chance = base_chance + loot_boost_bonus + legendary_bonus
        if is_boss:
            drop_chance *= CARD_BOSS_MULTIPLIER

        if random.random() >= drop_chance:
            return None

        # Sélectionner une carte selon la rareté
        # Plus l'ennemi est fort, plus les cartes épiques/légendaires sont probables
        if enemy_level >= 20 or (is_boss and random.random() < 0.3):
            possible = [name for name, data in CARDS.items() if data['rarity'] in ('epique', 'legendaire')]
        elif enemy_level >= 10 or is_boss:
            possible = [name for name, data in CARDS.items() if data['rarity'] in ('rare', 'epique')]
        else:
            possible = [name for name, data in CARDS.items() if data['rarity'] == 'rare']

        if not possible:
            return None

        card_name = random.choice(possible)
        self.card_inventory[card_name] = self.card_inventory.get(card_name, 0) + 1
        card_data = CARDS[card_name]
        return f"{card_data['icon']} {card_name}"

    def use_card(self, card_name):
        """Utilise une carte pour appliquer son bonus permanent."""
        if card_name not in CARDS:
            return t("Carte inconnue !", self.language)
        if card_name not in self.card_inventory or self.card_inventory[card_name] <= 0:
            return t("Vous n'avez pas de", self.language) + f" {card_name} !"

        card_data = CARDS[card_name]
        stat = card_data["stat"]
        value = card_data["value"]

        # Consommer la carte
        self.card_inventory[card_name] -= 1
        if self.card_inventory[card_name] <= 0:
            del self.card_inventory[card_name]

        # Appliquer le bonus permanent
        if stat == "loot_boost":
            self.loot_boost_count += int(value / 0.5) if value >= 0.5 else 1
            self.cards_used.append(card_name)
            return f"{card_data['icon']} {card_name} " + t("utilisée !", self.language) + " " + t("Chance de loot", self.language) + f" +{value}% " + t("permanente !", self.language)
        elif stat == "max_health":
            self.player_stats["max_health"] += value
            self.player_stats["health"] += value
        elif stat == "max_mana":
            self.player_stats["max_mana"] += value
            self.player_stats["mana"] += value
        elif stat == "attack":
            self.player_stats["attack"] += value
        elif stat == "defense":
            self.player_stats["defense"] += value

        self.cards_used.append(card_name)
        stat_names = {"attack": t("Attaque", self.language), "defense": t("Défense", self.language), "max_health": t("PV max", self.language), "max_mana": t("Mana max", self.language)}
        return f"{card_data['icon']} {card_name} " + t("utilisée !", self.language) + f" {stat_names.get(stat, stat)} +{value} " + t("permanent !", self.language)

    def get_cards_display(self):
        """Retourne les cartes pour l'affichage."""
        cards = []
        for name, qty in self.card_inventory.items():
            data = CARDS.get(name, {})
            cards.append({
                "name": name,
                "icon": data.get("icon", "🃏"),
                "rarity": data.get("rarity", "rare"),
                "description": data.get("description", ""),
                "lore": data.get("lore", ""),
                "quantity": qty,
                "stat": data.get("stat", ""),
                "value": data.get("value", 0)
            })
        return cards

    # ==================== SYSTÈME DE SCORE ====================

    def get_score_details(self):
        """Calcule le détail du score par catégorie."""
        details = {}

        details[t("Niveau", self.language)] = {
            "value": self.player_stats["level"],
            "points": self.player_stats["level"] * 100,
            "icon": "⭐"
        }

        details[t("Ennemis vaincus", self.language)] = {
            "value": self.total_enemies_defeated,
            "points": self.total_enemies_defeated * 10,
            "icon": "⚔️"
        }

        details[t("Boss vaincus", self.language)] = {
            "value": len(self.boss_defeated),
            "points": len(self.boss_defeated) * 500,
            "icon": "👹"
        }

        details[t("Quêtes complétées", self.language)] = {
            "value": len(self.dynamic_quests_completed),
            "points": len(self.dynamic_quests_completed) * 200,
            "icon": "📜"
        }

        details[t("Or accumulé", self.language)] = {
            "value": self.player_stats["gold"],
            "points": self.player_stats["gold"] // 5,
            "icon": "💰"
        }

        details[t("Dégâts infligés", self.language)] = {
            "value": self.total_damage_dealt,
            "points": int(self.total_damage_dealt * 0.5),
            "icon": "💥"
        }

        legendary_count = sum(
            1 for item, qty in self.inventory.items()
            if item in ITEMS and ITEMS[item].get("rarity") == "legendaire"
            for _ in range(qty)
        )
        for slot, equipped_item in self.equipped.items():
            if equipped_item and equipped_item in ITEMS and ITEMS[equipped_item].get("rarity") == "legendaire":
                legendary_count += 1

        details[t("Items légendaires", self.language)] = {
            "value": legendary_count,
            "points": legendary_count * 300,
            "icon": "🏆"
        }

        details[t("Cartes utilisées", self.language)] = {
            "value": len(self.cards_used),
            "points": len(self.cards_used) * 150,
            "icon": "🃏"
        }

        runes_count = sum(self.rune_inventory.values())
        details[t("Runes collectées", self.language)] = {
            "value": runes_count,
            "points": runes_count * 20,
            "icon": "🔮"
        }

        return details

    def get_score(self):
        """Retourne le score total du joueur."""
        details = self.get_score_details()
        total = sum(d["points"] for d in details.values())

        if total < 500:
            rank = t("Novice", self.language)
            rank_icon = "🥉"
        elif total < 2000:
            rank = t("Apprenti", self.language)
            rank_icon = "🥉"
        elif total < 5000:
            rank = t("Aventurier", self.language)
            rank_icon = "🥈"
        elif total < 10000:
            rank = t("Héros", self.language)
            rank_icon = "🥈"
        elif total < 20000:
            rank = t("Champion", self.language)
            rank_icon = "🥇"
        elif total < 40000:
            rank = t("Légende", self.language)
            rank_icon = "🥇"
        else:
            rank = t("Dieu", self.language)
            rank_icon = "👑"

        return {
            "total": total,
            "rank": rank,
            "rank_icon": rank_icon,
            "details": details
        }

    def toggle_options(self):
        self.show_options = not self.show_options
        return self.show_options
    
    def toggle_inventory(self):
        self.show_inventory = not self.show_inventory
        return self.show_inventory
    
    def toggle_quests(self):
        self.show_quests = not self.show_quests
        return self.show_quests
    
    def toggle_skills(self):
        self.show_skills = not self.show_skills
        return self.show_skills
