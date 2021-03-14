from scipy.optimize import minimize, LbfgsInvHessProduct
import numpy

def dist(a, b):
    return numpy.linalg.norm(a-b)

def cost_function(approx, measurements):
    """
    Cost function for the 3D problem

    Based on code from https://github.com/AlexisTM/MultilaterationTDOA
    TODO: Use weighed least square cost function
    """
    e = 0
    for mea in measurements:
        error = mea[2] - (dist(mea[1], approx) - dist(mea[0], approx))
        e += error**2

    #print("cost", approx, measurements, "->", e)
    return e


def solve(measurements, last_result):
    """Optimize the position for LSE using in a 3D problem."""
    approx = last_result
    result = minimize(cost_function, approx, args=(measurements))
    position = result.x

    #if(type(result.hess_inv) == LbfgsInvHessProduct):
    #    hess_inv = result.hess_inv.todense()
    #else:
    #    hess_inv = result.hess_inv
    #dist = self.scalar_hess_squared(hess_inv)
    #if dist < self.max_dist_hess_squared:
    #    self.last_result = position

    last_result = position
    #return position, hess_inv
    return position



