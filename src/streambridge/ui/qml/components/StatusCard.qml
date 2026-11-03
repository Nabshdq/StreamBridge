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
        "connected":    { icon: "circle-check",   label: qsTr("Connected") },
        "connecting":   { icon: "loader",         label: qsTr("Connecting") },
        "waiting_live": { icon: "clock",          label: qsTr("Waiting for LIVE") },
        "disconnected": { icon: "triangle-alert", label: qsTr("Disconnected") },
        "error":        { icon: "circle-x",       label: qsTr("Problem") },
        "stopped":      { icon: "square",         label: qsTr("Stopped") }
    })
    readonly property var current: look[status] || look["stopped"]
    readonly property bool needsAttention: status === "error" || status === "disconnected"

    implicitHeight: 96
    implicitWidth: 240
    radius: Theme.radiusMedium
    color: Theme.surface

    Column {
        anchors.fill: parent
        anchors.margins: Theme.space2
        spacing: Theme.space1 / 2

        Text {
            text: root.title
            font.family: Theme.fontFamily
            font.pixelSize: Theme.labelSize
            font.weight: Theme.weightMedium
            color: Theme.textSecondary
        }
        Row {
            spacing: Theme.space1
            SvgIcon {
                anchors.verticalCenter: parent.verticalCenter
                name: root.current.icon
                color: root.needsAttention ? Theme.attention : Theme.text
            }
            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: root.current.label
                font.family: Theme.fontFamily
                font.pixelSize: Theme.headingSize
                font.weight: Theme.weightSemiBold
                color: Theme.text
            }
        }
        Text {
            width: parent.width
            text: root.detail
            visible: root.detail !== ""
            elide: Text.ElideRight
            font.family: Theme.fontFamily
            font.pixelSize: Theme.captionSize
            color: Theme.textSecondary
        }
    }
}
