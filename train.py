import itertools, time, random
import numpy as np
import tensorflow as tf

import sys
from matplotlib import pyplot as plt

from agents.random_agent import RandomAgent
from agents.deep_agent import DeepAgent
import environment as brisc



# Parameters
# ==================================================

# Model directory
tf.flags.DEFINE_string("model_dir", "", "Where to save the trained model, checkpoints and stats (default: pwd/runs/timestamp)")

# Training parameters
tf.flags.DEFINE_integer("batch_size", 100, "Batch Size")
tf.flags.DEFINE_integer("num_epochs", 20000, "Number of training epochs")

# Saver parameters
tf.flags.DEFINE_integer("evaluate_every", 1000, "Evaluate model on dev set after this many steps")

FLAGS = tf.flags.FLAGS

def test(game, agents):

    deck = game.deck
    n_games = 250
    total_wins = [0, 0]
    total_points = [0, 0]

    for _ in range(n_games):

        game.reset()
        keep_playing = True

        while keep_playing:

            players_order = game.get_players_order()
            for player_id in players_order:

                player = game.players[player_id]
                agent = agents[player_id]

                agent.observe(game, player, deck)
                available_actions = game.get_player_actions(player_id)
                action = agent.select_action(available_actions)

                game.play_step(action, player_id)

            winner_player_id, points = game.evaluate_step()

            keep_playing = game.draw_step()

        game_winner_id, winner_points = game.end_game()

        total_wins[game_winner_id] += 1
        total_points[game_winner_id] += winner_points
        total_points[1 - game_winner_id] += (120 - winner_points)


    victory_rate = (total_wins[0]/float(n_games))*100
    print("DeepAgent wins ", victory_rate, "% with average points ", float(total_points[0])/float(n_games))

    return victory_rate



def main(argv=None):

    # Initializing the environment
    game = brisc.BriscolaGame(  verbosity=brisc.LoggerLevels.TRAIN)
    deck = game.deck

    # Initialize agents
    agents = []
    agents.append(DeepAgent())
    agents.append(RandomAgent())

    best_winning_ratio = -1

    for epoch in range(1, FLAGS.num_epochs + 1):
        print ("Epoch: ", epoch, end='\r')
        game.reset()
        keep_playing = True

        while keep_playing:

            # step
            players_order = game.get_players_order()
            for player_id in players_order:

                player = game.players[player_id]
                agent = agents[player_id]

                agent.observe(game, player, deck)
                available_actions = game.get_player_actions(player_id)
                action = agent.select_action(available_actions)

                game.play_step(action, player_id)


            winner_player_id, points = game.evaluate_step()

            # update environment
            keep_playing = game.draw_step()

            # update agents
            for player_id in players_order:
                player = game.players[player_id]
                agent = agents[player_id]

                agent.observe(game, player, deck)
                available_actions = game.get_player_actions(player_id)

                # compute reward function for this player
                if player_id is winner_player_id:
                    reward = points
                elif points >= 10:
                    reward = -2
                else:
                    reward = 0

                agent.update(reward, available_actions)

        game_winner_id, winner_points = game.end_game()

        # here i should update the network according to game results

        if epoch % FLAGS.evaluate_every == 0:
            winning_ratio = test(game, agents)
            if winning_ratio > best_winning_ratio:
                best_winning_ratio = winning_ratio
                agents[0].save_model(FLAGS.model_dir)



if __name__ == '__main__':
    tf.app.run()