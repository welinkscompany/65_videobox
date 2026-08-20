from __future__ import annotations

from dataclasses import dataclass, field
import re

from videobox_domain_models.caption_fonts import default_caption_font_family


_RGBA = re.compile(r"^#[0-9A-Fa-f]{8}$")


@dataclass(frozen=True, slots=True)
class CaptionStyle:
    # 기본값은 **이 기계에 실제로 있는** 글꼴이어야 한다. 예전 기본값 `Arial`은
    # 컨테이너에 없어서, 모양을 따로 고르지 않은 자막이 전부 조용히 다른
    # 글꼴로 떨어지고 있었다.
    #
    # 그래서 이름을 여기 박지 않고 **물어서** 받는다. 박아 두면 목록·이미지가
    # 바뀔 때 이 줄만 남아 다시 어긋난다 -- 실제로 API가 내주는 기본값만 기계를
    # 보고 이 줄은 박힌 이름이던 시기가 있었고, 그동안 `CaptionStyle()`을 직접
    # 만드는 자리(자막 모양을 한 번도 안 고친 편집본의 렌더가 그 자리다)는
    # 없는 이름을 그대로 ASS `Fontname`에 적을 수 있었다.
    #
    # 답은 `lru_cache`에 남아 렌더마다 디스크를 다시 읽지 않는다. 고른 이름이
    # 들어오면 이 함수는 아예 불리지 않는다 -- 남이 고른 것은 고쳐 주지 않는다.
    font_family: str = field(default_factory=default_caption_font_family)
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
        # `field`는 위에서 `dataclasses.field`로 들여온 이름이다. 여기서 같은
        # 이름을 다시 쓰면 읽는 사람이 헷갈린다.
        allowed = {spec.name for spec in cls.__dataclass_fields__.values()}
        unknown = sorted(str(key) for key in values if key not in allowed)
        if unknown:
            raise ValueError(f"Unsupported caption style fields: {', '.join(unknown)}")
        return cls(**values)

    def to_dict(self) -> dict[str, object]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}

    def rgba_floats(self, value: str) -> tuple[float, float, float, float]:
        return tuple(int(value[index : index + 2], 16) / 255 for index in range(1, 9, 2))  # type: ignore[return-value]
