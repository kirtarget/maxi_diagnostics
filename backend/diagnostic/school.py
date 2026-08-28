import re
import unicodedata
import html
from io import BytesIO
from xml.etree import ElementTree
from pathlib import Path

from pydantic import (
    BaseModel, ConfigDict, Field, HttpUrl, ValidationError,
    field_validator, model_validator,
)
from reportlab.lib.utils import ImageReader
from svglib.svglib import svg2rlg
import tinycss2

from diagnostic.font_support import validate_report_text
from diagnostic.jsonutil import load_json_file


_ASSET_PATH = re.compile(
    r"^assets/(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+\.(?:svg|png|jpe?g)$",
    re.IGNORECASE,
)
_SCHOOL_ROOT_ENTRIES = frozenset(
    {"brand.json", "links.json", "diagnostics", "assets", ".initialized.json"}
)
_WINDOWS_RESERVED_BASENAMES = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{index}" for index in range(1, 10)}
    | {f"lpt{index}" for index in range(1, 10)}
)
_MAX_IMAGE_SIDE = 4096
_MAX_IMAGE_PIXELS = 4_000_000
_MAX_SVG_ATTRIBUTE_LENGTH = 65_536
_MAX_SVG_TEXT_LENGTH = 65_536
_MAX_SVG_MARKUP_COMPLEXITY = 262_144
_MAX_ASSET_REFERENCE_PIXELS = 50_000_000


def _contains_unsafe_text(value: str) -> bool:
    return any(
        unicodedata.category(character).startswith("C")
        or unicodedata.category(character) in {"Zl", "Zp"}
        for character in value
    )


def validate_school_layout(root: Path) -> None:
    for entry in root.iterdir():
        if entry.name not in _SCHOOL_ROOT_ENTRIES:
            raise ValueError("school_unexpected_entry")
        if entry.is_symlink():
            raise ValueError("school_symlink_not_allowed")
        if entry.name in {"brand.json", "links.json", ".initialized.json"}:
            if not entry.is_file():
                raise ValueError("school_config_not_file")
        elif entry.name in {"diagnostics", "assets"} and not entry.is_dir():
            raise ValueError("school_directory_invalid")


def validate_asset_path(value: str) -> str:
    segments = value.split("/")
    if (
        len(value) > 255
        or not _ASSET_PATH.fullmatch(value)
        or ".." in value
        or any(
            segment.split(".", 1)[0].casefold() in _WINDOWS_RESERVED_BASENAMES
            for segment in segments
        )
    ):
        raise ValueError("invalid_asset_path")
    return value


def _validate_css_tokens(tokens) -> int:
    count = 0
    for token in tokens:
        count += 1
        if count > 10_000 or token.type in {"error", "at-keyword"}:
            raise ValueError("asset_unsafe_svg")
        if token.type == "url":
            if not token.value.strip().startswith("#"):
                raise ValueError("asset_unsafe_svg")
        nested = getattr(token, "content", None)
        if nested is not None:
            count += _validate_css_tokens(nested)
            if count > 10_000:
                raise ValueError("asset_unsafe_svg")
        arguments = getattr(token, "arguments", None)
        if arguments is not None:
            if getattr(token, "lower_name", "") == "url":
                serialized = tinycss2.serialize(arguments).strip().strip("'\"").strip()
                if not serialized.startswith("#"):
                    raise ValueError("asset_unsafe_svg")
            count += _validate_css_tokens(arguments)
            if count > 10_000:
                raise ValueError("asset_unsafe_svg")
    return count


def _validate_svg_css(value: str) -> int:
    return _validate_css_tokens(tinycss2.parse_component_value_list(value))


