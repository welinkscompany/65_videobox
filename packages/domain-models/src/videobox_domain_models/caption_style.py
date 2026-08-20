from __future__ import annotations

from dataclasses import dataclass
import re

from videobox_domain_models.caption_fonts import DEFAULT_CAPTION_FONT_FAMILY


_RGBA = re.compile(r"^#[0-9A-Fa-f]{8}$")


@dataclass(frozen=True, slots=True)
class CaptionStyle:
    # 기본값은 **실제로 설치돼 있는** 글꼴이어야 한다. 예전 기본값 `Arial`은
    # 컨테이너에 없어서, 모양을 따로 고르지 않은 자막이 전부 조용히 다른
    # 글꼴로 떨어지고 있었다.
    font_family: str = DEFAULT_CAPTION_FONT_FAMILY
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
        if not isinstance(raw, dict):
            raise ValueError("Caption style must be an object.")
        values = raw
        allowed = {field.name for field in cls.__dataclass_fields__.values()}
        unknown = sorted(str(key) for key in values if key not in allowed)
        if unknown:
            raise ValueError(f"Unsupported caption style fields: {', '.join(unknown)}")
        return cls(**values)

    def to_dict(self) -> dict[str, object]:
        return {field: getattr(self, field) for field in self.__dataclass_fields__}

    def rgba_floats(self, value: str) -> tuple[float, float, float, float]:
        return tuple(int(value[index : index + 2], 16) / 255 for index in range(1, 9, 2))  # type: ignore[return-value]
