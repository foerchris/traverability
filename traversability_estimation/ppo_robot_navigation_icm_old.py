#!/usr/bin/env python2
# -*- coding: utf-8

import math
import random

import numpy as np
from torchviz import make_dot

import torch
import torch.nn as nn
from numpy import number
from torch.distributions import Normal
import tensorflow as tf

import matplotlib.pyplot as plt

import rospy
from collections import deque
from time import  sleep
import gc
import os
dirname = os.path.dirname(__file__)

use_cuda = torch.cuda.is_available()
device   = torch.device("cuda" if use_cuda else "cpu")
torch.cuda.empty_cache()
import sys
sys.path.append(os.path.join(dirname, 'common'))
from tensorboardX import SummaryWriter


from multiprocessing_env import SubprocVecEnv
from robot_env import robotEnv

from agents import Agent


MODELPATH = os.path.join(dirname, 'train_getjag/ppo/Model')

load_model = False
last_number_of_frames = 0
frame_idx  = 0 + last_number_of_frames
num_envs_possible = 16;
num_envs = 0;

summary_writer = tf.summary.FileWriter("train_getjag/ppo/Tensorboard")

#test_writer = tf.summary.FileWriter("train_getjag/train_" + str(0), sess.graph)

writer = SummaryWriter("train_getjag/ppo/Tensorboard")
for i in range(num_envs_possible):
    if (rospy.has_param("/GETjag" + str(i) + "/worker_ready")):
        if (rospy.get_param("/GETjag" + str(i) + "/worker_ready")):
            num_envs += 1
            print("worker_", num_envs)

def make_env(i):
    def _thunk():
        #env = gym.make(env_name)
        env =  robotEnv(i)
        return env

    return _thunk

envs = [make_env(i+1) for i in range(num_envs)]

envs = SubprocVecEnv(envs)

#env = robotEnv(1)


state_size_map  = envs.observation_space[0].shape[0] * envs.observation_space[0].shape[1]
state_size_depth  = envs.observation_space[1].shape[0] * envs.observation_space[1].shape[1]
state_size_goal   = envs.observation_space[2].shape[0]


num_outputs = envs.action_space.shape[0]

stack_size = 1
stack_size_depth = 4
class image_stacker():
    def __init__(self, state_size, stack_size):
        self.stacked_frames = deque([np.zeros((state_size_map), dtype=np.float16) for i in range(stack_size)], maxlen=stack_size)
    def return_stacked_frame(self):
            return self.stacked_frames





stacked_map_frames = deque([np.zeros((num_envs,state_size_map/state_size_map,state_size_map/state_size_map), dtype=np.float16) for i in range(stack_size)], maxlen=stack_size)
stacked_depth_frames = deque([np.zeros((num_envs,state_size_depth/state_size_depth,state_size_depth/state_size_depth), dtype=np.float16) for i in range(stack_size_depth)], maxlen=stack_size)
stacked_goal_frames = deque([np.zeros((num_envs,state_size_goal), dtype=np.float16) for i in range(stack_size)], maxlen=stack_size)


def reset_single_frame(stacked_frames, state, stack_size, number):

    for i in range(0, stack_size, 1):
        #stacked_frames.append(state)
        stacked_frames[i][number] = state

    stacked_state = np.stack(stacked_frames, axis=1)

    return stacked_state, stacked_frames

def stack_frames(stacked_frames, state, stack_size, is_new_episode):

    if is_new_episode:
        # Clear our stacked_frames
        stacked_frames = deque([np.zeros((state.shape), dtype=np.float16) for i in range(stack_size)], maxlen=stack_size)


        # Because we're in a new episode, copy the same frame 4x
        for i in range(0, stack_size, 1):

            stacked_frames.append(state)


        # Stack the frames
        stacked_state = np.stack(stacked_frames, axis=1)


    else:

        stacked_frames.append(state)

        # Build the stacked state (first dimension specifies different frames)
        stacked_state = np.stack(stacked_frames, axis=1)

    return stacked_state, stacked_frames


def plot(frame_idx, rewards):
    #plt.figure(figsize=(20, 5))
   # plt.subplot(131)
    #print("frame_idx" + str(frame_idx))
    #print("rewards" + str(rewards))

    plt.title('frame %s. reward: %s' % (frame_idx, rewards[-1]))
    plt.plot(rewards)
    plt.show(block=False)


#Hyper params:
hidden_size      = 576
lr               = 1e-4
lr_decay_epoch   = 60.0
init_lr          = lr
epoch            = 0.0

max_num_steps    = 300
num_steps        = 500
mini_batch_size  = 10
ppo_epochs       = 8
GAMMA            = 0.99
GAE_LAMBDA       = 0.95
PPO_EPSILON      = 0.2
CRICIC_DISCOUNT  = 0.5
ENTROPY_BETA     = 0.01
eta              = 0.01
threshold_reward = 5
#


