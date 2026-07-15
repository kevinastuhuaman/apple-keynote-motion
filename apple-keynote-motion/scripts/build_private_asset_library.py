#!/usr/bin/env python3
"""Build a private, deduplicated media library from user-supplied Keynote decks.

The source decks are opened read-only. Media payloads are streamed from each
archive, stored by SHA-256, and indexed with deck and slide-component
provenance when keynote-parser is available. Apple-owned or third-party media
produced by this tool must remain outside a redistributable Codex skill.
"""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import html
import json
import mimetypes
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unicodedata
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from keynote_archive import ArchiveMember, KeynoteArchive


MEDIA_EXTENSIONS = {
    ".aif",
    ".aiff",
    ".ai",
    ".caf",
    ".gif",
    ".heic",
    ".icns",
    ".jpeg",
    ".jpg",
    ".m4a",
    ".m4v",
    ".mov",
    ".mp3",
    ".mp4",
    ".pdf",
    ".png",
    ".tif",
    ".tiff",
    ".wav",
    ".webp",
}

TYPE_EXTENSIONS = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/tiff": ".tiff",
    "image/icns": ".icns",
    "image/heic": ".heic",
    "application/pdf": ".pdf",
    "video/quicktime": ".mov",
    "video/mp4": ".mp4",
    "audio/mp4": ".m4a",
    "audio/wav": ".wav",
    "audio/aiff": ".aiff",
    "audio/caf": ".caf",
}

