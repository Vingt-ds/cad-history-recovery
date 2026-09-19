# Gate 6 modifier selection review

Baseline: `c3e448525e9424383e847332f4d0afc1444e7380`. This is oracle operationalization, not inference or benchmark construction.

Fixed prismatic Join J and Cut C give `(B union J) minus C` versus `(B minus C) union J`. Their volume difference is analytically `Vol(J intersection C)` (regularized solids, ignoring boundary membership). Disjoint J/C predict identical occupied sets; overlapping J/C predict distinguishable results. Every operation remains effective and both Joins have positive-volume attachment. Two fixed Cuts instead commute as set subtraction and cannot alone provide the required order-sensitive candidate.

The chosen OS Cut lies inside J. JC leaves a 160 mm3 cavity; CJ refills the removed material. DE uses an internal cavity separated from J by sqrt(328) mm. Shell expectations provide an independent topological check, while face and edge split counts remain observed evidence rather than prescribed outcomes.

Tools are independently built and verified, not defined by state-dependent extrude scopes. Absolute prismatic volumes exclude through-all extents and face references. The existing Gate 0-4 executor/schema cannot be silently extended: qualification implementation lives in new Gate 6 modules and a separate Fusion script.

The base is not symmetry-free. Unequal dimensions remove axis permutations; J placement breaks each of the remaining seven nonidentity axis reflections. No registration is allowed.

Approval permits contract, executor/comparator and synthetic qualification development. Formal 12-run replay needs separate authorization after frozen implementation and preflight. DE remains a candidate until full observable equivalence passes. No healing or face merging may be used to force that result.
