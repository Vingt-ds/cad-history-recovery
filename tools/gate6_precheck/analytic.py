"""Independent rational interval-cell arithmetic, never a CAD boolean oracle."""
from dataclasses import dataclass
from fractions import Fraction
from itertools import product
from math import sqrt

from .contract import ContractError, validate_contract


def rational(value):
    return Fraction(str(value))


@dataclass(frozen=True)
class Box:
    minimum: tuple
    maximum: tuple

    def __post_init__(self):
        object.__setattr__(self, 'minimum', tuple(map(rational, self.minimum)))
        object.__setattr__(self, 'maximum', tuple(map(rational, self.maximum)))
        if len(self.minimum) != 3 or len(self.maximum) != 3 or any(a >= b for a, b in zip(self.minimum, self.maximum)):
            raise ValueError('Box requires three strictly increasing intervals')

    def contains(self, point):
        return all(a < v < b for a, v, b in zip(self.minimum, point, self.maximum))


@dataclass(frozen=True)
class Rectangle:
    axis: int
    coordinate: Fraction
    minimum: tuple
    maximum: tuple
    outward_sign: int

    @property
    def area(self):
        return (self.maximum[0] - self.minimum[0]) * (self.maximum[1] - self.minimum[1])


def _components(cells):
    remaining = set(cells)
    groups = []
    while remaining:
        stack = [remaining.pop()]
        group = set(stack)
        while stack:
            current = stack.pop()
            for axis, direction in product(range(3), (-1, 1)):
                neighbor = list(current)
                neighbor[axis] += direction
                neighbor = tuple(neighbor)
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    group.add(neighbor)
                    stack.append(neighbor)
        groups.append(group)
    return groups


@dataclass(frozen=True)
class Region:
    volume: Fraction
    boundary_rectangles: tuple
    component_count: int
    shell_count: int


class CellOracle:
    def __init__(self, boxes):
        if not boxes:
            raise ValueError('At least one box required')
        self.boxes = dict(boxes)
        self.axes = tuple(tuple(sorted({v for box in boxes.values() for v in (box.minimum[a], box.maximum[a])})) for a in range(3))

    def evaluate(self, predicate):
        counts = tuple(len(axis) - 1 for axis in self.axes)
        all_cells = set(product(*(range(n) for n in counts)))
        occupied = set()
        volume = Fraction(0)
        for cell in sorted(all_cells):
            center = tuple((axis[i] + axis[i + 1]) / 2 for axis, i in zip(self.axes, cell))
            if predicate({name: box.contains(center) for name, box in self.boxes.items()}):
                occupied.add(cell)
                cell_volume = Fraction(1)
                for axis, i in zip(self.axes, cell):
                    cell_volume *= axis[i + 1] - axis[i]
                volume += cell_volume
        rectangles = []
        for cell in sorted(occupied):
            for axis, sign in product(range(3), (-1, 1)):
                neighbor = list(cell)
                neighbor[axis] += sign
                if tuple(neighbor) in occupied:
                    continue
                projected = [a for a in range(3) if a != axis]
                rectangles.append(Rectangle(axis, self.axes[axis][cell[axis] + (sign == 1)],
                                            tuple(self.axes[a][cell[a]] for a in projected),
                                            tuple(self.axes[a][cell[a] + 1] for a in projected), sign))
        components = len(_components(occupied))
        cavities = sum(not any(any(index[a] in (0, counts[a] - 1) for a in range(3)) for index in group)
                       for group in _components(all_cells - occupied))
        # This arithmetic count applies to regular orthogonal material regions;
        # it does not validate a CAD shell or replace shell extraction.
        return Region(volume, tuple(rectangles), components, components + cavities)


def static_expectations(config):
    """Recompute the frozen arithmetic without constructing any CAD geometry."""
    result = {}
    for group in ('OS', 'DE'):
        boxes = {name: Box(config['solids'][key]['min'], config['solids'][key]['max'])
                 for name, key in (('B', 'B'), ('J', 'J'), ('C', 'C_' + group))}
        oracle = CellOracle(boxes)
        formulas = {
            'B': lambda p: p['B'], 'J': lambda p: p['J'], 'C': lambda p: p['C'],
            'after_J': lambda p: p['B'] or p['J'],
            'after_C': lambda p: p['B'] and not p['C'],
            'final_JC': lambda p: (p['B'] or p['J']) and not p['C'],
            'final_CJ': lambda p: (p['B'] and not p['C']) or p['J'],
            'difference': lambda p: p['J'] and p['C'],
            'join_on_base': lambda p: p['J'] and not p['B'],
            'cut_after_join': lambda p: p['C'] and (p['B'] or p['J']),
            'cut_on_base': lambda p: p['C'] and p['B'],
            'join_after_cut': lambda p: p['J'] and not (p['B'] and not p['C']),
            'connectivity_on_base': lambda p: p['J'] and p['B'],
            'connectivity_after_cut': lambda p: p['J'] and p['B'] and not p['C'],
        }
        regions = {name: oracle.evaluate(formula) for name, formula in formulas.items()}
        values = {name: region.volume for name, region in regions.items()}
        values.update(shells_JC=regions['final_JC'].shell_count, shells_CJ=regions['final_CJ'].shell_count)
        values.update(shells_after_J=regions['after_J'].shell_count,
                      shells_after_C=regions['after_C'].shell_count)
        result[group] = values
    return result


def verify_expected(config):
    validate_contract(config)
    computed = static_expectations(config)
    for group, expected in config['expected'].items():
        for key, value in expected.items():
            if computed[group][key] != value:
                raise ContractError('analytic_expectation_mismatch', f'{group}.{key}: {computed[group][key]} != {value}')
    # Section 7 of the byte-bound prose contract specifies intermediate shells;
    # these fields are deliberately not added to the frozen JSON specification.
    for group, after_cut in (('OS', 1), ('DE', 2)):
        if computed[group]['shells_after_J'] != 1 or computed[group]['shells_after_C'] != after_cut:
            raise ContractError('analytic_expectation_mismatch', f'{group}: intermediate shell counts differ')
    j, c = (config['solids'][name] for name in ('J', 'C_DE'))
    gap_squared = sum(max(0, j['min'][a] - c['max'][a], c['min'][a] - j['max'][a]) ** 2 for a in range(3))
    if gap_squared != 328 or sqrt(gap_squared) <= config['tolerances']['gap_mm']:
        raise ContractError('disjoint_margin_failure', 'Static DE gap failed')
    if computed['OS']['difference'] < config['tolerances']['separation_volume_mm3']:
        raise ContractError('separation_margin_failure', 'Static OS separation failed')
    return True
