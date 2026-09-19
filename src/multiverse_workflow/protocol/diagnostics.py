from dataclasses import dataclass, field
from typing import Any, Literal

Severity = Literal["error", "warning", "info"]


@dataclass(frozen=True)
class Diagnostic:
    code: str
    file: str
    pointer: str
    message: str
    severity: Severity = "error"
    suggestion: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "code": self.code,
            "file": self.file,
            "pointer": self.pointer,
            "message": self.message,
            "severity": self.severity,
        }
        if self.suggestion is not None:
            result["suggestion"] = self.suggestion
        if self.details:
            result["details"] = self.details
        return result


class DiagnosticError(ValueError):
    def __init__(self, diagnostic: Diagnostic) -> None:
        super().__init__(diagnostic.message)
        self.diagnostic = diagnostic