GENERIC_NAME_RE = re.compile(
    r"^(?:mt|st|posterimage|pasted-image|image|movie|audio|asset|[0-9a-f-]{12,})$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Detection:
    mime: str
    kind: str
    extension: str
    brand: str | None = None


def sha256_file(path: Path, chunk_size: int = 4 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_stream(stream: Any, destination: Path, chunk_size: int = 4 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as output:
        while chunk := stream.read(chunk_size):
            digest.update(chunk)
            output.write(chunk)
    return digest.hexdigest()


def recover_utf8_zip_name(name: str, utf8_flag: bool = False) -> str:
    """Recover UTF-8 bytes that were decoded as CP437 by zipfile."""

    if utf8_flag:
        return unicodedata.normalize("NFC", name)
    try:
        recovered = name.encode("cp437").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        recovered = name
    return unicodedata.normalize("NFC", recovered)


def raw_zip_name_b64(name: str, utf8_flag: bool = False) -> str:
    try:
        raw = name.encode("utf-8" if utf8_flag else "cp437")
    except UnicodeEncodeError:
        raw = name.encode("utf-8", errors="surrogatepass")
    return base64.b64encode(raw).decode("ascii")


def detect_file_kind(head: bytes, filename: str = "") -> Detection:
    lower = filename.lower()
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return Detection("image/png", "image", ".png")
    if head.startswith(b"\xff\xd8\xff"):
        return Detection("image/jpeg", "image", ".jpg")
    if head.startswith((b"II*\x00", b"MM\x00*")):
        return Detection("image/tiff", "image", ".tiff")
    if head.startswith((b"GIF87a", b"GIF89a")):
        return Detection("image/gif", "image", ".gif")
    if head.startswith(b"icns"):
        return Detection("image/icns", "image", ".icns")
    if head.startswith(b"%PDF"):
        return Detection("application/pdf", "document", ".pdf")
    if head.startswith(b"RIFF") and head[8:12] == b"WAVE":
        return Detection("audio/wav", "audio", ".wav")
    if head.startswith(b"FORM") and head[8:12] in {b"AIFF", b"AIFC"}:
        return Detection("audio/aiff", "audio", ".aiff")
    if head.startswith(b"caff"):
        return Detection("audio/caf", "audio", ".caf")
    if len(head) >= 12 and head[4:8] == b"ftyp":
        brand = head[8:12].decode("latin-1", errors="replace").strip()
        if brand.lower().startswith("m4a"):
            return Detection("audio/mp4", "audio", ".m4a", brand)
        if brand.lower() in {"heic", "heix", "hevc", "mif1", "msf1"}:
            return Detection("image/heic", "image", ".heic", brand)
        if brand == "qt":
            return Detection("video/quicktime", "video", ".mov", brand)
        return Detection("video/mp4", "video", ".mp4", brand)

    extension = Path(lower).suffix
    mime = mimetypes.guess_type(lower)[0] or "application/octet-stream"
    if extension in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".icns", ".gif", ".heic"}:
        return Detection(mime, "image", extension)
    if extension in {".mov", ".mp4", ".m4v"}:
        return Detection(mime, "video", extension)
    if extension in {".wav", ".aif", ".aiff", ".caf", ".m4a", ".mp3"}:
        return Detection(mime, "audio", extension)
    if extension in {".pdf", ".ai"}:
        return Detection(mime, "document", extension)
    return Detection(mime, "other", extension or ".bin")


def normalized_stem(name: str) -> str:
    stem = Path(name).stem
    stem = re.sub(r"-small(?:-[0-9]+)?$", "", stem, flags=re.IGNORECASE)
    stem = re.sub(r"-[0-9]+$", "", stem)
    return " ".join(re.sub(r"[_-]+", " ", stem).split())


def classify_asset_name(name: str, kind: str) -> tuple[str, list[str]]:
    text = normalized_stem(name).casefold()
    tags: list[str] = []
    tag_groups = {
        "device": ("iphone", "ipad", "imac", "macbook", "mac pro", "apple watch", "airtag", "airpods"),
        "ui": ("screen", "screenshot", "browse", "setting", "facetime", "safari", "storekit", "app store", "home screen"),
        "component": ("chip", "camera", "sensor", "logic board", "speaker", "microphone", "lidar", "display", "battery"),
        "environment": ("forest", "sky", "city", "school", "classroom", "field", "wallpaper", "background"),
        "service": ("music", "fitness", "arcade", "tv", "news", "itunes", "icloud"),
    }
    for tag, words in tag_groups.items():
        if any(word in text for word in words):
            tags.append(tag)

    if kind == "video":
        return "video-motion", tags
    if kind == "audio":
        return "audio", tags
    if "posterimage" in name.casefold() or Path(name).name.casefold().startswith("st-"):
        return "poster-frame", tags
    if any(word in text for word in ("wallpaper", "background", " bg", "hero background")):
        return "background", tags
    if any(word in text for word in ("icon", "logo", "symbol", "glyph", "emoji")):
        return "icon-logo", tags
    if "ui" in tags or any(word in text for word in ("menu", "notification", "control center", "app switch")):
        return "ui-screenshot", tags
    if "component" in tags:
        return "component-diagram", tags
    if "device" in tags or any(word in text for word in ("keyboard", "remote", "pencil", "trackpad", "magic mouse")):
        return "product-render", tags
    if kind == "image" and Path(name).suffix.casefold() in {".jpg", ".jpeg", ".tif", ".tiff"}:
        return "photography", tags
    if kind == "image":
        return "graphic", tags
    if kind == "document":
        return "vector-document", tags
    return "other", tags


def descriptive_name(name: str) -> bool:
    stem = normalized_stem(name)
    return bool(stem and not GENERIC_NAME_RE.match(stem))


def require_keynote_parser() -> tuple[Any, Any] | None:
    try:
        try:
            import keynote_parser.mapping as legacy_mapping
            from keynote_parser.generated import TSTArchives_pb2

            group_node = TSTArchives_pb2.GroupByArchive.GroupNodeArchive
            legacy_mapping.ID_NAME_MAP.setdefault(6383, group_node)
            legacy_mapping.NAME_CLASS_MAP.setdefault(group_node.DESCRIPTOR.full_name, group_node)
        except (ImportError, AttributeError):
            pass
        from keynote_parser.codec import IWAFile, message_to_dict

        return IWAFile, message_to_dict
    except ImportError:
        return None


def package_metadata(archive: KeynoteArchive) -> dict[str, Any] | None:
    parser = require_keynote_parser()
    if parser is None:
        return None
    IWAFile, message_to_dict = parser
    try:
        raw = archive.read("Index/Metadata.iwa")
        iwa = IWAFile.from_buffer(raw, "Index/Metadata.iwa")
    except Exception as exc:
        print(f"warning: metadata graph unavailable: {exc}", file=sys.stderr)
        return None
    for chunk in iwa.chunks:
        for segment in chunk.archives:
            for obj in segment.objects:
                data = message_to_dict(obj)
                if data.get("_pbtype") == "TSP.PackageMetadata":
                    return data
    return None


def index_package_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    if not metadata:
        return {"data_by_filename": {}, "relations_by_data_id": {}, "data_by_id": {}}

    data_by_id: dict[str, dict[str, Any]] = {}
    data_by_filename: dict[str, dict[str, Any]] = {}
    for row in metadata.get("datas", []):
        identifier = str(row.get("identifier", ""))
        if identifier:
            data_by_id[identifier] = row
        for key in ("fileName", "preferredFileName"):
            filename = row.get(key)
            if isinstance(filename, str) and filename:
                data_by_filename[unicodedata.normalize("NFC", filename).casefold()] = row

    relations: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for component in metadata.get("components", []):
        locator = component.get("locator") or component.get("preferredLocator") or ""
        preferred = component.get("preferredLocator") or ""
        for relation in component.get("dataReferences", []):
            data_id = str(relation.get("dataIdentifier", ""))
            if not data_id:
                continue
            relations[data_id].append(
                {
                    "component_id": str(component.get("identifier", "")),
                    "preferred_locator": preferred,
                    "locator": locator,
                    "object_ids": [
                        str(item.get("objectIdentifier", ""))
                        for item in relation.get("objectReferenceList", [])
                        if item.get("objectIdentifier") is not None
                    ],
                }
            )
    return {
        "data_by_filename": data_by_filename,
        "relations_by_data_id": dict(relations),
        "data_by_id": data_by_id,
    }


def recover_slide_number_map(deck: Path) -> dict[str, int]:
    try:
        from recover_slide_order import recover

        payload = recover(deck)
    except Exception as exc:
        print(f"warning: slide order unavailable for {deck.name}: {exc}", file=sys.stderr)
        return {}
    return {str(row["archive_name"]): int(row["slide_number"]) for row in payload["rows"]}


def logical_data_name(member: ArchiveMember) -> tuple[str, str, str]:
    utf8_flag = bool(member.info.flag_bits & 0x800)
    recovered = recover_utf8_zip_name(member.name, utf8_flag)
    basename = recovered.split("/", 1)[1] if "/" in recovered else recovered
    raw_b64 = raw_zip_name_b64(member.info.filename, utf8_flag)
    return recovered, basename, raw_b64


def lookup_data_info(name: str, metadata_index: dict[str, Any]) -> dict[str, Any] | None:
    candidates = [name, Path(name).name]
    for candidate in candidates:
        row = metadata_index["data_by_filename"].get(
            unicodedata.normalize("NFC", candidate).casefold()
        )
        if row:
            return row
    return None


def slide_relations(
    data_id: str | None,
    metadata_index: dict[str, Any],
    slide_number_map: dict[str, int],
) -> tuple[list[int], list[str], list[str]]:
    slide_numbers: set[int] = set()
    components: set[str] = set()
    object_ids: set[str] = set()
    if not data_id:
        return [], [], []
    for relation in metadata_index["relations_by_data_id"].get(data_id, []):
        locator = str(relation.get("locator") or relation.get("preferred_locator") or "")
        components.add(locator)
        archive_name = f"Index/{locator}.iwa"
        if archive_name in slide_number_map:
            slide_numbers.add(slide_number_map[archive_name])
        object_ids.update(relation.get("object_ids", []))
    return sorted(slide_numbers), sorted(components), sorted(object_ids)


def ffprobe(path: Path) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration:stream=codec_type,codec_name,width,height,r_frame_rate,channels",
                "-of",
                "json",
                str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
        return json.loads(proc.stdout)
    except (FileNotFoundError, subprocess.SubprocessError, json.JSONDecodeError):
        return {}


def image_metadata(path: Path) -> dict[str, Any]:
    try:
        from PIL import Image, ImageStat

        with Image.open(path) as image:
            width, height = image.size
            alpha = image.mode in {"RGBA", "LA"} or "transparency" in image.info
            sample = image.convert("RGBA")
            sample.thumbnail((64, 64))
            opaque = Image.new("RGBA", sample.size, (0, 0, 0, 255))
            opaque.alpha_composite(sample)
            stats = ImageStat.Stat(opaque.convert("RGB"))
            average = "#" + "".join(f"{round(value):02x}" for value in stats.mean[:3])
            return {
                "width": width,
                "height": height,
                "alpha": alpha,
                "average_color": average,
            }
    except Exception:
        return {}


def media_metadata(path: Path, detection: Detection) -> dict[str, Any]:
    if detection.kind == "image":
        return image_metadata(path)
    if detection.kind not in {"video", "audio"}:
        return {}
    probe = ffprobe(path)
    streams = probe.get("streams", [])
    video = next((row for row in streams if row.get("codec_type") == "video"), {})
    audio = next((row for row in streams if row.get("codec_type") == "audio"), {})
    duration = probe.get("format", {}).get("duration")
    return {
        "width": video.get("width"),
        "height": video.get("height"),
        "duration": float(duration) if duration else None,
        "codec": video.get("codec_name") or audio.get("codec_name"),
        "frame_rate": video.get("r_frame_rate"),
        "channels": audio.get("channels"),
    }


def orientation(width: int | None, height: int | None) -> str | None:
    if not width or not height:
        return None
    if abs(width - height) / max(width, height) < 0.05:
        return "square"
    return "landscape" if width > height else "portrait"


def make_image_preview(source: Path, destination: Path) -> bool:
    try:
        from PIL import Image, ImageOps

        with Image.open(source) as opened:
            image = ImageOps.exif_transpose(opened).convert("RGBA")
            image.thumbnail((480, 300), Image.Resampling.LANCZOS)
            canvas = Image.new("RGB", (480, 300), (18, 18, 18))
            tile = 20
            for y in range(0, 300, tile):
                for x in range(0, 480, tile):
                    shade = 34 if (x // tile + y // tile) % 2 else 24
                    canvas.paste((shade, shade, shade), (x, y, x + tile, y + tile))
            x = (480 - image.width) // 2
            y = (300 - image.height) // 2
            canvas.paste(image, (x, y), image)
            destination.parent.mkdir(parents=True, exist_ok=True)
            canvas.save(destination, "JPEG", quality=86, optimize=True)
        return True
    except Exception:
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                ["sips", "-s", "format", "jpeg", str(source), "--out", str(destination)],
                check=True,
                capture_output=True,
                timeout=120,
            )
            return destination.exists() and destination.stat().st_size > 0
        except (FileNotFoundError, subprocess.SubprocessError):
            return False


def make_video_preview(source: Path, destination: Path, duration: float | None) -> bool:
    seek = max(0.25, (duration or 3.0) * 0.33)
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-v",
                "error",
                "-ss",
                f"{seek:.3f}",
                "-i",
                str(source),
                "-frames:v",
                "1",
                "-vf",
                "scale=480:300:force_original_aspect_ratio=decrease,pad=480:300:(ow-iw)/2:(oh-ih)/2:color=0x121212",
                "-q:v",
                "3",
                str(destination),
            ],
            check=True,
            timeout=180,
        )
        return destination.exists() and destination.stat().st_size > 0
    except (FileNotFoundError, subprocess.SubprocessError):
        return False


