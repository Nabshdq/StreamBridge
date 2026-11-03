"""Serves the Lucide icons to QML in any colour.

QML asks for ``image://icons/<name>/<rrggbb>``. The icon files are white; this
provider swaps the white for the requested colour and draws the SVG. Doing it in
Python keeps icons crisp at any size and needs no GPU shader effects.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QByteArray, QSize
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtQuick import QQuickImageProvider
from PySide6.QtSvg import QSvgRenderer

WHITE = "#FFFFFF"
DEFAULT_SIZE = 24


class IconProvider(QQuickImageProvider):
    """Image provider registered under the name ``icons``."""

    def __init__(self, icon_dir: Path) -> None:
        """Create the provider.

        Args:
            icon_dir: Folder with the white ``<name>.svg`` files.
        """
        super().__init__(QQuickImageProvider.ImageType.Image)
        self._icon_dir = icon_dir

    def requestImage(self, image_id: str, size: QSize, requested_size: QSize) -> QImage:
        """Draw icon ``name/rrggbb`` at the requested size (transparent if unknown)."""
        name, _, hex_color = image_id.partition("/")
        width = requested_size.width() if requested_size.width() > 0 else DEFAULT_SIZE
        height = requested_size.height() if requested_size.height() > 0 else DEFAULT_SIZE
        image = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(0)
        svg_file = self._icon_dir / f"{Path(name).name}.svg"
        if svg_file.is_file():
            colour = QColor(f"#{hex_color}") if hex_color else QColor(WHITE)
            if not colour.isValid():
                colour = QColor(WHITE)
            svg = svg_file.read_text(encoding="utf-8").replace(WHITE, colour.name())
            renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
            painter = QPainter(image)
            renderer.render(painter)
            painter.end()
        size.setWidth(width)
        size.setHeight(height)
        return image
