"""Geometry shared by the eraser and date-anchored stamps."""
import math


def distance_to_segment(point, a, b):
    x,y = point
    dx,dy = b[0]-a[0],b[1]-a[1]
    length = dx*dx+dy*dy
    t = max(0,min(1,((x-a[0])*dx+(y-a[1])*dy)/length)) if length else 0
    return math.hypot(x-a[0]-t*dx,y-a[1]-t*dy)


def segment_distance(a, b, c, d):
    """Distance between two closed line segments, including intersections."""
    def cross(p, q, r):
        return (q[0]-p[0])*(r[1]-p[1])-(q[1]-p[1])*(r[0]-p[0])
    ab_c, ab_d = cross(a,b,c), cross(a,b,d)
    cd_a, cd_b = cross(c,d,a), cross(c,d,b)
    if ((ab_c > 0 and ab_d < 0) or (ab_c < 0 and ab_d > 0)) and ((cd_a > 0 and cd_b < 0) or (cd_a < 0 and cd_b > 0)):
        return 0
    return min(distance_to_segment(a,c,d),distance_to_segment(b,c,d),distance_to_segment(c,a,b),distance_to_segment(d,a,b))


def stroke_hit(stroke, point, width, height, radius, previous=None):
    points = [(a*width,b*height) for a,b in stroke['points']]
    radius += stroke['width']*width/700/2
    previous = previous if previous is not None else point
    if len(points) == 1:
        return distance_to_segment(points[0],previous,point) <= radius
    return any(segment_distance(previous,point,a,b) <= radius for a,b in zip(points,points[1:]))
