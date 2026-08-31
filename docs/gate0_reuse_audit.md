# Gate 0 Reuse Audit

## Fusion 360 Gallery engineering review (45-minute cap)

Scope reviewed: reconstruction interfaces, Fusion 360 Gym execution boundary, and search-tool architecture described by the Autodesk Fusion 360 Gallery repository.

Useful design ideas retained:

- Keep JSON parsing separate from Fusion execution.
- Return a uniform success/failure record with the executed action and exception details.
- Preserve per-run logs and treat a fresh document as part of execution state.
- Bound execution time and preserve the input that caused a failure.
- Reconstruct from explicit geometry parameters rather than transient Fusion face identifiers where possible.

Explicit Gate 0 exclusions:

- Do not run the Gallery Search implementation.
- Do not introduce Agent, Beam Search, SMT, or a neural policy.
- Do not introduce the Gym HTTP server/client architecture.
- Do not copy repository code whose licensing scope has not been separately confirmed.
- Do not make Gallery tooling a dependency of the Gate 0 Fusion script.

Primary references:

- <https://github.com/AutodeskAILab/Fusion360GalleryDataset/tree/master/tools>
- <https://github.com/AutodeskAILab/Fusion360GalleryDataset/tree/master/tools/fusion360gym>
- <https://github.com/AutodeskAILab/Fusion360GalleryDataset/tree/master/tools/search>

## Analysis Situs rule-design review (30-minute cap)

Gate 0 records the following design constraints for later gates; none is implemented now:

- An attributed adjacency graph must retain shared edges and geometric/convexity attributes, not only neighbouring face IDs.
- A through-hole hypothesis needs a cylindrical face plus concave adjacency and open-boundary/cap relationships; a cylindrical face alone is insufficient.
- Recognition rules must be allowed to reject unsupported or ambiguous topology.
- Analysis Situs remains an architectural reference; its C++ system is not integrated in Gate 0.

Primary reference:

- <https://analysissitus.org/features/features_recognition-principles.html>

## Reuse decision

Gate 0 uses Autodesk Fusion's installed Python API and CadQuery/OCP as infrastructure. All shared-JSON validation, run logging, smoke checks, and verification logic in this repository are project-local minimal implementations.
