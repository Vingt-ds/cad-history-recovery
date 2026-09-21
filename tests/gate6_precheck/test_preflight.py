import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from tools.gate6_precheck.contract import CONFIG_PATH, CONTRACT_PATH, ContractError, load_contract
from tools.gate6_precheck.evidence import EvidencePackage
from tools.gate6_precheck import preflight


PROJECT_ROOT = Path(__file__).resolve().parents[2]
IMPLEMENTATION_COMMIT = "a" * 40


def make_bound_repo(folder):
    root = Path(folder) / "repo"
    for relative in (
        CONFIG_PATH,
        CONTRACT_PATH,
        preflight.PROBE_SCRIPT_PATH,
        preflight.PROBE_MANIFEST_PATH,
    ):
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PROJECT_ROOT / relative, destination)
    return root


def clean_git(root, args):
    command = tuple(args)
    if command == ("rev-parse", "HEAD"):
        return IMPLEMENTATION_COMMIT
    if command == ("status", "--porcelain=v1"):
        return ""
    if command == (
        "merge-base", "--is-ancestor", preflight.SPECIFICATION_COMMIT, IMPLEMENTATION_COMMIT
    ):
        return ""
    for index, relative in enumerate((preflight.PROBE_SCRIPT_PATH, preflight.PROBE_MANIFEST_PATH), 1):
        if command == ("rev-parse", f"{IMPLEMENTATION_COMMIT}:{relative}"):
            return str(index) * 40
        if command == ("hash-object", f"--path={relative}", relative):
            return str(index) * 40
    raise AssertionError(command)


def valid_response(root, challenge_record):
    challenge = challenge_record["challenge"]
    response = {
        "schema_version": preflight.RESPONSE_SCHEMA_VERSION,
        "challenge_sha256": challenge_record["challenge_sha256"],
        "challenge_id": challenge["challenge_id"],
        "challenge_nonce": challenge["challenge_nonce"],
        "specification_commit": challenge["specification_commit"],
        "implementation_commit": challenge["implementation_commit"],
        "contract_version": challenge["contract_version"],
        "live_environment": {
            "fusion": "2704.1.53",
            "fusion_python": "3.14.0",
            "os": "Windows-10-10.0.22621-SP0",
            "pid": 1234,
            "process_start_utc": "2026-09-20T00:00:00Z",
        },
        "probe": {
            "script_sha256": hashlib.sha256(
                (root / preflight.PROBE_SCRIPT_PATH).read_bytes()
            ).hexdigest(),
            "manifest_sha256": hashlib.sha256(
                (root / preflight.PROBE_MANIFEST_PATH).read_bytes()
            ).hexdigest(),
            "fusion_scripts": [],
        },
        "campaign": {
            "status": "NOT_STARTED",
            "oracle_run_count": 0,
            "formal_replay_performed": False,
            "authorized": False,
        },
    }
    return response


