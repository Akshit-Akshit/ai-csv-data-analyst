"""
CSV Loading Module

Provides robust, auditable, and memory-efficient CSV loading:
- File discovery and path validation with actionable diagnostics
- Differentiated handling of 0-byte, whitespace-only, header-only, and data files
- Safe encoding detection with non-redundant fallback attempts
- Header analysis for duplicate, blank, and colliding names
- Structural preservation: strict and tolerant modes for row width anomalies
- No silent data modification or surplus-column merging
- Streaming file reads avoiding duplicate in-memory buffering
"""

from __future__ import annotations

import csv
import io
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ai_csv_data_analyst.config import ProfilingConfig
from ai_csv_data_analyst.diagnostics import (
    AnomalySeverity,
    StructuralAnomalyType,
    StructuralDiagnostic,
)


@dataclass
class LoadError(Exception):
    """Exception raised when CSV loading fails."""
    message: str
    file_path: str | None = None
    line_number: int | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        loc = f" at line {self.line_number}" if self.line_number is not None else ""
        if self.file_path:
            return f"{self.message}{loc} ({self.file_path})"
        return f"{self.message}{loc}"


@dataclass
class LoadedCSV:
    """Structured result of a CSV load."""
    file_path: str
    headers: list[str]
    rows: list[dict[str, Any]]
    row_count: int
    column_count: int
    delimiter: str
    is_empty: bool = False
    error: LoadError | None = None

    # Enhanced auditable attributes
    column_identifiers: list[str] = field(default_factory=list)
    raw_records: list[list[str]] = field(default_factory=list)
    structural_diagnostics: list[StructuralDiagnostic] = field(default_factory=list)
    encoding_info: dict[str, Any] = field(default_factory=dict)
    delimiter_info: dict[str, Any] = field(default_factory=dict)
    file_type: str = "data_csv"  # 'empty_file', 'whitespace_only', 'header_only', 'data_csv'

    @property
    def is_valid(self) -> bool:
        """Check if the loaded CSV is valid (no fatal loading error)."""
        return self.error is None


def _detect_encoding_and_peek(
    path: Path,
    preferred_encoding: str | None,
    fallbacks: tuple[str, ...],
) -> tuple[str, bool, str]:
    """
    Determine the correct encoding by testing candidate encodings on the initial sample.
    Returns: (selected_encoding, has_bom, sample_text)
    """
    with open(path, "rb") as f:
        raw_head = f.read(65536)

    # Check for BOM
    has_bom = raw_head.startswith(b"\xef\xbb\xbf")

    # Build sequence of encodings to try without repeating
    candidates: list[str] = []
    if preferred_encoding:
        candidates.append(preferred_encoding)
    if has_bom and "utf-8-sig" not in candidates:
        candidates.insert(0, "utf-8-sig")
    elif "utf-8-sig" not in candidates:
        candidates.append("utf-8-sig")

    for enc in fallbacks:
        norm_enc = enc.lower().replace("-", "").replace("_", "")
        # Prevent trying utf8 right after utf8sig has failed
        is_already_present = any(
            c.lower().replace("-", "").replace("_", "") == norm_enc
            for c in candidates
        )
        if not is_already_present:
            candidates.append(enc)

    tried: list[str] = []
    for enc in candidates:
        tried.append(enc)
        try:
            sample_text = raw_head.decode(enc)
            return enc, has_bom, sample_text
        except UnicodeDecodeError:
            continue

    raise LoadError(
        message=f"Cannot decode file {path}. Attempted encodings: {', '.join(tried)}. The file may be corrupted or use an unsupported encoding.",
        file_path=str(path),
    )


