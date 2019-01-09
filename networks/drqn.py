import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import numpy as np
import tensorflow as tf

from networks.base_network import BaseNetwork


class ReplayMemory:

    def __init__(self, capacity, n_features):

        self.capacity = capacity
        self.event_size = n_features * 2 + 2
        # initialize zero memory, each sample in memory has size [s + a + r + s_]
        self.memory = np.zeros((self.capacity, 20, self.event_size))
        self.memory_counter = 0

    def push(self, episode):
        # get the index where to insert the episode
        index = self.memory_counter % self.capacity
        self.memory[index, :] = episode

        # increment memory_counter avoiding overflow
        self.memory_counter += 1
        if self.memory_counter == (self.capacity * 2):
            self.memory_counter = self.capacity

    def sample(self, batch_size, trace_length):

        if self.memory_counter > self.capacity:
            # the replay memory is all written, so I can sample on all the array size [0, self.capacity]
            sample_index = np.random.choice(self.capacity, size=batch_size)
        else:
            # only part of the replay memory is written, so I sample up to where it's written [0, self.memory_counter]
            sample_index = np.random.choice(self.memory_counter, size=batch_size)

        batch_episodes = self.memory[sample_index, :]

        sampled_traces = []
        for episode in batch_episodes:
            start_index = np.random.randint(0, len(episode) + 1 - trace_length)
            sampled_traces.append(episode[start_index:start_index+trace_length])

        sampled_traces = np.array(sampled_traces)
        return np.reshape(sampled_traces,[batch_size*trace_length,self.event_size])

    def size(self):
        return min(self.capacity, self.memory_counter)


