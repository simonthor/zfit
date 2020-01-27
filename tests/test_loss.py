#  Copyright (c) 2020 zfit
import numpy as np
import pytest
import tensorflow as tf

import zfit.core.basepdf
import zfit.models.dist_tfp
import zfit.settings
from zfit import z
from zfit.core.limits import Space
from zfit.core.loss import UnbinnedNLL
from zfit.core.testing import setup_function, teardown_function, tester
from zfit.minimizers.minimizer_minuit import Minuit
from zfit.models.dist_tfp import Gauss
from zfit.util.exception import IntentionNotUnambiguousError

mu_true = 1.2
sigma_true = 4.1
mu_true2 = 1.01
sigma_true2 = 3.5

yield_true = 3000
test_values_np = np.random.normal(loc=mu_true, scale=sigma_true, size=(yield_true, 1))
test_values_np2 = np.random.normal(loc=mu_true2, scale=sigma_true2, size=yield_true)

low, high = -24.3, 28.6


def create_params1(nameadd=""):
    mu1 = zfit.Parameter("mu1" + nameadd, z.to_real(mu_true) - 0.2, mu_true - 1., mu_true + 1.)
    sigma1 = zfit.Parameter("sigma1" + nameadd, z.to_real(sigma_true) - 0.3, sigma_true - 2., sigma_true + 2.)
    return mu1, sigma1


def create_params2(nameadd=""):
    mu2 = zfit.Parameter("mu25" + nameadd, z.to_real(mu_true) - 0.2, mu_true - 1., mu_true + 1.)
    sigma2 = zfit.Parameter("sigma25" + nameadd, z.to_real(sigma_true) - 0.3, sigma_true - 2., sigma_true + 2.)
    return mu2, sigma2


def create_params3(nameadd=""):
    mu3 = zfit.Parameter("mu35" + nameadd, z.to_real(mu_true) - 0.2, mu_true - 1., mu_true + 1.)
    sigma3 = zfit.Parameter("sigma35" + nameadd, z.to_real(sigma_true) - 0.3, sigma_true - 2., sigma_true + 2.)
    yield3 = zfit.Parameter("yield35" + nameadd, yield_true + 300, 0, yield_true + 20000)
    return mu3, sigma3, yield3


obs1 = 'obs1'

mu_constr = [1.6, 0.2]  # mu, sigma
sigma_constr = [3.8, 0.2]
constr = lambda: [mu_constr[1], sigma_constr[1]]
constr_tf = lambda: z.convert_to_tensor(constr())
covariance = lambda: np.array([[mu_constr[1] ** 0.5, -0.05], [-0.05, sigma_constr[1] ** 0.5]])
covariance_tf = lambda: z.convert_to_tensor(covariance())


def create_gauss1():
    mu, sigma = create_params1()
    return Gauss(mu, sigma, obs=obs1, name="gaussian1"), mu, sigma


def create_gauss2():
    mu, sigma = create_params2()
    return Gauss(mu, sigma, obs=obs1, name="gaussian2"), mu, sigma


def create_gauss3ext():
    mu, sigma, yield3 = create_params3()
    gaussian3 = Gauss(mu, sigma, obs=obs1, name="gaussian3")
    gaussian3 = gaussian3.create_extended(yield3)
    return gaussian3, mu, sigma, yield3


@pytest.mark.flaky(3)  # minimization can fail
def test_extended_unbinned_nll():
    test_values = z.constant(test_values_np)
    test_values = zfit.Data.from_tensor(obs=obs1, tensor=test_values)
    gaussian3, mu3, sigma3, yield3 = create_gauss3ext()
    nll_object = zfit.loss.ExtendedUnbinnedNLL(model=gaussian3,
                                               data=test_values,
                                               fit_range=(-20, 20))
    minimizer = Minuit()
    status = minimizer.minimize(loss=nll_object)
    params = status.params
    assert params[mu3]['value'] == pytest.approx(np.mean(test_values_np), rel=0.005)
    assert params[sigma3]['value'] == pytest.approx(np.std(test_values_np), rel=0.005)
    assert params[yield3]['value'] == pytest.approx(yield_true, rel=0.005)


