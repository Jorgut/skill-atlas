import Cocoa

struct HelperConfig: Decodable {
    let python: String
    let cli: String
    let registry: String
    let state: String
    let log: String
    let interval: Double
}

struct SyncItem: Decodable {
    let path: String
    let branch: String
    let has_upstream: Bool
    let ahead: Int
    let behind: Int
    let dirty: Int
    let detached: Bool
    let warnings: [String]
}

struct SyncResult: Decodable {
    let status: String
    let notified: [SyncItem]
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    private var statusItem: NSStatusItem!
    private var timer: Timer?
    private var config: HelperConfig?
    private var items: [SyncItem] = []
    private var lastError: String?
    private var refreshing = false

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.accessory)
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        statusItem.button?.title = "SA"
        statusItem.button?.toolTip = "Skill Atlas sync monitor"
        statusItem.menu = NSMenu()
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

    private func refresh() {
        guard !refreshing else { return }
        guard let config = config else {
            render()
            return
        }
        refreshing = true
        let process = Process()
        process.executableURL = URL(fileURLWithPath: config.python)
        process.arguments = [
            config.cli, "sync", "notify",
            "--registry", config.registry,
            "--channel", "json",
            "--min-interval", "0",
            "--idle-minutes", "0",
            "--state", config.state,
            "--log", config.log,
        ]
        let pipe = Pipe()
        let errPipe = Pipe()
        process.standardOutput = pipe
        process.standardError = errPipe
        process.terminationHandler = { [weak self] proc in
            let out = pipe.fileHandleForReading.readDataToEndOfFile()
            let err = errPipe.fileHandleForReading.readDataToEndOfFile()
            DispatchQueue.main.async {
                guard let self = self else { return }
                self.refreshing = false
                if proc.terminationStatus != 0 {
                    self.lastError = String(data: err, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? "sync notify failed"
                    self.items = []
                } else if let result = try? JSONDecoder().decode(SyncResult.self, from: out) {
                    self.items = result.notified
                    self.lastError = nil
                } else {
                    self.lastError = "Could not decode sync notify output"
                    self.items = []
                }
                self.render()
            }
        }
        do {
            try process.run()
        } catch {
            refreshing = false
            lastError = error.localizedDescription
            render()
        }
    }

    private func render() {
        let count = items.count
        statusItem.button?.title = count > 0 ? "SA \(count)" : (lastError == nil ? "SA" : "SA !")
        statusItem.button?.toolTip = count > 0 ? "\(count) repository/worktree issue(s)" : (lastError ?? "Skill Atlas: all clean")
        let menu = NSMenu()
        menu.autoenablesItems = false
        let title = NSMenuItem(title: "Skill Atlas Sync Monitor", action: nil, keyEquivalent: "")
        title.isEnabled = false
        menu.addItem(title)
        if let error = lastError {
            let item = NSMenuItem(title: "Error: \(error)", action: nil, keyEquivalent: "")
            item.isEnabled = false
            menu.addItem(item)
        } else if items.isEmpty {
            let item = NSMenuItem(title: "All clean", action: nil, keyEquivalent: "")
            item.isEnabled = false
            menu.addItem(item)
        } else {
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
        }
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

    @objc private func refreshNow() {
        refresh()
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

    @objc private func quit() {
        NSApp.terminate(nil)
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.run()
