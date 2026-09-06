# Gate 5 Local Delivery Package

## Authority model

The private GitHub repository is authoritative for code, auditable documentation, frozen protocols, and formal evidence. The local delivery package is a presentation carrier for Dr. Li; it is not a second source of code or experimental truth.

The package is generated outside Git at:

```text
delivery_package/gate5-delivery-v1_20260924/
```

Both `delivery_package/` and `runs/` are ignored by Git.

## Fixed layout

```text
gate5-delivery-v1_20260924/
├── slides/gate5_delivery_v1.pptx
├── videos/
│   ├── demo_01_single_extrusion_v1.mp4
│   ├── demo_02_through_hole_v1.mp4
│   └── demo_03_ambiguity_v1.mp4
├── screenshots/
│   ├── demo_01_single_extrusion_v1.png
│   ├── demo_02_through_hole_v1.png
│   └── demo_03_ambiguity_v1.png
├── README_DELIVERY.md
├── submission_manifest.json
└── SHA256SUMS.txt
```

## Checkpoint A preflight

Before PPT production, create all non-PPT files and run:

```powershell
python tools/gate5_delivery.py generate `
  --project-root . `
  --package-dir delivery_package/gate5-delivery-v1_20260924 `
  --mode preflight

python tools/gate5_delivery.py verify `
  --project-root . `
  --package-dir delivery_package/gate5-delivery-v1_20260924 `
  --mode preflight
```

Preflight rejects a missing required video or screenshot, a hash/size mismatch, an extra unregistered file, a copied benchmark/result directory, an unsafe package path, or an unignored package directory. The PPT must not be present in preflight mode.

## Checkpoint B final verification

After Checkpoint A approval, create the PPT and the annotated `gate5-delivery-v1` tag at the final delivery commit. Regenerate and verify the package in final mode:

```powershell
python tools/gate5_delivery.py generate `
  --project-root . `
  --package-dir delivery_package/gate5-delivery-v1_20260924 `
  --mode final

python tools/gate5_delivery.py verify `
  --project-root . `
  --package-dir delivery_package/gate5-delivery-v1_20260924 `
  --mode final
```

Final mode requires the PPT, an annotated delivery tag, and a tag peel target equal to the manifest delivery commit.

## Non-duplication rule

The manifest records Git references and external presentation assets only. Source code, benchmark inputs, and Gate 0-4 formal result packages remain `reference_only` and must not be copied into this directory.
