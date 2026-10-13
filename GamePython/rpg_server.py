#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Serveur Flask pour le RPG Text-Based GamePython
Lance le jeu d'aventure en ligne
"""

from flask import Flask, render_template, request, session, redirect, url_for, jsonify, send_file
from game_engine import GameEngine
from game_config import GAME_CONFIG, ITEMS, CLASSES, SKILLS, LOCATIONS, SHOPS
from translations import t
import threading
import os
import json
import io

app = Flask(__name__, template_folder='templates')
app.secret_key = 'gamepython_secret_rpg_key_2024'

# Dictionnaire des sessions de jeu
game_sessions = {}


def get_game_session():
    """Obtient ou crée une session de jeu pour l'utilisateur"""
    if 'game_id' not in session:
        session['game_id'] = os.urandom(16).hex()
    
    game_id = session['game_id']
    
    if game_id not in game_sessions:
        game_sessions[game_id] = GameEngine()
        
        # Charger la classe si sauvegardée
        if 'player_class' in session:
            game_sessions[game_id].set_class(session['player_class'])
        
        # Charger les stats sauvegardées si elles existent
        if 'saved_stats' in session:
            saved_stats = session['saved_stats']
            # Utiliser la fonction centralisée pour restaurer toutes les stats
            game_sessions[game_id].load_save_stats(saved_stats)
            
            # Gérer les cas spéciaux (rétrocompatibilité)
            # Charger l'inventaire avec gestion des anciens formats (liste vs dict)
            saved_inventory = saved_stats.get('inventory', {})
            if isinstance(saved_inventory, list):
                game_sessions[game_id].inventory = {}
                for item in saved_inventory:
                    game_sessions[game_id].inventory[item] = game_sessions[game_id].inventory.get(item, 0) + 1
            
            # Charger l'équipement
            saved_equipped = saved_stats.get('equipped', {})
            if isinstance(saved_equipped, dict):
                for slot in game_sessions[game_id].equipped:
                    game_sessions[game_id].equipped[slot] = saved_equipped.get(slot, None)

            saved_cards = saved_stats.get('card_inventory', {})
            if isinstance(saved_cards, dict):
                game_sessions[game_id].card_inventory = saved_cards.copy()
            saved_cards_used = saved_stats.get('cards_used', [])
            if isinstance(saved_cards_used, list):
                game_sessions[game_id].cards_used = saved_cards_used.copy()

            # Restaurer les stats supplémentaires (aussi dans saved_stats maintenant)
            extra = session.get('extra_save', {})
            game_sessions[game_id].total_enemies_defeated = saved_stats.get('total_enemies_defeated', extra.get('total_enemies_defeated', 0))
            game_sessions[game_id].total_damage_dealt = saved_stats.get('total_damage_dealt', extra.get('total_damage_dealt', 0))
            game_sessions[game_id].total_damage_taken = saved_stats.get('total_damage_taken', extra.get('total_damage_taken', 0))
            game_sessions[game_id].boss_defeated = saved_stats.get('boss_defeated', extra.get('boss_defeated', {}))
            game_sessions[game_id].difficulty = saved_stats.get('difficulty', extra.get('difficulty', 'moyen'))

        # Charger les compétences sauvegardées après chaque action (clé séparée)
        saved_skills = session.get('saved_skills')
        if saved_skills and isinstance(saved_skills, dict):
            saved_sl = saved_skills.get('skills_learned', {})
            if isinstance(saved_sl, dict) and saved_sl:
                game_sessions[game_id].skills_learned = {k: v.copy() if isinstance(v, dict) else v for k, v in saved_sl.items()}
            saved_us = saved_skills.get('unlocked_skills', {})
            if isinstance(saved_us, dict) and saved_us:
                game_sessions[game_id].unlocked_skills = saved_us.copy()

        # Re-débloquer les compétences progressives selon le niveau actuel
        game_sessions[game_id].unlock_progressive_skills()

    # Si le joueur a choisi une classe mais que le GameEngine n'en a pas encore,
    # l'appliquer maintenant (cas où le GameEngine a été créé avant le choix de classe)
    game = game_sessions[game_id]
    if 'player_class' in session and game.player_class is None:
        game.set_class(session['player_class'])
        # Re-débloquer les compétences après avoir défini la classe
        game.unlock_progressive_skills()

    game_sessions[game_id].language = session.get('language', 'fr')
    return game_sessions[game_id]