def validate_asset_bytes(relative_path: str, raw: bytes) -> int:
    validate_asset_path(relative_path)
    if not raw or len(raw) > 5 * 1024 * 1024:
        raise ValueError("asset_too_large")
    suffix = Path(relative_path).suffix.lower()
    try:
        if suffix == ".svg":
            lowered = raw.lower()
            if any(marker in lowered for marker in (b"<!doctype", b"<!entity")):
                raise ValueError("asset_unsafe_svg")
            if re.search(rb"<\?(?!xml(?:\s|\?>))", lowered):
                raise ValueError("asset_unsafe_svg")
            svg_root = ElementTree.fromstring(raw)
            node_count = 0
            markup_complexity = 0
            for element in svg_root.iter():
                node_count += 1
                if node_count > 10_000:
                    raise ValueError("asset_too_complex")
                local_name = element.tag.rsplit("}", 1)[-1].casefold()
                if local_name in {"script", "foreignobject"}:
                    raise ValueError("asset_unsafe_svg")
                for attribute, value in element.attrib.items():
                    if len(value) > _MAX_SVG_ATTRIBUTE_LENGTH:
                        raise ValueError("asset_too_complex")
                    markup_complexity += len(value)
                    if markup_complexity > _MAX_SVG_MARKUP_COMPLEXITY:
                        raise ValueError("asset_too_complex")
                    attribute_name = attribute.rsplit("}", 1)[-1].casefold()
                    normalized_value = value.strip().casefold()
                    if attribute_name.startswith("on"):
                        raise ValueError("asset_unsafe_svg")
                    if (
                        attribute_name == "href"
                        and normalized_value
                        and not normalized_value.startswith("#")
                    ):
                        raise ValueError("asset_unsafe_svg")
                    if attribute_name == "d" and len(value) > _MAX_SVG_ATTRIBUTE_LENGTH:
                        raise ValueError("asset_too_complex")
                    _validate_svg_css(value)
                if element.text:
                    if len(element.text) > _MAX_SVG_TEXT_LENGTH:
                        raise ValueError("asset_too_complex")
                    markup_complexity += len(element.text)
                    if markup_complexity > _MAX_SVG_MARKUP_COMPLEXITY:
                        raise ValueError("asset_too_complex")
                    _validate_svg_css(element.text)
            drawing = svg2rlg(BytesIO(raw))
            if (
                drawing is None
                or drawing.width <= 0
                or drawing.height <= 0
                or drawing.width > _MAX_IMAGE_SIDE
                or drawing.height > _MAX_IMAGE_SIDE
                or drawing.width * drawing.height > _MAX_IMAGE_PIXELS
            ):
                raise ValueError("asset_invalid")
            return 0
        elif suffix in {".png", ".jpg", ".jpeg"}:
            image = ImageReader(BytesIO(raw))
            width, height = image.getSize()
            if (
                width <= 0 or height <= 0
                or width > _MAX_IMAGE_SIDE or height > _MAX_IMAGE_SIDE
                or width * height > _MAX_IMAGE_PIXELS
            ):
                raise ValueError("asset_invalid")
            image.getRGBData()
            return width * height
        else:
            raise ValueError("invalid_asset_path")
    except (ElementTree.ParseError, OSError) as exc:
        raise ValueError("asset_invalid") from exc
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("asset_invalid") from exc


def validate_asset_file(root: Path, relative_path: str) -> Path:
    validate_asset_path(relative_path)
    resolved_root = root.resolve(strict=True)
    current = resolved_root
    for part in Path(relative_path).parts:
        try:
            matching = [
                entry for entry in current.iterdir()
                if entry.name.casefold() == part.casefold()
            ]
        except OSError as exc:
            raise ValueError("asset_unreadable") from exc
        if len(matching) > 1:
            raise ValueError("asset_case_collision")
        if not matching or matching[0].name != part:
            raise ValueError("asset_case_mismatch")
        current = matching[0]
        if current.is_symlink():
            raise ValueError("asset_symlink_not_allowed")
    candidate = current
    try:
        resolved = candidate.resolve(strict=True)
        if not resolved.is_relative_to(resolved_root) or not resolved.is_file():
            raise ValueError("asset_not_file")
        size = resolved.stat().st_size
        if size > 5 * 1024 * 1024:
            raise ValueError("asset_too_large")
        validate_asset_bytes(relative_path, resolved.read_bytes())
    except OSError as exc:
        raise ValueError("asset_unreadable") from exc
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("asset_invalid") from exc
    return resolved