agent = Agent(state_size_map, state_size_depth , state_size_goal, num_outputs, hidden_size, stack_size, load_model, MODELPATH, lr, mini_batch_size, num_envs, lr_decay_epoch, init_lr, eta)
max_frames = 500000
test_rewards = []

#decay_ppo_epsilon = tf.train.polynomial_decay(PPO_EPSILON, frame_idx, max_num_steps, 1e-2, power=1.0)
#learning_rate = tf.train.polynomial_decay(lr, frame_idx, max_num_steps, 1e-5, power=1.0)
#optimizer = optim.Adam(model.parameters(), lr=learning_rate )

episode_length = []
for i in range(0, num_envs):
    episode_length.append(max_num_steps)

envs.set_episode_length(episode_length)


early_stop = False

best_reward = 0

map_state,depth_state, goal_state = envs.reset()

map_state, stacked_map_frames = stack_frames(stacked_map_frames, map_state, stack_size, True)
depth_state, stacked_depth_frames = stack_frames(stacked_depth_frames, depth_state, stack_size_depth, True)
goal_state, stacked_goal_frames = stack_frames(stacked_goal_frames, goal_state, stack_size, True)

agent.ac_model.hidden = agent.ac_model.init_hidden(num_envs)
(hidden_state_h, hidden_state_c) = agent.ac_model.hidden

done_cache = []
step_count = []
total_reward = []
total_total_reward = []
total_step_count = []
for i in range(0, num_envs):
    done_cache.append(False)
    step_count.append(0)
    total_reward.append(0)