def make_audio_preview(source: Path, destination: Path) -> bool:
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-v",
                "error",
                "-i",
                str(source),
                "-filter_complex",
                "showwavespic=s=480x300:colors=white",
                "-frames:v",
                "1",
                str(destination),
            ],
            check=True,
            timeout=180,
        )
        return destination.exists() and destination.stat().st_size > 0
    except (FileNotFoundError, subprocess.SubprocessError):
        return False


def create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS decks (
            deck_id TEXT PRIMARY KEY,
            filename TEXT NOT NULL,
            private_source_path TEXT NOT NULL,
            source_sha256 TEXT NOT NULL,
            size_bytes INTEGER NOT NULL,
            archive_layout TEXT NOT NULL,
            slide_count INTEGER,
            xattrs_json TEXT NOT NULL,
            source_mtime REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS objects (
            sha256 TEXT PRIMARY KEY,
            object_path TEXT NOT NULL,
            preview_path TEXT,
            size_bytes INTEGER NOT NULL,
            mime TEXT NOT NULL,
            kind TEXT NOT NULL,
            extension TEXT NOT NULL,
            brand TEXT,
            width INTEGER,
            height INTEGER,
            orientation TEXT,
            duration REAL,
            codec TEXT,
            frame_rate TEXT,
            channels INTEGER,
            has_alpha INTEGER,
            average_color TEXT
        );
        CREATE TABLE IF NOT EXISTS occurrences (
            occurrence_id INTEGER PRIMARY KEY AUTOINCREMENT,
            deck_id TEXT NOT NULL REFERENCES decks(deck_id),
            zip_index INTEGER NOT NULL,
            data_identifier TEXT,
            archive_member TEXT NOT NULL,
            recovered_name TEXT NOT NULL,
            preferred_name TEXT,
            raw_member_name_b64 TEXT NOT NULL,
            crc32 TEXT NOT NULL,
            compressed_size INTEGER NOT NULL,
            size_bytes INTEGER NOT NULL,
            sha256 TEXT NOT NULL REFERENCES objects(sha256),
            category TEXT NOT NULL,
            tags_json TEXT NOT NULL,
            slide_numbers_json TEXT NOT NULL,
            components_json TEXT NOT NULL,
            object_ids_json TEXT NOT NULL,
            is_small_variant INTEGER NOT NULL,
            is_descriptive_name INTEGER NOT NULL,
            UNIQUE(deck_id, zip_index)
        );
        CREATE INDEX IF NOT EXISTS occurrences_name_idx ON occurrences(recovered_name);
        CREATE INDEX IF NOT EXISTS occurrences_kind_idx ON occurrences(category);
        CREATE INDEX IF NOT EXISTS occurrences_sha_idx ON occurrences(sha256);
        CREATE VIRTUAL TABLE IF NOT EXISTS asset_search USING fts5(
            occurrence_id UNINDEXED,
            recovered_name,
            preferred_name,
            deck_id,
            category,
            tags
        );
        """
    )


def source_xattrs(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    try:
        names = subprocess.run(
            ["xattr", str(path)],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
        for name in names:
            value = subprocess.run(
                ["xattr", "-px", name, str(path)],
                check=True,
                capture_output=True,
            ).stdout.strip()
            result[name] = value.decode("ascii", errors="replace")
    except (FileNotFoundError, subprocess.SubprocessError):
        return result
    return result


def deck_id(path: Path) -> str:
    name = path.stem.casefold()
    name = re.sub(r"^apple-event-", "", name)
    name = re.sub(r"\s*\([0-9]+\)$", "", name)
    return re.sub(r"[^a-z0-9]+", "-", name).strip("-")


def deck_paths(source_dir: Path, explicit: list[Path]) -> list[Path]:
    paths = [path.expanduser().resolve() for path in explicit]
    if source_dir:
        paths.extend(sorted(source_dir.expanduser().resolve().glob("*.key")))
    unique: dict[Path, None] = {}
    for path in paths:
        if path.is_file() and path.suffix.casefold() == ".key":
            unique[path] = None
    return list(unique)


def object_destination(root: Path, sha256: str, extension: str) -> Path:
    safe_extension = extension if re.fullmatch(r"\.[a-z0-9]{1,8}", extension) else ".bin"
    return root / "objects" / "sha256" / sha256[:2] / f"{sha256}{safe_extension}"


def insert_object(
    connection: sqlite3.Connection,
    sha256: str,
    object_path: Path,
    detection: Detection,
    metadata: dict[str, Any],
    output_root: Path,
) -> None:
    connection.execute(
        """
        INSERT OR IGNORE INTO objects (
            sha256, object_path, size_bytes, mime, kind, extension, brand,
            width, height, orientation, duration, codec, frame_rate, channels,
            has_alpha, average_color
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            sha256,
            str(object_path.relative_to(output_root)),
            object_path.stat().st_size,
            detection.mime,
            detection.kind,
            detection.extension,
            detection.brand,
            metadata.get("width"),
            metadata.get("height"),
            orientation(metadata.get("width"), metadata.get("height")),
            metadata.get("duration"),
            metadata.get("codec"),
            metadata.get("frame_rate"),
            metadata.get("channels"),
            int(bool(metadata.get("alpha"))),
            metadata.get("average_color"),
        ),
    )


