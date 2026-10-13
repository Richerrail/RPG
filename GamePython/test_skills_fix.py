# Test flux réel : GameEngine créé sans classe, puis choix de classe
from game_engine import GameEngine

print("=== Simulation flux serveur ===")

# 1. Première visite : GameEngine créé, pas de player_class en session
session = {}
session['game_id'] = 'test123'
game_sessions = {}

game_id = session['game_id']
if game_id not in game_sessions:
    game_sessions[game_id] = GameEngine()
    if 'player_class' in session:
        game_sessions[game_id].set_class(session['player_class'])

game = game_sessions[game_id]
print("1. Après première visite:")
print("   player_class:", game.player_class)
print("   skills:", list(game.get_available_skills_for_level().keys()))

# 2. Joueur choisit sa classe
session['player_class'] = 'Guerrier'
print("\n2. Joueur choisit Guerrier dans session")

# 3. Retour sur / - GameEngine existe déjà
# Ancien code : set_class() JAMAIS appelé
# Nouveau code : set_class() appelé car player_class in session et game.player_class is None
if game.player_class is None and 'player_class' in session:
    game.set_class(session['player_class'])
    game.unlock_progressive_skills()

print("3. Après retour sur / avec fix:")
print("   player_class:", game.player_class)
print("   skills:", list(game.get_available_skills_for_level().keys()))

print("\nRESULTAT:", "OK" if game.player_class == 'Guerrier' and len(game.get_available_skills_for_level()) == 2 else "BUG - skills non débloqués!")
