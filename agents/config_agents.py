#!/usr/bin/env python
# coding=utf8
# import agents


def config_agent(_flags):
    flags = _flags

    flags.DEFINE_string("agent", "cfao_sa_generalized", "Agent")

    flags.DEFINE_integer("training_step", 40000, "Training time step")
    flags.DEFINE_integer("testing_step", 1000, "Testing time step")
    flags.DEFINE_integer("max_step", 200, "Maximum time step per episode")
    flags.DEFINE_integer("eval_step", 10, "Number of steps before training")
    # flags.DEFINE_integer("training_step", 5000, "Training time step")
    # flags.DEFINE_integer("testing_step", 1000, "Testing time step")
    # flags.DEFINE_integer("max_step", 200, "Maximum time step per episode")
    # flags.DEFINE_integer("eval_step", 1000, "Number of steps before training")

    flags.DEFINE_integer("b_size", 10000, "Size of the replay memory")
    flags.DEFINE_integer("m_size", 64, "Minibatch size")
    flags.DEFINE_integer("pre_train_step", 10, "during [m_size * pre_step] take random action")
    flags.DEFINE_float("lr", 0.0001, "Learning rate")
    # flags.DEFINE_float("lr", 0.01, "Learning rate") # it is for single
    flags.DEFINE_float("df", 0.999, "Discount factor")

    flags.DEFINE_boolean("load_nn", False, "Load nn from file or not")
    flags.DEFINE_string("nn_file", "results/nn/s", "The name of file for loading")
    
    flags.DEFINE_boolean("train", True, "Training or testing")
    flags.DEFINE_boolean("qtrace", False, "Use q trace")
    flags.DEFINE_boolean("kt", False, "Keyboard input test")
    flags.DEFINE_boolean("use_action_in_critic", False, "Use guided samples")




def get_filename():
    import config
    FLAGS = config.flags.FLAGS

    return "a-"+FLAGS.agent+"-lr-"+str(FLAGS.lr)+"-ms-"+str(FLAGS.m_size)