class DRQN(BaseNetwork):

    def __init__(self, n_actions, n_features, learning_rate = 1e-3, discount = 0.85):
        # initialize base class
        super().__init__()

        # network parameters
        self.n_features = n_features
        self.n_actions = n_actions
        self.learning_rate = learning_rate
        self.gamma = discount
        self.batch_size = 25
        self.trace_length = 5
        self.replace_target_iter = 500

        # layers parameters
        self.lstm_layers = [256, 128]

        # init vars
        self.learn_step_counter = 0
        self.wrong_move = False
        self.session = None

        # create replay memroy
        self.last_episode = []
        capacity = 2500
        self.replay_memory = ReplayMemory(capacity, n_features)

        # create network
        self.create_network()
        self.initialize_session()


    def create_network(self):

        with self.graph.as_default():
            # input placeholders
            self.s = tf.placeholder(tf.float32, [None, self.n_features], name='states')  # input State
            self.s_ = tf.placeholder(tf.float32, [None, self.n_features], name='states_')  # input Next State
            self.r = tf.placeholder(tf.float32, [None, ], name='rewards')  # input Reward
            self.a = tf.placeholder(tf.int32, [None, ], name='actions')  # input Action
            self.events_length = tf.placeholder(dtype=tf.int32)
            w_initializer, b_initializer = tf.random_normal_initializer(0., 0.3), tf.constant_initializer(0.1)

            # evaluation network
            with tf.variable_scope('eval_net'):

                e1 = tf.layers.dense(self.s, 128, tf.nn.relu, kernel_initializer=w_initializer,
                            bias_initializer=b_initializer, name= 'e1')


                rnn_s = tf.reshape(tf.contrib.slim.flatten(e1),[-1,self.events_length, 128])
                rnn_multi_cells_e = tf.contrib.rnn.MultiRNNCell([tf.nn.rnn_cell.LSTMCell(layer_size) for layer_size in self.lstm_layers])

                rnn_output_e, _ = tf.nn.dynamic_rnn(
                    rnn_multi_cells_e, rnn_s, dtype=tf.float32)
                rnn_output_e = tf.reshape(rnn_output_e,shape=[-1, self.lstm_layers[-1]])


                e2 = tf.layers.dense(rnn_output_e, 32, kernel_initializer=w_initializer,
                                        bias_initializer=b_initializer, name='e2')

                self.q = tf.layers.dense(e2, self.n_actions, kernel_initializer=w_initializer,
                                                bias_initializer=b_initializer, name='q')


            # target network
            with tf.variable_scope('target_net'):

                t1 = tf.layers.dense(self.s_, 128, tf.nn.relu, kernel_initializer=w_initializer,
                            bias_initializer=b_initializer, name='t1')

                rnn_s_ = tf.reshape(tf.contrib.slim.flatten(t1),[-1,self.events_length, 128])
                multi_cells_t = tf.contrib.rnn.MultiRNNCell([tf.nn.rnn_cell.LSTMCell(layer_size) for layer_size in self.lstm_layers])

                rnn_output_t, _ = tf.nn.dynamic_rnn(
                    multi_cells_t, rnn_s_, dtype=tf.float32)
                rnn_output_t = tf.reshape(rnn_output_t,shape=[-1, self.lstm_layers[-1]])



                t2 = tf.layers.dense(rnn_output_t, 32, kernel_initializer=w_initializer,
                                        bias_initializer=b_initializer, name='t2')

                self.q_next = tf.layers.dense(t2, self.n_actions, kernel_initializer=w_initializer,
                                                bias_initializer=b_initializer, name='q_next')

            with tf.variable_scope('predictions'):
                # predicted actions according to evaluation network
                self.argmax_action = tf.argmax(self.q, 1, output_type=tf.int32, name='argmax')
            with tf.variable_scope('q_target'):
                # discounted reward on the target network
                q_target = self.r + self.gamma * tf.reduce_max(self.q_next, axis=1, name='q_target')
                # stop gradient to avoid updating target network
                self.q_target = tf.stop_gradient(q_target)
            with tf.variable_scope('q_wrt_a'):
                # q value of chosen action
                a_indices = tf.stack([tf.range(tf.shape(self.a)[0], dtype=tf.int32), self.a], axis=1)
                self.q_wrt_a = tf.gather_nd(params=self.q, indices=a_indices)
            with tf.variable_scope('loss'):
                # loss computed as difference between predicted q[a] and (current_reward + discount * q_target[best_future_action])
                self.loss = tf.reduce_mean(tf.squared_difference(self.q_target, self.q_wrt_a, name='td_error'))
            with tf.variable_scope('train'):
                opt = tf.train.AdamOptimizer(self.learning_rate)
                grads_and_vars = opt.compute_gradients(self.loss)
                self._train_op = opt.apply_gradients(grads_and_vars, name='optimizer')

            t_params = tf.get_collection(tf.GraphKeys.GLOBAL_VARIABLES, scope='target_net')
            e_params = tf.get_collection(tf.GraphKeys.GLOBAL_VARIABLES, scope='eval_net')


            with tf.variable_scope('hard_replacement'):
                # operator for assiging evaluation network weights to the target network
                self.target_replace_op = [tf.assign(t, e) for t, e in zip(t_params, e_params)]


    def get_q_table(self, state):
            ''' Compute q table for current state'''

            states_op = self.session.graph.get_operation_by_name(f"states").outputs[0]
            #argmax_op = self.session.graph.get_operation_by_name("predictions/argmax").outputs[0]
            q_op = self.session.graph.get_operation_by_name(f"eval_net/q/BiasAdd").outputs[0]

            input_state = np.expand_dims(state, axis=0)
            q = self.session.run([q_op], feed_dict={states_op: input_state, self.events_length : 1})

            return q[0][0]


    def learn(self, last_state, action, reward, state):

        state_vector = np.hstack((last_state, [action, reward], state))
        self.last_episode.append(state_vector)

        # HACK for check end episode
        if len(self.last_episode) == 20:
            self.replay_memory.push(self.last_episode)
            self.last_episode = []

        if self.replay_memory.size() < self.batch_size:
            # there are not enough samples for a training step in the replay memory
            return
        # get a batch of samples from replay memory
        batch_memory = self.replay_memory.sample(self.batch_size, self.trace_length)

        # run a newtork training step
        _, loss = self.session.run(
            [self._train_op, self.loss,],
            feed_dict={
                self.s: batch_memory[:, : self.n_features],
                self.a: batch_memory[:, self.n_features],
                self.r: batch_memory[:, self.n_features + 1],
                self.s_: batch_memory[:, -self.n_features:],
                self.events_length : self.trace_length,
            })

        # check if it's time to copy the target network into the evaluation network
        if self.learn_step_counter % self.replace_target_iter == 0:
            self.session.run(self.target_replace_op)
            #print("Loss: ", loss)

        self.learn_step_counter += 1
