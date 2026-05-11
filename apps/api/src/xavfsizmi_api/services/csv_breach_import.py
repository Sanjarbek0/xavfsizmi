"""CSV bulk import for the BreachCache table.

Admins can paste a HIBP-style CSV (or any spreadsheet export) and have it
upserted into the cache mirror in one shot. The parser is intentionally lenient
about whitespace, casing, and extra columns — but strict about the required
``name`` column, so a typo never silently drops rows.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import BreachCache

REQUIRED_COLUMN = "name"

# Aliases — accept common spelling variants HIBP uses (``Name`` vs ``BreachName``
# vs ``slug``) without forcing the user to rename columns.
_ALIASES: dict[str, set[str]] = {
    "name": {"name", "breachname", "slug"},
    "title": {"title"},
    "domain": {"domain"},
    "breach_date": {"breach_date", "breachdate", "date"},
    "pwn_count": {"pwn_count", "pwncount", "count"},
    "is_verified": {"is_verified", "isverified", "verified"},
    "is_sensitive": {"is_sensitive", "issensitive", "sensitive"},
    "description": {"description", "details"},
    "data_classes": {"data_classes", "dataclasses", "classes"},
}

_TRUTHY = {"true", "yes", "1", "y", "t"}
_FALSY = {"false", "no", "0", "n", "f"}


@dataclass(slots=True)
class ParsedBreach:
    name: str
    title: str | None = None
    domain: str | None = None
    breach_date: str | None = None
    pwn_count: int | None = None
    is_verified: bool | None = None
    is_sensitive: bool | None = None
    description: str | None = None
    data_classes: list[str] | None = None


@dataclass(slots=True)
class CsvImportError:
    line: int
    message: str


@dataclass(slots=True)
class CsvParseResult:
    rows: list[ParsedBreach] = field(default_factory=list)
    errors: list[CsvImportError] = field(default_factory=list)
    headers: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ImportResult:
    inserted: int = 0
    updated: int = 0
    errors: list[CsvImportError] = field(default_factory=list)
    inserted_names: list[str] = field(default_factory=list)
    updated_names: list[str] = field(default_factory=list)


def _norm_header(value: str) -> str:
    return value.strip().lower().replace(" ", "_").replace("-", "_")


def _bool_or_none(raw: str) -> bool | None:
    s = raw.strip().lower()
    if not s:
        return None
    if s in _TRUTHY:
        return True
    if s in _FALSY:
        return False
    return None


def _int_or_none(raw: str) -> int | None:
    s = raw.strip().replace(",", "").replace("_", "")
    if not s:
        return None
    try:
        return int(s)
    except ValueError:
        return None


def _extract_cells(row: list[str], column_map: dict[str, int]) -> dict[str, str]:
    out: dict[str, str] = {}
    for canonical in _ALIASES:
        idx = column_map.get(canonical)
        if idx is None or idx >= len(row):
            out[canonical] = ""
        else:
            out[canonical] = row[idx]
    return out


def _split_data_classes(raw: str) -> list[str] | None:
    s = raw.strip()
    if not s:
        return None
    # Allow either ``;`` or ``|`` separators (CSV-safe alternatives to ``,``).
    if ";" in s:
        parts = [p.strip() for p in s.split(";")]
    elif "|" in s:
        parts = [p.strip() for p in s.split("|")]
    else:
        parts = [p.strip() for p in s.split(",")]
    cleaned = [p for p in parts if p]
    return cleaned or None


def parse_breach_csv(data: bytes | str) -> CsvParseResult:
    """Parse CSV bytes/text into :class:`ParsedBreach` rows + per-line errors."""
    if isinstance(data, bytes):
        text = data.decode("utf-8-sig", errors="replace")
    else:
        text = data
    reader = csv.reader(io.StringIO(text))
    try:
        raw_headers = next(reader)
    except StopIteration:
        return CsvParseResult(errors=[CsvImportError(line=0, message="empty_file")])

    headers = [_norm_header(h) for h in raw_headers]
    column_map: dict[str, int] = {}
    for canonical, aliases in _ALIASES.items():
        for idx, header in enumerate(headers):
            if header in aliases:
                column_map[canonical] = idx
                break

    if REQUIRED_COLUMN not in column_map:
        return CsvParseResult(
            headers=headers,
            errors=[CsvImportError(line=1, message="missing_required_column:name")],
        )

    result = CsvParseResult(headers=headers)
    for line_no, row in enumerate(reader, start=2):
        if not any(cell.strip() for cell in row):
            continue
        try:
            name = row[column_map["name"]].strip()
        except IndexError:
            result.errors.append(CsvImportError(line=line_no, message="malformed_row"))
            continue
        if not name:
            result.errors.append(CsvImportError(line=line_no, message="missing_name"))
            continue

        cells = _extract_cells(row, column_map)
        result.rows.append(
            ParsedBreach(
                name=name,
                title=cells["title"].strip() or None,
                domain=cells["domain"].strip() or None,
                breach_date=cells["breach_date"].strip() or None,
                pwn_count=_int_or_none(cells["pwn_count"]),
                is_verified=_bool_or_none(cells["is_verified"]),
                is_sensitive=_bool_or_none(cells["is_sensitive"]),
                description=cells["description"].strip() or None,
                data_classes=_split_data_classes(cells["data_classes"]),
            )
        )

    return result


async def import_breaches(
    session: AsyncSession,
    rows: list[ParsedBreach],
    *,
    dry_run: bool = False,
) -> ImportResult:
    """Upsert each :class:`ParsedBreach` into the BreachCache table."""
    result = ImportResult()
    for row in rows:
        existing = (
            await session.execute(select(BreachCache).where(BreachCache.name == row.name))
        ).scalar_one_or_none()
        if existing is None:
            if not dry_run:
                rec = BreachCache(
                    name=row.name,
                    title=row.title,
                    domain=row.domain,
                    breach_date=row.breach_date,
                    pwn_count=row.pwn_count,
                    is_verified=row.is_verified,
                    is_sensitive=row.is_sensitive,
                    description=row.description,
                    data_classes=row.data_classes,
                    payload={
                        "title": row.title,
                        "domain": row.domain,
                        "breach_date": row.breach_date,
                        "pwn_count": row.pwn_count,
                        "is_verified": row.is_verified,
                        "is_sensitive": row.is_sensitive,
                        "description": row.description,
                        "data_classes": row.data_classes,
                    },
                )
                session.add(rec)
            result.inserted += 1
            result.inserted_names.append(row.name)
        else:
            if not dry_run:
                # Only overwrite fields that the CSV actually provided so
                # operators can do partial backfills without zeroing existing
                # metadata.
                if row.title is not None:
                    existing.title = row.title
                if row.domain is not None:
                    existing.domain = row.domain
                if row.breach_date is not None:
                    existing.breach_date = row.breach_date
                if row.pwn_count is not None:
                    existing.pwn_count = row.pwn_count
                if row.is_verified is not None:
                    existing.is_verified = row.is_verified
                if row.is_sensitive is not None:
                    existing.is_sensitive = row.is_sensitive
                if row.description is not None:
                    existing.description = row.description
                if row.data_classes is not None:
                    existing.data_classes = row.data_classes
            result.updated += 1
            result.updated_names.append(row.name)

    return result


__all__ = [
    "CsvImportError",
    "CsvParseResult",
    "ImportResult",
    "ParsedBreach",
    "import_breaches",
    "parse_breach_csv",
]
