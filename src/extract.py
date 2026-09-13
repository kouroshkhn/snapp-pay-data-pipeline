from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"
SUPPORTED_EXTENSIONS = {".csv", ".tsv", ".xlsx", ".xls", ".parquet"}


@dataclass
class FileProfile:
    relative_file_path: str
    original_file_name: str
    file_extension: str
    file_size_bytes: int
    file_sha256: str
    sheet_name: str | None
    row_count: int | None
    column_count: int | None
    columns: list[str]
    read_status: str
    error_message: str | None
    profiled_at_utc: str


def calculate_sha256(file_path: Path, chunk_size: int = 1_048_576) -> str:
    hasher = hashlib.sha256()

    with file_path.open("rb") as file:
        for chunk in iter(lambda: file.read(chunk_size), b""):
            hasher.update(chunk)

    return hasher.hexdigest()

def detect_content_format(file_path: Path) -> str:
    with file_path.open("rb") as file:
        header = file.read(8_192)

    if header.startswith(b"PK\x03\x04"):
        return "xlsx"

    if header.startswith(b"\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1"):
        return "xls"

    decoded_header = header.decode("utf-8-sig", errors="replace")
    first_line = decoded_header.splitlines()[0] if decoded_header else ""

    if any(delimiter in first_line for delimiter in (",", ";", "\t")):
        return "csv"

    suffix = file_path.suffix.lower()

    if suffix == ".parquet":
        return "parquet"

    return "unknown"

def read_csv_with_fallbacks(file_path: Path) -> pd.DataFrame:
    encodings = ("utf-8-sig", "utf-8", "cp1256", "latin-1")
    delimiters = (",", ";", "\t")

    last_error: Exception | None = None

    for encoding in encodings:
        for delimiter in delimiters:
            try:
                dataframe = pd.read_csv(
                    file_path,
                    encoding=encoding,
                    sep=delimiter,
                    low_memory=False,
                )

                if dataframe.shape[1] > 1:
                    return dataframe
            except Exception as error:
                last_error = error

    message = f"Could not read CSV/TSV file: {file_path.name}"
    raise RuntimeError(message) from last_error


def profile_dataframe(
    file_path: Path,
    dataframe: pd.DataFrame,
    sheet_name: str | None,
    file_sha256: str,
) -> FileProfile:
    return FileProfile(
        relative_file_path=file_path.relative_to(PROJECT_ROOT).as_posix(),
        original_file_name=file_path.name,
        file_extension=file_path.suffix.lower().lstrip("."),
        file_size_bytes=file_path.stat().st_size,
        file_sha256=file_sha256,
        sheet_name=sheet_name,
        row_count=len(dataframe),
        column_count=len(dataframe.columns),
        columns=[str(column) for column in dataframe.columns],
        read_status="SUCCESS",
        error_message=None,
        profiled_at_utc=datetime.now(timezone.utc).isoformat(),
    )


def profile_file(file_path: Path) -> list[FileProfile]:
    file_sha256 = calculate_sha256(file_path)
    declared_extension = file_path.suffix.lower()
    content_format = detect_content_format(file_path)

    try:
        if content_format == "csv":
            dataframe = read_csv_with_fallbacks(file_path)
            return [profile_dataframe(file_path, dataframe, None, file_sha256)]

        if content_format == "xlsx":
            workbook = pd.ExcelFile(file_path, engine="openpyxl")
            profiles = []

            for sheet_name in workbook.sheet_names:
                dataframe = pd.read_excel(
                    workbook,
                    sheet_name=sheet_name,
                    engine="openpyxl",
                )
                profiles.append(
                    profile_dataframe(file_path, dataframe, sheet_name, file_sha256)
                )

            return profiles

        if content_format == "parquet":
            dataframe = pd.read_parquet(file_path)
            return [profile_dataframe(file_path, dataframe, None, file_sha256)]

        if content_format == "xls":
            raise ValueError(
                "Legacy XLS content detected. Install xlrd before reading this file."
            )

        raise ValueError(
            "Unsupported or unrecognized file content. "
            f"Declared extension: {declared_extension}; "
            f"detected content format: {content_format}."
        )

    except Exception as error:
        return [
            FileProfile(
                relative_file_path=file_path.relative_to(PROJECT_ROOT).as_posix(),
                original_file_name=file_path.name,
                file_extension=declared_extension.lstrip("."),
                file_size_bytes=file_path.stat().st_size,
                file_sha256=file_sha256,
                sheet_name=None,
                row_count=None,
                column_count=None,
                columns=[],
                read_status="FAILED",
                error_message=f"{type(error).__name__}: {error}",
                profiled_at_utc=datetime.now(timezone.utc).isoformat(),
            )
        ]
    

def discover_raw_files() -> list[Path]:
    if not RAW_DATA_DIR.exists():
        raise FileNotFoundError(
            f"Raw data directory does not exist: {RAW_DATA_DIR}"
        )

    return sorted(
        path
        for path in RAW_DATA_DIR.rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    )


def main() -> None:
    raw_files = discover_raw_files()

    if not raw_files:
        print(f"No supported source files found in: {RAW_DATA_DIR}")
        return

    profiles = [
        profile
        for file_path in raw_files
        for profile in profile_file(file_path)
    ]

    report_path = PROJECT_ROOT / "data" / "processed" / "raw_file_profile.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)

    report_path.write_text(
        json.dumps(
            [asdict(profile) for profile in profiles],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    successful_profiles = [
        profile for profile in profiles if profile.read_status == "SUCCESS"
    ]
    failed_profiles = [
        profile for profile in profiles if profile.read_status == "FAILED"
    ]

    print(f"Physical files discovered: {len(raw_files)}")
    print(f"Successful file/sheet profiles: {len(successful_profiles)}")
    print(f"Failed file/sheet profiles: {len(failed_profiles)}")
    print(f"Profile report written to: {report_path.relative_to(PROJECT_ROOT)}")

    for profile in profiles:
        sheet_suffix = f" | sheet={profile.sheet_name}" if profile.sheet_name else ""
        print(
            f"[{profile.read_status}] {profile.relative_file_path}{sheet_suffix} "
            f"| rows={profile.row_count} | columns={profile.column_count}"
        )

        if profile.error_message:
            print(f"  Error: {profile.error_message}")


if __name__ == "__main__":
    main()