def write_response(path, response):
    payload = json.dumps(response, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8") + b"\n"
    Path(path).write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def qualifications():
    return [
        {
            "name": "gate6",
            "command": preflight.REQUIRED_QUALIFICATION_COMMANDS["gate6"],
            "exit_code": 0,
            "output_sha256": "3" * 64,
        },
        {
            "name": "full_repo",
            "command": preflight.REQUIRED_QUALIFICATION_COMMANDS["full_repo"],
            "exit_code": 0,
            "output_sha256": "4" * 64,
        },
    ]


class ChallengeTests(unittest.TestCase):
    def test_full_repo_qualification_uses_discovery_without_nonpackage_top(self):
        self.assertEqual(
            preflight.REQUIRED_QUALIFICATION_COMMANDS["full_repo"],
            "python -m unittest discover -s tests -v",
        )

    def test_issue_requires_clean_head_full_sha_and_spec_ancestry(self):
        with tempfile.TemporaryDirectory() as folder:
            root = make_bound_repo(folder)
            destination = Path(folder) / "qualification-challenge"
            with self.assertRaises(ContractError) as caught:
                preflight.issue_challenge(root, "short", destination, _git=clean_git)
            self.assertEqual(caught.exception.code, "PF_IMPLEMENTATION_BINDING_INVALID")

            def blob_mismatch(repo, args):
                if tuple(args) == (
                    "hash-object", f"--path={preflight.PROBE_SCRIPT_PATH}",
                    preflight.PROBE_SCRIPT_PATH,
                ):
                    return "f" * 40
                return clean_git(repo, args)

            with self.assertRaises(ContractError) as caught:
                preflight.issue_challenge(root, IMPLEMENTATION_COMMIT, destination, _git=blob_mismatch)
            self.assertEqual(caught.exception.code, "PF_IMPLEMENTATION_BINDING_INVALID")

            def dirty_git(repo, args):
                if tuple(args) == ("status", "--porcelain=v1"):
                    return "?? unexpected.txt"
                return clean_git(repo, args)

            with self.assertRaises(ContractError) as caught:
                preflight.issue_challenge(root, IMPLEMENTATION_COMMIT, destination, _git=dirty_git)
            self.assertEqual(caught.exception.code, "PF_WORKTREE_DIRTY")

            def wrong_head(repo, args):
                if tuple(args) == ("rev-parse", "HEAD"):
                    return "b" * 40
                return clean_git(repo, args)

            with self.assertRaises(ContractError) as caught:
                preflight.issue_challenge(root, IMPLEMENTATION_COMMIT, destination, _git=wrong_head)
            self.assertEqual(caught.exception.code, "PF_IMPLEMENTATION_BINDING_INVALID")

    def test_issue_rejects_formal_destination_request_and_existing_root(self):
        with tempfile.TemporaryDirectory() as folder:
            root = make_bound_repo(folder)
            formal_destination = Path(folder) / "runs" / "gate6" / "precheck" / "challenge"
            with self.assertRaises(ContractError) as caught:
                preflight.issue_challenge(root, IMPLEMENTATION_COMMIT, formal_destination, _git=clean_git)
            self.assertEqual(caught.exception.code, "PF_UNSAFE_PATH")

            request = root / "gate6_formal_execution_request.json"
            request.write_text('{"formal_campaign_requested":true}', encoding="utf-8")
            with self.assertRaises(ContractError) as caught:
                preflight.issue_challenge(root, IMPLEMENTATION_COMMIT, Path(folder) / "q1", _git=clean_git)
            self.assertEqual(caught.exception.code, "PF_FORMAL_REQUEST_PRESENT")
            request.unlink()

            formal_root = root / "runs" / "gate6" / "precheck"
            formal_root.mkdir(parents=True)
            with self.assertRaises(ContractError) as caught:
                preflight.issue_challenge(root, IMPLEMENTATION_COMMIT, Path(folder) / "q2", _git=clean_git)
            self.assertEqual(caught.exception.code, "PF_FORMAL_ROOT_PRESENT")

    def test_issue_writes_exact_non_authorizing_challenge_and_seal(self):
        with tempfile.TemporaryDirectory() as folder:
            root = make_bound_repo(folder)
            destination = Path(folder) / "qualification-challenge"
            result = preflight.issue_challenge(root, IMPLEMENTATION_COMMIT, destination, _git=clean_git)
            self.assertEqual(result["challenge"]["implementation_commit"], IMPLEMENTATION_COMMIT)
            self.assertEqual(result["challenge"]["execution_authorization"], "not_granted")
            self.assertFalse(result["challenge"]["formal_campaign_requested"])
            self.assertEqual(result["challenge"]["oracle_run_count"], 0)
            self.assertTrue(EvidencePackage.verify_existing(destination, result["seal_sha256"]))
            with self.assertRaises(FileExistsError):
                preflight.issue_challenge(root, IMPLEMENTATION_COMMIT, destination, _git=clean_git)


class EvaluationTests(unittest.TestCase):
    def issue(self, folder):
        root = make_bound_repo(folder)
        record = preflight.issue_challenge(
            root, IMPLEMENTATION_COMMIT, Path(folder) / "qualification-challenge", _git=clean_git
        )
        return root, record

    @staticmethod
    def runner(argv, cwd):
        name = "gate6" if "tests/gate6_precheck" in argv else "full_repo"
        count = 91 if name == "gate6" else 384
        return subprocess.CompletedProcess(
            argv, 0, stdout="", stderr=f"Ran {count} tests in 1.000s\n\nOK\n"
        )

    @staticmethod
    def environment():
        return {
            "external_python": "3.11.16",
            "cadquery": "2.8.0",
            "ocp": "7.9.3.1",
            "numpy": "2.4.6",
            "scipy": "1.17.1",
            "os": "Windows-10-10.0.22621-SP0",
        }

    def evaluate(self, root, record, response_path, response_sha256, output, git=clean_git,
                 runner=None, environment=None):
        return preflight.evaluate_preflight(
            repo_root=root,
            challenge_path=record["challenge_path"],
            challenge_sha256=record["challenge_sha256"],
            challenge_seal_sha256=record["seal_sha256"],
            response_path=response_path,
            response_sha256=response_sha256,
            destination=output,
            _git=git,
            _runner=runner or self.runner,
            _env_collector=environment or self.environment,
        )

    def test_missing_fusion_response_is_honest_not_ready(self):
        with tempfile.TemporaryDirectory() as folder:
            root, record = self.issue(folder)
            result = self.evaluate(
                root, record, Path(folder) / "missing-response.json", None,
                Path(folder) / "preflight-evaluation",
            )
            self.assertEqual(result["report"]["outcome"], "NOT_READY_FOR_REVIEW")
            self.assertIn("PF_FUSION_PROBE_INVALID", [item["code"] for item in result["report"]["failures"]])
            self.assertFalse(result["report"]["campaign"]["authorized"])
            self.assertEqual(result["report"]["campaign"]["oracle_run_count"], 0)
            self.assertFalse(result["report"]["campaign"]["formal_replay_performed"])

    def test_environment_mismatch_cannot_be_ready(self):
        with tempfile.TemporaryDirectory() as folder:
            root, record = self.issue(folder)
            response = valid_response(root, record)
            response["live_environment"]["fusion"] = "wrong"
            response_path = Path(folder) / "fusion-response.json"
            response_hash = write_response(response_path, response)
            result = self.evaluate(
                root, record, response_path, response_hash, Path(folder) / "preflight-evaluation"
            )
            self.assertEqual(result["report"]["outcome"], "NOT_READY_FOR_REVIEW")
            self.assertIn("PF_ENVIRONMENT_MISMATCH", [item["code"] for item in result["report"]["failures"]])

    def test_complete_evidence_is_ready_for_review_but_not_authorized(self):
        with tempfile.TemporaryDirectory() as folder:
            root, record = self.issue(folder)
            response = valid_response(root, record)
            response_path = Path(folder) / "fusion-response.json"
            response_hash = write_response(response_path, response)
            output = Path(folder) / "preflight-evaluation"
            result = self.evaluate(root, record, response_path, response_hash, output)
            report = result["report"]
            self.assertEqual(report["outcome"], "READY_FOR_REVIEW_NOT_AUTHORIZED")
            self.assertEqual(report["failures"], [])
            self.assertEqual(report["campaign"]["status"], "NOT_STARTED")
            self.assertFalse(report["campaign"]["authorized"])
            self.assertRegex(report["captured_at_utc"], r"Z$")
            self.assertEqual(report["state_snapshot"]["head"], IMPLEMENTATION_COMMIT)
            self.assertTrue(report["state_snapshot"]["worktree_clean"])
            self.assertTrue(EvidencePackage.verify_existing(output, result["seal_sha256"]))
            self.assertTrue((output / "preflight_report.md").is_file())
            self.assertEqual(
                {path.relative_to(output).as_posix() for path in output.rglob("*") if path.is_file()},
                {
                    "inputs/preflight_challenge.json",
                    "inputs/fusion_environment_response.json",
                    "inputs/external_environment.json",
                    "inputs/qualification_results.json",
                    "inputs/gate6.stdout.txt",
                    "inputs/gate6.stderr.txt",
                    "inputs/full_repo.stdout.txt",
                    "inputs/full_repo.stderr.txt",
                    "preflight_report.json",
                    "preflight_report.md",
                    "SHA256SUMS",
                },
            )

    def test_dirty_worktree_after_evaluation_blocks_ready(self):
        with tempfile.TemporaryDirectory() as folder:
            root, record = self.issue(folder)
            response_path = Path(folder) / "fusion-response.json"
            response_hash = write_response(response_path, valid_response(root, record))
            statuses = iter(("", "?? changed.txt"))

            def becomes_dirty(repo, args):
                if tuple(args) == ("status", "--porcelain=v1"):
                    return next(statuses)
                return clean_git(repo, args)

            result = self.evaluate(
                root, record, response_path, response_hash,
                Path(folder) / "preflight-evaluation", git=becomes_dirty,
            )
            self.assertEqual(result["report"]["outcome"], "NOT_READY_FOR_REVIEW")
            self.assertIn("PF_WORKTREE_DIRTY", [item["code"] for item in result["report"]["failures"]])

    def test_naked_unbound_inputs_are_rejected_by_the_api(self):
        with tempfile.TemporaryDirectory() as folder:
            root, record = self.issue(folder)
            response_path = Path(folder) / "fusion-response.json"
            response_hash = write_response(response_path, valid_response(root, record))
            with self.assertRaises(TypeError):
                preflight.evaluate_preflight(
                    root, record["challenge_path"], record["challenge_sha256"],
                    record["seal_sha256"], response_path, response_hash,
                    Path(folder) / "evaluation",
                    external_environment={"external_python": "3.11.16"},
                    qualification_results=qualifications(), _git=clean_git,
                )

    def test_challenge_seal_mismatch_blocks_evaluation(self):
        with tempfile.TemporaryDirectory() as folder:
            root, record = self.issue(folder)
            response_path = Path(folder) / "fusion-response.json"
            response_hash = write_response(response_path, valid_response(root, record))
            record["seal_sha256"] = "0" * 64
            with self.assertRaises(ContractError) as caught:
                self.evaluate(root, record, response_path, response_hash, Path(folder) / "evaluation")
            self.assertEqual(caught.exception.code, "PF_CHALLENGE_INVALID")

    def test_internal_runner_must_return_completed_process_with_real_unittest_summary(self):
        with tempfile.TemporaryDirectory() as folder:
            root, record = self.issue(folder)
            response_path = Path(folder) / "fusion-response.json"
            response_hash = write_response(response_path, valid_response(root, record))
            for runner in (
                lambda argv, cwd: {"returncode": 0, "stdout": "Ran 1 test\nOK"},
                lambda argv, cwd: subprocess.CompletedProcess(argv, 0, "", "OK\n"),
            ):
                with self.subTest(runner=runner):
                    result = self.evaluate(
                        root, record, response_path, response_hash,
                        Path(folder) / ("evaluation-" + str(id(runner))), runner=runner,
                    )
                    self.assertEqual(result["report"]["outcome"], "NOT_READY_FOR_REVIEW")
                    self.assertIn("PF_QUALIFICATION_INVALID", {
                        failure["code"] for failure in result["report"]["failures"]
                    })

    def test_probe_hash_and_process_start_are_strictly_validated(self):
        for mutation in (
            lambda response: response["probe"].update(script_sha256="1" * 64),
            lambda response: response["live_environment"].update(
                process_start_utc="2026-09-20T00:00:00+00:00"
            ),
        ):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as folder:
                root, record = self.issue(folder)
                response = valid_response(root, record)
                mutation(response)
                response_path = Path(folder) / "fusion-response.json"
                response_hash = write_response(response_path, response)
                result = self.evaluate(
                    root, record, response_path, response_hash,
                    Path(folder) / "evaluation",
                )
                self.assertEqual(result["report"]["outcome"], "NOT_READY_FOR_REVIEW")
                self.assertIn("PF_FUSION_PROBE_INVALID", {
                    failure["code"] for failure in result["report"]["failures"]
                })

    def test_post_challenge_state_change_blocks_seal_readiness(self):
        for kind in ("root", "request", "authorization"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as folder:
                root, record = self.issue(folder)
                response_path = Path(folder) / "fusion-response.json"
                response_hash = write_response(response_path, valid_response(root, record))
                status_calls = 0

                def changes_after_start(repo, args):
                    nonlocal status_calls
                    if tuple(args) == ("status", "--porcelain=v1"):
                        status_calls += 1
                        if status_calls == 1:
                            if kind == "root":
                                (root / "runs/gate6/precheck").mkdir(parents=True)
                            else:
                                if kind == "request":
                                    (root / "gate6_formal_execution_request.json").write_text(
                                        '{"formal_campaign_requested":true}', encoding="utf-8"
                                    )
                                else:
                                    config_path = root / CONFIG_PATH
                                    config = json.loads(config_path.read_text(encoding="utf-8"))
                                    config["execution_authorization"] = "granted"
                                    config_path.write_text(json.dumps(config), encoding="utf-8")
                        return ""
                    return clean_git(repo, args)

                result = self.evaluate(
                    root, record, response_path, response_hash,
                    Path(folder) / "evaluation", git=changes_after_start,
                )
                expected = {
                    "root": "PF_FORMAL_ROOT_PRESENT",
                    "request": "PF_FORMAL_REQUEST_PRESENT",
                    "authorization": "PF_AUTHORIZATION_STATE_INVALID",
                }[kind]
                self.assertIn(expected, {failure["code"] for failure in result["report"]["failures"]})

    def test_authorization_change_before_evaluation_is_reported_fail_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            root, record = self.issue(folder)
            response_path = Path(folder) / "fusion-response.json"
            response_hash = write_response(response_path, valid_response(root, record))
            config_path = root / CONFIG_PATH
            config = json.loads(config_path.read_text(encoding="utf-8"))
            config["execution_authorization"] = "granted"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            result = self.evaluate(
                root, record, response_path, response_hash, Path(folder) / "evaluation"
            )
            self.assertEqual(result["report"]["outcome"], "NOT_READY_FOR_REVIEW")
            self.assertIn("PF_AUTHORIZATION_STATE_INVALID", {
                failure["code"] for failure in result["report"]["failures"]
            })

    def test_state_change_after_seal_never_returns_ready(self):
        with tempfile.TemporaryDirectory() as folder:
            root, record = self.issue(folder)
            response_path = Path(folder) / "fusion-response.json"
            response_hash = write_response(response_path, valid_response(root, record))
            status_calls = 0

            def changes_after_seal(repo, args):
                nonlocal status_calls
                if tuple(args) == ("status", "--porcelain=v1"):
                    status_calls += 1
                    return "?? changed-after-seal.txt" if status_calls == 3 else ""
                return clean_git(repo, args)

            with self.assertRaises(ContractError) as caught:
                self.evaluate(
                    root, record, response_path, response_hash,
                    Path(folder) / "evaluation", git=changes_after_seal,
                )
            self.assertEqual(caught.exception.code, "PF_STATE_CHANGED_DURING_SEAL")


if __name__ == "__main__":
    unittest.main()
