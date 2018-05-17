#!/usr/bin/env python
# coding=utf8

import numpy as np
import tensorflow as tf
import config
from agents.comm_obs import comm

FLAGS = config.flags.FLAGS

gamma = FLAGS.df  # reward discount factor


h_critic = FLAGS.h_critic

h1_critic = h_critic  # hidden layer 1 size for the critic
h2_critic = h_critic  # hidden layer 2 size for the critic
h3_critic = h_critic  # hidden layer 3 size for the critic

lr_actor = FLAGS.a_lr   # learning rate for the actor
lr_critic = FLAGS.c_lr  # learning rate for the critic
lr_decay = 1  # learning rate decay (per episode)

tau = 5e-2  # soft target update rate

np.set_printoptions(threshold=np.nan)


class ActorNetwork:

    def __init__(self, sess, n_agent, obs_dim_per_unit, action_dim, nn_id=None):

        self.sess = sess
        self.n_agent = n_agent
        self.obs_dim_per_unit = obs_dim_per_unit
        self.action_dim = action_dim

        if nn_id == None:
            scope = 'actor'
        else:
            scope = 'actor_' + str(nn_id)

        # placeholders
        self.state_ph = tf.placeholder(dtype=tf.float32, shape=[None, obs_dim_per_unit*n_agent])
        self.next_state_ph = tf.placeholder(dtype=tf.float32, shape=[None, obs_dim_per_unit*n_agent])
        # concat action space
        self.action_ph = tf.placeholder(dtype=tf.int32, shape=[None, n_agent])
        self.schedule_ph = tf.placeholder(dtype=tf.float32, shape=[None, self.n_agent])
        self.a_onehot = tf.reshape(tf.one_hot(self.action_ph, self.action_dim, 1.0, 0.0), [-1, action_dim * n_agent])
        self.td_errors = tf.placeholder(dtype=tf.float32, shape=[None, 1])

        # indicators (go into target computation)
        self.is_training_ph = tf.placeholder(dtype=tf.bool, shape=())  # for dropout

        # actor network
        with tf.variable_scope(scope):
            # Policy's outputted action for each state_ph (for generating actions and training the critic)
            self.actions = self.generate_actor_network(self.state_ph, self.schedule_ph, trainable=True)

        # actor loss function (mean Q-values under current policy with regularization)
        self.actor_vars = tf.get_collection(tf.GraphKeys.TRAINABLE_VARIABLES, scope=scope)

        self.responsible = tf.multiply(self.actions, self.a_onehot)
        
        log_prob = tf.log(tf.reduce_sum(self.responsible, reduction_indices=1, keep_dims=True))
        entropy = -tf.reduce_sum(self.actions*tf.log(self.actions), 1)

        self.loss = tf.reduce_sum(-(tf.multiply(log_prob, self.td_errors) + 0.01*entropy)) 

        var_grads = tf.gradients(self.loss, self.actor_vars)
        self.actor_train_op = tf.train.AdamOptimizer(lr_actor * lr_decay).apply_gradients(zip(var_grads,self.actor_vars))

        if FLAGS.ae_initializer:
            self.ae_input = tf.placeholder(dtype=tf.float32, shape=[None, obs_dim_per_unit])
            with tf.variable_scope("ae_" + scope):
                self.autoencoder = self.generate_autoencoder(self.ae_input, obs_dim_per_unit)

            self.ae_loss = tf.reduce_mean(tf.squred_difference(self.ae_input, self.autoencoder))
            self.ae_train_op = tf.train.AdamOptimizer(lr_actor).minimize(self.ae_loss)

            self.initialize_encoder_op = self.copy_ae_values_to_encoders()

    # will use this to initialize both the actor network its slowly-changing target network with same structure
    def generate_actor_network(self, obs, schedule, trainable, share=False):

        obs_list = list()
        for i in range(self.n_agent):
            obs_list.append(obs[:, i * self.obs_dim_per_unit:(i + 1) * self.obs_dim_per_unit])

        ret = comm.generate_comm_network(obs_list, self.obs_dim_per_unit, self.action_dim, self.n_agent, schedule=schedule)
        # ret = comm.generate_comm_network_0_schedule(obs_list, self.action_dim, self.n_agent)
        # ret = comm.generate_actor_network(obs_list, self.action_dim, self.n_agent)
        return ret

    def action_for_state(self, state_ph, schedule_ph):
        return self.sess.run(self.actions,
                             feed_dict={self.state_ph: state_ph,
                                        self.schedule_ph: schedule_ph,
                                        self.is_training_ph: False})

    def training_actor(self, state_ph, action_ph, schedule_ph, td_errors):
        return self.sess.run(self.actor_train_op,
                             feed_dict={self.state_ph: state_ph,
                                        self.action_ph: action_ph,
                                        self.schedule_ph: schedule_ph,
                                        self.td_errors: td_errors,
                                        self.is_training_ph: True})


    def generate_autoencoder(e_input, obs_dim_per_unit, out_dim=FLAGS.capa, h_num=32, h_level=1, name="ae", trainable=True):
        if FLAGS.use_codec:
            hidden = e_input

            with tf.variable_scope("encoder"):
                for i in range(h_level):

                    hidden = tf.layers.dense(hidden, h_num, activation=tf.nn.relu,
                                             kernel_initializer=tf.random_normal_initializer(0., .1),  # weights
                                             bias_initializer=tf.constant_initializer(0.1),  # biases
                                             use_bias=True, trainable=trainable, reuse=tf.AUTO_REUSE, name=name+str(i))

                enc = tf.layers.dense(hidden, out_dim, activation=tf.nn.relu,
                                    kernel_initializer=tf.random_normal_initializer(0., .1),  # weights
                                    bias_initializer=tf.constant_initializer(0.1),  # biases
                                    use_bias=True, trainable=trainable, reuse=tf.AUTO_REUSE, name=name+"_out")

            hidden = enc

            with tf.variable_scope("decoder"):
                for i in range(h_level):

                    hidden = tf.layers.dense(hidden, h_num, activation=tf.nn.relu,
                                             kernel_initializer=tf.random_normal_initializer(0., .1),  # weights
                                             bias_initializer=tf.constant_initializer(0.1),  # biases
                                             use_bias=True, trainable=trainable, reuse=tf.AUTO_REUSE, name=name+str(i))
                
                dec = tf.layers.dense(hidden, obs_dim_per_unit,
                                    kernel_initializer=tf.random_normal_initializer(0., .1),  # weights
                                    bias_initializer=tf.constant_initializer(0.1),  # biases
                                    use_bias=True, trainable=trainable, reuse=tf.AUTO_REUSE, name=name+"_out")
            return dec
        else:
            return e_input

    def copy_ae_values_to_encoders(self):
        if not FLAGS.e_share:
            enc_scopes = ["encoder" + str(i) for i in range(self.n_agent)]
        else:
            enc_scopes = ["encoder"]

        ae_vars = tf.get_collection(tf.GraphKeys.TRAINABLE_VARIABLES, scope="ae_" + scope + "/encoder")

        update_encoder_ops_c = []
        for scope in enc_scopes:
            encoder_vars = tf.get_collection(tf.GraphKeys.GLOBAL_VARIABLES, scope=scope)
            for i, enc_var in enumerate(encoder_vars):
                update_encoder_op = enc_var.assign(ae_vars[i])
                update_encoder_ops_c.append(update_encoder_op)

        return tf.group(*update_encoder_op_c)

    def initialize_encoder_using_ae_weights(self):
        return self.sess.run(self.initialize_encoders_op)

    def train_autoencoder(self, obs):
        error,_ = self.sess.run([self.ae_loss, self.ae_train_op], feed_dict={self.ae_input: obs})
        return error

