"""Repair the approved QEdge Agent guidance and retain the prior values."""

import json
from datetime import datetime, timezone
from pathlib import Path

from onyx.db.agent_configuration import repair_stored_agent_instructions


def main() -> None:
    backup = Path(
        "/app/qedge-agent-instructions-"
        + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        + ".json"
    )
    ids = repair_stored_agent_instructions(backup)
    print(json.dumps({"backup": str(backup), "updated_agent_ids": ids}))


if __name__ == "__main__":
    main()
