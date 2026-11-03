import QtQuick
import QtQuick.Layouts
import ".."
import "../components"

// Version, links, the log folder and the license.
Item {
    id: root

    required property var settings

    ColumnLayout {
        x: Theme.space4
        y: Theme.space4
        width: Math.min(parent.width - Theme.space4 * 2, Theme.contentWidth)
        spacing: Theme.space3

        Text {
            text: i18n.strings["ui.about.title"]
            font.family: Theme.fontFamily
            font.pixelSize: Theme.titleSize
            font.weight: Theme.weightSemiBold
            color: Theme.text
        }

        SectionCard {
            title: "StreamBridge"

            Text {
                Layout.fillWidth: true
                text: i18n.strings["ui.about.tagline"]
                wrapMode: Text.Wrap
                font.family: Theme.fontFamily
                font.pixelSize: Theme.bodySize
                color: Theme.text
            }
            Text {
                text: i18n.strings["ui.about.version"].replace("%1", () => root.settings.appVersion)
                font.family: Theme.fontFamily
                font.pixelSize: Theme.bodySize
                color: Theme.textSecondary
            }
            Text {
                text: i18n.strings["ui.about.license"]
                font.family: Theme.fontFamily
                font.pixelSize: Theme.bodySize
                color: Theme.textSecondary
            }

            Flow {
                Layout.fillWidth: true
                spacing: Theme.space1

                SecondaryButton {
                    text: i18n.strings["ui.about.github"]
                    iconName: "external-link"
                    onClicked: root.settings.openUrl(root.settings.githubUrl)
                }
                SecondaryButton {
                    text: i18n.strings["ui.about.guide"]
                    iconName: "external-link"
                    onClicked: root.settings.openUrl(root.settings.githubUrl + "#readme")
                }
                SecondaryButton {
                    text: i18n.strings["ui.about.logs"]
                    iconName: "external-link"
                    onClicked: root.settings.openLogFolder()
                }
            }
        }
    }
}
