import Foundation

/// 一个产物文件(分轨 WAV 或 MIDI),用于在界面列表中展示与「在 Finder 中显示」。
struct OutputFile: Identifiable, Hashable {
    let id = UUID()
    let label: String   // 例如 "other" / "bass" / "full"
    let kind: String    // "WAV" / "MIDI"
    let path: String
}

/// 运行配置,由界面收集后传给 PipelineRunner。
struct RunConfig {
    var projectDir: String
    var audioPath: String
    var outputDir: String
    var separateFirst: Bool
    var stems: [String]
    var onsetThreshold: Double
    var frameThreshold: Double
    var minNote: Int
    var maxNote: Int
}

/// 负责调用 `.venv/bin/python cli.py --json`,
/// 解析逐行 JSON 进度/结果,并把状态发布给 SwiftUI 界面。
final class PipelineRunner: ObservableObject {
    @Published var isRunning = false
    @Published var progress: Double = 0          // 0~1
    @Published var statusText = "就绪"
    @Published var stems: [OutputFile] = []
    @Published var midis: [OutputFile] = []
    @Published var errorText: String? = nil

    private var process: Process?
    private var stdoutBuffer = Data()
    private let newline = UInt8(ascii: "\n")
    private var stderrTail = ""   // 保留 stderr 末尾,出错时辅助展示

    /// 开始一次处理。线程安全:UI 更新都派发回主线程。
    func run(_ config: RunConfig) {
        guard !isRunning else { return }

        let pythonPath = (config.projectDir as NSString)
            .appendingPathComponent(".venv/bin/python")
        let cliPath = (config.projectDir as NSString)
            .appendingPathComponent("cli.py")

        guard FileManager.default.fileExists(atPath: pythonPath) else {
            self.errorText = "找不到 Python 解释器:\(pythonPath)\n请确认项目目录正确,且已按 README 创建 .venv 虚拟环境。"
            return
        }
        guard FileManager.default.fileExists(atPath: cliPath) else {
            self.errorText = "找不到 cli.py:\(cliPath)\n请确认项目目录设置正确。"
            return
        }

        // 重置状态
        isRunning = true
        progress = 0
        statusText = "启动中…"
        stems = []
        midis = []
        errorText = nil
        stdoutBuffer = Data()
        stderrTail = ""

        // 组装命令行参数
        var args = ["cli.py", config.audioPath, "--output", config.outputDir, "--json"]
        if config.separateFirst {
            let joined = config.stems.joined(separator: ",")
            // 即使没勾选轨道,也允许只分轨不转 MIDI(stems 传空字符串)
            args += ["--stems", joined]
        } else {
            args += ["--no-separate"]
        }
        args += ["--onset-threshold", String(config.onsetThreshold)]
        args += ["--frame-threshold", String(config.frameThreshold)]
        args += ["--min-note", String(config.minNote)]
        args += ["--max-note", String(config.maxNote)]

        let proc = Process()
        proc.executableURL = URL(fileURLWithPath: pythonPath)
        proc.arguments = args
        proc.currentDirectoryURL = URL(fileURLWithPath: config.projectDir)

        let outPipe = Pipe()
        let errPipe = Pipe()
        proc.standardOutput = outPipe
        proc.standardError = errPipe

        // stdout:逐行 JSON
        outPipe.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            guard !data.isEmpty else { return }
            self?.handleStdout(data)
        }

        // stderr:进度条/警告/traceback,留作出错时展示
        errPipe.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            guard !data.isEmpty, let s = String(data: data, encoding: .utf8) else { return }
            DispatchQueue.main.async {
                // 只保留末尾约 4000 字符,避免无限增长
                self?.stderrTail = String(((self?.stderrTail ?? "") + s).suffix(4000))
            }
        }

        proc.terminationHandler = { [weak self] p in
            DispatchQueue.main.async {
                self?.finish(exitCode: p.terminationStatus)
            }
        }

        self.process = proc
        do {
            try proc.run()
        } catch {
            isRunning = false
            errorText = "无法启动处理进程:\(error.localizedDescription)"
        }
    }

    /// 取消正在运行的处理。
    func cancel() {
        process?.terminate()
    }

    // MARK: - 私有

    private func handleStdout(_ data: Data) {
        // 累积到缓冲,按换行切分;UI 更新回主线程
        DispatchQueue.main.async {
            self.stdoutBuffer.append(data)
            while let idx = self.stdoutBuffer.firstIndex(of: self.newline) {
                let lineData = self.stdoutBuffer.subdata(in: self.stdoutBuffer.startIndex..<idx)
                self.stdoutBuffer.removeSubrange(self.stdoutBuffer.startIndex...idx)
                if let line = String(data: lineData, encoding: .utf8) {
                    self.parseEvent(line)
                }
            }
        }
    }

    private func parseEvent(_ line: String) {
        let trimmed = line.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty,
              let jsonData = trimmed.data(using: .utf8),
              let obj = try? JSONSerialization.jsonObject(with: jsonData) as? [String: Any],
              let type = obj["type"] as? String
        else { return }

        switch type {
        case "progress":
            if let f = obj["fraction"] as? Double { progress = f }
            if let d = obj["desc"] as? String, !d.isEmpty { statusText = d }
        case "result":
            if let s = obj["stems"] as? [String: String] {
                stems = s.sorted { $0.key < $1.key }.map {
                    OutputFile(label: $0.key, kind: "WAV", path: $0.value)
                }
            }
            if let m = obj["midis"] as? [String: String] {
                midis = m.sorted { $0.key < $1.key }.map {
                    OutputFile(label: $0.key, kind: "MIDI", path: $0.value)
                }
            }
            progress = 1
            statusText = "处理完成 ✅"
        case "error":
            errorText = (obj["message"] as? String) ?? "未知错误"
        default:
            break
        }
    }

    private func finish(exitCode: Int32) {
        isRunning = false
        process = nil
        if exitCode != 0 && errorText == nil {
            // 没有结构化错误但退出码非 0,展示 stderr 末尾辅助排查
            let tail = stderrTail.trimmingCharacters(in: .whitespacesAndNewlines)
            errorText = "处理失败(退出码 \(exitCode))。\n\(tail.isEmpty ? "" : "\n详情:\n\(tail)")"
        }
        if errorText != nil {
            statusText = "处理失败 ❌"
        }
    }
}