class CriticNetwork:
    def __init__(self, sess, n_agent, state_dim, nn_id=None):

        self.sess = sess
        self.n_agent = n_agent
        self.state_dim = state_dim

        if nn_id == None:
            scope = 'critic'
        else:
            scope = 'critic_' + str(nn_id)

        # placeholders
        self.state_ph = tf.placeholder(dtype=tf.float32, shape=[None, state_dim])
        self.reward_ph = tf.placeholder(dtype=tf.float32, shape=[None])
        self.next_state_ph = tf.placeholder(dtype=tf.float32, shape=[None, state_dim])

        self.is_not_terminal_ph = tf.placeholder(dtype=tf.float32, shape=[None])  # indicators (go into target computation)
        self.is_training_ph = tf.placeholder(dtype=tf.bool, shape=())  # for dropout

        with tf.variable_scope(scope):
            # Critic applied to state_ph
            self.q_values = self.generate_critic_network(self.state_ph, trainable=True)

        # slow target critic network
        with tf.variable_scope('slow_target_'+scope):
            self.slow_q_values = tf.stop_gradient(
                self.generate_critic_network(self.next_state_ph, trainable=False))

        # One step TD targets y_i for (s,a) from experience replay
        # = r_i + gamma*Q_slow(s',mu_slow(s')) if s' is not terminal
        # = r_i if s' terminal
        targets = tf.expand_dims(self.reward_ph, 1) + tf.expand_dims(self.is_not_terminal_ph, 1) * gamma * self.slow_q_values

        # 1-step temporal difference errors
        self.td_errors = targets - self.q_values

        critic_vars = tf.get_collection(tf.GraphKeys.TRAINABLE_VARIABLES, scope=scope)
        critic_loss = tf.reduce_mean(tf.square(self.td_errors))

        # critic optimizer
        self.critic_train_op = tf.train.AdamOptimizer(lr_critic * lr_decay).minimize(critic_loss, var_list=critic_vars)

        slow_target_critic_vars = tf.get_collection(tf.GraphKeys.GLOBAL_VARIABLES, scope='slow_target_'+scope)
        update_slow_target_ops_c = []
        for i, slow_target_var in enumerate(slow_target_critic_vars):
            update_slow_target_critic_op = slow_target_var.assign(tau * critic_vars[i] + (1 - tau) * slow_target_var)
            # update_slow_target_critic_op = slow_target_var.assign(critic_vars[i]) #copy only
            update_slow_target_ops_c.append(update_slow_target_critic_op)
        self.update_slow_targets_op_c = tf.group(*update_slow_target_ops_c)

    # will use this to initialize both the critic network its slowly-changing target network with same structure
    def generate_critic_network(self, s, trainable):
        state_action = s

        hidden = tf.layers.dense(state_action, h1_critic, activation=tf.nn.relu,
                                 kernel_initializer=tf.random_normal_initializer(0., .1),    # weights
                                 bias_initializer=tf.constant_initializer(0.1),  # biases
                                 use_bias=True, trainable=trainable, name='dense_c1')

        hidden_2 = tf.layers.dense(hidden, h2_critic, activation=tf.nn.relu,
                                   kernel_initializer=tf.random_normal_initializer(0., .1),    # weights
                                   bias_initializer=tf.constant_initializer(0.1),  # biases
                                   use_bias=True, trainable=trainable, name='dense_c2')

        hidden_3 = tf.layers.dense(hidden_2, h3_critic, activation=tf.nn.relu,
                                   kernel_initializer=tf.random_normal_initializer(0., .1),    # weights
                                   bias_initializer=tf.constant_initializer(0.1),  # biases
                                   use_bias=True, trainable=trainable, name='dense_c3')

        q_values = tf.layers.dense(hidden_3, 1, trainable=trainable,
                                   kernel_initializer=tf.random_normal_initializer(0., .1),    # weights
                                   bias_initializer=tf.constant_initializer(0.1),  # biases
                                   name='dense_c4', use_bias=False)
        return q_values

    def training_critic(self, state_ph, reward_ph, next_state_ph, is_not_terminal_ph):

        return self.sess.run([self.td_errors, self.critic_train_op],
                             feed_dict={self.state_ph: state_ph,
                                        self.reward_ph: reward_ph,
                                        self.next_state_ph: next_state_ph,
                                        self.is_not_terminal_ph: is_not_terminal_ph,
                                        self.is_training_ph: True})

    def training_target_critic(self):
        return self.sess.run(self.update_slow_targets_op_c,
                             feed_dict={self.is_training_ph: False})
