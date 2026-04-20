"""Multi-format tile exporter."""
import json
import csv
import io
from dataclasses import dataclass
from typing import Optional

@dataclass
class ExportOptions:
    format: str = "json"
    include_metadata: bool = True
    fields: list[str] = None
    indent: int = 2

class TileExporter:
    def __init__(self, options: ExportOptions = None):
        self.options = options or ExportOptions()

    def export(self, tiles: list[dict], fmt: str = "") -> str:
        fmt = fmt or self.options.format
        if fmt == "json":
            return self.to_json(tiles)
        elif fmt == "csv":
            return self.to_csv(tiles)
        elif fmt == "markdown":
            return self.to_markdown(tiles)
        elif fmt == "compact":
            return self.to_compact(tiles)
        else:
            return self.to_json(tiles)

    def to_json(self, tiles: list[dict]) -> str:
        if self.options.fields:
            tiles = [{k: t.get(k) for k in self.options.fields if k in t} for t in tiles]
        return json.dumps(tiles, indent=self.options.indent, default=str)

    def to_csv(self, tiles: list[dict]) -> str:
        if not tiles:
            return ""
        fields = self.options.fields or list(tiles[0].keys())
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        for tile in tiles:
            row = {k: tile.get(k, "") for k in fields}
            writer.writerow(row)
        return output.getvalue()

    def to_markdown(self, tiles: list[dict]) -> str:
        if not tiles:
            return "# No tiles to export\n"
        fields = self.options.fields or ["id", "content", "domain", "confidence", "priority"]
        lines = ["# Tile Export\n"]
        lines.append(f"**Total: {len(tiles)} tiles**\n")
        for tile in tiles:
            lines.append(f"## {tile.get('id', 'unknown')}\n")
            for f in fields:
                if f != "id":
                    val = tile.get(f, "")
                    lines.append(f"- **{f}**: {val}")
            lines.append("")
        return "\n".join(lines)

    def to_compact(self, tiles: list[dict]) -> str:
        lines = []
        for t in tiles:
            parts = [t.get("id", "?"), t.get("domain", "?"), str(t.get("confidence", 0)),
                     t.get("priority", "?"), str(t.get("content", ""))[:60]]
            lines.append("|".join(parts))
        return "\n".join(lines)

    def export_batch(self, tiles: list[dict], formats: list[str] = None) -> dict[str, str]:
        formats = formats or ["json", "csv", "markdown"]
        return {fmt: self.export(tiles, fmt) for fmt in formats}
