import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"
import "pages"

ApplicationWindow {
    id: window

    width: 1120
    height: 720
    minimumWidth: 800
    minimumHeight: 560
    visible: true
    title: "StreamBridge"
    color: Theme.canvas

    // Index of the page shown on the right.
    property int page: 0

    RowLayout {
        anchors.fill: parent
        spacing: 0

        // ---- Side menu ----
        Rectangle {
            Layout.fillHeight: true
            Layout.preferredWidth: Theme.sidebarWidth
            color: Theme.surface

            Column {
                anchors.fill: parent
                anchors.margins: Theme.space2
                spacing: Theme.space1

                Text {
                    text: "StreamBridge"
                    height: Theme.touchTarget + Theme.space1
                    verticalAlignment: Text.AlignVCenter
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.headingSize
                    font.weight: Theme.weightSemiBold
                    color: Theme.text
                }

                Repeater {
                    model: [
                        { label: qsTr("Dashboard"), icon: "layout-dashboard" },
                        { label: qsTr("Settings"), icon: "settings" },
                        { label: qsTr("About"), icon: "info" }
                    ]
                    delegate: ItemDelegate {
                        id: item
                        required property var modelData
                        required property int index
                        width: parent.width
                        height: Theme.touchTarget
                        focusPolicy: Qt.StrongFocus
                        onClicked: window.page = index

                        contentItem: Row {
                            spacing: Theme.space2
                            leftPadding: Theme.space1
                            SvgIcon {
                                anchors.verticalCenter: parent.verticalCenter
                                name: item.modelData.icon
                                color: Theme.text
                            }
                            Text {
                                anchors.verticalCenter: parent.verticalCenter
                                text: item.modelData.label
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.bodySize
                                font.weight: window.page === item.index
                                             ? Theme.weightSemiBold : Theme.weightRegular
                                color: Theme.text
                            }
                        }
                        background: Rectangle {
                            radius: Theme.radiusSmall
                            color: window.page === item.index ? Theme.raised : "transparent"
                            border.width: item.activeFocus ? Theme.focusWidth : 0
                            border.color: Theme.text
                        }
                    }
                }
            }
        }

        // ---- Pages ----
        StackLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            currentIndex: window.page

            Dashboard { bridge: backend }

            // Settings and About are filled in during Phase 6.
            Placeholder { title: qsTr("Settings") }
            Placeholder { title: qsTr("About") }
        }
    }

    component Placeholder: Item {
        id: placeholder
        property string title: ""
        Text {
            anchors.centerIn: parent
            text: qsTr("%1 is coming soon.").arg(placeholder.title)
            font.family: Theme.fontFamily
            font.pixelSize: Theme.bodySize
            color: Theme.textSecondary
        }
    }
}
