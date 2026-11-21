from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TraceCollector:
    document_type: str | None = None
    classification: dict[str, Any] = field(default_factory=dict)
    pages: list[dict[str, Any]] = field(default_factory=list)
    fields: list[dict[str, Any]] = field(default_factory=list)
    validation: dict[str, Any] = field(default_factory=dict)

    def add(
        self,
        path: str,
        value: Any,
        page: int | None,
        rule_id: str,
        method: str,
        confidence: float,
        source_span: str | None,
    ) -> None:
        self.fields.append(
            {
                "path": path,
                "value": value,
                "page": page,
                "rule_id": rule_id,
                "method": method,
                "confidence": confidence,
                "source_span": (source_span[:240] if isinstance(source_span, str) else source_span),
            }
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_type": self.document_type,
            "classification": self.classification,
            "pages": self.pages,
            "fields": self.fields,
            "validation": self.validation,
        }
