pragma Singleton
import QtQuick

// Theme.qml: the ONLY place where colours, fonts and spacing are defined.
// Every other QML file reads from here (CLAUDE.md section 9).
//
// Palette (dark theme), split by role:
//   PRIMARY    the neutral surfaces and the text on them. Most of the screen.
//   SECONDARY  quieter text and borders that support the primary colours.
//   ACCENT     one single teal, used ONLY for the Start button.
//   SUPPORTING one amber for "needs attention". It is always paired with an
//              icon and a label, never shown as colour alone.
QtObject {
    id: theme

    // ---- Primary: surfaces (darkest to lightest) ----
    readonly property color canvas: "#0E1116"       // window background
    readonly property color surface: "#171B22"      // cards and the side menu
    readonly property color raised: "#222833"       // inputs, selected menu item

    // ---- Primary: text ----
    readonly property color text: "#F1F3F6"         // 17:1 on canvas
    // Not named "onAccent": QML reads property names starting with "on" as signal handlers.
    readonly property color textOnAccent: "#04211D" // text on the accent colour

    // ---- Secondary: supporting text and lines ----
    readonly property color textSecondary: "#A3ADBB" // 7.6:1 on surface (AA)
    readonly property color borderSubtle: "#2A313C"  // decorative separation only
    readonly property color borderStrong: "#6B7585"  // 3.7:1, for controls (AA, 3:1)

    // ---- Accent: Start button only ----
    readonly property color accent: "#2DD4BF"
    readonly property color accentHover: "#5EEAD4"

    // ---- Supporting: attention ----
    readonly property color attention: "#F5B544"

    // ---- Fonts: Inter for everything (one family, three weights) ----
    readonly property string fontFamily: "Inter"
    readonly property int weightRegular: Font.Normal
    readonly property int weightMedium: Font.Medium
    readonly property int weightSemiBold: Font.DemiBold

    // Text styles as pixel size / line height pairs.
    // Same-type elements always use the same style (section 9).
    readonly property int displaySize: 32
    readonly property int displayLine: 40
    readonly property int titleSize: 24
    readonly property int titleLine: 32
    readonly property int headingSize: 18
    readonly property int headingLine: 24
    readonly property int bodySize: 16
    readonly property int bodyLine: 24
    readonly property int labelSize: 14
    readonly property int labelLine: 20
    readonly property int captionSize: 13
    readonly property int captionLine: 18

    // ---- Spacing: multiples of 8 px ----
    readonly property int space1: 8
    readonly property int space2: 16
    readonly property int space3: 24
    readonly property int space4: 32
    readonly property int space6: 48

    // ---- Corner radius ----
    readonly property int radiusSmall: 8
    readonly property int radiusMedium: 12
    readonly property int radiusLarge: 16

    // ---- Sizes ----
    readonly property int touchTarget: 44           // minimum height of clickable things
    readonly property int iconSize: 24
    readonly property int focusWidth: 2             // keyboard focus ring
    readonly property int sidebarWidth: 240
}