@app.route('/choose-class/<class_name>')
def choose_class(class_name):
    """Permet au joueur de choisir sa classe"""
    session['player_class'] = class_name
    session.modified = True
    return redirect(url_for('index'))


@app.route('/')
def index():
    """Page d'accueil du jeu"""
    game = get_game_session()
    
    game_state = {
        'player_stats': game.get_player_stats(),
        'player_class': game.player_class,
        'location_description': game.get_location_description(),
        'available_actions': game.get_available_actions(),
        'navigation_map': game.get_navigation_map(),
        'world_map': game.get_world_map(),
        'in_combat': game.in_combat,
        'current_enemy': game.current_enemy,
        'enemy_health': getattr(game, 'enemy_health', 0),
        'enemy_max_health': getattr(game, 'enemy_max_health', 0),
        'enemy_level': getattr(game, 'enemy_level', 1),
        'enemy_attack': getattr(game, 'enemy_attack', 0),
        'enemy_defense': getattr(game, 'enemy_defense', 0),
        'is_boss_fight': getattr(game, 'is_boss_fight', False),
        'current_boss': getattr(game, 'current_boss', None),
        'game_over': game.game_over,
        'game_won': game.game_won,
        'last_message': session.get('last_message', t('Bienvenue dans GamePython RPG Adventure!', game.language)),
        'inventory': game.inventory,
        'gold': game.player_stats['gold'],
        'current_shop': game.current_shop,
        'shop_items': game.get_current_shop_items(),
        'difficulty': game.difficulty,
        'show_options': game.show_options,
        'show_inventory': game.show_inventory,
        'equipped': game.equipped,
        'all_items': ITEMS,
        'classes': CLASSES,
        'player_class_chosen': 'player_class' in session,
        'temporary_buffs': game.temporary_buffs,
        'show_quests': game.show_quests,
        'show_skills': game.show_skills,
        'quests': game.get_quests_display(),
        'completed_quests_count': len(game.dynamic_quests_completed),
        'player_skills': game.get_available_skills_for_level(),
        'upcoming_skills': game.get_upcoming_skills(),
        'unlocked_skills': game.unlocked_skills,
        'combat_animation': session.get('combat_animation'),
        'current_location_npcs': LOCATIONS.get(game.current_location, {}).get('npcs', []),
        'current_location_shops': LOCATIONS.get(game.current_location, {}).get('shops', []),
        'all_shops': SHOPS,
        'runes_data': game.get_runes_display(),
        'show_runes': game.show_runes,
        'rune_buffs': game.get_rune_buff_summary(),
        'loot_boost_info': game.get_loot_boost_info(),
        'cards_data': game.get_cards_display(),
        'cards_used': game.cards_used,
        'score': game.get_score(),
        'language': session.get('language', 'fr'),
        'dynamic_quests': game.get_dynamic_quests_display(),
        'show_dynamic_quests': True,
        # Système de Prestige / Arène
        'prestige_level': game.prestige_level,
        'reincarnation_count': game.reincarnation_count,
        'arena_wins': game.arena_wins,
        'arena_current_streak': game.arena_current_streak,
        'in_arena': game.in_arena,
        'arena_rewards': game.arena_rewards,
        'arena_enemies_defeated': game.arena_enemies_defeated,
        'last_arena_message': game.last_arena_message,
        'can_reincarnate': game.player_stats.get('level', 0) >= 30,
        'can_enter_arena': game.can_enter_arena() and game.current_location == 'arene'
    }

    if 'last_message' in session:
        del session['last_message']
    
    # Réinitialiser last_arena_message après l'avoir envoyé au template
    # (il sera affiché une seule fois)
    game.last_arena_message = None

    return render_template('game.html', game_state=game_state, t=t)


