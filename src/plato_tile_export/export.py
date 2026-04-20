"""Tile export — multi-format export, streaming, field selection, dedup on export."""
import json
import csv
import io
import time
import hashlib
from dataclasses import dataclass, field
from typing import Optional, Callable, Iterator
from enum import Enum

class ExportFormat(Enum):
    JSON = "json"
    JSONL = "jsonl"
    CSV = "csv"
    MARKDOWN = "markdown"
    YAML = "yaml"

@dataclass
class ExportOptions:
    format: ExportFormat = ExportFormat.JSON
    fields: list[str] = field(default_factory=list)
    include_metadata: bool = True
    include_timestamp: bool = True
    room_filter: str = ""
    domain_filter: str = ""
    min_confidence: float = 0.0
    sort_by: str = ""
    sort_desc: bool = True
    dedup: bool = False
    limit: int = 0
    indent: int = 2

@dataclass
class ExportResult:
    format: str
    records: int
    bytes_estimate: int
    duration_ms: float
    fields: list[str] = field(default_factory=list)

@dataclass
class TileRecord:
    id: str
    content: str
    domain: str
    confidence: float
    room: str
    tags: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    metadata: dict = field(default_factory=dict)

class TileExport:
    def __init__(self):
        self._formatters: dict[str, Callable] = {
            ExportFormat.JSON.value: self._to_json,
            ExportFormat.JSONL.value: self._to_jsonl,
            ExportFormat.CSV.value: self._to_csv,
            ExportFormat.MARKDOWN.value: self._to_markdown,
            ExportFormat.YAML.value: self._to_yaml,
        }
        self._export_log: list[dict] = []

    def export(self, tiles: list[TileRecord], options: ExportOptions = None) -> str:
        options = options or ExportOptions()
        start = time.time()
        filtered = self._filter(tiles, options)
        if options.dedup:
            filtered = self._dedup(filtered)
        if options.sort_by:
            filtered = self._sort(filtered, options.sort_by, options.sort_desc)
        if options.limit > 0:
            filtered = filtered[:options.limit]
        selected = self._select_fields(filtered, options)
        formatter = self._formatters.get(options.format.value, self._to_json)
        result = formatter(selected, options)
        duration = (time.time() - start) * 1000
        self._log_export(options, len(filtered), len(result))
        return result

    def export_stream(self, tiles: list[TileRecord], options: ExportOptions = None) -> Iterator[str]:
        """Streaming export — yields one record at a time (JSONL mode)."""
        options = options or ExportOptions()
        if options.format not in (ExportFormat.JSONL, ExportFormat.CSV):
            yield self.export(tiles, options)
            return
        filtered = self._filter(tiles, options)
        if options.sort_by:
            filtered = self._sort(filtered, options.sort_by, options.sort_desc)
        if options.limit > 0:
            filtered = filtered[:options.limit]
        if options.format == ExportFormat.JSONL:
            for tile in filtered:
                record = self._tile_to_dict(tile, options)
                yield json.dumps(record) + "\n"
        elif options.format == ExportFormat.CSV:
            fields = options.fields or ["id", "content", "domain", "confidence", "room"]
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=fields, extrasaction='ignore')
            writer.writeheader()
            yield output.getvalue()
            for tile in filtered:
                record = self._tile_to_dict(tile, options)
                output = io.StringIO()
                writer = csv.DictWriter(output, fieldnames=fields, extrasaction='ignore')
                writer.writerow(record)
                yield output.getvalue()

    def import_tiles(self, data: str, format: str = "json") -> list[TileRecord]:
        """Import tiles from exported format."""
        if format == "jsonl":
            records = []
            for line in data.strip().split("\n"):
                line = line.strip()
                if line:
                    records.append(self._dict_to_tile(json.loads(line)))
            return records
        elif format == "json":
            data_list = json.loads(data)
            if isinstance(data_list, list):
                return [self._dict_to_tile(d) for d in data_list]
            return [self._dict_to_tile(data_list)]
        elif format == "csv":
            reader = csv.DictReader(io.StringIO(data))
            return [self._dict_to_tile(row) for row in reader]
        return []

    def estimate_size(self, tiles: list[TileRecord], format: ExportFormat) -> int:
        sample = json.dumps([self._tile_to_dict(t, ExportOptions()) for t in tiles[:10]])
        per_record = len(sample) / max(len(tiles[:10]), 1)
        multiplier = {"json": 1.0, "jsonl": 0.9, "csv": 0.6, "markdown": 1.3, "yaml": 0.9}
        return int(per_record * len(tiles) * multiplier.get(format.value, 1.0))

    def _filter(self, tiles: list[TileRecord], opts: ExportOptions) -> list[TileRecord]:
        result = tiles
        if opts.room_filter:
            result = [t for t in result if t.room == opts.room_filter]
        if opts.domain_filter:
            result = [t for t in result if t.domain == opts.domain_filter]
        if opts.min_confidence > 0:
            result = [t for t in result if t.confidence >= opts.min_confidence]
        return result

    def _dedup(self, tiles: list[TileRecord]) -> list[TileRecord]:
        seen_content = set()
        result = []
        for t in tiles:
            h = hashlib.md5(t.content.encode()).hexdigest()[:12]
            if h not in seen_content:
                seen_content.add(h)
                result.append(t)
        return result

    def _sort(self, tiles: list[TileRecord], sort_by: str, desc: bool) -> list[TileRecord]:
        return sorted(tiles, key=lambda t: getattr(t, sort_by, 0), reverse=desc)

    def _select_fields(self, tiles: list[TileRecord], opts: ExportOptions) -> list[dict]:
        return [self._tile_to_dict(t, opts) for t in tiles]

    def _tile_to_dict(self, tile: TileRecord, opts: ExportOptions) -> dict:
        d = {"id": tile.id, "content": tile.content, "domain": tile.domain,
             "confidence": tile.confidence, "room": tile.room, "tags": tile.tags}
        if opts.include_metadata:
            d["metadata"] = tile.metadata
        if opts.include_timestamp:
            d["created_at"] = tile.created_at
        if opts.fields:
            d = {k: v for k, v in d.items() if k in opts.fields}
        return d

    def _dict_to_tile(self, d: dict) -> TileRecord:
        return TileRecord(
            id=d.get("id", ""), content=d.get("content", ""),
            domain=d.get("domain", ""), confidence=float(d.get("confidence", 0.5)),
            room=d.get("room", ""), tags=d.get("tags", []),
            created_at=d.get("created_at", time.time()),
            metadata=d.get("metadata", {})
        )

    def _to_json(self, records: list[dict], opts: ExportOptions) -> str:
        return json.dumps(records, indent=opts.indent, ensure_ascii=False, default=str)

    def _to_jsonl(self, records: list[dict], opts: ExportOptions) -> str:
        return "\n".join(json.dumps(r, ensure_ascii=False, default=str) for r in records) + "\n"

    def _to_csv(self, records: list[dict], opts: ExportOptions) -> str:
        if not records:
            return ""
        output = io.StringIO()
        fields = opts.fields or list(records[0].keys())
        writer = csv.DictWriter(output, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        for r in records:
            writer.writerow(r)
        return output.getvalue()

    def _to_markdown(self, records: list[dict], opts: ExportOptions) -> str:
        if not records:
            return ""
        fields = opts.fields or list(records[0].keys())
        lines = ["| " + " | ".join(fields) + " |"]
        lines.append("| " + " | ".join("---" for _ in fields) + " |")
        for r in records:
            vals = [str(r.get(f, ""))[:50] for f in fields]
            lines.append("| " + " | ".join(vals) + " |")
        return "\n".join(lines)

    def _to_yaml(self, records: list[dict], opts: ExportOptions) -> str:
        lines = []
        for r in records:
            lines.append("-")
            for k, v in r.items():
                lines.append(f"  {k}: {v}")
        return "\n".join(lines)

    def _log_export(self, opts: ExportOptions, records: int, bytes_len: int):
        self._export_log.append({"format": opts.format.value, "records": records,
                                "bytes": bytes_len, "timestamp": time.time()})
        if len(self._export_log) > 500:
            self._export_log = self._export_log[-500:]

    @property
    def stats(self) -> dict:
        return {"exports": len(self._export_log),
                "formats": list(self._formatters.keys())}
