from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
USES = re.compile(r"^\s*-?\s*uses:\s*([^\s#]+)", re.MULTILINE)


def test_every_external_action_in_active_workflows_is_immutable() -> None:
    failures: list[str] = []
    for path in sorted((ROOT / ".github/workflows").glob("*.yml")):
        text = path.read_text(encoding="utf-8")
        for reference in USES.findall(text):
            if reference.startswith("./") or reference.startswith("docker://"):
                continue
            if "@" not in reference:
                failures.append(f"{path.name}: action has no ref: {reference}")
                continue
            action, ref = reference.rsplit("@", 1)
            if not FULL_SHA.fullmatch(ref):
                failures.append(f"{path.name}: mutable action ref: {action}@{ref}")
    assert failures == []