@app.route('/action', methods=['POST'])
def action():
    """Gere les actions du joueur"""
    game = get_game_session()
    
    action_type = request.form.get('action_type') or ""
    action_value = request.form.get('action_value') or ""
    message = ""
    
    # Utilisation de match/case pour une meilleure lisibilité (Python 3.10+)
    match action_type:
        # Actions de déplacement et exploration
        case 'move':
            message = game.move(action_value)
            game.close_shop()
        case 'fight':
            message = game.start_fight(action_value)
            game.close_shop()
        case 'explore':
            message = game.explore_location()
            game.close_shop()
        case 'use_portal':
            message = game.use_portal(action_value)
            game.close_shop()
        case 'rest':
            message = game.rest()
            game.close_shop()
        
        # Actions sociales
        case 'talk':
            message = game.talk_to_npc(action_value)
        case 'visit_shop':
            message = game.visit_shop(action_value)
        
        # Actions de combat
        case 'attack':
            result = game.attack_enemy()
            if isinstance(result, dict):
                message = result.get("message", "")
                if result.get("action") in ["attack", "kill"]:
                    session['combat_animation'] = {
                        "type": "attack",
                        "player_damage": result.get("player_damage", 0),
                        "enemy_damage": result.get("enemy_damage", 0),
                        "is_critical": result.get("is_critical", False)
                    }
            else:
                message = result
        
        case 'use_skill':
            result = game.use_skill(action_value)
            if isinstance(result, dict):
                message = result.get("message", "")
                # Utilisation de match/case pour les actions de compétence
                match result.get("action"):
                    case "skill_attack" | "heal" | "defense_boost" | "attack_boost" | "damage_reduction":
                        session['combat_animation'] = {
                            "type": result.get("skill_type", "skill"),
                            "action": result.get("action", "skill"),
                            "total_damage": result.get("total_damage", 0),
                            "heal_amount": result.get("heal_amount", 0),
                            "boost_amount": result.get("boost_amount", 0),
                            "is_critical": result.get("is_critical", False),
                            "hits": result.get("hits", 1),
                            "skill_name": action_value
                        }
                    case "kill":
                        session['combat_animation'] = {
                            "type": result.get("skill_type", "magic"),
                            "action": "kill",
                            "total_damage": result.get("total_damage", 0),
                            "enemy_defeated": True
                        }
                    case _:
                        pass  # Aucune animation spéciale
            else:
                message = result if isinstance(result, str) else str(result)
        
        case 'flee':
            message = game.flee_combat()
        
        # Actions d'inventaire
        case 'equip':
            parts = action_value.split('|')
            item_name = parts[0]
            item_type = parts[1] if len(parts) > 1 else 'weapon'
            if game.equip_item(item_name, item_type):
                message = t("équipé(e)!", game.language).join([item_name + " ", ""])
            else:
                message = t("Impossible d'équiper cet objet.", game.language)

        case 'unequip':
            if game.unequip_item(action_value):
                message = t("Objet dés-équipé!", game.language)
            else:
                message = t("Aucun objet à dés-équiper.", game.language)

        case 'use_item':
            message = game.use_item(action_value)

        case 'drop_item':
            if game.drop_item(action_value):
                message = f"{action_value} " + t("jeté(e)!", game.language)
            else:
                message = t("Objet non trouvé.", game.language)

        case 'buy':
            message = game.buy_item(action_value)

        case 'close_shop':
            message = game.close_shop()

        # Actions d'interface
        case 'set_difficulty':
            message = game.set_difficulty(action_value)

        case 'set_language':
            lang = action_value if action_value in ('fr', 'en') else 'fr'
            session['language'] = lang
            message = t("Langue changée.", game.language) if lang == 'fr' else "Language changed."

        case 'toggle_options':
            game.toggle_options()
            message = t("Options ouvertes.", game.language) if game.show_options else t("Options fermées.", game.language)

        case 'toggle_inventory':
            game.toggle_inventory()
            message = t("Inventaire ouvert.", game.language) if game.show_inventory else t("Inventaire fermé.", game.language)

        case 'toggle_quests':
            game.toggle_quests()
            message = t("Quêtes ouvertes.", game.language) if game.show_quests else t("Quêtes fermées.", game.language)

        case 'toggle_skills':
            game.toggle_skills()
            message = t("Compétences ouvertes.", game.language) if game.show_skills else t("Compétences fermées.", game.language)

        case 'toggle_runes':
            game.toggle_runes()
            message = t("Runes ouvertes.", game.language) if game.show_runes else t("Runes fermées.", game.language)

        case 'craft_rune':
            message = game.craft_rune(action_value)

        case 'buy_loot_boost':
            message = game.buy_loot_boost()

        case 'use_card':
            message = game.use_card(action_value)

        case 'complete_quest':
            success, message = game.complete_dynamic_quest(action_value)
            if not success:
                message = t("Cette quête est déjà complétée ou non accomplie.", game.language)
        
        # Système de Prestige / Arène
        case 'reincarnate':
            if game.player_stats.get('level', 0) < 30:
                message = t("Vous devez être au moins niveau 30 pour vous réincarner !", game.language)
            else:
                success, message = game.reincarnate()
                if success:
                    # Sauvegarder les nouvelles stats après réincarnation
                    session['saved_stats'] = game.get_save_stats()
                    session['saved_skills'] = {
                        'skills_learned': {k: v.copy() if isinstance(v, dict) else v for k, v in game.skills_learned.items()},
                        'unlocked_skills': game.unlocked_skills.copy()
                    }
                    # Réinitialiser la session de jeu pour appliquer les changements
                    game_id = session.get('game_id')
                    if game_id and game_id in game_sessions:
                        del game_sessions[game_id]
        
        case 'enter_arena':
            if game.current_location != 'arene':
                message = t("Vous devez être à l'arène pour entrer en combat !", game.language)
            else:
                success, message = game.enter_arena()
                if not success:
                    session['last_message'] = message
        
        case 'leave_arena':
            message = game.leave_arena()

        # Cas par défaut
        case _:
            message = t("Action inconnue.", game.language)
    
    game.check_win()

    # Sauvegarder les compétences dans la session après chaque action
    # pour éviter leur perte en cas de recréation du GameEngine
    session['saved_skills'] = {
        'skills_learned': {k: v.copy() if isinstance(v, dict) else v for k, v in game.skills_learned.items()},
        'unlocked_skills': game.unlocked_skills.copy()
    }

    # Stocker le message dans la session pour affichage
    session['last_message'] = message

    # Sauvegarder automatiquement les stats si le joueur est mort
    if game.game_over:
        session['saved_stats'] = game.get_save_stats()
        session['saved_skills'] = {
            'skills_learned': {k: v.copy() if isinstance(v, dict) else v for k, v in game.skills_learned.items()},
            'unlocked_skills': game.unlocked_skills.copy()
        }
        session.modified = True
        # Supprimer la session de jeu actuelle pour forcer un rechargement
        # avec les stats sauvegardées au prochain accès
        game_id = session.get('game_id')
        if game_id and game_id in game_sessions:
            del game_sessions[game_id]
        # Réinitialiser game_over pour permettre de continuer
        game.game_over = False
    
    session['last_message'] = message
    session.modified = True
    
    return redirect(url_for('index'))


