# Third-party Sources and Reuse Boundary

No third-party source code is copied into the current implementation.

| Source | Authority and artifact | Licence decision | Retained idea | MVP decision |
| --- | --- | --- | --- | --- |
| Autodesk Fusion 360 Gallery Dataset | Autodesk Research dataset, reconstruction, Gym, and Search tooling | Dataset-oriented licence does not automatically clear every tool file; no code copied | Field mapping, uniform responses, logging, timeout, fresh-document handling | Architecture only; no Search, Agent, Beam Search, SMT, HTTP server, or neural guidance |
| Analysis Situs | Official documentation and C++ recognition system | Check exact licence before any reuse; no code needed | Attributed adjacency, shared-edge properties, concavity, explicit rejection | Rule-design reference; no C++ integration |
| DeepCAD | Paper and public research materials | Verify repository-specific terms before reuse | Minimal Sketch/Extrude vocabulary and evaluation ideas | Representation reference; no training or inference |
| CADParser | IJCAI paper and first-author repository, distinct from third-party reproductions | Record licence for the exact checkout before reuse | B-rep graph features, command categories, evaluation framing | Paper-level reference; learning method prohibited |
| Brep2Seq and CADOps-Net | Papers and public project materials where available | Verify exact repository terms before reuse | Failure modes, labels, benchmark reporting | Conceptual comparison; neural components excluded |
| CadQuery / OpenCascade | Installed CAD-kernel infrastructure | Upstream package terms apply | STEP I/O, B-rep traversal, validity, deterministic generation | Direct API dependency |
| Autodesk Fusion API | Installed Fusion Python API | Installed product/account terms apply | Native replay, F3D/STEP export, runtime logs | Required delivery backend |

Borrowed ideas must be cited. Any future code copy requires an exact URL, commit, licence check, attribution entry, and scope decision before copying.
