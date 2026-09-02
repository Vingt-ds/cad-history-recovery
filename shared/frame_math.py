"""Pure standard-library frame calculations shared with Fusion replay."""

import math


def cross(left, right):
    return (
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    )


def world_point(frame, point_2d):
    origin = frame["origin"]
    x_axis = frame["x_axis"]
    y_axis = cross(frame["normal"], x_axis)
    return tuple(
        origin[index]
        + point_2d[0] * x_axis[index]
        + point_2d[1] * y_axis[index]
        for index in range(3)
    )


def parallel_alignment_error(left, right):
    """Return the unsigned angle between two unit-vector directions."""

    cosine = abs(sum(a * b for a, b in zip(left, right)))
    return math.acos(max(-1.0, min(1.0, cosine)))
