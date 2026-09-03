# Gate 2 Calibration Revision Log

## Superseded attempt

- Protocol SHA-256: `58db05c47c1d981b12b491f07030c9e9593b902ec14f91f2ee284db1e633c14c`
- Seed rule: each compared STEP used its own file SHA-256.
- Preserved protocol: `superseded/gate2_validation_protocol_independent_seed.json`
- Preserved hash: `superseded/gate2_validation_protocol_independent_seed.json.sha256`
- Preserved STEP artifacts: `superseded/roundtrip/` and `superseded/controlled_perturbation/`

This attempt was superseded before the formal Gate 2 run. A RED determinism test showed that independent CadQuery exports of the same candidate geometry contain different STEP bytes. Because Gate 1 sampling derived each random seed from its own file SHA-256, identical candidate geometry received different point samples and could change final candidate order between runs. This was a reproducibility defect, not a case-specific threshold failure.

## Active protocol

- Protocol SHA-256: `8656e3882ee8c71c310b3ad5afe85177cf8e1d2e67d1bff6d03e13d64148c05a`
- Seed rule: both files in a comparison use the first eight bytes of the frozen reference STEP SHA-256.
- Active protocol: `config/gate2_validation_protocol.json`
- Active hash: `config/gate2_validation_protocol.json.sha256`

The shared reference seed makes repeated candidate exports numerically repeatable while leaving Gate 1's default file-SHA sampling behavior unchanged. The full 10-case round-trip and four-case controlled-perturbation calibration was rerun; thresholds were derived anew rather than copied or adjusted from the superseded values.
