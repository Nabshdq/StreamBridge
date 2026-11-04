import QtQuick
import ".."

// One connection (TikTok, Twitch or YouTube): name, an icon AND a text label.
// Meaning is never carried by colour alone (CLAUDE.md section 9).
Rectangle {
    id: root

    property string title: ""
    property string status: "stopped"
    property string detail: ""

    readonly property var look: ({
        "connected":    { icon: "circle-check",   label: i18n.strings["ui.status.connected"] },
        "connecting":   { icon: "loader",         label: i18n.strings["ui.status.connecting"] },
        "waiting_live": { icon: "clock",          label: i18n.strings["ui.status.waiting_live"] },
        "disconnected": { icon: "triangle-alert", label: i18n.strings["ui.status.disconnected"] },
        "error":        { icon: "circle-x",       label: i18n.strings["ui.status.error"] },
        "stopped":      { icon: "square",         label: i18n.strings["ui.status.stopped"] }
    })
    readonly property var current: look[status] || look["stopped"]
    readonly property bool needsAttention: status === "error" || status === "disconnected"

    // Fixed height (the detail line is always reserved), so the dashboard does not jump
    // when a detail appears. The width is set by the dashboard: narrow when three cards
    // share one row, so the status label sits on its own line below the title.
    implicitHeight: Theme.space1 * 2 + content.implicitHeight
    implicitWidth: 240
    radius: Theme.radiusMedium
    color: Theme.surface

    Column {
        id: content
        anchors.fill: parent
        anchors.leftMargin: Theme.space2
        anchors.rightMargin: Theme.space2
        anchors.topMargin: Theme.space1
        anchors.bottomMargin: Theme.space1
        spacing: Theme.space1 / 2

        Item {
            width: parent.width
            height: Theme.iconSize
            Text {
                anchors.left: parent.left
                anchors.right: icon.left
                anchors.rightMargin: Theme.space1
                anchors.verticalCenter: parent.verticalCenter
                text: root.title
                elide: Text.ElideRight
                font.family: Theme.fontFamily
                font.pixelSize: Theme.labelSize
                font.weight: Theme.weightMedium
                color: Theme.textSecondary
            }
            SvgIcon {
                id: icon
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                name: root.current.icon
                color: root.needsAttention ? Theme.attention : Theme.text
            }
        }
        Text {
            width: parent.width
            text: root.current.label
            wrapMode: Text.Wrap
            font.family: Theme.fontFamily
            font.pixelSize: Theme.bodySize
            font.weight: Theme.weightSemiBold
            color: Theme.text
        }
        Text {
            width: parent.width
            text: root.detail !== "" ? root.detail : " "
            elide: Text.ElideRight
            font.family: Theme.fontFamily
            font.pixelSize: Theme.captionSize
            color: Theme.textSecondary
        }
    }
}