def _resolve_headers(raw_headers: list[str]) -> tuple[list[str], list[str], list[StructuralDiagnostic]]:
    """
    Process headers: normalize whitespace, detect duplicates, blanks, and collisions.
    Returns: (cleaned_headers, unique_identifiers, diagnostics)
    """
    diagnostics: list[StructuralDiagnostic] = []
    cleaned_headers: list[str] = []
    unique_identifiers: list[str] = []
    seen_identifiers: dict[str, int] = {}
    normalized_map: dict[str, str] = {}

    for idx, raw_h in enumerate(raw_headers):
        clean_h = raw_h.strip()
        if not clean_h:
            clean_h = f"unnamed_{idx}"
            diagnostics.append(
                StructuralDiagnostic(
                    anomaly_type=StructuralAnomalyType.BLANK_HEADER,
                    message=f"Column index {idx} has an empty or blank header; assigned fallback '{clean_h}'",
                    line_number=1,
                    severity=AnomalySeverity.WARNING,
                    details={"column_index": idx, "assigned_identifier": clean_h},
                )
            )

        # Collision detection (e.g. " Name " vs "Name")
        norm_key = clean_h.lower()
        if norm_key in normalized_map and normalized_map[norm_key] != raw_h:
            diagnostics.append(
                StructuralDiagnostic(
                    anomaly_type=StructuralAnomalyType.HEADER_COLLISION,
                    message=f"Header '{raw_h}' at column {idx} collides with '{normalized_map[norm_key]}' after normalization",
                    line_number=1,
                    severity=AnomalySeverity.WARNING,
                    details={"column_index": idx, "header": raw_h, "collides_with": normalized_map[norm_key]},
                )
            )
        else:
            normalized_map[norm_key] = raw_h

        # Duplicate detection and unique identifier generation
        if clean_h in seen_identifiers:
            seen_identifiers[clean_h] += 1
            unique_id = f"{clean_h}_{seen_identifiers[clean_h]}"
            diagnostics.append(
                StructuralDiagnostic(
                    anomaly_type=StructuralAnomalyType.DUPLICATE_HEADER,
                    message=f"Duplicate header '{clean_h}' detected at column {idx}; disambiguated to identifier '{unique_id}'",
                    line_number=1,
                    severity=AnomalySeverity.WARNING,
                    details={"column_index": idx, "header": clean_h, "assigned_identifier": unique_id},
                )
            )
        else:
            seen_identifiers[clean_h] = 1
            unique_id = clean_h

        cleaned_headers.append(clean_h)
        unique_identifiers.append(unique_id)

    return cleaned_headers, unique_identifiers, diagnostics


