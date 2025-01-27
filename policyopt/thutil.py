import numpy as np
import theano
from theano import tensor
import util
import sparsemax_theano

def flatcat(arrays):
    '''
    Flattens arrays and concatenates them in order.
    '''
    return tensor.concatenate([a.flatten() for a in arrays])

def flatgrad(loss, vars_):
    return flatcat(tensor.grad(loss, vars_))

def mixture_gaussian_kl_upbnd(means1_N_D, stdevs1_N_D, mixture1_N_D, means2_N_D, stdevs2_N_D, mixture2_N_D):
    small_num = tensor.constant(1e-10)
    return tensor.sum(mixture1_N_D*(tensor.log((mixture1_N_D+small_num)/(mixture2_N_D+small_num)) + gaussian_kl(means1_N_D, stdevs1_N_D, means2_N_D, stdevs2_N_D)),axis=1)

def mixture_gaussian_ent_upbnd(means1_N_D, stdevs1_N_D, mixture1_N_D):
    small_num = tensor.constant(1e-10)
    D = tensor.shape(means1_N_D)[1]
    return tensor.sum(mixture1_N_D * (-tensor.log(mixture1_N_D + 1e-10) + .5*D*(1. + np.log(2.*np.pi)) + tensor.sum(tensor.log(stdevs1_N_D),axis=1)),axis=1)

def mixture_gaussian_tsallis_dist(means1_N_D, stdevs1_N_D, mixture1_N_D, means2_N_D, stdevs2_N_D, mixture2_N_D, K):
    small_num = tensor.constant(1e-10)
    return 1/8*(gaussian_energy(means1_N_D, stdevs1_N_D, mixture1_N_D, means1_N_D, stdevs1_N_D, mixture1_N_D, K) \
           + gaussian_energy(means2_N_D, stdevs2_N_D, mixture2_N_D, means2_N_D, stdevs2_N_D, mixture2_N_D, K)\
           -2*gaussian_energy(means1_N_D, stdevs1_N_D, mixture1_N_D, means2_N_D, stdevs2_N_D, mixture2_N_D, K))

def mixture_gaussian_tsallis_ent(means1_N_D, stdevs1_N_D, mixture1_N_D, K):
    small_num = tensor.constant(1e-10)
    return 1/2*(1-gaussian_energy(means1_N_D, stdevs1_N_D, mixture1_N_D, means1_N_D, stdevs1_N_D, mixture1_N_D, K))

def gaussian_energy(means1_N_D_K, stdevs1_N_D_K, mixture1_N_D_K, means2_N_D_K, stdevs2_N_D_K, mixture2_N_D_K, K):
    small_num = tensor.constant(1e-10)
    D = tensor.shape(means1_N_D_K)[1]
    components = []
    for i in range(K):
        for j in range(K):
            mu1i = means1_N_D_K[:,:,i]
            std1i = stdevs1_N_D_K[:,:,i]
            pi1i = mixture1_N_D_K[:,i]
            mu2j = means2_N_D_K[:,:,j]
            std2j = stdevs2_N_D_K[:,:,j]
            pi2j = mixture2_N_D_K[:,j]
            _mu = mu1i - mu2j
            _std = std1i + std2j
            _pi = pi1i*pi2j + small_num
            components.append(_pi*tensor.exp(-0.5*tensor.sum(tensor.sqr(_mu/_std),axis=1) - tensor.sum(tensor.log(_std),axis=1) - 0.5*D*np.log(2*np.pi)))
    components = tensor.reshape(tensor.concatenate(components, axis=0),[-1,K**2])
    return tensor.sum(components, axis=1)

def gaussian_kl(means1_N_D, stdevs1_N_D, means2_N_D, stdevs2_N_D):
    '''
    KL divergences between Gaussians with diagonal covariances
    Covariances matrices are specified with square roots of the diagonal (standard deviations)
    '''
    D = tensor.shape(means1_N_D)[1]
    return (
        .5 * (tensor.sqr(stdevs1_N_D/stdevs2_N_D).sum(axis=1) +
              tensor.sqr((means2_N_D-means1_N_D)/stdevs2_N_D).sum(axis=1) +
              2.*(tensor.log(stdevs2_N_D).sum(axis=1) - tensor.log(stdevs1_N_D).sum(axis=1)) - D
        ))

def gaussian_ent(stdevs1_N_D):
    D = tensor.shape(stdevs1_N_D)[1]
    return .5*D*(1. + np.log(2.*np.pi)) + tensor.sum(tensor.log(stdevs1_N_D),axis=1)

def mixture_gaussian_log_density(means_N_D, stdevs_N_D, mixture_N_D, x_N_D):
    small_num = tensor.constant(1e-10)
    D = tensor.shape(means_N_D)[1]
    lognormconsts_B = -.5 * (
    D * np.log(2. * np.pi) + 2. * tensor.log(stdevs_N_D).sum(axis=1))  # log normalization constants
    logprobs_B = -.5 * tensor.sqr((x_N_D.dimshuffle(0,1,'x') - means_N_D) / stdevs_N_D).sum(axis=1) + lognormconsts_B
    exponent = logprobs_B + tensor.log(mixture_N_D + small_num)
    max_exponent = tensor.max(exponent,axis=1)

    return max_exponent + tensor.log(tensor.sum(tensor.exp(exponent-tensor.max(exponent,axis=1,keepdims=True)),axis=1))

