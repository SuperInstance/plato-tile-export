"""Tile export — JSON, JSONL, CSV, Markdown, and custom format export."""
import json
import csv
import io
import time
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum

class ExportFormat(Enum):
    JSON = "json"
    JSONL = "jsonl"
    CSV = "csv"
    MARKDOWN = "markdown"
    CUSTOM = "custom"

@dataclass
class ExportResult:
    format: str
    size_bytes: int
    tile_count: int
    duration_ms: float = 0.0
    path: str = ""

class TileExporter:
    def __init__(self, default_fields: list[str] = None):
        self.default_fields = default_fields or ["id", "content", "domain", "confidence", "created_at"]
        self._export_history: list[dict] = []

    def export_json(self, tiles: list[dict], fields: list[str] = None,
                    indent: int = 2) -> ExportResult:
        start = time.time()
        fields = fields or self.default_fields
        filtered = [self._filter(t, fields) for t in tiles]
        output = json.dumps(filtered, indent=indent, default=str)
        result = ExportResult(format="json", size_bytes=len(output.encode()),
                            tile_count=len(filtered), duration_ms=(time.time() - start) * 1000)
        self._log(result)
        return result

    def export_jsonl(self, tiles: list[dict], fields: list[str] = None) -> ExportResult:
        start = time.time()
        fields = fields or self.default_fields
        lines = []
        for t in tiles:
            lines.append(json.dumps(self._filter(t, fields), default=str))
        output = "\n".join(lines) + "\n"
        result = ExportResult(format="jsonl", size_bytes=len(output.encode()),
                            tile_count=len(tiles), duration_ms=(time.time() - start) * 1000)
        self._log(result)
        return result

    def export_csv(self, tiles: list[dict], fields: list[str] = None) -> ExportResult:
        start = time.time()
        fields = fields or self.default_fields
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for t in tiles:
            row = {f: t.get(f, "") for f in fields}
            writer.writerow(row)
        content = output.getvalue()
        result = ExportResult(format="csv", size_bytes=len(content.encode()),
                            tile_count=len(tiles), duration_ms=(time.time() - start) * 1000)
        self._log(result)
        return result

    def export_markdown(self, tiles: list[dict], fields: list[str] = None,
                        title: str = "Tile Export") -> ExportResult:
        start = time.time()
        fields = fields or self.default_fields
        lines = [f"# {title}", f"_Exported {len(tiles)} tiles_", ""]
        # Table header
        lines.append("| " + " | ".join(fields) + " |")
        lines.append("| " + " | ".join(["---"] * len(fields)) + " |")
        for t in tiles:
            row = [str(t.get(f, ""))[:50] for f in fields]
            lines.append("| " + " | ".join(row) + " |")
        output = "\n".join(lines)
        result = ExportResult(format="markdown", size_bytes=len(output.encode()),
                            tile_count=len(tiles), duration_ms=(time.time() - start) * 1000)
        self._log(result)
        return result

    def export_custom(self, tiles: list[dict], template: str, fields: list[str] = None) -> ExportResult:
        """Export using a custom template string with {field} placeholders."""
        start = time.time()
        fields = fields or self.default_fields
        lines = []
        for t in tiles:
            filtered = self._filter(t, fields)
            try:
                lines.append(template.format(**filtered))
            except KeyError:
                safe = {k: filtered.get(k, "") for k in fields}
                lines.append(template.format(**safe))
        output = "\n".join(lines)
        result = ExportResult(format="custom", size_bytes=len(output.encode()),
                            tile_count=len(tiles), duration_ms=(time.time() - start) * 1000)
        self._log(result)
        return result

    def to_file(self, tiles: list[dict], path: str, fmt: str = "json", **kwargs) -> ExportResult:
        exporters = {"json": self.export_json, "jsonl": self.export_jsonl,
                    "csv": self.export_csv, "markdown": self.export_markdown}
        exporter = exporters.get(fmt, self.export_json)
        result = exporter(tiles, **kwargs)
        with open(path, "w") as f:
            if fmt == "json":
                json.dump([self._filter(t, kwargs.get("fields", self.default_fields)) for t in tiles], f, indent=2)
            elif fmt == "jsonl":
                for t in tiles:
                    f.write(json.dumps(self._filter(t, kwargs.get("fields", self.default_fields)), default=str) + "\n")
            elif fmt == "csv":
                f.write(result.to_string() if hasattr(result, 'to_string') else "")
        result.path = path
        return result

    def _filter(self, tile: dict, fields: list[str]) -> dict:
        return {f: tile.get(f, "") for f in fields}

    def _log(self, result: ExportResult):
        self._export_history.append({"format": result.format, "tiles": result.tile_count,
                                     "size_bytes": result.size_bytes, "duration_ms": result.duration_ms,
                                     "timestamp": time.time()})
        if len(self._export_history) > 100:
            self._export_history = self._export_history[-100:]

    @property
    def stats(self) -> dict:
        total_bytes = sum(e["size_bytes"] for e in self._export_history)
        return {"exports": len(self._export_history), "total_bytes": total_bytes,
                "total_tiles": sum(e["tiles"] for e in self._export_history)}
