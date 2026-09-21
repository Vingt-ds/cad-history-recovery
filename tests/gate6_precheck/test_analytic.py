import copy
import unittest
from fractions import Fraction

from tools.gate6_precheck.analytic import Box, CellOracle, static_expectations, verify_expected
from tools.gate6_precheck.contract import ContractError, load_contract


class AnalyticTests(unittest.TestCase):
    def test_cavity_volume_surface_and_components(self):
        oracle = CellOracle({'outer': Box((0, 0, 0), (3, 3, 3)),
                             'hole': Box((1, 1, 1), (2, 2, 2))})
        result = oracle.evaluate(lambda inside: inside['outer'] and not inside['hole'])
        self.assertEqual(result.volume, 26)
        self.assertEqual(result.component_count, 1)
        self.assertEqual(result.shell_count, 2)
        self.assertEqual(sum(r.area for r in result.boundary_rectangles), 60)

    def test_fractional_disconnected_boxes(self):
        oracle = CellOracle({'a': Box((0, 0, 0), ('0.5', 1, 1)),
                             'b': Box((2, 0, 0), (3, 1, 1))})
        region = oracle.evaluate(lambda inside: any(inside.values()))
        self.assertEqual(region.volume, Fraction(3, 2))
        self.assertEqual(region.component_count, 2)
        self.assertEqual(region.shell_count, 2)

    def test_static_arithmetic_contract_only(self):
        self.assertTrue(verify_expected(load_contract()))

    def test_intermediate_shell_counts_from_prose_contract(self):
        values = static_expectations(load_contract())
        self.assertEqual(values['OS']['shells_after_J'], 1)
        self.assertEqual(values['OS']['shells_after_C'], 1)
        self.assertEqual(values['DE']['shells_after_J'], 1)
        self.assertEqual(values['DE']['shells_after_C'], 2)

    def test_reject_removed_expected_contract(self):
        config = copy.deepcopy(load_contract())
        config['expected'] = {}
        with self.assertRaises(ContractError) as caught:
            verify_expected(config)
        self.assertEqual(caught.exception.code, 'specification_binding_failure')

    def test_reject_empty_or_inverted_box(self):
        with self.assertRaises(ValueError):
            Box((0, 0, 0), (0, 1, 1))
