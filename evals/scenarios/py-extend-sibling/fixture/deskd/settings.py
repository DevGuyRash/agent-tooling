"""deskd.conf: the desk's own settings, in the config directory beside the support calendar files."""
from dataclasses import dataclass, field
from pathlib import Path


class SettingsError(Exception):
    pass


@dataclass
class Settings:
    team: str = "Support"
    priority_labels: dict[str, str] = field(default_factory=dict)

    def label(self, priority: str) -> str:
        return self.priority_labels.get(priority, priority or "-")


def load(config_dir: str | Path) -> Settings:
    """Read DIR/deskd.conf: "team NAME..." and "priority CODE LABEL..." lines, # comments."""
    path = Path(config_dir) / "deskd.conf"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SettingsError(f"cannot read {path}: {exc.strerror}") from None
    settings = Settings()
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        key, _, rest = line.partition(" ")
        rest = rest.strip()
        if key == "team" and rest:
            settings.team = rest
        elif key == "priority" and len(rest.split(None, 1)) == 2:
            code, label = rest.split(None, 1)
            settings.priority_labels[code] = label
        else:
            raise SettingsError(f"{path} line {number}: expected 'team NAME' or 'priority CODE LABEL'")
    return settings
