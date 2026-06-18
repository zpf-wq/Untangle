import SwiftUI
import AppKit

@main
struct UntangleApp: App {
    var body: some Scene {
        WindowGroup("Untangle") {
            ContentView()
                .frame(minWidth: 560, minHeight: 640)
        }
        .windowResizability(.contentMinSize)
    }
}

struct ContentView: View {
    @StateObject private var runner = PipelineRunner()

    // 项目目录持久化(.venv 与 cli.py 所在目录)
    @AppStorage("projectDir") private var projectDir = "/Users/zhangpengfei/Untangle"
    @AppStorage("outputDir") private var outputDir = ""

    @State private var audioPath = ""
    @State private var separateFirst = true
    @State private var selectedStems: Set<String> = ["other"]

    @State private var onset = 0.5
    @State private var frame = 0.3
    @State private var minNote = 21.0
    @State private var maxNote = 108.0
    @State private var showAdvanced = false

    private let allStems = ["drums", "bass", "vocals", "other"]

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                header

                groupBox("① 项目与音频") {
                    pathRow(title: "项目目录", value: projectDir, isDir: true) { picked in
                        projectDir = picked
                    }
                    pathRow(title: "音频文件", value: audioPath.isEmpty ? "（未选择）" : audioPath, isDir: false) { picked in
                        audioPath = picked
                    }
                    pathRow(title: "输出目录", value: effectiveOutputDir, isDir: true) { picked in
                        outputDir = picked
                    }
                }