while frame_idx < max_frames and not early_stop:

    log_probs = []
    values = []
    map_states = []
    depth_states = []
    goal_states = []
    hidden_states_h = []
    hidden_states_c = []
    actions = []
    rewards = []
    masks = []
    entropy = 0

    agent.ac_model.eval()
    agent.icm_model.eval()
    total_reward_worker1 = []
    for i in range(0, num_envs):
        total_reward_worker1.append(0)

    with torch.no_grad():
        for _ in range(num_steps):


            map_state = torch.FloatTensor(map_state).to(device)
            depth_state = torch.FloatTensor(depth_state).to(device)
            goal_state = torch.FloatTensor(goal_state).to(device)

            hidden_states_h.append(hidden_state_h)
            hidden_states_c.append(hidden_state_c)

            dist, value, next_hidden_state_h, next_hidden_state_c = agent.ac_model( map_state, depth_state, goal_state, hidden_state_h, hidden_state_c)

            action = dist.sample()

            # this is a x,1 tensor is kontains alle the possible actions
            # the cpu command move it from a gpu tensor to a cpu tensor
            next_map_state, next_depth_state, next_goal_state, reward, done, _ = envs.step( action.cpu().numpy())


            for i in range(0, num_envs):
                if (done[i] == True):
                    _, stacked_map_frames = reset_single_frame(stacked_map_frames, next_map_state[i], stack_size, i)
                    _, stacked_depth_frames = reset_single_frame(stacked_depth_frames, next_depth_state[i], stack_size_depth,
                                                                 i)
                    _, stacked_goal_frames = reset_single_frame(stacked_goal_frames, next_goal_state[i], stack_size, i)

                    (single_hidden_state_h, single_hidden_state_c) = agent.ac_model.init_hidden(1)
                    next_hidden_state_h[0][i] = single_hidden_state_h
                    next_hidden_state_c[0][i] = single_hidden_state_c




            next_map_state, stacked_map_frames = stack_frames(stacked_map_frames,next_map_state,stack_size, False)
            next_depth_state, stacked_depth_frames = stack_frames(stacked_depth_frames,next_depth_state,stack_size_depth, False)
            next_goal_state, stacked_goal_frames = stack_frames(stacked_goal_frames,next_goal_state,stack_size, False)

            # total reward = int reward
            intrinsic_reward = agent.compute_intrinsic_reward(map_state, depth_state, goal_state, hidden_state_h, hidden_state_c,
                                                              torch.FloatTensor(next_map_state).to(device), torch.FloatTensor(next_depth_state).to(device), torch.FloatTensor(next_goal_state).to(device),
                                                              next_hidden_state_h, next_hidden_state_c, action)

            reward +=  intrinsic_reward
            total_reward += reward

            for i in range(0, num_envs):
                step_count[i] += 1
                if (done[i] == True):
                    total_step_count.append(step_count[i])
                    step_count[i] = 0
                    total_total_reward.append(total_reward[i])
                    total_reward[i] = 0

            #sample_i_rall += intrinsic_reward[sample_env_idx]
            log_prob = dist.log_prob(action)
            entropy += dist.entropy().mean()

            log_probs.append(log_prob)
            values.append(value)
            reward = torch.FloatTensor(reward).unsqueeze(1).to(device)
            rewards.append(reward)
            done = torch.FloatTensor(1 - done).unsqueeze(1).to(device)
            masks.append(done)

            map_states.append(map_state)
            depth_states.append(depth_state)
            goal_states.append(goal_state)

            actions.append(action)

            map_state = next_map_state
            depth_state = next_depth_state
            goal_state = next_goal_state

            #torch.cuda.empty_cache()
            frame_idx += 1

            if frame_idx % 1000 == 0:
                #mean_test_rewards = []
                #mean_test_lenghts = []
                #mean_test_log_probs = []
                #mean_test_values = []
                #mean_test_entropy = []
                #print("test env")

                #for _ in range(5):
                #    test_reward, test_lenght, test_log_probs, test_values, test_entropy = multi_test_env()

                #    mean_test_rewards.append( np.mean(test_reward))
                 #   mean_test_lenghts.append( np.mean(test_lenght))
                 #   mean_test_log_probs.append(np.mean(test_log_probs))
                 #   mean_test_values.append(np.mean(test_values))
                #    mean_test_entropy.append(test_entropy)

                mean_test_rewards = np.mean(total_total_reward)
                total_total_reward = []
                mean_test_lenghts = np.mean(total_step_count)
                total_step_count = []
                #mean_test_log_probs = np.mean(mean_test_log_probs)
                #mean_test_values = np.mean(mean_test_values)
                #mean_test_entropy = np.mean(mean_test_entropy)

                test_rewards.append(mean_test_rewards)
                print("update tensorboard")
                #plot(frame_idx, test_rewards)
                summary = tf.Summary()
                summary.value.add(tag='Perf/mean_test_rewards', simple_value=float(mean_test_rewards))
                summary.value.add(tag='Perf/mean_test_lenghts', simple_value=float(mean_test_lenghts))
                #summary.value.add(tag='Perf/mean_test_log_probs', simple_value=float(mean_test_log_probs))
                #summary.value.add(tag='Perf/mean_test_values', simple_value=float(mean_test_values))
                #summary.value.add(tag='Perf/mean_test_entropy', simple_value=float(mean_test_entropy))
                summary_writer.add_summary(summary, frame_idx)

                for name, param in agent.ac_model.named_parameters():
                    if param.requires_grad:
                        tensor = param.data
                        tensor = tensor.cpu().numpy()
                        writer.add_histogram(name, tensor, bins='doane')

                print("updated tensorboard")

                if best_reward is None or best_reward < mean_test_rewards:
                    if best_reward is not None:
                        print("Best reward updated: %.3f -> %.3f" % (best_reward, mean_test_rewards))
                        name = "%s_best_%+.3f_%d.dat" % ('ppo_robot_nav', mean_test_rewards, frame_idx)
                        #fname = os.path.join('.', 'checkpoints', name)
                        torch.save(agent.ac_model.state_dict(), MODELPATH + name)
                    best_reward = mean_test_rewards

                if mean_test_rewards > threshold_reward: early_stop = True
                torch.save(agent.ac_model.state_dict(), MODELPATH + '/save_ppo_ac_model.dat')
                torch.save(agent.icm_model.state_dict(), MODELPATH + '/save_ppo_icm_model.dat')


            next_map_state = torch.FloatTensor(next_map_state).to(device)
            next_depth_state = torch.FloatTensor(next_depth_state).to(device)
            next_goal_state = torch.FloatTensor(next_goal_state).to(device)

            hidden_state_h = next_hidden_state_h
            hidden_state_c = next_hidden_state_c


    agent.ac_model.train()
    agent.icm_model.train()

    _, next_value, hidden_state_h, hidden_state_c = agent.ac_model(next_map_state, next_depth_state, next_goal_state, hidden_state_h, hidden_state_c)
    returns = agent.compute_gae(next_value, rewards, masks, values, GAMMA, GAE_LAMBDA)

    returns = torch.cat(returns).detach()
    log_probs = torch.cat(log_probs).detach()
    values = torch.cat(values).detach()
    map_states = torch.cat(map_states)
    depth_states = torch.cat(depth_states)
    goal_states = torch.cat(goal_states)
    hidden_states_h = torch.cat(hidden_states_h)
    hidden_states_c = torch.cat(hidden_states_c)

    hidden_states_h = hidden_states_h.view(-1, 1, hidden_states_h.shape[2])
    hidden_states_c = hidden_states_c.view(-1, 1, hidden_states_c.shape[2])


    actions = torch.cat(actions)
    advantages = returns - values

    epoch += 1.0
    agent.ppo_update(frame_idx, ppo_epochs,  map_states, depth_states, goal_states, hidden_states_h, hidden_states_c , actions, log_probs, returns, advantages, values, epoch, PPO_EPSILON, CRICIC_DISCOUNT, ENTROPY_BETA)

