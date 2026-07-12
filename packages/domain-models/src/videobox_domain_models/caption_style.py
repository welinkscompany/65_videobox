from __future__ import annotations

from dataclasses import dataclass
import re


_RGBA = re.compile(r"^#[0-9A-Fa-f]{8}$")


@dataclass(frozen=True, slots=True)
class CaptionStyle:
    font_family: str = "Arial"
    font_size_px: int = 54
    text_color: str = "#FFFFFFFF"
    outline_color: str = "#000000FF"
    outline_width_px: int = 3
    background_color: str = "#00000000"
    position_x_percent: int = 50
    position_y_percent: int = 88
    horizontal_align: str = "center"
    safe_area_enabled: bool = True
    shadow_blur_px: int = 0

    def __post_init__(self) -> None:
        for field_name in ("text_color", "outline_color", "background_color"):
            if not _RGBA.fullmatch(str(getattr(self, field_name))):
                raise ValueError(f"{field_name} must use #RRGGBBAA.")
        if not 12 <= self.font_size_px <= 160:
            raise ValueError("font_size_px must be between 12 and 160.")
        if not 0 <= self.outline_width_px <= 12:
            raise ValueError("outline_width_px must be between 0 and 12.")
        if self.horizontal_align not in {"left", "center", "right"}:
            raise ValueError("horizontal_align must be left, center, or right.")
        if not 0 <= self.position_x_percent <= 100:
            raise ValueError("position_x_percent must be between 0 and 100.")
        if not 0 <= self.position_y_percent <= 100:
            raise ValueError("position_y_percent must be between 0 and 100.")
        if self.safe_area_enabled and self.position_y_percent > 94:
            object.__setattr__(self, "position_y_percent", 94)

    @classmethod
    def from_dict(cls, raw: object) -> "CaptionStyle":
        values = raw if isinstance(raw, dict) else {}
        allowed = {field.name for field in cls.__dataclass_fields__.values()}
        return cls(**{key: value for key, value in values.items() if key in allowed})

    def to_dict(self) -> dict[str, object]:
        return {field: getattr(self, field) for field in self.__dataclass_fields__}

    def rgba_floats(self, value: str) -> tuple[float, float, float, float]:
        return tuple(int(value[index : index + 2], 16) / 255 for index in range(1, 9, 2))  # type: ignore[return-value]
