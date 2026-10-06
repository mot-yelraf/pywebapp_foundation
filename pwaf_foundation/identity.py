"""Read app-owned native branding without importing application services.

Identity metadata is packaged with the application and remains independent of
editable runtime preferences and the foundation's reusable package name.
"""

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DesktopIdentity:
    """Stable installation ID, display name, and optional packaged icon directory."""

    id: str
    name: str = "Python Web App"
    icon_dir: Path = Path(__file__).parent / "static/icons"
    icon_stem: str = "pwaf-desktop-icon"

    def __post_init__(self) -> None:
        if (not isinstance(self.id, str)
                or not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,127}", self.id)):
            raise ValueError("Invalid application id")
        if (not isinstance(self.name, str) or not self.name.strip() or len(self.name) > 100
                or any(ord(c) < 32 or ord(c) == 127 or c in '/\\:*?"<>|' for c in self.name)
                or self.name in {".", ".."} or self.name.endswith((".", " "))):
            raise ValueError("Invalid native application name")
        reserved = {"CON", "PRN", "AUX", "NUL"} | {
            f"{prefix}{number}" for prefix in ("COM", "LPT") for number in range(1, 10)
        }
        if self.name.split(".", 1)[0].upper() in reserved:
            raise ValueError("Invalid native application name")
        if (not isinstance(self.icon_stem, str)
                or not re.fullmatch(r"[a-zA-Z0-9_-]+", self.icon_stem)):
            raise ValueError("Invalid desktop icon stem")

    @property
    def native_id(self) -> str:
        """Return a cross-platform namespace valid for desktop entry filenames."""
        return "org.pwaf.app_" + hashlib.sha256(self.id.encode()).hexdigest()[:32]

    def icon(self, extension: str) -> Path:
        """Resolve one platform's icon in the packaged artwork directory."""
        return self.icon_dir / f"{self.icon_stem}.{extension}"

    @classmethod
    def load(cls, path: Path) -> "DesktopIdentity":
        """Load metadata; resolve optional icon_dir relative to the identity file."""
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            options = {}
            if "icon_dir" in value:
                relative = Path(value["icon_dir"])
                if relative.is_absolute() or ".." in relative.parts:
                    raise ValueError("icon_dir must be inside the application package")
                options["icon_dir"] = path.parent / relative
            return cls(value["id"], value.get("name", "Python Web App"),
                       icon_stem=value.get("icon_stem", "pwaf-desktop-icon"), **options)
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
            raise ValueError(
                "Source requires app/identity.json with valid native identity"
            ) from exc
