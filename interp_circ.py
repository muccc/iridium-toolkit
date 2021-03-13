import numpy
import matplotlib.pyplot as plt
from numpy.polynomial import Polynomial


def rodrigues_rot(P, n0, n1):
    """Based on https://meshlogic.github.io/posts/jupyter/curve-fitting/fitting-a-circle-to-cluster-of-3d-points/"""
    # If P is only 1d array (coords of single point), fix it to be matrix
    if P.ndim == 1:
        P = P[numpy.newaxis,:]

    # Get vector of rotation k and angle theta
    n0 = n0/numpy.linalg.norm(n0)
    n1 = n1/numpy.linalg.norm(n1)
    k = numpy.cross(n0,n1)
    k = k/numpy.linalg.norm(k)
    theta = numpy.arccos(numpy.dot(n0,n1))

    # Compute rotated points
    P_rot = numpy.zeros((len(P),3))
    for i in range(len(P)):
        P_rot[i] = P[i]*numpy.cos(theta) + numpy.cross(k,P[i])*numpy.sin(theta) + k*numpy.dot(k,P[i])*(1-numpy.cos(theta))

    return P_rot

def lin_interp(y, t, t0, plot=False):
    """ Linear interpolation inside time series y/t"""
    model = numpy.polyfit(t, y, 1)
    p = numpy.poly1d(model)
    y0 = p(t0)

    if plot:
        plt.plot(t, y, "-*")
        plt.scatter([t0], [y0])

        t = numpy.linspace(t[0], t[-1], 100)
        y = p(t)
        plt.plot(t, y)

        plt.show()
    return y0

def quad_interp(y, t, t0, plot=False):
    """ Quadratic interpolation inside time series y/t"""
    p = Polynomial.fit(t, y, deg=2)
    return p(t0)


def interp(P, T, tu, plot=False):
    """ Interpolate time series P/T on a circle """
    P = numpy.array(P)

    # Interpolate radius at time tu
    R = numpy.linalg.norm(P, axis=0)
    r0 = lin_interp(R, T, tu, plot)

    # An attempt to interpolate on an ellipse.
    # Does not improve the result though
    #r0 = quad_interp(R, T, tu, plot)

    P = numpy.transpose(P)

    # Add the origin to the plane. Probably not needed.
    #P = numpy.concatenate((P, [[0,0,0]]))

    #Calculate normal of plane through points
    U,s,V = numpy.linalg.svd(P)
    normal = V[2,:]

    # Rotate points onto XY plane
    P_xy = rodrigues_rot(P, normal, [0,0,1])

    #plt.plot(T, P_xy[:,2])
    #plt.show()
    #P_xy[:,2] = 0
    #plt.plot(T, R)
    #plt.plot(T, numpy.linalg.norm(P_xy, axis=1))
    #plt.show()

    # Get angle over time. Unwrap to remove jumps.
    angles = numpy.unwrap(numpy.arctan2(P_xy[:,0], P_xy[:,1]))

    # Interpolate angle at time tu
    a = lin_interp(angles, T, tu, plot)

    # Calculate new point on the circle
    ix = numpy.sin(a) * r0
    iy = numpy.cos(a) * r0

    # Rotate back onto the plane
    ix, iy, iz = rodrigues_rot(numpy.array([ix, iy, 0]), [0,0,1], normal).flatten()
    return ix, iy, iz
