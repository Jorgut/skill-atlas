import Cocoa

struct HelperConfig: Decodable {
    let registry: String
    let interval: Double?
    let dirty_min_files: Int?
}

struct Registry: Decodable {
    let projects: [String]
}

struct SyncItem {
    let path: String
    let branch: String
    let hasUpstream: Bool
    let ahead: Int
    let behind: Int
    let dirty: Int
    let detached: Bool
    let warnings: [String]
}

struct SkippedItem {
    let project: String
    let reason: String
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    private var statusItem: NSStatusItem!
    private var timer: Timer?
    private var config: HelperConfig?
    private var items: [SyncItem] = []
    private var skippedItems: [SkippedItem] = []
    private var lastError: String?
    private var refreshing = false
    private var promptedForAccess = false

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.accessory)
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        statusItem.button?.title = "SA"
        statusItem.button?.toolTip = "Skill Atlas sync monitor"
        statusItem.menu = NSMenu()
        NSApp.activate(ignoringOtherApps: true)
        loadConfig()
        refresh()
        schedule()
    }

    private func configPath() -> URL {
        let base = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        return base.appendingPathComponent("Skill Atlas/helper.json")
    }

    private func loadConfig() {
        do {
            let data = try Data(contentsOf: configPath())
            config = try JSONDecoder().decode(HelperConfig.self, from: data)
        } catch {
            lastError = "Missing helper config: \(error.localizedDescription)"
        }
    }

    private func schedule() {
        let seconds = max(60.0, config?.interval ?? 900.0)
        timer?.invalidate()
        timer = Timer.scheduledTimer(withTimeInterval: seconds, repeats: true) { [weak self] _ in
            self?.refresh()
        }
    }

    private func git(_ project: String, _ arguments: [String]) -> (Int32, String) {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/git")
        process.arguments = ["-C", project] + arguments
        let pipe = Pipe()
        let err = Pipe()
        process.standardOutput = pipe
        process.standardError = err
        do {
            try process.run()
        } catch {
            return (127, error.localizedDescription)
        }
        process.waitUntilExit()
        let out = String(data: pipe.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
        let errOut = String(data: err.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
        return (process.terminationStatus, out.isEmpty ? errOut : out)
    }

    private func worktrees(_ project: String) -> (paths: [String], error: String?) {
        let (code, output) = git(project, ["worktree", "list", "--porcelain"])
        guard code == 0 else { return ([], output.trimmingCharacters(in: .whitespacesAndNewlines)) }
        let paths = output.split(separator: "\n").compactMap { line -> String? in
            guard line.hasPrefix("worktree ") else { return nil }
            return String(line.dropFirst("worktree ".count))
        }
        return (paths.isEmpty ? [project] : paths, nil)
    }

    private func status(_ path: String) -> SyncItem? {
        let branchResult = git(path, ["symbolic-ref", "--short", "HEAD"])
        let detached = branchResult.0 != 0
        let branch = detached ? "DETACHED" : branchResult.1.trimmingCharacters(in: .whitespacesAndNewlines)
        let upstreamResult = git(path, ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"])
        let hasUpstream = upstreamResult.0 == 0
        var ahead = 0
        var behind = 0
        if hasUpstream {
            let upstream = upstreamResult.1.trimmingCharacters(in: .whitespacesAndNewlines)
            let counts = git(path, ["rev-list", "--left-right", "--count", "\(upstream)...HEAD"])
            if counts.0 == 0 {
                let parts = counts.1.split(whereSeparator: { $0.isWhitespace })
                if parts.count == 2 {
                    behind = Int(parts[0]) ?? 0
                    ahead = Int(parts[1]) ?? 0
                }
            }
        }
        let statusResult = git(path, ["status", "--porcelain=v1", "--untracked-files=all"])
        let dirty = statusResult.0 == 0 ? statusResult.1.split(separator: "\n").filter { line in
            !line.hasPrefix("?? .agent-state/") && !line.hasPrefix(" M .agent-state/")
        }.count : 0
        let threshold = max(1, config?.dirty_min_files ?? 20)
        var warnings: [String] = []
        if detached { warnings.append("detached HEAD") }
        if !hasUpstream { warnings.append("no upstream") }
        if ahead > 0 { warnings.append("\(ahead) unpushed commit(s)") }
        if behind > 0 { warnings.append("behind remote by \(behind) commit(s)") }
        if dirty >= threshold { warnings.append("\(dirty) uncommitted change(s)") }
        guard !warnings.isEmpty else { return nil }
        return SyncItem(path: path, branch: branch, hasUpstream: hasUpstream,
                        ahead: ahead, behind: behind, dirty: dirty,
                        detached: detached, warnings: warnings)
    }

    private func collect() -> ([SyncItem], [SkippedItem], String?) {
        guard let config = config else { return ([], [], lastError) }
        do {
            let data = try Data(contentsOf: URL(fileURLWithPath: config.registry))
            let registry = try JSONDecoder().decode(Registry.self, from: data)
            var found: [SyncItem] = []
            var skipped: [SkippedItem] = []
            for project in registry.projects {
                let wt = worktrees(project)
                if let error = wt.error {
                    skipped.append(SkippedItem(project: project, reason: error))
                    continue
                }
                for path in wt.paths {
                    if let item = status(path) { found.append(item) }
                }
            }
            return (found, skipped, nil)
        } catch {
            return ([], [], "Cannot read registry: \(error.localizedDescription)")
        }
    }

    private func refresh() {
        guard !refreshing else { return }
        refreshing = true
        DispatchQueue.global(qos: .utility).async { [weak self] in
            guard let self = self else { return }
            let result = self.collect()
            DispatchQueue.main.async {
                self.items = result.0
                self.skippedItems = result.1
                self.lastError = result.2
                self.refreshing = false
                self.render()
            }
        }
    }

    private func render() {
        let count = items.count
        let unreadable = lastError != nil || !skippedItems.isEmpty
        statusItem.button?.title = count > 0 ? "SA \(count)" : (unreadable ? "SA !" : "SA")
        statusItem.button?.toolTip = count > 0
            ? "\(count) repository/worktree issue(s)"
            : (lastError ?? (skippedItems.isEmpty ? "Skill Atlas: all clean" : "\(skippedItems.count) project(s) need file access"))
        let menu = NSMenu()
        menu.autoenablesItems = false
        let title = NSMenuItem(title: "Skill Atlas Sync Monitor", action: nil, keyEquivalent: "")
        title.isEnabled = false
        menu.addItem(title)
        if let error = lastError {
            let item = NSMenuItem(title: error, action: nil, keyEquivalent: "")
            item.isEnabled = false
            menu.addItem(item)
        }
        for item in items {
            let label = "\(URL(fileURLWithPath: item.path).lastPathComponent) · \(item.branch): \(item.warnings.joined(separator: ", "))"
            let entry = NSMenuItem(title: label, action: nil, keyEquivalent: "")
            let submenu = NSMenu()
            let openTerminal = NSMenuItem(title: "Open in Terminal", action: #selector(openInTerminal(_:)), keyEquivalent: "")
            openTerminal.target = self
            openTerminal.representedObject = item.path
            submenu.addItem(openTerminal)
            let openFinder = NSMenuItem(title: "Open in Finder", action: #selector(openInFinder(_:)), keyEquivalent: "")
            openFinder.target = self
            openFinder.representedObject = item.path
            submenu.addItem(openFinder)
            entry.submenu = submenu
            menu.addItem(entry)
        }
        if items.isEmpty && lastError == nil && skippedItems.isEmpty {
            let item = NSMenuItem(title: "All clean", action: nil, keyEquivalent: "")
            item.isEnabled = false
            menu.addItem(item)
        }
        if !skippedItems.isEmpty && !promptedForAccess {
            promptedForAccess = true
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.4) { [weak self] in
                self?.grantFileAccess()
            }
        }
        if !skippedItems.isEmpty {
            menu.addItem(NSMenuItem.separator())
            for skipped in skippedItems {
                let entry = NSMenuItem(title: "Cannot read \(URL(fileURLWithPath: skipped.project).lastPathComponent): \(skipped.reason)", action: nil, keyEquivalent: "")
                entry.isEnabled = false
                menu.addItem(entry)
            }
            let privacy = NSMenuItem(title: "Open Privacy settings…", action: #selector(openPrivacy), keyEquivalent: "")
            privacy.target = self
            menu.addItem(privacy)
        }
        let grantItem = NSMenuItem(title: "Grant file access…", action: #selector(grantAccess), keyEquivalent: "g")
        grantItem.target = self
        menu.addItem(grantItem)
        menu.addItem(NSMenuItem.separator())
        let refreshItem = NSMenuItem(title: "Refresh now", action: #selector(refreshNow), keyEquivalent: "r")
        refreshItem.target = self
        menu.addItem(refreshItem)
        let registryItem = NSMenuItem(title: "Open registry", action: #selector(openRegistry), keyEquivalent: "o")
        registryItem.target = self
        menu.addItem(registryItem)
        menu.addItem(NSMenuItem.separator())
        let quitItem = NSMenuItem(title: "Quit Skill Atlas Notify", action: #selector(quit), keyEquivalent: "q")
        quitItem.target = self
        menu.addItem(quitItem)
        statusItem.menu = menu
    }

    @objc private func grantAccess() { grantFileAccess() }

    private func grantFileAccess() {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.allowsMultipleSelection = true
        panel.message = "Choose the folder(s) that contain your registered repositories (for example Documents)."
        panel.prompt = "Allow"
        if panel.runModal() == .OK {
            refresh()
        }
    }

    @objc private func refreshNow() { refresh() }

    @objc private func openPrivacy() {
        if let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_FilesAndFolders") {
            NSWorkspace.shared.open(url)
        }
    }

    @objc private func openRegistry() {
        guard let config = config else { return }
        NSWorkspace.shared.open(URL(fileURLWithPath: config.registry))
    }

    @objc private func openInTerminal(_ sender: NSMenuItem) {
        guard let path = sender.representedObject as? String else { return }
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/open")
        process.arguments = ["-a", "Terminal", path]
        try? process.run()
    }

    @objc private func openInFinder(_ sender: NSMenuItem) {
        guard let path = sender.representedObject as? String else { return }
        NSWorkspace.shared.open(URL(fileURLWithPath: path))
    }

    @objc private func quit() { NSApp.terminate(nil) }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.run()
