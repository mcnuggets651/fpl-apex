# Generated Apex outputs

This directory is a runtime workspace, not the live Apex database.

Production runs may create recommendation, answer-context, projection, parity, calibration and decision-bundle files here while executing. Those files must not be committed as the current recommendation.

The authoritative runtime lineage is:

qualified source/runtime identity -> sealed runtime packet -> immutable ArtifactStore objects -> ReleaseRegistry record/current pointer.

During Slice 0, `Apex Unified` uploads a sealed Actions artifact as a **transitional** runtime carrier. That artifact is not yet the final durable V2 store.

If no certified/current runtime release exists, Apex must abstain. A stale file from Git history is never a valid substitute.
