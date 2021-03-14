from scipy.optimize import minimize, LbfgsInvHessProduct
import numpy

def dist(a, b):
    return numpy.linalg.norm(a-b)

def cost_function(approx, deltaranges):
    """
    Cost function for the 3D problem

    Based on code from https://github.com/AlexisTM/MultilaterationTDOA
    TODO: Use weighed least square cost function
    """
    e = 0
    for dr in deltaranges:
        error = dr[2] - (dist(dr[1], approx) - dist(dr[0], approx))
        e += error**2

    #print("cost", approx, deltaranges, "->", e)
    return e


def solve(pseudoranges, guess):
    deltaranges = []
    ref = pseudoranges[0]
    for pseudorange in pseudoranges[1:]:
        deltaranges.append(
            (
                ref[0], # Position of reference station
                pseudorange[0], # Position of second station
                (pseudorange[1] - ref[1]) * 299792458.) # delta range
            )

    result = minimize(cost_function, guess, args=(deltaranges))
    position = result.x

    #if(type(result.hess_inv) == LbfgsInvHessProduct):
    #    hess_inv = result.hess_inv.todense()
    #else:
    #    hess_inv = result.hess_inv
    #dist = self.scalar_hess_squared(hess_inv)
    #if dist < self.max_dist_hess_squared:
    #    self.last_result = position

    #return position, hess_inv
    return position