@app.route('/restart', methods=['POST'])
def restart():
    """Recommence le jeu en gardant l'XP, les objets et toutes les stats"""
    game = get_game_session()
    
    # Sauvegarder TOUTES les stats actuelles dans la session
    session['saved_stats'] = game.get_save_stats()
    
    # Mettre aussi à jour saved_skills pour cohérence
    session['saved_skills'] = {
        'skills_learned': {k: v.copy() if isinstance(v, dict) else v for k, v in game.skills_learned.items()},
        'unlocked_skills': game.unlocked_skills.copy()
    }

    game_id = session.get('game_id')
    if game_id and game_id in game_sessions:
        del game_sessions[game_id]

    if 'last_message' in session:
        del session['last_message']

    session['game_id'] = os.urandom(16).hex()
    session.modified = True
    
    return redirect(url_for('index'))


@app.route('/reset-dynamic-quests', methods=['POST'])
def reset_dynamic_quests():
    """Reset manuellement les quêtes dynamiques"""
    game = get_game_session()
    result = game.reset_dynamic_quests()
    session['last_message'] = result
    session.modified = True
    return redirect(url_for('index'))


@app.route('/complete-dynamic-quest/<quest_id>', methods=['POST'])
def complete_dynamic_quest(quest_id):
    """Complète une quête dynamique"""
    game = get_game_session()
    success, message = game.complete_dynamic_quest(quest_id)
    session['last_message'] = message
    session.modified = True
    return redirect(url_for('index'))