def test_unbinned_simultaneous_nll():
    test_values = tf.constant(test_values_np)
    test_values = zfit.Data.from_tensor(obs=obs1, tensor=test_values)
    test_values2 = tf.constant(test_values_np2)
    test_values2 = zfit.Data.from_tensor(obs=obs1, tensor=test_values2)
    gaussian1, mu1, sigma1 = create_gauss1()
    gaussian2, mu2, sigma2 = create_gauss2()
    nll_object = zfit.loss.UnbinnedNLL(model=[gaussian1, gaussian2],
                                       data=[test_values, test_values2],
                                       fit_range=[(-np.infty, np.infty), (-np.infty, np.infty)]
                                       )
    minimizer = Minuit()
    status = minimizer.minimize(loss=nll_object, params=[mu1, sigma1, mu2, sigma2])
    params = status.params
    assert params[mu1]['value'] == pytest.approx(np.mean(test_values_np), rel=0.005)
    assert params[mu2]['value'] == pytest.approx(np.mean(test_values_np2), rel=0.005)
    assert params[sigma1]['value'] == pytest.approx(np.std(test_values_np), rel=0.005)
    assert params[sigma2]['value'] == pytest.approx(np.std(test_values_np2), rel=0.005)


@pytest.mark.flaky(3)
@pytest.mark.parametrize('weights', (None, np.random.normal(loc=1., scale=0.2, size=test_values_np.shape[0])))
@pytest.mark.parametrize('sigma', (constr, covariance, constr_tf))
def test_unbinned_nll(weights, sigma):
    gaussian1, mu1, sigma1 = create_gauss1()
    gaussian2, mu2, sigma2 = create_gauss2()

    test_values = tf.constant(test_values_np)
    test_values = zfit.Data.from_tensor(obs=obs1, tensor=test_values, weights=weights)
    nll_object = zfit.loss.UnbinnedNLL(model=gaussian1, data=test_values, fit_range=(-np.infty, np.infty))
    minimizer = Minuit()
    status = minimizer.minimize(loss=nll_object, params=[mu1, sigma1])
    params = status.params
    rel_error = 0.005 if weights is None else 0.1  # more fluctuating with weights

    assert params[mu1]['value'] == pytest.approx(np.mean(test_values_np), rel=rel_error)
    assert params[sigma1]['value'] == pytest.approx(np.std(test_values_np), rel=rel_error)

    constraints = zfit.constraint.nll_gaussian(x=[mu_constr[0], sigma_constr[0]],
                                               mu=[mu2, sigma2],
                                               sigma=sigma())
    nll_object = UnbinnedNLL(model=gaussian2, data=test_values, fit_range=(-np.infty, np.infty),
                             constraints=constraints)

    minimizer = Minuit()
    status = minimizer.minimize(loss=nll_object, params=[mu2, sigma2])
    params = status.params
    if weights is None:
        assert params[mu2]['value'] > np.mean(test_values_np)
        assert params[sigma2]['value'] < np.std(test_values_np)


def test_add():
    param1 = zfit.Parameter("param1", 1.)
    param2 = zfit.Parameter("param2", 2.)

    pdfs = [0] * 4
    pdfs[0] = Gauss(param1, 4, obs=obs1)
    pdfs[1] = Gauss(param2, 5, obs=obs1)
    pdfs[2] = Gauss(3, 6, obs=obs1)
    pdfs[3] = Gauss(4, 7, obs=obs1)

    datas = [0] * 4
    datas[0] = z.constant(1.)
    datas[1] = z.constant(2.)
    datas[2] = z.constant(3.)
    datas[3] = z.constant(4.)

    ranges = [0] * 4
    ranges[0] = (1, 4)
    ranges[1] = Space(limits=(2, 5), obs=obs1)
    ranges[2] = Space(limits=(3, 6), obs=obs1)
    ranges[3] = Space(limits=(4, 7), obs=obs1)

    constraint1 = zfit.constraint.nll_gaussian(x=1, mu=param1, sigma=0.5)
    constraint2 = zfit.constraint.nll_gaussian(x=2, mu=param1, sigma=0.25)
    merged_contraints = [constraint1, constraint2]

    nll1 = UnbinnedNLL(model=pdfs[0], data=datas[0], fit_range=ranges[0], constraints=constraint1)
    nll2 = UnbinnedNLL(model=pdfs[1], data=datas[1], fit_range=ranges[1], constraints=constraint2)
    nll3 = UnbinnedNLL(model=[pdfs[2], pdfs[3]], data=[datas[2], datas[3]], fit_range=[ranges[2], ranges[3]])

    simult_nll = nll1 + nll2 + nll3

    assert simult_nll.model == pdfs
    assert simult_nll.data == datas

    ranges[0] = Space._from_any(limits=ranges[0], obs=obs1,
                                axes=(0,))  # for comparison, Space can only compare with Space
    ranges[1]._axes = (0,)
    ranges[2]._axes = (0,)
    ranges[3]._axes = (0,)
    assert simult_nll.fit_range == ranges

    def eval_constraint(constraints):
        return z.reduce_sum([c.value() for c in constraints]).numpy()

    assert eval_constraint(simult_nll.constraints) == eval_constraint(merged_contraints)


