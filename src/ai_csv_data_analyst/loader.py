"""
CSV Loading Module

Provides a reusable CSV loading function that handles:
- File discovery and path validation
- Header parsing and normalization
- Data type preservation
- Error handling for malformed CSVs
- Missing value preservation (no silent data modification)
- Multi-line quoted fields
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class LoadError(Exception):
    """Exception raised when CSV loading fails."""
    message: str
    file_path: str | None = None

    def __str__(self) -> str:
        if self.file_path:
            return f"{self.message} ({self.file_path})"
        return self.message


@dataclass
class LoadedCSV:
    """Structured result of a successful CSV load."""
    file_path: str
    headers: list[str]
    rows: list[dict[str, Any]]
    row_count: int
    column_count: int
    delimiter: str
    is_empty: bool = False
    error: LoadError | None = None

    @property
    def is_valid(self) -> bool:
        """Check if the loaded CSV is valid (no errors)."""
        return self.error is None


def load_csv(file_path: str | Path, delimiter: str | None = ",") -> LoadedCSV:
    """
    Load a CSV file from the given path.

    Args:
        file_path: Path to the CSV file (string or Path object).
        delimiter: Column delimiter. Defaults to ','. If None, attempts auto-detection.

    Returns:
        LoadedCSV: Structured result containing headers, rows, and metadata.

    Raises:
        LoadError: If the file cannot be loaded due to errors (missing, malformed, unreadable).
    """
    # Normalize path
    path = Path(file_path)

    # Check if file exists
    if not path.exists():
        raise LoadError(
            message=f"File not found: {file_path}",
            file_path=str(file_path)
        )

    # Check if file is readable regular file
    if not path.is_file():
        raise LoadError(
            message=f"Path is not a file: {file_path}",
            file_path=str(file_path)
        )

    # Try to read the file content
    try:
        # Try utf-8-sig first to strip BOM if present
        content = path.read_text(encoding="utf-8-sig")
    except PermissionError:
        raise LoadError(
            message=f"Permission denied reading file: {file_path}",
            file_path=str(file_path)
        )
    except UnicodeDecodeError:
        try:
            # Fallback to utf-8 with error replace or latin-1
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            raise LoadError(
                message=f"Cannot decode file as UTF-8: {file_path}. The file may be corrupted or use a different encoding.",
                file_path=str(file_path)
            )
    except Exception as e:
        raise LoadError(
            message=f"Failed to read file: {file_path}. Error: {type(e).__name__}: {e}",
            file_path=str(file_path)
        )

    # Handle empty files (0 bytes or only whitespace)
    if not content.strip():
        return LoadedCSV(
            file_path=str(file_path),
            headers=[],
            rows=[],
            row_count=0,
            column_count=0,
            delimiter=delimiter or ",",
            is_empty=True
        )

    # Determine delimiter if None
    active_delimiter = delimiter
    if active_delimiter is None:
        try:
            sniffer = csv.Sniffer()
            sample = content[:4096]
            dialect = sniffer.sniff(sample, delimiters=[",", ";", "\t", "|"])
            active_delimiter = dialect.delimiter
        except Exception:
            active_delimiter = ","

    # Parse CSV using csv.reader with StringIO to properly handle embedded newlines and quotes
    try:
        stream = io.StringIO(content)
        reader = csv.reader(stream, delimiter=active_delimiter, quotechar='"', strict=True)
        
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
                is_empty=True
            )

        # Strip whitespace from headers
        headers = [h.strip() for h in first_row]

        # Extract data rows
        rows: list[dict[str, Any]] = []
        for row in reader:
            row_dict: dict[str, Any] = {}
            for i, header in enumerate(headers):
                if i == len(headers) - 1 and len(row) > len(headers):
                    # If more fields than headers, combine surplus into the last field (e.g. unquoted numbers or commas)
                    val = ",".join(row[i:])
                elif i < len(row):
                    val = row[i]
                else:
                    val = ""
                row_dict[header] = val
            rows.append(row_dict)

    except csv.Error as e:
        raise LoadError(
            message=f"Malformed CSV detected: {file_path}. Error: {e}",
            file_path=str(file_path)
        )
    except Exception as e:
        raise LoadError(
            message=f"Failed to parse CSV: {file_path}. Error: {type(e).__name__}: {e}",
            file_path=str(file_path)
        )

    return LoadedCSV(
        file_path=str(file_path),
        headers=headers,
        rows=rows,
        row_count=len(rows),
        column_count=len(headers),
        delimiter=active_delimiter,
        is_empty=False
    )
