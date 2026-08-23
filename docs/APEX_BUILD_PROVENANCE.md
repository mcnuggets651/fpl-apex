# Apex V2 Build Provenance

A qualified runtime must record source SHA, dependency-lock digest, runtime content digest, builder identity, build timestamp supplied by the control plane, SBOM reference and provenance statement reference.

Runtime identity is a digest. Tags and branch names are labels only.

Slice 1 introduces the proof/provenance contracts and deterministic dependency surface. CI qualification and production must converge on the same immutable runtime digest before V2 cutover.
