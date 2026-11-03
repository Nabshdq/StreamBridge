"""Tests for the QML design tokens (CLAUDE.md section 9: contrast and 8 px grid)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtCore import QUrl  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtQml import QQmlComponent, QQmlEngine  # noqa: E402

QML_DIR = Path(__file__).resolve().parents[1] / "src" / "streambridge" / "ui" / "qml"
FONT_DIR = Path(__file__).resolve().parents[1] / "resources" / "fonts"
ICON_DIR = Path(__file__).resolve().parents[1] / "resources" / "icons"


@pytest.fixture(scope="module")
def theme():
    """Load Theme.qml through a real QML engine and return the singleton object."""
    app = QGuiApplication.instance() or QGuiApplication([])
    engine = QQmlEngine()
    engine.addImportPath(str(QML_DIR.parent))
    component = QQmlComponent(engine)
    component.setData(
        b'import QtQuick\nimport "' + QUrl.fromLocalFile(str(QML_DIR)).toString().encode() + b'"\n'
        b"Item { property var t: Theme }",
        QUrl("file:///theme_test.qml"),
    )
    obj = component.create()
    assert obj is not None, [e.toString() for e in component.errors()]
    yield obj.property("t")
    del obj, engine, app


def _luminance(color) -> float:
    """Relative luminance of a QColor (WCAG 2.x)."""

    def channel(value: float) -> float:
        return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4

    return (
        0.2126 * channel(color.redF())
        + 0.7152 * channel(color.greenF())
        + 0.0722 * channel(color.blueF())
    )


def contrast(a, b) -> float:
    """WCAG contrast ratio between two QColors."""
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


@pytest.mark.parametrize("background", ["canvas", "surface", "raised"])
@pytest.mark.parametrize("foreground", ["text", "textSecondary"])
def test_text_has_normal_text_contrast(theme, foreground, background):
    assert contrast(theme.property(foreground), theme.property(background)) >= 4.5


@pytest.mark.parametrize("background", ["canvas", "surface", "raised"])
def test_control_borders_have_non_text_contrast(theme, background):
    assert contrast(theme.property("borderStrong"), theme.property(background)) >= 3.0


def test_text_on_accent_has_normal_text_contrast(theme):
    assert contrast(theme.property("textOnAccent"), theme.property("accent")) >= 4.5


def test_accent_stands_out_from_the_surfaces(theme):
    assert contrast(theme.property("accent"), theme.property("canvas")) >= 3.0
    assert contrast(theme.property("attention"), theme.property("surface")) >= 3.0


@pytest.mark.parametrize("name", ["space1", "space2", "space3", "space4", "space6"])
def test_spacing_is_a_multiple_of_eight(theme, name):
    assert theme.property(name) % 8 == 0


def test_touch_target_is_at_least_44px(theme):
    assert theme.property("touchTarget") >= 44


def test_bundled_fonts_and_licenses_exist():
    names = ("Inter-Regular.ttf", "Inter-Medium.ttf", "Inter-SemiBold.ttf", "Inter-LICENSE.txt")
    for name in names:
        assert (FONT_DIR / name).is_file(), name
    assert (ICON_DIR / "LUCIDE-LICENSE.txt").is_file()
