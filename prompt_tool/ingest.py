from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .models import PromptBundle


def load_prompt_bundle(path: str | Path) -> PromptBundle:
    input_path = Path(path)
    data = json.loads(input_path.read_text())
    return PromptBundle.model_validate(data)


def dump_json(path: str | Path, payload: Any) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n")


def dump_text(path: str | Path, payload: str) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(payload.rstrip() + "\n")


def prompt_fingerprint(bundle: PromptBundle) -> str:
    digest = hashlib.sha256()
    digest.update(bundle.agent_name.encode("utf-8"))
    digest.update(bundle.model.encode("utf-8"))
    digest.update(bundle.general_prompt.encode("utf-8"))
    digest.update(str(len(bundle.general_tools)).encode("utf-8"))
    return digest.hexdigest()[:16]
