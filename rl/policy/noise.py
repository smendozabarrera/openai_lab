import numpy as np
from rl.util import logger, log_self
from rl.policy.base_policy import Policy


class DDPGLinearNoisePolicy(Policy):

    '''
    policy with linearly decaying noise (1. / (1. + self.epi))
    TODO absorb under noise too
    '''

    def __init__(self, env_spec,
                 **kwargs):  # absorb generic param without breaking
        super(DDPGLinearNoisePolicy, self).__init__(env_spec)
        self.epi = 0  # init
        log_self(self)

    def select_action(self, state):
        # TODO externalize to policy
        # TODO also try to externalize bounded
        action = self.agent.actor.predict(
            np.expand_dims(state, axis=0)) + (1. / (1. + self.epi))
        return action[0]

    def update(self, sys_vars):
        self.epi = sys_vars['epi'] + 1


class DDPGBoundedPolicy(Policy):

    '''
    The bounded policy for actor critic agents
    and continous, bounded policy spaces
    Action bounded above and below by
    - action_bound, + action_bound
    '''

    def __init__(self, env_spec,
                 **kwargs):  # absorb generic param without breaking
        super(DDPGBoundedPolicy, self).__init__(env_spec)
        self.action_bound = env_spec['action_bound_high']
        assert env_spec['action_bound_high'] == -env_spec['action_bound_low']
        log_self(self)

    def select_action(self, state):
        agent = self.agent
        state = np.expand_dims(state, axis=0)
        A_score = agent.actor.predict(state)[0]  # extract from batch predict
        # action = np.tanh(A_score) * self.action_bound
        action = A_score * self.action_bound
        return action

    def update(self, sys_vars):
        pass


class AnnealedGaussian(Policy):

    '''
    Noise policy, mainly for DDPG.
    Original inspiration from
    https://github.com/matthiasplappert/keras-rl/blob/master/rl/random.py
    '''

    def __init__(self, env_spec,
                 mu, sigma, sigma_min,
                 **kwargs):  # absorb generic param without breaking
        super(AnnealedGaussian, self).__init__(env_spec)
        # epsilon-greedy * noise
        self.init_e = 1.0
        self.final_e = 0.0
        self.e = self.init_e
        self.exploration_anneal_episodes = 100

        self.size = env_spec['action_dim']
        self.action_bound = env_spec['action_bound_high']
        assert env_spec['action_bound_high'] == -env_spec['action_bound_low']
        self.n_steps_annealing = env_spec['timestep_limit'] / 2
        self.mu = mu
        self.sigma = sigma
        self.n_steps = 0

        if sigma_min is not None:
            self.m = -float(sigma - sigma_min) / float(self.n_steps_annealing)
            self.c = sigma
            self.sigma_min = sigma_min
        else:
            self.m = 0.
            self.c = sigma
            self.sigma_min = sigma

    @property
    def current_sigma(self):
        sigma = max(self.sigma_min, self.m * float(self.n_steps) + self.c)
        return sigma

    def select_action(self, state):
        agent = self.agent
        state = np.expand_dims(state, axis=0)
        if self.env_spec['actions'] == 'continuous':
            action = agent.actor.predict(
                state)[0] * self.action_bound + self.sample() * self.e
        else:
            Q_state = agent.actor.predict(state)[0]
            assert Q_state.ndim == 1
            action = np.argmax(Q_state)
            logger.info(str(Q_state)+' '+str(action))
        return action

    def update(self, sys_vars):
        epi = sys_vars['epi']
        rise = self.final_e - self.init_e
        slope = rise / float(self.exploration_anneal_episodes)
        self.e = max(slope * epi + self.init_e, self.final_e)
        return self.e


class GaussianWhiteNoise(AnnealedGaussian):

    def __init__(self, env_spec,
                 mu=0., sigma=.3, sigma_min=None,
                 **kwargs):  # absorb generic param without breaking
        super(GaussianWhiteNoise, self).__init__(
            env_spec, mu, sigma, sigma_min)

    def sample(self):
        sample = np.random.normal(self.mu, self.current_sigma, self.size)
        self.n_steps += 1
        return sample


class OUNoise(AnnealedGaussian):

    '''
    Based on
    http://math.stackexchange.com/questions/1287634/implementing-ornstein-uhlenbeck-in-matlab
    '''

    def __init__(self, env_spec,
                 theta=.15, mu=0., sigma=.3, dt=1e-2, x0=None, sigma_min=None,
                 **kwargs):  # absorb generic param without breaking
        super(OUNoise, self).__init__(
            env_spec, mu, sigma, sigma_min,
            **kwargs)
        self.theta = theta
        self.mu = mu
        self.dt = dt
        self.x0 = x0
        self.reset_states()

    def reset_states(self):
        self.x_prev = self.x0 if self.x0 is not None else np.zeros(self.size)

    def sample(self):
        x = self.x_prev + self.theta * \
            (self.mu - self.x_prev) * self.dt + self.current_sigma * \
            np.sqrt(self.dt) * np.random.normal(size=self.size)
        self.x_prev = x
        self.n_steps += 1
        return x
