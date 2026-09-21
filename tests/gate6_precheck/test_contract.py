import copy
import unittest

from tools.gate6_precheck.contract import canonical_json_bytes, load_contract, ContractError, validate_contract


class ContractTests(unittest.TestCase):
    def test_frozen_contract_and_canonical_numbers(self):
        spec = load_contract()
        self.assertEqual(spec['execution_authorization'], 'not_granted')
        self.assertEqual(canonical_json_bytes({'z': 1e-7, 'a': [0.00001, -0.0, 0.5]}),
                         b'{"a":[0.00001,0,0.5],"z":1e-7}')

    def test_reject_mutated_contract(self):
        spec = copy.deepcopy(load_contract())
        spec['tolerances']['volume_mm3'] = 0.01
        with self.assertRaises(ContractError):
            validate_contract(spec)

    def test_reject_nonfinite_and_out_of_domain_numbers(self):
        for value in [float('nan'), float('inf'), 2 ** 53, 0.12345678912345678]:
            with self.assertRaises(ContractError):
                canonical_json_bytes(value)

    def test_utf16_key_order(self):
        self.assertEqual(canonical_json_bytes({'\ue000': 2, '\U00010000': 1}),
                         '{"\U00010000":1,"\ue000":2}'.encode('utf-8'))

    def test_lone_surrogates_rejected_in_keys_and_values(self):
        for value in ['\ud800', {'\udfff': 1}, {'ok': '\ud800'}]:
            with self.assertRaises(ContractError):
                canonical_json_bytes(value)