@app.route('/save')
def save_game():
    """Exporte la sauvegarde du joueur en fichier JSON."""
    game = get_game_session()
    save_data = {
        "version": "1.0",
        "player_class": session.get('player_class', None),
        "player_stats": {
            "health": game.player_stats["health"],
            "max_health": game.player_stats["max_health"],
            "mana": game.player_stats["mana"],
            "max_mana": game.player_stats["max_mana"],
            "attack": game.player_stats["attack"],
            "defense": game.player_stats["defense"],
            "level": game.player_stats["level"],
            "exp": game.player_stats["exp"],
            "exp_for_next_level": game.player_stats["exp_for_next_level"],
            "gold": game.player_stats["gold"]
        },
        "inventory": game.inventory.copy(),
        "equipped": game.equipped.copy(),
        "dynamic_quest_progress": game.dynamic_quest_progress.copy(),
        "dynamic_quests_completed": game.dynamic_quests_completed.copy(),
        "skills_learned": {k: v.copy() if isinstance(v, dict) else v for k, v in game.skills_learned.items()},
        "unlocked_skills": game.unlocked_skills.copy(),
        "rune_inventory": game.rune_inventory.copy(),
        "loot_boost_count": game.loot_boost_count,
        "card_inventory": game.card_inventory.copy(),
        "cards_used": game.cards_used.copy(),
        "total_enemies_defeated": game.total_enemies_defeated,
        "total_damage_dealt": game.total_damage_dealt,
        "total_damage_taken": game.total_damage_taken,
        "boss_defeated": game.boss_defeated.copy(),
        "difficulty": game.difficulty,
        # Système de Prestige / Réincarnation
        "prestige_level": game.prestige_level,
        "reincarnation_count": game.reincarnation_count,
        # Système d'Arène
        "in_arena": game.in_arena,
        "arena_wins": game.arena_wins,
        "arena_current_streak": game.arena_current_streak,
        "arena_enemies_defeated": game.arena_enemies_defeated,
        "arena_rewards": game.arena_rewards.copy(),
        # Position
        "current_location": game.current_location,
        "visited_locations": list(game.visited_locations) if hasattr(game, 'visited_locations') else []
    }
    json_str = json.dumps(save_data, ensure_ascii=False, indent=2)
    return send_file(
        io.BytesIO(json_str.encode('utf-8')),
        mimetype='application/json',
        as_attachment=True,
        download_name=f'gamepython_save_lvl{game.player_stats["level"]}.json'
    )