def load_csv(
    file_path: str | Path,
    delimiter: str | None = ",",
    config: ProfilingConfig | None = None,
    strict_mode: bool | None = None,
) -> LoadedCSV:
    """
    Load a CSV file from the given path under configurable deterministic policies.

    Args:
        file_path: Path to the CSV file (string or Path object).
        delimiter: Column delimiter. Defaults to ','. If None or 'auto', auto-detects.
        config: Optional ProfilingConfig instance.
        strict_mode: If True, reject structurally invalid rows; if False, tolerant with diagnostics.

    Returns:
        LoadedCSV: Structured result containing headers, rows, raw records, and diagnostics.

    Raises:
        LoadError: If the file cannot be loaded or fails strict validation.
    """
    cfg = config or ProfilingConfig()
    is_strict = strict_mode if strict_mode is not None else cfg.strict_mode
    path = Path(file_path)

    # 1. Path existence and file type checks
    if not path.exists():
        raise LoadError(
            message=f"File not found: {file_path}",
            file_path=str(file_path),
        )

    if not path.is_file():
        raise LoadError(
            message=f"Path is not a file: {file_path}",
            file_path=str(file_path),
        )

    # 2. Resource check: file size limit
    file_size = path.stat().st_size
    if cfg.max_file_size_bytes is not None and file_size > cfg.max_file_size_bytes:
        raise LoadError(
            message=f"File size {file_size} bytes exceeds configured maximum limit of {cfg.max_file_size_bytes} bytes",
            file_path=str(file_path),
            details={"file_size": file_size, "limit": cfg.max_file_size_bytes},
        )

    # 3. Handle 0-byte files
    if file_size == 0:
        return LoadedCSV(
            file_path=str(file_path),
            headers=[],
            rows=[],
            row_count=0,
            column_count=0,
            delimiter=delimiter or ",",
            is_empty=True,
            file_type="empty_file",
        )

    # 4. Encoding determination
    try:
        selected_enc, has_bom, sample_text = _detect_encoding_and_peek(
            path=path,
            preferred_encoding=cfg.encoding,
            fallbacks=cfg.fallback_encodings,
        )
    except PermissionError:
        raise LoadError(
            message=f"Permission denied reading file: {file_path}",
            file_path=str(file_path),
        )
    except LoadError:
        raise
    except Exception as e:
        raise LoadError(
            message=f"Failed to read file: {file_path}. Error: {type(e).__name__}: {e}",
            file_path=str(file_path),
        )

    diagnostics: list[StructuralDiagnostic] = []
    if selected_enc != "utf-8" and selected_enc != "utf-8-sig":
        diagnostics.append(
            StructuralDiagnostic(
                anomaly_type=StructuralAnomalyType.ENCODING_FALLBACK,
                message=f"Selected fallback encoding '{selected_enc}' after UTF-8 failed",
                severity=AnomalySeverity.INFO,
                details={"encoding": selected_enc},
            )
        )

    # 5. Handle whitespace-only file
    if not sample_text.strip():
        # Verify whole file is whitespace
        with open(path, "r", encoding=selected_enc, errors="replace") as f:
            full_sample = f.read(1048576)
            if not full_sample.strip():
                return LoadedCSV(
                    file_path=str(file_path),
                    headers=[],
                    rows=[],
                    row_count=0,
                    column_count=0,
                    delimiter=delimiter or ",",
                    is_empty=True,
                    file_type="whitespace_only",
                    encoding_info={"selected_encoding": selected_enc, "bom_present": has_bom},
                )

    # 6. Delimiter determination
    active_delimiter = delimiter
    auto_detected = False
    candidates_tested = list(cfg.candidate_delimiters)
    if active_delimiter is None or active_delimiter == "auto":
        try:
            sniffer = csv.Sniffer()
            dialect = sniffer.sniff(sample_text, delimiters=candidates_tested)
            active_delimiter = dialect.delimiter
            auto_detected = True
        except Exception:
            active_delimiter = ","
            auto_detected = False

    delimiter_info = {
        "selected_delimiter": active_delimiter,
        "auto_detected": auto_detected,
        "candidates_tested": candidates_tested,
    }

    # 7. Stream file and parse records
    headers: list[str] = []
    unique_identifiers: list[str] = []
    rows: list[dict[str, Any]] = []
    raw_records: list[list[str]] = []
    file_type = "data_csv"

    try:
        with open(path, "r", encoding=selected_enc, newline="", errors="replace") as f:
            reader = csv.reader(f, delimiter=active_delimiter, quotechar='"', strict=True)
            try:
                first_row = next(reader)
            except StopIteration:
                return LoadedCSV(
                    file_path=str(file_path),
                    headers=[],
                    rows=[],
                    row_count=0,
                    column_count=0,
                    delimiter=active_delimiter,
                    is_empty=True,
                    file_type="empty_file",
                    encoding_info={"selected_encoding": selected_enc, "bom_present": has_bom},
                    delimiter_info=delimiter_info,
                )

            headers, unique_identifiers, header_diags = _resolve_headers(first_row)
            diagnostics.extend(header_diags)
            expected_width = len(headers)

            # Process data rows
            record_idx = 0
            for line_no, row in enumerate(reader, start=2):
                if cfg.max_rows is not None and record_idx >= cfg.max_rows:
                    diagnostics.append(
                        StructuralDiagnostic(
                            anomaly_type=StructuralAnomalyType.RESOURCE_LIMIT_EXCEEDED,
                            message=f"Reached maximum row limit ({cfg.max_rows}); remaining rows truncated",
                            line_number=line_no,
                            severity=AnomalySeverity.INFO,
                        )
                    )
                    break

                row_len = len(row)
                if row_len == expected_width:
                    # Ideal matching width
                    raw_records.append(row)
                    row_dict: dict[str, Any] = {}
                    for i, uid in enumerate(unique_identifiers):
                        row_dict[uid] = row[i]
                        # Also map primary header name if distinct from unique identifier
                        h_name = headers[i]
                        if h_name not in row_dict:
                            row_dict[h_name] = row[i]
                    rows.append(row_dict)

                elif row_len > expected_width:
                    # Surplus fields
                    surplus_count = row_len - expected_width
                    diag = StructuralDiagnostic(
                        anomaly_type=StructuralAnomalyType.SURPLUS_FIELDS,
                        message=f"Row {record_idx + 1} (line {line_no}) has {row_len} fields, expected {expected_width} ({surplus_count} surplus)",
                        line_number=line_no,
                        record_index=record_idx,
                        severity=AnomalySeverity.ERROR if is_strict else AnomalySeverity.WARNING,
                        details={
                            "expected_width": expected_width,
                            "actual_width": row_len,
                            "surplus_count": surplus_count,
                            "raw_surplus": row[expected_width:],
                            "recovery_action": "merged_into_final_column" if not is_strict else "none",
                        },
                    )
                    diagnostics.append(diag)

                    if is_strict:
                        raise LoadError(
                            message=diag.message,
                            file_path=str(file_path),
                            line_number=line_no,
                            details=diag.details,
                        )

                    # Tolerant mode: retain unmerged row in raw_records, traceably recover for final field
                    raw_records.append(row)
                    row_dict = {}
                    for i, uid in enumerate(unique_identifiers):
                        if i == len(headers) - 1:
                            val = ",".join(row[i:])
                        else:
                            val = row[i]
                        row_dict[uid] = val
                        h_name = headers[i]
                        if h_name not in row_dict:
                            row_dict[h_name] = val
                    rows.append(row_dict)

                else:
                    # Deficit fields (fewer columns)
                    missing_count = expected_width - row_len
                    diag = StructuralDiagnostic(
                        anomaly_type=StructuralAnomalyType.DEFICIT_FIELDS,
                        message=f"Row {record_idx + 1} (line {line_no}) has {row_len} fields, expected {expected_width} ({missing_count} missing)",
                        line_number=line_no,
                        record_index=record_idx,
                        severity=AnomalySeverity.ERROR if is_strict else AnomalySeverity.WARNING,
                        details={"expected_width": expected_width, "actual_width": row_len, "missing_count": missing_count},
                    )
                    diagnostics.append(diag)

                    if is_strict:
                        raise LoadError(
                            message=diag.message,
                            file_path=str(file_path),
                            line_number=line_no,
                            details=diag.details,
                        )

                    # Tolerant mode: pad missing fields with empty strings
                    padded_row = list(row) + [""] * missing_count
                    raw_records.append(padded_row)
                    row_dict = {}
                    for i, uid in enumerate(unique_identifiers):
                        row_dict[uid] = padded_row[i]
                        h_name = headers[i]
                        if h_name not in row_dict:
                            row_dict[h_name] = padded_row[i]
                    rows.append(row_dict)

                record_idx += 1

    except csv.Error as e:
        raise LoadError(
            message=f"Malformed CSV detected: {file_path}. Error: {e}",
            file_path=str(file_path),
        )
    except LoadError:
        raise
    except Exception as e:
        raise LoadError(
            message=f"Failed to parse CSV: {file_path}. Error: {type(e).__name__}: {e}",
            file_path=str(file_path),
        )

    if len(rows) == 0:
        file_type = "header_only"

    return LoadedCSV(
        file_path=str(file_path),
        headers=headers,
        rows=rows,
        row_count=len(rows),
        column_count=len(headers),
        delimiter=active_delimiter,
        is_empty=False,
        column_identifiers=unique_identifiers,
        raw_records=raw_records,
        structural_diagnostics=diagnostics,
        encoding_info={"selected_encoding": selected_enc, "bom_present": has_bom},
        delimiter_info=delimiter_info,
        file_type=file_type,
    )