def process_deck(
    deck: Path,
    output_root: Path,
    connection: sqlite3.Connection,
    extract: bool,
    max_assets: int | None,
) -> None:
    before_hash = sha256_file(deck)
    before_stat = deck.stat()
    current_deck_id = deck_id(deck)
    print(f"deck {current_deck_id}: reading metadata graph")

    with KeynoteArchive(deck) as archive:
        metadata_index = index_package_metadata(package_metadata(archive))
        slide_number_map = recover_slide_number_map(deck) if metadata_index["data_by_id"] else {}
        data_members = [member for member in archive.infolist() if member.name.startswith("Data/")]
        if max_assets is not None:
            data_members = data_members[:max_assets]
        old_occurrences = connection.execute(
            "SELECT occurrence_id FROM occurrences WHERE deck_id = ?", (current_deck_id,)
        ).fetchall()
        for (occurrence_id,) in old_occurrences:
            connection.execute("DELETE FROM asset_search WHERE occurrence_id = ?", (occurrence_id,))
        connection.execute("DELETE FROM occurrences WHERE deck_id = ?", (current_deck_id,))
        connection.execute(
            """
            INSERT OR REPLACE INTO decks VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                current_deck_id,
                deck.name,
                str(deck),
                before_hash,
                before_stat.st_size,
                archive.layout,
                len(slide_number_map) or None,
                json.dumps(source_xattrs(deck), sort_keys=True),
                before_stat.st_mtime,
            ),
        )

        for zip_index, member in enumerate(data_members):
            recovered_path, recovered_name, raw_name = logical_data_name(member)
            with archive.open(member) as source:
                head = source.read(64)
            detection = detect_file_kind(head, recovered_name)
            if detection.kind == "other" and Path(recovered_name).suffix.casefold() not in MEDIA_EXTENSIONS:
                continue

            with tempfile.NamedTemporaryFile(
                prefix="keynote-asset-", dir=output_root / "tmp", delete=False
            ) as temp:
                temp_path = Path(temp.name)
            try:
                with archive.open(member) as source:
                    payload_sha = sha256_stream(source, temp_path)
                destination = object_destination(output_root, payload_sha, detection.extension)
                existing = connection.execute(
                    "SELECT object_path FROM objects WHERE sha256 = ?", (payload_sha,)
                ).fetchone()
                if existing:
                    destination = output_root / existing[0]
                    temp_path.unlink(missing_ok=True)
                elif extract:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(temp_path, destination)
                    os.chmod(destination, 0o400)
                else:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(temp_path, destination)

                metadata = media_metadata(destination, detection)
                insert_object(connection, payload_sha, destination, detection, metadata, output_root)

                data_info = lookup_data_info(recovered_name, metadata_index)
                data_identifier = str(data_info.get("identifier")) if data_info else None
                preferred_name = data_info.get("preferredFileName") if data_info else None
                slides, components, object_ids = slide_relations(
                    data_identifier, metadata_index, slide_number_map
                )
                category, tags = classify_asset_name(preferred_name or recovered_name, detection.kind)
                cursor = connection.execute(
                    """
                    INSERT OR REPLACE INTO occurrences (
                        deck_id, zip_index, data_identifier, archive_member, recovered_name,
                        preferred_name, raw_member_name_b64, crc32, compressed_size,
                        size_bytes, sha256, category, tags_json, slide_numbers_json,
                        components_json, object_ids_json, is_small_variant,
                        is_descriptive_name
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        current_deck_id,
                        zip_index,
                        data_identifier,
                        member.name,
                        recovered_name,
                        preferred_name,
                        raw_name,
                        f"{member.info.CRC:08x}",
                        member.compressed,
                        member.size,
                        payload_sha,
                        category,
                        json.dumps(tags),
                        json.dumps(slides),
                        json.dumps(components),
                        json.dumps(object_ids),
                        int("-small" in recovered_name.casefold()),
                        int(descriptive_name(preferred_name or recovered_name)),
                    ),
                )
                occurrence_id = cursor.lastrowid
                connection.execute("DELETE FROM asset_search WHERE occurrence_id = ?", (occurrence_id,))
                connection.execute(
                    "INSERT INTO asset_search VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        occurrence_id,
                        recovered_name,
                        preferred_name or "",
                        current_deck_id,
                        category,
                        " ".join(tags),
                    ),
                )
                if (zip_index + 1) % 100 == 0 or zip_index + 1 == len(data_members):
                    connection.commit()
                    print(f"deck {current_deck_id}: {zip_index + 1}/{len(data_members)} assets")
            finally:
                temp_path.unlink(missing_ok=True)

    after_stat = deck.stat()
    after_hash = sha256_file(deck)
    if after_hash != before_hash or after_stat.st_size != before_stat.st_size or after_stat.st_mtime != before_stat.st_mtime:
        raise RuntimeError(f"source changed during extraction: {deck}")


