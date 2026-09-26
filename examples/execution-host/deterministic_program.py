"""A trusted deterministic program exercising HTTP Job and real artifact transfer."""

import json
import sys
from pathlib import Path

request = json.load(sys.stdin)
goal = request["input"].get("goal", "Review the supplied deliverable")
text = f"Deterministic execution host deliverable: {goal}"
Path("deliverable.txt").write_text(text, encoding="utf-8")
print(
    json.dumps(
        {
            "output": {"text": text, "artifact_refs": []},
            "artifacts": [
                {"path": "deliverable.txt", "name": "deliverable.txt", "mediaType": "text/plain"}
            ],
        }
    )
)