def validate_asset_inventory(root: Path, references) -> None:
    reference_list = list(references)
    unique_references = set(reference_list)
    if len(unique_references) > 201:
        raise ValueError("too_many_assets")
    total_bytes = 0
    sizes = {}
    pixel_costs = {}
    for relative_path in sorted(unique_references):
        resolved = validate_asset_file(root, relative_path)
        raw = resolved.read_bytes()
        sizes[relative_path] = len(raw)
        pixel_costs[relative_path] = validate_asset_bytes(relative_path, raw)
        total_bytes += sizes[relative_path]
    if total_bytes > 20 * 1024 * 1024:
        raise ValueError("assets_total_too_large")
    if sum(sizes[relative_path] for relative_path in reference_list) > 20 * 1024 * 1024:
        raise ValueError("asset_reference_workload_too_large")
    if sum(pixel_costs[relative_path] for relative_path in reference_list) > _MAX_ASSET_REFERENCE_PIXELS:
        raise ValueError("asset_reference_workload_too_large")
    assets_root = root / "assets"
    if not assets_root.is_dir() or assets_root.is_symlink():
        raise ValueError("assets_directory_invalid")
    for candidate in sorted(assets_root.rglob("*"), key=lambda item: item.as_posix()):
        if candidate.is_symlink():
            raise ValueError("asset_symlink_not_allowed")
        if candidate.is_file() and candidate.relative_to(root).as_posix() not in unique_references:
            raise ValueError("asset_unreferenced")


def validate_public_url(value: HttpUrl) -> HttpUrl:
    if (
        value.scheme != "https"
        or value.username is not None
        or value.password is not None
        or value.fragment is not None
        or len(str(value)) > 2048
        or len(value.query or "") > 512
    ):
        raise ValueError("invalid_public_url")
    return value


class BrandColors(BaseModel):
    model_config = ConfigDict(extra="forbid")

    primary: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    accent: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    background: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    signal: str = Field(default="#D8FF42", pattern=r"^#[0-9A-Fa-f]{6}$")
    ink: str = Field(default="#101517", pattern=r"^#[0-9A-Fa-f]{6}$")
    paper: str = Field(default="#F5F5F0", pattern=r"^#[0-9A-Fa-f]{6}$")