def preview_one(row: sqlite3.Row, output_root: Path) -> tuple[str, str | None]:
    source = output_root / row["object_path"]
    destination = output_root / "previews" / row["sha256"][:2] / f"{row['sha256']}.jpg"
    if destination.exists() and destination.stat().st_size > 0:
        return row["sha256"], str(destination.relative_to(output_root))
    ok = False
    if row["kind"] == "image":
        ok = make_image_preview(source, destination)
    elif row["kind"] == "video":
        ok = make_video_preview(source, destination, row["duration"])
    elif row["kind"] == "audio":
        ok = make_audio_preview(source, destination)
    return row["sha256"], str(destination.relative_to(output_root)) if ok else None


def build_previews(connection: sqlite3.Connection, output_root: Path, workers: int) -> None:
    connection.row_factory = sqlite3.Row
    rows = connection.execute(
        "SELECT * FROM objects WHERE kind IN ('image', 'video', 'audio') ORDER BY size_bytes"
    ).fetchall()
    print(f"previews: rendering {len(rows)} unique media objects with {workers} workers")
    completed = 0
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(preview_one, row, output_root) for row in rows]
        for future in as_completed(futures):
            sha256, preview_path = future.result()
            connection.execute(
                "UPDATE objects SET preview_path = ? WHERE sha256 = ?", (preview_path, sha256)
            )
            completed += 1
            if completed % 100 == 0 or completed == len(rows):
                connection.commit()
                print(f"previews: {completed}/{len(rows)}")


