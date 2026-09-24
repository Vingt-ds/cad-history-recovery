# Gate 5 Licence and Third-Party Audit

## Project licence boundary

This repository is publicly accessible for project review but does not currently grant permission to copy, modify, or distribute the project code or data. The absence of a project licence is deliberate; public access is not a software licence. Any future licensed release requires a separate ownership, data-rights, dependency-notice, and licence decision.

No third-party source code was copied into the Gate 5 delivery layer. Installed libraries and Autodesk Fusion are invoked through their public or installed APIs. The earlier architecture-only reuse review remains in `docs/third_party_and_references.md` and `docs/gate0_reuse_audit.md`.

## Direct runtime dependencies

| Component | Verified version | Use in this project | Upstream source | Licence/status |
| --- | --- | --- | --- | --- |
| CadQuery | 2.8.0 | STEP I/O, deterministic source construction, B-rep access, candidate reconstruction | <https://github.com/CadQuery/cadquery> | Apache-2.0, as reported by installed package metadata and the upstream repository |
| OCP Python bindings | 7.9.3.1 | Python access to Open CASCADE topology and geometry APIs | <https://github.com/CadQuery/OCP> | Apache-2.0 for the bindings package, as reported by installed Conda metadata |
| Open CASCADE Technology | 7.9.3 | CAD kernel supplied through the OCP dependency | <https://dev.opencascade.org/> | LGPL-2.1-only in the installed Conda package metadata; upstream additional exception/terms must be reviewed before redistribution |
| NumPy | 2.4.6 | Numeric arrays and geometry calculations used by the frozen implementation | <https://github.com/numpy/numpy> | Primarily BSD-3-Clause; the installed distribution reports additional licences for bundled components |
| SciPy | 1.17.1 | Spatial/numeric routines used by frozen geometry validation | <https://github.com/scipy/scipy> | BSD-3-Clause upstream; bundled-component notices remain governed by the installed distribution |
| Autodesk Fusion API | Fusion 2704.1.53 | Native parametric replay and F3D/STEP export | <https://help.autodesk.com/view/fusion360/ENU/?guid=GUID-C1545D80-D804-4CF3-886D-9B5C54B2D7A2> | Proprietary installed-product and Autodesk account terms; not an open-source dependency |

Versions above are the verified baseline environment values. `environment/environment.yml` is the preferred direct-environment definition.

## `pip-freeze.txt` interpretation

`environment/pip-freeze.txt` is an audit snapshot of the complete verified Python environment. It includes transitive packages, build locations, and utilities that are not direct project dependencies. Inclusion in that file does not mean that the package is directly imported, redistributed, or claimed as project code.

## Delivery-package boundary

The local Gate 5 package contains only the slide deck, three short demonstration videos, screenshots, a delivery README, a manifest, and checksums. It does not copy source code, benchmark inputs, formal result packages, dependency binaries, or third-party source. Those items remain references to the private Git repository and frozen tags.