# @pytest.mark.xfail  # TODO(TF2): grads not supported, use numerical ones? Or calculate on the fly?
@pytest.mark.parametrize("chunksize", [10000000, 1000])
def test_gradients(chunksize):
    from numdifftools import Gradient
    zfit.run.chunking.active = True
    zfit.run.chunking.max_n_points = chunksize

    initial1 = 1.
    initial2 = 2;
    param1 = zfit.Parameter("param1", initial1)
    param2 = zfit.Parameter("param2", initial2)

    gauss1 = Gauss(param1, 4, obs=obs1)
    gauss1.set_norm_range((-5, 5))
    gauss2 = Gauss(param2, 5, obs=obs1)
    gauss2.set_norm_range((-5, 5))

    data1 = zfit.Data.from_tensor(obs=obs1, tensor=z.constant(1., shape=(100,)))
    data1.set_data_range((-5, 5))
    data2 = zfit.Data.from_tensor(obs=obs1, tensor=z.constant(1., shape=(100,)))
    data2.set_data_range((-5, 5))

    nll = UnbinnedNLL(model=[gauss1, gauss2], data=[data1, data2])

    def loss_func(values):
        for val, param in zip(values, nll.get_dependents(only_floating=True)):
            param.set_value(val)
        return nll.value().numpy()

    # theoretical, numerical = tf.test.compute_gradient(loss_func, list(params))
    gradient1 = nll.gradients(params=param1)
    gradient_func = Gradient(loss_func)
    # gradient_func = lambda *args, **kwargs: list(gradient_func_numpy(*args, **kwargs))
    assert gradient1[0].numpy() == pytest.approx(gradient_func([param1.numpy()]))
    param1.set_value(initial1)
    param2.set_value(initial2)
    params = [param2, param1]
    gradient2 = nll.gradients(params=params)
    both_gradients_true = list(reversed(list(gradient_func([initial1, initial2]))))  # because param2, then param1
    assert [g.numpy() for g in gradient2] == pytest.approx(both_gradients_true)

    param1.set_value(initial1)
    param2.set_value(initial2)
    gradient3 = nll.gradients()
    assert frozenset([g.numpy() for g in gradient3]) == pytest.approx(frozenset(both_gradients_true))


def test_simple_loss():
    true_a = 1.
    true_b = 4.
    true_c = -0.3
    a_param = zfit.Parameter("variable_a15151loss", 1.5, -1., 20.,
                             step_size=z.constant(0.1))
    b_param = zfit.Parameter("variable_b15151loss", 3.5)
    c_param = zfit.Parameter("variable_c15151loss", -0.23)
    param_list = [a_param, b_param, c_param]

    def loss_func():
        probs = z.convert_to_tensor((a_param - true_a) ** 2
                                    + (b_param - true_b) ** 2
                                    + (c_param - true_c) ** 4) + 0.42
        return tf.reduce_sum(input_tensor=tf.math.log(probs))

    loss_deps = zfit.loss.SimpleLoss(func=loss_func, dependents=param_list)
    # loss = zfit.loss.SimpleLoss(func=loss_func)
    loss = zfit.loss.SimpleLoss(func=loss_func, dependents=param_list)

    assert loss_deps.get_dependents() == set(param_list)
    # assert loss.get_dependents() == set(param_list)  # TODO: uncomment if auto deps available again?

    loss_tensor = loss_func()
    loss_value_np = loss_tensor.numpy()

    assert loss.value().numpy() == loss_value_np
    assert loss_deps.value().numpy() == loss_value_np

    with pytest.raises(IntentionNotUnambiguousError):
        _ = loss + loss_deps

    minimizer = zfit.minimize.Minuit()
    result = minimizer.minimize(loss=loss)

    assert true_a == pytest.approx(result.params[a_param]['value'], rel=0.03)
    assert true_b == pytest.approx(result.params[b_param]['value'], rel=0.06)
    assert true_c == pytest.approx(result.params[c_param]['value'], rel=0.5)
