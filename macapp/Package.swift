// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "Untangle",
    platforms: [
        .macOS(.v13)
    ],
    targets: [
        .executableTarget(
            name: "Untangle",
            path: "Sources/Untangle"
        )
    ]
)