class PdfBrand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    header: str
    score_label: str
    correct_label: str
    strong_topics_label: str
    growth_topics_label: str
    forecast_label: str
    answer_label: str

    @field_validator("*")
    @classmethod
    def validate_pdf_label(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized or len(normalized) > 128 or _contains_unsafe_text(normalized):
            raise ValueError("invalid_pdf_label")
        return validate_report_text(normalized)


class InterfaceLabels(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command_start: str
    command_diagnostics: str
    command_results: str
    command_plan: str
    start_diagnostic: str
    open_diagnostic: str
    results: str
    plan: str
    home: str
    take_full_diagnostic: str
    check_another_subject: str
    take_another_diagnostic: str
    quick_result: str
    full_result: str
    ready_result: str
    unassessed_full: str
    results_heading: str
    diagnostic_fallback: str
    plan_for: str
    keep_strong: str
    focus_next: str
    open_result_hint: str
    result_not_found: str
    back: str
    task_label: str
    of_label: str
    answer_label: str
    enter_answer: str
    choose_option: str
    next_question: str
    get_result: str
    result_in_telegram: str
    privacy_label: str
    support_label: str
    choose_label: str
    close_diagnostic: str
    illustration_alt: str
    result_score: str
    result_correct: str
    delivery_note: str

    @field_validator("*")
    @classmethod
    def validate_label(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized or len(normalized) > 64 or _contains_unsafe_text(normalized):
            raise ValueError("invalid_interface_label")
        return normalized


class MessageTemplates(BaseModel):
    model_config = ConfigDict(extra="forbid")

    welcome: str
    results_empty: str
    plan_empty: str
    data_erased: str
    quick_complete: str
    full_complete: str
    not_started: str
    incomplete: str
    result_unviewed: str
    day_followup: str
    quick_to_full: str
    month_retest: str
    lives_refill: str = "Жизни в тренажёре восстановились — можно продолжать подготовку."
    generic: str

    @field_validator("*")
    @classmethod
    def validate_template_text(cls, value: str) -> str:
        if not value.strip() or len(value) > 2048 or _contains_unsafe_text(value):
            raise ValueError("invalid_message_template")
        return value

    def keyed(self) -> dict[str, str]:
        return {
            "WELCOME": self.welcome,
            "RESULTS_EMPTY": self.results_empty,
            "PLAN_EMPTY": self.plan_empty,
            "DATA_ERASED": self.data_erased,
            "QUICK_COMPLETE": self.quick_complete,
            "FULL_COMPLETE": self.full_complete,
            "NOT_STARTED": self.not_started,
            "INCOMPLETE": self.incomplete,
            "RESULT_UNVIEWED": self.result_unviewed,
            "DAY_FOLLOWUP": self.day_followup,
            "QUICK_TO_FULL": self.quick_to_full,
            "MONTH_RETEST": self.month_retest,
            "LIVES_REFILL": self.lives_refill,
        }


class BrandConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    school_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,62}$")
    name: str = Field(min_length=1, max_length=128)
    short_name: str = Field(min_length=1, max_length=64)
    bot_username: str | None = Field(
        default=None, pattern=r"^[A-Za-z][A-Za-z0-9_]{1,28}[Bb][Oo][Tt]$"
    )
    colors: BrandColors
    logo: str
    pdf: PdfBrand
    interface: InterfaceLabels
    messages: MessageTemplates

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if value != value.strip() or _contains_unsafe_text(value):
            raise ValueError("invalid_brand_name")
        return validate_report_text(value)

    @field_validator("short_name")
    @classmethod
    def validate_short_name(cls, value: str) -> str:
        if value != value.strip() or _contains_unsafe_text(value):
            raise ValueError("invalid_brand_name")
        return value

    @field_validator("logo")
    @classmethod
    def validate_logo(cls, value: str) -> str:
        return validate_asset_path(value)


class OfferConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,31}$")
    label: str = Field(min_length=1, max_length=128)
    button: str = Field(min_length=1, max_length=64)
    url: HttpUrl
    forecast_delta: int = Field(ge=0, le=100, strict=True)

    @field_validator("label")
    @classmethod
    def validate_offer_label(cls, value: str) -> str:
        if value != value.strip() or _contains_unsafe_text(value):
            raise ValueError("invalid_offer_text")
        return validate_report_text(value)

    @field_validator("button")
    @classmethod
    def validate_offer_button(cls, value: str) -> str:
        if value != value.strip() or _contains_unsafe_text(value):
            raise ValueError("invalid_offer_text")
        return value

    @field_validator("url")
    @classmethod
    def validate_offer_url(cls, value: HttpUrl) -> HttpUrl:
        return validate_public_url(value)


class LinksConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    website: HttpUrl
    support: HttpUrl
    privacy: HttpUrl
    offers: list[OfferConfig] = Field(max_length=10)

    @field_validator("website", "support", "privacy")
    @classmethod
    def validate_link_url(cls, value: HttpUrl) -> HttpUrl:
        return validate_public_url(value)

    @model_validator(mode="after")
    def validate_offer_ids(self) -> "LinksConfig":
        ids = [offer.id for offer in self.offers]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate_offer_id")
        return self


class SchoolConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    root: Path
    brand: BrandConfig
    links: LinksConfig

    def resolve_asset(self, relative_path: str) -> Path:
        root = self.root.resolve(strict=True)
        candidate = root
        for part in Path(relative_path).parts:
            if part in {"", ".", ".."}:
                raise ValueError("school_asset_outside_root")
            candidate = candidate / part
            if candidate.is_symlink():
                raise ValueError("school_asset_symlink_not_allowed")
        asset = candidate.resolve(strict=True)
        if not asset.is_relative_to(root):
            raise ValueError("school_asset_outside_root")
        return asset


def load_school(root: Path = Path("school")) -> SchoolConfig:
    if root.is_symlink() or not root.is_dir():
        raise ValueError("school_root_invalid")
    root = root.resolve(strict=True)
    validate_school_layout(root)
    brand_data = load_json_file(root / "brand.json", max_bytes=1024 * 1024)
    links_data = load_json_file(root / "links.json", max_bytes=1024 * 1024)
    try:
        school = SchoolConfig(root=root, brand=brand_data, links=links_data)
    except ValidationError:
        raise ValueError("school_config_invalid") from None
    from diagnostic.message_validation import validate_message_template

    primary_offer = school.links.offers[0] if school.links.offers else None
    raw_values = {
        "school_name": school.brand.name,
        "school_short_name": school.brand.short_name,
        "primary_offer_label": primary_offer.label if primary_offer else school.brand.name,
        "primary_offer_url": str(primary_offer.url if primary_offer else school.links.website),
        "website_url": str(school.links.website),
        "support_url": str(school.links.support),
        "privacy_url": str(school.links.privacy),
        "subject": "&" * 128,
        "mode": "full",
    }
    safe_values = {key: html.escape(value, quote=True) for key, value in raw_values.items()}

    try:
        for key, template in school.brand.messages.keyed().items():
            validate_message_template(key, template, safe_values)
        validate_message_template("GENERIC", school.brand.messages.generic, safe_values)
    except ValueError:
        raise ValueError("school_config_invalid") from None
    validate_asset_file(root, school.brand.logo)
    return school