                groupBox("② 处理选项") {
                    Toggle("先分轨(关闭则直接对整首转 MIDI)", isOn: $separateFirst)
                    if separateFirst {
                        Text("选择要转 MIDI 的轨道:")
                            .font(.subheadline).foregroundStyle(.secondary)
                        HStack(spacing: 16) {
                            ForEach(allStems, id: \.self) { stem in
                                Toggle(stem, isOn: Binding(
                                    get: { selectedStems.contains(stem) },
                                    set: { on in
                                        if on { selectedStems.insert(stem) }
                                        else { selectedStems.remove(stem) }
                                    }
                                ))
                                .toggleStyle(.checkbox)
                            }
                        }
                        Text("不勾选任何轨道也可以,届时只分轨、不转 MIDI。")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                }

                DisclosureGroup("③ 高级参数(可选)", isExpanded: $showAdvanced) {
                    VStack(alignment: .leading, spacing: 10) {
                        sliderRow("onset 阈值", value: $onset, range: 0...1, step: 0.05,
                                  hint: "越高音符越保守")
                        sliderRow("frame 阈值", value: $frame, range: 0...1, step: 0.05, hint: "")
                        sliderRow("最低音符(MIDI)", value: $minNote, range: 0...127, step: 1,
                                  hint: "21 = A0")
                        sliderRow("最高音符(MIDI)", value: $maxNote, range: 0...127, step: 1,
                                  hint: "108 = C8")
                    }
                    .padding(.top, 6)
                }
                .padding(.horizontal, 4)

                runSection

                if let err = runner.errorText {
                    errorBox(err)
                }

                if !runner.stems.isEmpty || !runner.midis.isEmpty {
                    resultsSection
                }
            }
            .padding(20)
        }
    }

    // MARK: - 子视图

    private var header: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("🎵 Untangle").font(.largeTitle).bold()
            Text("本地音频分轨(Demucs)+ 转 MIDI(basic-pitch),全程离线运行。")
                .font(.subheadline).foregroundStyle(.secondary)
        }
    }

    private var runSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                if runner.isRunning {
                    Button(role: .destructive) { runner.cancel() } label: {
                        Label("取消", systemImage: "stop.fill")
                    }
                } else {
                    Button {
                        startRun()
                    } label: {
                        Label("开始处理", systemImage: "play.fill")
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.large)
                    .disabled(audioPath.isEmpty)
                }
            }

            if runner.isRunning || runner.progress > 0 {
                ProgressView(value: runner.progress)
                Text(runner.statusText)
                    .font(.callout).foregroundStyle(.secondary)
            }
        }
    }

    private var resultsSection: some View {
        groupBox("产物") {
            if !runner.stems.isEmpty {
                Text("分轨 WAV").font(.headline)
                ForEach(runner.stems) { fileRow($0) }
            }
            if !runner.midis.isEmpty {
                Text("MIDI 文件").font(.headline).padding(.top, 4)
                ForEach(runner.midis) { fileRow($0) }
            }
        }
    }

    private func fileRow(_ f: OutputFile) -> some View {
        HStack {
            Image(systemName: f.kind == "MIDI" ? "pianokeys" : "waveform")
                .foregroundStyle(.secondary)
            VStack(alignment: .leading, spacing: 1) {
                Text("\(f.label) · \(f.kind)").font(.callout)
                Text((f.path as NSString).lastPathComponent)
                    .font(.caption).foregroundStyle(.secondary)
            }
            Spacer()
            Button("在 Finder 中显示") {
                NSWorkspace.shared.activateFileViewerSelecting([URL(fileURLWithPath: f.path)])
            }
            .controlSize(.small)
        }
        .padding(.vertical, 2)
    }

    private func errorBox(_ msg: String) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Label("出错了", systemImage: "exclamationmark.triangle.fill")
                .foregroundStyle(.red).font(.headline)
            ScrollView {
                Text(msg).font(.system(.caption, design: .monospaced))
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .textSelection(.enabled)
            }
            .frame(maxHeight: 160)
        }
        .padding(12)
        .background(Color.red.opacity(0.08))
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }

    // MARK: - 复用控件

    private func groupBox<Content: View>(_ title: String,
                                         @ViewBuilder content: () -> Content) -> some View {
        GroupBox(label: Text(title).font(.headline)) {
            VStack(alignment: .leading, spacing: 8) {
                content()
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.top, 4)
        }
    }

    private func pathRow(title: String, value: String, isDir: Bool,
                         onPick: @escaping (String) -> Void) -> some View {
        HStack {
            Text(title).frame(width: 70, alignment: .leading)
            Text(value).font(.caption).foregroundStyle(.secondary)
                .lineLimit(1).truncationMode(.middle)
                .frame(maxWidth: .infinity, alignment: .leading)
            Button("选择…") {
                if let p = pickPath(directory: isDir) { onPick(p) }
            }
            .controlSize(.small)
        }
    }

    private func sliderRow(_ title: String, value: Binding<Double>,
                           range: ClosedRange<Double>, step: Double,
                           hint: String) -> some View {
        HStack {
            Text(title).frame(width: 130, alignment: .leading).font(.callout)
            Slider(value: value, in: range, step: step)
            Text(step >= 1 ? String(Int(value.wrappedValue)) : String(format: "%.2f", value.wrappedValue))
                .font(.system(.caption, design: .monospaced))
                .frame(width: 44, alignment: .trailing)
            if !hint.isEmpty {
                Text(hint).font(.caption2).foregroundStyle(.secondary).frame(width: 60, alignment: .leading)
            }
        }
    }

    // MARK: - 逻辑

    private var effectiveOutputDir: String {
        if !outputDir.isEmpty { return outputDir }
        return (projectDir as NSString).appendingPathComponent("out")
    }

    private func startRun() {
        let config = RunConfig(
            projectDir: projectDir,
            audioPath: audioPath,
            outputDir: effectiveOutputDir,
            separateFirst: separateFirst,
            stems: allStems.filter { selectedStems.contains($0) },
            onsetThreshold: onset,
            frameThreshold: frame,
            minNote: Int(minNote),
            maxNote: Int(maxNote)
        )
        runner.run(config)
    }

    /// 弹出系统文件选择面板。directory=true 选目录,否则选音频文件。
    private func pickPath(directory: Bool) -> String? {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = directory
        panel.canChooseFiles = !directory
        panel.allowsMultipleSelection = false
        if !directory {
            panel.allowedContentTypes = []   // 不强限制类型,允许 wav/mp3/flac/m4a 等
        }
        return panel.runModal() == .OK ? panel.url?.path : nil
    }
}