def gaussian_log_density(means_N_D, stdevs_N_D, x_N_D):
    '''Log density of a Gaussian distribution with diagonal covariance (specified as standard deviations).'''
    D = tensor.shape(means_N_D)[1]
    lognormconsts_B = -.5*(D*np.log(2.*np.pi) + 2.*tensor.log(stdevs_N_D).sum(axis=1)) # log normalization constants
    logprobs_B = -.5*tensor.sqr((x_N_D - means_N_D)/stdevs_N_D).sum(axis=1) + lognormconsts_B
    return logprobs_B

def sigmoid_cross_entropy_with_logits(logits_B, labels_B):
    return tensor.nnet.binary_crossentropy(tensor.nnet.sigmoid(logits_B), labels_B)

def logsigmoid(a):
    '''Equivalent to tf.log(tf.sigmoid(a))'''
    return -tensor.nnet.softplus(-a)

def logit_bernoulli_kl(logits1_B, logits2_B):
    logp1_B, logp2_B = logsigmoid(logits1_B), logsigmoid(logits2_B)
    logq1_B, logq2_B = logp1_B - logits1_B, logp2_B - logits2_B # these are log(1-p)
    p1_B = tensor.nnet.sigmoid(logits1_B)
    kl_B = p1_B*(logp1_B - logp2_B) + (1.-p1_B)*(logq1_B - logq2_B)
    return kl_B

def logit_bernoulli_entropy(logits_B):
    ent_B = (1.-tensor.nnet.sigmoid(logits_B))*logits_B - logsigmoid(logits_B)
    return ent_B

def logsumexp(a, axis, name=None):
    '''
    Like scipy.misc.logsumexp with keepdims=True
    (does NOT eliminate the singleton axis)
    '''
    amax = a.max(axis=axis, keepdims=True)
    return amax + tensor.log(tensor.exp(a-amax).sum(axis=axis, keepdims=True))

def categorical_ent(logprobs1_B_A, name=None):
    '''KL divergence between categorical distributions, specified as log probabilities'''
    return (tensor.exp(logprobs1_B_A) * (- logprobs1_B_A)).sum(axis=1)

def categorical_tsallis_ent(logprobs1_B_A, name=None):
    B_Pa = sparsemax_theano.sparsemaxdist(logprobs1_B_A)
    return 0.5*(B_Pa*(1-B_Pa)).sum(axis=1)

def categorical_kl(logprobs1_B_A, logprobs2_B_A, name=None):
    '''KL divergence between categorical distributions, specified as log probabilities'''
    kl_B = (tensor.exp(logprobs1_B_A) * (logprobs1_B_A - logprobs2_B_A)).sum(axis=1)
    return kl_B

def categorical_sparse_kl(logprobs1_B_A, logprobs2_B_A, name=None):
    B_Pa = sparsemax_theano.sparsemaxdist(logprobs1_B_A)
    return - (B_Pa*logprobs2_B_A).sum(axis=1) + sparsemax_theano.sparsemax(logprobs2_B_A).mean(axis=1) - 0.5 + 0.5*(B_Pa*B_Pa).sum(axis=1)

def unflatten_into_tensors(flatparams_P, output_shapes, name=None):
    '''
    Unflattens a vector produced by flatcat into a list of tensors of the specified shapes.
    '''
    outputs = []
    curr_pos = 0
    for shape in output_shapes:
        size = np.prod(shape)
        flatval = flatparams_P[curr_pos:curr_pos+size]
        outputs.append(flatval.reshape(shape))
        curr_pos += size
    # assert curr_pos == flatparams_P.get_shape().num_elements()
    return outputs

# from http://arxiv.org/abs/1412.6980
# and https://gist.github.com/Newmu/acb738767acb4788bac3
# suggested lr 0.001
def adam(cost, params, lr, beta1=0.9, beta2=0.999, eps=1e-8):
    updates = []
    grads = tensor.grad(cost, params); assert len(params) == len(grads)
    t0 = theano.shared(np.array(0., dtype=theano.config.floatX))
    t = t0 + 1
    corr1 = (1 - beta1**t)
    corr2 = (1 - beta2**t)
    alpha = lr * tensor.sqrt(corr2) / corr1
    for p, g in zip(params, grads):
        m = theano.shared(value=np.zeros(p.get_value().shape, dtype=theano.config.floatX), broadcastable=p.broadcastable)
        v = theano.shared(value=np.zeros(p.get_value().shape, dtype=theano.config.floatX), broadcastable=p.broadcastable)
        m_t = beta1 * m + (1 - beta1) * g
        v_t = beta2 * v + (1 - beta2) * tensor.square(g)
        p_t = p - alpha * m_t/(tensor.sqrt(v_t) + eps)
        updates.append((m, m_t))
        updates.append((v, v_t))
        updates.append((p, p_t))
    updates.append((t0, t))
    return updates


def function(inputs, outputs, **kwargs):
    # Cache compiled function
    f = theano.function(inputs, outputs, **kwargs)
    def wrapper(*args):
        # Execute
        out = f(*args)
        # Find output elements with shape == () and convert them to scalars
        is_list = isinstance(out, (list,tuple))
        out_as_list = list(out) if is_list else [out]
        for i in xrange(len(out_as_list)):
            if isinstance(out_as_list[i], np.ndarray) and out_as_list[i].shape == ():
                out_as_list[i] = np.asscalar(out_as_list[i])
        return out_as_list if is_list else out_as_list[0]
    return wrapper
