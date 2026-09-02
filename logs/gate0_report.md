# Gate 0 Verification Report

Overall automated status: **PASS** (22/22 checks passed)

> Timeline screenshots require separate visual review; file presence alone is not visual approval.

| Status | Check | Detail |
| --- | --- | --- |
| PASS | `shared_config` | valid; SHA-256=c045652c5c06a6a5042f36edd44228cfb0b54c7ba3ff4adf86247a8360150a4f |
| PASS | `artifact:models/manual_box_hole.f3d` | 60349 bytes |
| PASS | `artifact:models/manual_box_hole.step` | 10571 bytes |
| PASS | `artifact:models/manual_box_hole_reimported.f3d` | 40549 bytes |
| PASS | `artifact:models/fusion_script_box_run01.step` | 9076 bytes |
| PASS | `artifact:models/fusion_script_box_run02.step` | 9076 bytes |
| PASS | `artifact:models/cadquery_box.step` | 15402 bytes |
| PASS | `artifact:evidence/01_original_timeline.png` | 790513 bytes |
| PASS | `artifact:evidence/02_reimported_timeline.png` | 765202 bytes |
| PASS | `artifact:evidence/export_settings.md` | 1207 bytes |
| PASS | `artifact:docs/gate0_reuse_audit.md` | 2264 bytes |
| PASS | `artifact:environment/environment.yml` | 281 bytes |
| PASS | `artifact:environment/pip-freeze.txt` | 4998 bytes |
| PASS | `artifact:logs/fusion_run01.json` | 461 bytes |
| PASS | `artifact:logs/fusion_run02.json` | 461 bytes |
| PASS | `artifact:logs/external_python.json` | 1354 bytes |
| PASS | `manual_evidence_record` | manual export record and both visual reviews marked PASS |
| PASS | `environment_record` | Conda history and pip records present; OCP version is verified by external smoke log |
| PASS | `fusion_run01` | status=success, bodies=1, faces=6 |
| PASS | `fusion_run02` | status=success, bodies=1, faces=6 |
| PASS | `external_python` | all four STEP checks passed |
| PASS | `shared_json_hash` | config=c045652c5c06a6a5042f36edd44228cfb0b54c7ba3ff4adf86247a8360150a4f; recorded=['c045652c5c06a6a5042f36edd44228cfb0b54c7ba3ff4adf86247a8360150a4f', 'c045652c5c06a6a5042f36edd44228cfb0b54c7ba3ff4adf86247a8360150a4f', 'c045652c5c06a6a5042f36edd44228cfb0b54c7ba3ff4adf86247a8360150a4f'] |