def export_catalog(connection: sqlite3.Connection, output_root: Path) -> list[dict[str, Any]]:
    connection.row_factory = sqlite3.Row
    rows = connection.execute(
        """
        SELECT o.occurrence_id, o.deck_id, o.recovered_name, o.preferred_name,
               o.category, o.tags_json, o.slide_numbers_json, o.is_small_variant,
               o.is_descriptive_name, b.sha256, b.object_path, b.preview_path,
               b.size_bytes, b.mime, b.kind, b.width, b.height, b.orientation,
               b.duration, b.codec, b.has_alpha, b.average_color
        FROM occurrences o JOIN objects b ON o.sha256 = b.sha256
        ORDER BY o.deck_id, o.zip_index
        """
    ).fetchall()
    payload: list[dict[str, Any]] = []
    csv_path = output_root / "catalog.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        fieldnames = list(rows[0].keys()) if rows else []
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        if rows:
            writer.writeheader()
        for row in rows:
            raw = dict(row)
            writer.writerow(raw)
            item = dict(raw)
            item["tags"] = json.loads(item.pop("tags_json"))
            item["slides"] = json.loads(item.pop("slide_numbers_json"))
            payload.append(item)
    (output_root / "catalog.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return payload


def write_browser(payload: list[dict[str, Any]], output_root: Path) -> None:
    compact = [
        {
            "id": row["occurrence_id"],
            "deck": row["deck_id"],
            "name": row["preferred_name"] or row["recovered_name"],
            "archiveName": row["recovered_name"],
            "category": row["category"],
            "tags": row["tags"],
            "slides": row["slides"],
            "kind": row["kind"],
            "orientation": row["orientation"],
            "width": row["width"],
            "height": row["height"],
            "duration": row["duration"],
            "size": row["size_bytes"],
            "alpha": bool(row["has_alpha"]),
            "preview": row["preview_path"],
            "object": row["object_path"],
        }
        for row in payload
    ]
    data = json.dumps(compact, ensure_ascii=False).replace("</", "<\\/")
    template = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Private Apple Keynote Asset Library</title>
<style>
:root{color-scheme:dark;font-family:-apple-system,BlinkMacSystemFont,"Helvetica Neue",Arial,sans-serif;background:#080808;color:#f5f5f7}*{box-sizing:border-box}body{margin:0}header{position:sticky;top:0;z-index:2;background:rgba(8,8,8,.96);border-bottom:1px solid #2a2a2d;padding:18px 24px}.title{font-size:22px;font-weight:650;margin-bottom:14px}.controls{display:grid;grid-template-columns:minmax(220px,2fr) repeat(4,minmax(120px,1fr));gap:10px}input,select{width:100%;background:#1c1c1e;color:#f5f5f7;border:1px solid #3a3a3c;border-radius:6px;padding:10px;font-size:14px}.summary{padding:14px 24px;color:#a1a1a6;border-bottom:1px solid #242426}.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:14px;padding:18px 24px 40px}.asset{border:1px solid #2c2c2e;border-radius:8px;overflow:hidden;background:#141416;min-width:0}.thumb{display:block;width:100%;aspect-ratio:8/5;object-fit:cover;background:#1c1c1e}.missing{width:100%;aspect-ratio:8/5;display:grid;place-items:center;color:#636366;background:#1c1c1e}.meta{padding:11px}.name{font-size:14px;font-weight:600;line-height:1.25;overflow-wrap:anywhere}.sub{font-size:12px;color:#98989d;margin-top:7px;line-height:1.35}.pill{display:inline-block;border:1px solid #3a3a3c;border-radius:999px;padding:2px 6px;margin:5px 4px 0 0;font-size:11px;color:#c7c7cc}a{color:inherit;text-decoration:none}@media(max-width:850px){.controls{grid-template-columns:1fr 1fr}.controls input{grid-column:1/-1}}
</style></head><body>
<header><div class="title">Private Apple Keynote Asset Library</div><div class="controls">
<input id="q" type="search" placeholder="Search product, UI, camera, chip, education…">
<select id="deck"><option value="">All decks</option></select><select id="kind"><option value="">All media</option></select>
<select id="category"><option value="">All categories</option></select><select id="orientation"><option value="">All orientations</option></select>
</div></header><div class="summary" id="summary"></div><main class="grid" id="grid"></main>
<script>const assets=__DATA__;const $=id=>document.getElementById(id);const filters=['deck','kind','category','orientation'];
function options(id,key){const values=[...new Set(assets.map(x=>x[key]).filter(Boolean))].sort();for(const value of values){const o=document.createElement('option');o.value=value;o.textContent=value;$(id).appendChild(o)}}
for(const key of filters)options(key,key);function formatSize(n){if(!n)return'';const u=['B','KB','MB','GB'];let i=0;while(n>=1024&&i<u.length-1){n/=1024;i++}return `${n.toFixed(i?1:0)} ${u[i]}`}
function render(){const query=$('q').value.trim().toLowerCase();let rows=assets.filter(a=>{if(query&&!`${a.name} ${a.archiveName} ${a.deck} ${a.category} ${(a.tags||[]).join(' ')}`.toLowerCase().includes(query))return false;return filters.every(k=>!$(k).value||a[k]===$(k).value)});$('summary').textContent=`${rows.length.toLocaleString()} matches · showing up to 600`;rows=rows.slice(0,600);$('grid').replaceChildren(...rows.map(a=>{const card=document.createElement('article');card.className='asset';const media=a.preview?`<a href="${a.object}" target="_blank"><img class="thumb" loading="lazy" src="${a.preview}" alt=""></a>`:`<a href="${a.object}" target="_blank"><div class="missing">No preview</div></a>`;const details=[a.deck,a.kind,a.category,a.width&&a.height?`${a.width}×${a.height}`:'',a.duration?`${Number(a.duration).toFixed(1)}s`:'',formatSize(a.size)].filter(Boolean).join(' · ');card.innerHTML=media+`<div class="meta"><div class="name">${escapeHtml(a.name)}</div><div class="sub">${escapeHtml(details)}${a.slides?.length?`<br>Slides ${a.slides.join(', ')}`:''}</div>${(a.tags||[]).map(t=>`<span class="pill">${escapeHtml(t)}</span>`).join('')}</div>`;return card}))}
function escapeHtml(s){return String(s??'').replace(/[&<>\"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}[c]))}for(const id of ['q',...filters])$(id).addEventListener('input',render);render();</script></body></html>"""
    (output_root / "index.html").write_text(template.replace("__DATA__", data), encoding="utf-8")


def write_summary(connection: sqlite3.Connection, output_root: Path) -> None:
    unique_objects, total_occurrences, total_bytes = connection.execute(
        "SELECT (SELECT count(*) FROM objects), count(*), sum(size_bytes) FROM occurrences"
    ).fetchone()
    by_kind = connection.execute(
        "SELECT b.kind, count(*), sum(o.size_bytes) FROM occurrences o JOIN objects b ON o.sha256=b.sha256 GROUP BY b.kind ORDER BY count(*) DESC"
    ).fetchall()
    by_deck = connection.execute(
        "SELECT deck_id, count(*), sum(size_bytes) FROM occurrences GROUP BY deck_id ORDER BY deck_id"
    ).fetchall()
    lines = [
        "# Private Keynote Asset Library",
        "",
        "This local library contains media extracted from user-supplied Apple-event deck copies. It is for private reference and user-authorized deck work only. Do not redistribute it or bundle it with the shareable skill. Archive provenance does not prove that every embedded asset was created or licensed by Apple.",
        "",
        f"- Asset occurrences: **{total_occurrences:,}**",
        f"- Unique payloads: **{unique_objects:,}**",
        f"- Indexed occurrence bytes: **{total_bytes:,}**",
        "",
        "## By Media Type",
        "",
        "| Type | Occurrences | Bytes |",
        "| --- | ---: | ---: |",
    ]
    lines.extend(f"| {kind} | {count:,} | {size:,} |" for kind, count, size in by_kind)
    lines.extend(["", "## By Deck", "", "| Deck | Assets | Bytes |", "| --- | ---: | ---: |"])
    lines.extend(f"| {deck} | {count:,} | {size:,} |" for deck, count, size in by_deck)
    lines.extend(
        [
            "",
            "## Use",
            "",
            "Open `index.html` to browse visually. Query `catalog.sqlite` with `query_asset_library.py` for deterministic retrieval. Object files are stored by SHA-256 under `objects/sha256/` and should not be renamed in place.",
            "",
        ]
    )
    (output_root / "LIBRARY.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path)
    parser.add_argument("--deck", action="append", type=Path, default=[])
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--no-previews", action="store_true")
    parser.add_argument("--preview-workers", type=int, default=4)
    parser.add_argument("--max-assets-per-deck", type=int)
    parser.add_argument(
        "--rebuild-index-only",
        action="store_true",
        help="regenerate CSV, JSON, HTML, and summary from an existing catalog.sqlite",
    )
    args = parser.parse_args()

    output_root = args.output_dir.expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(output_root, 0o700)
    (output_root / "tmp").mkdir(exist_ok=True, mode=0o700)
    database = output_root / "catalog.sqlite"
    if args.rebuild_index_only:
        if not database.is_file():
            parser.error(f"catalog not found: {database}")
        connection = sqlite3.connect(database)
        try:
            payload = export_catalog(connection, output_root)
            write_browser(payload, output_root)
            write_summary(connection, output_root)
        finally:
            connection.close()
            shutil.rmtree(output_root / "tmp", ignore_errors=True)
        print(f"library index rebuilt: {output_root}")
        return 0

    decks = deck_paths(args.source_dir, args.deck)
    if not decks:
        parser.error("no readable .key decks found")
    if args.preview_workers < 1:
        parser.error("--preview-workers must be at least 1")

    connection = sqlite3.connect(database)
    try:
        create_schema(connection)
        for deck in decks:
            process_deck(
                deck,
                output_root,
                connection,
                extract=True,
                max_assets=args.max_assets_per_deck,
            )
            connection.commit()
        if not args.no_previews:
            build_previews(connection, output_root, args.preview_workers)
        payload = export_catalog(connection, output_root)
        write_browser(payload, output_root)
        write_summary(connection, output_root)
        connection.commit()
    finally:
        connection.close()
        shutil.rmtree(output_root / "tmp", ignore_errors=True)
    print(f"library complete: {output_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