@app.route('/load', methods=['POST'])
def load_game():
    """Importe une sauvegarde depuis un fichier JSON."""
    lang = session.get('language', 'fr')
    if 'save_file' not in request.files:
        session['last_message'] = t("Aucun fichier sélectionné.", lang)
        return redirect(url_for('index'))
    file = request.files['save_file']
    if file.filename == '':
        session['last_message'] = t("Aucun fichier sélectionné.", lang)
        return redirect(url_for('index'))
    try:
        content = file.read().decode('utf-8')
        save_data = json.loads(content)
    except (json.JSONDecodeError, UnicodeDecodeError):
        session['last_message'] = t("Fichier invalide ! Ce n'est pas une sauvegarde GamePython.", lang)
        return redirect(url_for('index'))

    if "version" not in save_data or "player_class" not in save_data:
        session['last_message'] = t("Fichier de sauvegarde invalide ou corrompu.", lang)
        return redirect(url_for('index'))

    # Sauvegarder dans la session
    session['player_class'] = save_data.get('player_class')
    session['saved_stats'] = {
        'exp': save_data.get('player_stats', {}).get('exp', 0),
        'level': save_data.get('player_stats', {}).get('level', 1),
        'gold': save_data.get('player_stats', {}).get('gold', 0),
        'exp_for_next_level': save_data.get('player_stats', {}).get('exp_for_next_level', 100),
        'health': save_data.get('player_stats', {}).get('health', 100),
        'max_health': save_data.get('player_stats', {}).get('max_health', 100),
        'mana': save_data.get('player_stats', {}).get('mana', 50),
        'max_mana': save_data.get('player_stats', {}).get('max_mana', 50),
        'attack': save_data.get('player_stats', {}).get('attack', 5),
        'defense': save_data.get('player_stats', {}).get('defense', 0),
        'inventory': save_data.get('inventory', {}),
        'equipped': save_data.get('equipped', {}),
        'dynamic_quest_progress': save_data.get('dynamic_quest_progress', {}),
        'dynamic_quests_completed': save_data.get('dynamic_quests_completed', []),
        'skills_learned': save_data.get('skills_learned', {}),
        'unlocked_skills': save_data.get('unlocked_skills', {}),
        'rune_inventory': save_data.get('rune_inventory', {}),
        'loot_boost_count': save_data.get('loot_boost_count', 0),
        'card_inventory': save_data.get('card_inventory', {}),
        'cards_used': save_data.get('cards_used', []),
        'prestige_level': save_data.get('prestige_level', 0),
        'reincarnation_count': save_data.get('reincarnation_count', 0),
        'arena_rewards': save_data.get('arena_rewards', {"exp": 0, "gold": 0, "runes": {}, "cards": {}}),
        'in_arena': save_data.get('in_arena', False),
        'arena_wins': save_data.get('arena_wins', 0),
        'arena_current_streak': save_data.get('arena_current_streak', 0),
        'arena_enemies_defeated': save_data.get('arena_enemies_defeated', 0),
        'current_location': save_data.get('current_location', GAME_CONFIG.get('starting_location', 'forest')),
        'visited_locations': list(set(save_data.get('visited_locations', [GAME_CONFIG.get('starting_location', 'forest')]))),
        'total_enemies_defeated': save_data.get('total_enemies_defeated', 0),
        'total_damage_dealt': save_data.get('total_damage_dealt', 0),
        'total_damage_taken': save_data.get('total_damage_taken', 0),
        'difficulty': save_data.get('difficulty', 'moyen')
    }

    # Supprimer l'ancienne session de jeu pour forcer le rechargement
    game_id = session.get('game_id')
    if game_id and game_id in game_sessions:
        del game_sessions[game_id]

    # Mettre à jour saved_skills pour cohérence
    session['saved_skills'] = {
        'skills_learned': save_data.get('skills_learned', {}),
        'unlocked_skills': save_data.get('unlocked_skills', {})
    }

    # Restaurer les stats de jeu supplémentaires (pour rétrocompatibilité)
    session['extra_save'] = {
        'total_enemies_defeated': save_data.get('total_enemies_defeated', 0),
        'total_damage_dealt': save_data.get('total_damage_dealt', 0),
        'total_damage_taken': save_data.get('total_damage_taken', 0),
        'boss_defeated': save_data.get('boss_defeated', {}),
        'difficulty': save_data.get('difficulty', 'moyen')
    }

    session['game_id'] = os.urandom(16).hex()
    session['last_message'] = t("Sauvegarde chargée !", lang) + f" {t('Classe:', lang)} {save_data.get('player_class')}, {t('Niveau:', lang)} {save_data.get('player_stats', {}).get('level', 1)}"
    session.modified = True

    return redirect(url_for('index'))


@app.route('/health')
def health():
    """Route de sante du serveur"""
    return {'status': 'ok', 'message': 'Serveur RPG actif'}, 200


@app.route('/clear_animation', methods=['POST'])
def clear_animation():
    """Nettoie l'animation de combat après affichage"""
    if 'combat_animation' in session:
        del session['combat_animation']
        session.modified = True
    return '', 200


def open_browser():
    """Ouvre le navigateur"""
    url = "http://127.0.0.1:5000"
    webbrowser.open(url)
    print(f"Navigateur ouvert a: {url}")


if __name__ == '__main__':
    print("Serveur RPG GamePython demarrage!")
    print("Acces a: http://127.0.0.1:5000")
    print("Pour arreter: Ctrl+C")
    print()
    
    browser_thread = threading.Thread(target=open_browser, daemon=True)
    browser_thread.start()
    
    app.run(
        host='127.0.0.1',
        port=5000,
        debug=True,
        use_reloader=False
    )
