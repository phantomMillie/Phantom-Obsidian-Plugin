import Cocoa
import SpriteKit

// TODO Pile — 할 일이 블록이 되어 바탕화면(폴더 아이콘 위, 앱 창 아래)에 떨어져 기울고 구르며 쌓인다.
// 할 일 = 글자 카드(급할수록 글자가 크다, 길면 여러 줄), 메아리 = 글자 없는 작은 블록. 오래될수록 · 마감이 다가오거나 지날수록
// · 중요할수록 카드가 커지고 메아리가 늘어 더 높이 쌓인다. 끝낸 할 일의 카드는 빠지고 위가 무너져 내려앉는다.
// 왼쪽 클릭 = 잡고 끌기(던지기), 오른쪽 클릭 = Claude 로 해결 · 완료 · 마감 정하기. 블록 밖 클릭은 바탕화면으로 통과한다.
// 메뉴바 = 할 일 목록 · 할 일 추가 · 블록 보이기 켜고 끄기.
// 읽고 쓰는 곳: vault 의 최신 `3. Resources/07. TODO/YYYY-MM-DD.md`
//   - [ ] ⏭ 09-13 🔸 [프로젝트] 내용 · ❗상 · 📅 2026-10-20 · ↻1

let home = FileManager.default.homeDirectoryForCurrentUser.path
let env = ProcessInfo.processInfo.environment

let cal = Calendar.current
let iso: DateFormatter = {
    let f = DateFormatter()
    f.locale = Locale(identifier: "en_US_POSIX"); f.calendar = Calendar(identifier: .gregorian); f.dateFormat = "yyyy-MM-dd"
    return f
}()
func today() -> Date { cal.startOfDay(for: Date()) }
func days(_ a: Date, _ b: Date) -> Int { cal.dateComponents([.day], from: cal.startOfDay(for: a), to: cal.startOfDay(for: b)).day ?? 0 }

/// vault_record.py 위치 — 레포(plugin/scripts) → 예전 자리(scripts) → 플러그인 캐시 중 가장 최근.
func vaultRecordPath() -> String {
    let fm = FileManager.default
    for c in [home + "/.phantom-obsidian/plugin/scripts/vault_record.py", home + "/.phantom-obsidian/scripts/vault_record.py"] where fm.fileExists(atPath: c) { return c }
    let cache = home + "/.claude/plugins/cache"
    let found = (fm.enumerator(atPath: cache)?.compactMap { $0 as? String } ?? [])
        .filter { $0.hasSuffix("scripts/vault_record.py") }.map { cache + "/" + $0 }
        .max { ((try? fm.attributesOfItem(atPath: $0)[.modificationDate] as? Date) ?? .distantPast) ?? .distantPast
             < ((try? fm.attributesOfItem(atPath: $1)[.modificationDate] as? Date) ?? .distantPast) ?? .distantPast }
    return found ?? home + "/.phantom-obsidian/plugin/scripts/vault_record.py"
}

func vaultPath() -> String {
    if let v = env["PHANTOM_VAULT"] { return v }
    if let d = FileManager.default.contents(atPath: home + "/.phantom-obsidian/config.json"),
       let j = try? JSONSerialization.jsonObject(with: d) as? [String: Any],
       let v = j["vault"] as? String { return (v as NSString).expandingTildeInPath }
    return home + "/.phantom-obsidian/vault"
}

func latestTodoFile() -> String? {
    if let f = env["PILE_TODO_FILE"] { return f }
    let dir = vaultPath() + "/3. Resources/07. TODO"
    let names = ((try? FileManager.default.contentsOfDirectory(atPath: dir)) ?? [])
        .filter { $0.range(of: #"^\d{4}-\d{2}-\d{2}\.md$"#, options: .regularExpression) != nil }.sorted()
    return names.last.map { dir + "/" + $0 }
}

func capture(_ s: String, _ pattern: String) -> String? {
    guard let re = try? NSRegularExpression(pattern: pattern),
          let m = re.firstMatch(in: s, range: NSRange(s.startIndex..., in: s)), m.numberOfRanges > 1,
          let r = Range(m.range(at: 1), in: s) else { return nil }
    return String(s[r])
}

func stripMarkers(_ s: String) -> String {
    s.replacingOccurrences(of: #"\s*·\s*(❗(상|중|하)|📅\s*\d{4}-\d{2}-\d{2}|↻\d+|🗑[^·]*)"#, with: "", options: .regularExpression)
}

struct Item {
    let raw: String
    let origin: Date
    let project: String?
    let text: String
    let importance: String?
    let due: Date?
    let postponed: Int
    var jiraKey: String? = nil     // Jira 이슈면 키 (TECHCLIENT-1815)
    var status: String? = nil      // Jira 상태 (진행 중 …)
    var age: Int { days(origin, today()) }
    var late: Int? { due.map { days($0, today()) } }   // >0 지남, 0 오늘, <0 남음
}

func parseLine(_ l: String, fileDate: Date) -> Item? {
    guard l.hasPrefix("- [ ] ") else { return nil }
    var body = String(l.dropFirst(6))
    var origin = fileDate
    if let mm = capture(body, #"^⏭\s*(\d{2})-\d{2}"#), let dd = capture(body, #"^⏭\s*\d{2}-(\d{2})"#),
       let m = Int(mm), let d = Int(dd) {
        var c = cal.dateComponents([.year], from: today()); c.month = m; c.day = d
        if var o = cal.date(from: c) {
            if o > today() { o = cal.date(byAdding: .year, value: -1, to: o)! }
            origin = o
        }
        body = body.replacingOccurrences(of: #"^⏭\s*\d{2}-\d{2}\s*"#, with: "", options: .regularExpression)
    }
    for e in ["⚡", "🔸", "🧱"] where body.hasPrefix(e) { body = String(body.dropFirst()).trimmingCharacters(in: .whitespaces) }
    var project: String? = nil
    if body.hasPrefix("["), let close = body.firstIndex(of: "]") {
        project = String(body[body.index(after: body.startIndex)..<close])
        body = String(body[body.index(after: close)...]).trimmingCharacters(in: .whitespaces)
    }
    return Item(raw: l, origin: origin, project: project, text: stripMarkers(body),
                importance: capture(body, #"·\s*❗(상|중|하)"#),
                due: capture(body, #"·\s*📅\s*(\d{4}-\d{2}-\d{2})"#).flatMap { iso.date(from: $0) },
                postponed: Int(capture(body, #"·\s*↻(\d+)"#) ?? "") ?? 0)
}

func loadItems() -> [Item] {
    guard let f = latestTodoFile(), let text = try? String(contentsOfFile: f, encoding: .utf8) else { return [] }
    let stem = ((f as NSString).lastPathComponent as NSString).deletingPathExtension
    let fd = iso.date(from: stem) ?? today()
    return text.components(separatedBy: "\n").compactMap { parseLine($0, fileDate: fd) }
}

// ── 압박 ────────────────────────────────────────────────────
/// 클수록 급하다. 중요도 + 묵은 날(주 단위) + 마감(지남이면 하루마다 2) + 미룬 횟수.
func pressure(_ it: Item) -> CGFloat {
    var p: CGFloat = ["상": 3, "중": 2, "하": 1][it.importance ?? ""] ?? 1.5
    p += CGFloat(it.age) / 7
    if let late = it.late {
        if late > 0 { p += 3 + CGFloat(late) * 2 } else if late == 0 { p += 3 } else if late >= -2 { p += 1 }
    }
    return p + CGFloat(it.postponed)
}

/// 같이 떨어지는 메아리 블록 수. 마감 지나면 하루마다 3개, 아니면 열흘마다 1개.
func echoes(_ it: Item) -> Int {
    if let late = it.late, late > 0 { return min(late * 3, 30) }
    if it.jiraKey != nil { return 0 }      // Jira 는 마감 지났을 때만 쌓인다
    return min(it.age / 10, 8)
}

func meta(_ it: Item) -> String {
    var m: [String] = []
    if let late = it.late { m.append(late > 0 ? "마감 \(late)일 지남" : late == 0 ? "오늘 마감" : "마감 \(-late)일 남음") }
    else { m.append("마감 없음") }
    m.append("\(it.age)일째")
    if let i = it.importance { m.append("중요도 \(i)") }
    if it.postponed > 0 { m.append("\(it.postponed)번 미룸") }
    return m.joined(separator: " · ")
}

/// 줄 원문으로 정해지는 난수 — 다시 읽어도 블록 자리가 안 튄다.
struct Rng {
    var s: UInt64
    init(_ text: String) { s = 1469598103934665603; for b in text.utf8 { s = (s ^ UInt64(b)) &* 1099511628211 } }
    mutating func next() -> CGFloat {
        s &+= 0x9E3779B97F4A7C15
        var z = s; z = (z ^ (z >> 30)) &* 0xBF58476D1CE4E5B9; z = (z ^ (z >> 27)) &* 0x94D049BB133111EB
        return CGFloat(z ^ (z >> 31)) / CGFloat(UInt64.max)
    }
}

// ── TODO 파일에 쓰기 ────────────────────────────────────────
/// 파일을 다시 읽어 같은 줄을 찾아 바꾼다. 그 사이 배치가 파일을 바꿨으면 false.
func rewrite(_ raw: String, _ f: (String) -> String) -> Bool {
    guard let path = latestTodoFile(), let text = try? String(contentsOfFile: path, encoding: .utf8) else { return false }
    var lines = text.components(separatedBy: "\n")
    guard let i = lines.firstIndex(of: raw) else { return false }
    lines[i] = f(lines[i])
    return (try? lines.joined(separator: "\n").write(toFile: path, atomically: true, encoding: .utf8)) != nil
}
func markDone(_ l: String) -> String { "- [x]" + l.dropFirst(5) }
func withMarkers(_ l: String, importance: String, due: Date, postponed: Int) -> String {
    stripMarkers(l) + " · ❗\(importance) · 📅 \(iso.string(from: due))" + (postponed > 0 ? " · ↻\(postponed)" : "")
}

// ── 설정 (보이기 · 프로젝트별 코드 폴더) ──────────────────────
struct Prefs: Codable {
    var visible = true
    var dirs: [String: String] = [:]     // 프로젝트 → Claude 를 열 코드 폴더
    var lastProject = ""
    var jiraSite: String? = nil      // millietown.atlassian.net
    var jiraEmail: String? = nil
    var jiraShow: [String]? = nil    // 블록으로 떨어뜨릴 Jira 상태 (없으면 기본값)
    var colors: [String: [Double]]? = nil   // 프로젝트 → [색상(0~1), 밝기 단계(0·1)] — 한 번 정하면 안 바뀐다
}
let jiraShowDefault = ["할 일", "해야 할 일", "진행 중", "PROGRESS"]
let prefsFile = home + "/.phantom-obsidian/state/todo-pile.json"
func loadPrefs() -> Prefs {
    guard let d = FileManager.default.contents(atPath: prefsFile), let p = try? JSONDecoder().decode(Prefs.self, from: d) else { return Prefs() }
    return p
}
func savePrefs(_ p: Prefs) {
    try? FileManager.default.createDirectory(atPath: (prefsFile as NSString).deletingLastPathComponent, withIntermediateDirectories: true)
    try? JSONEncoder().encode(p).write(to: URL(fileURLWithPath: prefsFile))
}

func vaultProjects() -> [String] {
    let dir = vaultPath() + "/1. Projects"
    return ((try? FileManager.default.contentsOfDirectory(atPath: dir)) ?? [])
        .filter { var d: ObjCBool = false; return FileManager.default.fileExists(atPath: dir + "/" + $0, isDirectory: &d) && d.boolValue && !$0.hasPrefix(".") }
        .map { $0.replacingOccurrences(of: #"^\d+\.\s*"#, with: "", options: .regularExpression) }.sorted()
}

// ── Jira (나한테 할당된 미완료 이슈) ─────────────────────────
// 토큰은 키체인(서비스 todo-pile-jira, 계정 = 이메일), 사이트·이메일은 설정 파일. 마지막 결과는 state/jira-cache.json
let jiraService = "todo-pile-jira"
let jiraCache = home + "/.phantom-obsidian/state/jira-cache.json"

func keychainGet(_ account: String) -> String? {
    let q: [String: Any] = [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: jiraService,
                            kSecAttrAccount as String: account, kSecReturnData as String: true]
    var out: CFTypeRef?
    guard SecItemCopyMatching(q as CFDictionary, &out) == errSecSuccess, let d = out as? Data else { return nil }
    return String(data: d, encoding: .utf8)
}
func keychainSet(_ account: String, _ secret: String) {
    let base: [String: Any] = [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: jiraService, kSecAttrAccount as String: account]
    SecItemDelete(base as CFDictionary)
    var add = base; add[kSecValueData as String] = Data(secret.utf8)
    SecItemAdd(add as CFDictionary, nil)
}

func jiraRequest(site: String, email: String, token: String, path: String, query: [URLQueryItem]) -> URLRequest? {
    var c = URLComponents(); c.scheme = "https"; c.host = site; c.path = path; c.queryItems = query.isEmpty ? nil : query
    guard let u = c.url else { return nil }
    var r = URLRequest(url: u, timeoutInterval: 20)
    r.setValue("Basic " + Data("\(email):\(token)".utf8).base64EncodedString(), forHTTPHeaderField: "Authorization")
    r.setValue("application/json", forHTTPHeaderField: "Accept")
    return r
}

let jiraISO: ISO8601DateFormatter = { let f = ISO8601DateFormatter(); f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]; return f }()
func jiraDate(_ s: String?) -> Date? {
    guard let s = s else { return nil }
    let fixed = s.replacingOccurrences(of: #"([+-]\d{2})(\d{2})$"#, with: "$1:$2", options: .regularExpression)   // +0900 → +09:00
    return jiraISO.date(from: fixed) ?? ISO8601DateFormatter().date(from: fixed)
}

/// Jira 응답(JSON) → 블록용 항목.
func jiraItems(_ data: Data, site: String) -> [Item]? {
    guard let j = try? JSONSerialization.jsonObject(with: data) as? [String: Any], let issues = j["issues"] as? [[String: Any]] else { return nil }
    return issues.compactMap { i in
        guard let key = i["key"] as? String, let f = i["fields"] as? [String: Any] else { return nil }
        let pri = ((f["priority"] as? [String: Any])?["name"] as? String) ?? ""
        let imp: String? = ["Highest": "상", "High": "상", "Medium": "중", "Low": "하", "Lowest": "하"][pri]
        return Item(raw: "jira:" + key, origin: jiraDate(f["created"] as? String) ?? today(),
                    project: ((f["project"] as? [String: Any])?["key"] as? String) ?? "Jira",
                    text: "\(key) " + ((f["summary"] as? String) ?? ""), importance: imp,
                    due: (f["duedate"] as? String).flatMap { iso.date(from: $0) }, postponed: 0,
                    jiraKey: key, status: (f["status"] as? [String: Any])?["name"] as? String)
    }
}

/// 캐시의 전체 Jira 항목 (상태 거르기 전).
func jiraAll() -> [Item] {
    guard let d = FileManager.default.contents(atPath: jiraCache), let site = loadPrefs().jiraSite else { return [] }
    return jiraItems(d, site: site) ?? []
}
/// 고른 상태만.
func loadJiraCache() -> [Item] {
    let show = Set(loadPrefs().jiraShow ?? jiraShowDefault)
    return jiraAll().filter { show.contains($0.status ?? "") }
}

/// 나한테 할당된 미완료 이슈를 가져와 캐시에 쓴다. 결과(성공 여부, 알림 말)는 메인 스레드로.
func fetchJira(_ done: @escaping (Bool, String) -> Void) {
    let pr = loadPrefs()
    guard let site = pr.jiraSite, let email = pr.jiraEmail, let token = keychainGet(email),
          let req = jiraRequest(site: site, email: email, token: token, path: "/rest/api/3/search/jql", query: [
              URLQueryItem(name: "jql", value: "assignee = currentUser() AND statusCategory != Done ORDER BY updated DESC"),
              URLQueryItem(name: "fields", value: "summary,status,project,issuetype,duedate,priority,created,updated"),
              URLQueryItem(name: "maxResults", value: "100")]) else { done(false, "Jira 연결 안 됨"); return }
    URLSession.shared.dataTask(with: req) { data, resp, err in
        let code = (resp as? HTTPURLResponse)?.statusCode ?? 0
        DispatchQueue.main.async {
            guard let data = data, code == 200, let items = jiraItems(data, site: site) else {
                plog("jira 실패 \(code) \(err?.localizedDescription ?? "")"); done(false, "Jira 응답 \(code)"); return
            }
            try? data.write(to: URL(fileURLWithPath: jiraCache))
            plog("jira \(items.count)건"); done(true, "Jira \(items.count)건")
        }
    }.resume()
}

// ── 블록 ────────────────────────────────────────────────────
// 프로젝트마다 한 색 (빨강은 마감 경고용으로 비워 둔다)
/// 프로젝트 색 — 새 프로젝트가 생기면 이미 쓰는 색들과 색상환에서 가장 먼 색을 고른다.
/// 빨강 근처는 마감 경고용으로 비워 두고, 색상이 가까운 이웃과는 밝기 단계를 달리 한다. 한 번 정한 색은 설정에 남아 안 바뀐다.
func hueGap(_ a: Double, _ b: Double) -> Double { let d = abs(a - b).truncatingRemainder(dividingBy: 1); return min(d, 1 - d) }
func projectColors(_ projects: [String]) -> [String: NSColor] {
    var pr = loadPrefs()
    var tab = pr.colors ?? [:]
    var changed = false
    for p in Set(projects).sorted() where tab[p] == nil {
        let used = tab.values.map { $0[0] }
        var best = 0.58, bestGap = used.isEmpty ? 2.0 : -1.0       // 첫 색은 파랑
        for i in 0..<360 {
            let h = Double(i) / 360
            if h < 0.04 || h > 0.94 { continue }                    // 빨강 · 진분홍 근처 비움
            let gap = used.map { hueGap($0, h) }.min() ?? 1
            if gap > bestGap { bestGap = gap; best = h }
        }
        let near = tab.values.min { hueGap($0[0], best) < hueGap($1[0], best) }
        tab[p] = [best, near.map { 1 - $0[1] } ?? 0]
        changed = true
    }
    if changed { pr.colors = tab; savePrefs(pr) }
    return tab.mapValues { v in
        NSColor(calibratedHue: v[0], saturation: v[1] == 0 ? 0.78 : 0.62, brightness: v[1] == 0 ? 0.80 : 0.60, alpha: 1)
    }
}
func luminance(_ c: NSColor) -> CGFloat { let x = c.usingColorSpace(.deviceRGB) ?? c; return 0.3 * x.redComponent + 0.59 * x.greenComponent + 0.11 * x.blueComponent }

let alert = NSColor(srgbRed: 0.95, green: 0.23, blue: 0.25, alpha: 1)
let shadowPad: CGFloat = 6

struct Spec {
    let key: String           // 줄 원문 + "#메아리번호"
    let raw: String
    let size: CGSize          // 몸체 크기 (그림자 여백 뺀 것)
    let color: NSColor
    let title: String?
    let sub: String?
    let font: CGFloat
    let textW: CGFloat        // 글자 줄바꿈 폭
    let badge: String?        // "오늘" · "D+3"
    var primary: Bool { title != nil }
}

func fonts(_ f: CGFloat) -> (NSFont, NSFont) {
    (NSFont.systemFont(ofSize: f, weight: .semibold), NSFont.systemFont(ofSize: max(9, f * 0.66), weight: .medium))
}
func titleSize(_ t: String, _ f: NSFont, _ w: CGFloat) -> CGSize {
    let b = (t as NSString).boundingRect(with: NSSize(width: w, height: 10_000), options: [.usesLineFragmentOrigin, .usesFontLeading], attributes: [.font: f])
    return CGSize(width: ceil(b.width), height: ceil(b.height))
}

/// 할 일 = 글자 카드 (급할수록 글자가 크고, 길면 줄을 바꿔 카드가 커진다), 메아리 = 글자 없는 작은 블록.
func makeSpec(_ it: Item, echo: Int, k: CGFloat, color: NSColor) -> Spec {
    let key = it.raw + "#\(echo)"
    var r = Rng(key)
    if echo > 0 {
        let u = 16 * k
        let shapes: [(CGFloat, CGFloat)] = [(1, 1), (2, 1), (1, 2), (3, 1), (2, 2), (1.5, 1)]
        let sh = shapes[Int(r.next() * CGFloat(shapes.count)) % shapes.count]
        return Spec(key: key, raw: it.raw, size: CGSize(width: sh.0 * u, height: sh.1 * u), color: color,
                    title: nil, sub: nil, font: 0, textW: 0, badge: nil)
    }
    let p = pressure(it)
    let f = min(24, max(12, 11 + p * 0.85)) * k
    let (f1, f2) = fonts(f)
    var subParts = [it.project ?? "미분류"] + (it.status.map { [$0] } ?? []) + ["\(it.age)일째"]
    if it.due == nil { subParts.append("마감 없음") } else if let late = it.late, late < 0 { subParts.append("마감 \(-late)일 남음") }
    if let i = it.importance { subParts.append("중요도 \(i)") }
    if it.postponed > 0 { subParts.append("\(it.postponed)번 미룸") }
    let sub = subParts.joined(separator: " · ")
    let badge: String? = it.late.flatMap { $0 > 0 ? "D+\($0)" : ($0 == 0 ? "오늘" : nil) }
    let padX = f * 0.9, padY = f * 0.55
    let badgeW: CGFloat = badge == nil ? 0 : (badge! as NSString).size(withAttributes: [.font: f2]).width + f * 1.2
    let ts = titleSize(it.text, f1, 420 * k)
    let subW = (sub as NSString).size(withAttributes: [.font: f2]).width
    let textW = max(ts.width, subW)
    let h = ts.height + (f2.ascender - f2.descender) + f * 0.3 + padY * 2
    return Spec(key: key, raw: it.raw, size: CGSize(width: ceil(textW + padX * 2 + badgeW), height: ceil(h)), color: color,
                title: it.text, sub: sub, font: f, textW: max(ts.width, 1), badge: badge)
}

/// 둥근 카드 + 은은한 위쪽 빛 + 그림자. 메아리는 같은 색을 어둡고 반투명하게.
func texture(_ s: Spec) -> SKTexture {
    let px: CGFloat = 2
    let W = s.size.width + shadowPad * 2, H = s.size.height + shadowPad * 2
    let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: Int(W * px), pixelsHigh: Int(H * px), bitsPerSample: 8,
                               samplesPerPixel: 4, hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
    rep.size = NSSize(width: W, height: H)
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
    let body = NSRect(x: shadowPad, y: shadowPad, width: s.size.width, height: s.size.height)
    let radius = s.primary ? min(14, s.font * 0.9) : min(6, min(s.size.width, s.size.height) * 0.25)
    let path = NSBezierPath(roundedRect: body, xRadius: radius, yRadius: radius)
    NSGraphicsContext.saveGraphicsState()
    let sh = NSShadow(); sh.shadowColor = NSColor(white: 0, alpha: s.primary ? 0.35 : 0.25); sh.shadowBlurRadius = 5; sh.shadowOffset = NSSize(width: 0, height: -2); sh.set()
    let base = s.primary ? s.color : (s.color.blended(withFraction: 0.35, of: .black) ?? s.color).withAlphaComponent(0.78)
    base.setFill(); path.fill()
    NSGraphicsContext.restoreGraphicsState()
    let top = (s.color.blended(withFraction: 0.22, of: .white) ?? s.color).withAlphaComponent(s.primary ? 1 : 0.78)
    NSGradient(starting: top, ending: base)?.draw(in: path, angle: -90)
    NSColor(white: 1, alpha: 0.18).setStroke(); let edge = NSBezierPath(roundedRect: body.insetBy(dx: 0.5, dy: 0.5), xRadius: radius, yRadius: radius); edge.lineWidth = 1; edge.stroke()
    if let title = s.title, let sub = s.sub {
        let ink = luminance(s.color) > 0.62 ? NSColor(calibratedWhite: 0.08, alpha: 1) : NSColor.white
        let (f1, f2) = fonts(s.font)
        let padX = s.font * 0.9, padY = s.font * 0.55
        let line2 = f2.ascender - f2.descender
        (sub as NSString).draw(at: NSPoint(x: body.minX + padX, y: body.minY + padY),
                               withAttributes: [.font: f2, .foregroundColor: ink.withAlphaComponent(0.72)])
        let ts = titleSize(title, f1, s.textW + 1)
        // draw(in:) 은 뒤집히지 않은 좌표에서도 위에서부터 줄을 내려 쓴다
        (title as NSString).draw(in: NSRect(x: body.minX + padX, y: body.minY + padY + line2 + s.font * 0.3, width: s.textW + 1, height: ts.height + 2),
                                 withAttributes: [.font: f1, .foregroundColor: ink])
        if let badge = s.badge {
            let bw = (badge as NSString).size(withAttributes: [.font: f2]).width + s.font * 0.7, bh = line2 + 4
            let br = NSRect(x: body.maxX - padX * 0.6 - bw, y: body.maxY - padY * 0.7 - bh, width: bw, height: bh)
            alert.setFill(); NSBezierPath(roundedRect: br, xRadius: bh / 2, yRadius: bh / 2).fill()
            (badge as NSString).draw(at: NSPoint(x: br.minX + s.font * 0.35, y: br.minY + 2),
                                     withAttributes: [.font: NSFont.systemFont(ofSize: f2.pointSize, weight: .bold), .foregroundColor: NSColor.white])
            alert.setStroke(); let o = NSBezierPath(roundedRect: body.insetBy(dx: 1, dy: 1), xRadius: radius, yRadius: radius); o.lineWidth = 2; o.stroke()
        }
    }
    NSGraphicsContext.restoreGraphicsState()
    return SKTexture(cgImage: rep.cgImage!)
}

// ── 판 ──────────────────────────────────────────────────────
/// 문제 추적용 기록 (state/todo-pile.log, 200KB 넘으면 비운다)
func plog(_ m: String) {
    let f = home + "/.phantom-obsidian/state/todo-pile.log"
    let line = "\(Date()) \(m)\n"
    if let a = try? FileManager.default.attributesOfItem(atPath: f), (a[.size] as? Int ?? 0) > 200_000 { try? FileManager.default.removeItem(atPath: f) }
    if let h = FileHandle(forWritingAtPath: f) { h.seekToEndOfFile(); h.write(line.data(using: .utf8)!); h.closeFile() }
    else { FileManager.default.createFile(atPath: f, contents: line.data(using: .utf8)) }
}

final class PileSKView: SKView {
    override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }   // 비활성 앱이어도 첫 클릭부터 잡힌다
    override func mouseDown(with e: NSEvent) { plog("view mouseDown"); super.mouseDown(with: e) }
    override func rightMouseDown(with e: NSEvent) { plog("view rightMouseDown"); super.rightMouseDown(with: e) }
}

final class PileScene: SKScene {
    var area: CGRect = .zero
    var k: CGFloat = 1
    var queue: [Spec] = []
    var skipped = 0
    var last: TimeInterval = 0
    var spawnClock: TimeInterval = 0
    var calm = 0
    var idle: TimeInterval = 0      // 다 떨어뜨린 뒤 흐른 시간
    var dragNode: SKSpriteNode?
    var dragTo = CGPoint.zero
    var onSettled: () -> Void = {}
    var onWake: () -> Void = {}
    var onMenu: (String, NSEvent) -> Void = { _, _ in }   // 줄 원문, 이벤트

    func setup() {
        backgroundColor = .clear
        scaleMode = .resizeFill
        physicsWorld.gravity = CGVector(dx: 0, dy: -9.8)
        physicsWorld.speed = 1.6
        // 왼쪽 벽 · 바닥 · 오른쪽 벽 (위는 뚫려 있다)
        let p = CGMutablePath()
        p.move(to: CGPoint(x: area.minX, y: area.maxY + 4000)); p.addLine(to: CGPoint(x: area.minX, y: area.minY))
        p.addLine(to: CGPoint(x: area.maxX, y: area.minY)); p.addLine(to: CGPoint(x: area.maxX, y: area.maxY + 4000))
        physicsBody = SKPhysicsBody(edgeChainFrom: p)
        physicsBody?.friction = 0.9
    }

    var blocks: [SKSpriteNode] { children.compactMap { $0 as? SKSpriteNode } }

    /// 점 아래 블록 (돌아간 몸체 안쪽만, 그림자 여백 제외). 위에 그려진 것 먼저.
    func block(at pt: CGPoint) -> SKSpriteNode? {
        blocks.reversed().first { n in
            let l = n.convert(pt, from: self)
            return abs(l.x) <= n.size.width / 2 - shadowPad && abs(l.y) <= n.size.height / 2 - shadowPad
        }
    }

    func restingTop() -> CGFloat {
        blocks.filter { abs($0.physicsBody?.velocity.dy ?? 0) < 30 }.map { $0.frame.maxY }.max() ?? area.minY
    }

    func spawn(_ s: Spec) -> Bool {
        // 꽉 차면 메아리는 건너뛴다 (할 일 카드는 항상 넣는다)
        if !s.primary && restingTop() > area.minY + area.height * 0.8 { skipped += 1; return true }
        let W = s.size.width, H = s.size.height
        var r = Rng(s.key)
        let x = area.minX + W / 2 + 4 + r.next() * max(area.width - W - 8, 1)
        let y = area.maxY + H + 10
        let box = CGRect(x: x - W / 2 - 4, y: y - H / 2 - 4, width: W + 8, height: H + 8)
        if blocks.contains(where: { $0.frame.intersects(box) }) { return false }   // 나올 자리가 막혔으면 다음 프레임에
        addChild(makeNode(s, at: CGPoint(x: x, y: y), rng: &r))
        return true
    }

    func makeNode(_ s: Spec, at p: CGPoint, rng r: inout Rng) -> SKSpriteNode {
        let W = s.size.width, H = s.size.height
        let n = SKSpriteNode(texture: texture(s), size: CGSize(width: W + shadowPad * 2, height: H + shadowPad * 2))
        n.name = s.key
        n.userData = ["raw": s.raw]
        n.position = p
        n.zRotation = (r.next() - 0.5) * (s.primary ? 0.3 : 1.2)
        let body = SKPhysicsBody(rectangleOf: CGSize(width: W, height: H))
        body.friction = 0.7; body.restitution = 0.05; body.linearDamping = 0.15; body.angularDamping = 0.4; body.density = 1
        n.physicsBody = body
        // 할 일 카드는 30도 넘게 안 넘어간다 — 뒤집히면 못 읽으니까
        if s.primary { n.constraints = [SKConstraint.zRotation(SKRange(lowerLimit: -0.5, upperLimit: 0.5))] }
        return n
    }

    /// 한 번에 내려오기 — 전부 화면 위에 줄지어 놓고 같이 떨어뜨린다 (오래된 것이 아래 줄 → 바닥에 깔린다).
    /// 메아리는 화면 면적의 절반을 넘으면 뺀다 (할 일 카드는 다 넣는다).
    func dropAll(_ specs: [Spec]) {
        var x = area.minX + 4, y = area.maxY + 40, rowH: CGFloat = 0
        var used: CGFloat = 0
        let budget = area.width * area.height * 0.5
        for s in specs {
            let a = s.size.width * s.size.height
            if !s.primary && used + a > budget { skipped += 1; continue }
            used += a
            var r = Rng(s.key)
            let W = s.size.width + 8 + r.next() * 24, H = s.size.height + 8
            if x + W > area.maxX { x = area.minX + 4 + r.next() * 30; y += rowH; rowH = 0 }
            addChild(makeNode(s, at: CGPoint(x: x + W / 2, y: y + H / 2), rng: &r))
            x += W; rowH = max(rowH, H)
        }
    }

    override func update(_ now: TimeInterval) {
        let dt = last == 0 ? 0 : min(now - last, 0.1); last = now
        spawnClock += dt
        if spawnClock > 0.05, let s = queue.first {
            if spawn(s) { queue.removeFirst(); spawnClock = 0 }
        }
        if let n = dragNode, let b = n.physicsBody {   // 잡은 블록은 마우스를 따라간다 (다른 블록을 밀어낸다)
            b.velocity = CGVector(dx: (dragTo.x - n.position.x) * 14, dy: (dragTo.y - n.position.y) * 14)
            b.angularVelocity *= 0.8
        }
        if queue.isEmpty && dragNode == nil {
            idle += dt
            let still = blocks.allSatisfy { b in
                guard let v = b.physicsBody else { return true }
                return hypot(v.velocity.dx, v.velocity.dy) < 6 && abs(v.angularVelocity) < 0.15
            }
            calm = still ? calm + 1 : 0
            // 1초 동안 다 멈춰 있거나, 20초 지나면 끝 → 그리기를 멈춘다 (CPU 0)
            if calm == 60 || (idle > 20 && idle - dt <= 20) { onSettled() }
        } else { calm = 0; idle = 0 }
    }

    // 왼쪽 클릭 = 잡고 끌기, 놓으면 그 속도로 던져진다
    override func mouseDown(with e: NSEvent) {
        let pt = e.location(in: self)
        plog("scene mouseDown \(pt) hit=\(block(at: pt)?.name?.prefix(30) ?? "nil")")
        guard let n = block(at: pt) else { return }
        dragNode = n; dragTo = pt
        n.physicsBody?.linearDamping = 4
        onWake()
    }
    override func mouseDragged(with e: NSEvent) { if dragNode != nil { dragTo = e.location(in: self) } }
    override func mouseUp(with e: NSEvent) {
        dragNode?.physicsBody?.linearDamping = 0.15
        dragNode = nil; calm = 0; idle = 0
    }
    // 오른쪽 클릭 = 이 할 일로 할 수 있는 것
    override func rightMouseDown(with e: NSEvent) {
        plog("scene rightMouseDown hit=\(block(at: e.location(in: self))?.name?.prefix(30) ?? "nil")")
        guard let n = block(at: e.location(in: self)), let raw = n.userData?["raw"] as? String else { return }
        onMenu(raw, e)
    }
}

final class PileController {
    let view: SKView
    let area: CGRect
    var scene: PileScene!
    var day = ""
    var keys: [String] = []

    init(view: SKView, area: CGRect) { self.view = view; self.area = area }

    func specs(_ items: [Item], k: CGFloat) -> [Spec] {
        let cmap = projectColors(items.map { $0.project ?? "미분류" })
        // 오래된 것부터 떨어져 아래에, 메아리는 본 카드 뒤에
        return items.sorted { $0.origin < $1.origin }.flatMap { it in
            (0...echoes(it)).map { makeSpec(it, echo: $0, k: k, color: cmap[it.project ?? "미분류"] ?? .gray) }
        }
    }

    /// 다 쌓였을 때 화면을 40% 남짓 덮는 크기 배율 (어지럽게 쌓이니 틈이 많다).
    func scale(_ items: [Item]) -> CGFloat {
        let a = specs(items, k: 1).reduce(0) { $0 + $1.size.width * $1.size.height }
        return min(1.6, max(0.55, (0.4 * area.width * area.height / max(a, 1)).squareRoot()))
    }

    /// 날이 바뀌면 처음부터 다시 쌓고, 아니면 끝낸 건 빼고(위가 무너져 내려앉는다) 새것은 위에서 떨어뜨린다.
    func sync(_ items: [Item], configure: (PileScene) -> Void) {
        let today = iso.string(from: Date())
        if scene == nil || today != day {
            day = today
            let s = PileScene(size: view.bounds.size)
            s.area = area; s.k = scale(items); s.setup()
            let all = specs(items, k: s.k)
            s.dropAll(all)                       // 처음 · 새로고침은 한 번에 내려온다
            keys = all.map { $0.key }            // 빠진 메아리도 "있는 것"으로 — 나중에 하나씩 떨어지지 않게
            s.onSettled = { [weak self] in
                guard let self = self else { return }
                self.view.isPaused = true
                let pts = s.blocks.filter { $0.userData?["raw"] != nil && $0.size.width > 120 }.prefix(3).map { n -> String in
                    let vp = s.convertPoint(toView: n.position)
                    let wp = self.view.convert(vp, to: nil)
                    let sp = self.view.window?.convertPoint(toScreen: wp) ?? .zero
                    return "\(Int(sp.x)),\(Int(sp.y))"
                }
                plog("settled blocks=\(s.blocks.count) sample screen pts: \(pts.joined(separator: " "))")
            }
            s.onWake = { [weak self] in self?.view.isPaused = false }
            configure(s)
            scene = s
            view.isPaused = false
            view.presentScene(s)
            return
        }
        let all = specs(items, k: scene.k)
        let want = Set(all.map { $0.key })
        var changed = false
        for b in scene.blocks where !want.contains(b.name ?? "") { b.removeFromParent(); changed = true }
        scene.queue.removeAll { !want.contains($0.key) }
        let have = Set(keys)
        let fresh = all.filter { !have.contains($0.key) }
        if !fresh.isEmpty { scene.queue += fresh; changed = true }
        keys = all.map { $0.key }
        if changed { scene.calm = 0; scene.idle = 0; view.isPaused = false }
    }
}

// ── 창 (할 일 추가 · 마감 정하기) ─────────────────────────────
final class FormPanel: NSPanel {
    override var canBecomeKey: Bool { true }
}

func label(_ s: String) -> NSTextField { let l = NSTextField(labelWithString: s); l.textColor = .secondaryLabelColor; return l }

/// 할 일 추가 — 내용 · 프로젝트 · 중요도 · 마감 · 난이도를 다 정해야 들어간다 (vault_record.py todo).
final class AddForm: NSObject {
    let panel = FormPanel(contentRect: NSRect(x: 0, y: 0, width: 460, height: 250), styleMask: [.titled, .closable], backing: .buffered, defer: false)
    let text = NSTextField()
    let project = NSPopUpButton()
    let importance = NSSegmentedControl(labels: ["상", "중", "하"], trackingMode: .selectOne, target: nil, action: nil)
    let due = NSDatePicker()
    let effort = NSSegmentedControl(labels: ["⚡ 30분", "🔸 반나절", "🧱 하루+"], trackingMode: .selectOne, target: nil, action: nil)
    let err = NSTextField(labelWithString: "")
    var onDone: () -> Void = {}

    override init() {
        super.init()
        panel.title = "할 일 추가"
        panel.level = .floating
        text.placeholderString = "무엇을 (끝났는지 알 수 있게)"
        let prefs = loadPrefs()
        project.addItems(withTitles: vaultProjects())
        if project.itemTitles.contains(prefs.lastProject) { project.selectItem(withTitle: prefs.lastProject) }
        due.datePickerStyle = .textFieldAndStepper; due.datePickerElements = .yearMonthDay
        due.minDate = today(); due.dateValue = cal.date(byAdding: .day, value: 3, to: today())!
        err.textColor = .systemRed
        let add = NSButton(title: "추가", target: self, action: #selector(submit)); add.keyEquivalent = "\r"
        let grid = NSGridView(views: [
            [label("내용"), text], [label("프로젝트"), project], [label("중요도"), importance],
            [label("마감"), due], [label("난이도"), effort], [NSView(), err], [NSView(), add],
        ])
        grid.column(at: 0).xPlacement = .trailing
        grid.rowSpacing = 10; grid.columnSpacing = 12
        grid.translatesAutoresizingMaskIntoConstraints = false
        panel.contentView = NSView()
        panel.contentView!.addSubview(grid)
        NSLayoutConstraint.activate([
            grid.topAnchor.constraint(equalTo: panel.contentView!.topAnchor, constant: 20),
            grid.leadingAnchor.constraint(equalTo: panel.contentView!.leadingAnchor, constant: 20),
            grid.trailingAnchor.constraint(equalTo: panel.contentView!.trailingAnchor, constant: -20),
            text.widthAnchor.constraint(equalToConstant: 320),
        ])
    }

    func show() { panel.center(); NSApp.activate(ignoringOtherApps: true); panel.makeKeyAndOrderFront(nil); panel.makeFirstResponder(text) }

    @objc func submit() {
        let t = text.stringValue.trimmingCharacters(in: .whitespaces)
        guard !t.isEmpty else { err.stringValue = "내용을 적어 주세요."; return }
        guard importance.selectedSegment >= 0 else { err.stringValue = "중요도를 골라 주세요."; return }
        guard effort.selectedSegment >= 0 else { err.stringValue = "난이도를 골라 주세요."; return }
        guard let proj = project.titleOfSelectedItem else { err.stringValue = "프로젝트를 골라 주세요."; return }
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/usr/bin/python3")
        p.arguments = [vaultRecord, "todo", "--project", proj, "--text", t,
                       "--importance", ["상", "중", "하"][importance.selectedSegment],
                       "--due", iso.string(from: due.dateValue), "--effort", ["⚡", "🔸", "🧱"][effort.selectedSegment]]
        let pipe = Pipe(); p.standardError = pipe; p.standardOutput = Pipe()
        do { try p.run() } catch { err.stringValue = "실행 실패: \(error.localizedDescription)"; return }
        p.waitUntilExit()
        if p.terminationStatus != 0 {
            err.stringValue = String(data: pipe.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8)?.split(separator: "\n").first.map(String.init) ?? "실패"
            return
        }
        var prefs = loadPrefs(); prefs.lastProject = proj; savePrefs(prefs)
        panel.close(); onDone()
    }
}

/// 마감 · 중요도 정하기 (미루면 미룬 횟수 ↻ 가 는다).
final class DueForm: NSObject {
    let panel = FormPanel(contentRect: NSRect(x: 0, y: 0, width: 420, height: 170), styleMask: [.titled, .closable], backing: .buffered, defer: false)
    let importance = NSSegmentedControl(labels: ["상", "중", "하"], trackingMode: .selectOne, target: nil, action: nil)
    let due = NSDatePicker()
    let err = NSTextField(labelWithString: "")
    let item: Item
    var onDone: () -> Void = {}

    init(item: Item) {
        self.item = item
        super.init()
        panel.title = "마감 · 중요도 — " + String(item.text.prefix(24))
        panel.level = .floating
        importance.selectedSegment = ["상": 0, "중": 1, "하": 2][item.importance ?? ""] ?? -1
        due.datePickerStyle = .textFieldAndStepper; due.datePickerElements = .yearMonthDay
        due.minDate = today()
        due.dateValue = max(item.due ?? today(), cal.date(byAdding: .day, value: 1, to: today())!)
        err.textColor = .systemRed
        let ok = NSButton(title: "정하기", target: self, action: #selector(submit)); ok.keyEquivalent = "\r"
        let grid = NSGridView(views: [[label("중요도"), importance], [label("마감"), due], [NSView(), err], [NSView(), ok]])
        grid.column(at: 0).xPlacement = .trailing
        grid.rowSpacing = 10; grid.columnSpacing = 12
        grid.translatesAutoresizingMaskIntoConstraints = false
        panel.contentView = NSView()
        panel.contentView!.addSubview(grid)
        NSLayoutConstraint.activate([grid.topAnchor.constraint(equalTo: panel.contentView!.topAnchor, constant: 20),
                                     grid.leadingAnchor.constraint(equalTo: panel.contentView!.leadingAnchor, constant: 20)])
    }

    func show() { panel.center(); NSApp.activate(ignoringOtherApps: true); panel.makeKeyAndOrderFront(nil) }

    @objc func submit() {
        guard importance.selectedSegment >= 0 else { err.stringValue = "중요도를 골라 주세요."; return }
        let d = cal.startOfDay(for: due.dateValue)
        let pp = item.postponed + ((item.due.map { d > $0 } ?? false) ? 1 : 0)
        guard rewrite(item.raw, { withMarkers($0, importance: ["상", "중", "하"][self.importance.selectedSegment], due: d, postponed: pp) }) else {
            err.stringValue = "TODO 파일이 그 사이 바뀌었어요. 다시 열어 주세요."; return
        }
        panel.close(); onDone()
    }
}

/// Jira 연결 — 사이트 · 이메일 · API 토큰. 확인되면 토큰은 키체인에, 나머지는 설정에.
final class JiraForm: NSObject {
    let panel = FormPanel(contentRect: NSRect(x: 0, y: 0, width: 480, height: 230), styleMask: [.titled, .closable], backing: .buffered, defer: false)
    let site = NSTextField(), email = NSTextField(), token = NSSecureTextField()
    let err = NSTextField(labelWithString: "")
    var onDone: () -> Void = {}

    override init() {
        super.init()
        panel.title = "Jira 연결"; panel.level = .floating
        let pr = loadPrefs()
        site.stringValue = pr.jiraSite ?? "millietown.atlassian.net"
        email.stringValue = pr.jiraEmail ?? ""; email.placeholderString = "Atlassian 로그인 이메일"
        token.placeholderString = "API 토큰"
        err.textColor = .secondaryLabelColor
        err.stringValue = "토큰 만들기: id.atlassian.com → 보안 → API 토큰"
        let link = NSButton(title: "토큰 만들러 가기", target: self, action: #selector(openTokenPage)); link.bezelStyle = .inline
        let ok = NSButton(title: "연결", target: self, action: #selector(submit)); ok.keyEquivalent = "\r"
        let grid = NSGridView(views: [[label("사이트"), site], [label("이메일"), email], [label("API 토큰"), token],
                                      [NSView(), err], [link, ok]])
        grid.column(at: 0).xPlacement = .trailing; grid.rowSpacing = 10; grid.columnSpacing = 12
        grid.translatesAutoresizingMaskIntoConstraints = false
        panel.contentView = NSView(); panel.contentView!.addSubview(grid)
        NSLayoutConstraint.activate([grid.topAnchor.constraint(equalTo: panel.contentView!.topAnchor, constant: 20),
                                     grid.leadingAnchor.constraint(equalTo: panel.contentView!.leadingAnchor, constant: 20),
                                     site.widthAnchor.constraint(equalToConstant: 300)])
    }
    func show() { panel.center(); NSApp.activate(ignoringOtherApps: true); panel.makeKeyAndOrderFront(nil) }
    @objc func openTokenPage() { NSWorkspace.shared.open(URL(string: "https://id.atlassian.com/manage-profile/security/api-tokens")!) }

    @objc func submit() {
        let st = site.stringValue.trimmingCharacters(in: .whitespaces).replacingOccurrences(of: "https://", with: "").trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        let em = email.stringValue.trimmingCharacters(in: .whitespaces), tk = token.stringValue.trimmingCharacters(in: .whitespaces)
        guard !st.isEmpty, !em.isEmpty, !tk.isEmpty, let req = jiraRequest(site: st, email: em, token: tk, path: "/rest/api/3/myself", query: []) else {
            err.textColor = .systemRed; err.stringValue = "세 칸을 다 채워 주세요."; return
        }
        err.textColor = .secondaryLabelColor; err.stringValue = "확인 중…"
        URLSession.shared.dataTask(with: req) { data, resp, _ in
            let code = (resp as? HTTPURLResponse)?.statusCode ?? 0
            let name = data.flatMap { try? JSONSerialization.jsonObject(with: $0) as? [String: Any] }?["displayName"] as? String
            DispatchQueue.main.async {
                guard code == 200 else { self.err.textColor = .systemRed; self.err.stringValue = "연결 실패 (응답 \(code)) — 이메일 · 토큰을 확인해 주세요."; return }
                keychainSet(em, tk)
                var pr = loadPrefs(); pr.jiraSite = st; pr.jiraEmail = em; savePrefs(pr)
                self.err.textColor = .systemGreen; self.err.stringValue = "연결됨 — \(name ?? em)"
                self.onDone()
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.8) { self.panel.close() }
            }
        }.resume()
    }
}

// ── Claude 열기 ─────────────────────────────────────────────
/// `cd <dir> && claude --model sonnet "<prompt>"` 스크립트. 프롬프트는 heredoc 으로 넣어 따옴표가 안 깨진다.
func writeClaudeScript(dir: String, prompt: String, model: String = "sonnet", flags: [String] = []) -> String {
    let script = home + "/.phantom-obsidian/state/todo-claude-\(Int(Date().timeIntervalSince1970)).sh"
    let body = "#!/bin/zsh -l\ncd '\(dir.replacingOccurrences(of: "'", with: "'\\''"))' || exit 1\nrm -f \"$0\"\n"
        + "PROMPT=$(cat <<'__TODO_PROMPT__'\n\(prompt)\n__TODO_PROMPT__\n)\n# 프롬프트를 먼저 — --allowedTools 는 뒤의 인자를 다 목록으로 먹는다\nexec claude \"$PROMPT\" --model \(model) " + flags.map { "'" + $0.replacingOccurrences(of: "'", with: "'\\''") + "'" }.joined(separator: " ") + "\n"
    try? FileManager.default.createDirectory(atPath: (script as NSString).deletingLastPathComponent, withIntermediateDirectories: true)
    try? body.write(toFile: script, atomically: true, encoding: .utf8)
    try? FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: script)
    return script
}

let vaultRecord = vaultRecordPath()

/// "AI 로 수정하기" 첫 메시지 — vault 에서 Ghostty 로 연 claude 에게 보낸다. 수정사항은 다음 답변으로 준다.
func editPrompt(_ it: Item) -> String {
    """
    "\(it.text)" 항목 수정할거야. 수정사항은 다음 답변에서 줄게.
    TODO 파일: \(latestTodoFile() ?? "-")
    원래 줄: \(it.raw)
    (줄 고치기 · 완료 · 버리기는 이 줄만 고친다. 프로젝트로 바꾸기 · 쪼개기는 vault-record 규칙대로 `python3 \(vaultRecord) …` 로 — 필요한 값은 나한테 묻고, 고치기 전에 바뀔 내용을 먼저 보여 줘)
    """
}

// ── 앱 ──────────────────────────────────────────────────────
final class App: NSObject, NSApplicationDelegate, NSMenuDelegate {
    var window: NSWindow?
    var pile: PileController?
    var status: NSStatusItem!
    var timer: Timer?
    var hover: Timer?
    var items: [Item] = []
    var forms: [NSObject] = []     // 열린 창을 붙잡아 둔다
    var stamp = ""                 // TODO 파일 이름 + 수정 시각 — 바뀌면 바로 다시 읽는다
    var jiraTimer: Timer?
    var jiraNote = ""              // 마지막 Jira 가져오기 결과 (메뉴에 보인다)

    func allItems() -> [Item] { loadItems() + loadJiraCache() }

    /// Jira 를 가져와 바뀌었으면 블록에 반영 (10분마다 · 새로고침 · 연결 직후).
    func pullJira() {
        guard loadPrefs().jiraEmail != nil else { return }
        fetchJira { [weak self] ok, msg in self?.jiraNote = msg; if ok { self?.refresh() } }
    }

    func applicationDidFinishLaunching(_ n: Notification) {
        status = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        let menu = NSMenu(); menu.delegate = self
        status.menu = menu
        rebuild()
        NotificationCenter.default.addObserver(forName: NSApplication.didChangeScreenParametersNotification, object: nil, queue: .main) { [weak self] _ in self?.rebuild() }
        // 3초마다 TODO 파일이 바뀌었는지 본다 (Claude · 옵시디언에서 고치면 바로 블록에 반영)
        let tm = Timer(timeInterval: 3, repeats: true) { [weak self] _ in self?.refreshIfChanged() }
        RunLoop.main.add(tm, forMode: .common); timer = tm
        let jt = Timer(timeInterval: 600, repeats: true) { [weak self] _ in self?.pullJira() }
        RunLoop.main.add(jt, forMode: .common); jiraTimer = jt
        pullJira()
        // 마우스가 블록 위에 있을 때만 창이 클릭을 받는다 — 나머지는 바탕화면으로 통과
        let hv = Timer(timeInterval: 1.0 / 30, repeats: true) { [weak self] _ in self?.updateHover() }
        RunLoop.main.add(hv, forMode: .common); hover = hv
        if let sec = env["PILE_TEST_CLOSE"].flatMap(Double.init) {   // 시험용: N초 뒤 종료
            DispatchQueue.main.asyncAfter(deadline: .now() + sec) {
                if let s = self.pile?.scene { print("blocks \(s.blocks.count) · skipped \(s.skipped) · queue \(s.queue.count) · scale \(String(format: "%.2f", s.k)) · paused \(self.pile!.view.isPaused)") }
                NSApp.terminate(nil)
            }
        }
    }

    func updateHover() {
        guard let w = window, w.isVisible, let s = pile?.scene, let v = pile?.view else { return }
        if s.dragNode != nil { w.ignoresMouseEvents = false; return }
        let p = v.convert(w.convertPoint(fromScreen: NSEvent.mouseLocation), from: nil)
        let ignore = s.block(at: s.convertPoint(fromView: p)) == nil
        if ignore != w.ignoresMouseEvents { plog("hover \(ignore ? "off" : "on") at \(NSEvent.mouseLocation)") }
        w.ignoresMouseEvents = ignore
    }

    /// 메뉴바가 있는 기본 모니터에, 바탕화면 아이콘 바로 위 층 창 하나 (앱 창보다는 아래).
    func fileStamp() -> String {
        guard let f = latestTodoFile(), let m = (try? FileManager.default.attributesOfItem(atPath: f))?[.modificationDate] as? Date else { return "" }
        return f + "@\(m.timeIntervalSince1970)"
    }
    func refreshIfChanged() { let s = fileStamp(); if s != stamp { plog("TODO 파일 바뀜 → 다시 읽음"); refresh() } }

    /// 새로고침 — TODO 를 다시 읽고 블록을 처음부터 다시 떨어뜨린다 (멈췄거나 꼬였을 때).
    @objc func reload() { plog("새로고침"); rebuild(); pullJira() }

    func rebuild() {
        window?.orderOut(nil)
        let idx = Int(env["PILE_SCREEN"] ?? "0") ?? 0
        let screen = NSScreen.screens.indices.contains(idx) ? NSScreen.screens[idx] : NSScreen.screens[0]
        let w = NSWindow(contentRect: screen.frame, styleMask: .borderless, backing: .buffered, defer: false)
        w.setFrame(screen.frame, display: false)
        w.level = env["PILE_TEST_CLOSE"] != nil ? .floating : NSWindow.Level(rawValue: Int(CGWindowLevelForKey(.desktopIconWindow)) + 1)
        w.isOpaque = false; w.backgroundColor = .clear; w.hasShadow = false
        w.ignoresMouseEvents = true
        w.acceptsMouseMovedEvents = true
        w.collectionBehavior = [.canJoinAllSpaces, .stationary, .ignoresCycle]
        let v = PileSKView(frame: NSRect(origin: .zero, size: screen.frame.size))
        v.allowsTransparency = true
        v.ignoresSiblingOrder = true
        w.contentView = v
        if loadPrefs().visible { w.orderFrontRegardless() }
        let vf = screen.visibleFrame, f = screen.frame
        window = w
        pile = PileController(view: v, area: CGRect(x: vf.minX - f.minX + 4, y: vf.minY - f.minY + 2, width: vf.width - 8, height: vf.height - 6))
        refresh()
    }

    @objc func refresh() {
        stamp = fileStamp()
        items = allItems()
        pile?.sync(items) { s in s.onMenu = { [weak self] raw, e in self?.contextMenu(raw, e) } }
        let late = items.filter { ($0.late ?? 0) > 0 }.count
        let jira = items.filter { $0.jiraKey != nil }.count
        status.button?.title = "TODO \(items.count - jira)" + (jira > 0 ? " · Jira \(jira)" : "") + (late > 0 ? " 🔴\(late)" : "")
    }

    // ── 메뉴바: 켜고 끄기 · 할 일 추가 · 할 일 목록 ──
    func menuNeedsUpdate(_ menu: NSMenu) {
        items = allItems()
        menu.removeAllItems()
        let vis = menu.addItem(withTitle: "바탕화면에 블록 보이기", action: #selector(toggleVisible), keyEquivalent: "")
        vis.target = self; vis.state = loadPrefs().visible ? .on : .off
        menu.addItem(withTitle: "할 일 추가…", action: #selector(addTodo), keyEquivalent: "n").target = self
        menu.addItem(withTitle: "새로고침", action: #selector(reload), keyEquivalent: "r").target = self
        let pr = loadPrefs()
        menu.addItem(withTitle: pr.jiraEmail == nil ? "Jira 연결…" : "Jira 연결 바꾸기…" + (jiraNote.isEmpty ? "" : "  (\(jiraNote))"),
                     action: #selector(connectJira), keyEquivalent: "").target = self
        if pr.jiraEmail != nil {
            // Jira 상태별 켜고 끄기 (체크된 상태만 블록으로)
            let all = jiraAll()
            let counts = Dictionary(grouping: all, by: { $0.status ?? "-" }).mapValues { $0.count }
            let show = Set(pr.jiraShow ?? jiraShowDefault)
            let sm = NSMenu()
            for (st, n) in counts.sorted(by: { $0.value > $1.value }) {
                let mi = sm.addItem(withTitle: "\(st)  (\(n))", action: #selector(toggleJiraStatus(_:)), keyEquivalent: "")
                mi.target = self; mi.representedObject = st; mi.state = show.contains(st) ? .on : .off
            }
            let jm = NSMenuItem(title: "Jira 상태 — \(all.filter { show.contains($0.status ?? "") }.count) / \(all.count)건", action: nil, keyEquivalent: "")
            jm.submenu = sm; menu.addItem(jm)
        }
        menu.addItem(.separator())
        let sorted = items.sorted { pressure($0) > pressure($1) }
        for it in sorted.prefix(30) {
            let mark = (it.jiraKey != nil ? "🎫 " : "") + (it.late.map { $0 > 0 ? "🔴 D+\($0)" : ($0 == 0 ? "🟠 오늘" : "📅 \(-$0)일") } ?? "⚪︎ \(it.age)일")
            let mi = NSMenuItem(title: "\(mark)  " + (it.text.count > 46 ? String(it.text.prefix(46)) + "…" : it.text), action: nil, keyEquivalent: "")
            mi.toolTip = (it.project.map { "[\($0)] " } ?? "") + it.text
            mi.submenu = actions(for: it)
            menu.addItem(mi)
        }
        if sorted.count > 30 {
            menu.addItem(withTitle: "… 외 \(sorted.count - 30)개 — TODO 파일 열기", action: #selector(openFile), keyEquivalent: "").target = self
        }
        menu.addItem(.separator())
        menu.addItem(withTitle: "TODO 파일 열기", action: #selector(openFile), keyEquivalent: "").target = self
        menu.addItem(withTitle: "종료", action: #selector(quit), keyEquivalent: "").target = self
    }

    // ── 블록 오른쪽 클릭 · 목록 하위 메뉴: 이 할 일로 할 수 있는 것 ──
    func actions(for it: Item) -> NSMenu {
        let m = NSMenu()
        func add(_ t: String, _ sel: Selector) { let i = m.addItem(withTitle: t, action: sel, keyEquivalent: ""); i.target = self; i.representedObject = it.raw }
        let head = NSMenuItem(title: (it.project.map { "[\($0)] " } ?? "") + (it.text.count > 60 ? String(it.text.prefix(60)) + "…" : it.text), action: nil, keyEquivalent: "")
        head.isEnabled = false; m.addItem(head)
        m.addItem(.separator())
        let proj = it.project ?? "미분류"
        if it.jiraKey != nil {
            add("Jira 에서 열기", #selector(openJira(_:)))
            if let d = loadPrefs().dirs[proj] { add("Claude 로 해결하기 — \((d as NSString).lastPathComponent)", #selector(solve(_:))) }
            else { add("Claude 로 해결하기 — 코드 폴더 고르기…", #selector(solve(_:))) }
            m.addItem(.separator())
            add("`\(proj)` 코드 폴더 바꾸기…", #selector(pickDir(_:)))
            return m
        }
        if let d = loadPrefs().dirs[proj] { add("Claude 로 해결하기 — \((d as NSString).lastPathComponent)", #selector(solve(_:))) }
        else { add("Claude 로 해결하기 — 코드 폴더 고르기…", #selector(solve(_:))) }
        add("AI 로 수정하기", #selector(editWithAI(_:)))
        add("완료", #selector(done(_:)))
        add("마감 · 중요도 정하기…", #selector(setDue(_:)))
        add("버리기", #selector(drop(_:)))
        m.addItem(.separator())
        add("`\(proj)` 코드 폴더 바꾸기…", #selector(pickDir(_:)))
        add("TODO 파일 열기", #selector(openFile))
        return m
    }

    func contextMenu(_ raw: String, _ e: NSEvent) {
        guard let it = items.first(where: { $0.raw == raw }), let v = pile?.view else { return }
        NSMenu.popUpContextMenu(actions(for: it), with: e, for: v)
    }

    func item(_ sender: NSMenuItem) -> Item? { (sender.representedObject as? String).flatMap { r in items.first { $0.raw == r } } }

    @objc func done(_ s: NSMenuItem) { if let it = item(s) { _ = rewrite(it.raw, markDone); refresh() } }
    @objc func drop(_ s: NSMenuItem) { if let it = item(s) { _ = rewrite(it.raw) { markDone($0) + " · 🗑 버림" }; refresh() } }
    @objc func setDue(_ s: NSMenuItem) {
        guard let it = item(s) else { return }
        let f = DueForm(item: it); f.onDone = { [weak self] in self?.refresh() }
        forms.append(f); f.show()
    }
    @objc func openJira(_ s: NSMenuItem) {
        guard let key = item(s)?.jiraKey, let u = URL(string: "https://\(loadPrefs().jiraSite ?? "millietown.atlassian.net")/browse/\(key)") else { return }
        NSWorkspace.shared.open(u)
    }
    @objc func toggleJiraStatus(_ s: NSMenuItem) {
        guard let st = s.representedObject as? String else { return }
        var pr = loadPrefs(); var show = pr.jiraShow ?? jiraShowDefault
        if let i = show.firstIndex(of: st) { show.remove(at: i) } else { show.append(st) }
        pr.jiraShow = show; savePrefs(pr); refresh()
    }
    @objc func connectJira() {
        let f = JiraForm(); f.onDone = { [weak self] in self?.pullJira() }
        forms.append(f); f.show()
    }
    @objc func addTodo() {
        let f = AddForm(); f.onDone = { [weak self] in self?.refresh() }
        forms.append(f); f.show()
    }

    /// 프로젝트의 코드 폴더를 고른다 (한 번 고르면 기억).
    func chooseDir(_ proj: String) -> String? {
        let p = NSOpenPanel()
        p.canChooseDirectories = true; p.canChooseFiles = false; p.allowsMultipleSelection = false
        p.message = "`\(proj)` 할 일을 Claude 로 풀 코드 폴더"
        p.directoryURL = URL(fileURLWithPath: home + "/Desktop/00.Projects")
        NSApp.activate(ignoringOtherApps: true)
        guard p.runModal() == .OK, let u = p.url else { return nil }
        var prefs = loadPrefs(); prefs.dirs[proj] = u.path; savePrefs(prefs)
        return u.path
    }
    @objc func pickDir(_ s: NSMenuItem) { if let it = item(s) { _ = chooseDir(it.project ?? "미분류") } }

    /// 그 프로젝트 코드 폴더에서 Ghostty(없으면 터미널)로 Claude 를 열고, 할 일을 첫 메시지로 넘긴다.
    /// 해결할 모델 고르기 — 엔터 = Opus, Esc = 취소.
    func pickModel(_ it: Item) -> String? {
        let a = NSAlert()
        a.messageText = "어떤 모델로 해결할까요?"
        a.informativeText = it.text.count > 120 ? String(it.text.prefix(120)) + "…" : it.text
        for t in ["Opus", "Sonnet", "Haiku", "취소"] { a.addButton(withTitle: t) }   // 첫 버튼(Opus)이 엔터
        a.buttons.last?.keyEquivalent = "\u{1b}"
        NSApp.activate(ignoringOtherApps: true)
        switch a.runModal() {
        case .alertFirstButtonReturn: return "opus"
        case .alertSecondButtonReturn: return "sonnet"
        case .alertThirdButtonReturn: return "haiku"
        default: return nil
        }
    }

    @objc func solve(_ s: NSMenuItem) {
        guard let it = item(s) else { return }
        let proj = it.project ?? "미분류"
        guard let dir = loadPrefs().dirs[proj] ?? chooseDir(proj), let model = pickModel(it) else { return }
        if let key = it.jiraKey {
            let url = "https://\(loadPrefs().jiraSite ?? "millietown.atlassian.net")/browse/\(key)"
            let jp = """
            Jira 이슈를 해결하자.
            이슈: \(it.text)
            링크: \(url)
            상태: \(it.status ?? "-") · \(meta(it))
            먼저 이슈 내용을 확인하고(Atlassian 연결이 있으면 읽어서), 무엇이 끝나야 완료인지 한 줄로 정하고 시작해.
            """
            openClaude(in: dir, prompt: jp, model: model)
            return
        }
        let prompt = """
        vault TODO 를 해결하자.
        할 일: \(it.text)
        프로젝트: \(proj) · \(meta(it))
        TODO 파일의 원래 줄: \(it.raw)
        먼저 무엇이 끝나야 완료인지 한 줄로 정하고 시작해. 끝나면 TODO 줄을 [x] 로 바꿔도 되는지 물어봐.
        """
        openClaude(in: dir, prompt: prompt, model: model)
    }

    /// 이 할 일 줄을 고치러 vault 에서 Claude 를 연다 (Ghostty 보통 창, sonnet). 수정사항은 다음 답변으로 준다.
    @objc func editWithAI(_ s: NSMenuItem) {
        guard let it = item(s) else { return }
        openClaude(in: vaultPath(), prompt: editPrompt(it))
    }

    /// 그 폴더에서 Ghostty(없으면 터미널)로 claude 를 열고 prompt 를 첫 메시지로 넘긴다.
    func openClaude(in dir: String, prompt: String, model: String = "sonnet", flags: [String] = []) {
        let script = writeClaudeScript(dir: dir, prompt: prompt, model: model, flags: flags)
        let ghostty = URL(fileURLWithPath: "/Applications/Ghostty.app")
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/usr/bin/open")
        if FileManager.default.fileExists(atPath: ghostty.path) {
            // 새 인스턴스라 예전 창을 복원하지 않게 · 전체화면 말고 보통 창으로 · 다 끝나면 스스로 닫히게
            p.arguments = ["-na", ghostty.path, "--args", "--window-save-state=never", "--quit-after-last-window-closed=true",
                           "--fullscreen=false", "--maximize=false", "--window-width=110", "--window-height=32",
                           "--title=TODO · Claude", "-e", script]
        } else {
            let cmd = home + "/.phantom-obsidian/state/todo-claude.command"
            try? FileManager.default.removeItem(atPath: cmd)
            try? FileManager.default.copyItem(atPath: script, toPath: cmd)
            p.arguments = ["-a", "Terminal", cmd]
        }
        try? p.run()
    }

    @objc func toggleVisible() {
        var prefs = loadPrefs(); prefs.visible.toggle(); savePrefs(prefs)
        if prefs.visible { window?.orderFrontRegardless(); pile?.view.isPaused = false } else { window?.orderOut(nil); pile?.view.isPaused = true }
    }
    /// TODO 파일은 옵시디언으로 연다 (`obsidian://open?path=`). 옵시디언이 없으면 기본 앱으로.
    @objc func openFile() {
        guard let f = latestTodoFile() else { return }
        var c = URLComponents(); c.scheme = "obsidian"; c.host = "open"; c.queryItems = [URLQueryItem(name: "path", value: f)]
        if let u = c.url, NSWorkspace.shared.urlForApplication(toOpen: u) != nil { NSWorkspace.shared.open(u) }
        else { NSWorkspace.shared.open(URL(fileURLWithPath: f)) }
    }
    @objc func quit() { NSApp.terminate(nil) }
}

// 시험: `todo-pile --jira-parse 응답.json` — Jira 응답을 블록 항목으로 바꿔 보고 출력
if let i = CommandLine.arguments.firstIndex(of: "--jira-parse"), i + 1 < CommandLine.arguments.count,
   let d = FileManager.default.contents(atPath: CommandLine.arguments[i + 1]) {
    for it in jiraItems(d, site: "x") ?? [] { print(it.raw, "|", it.project ?? "-", "|", it.text, "|", it.status ?? "-", "|", it.importance ?? "-", "|", it.due.map { iso.string(from: $0) } ?? "-", "|", "\(it.age)일", "| 메아리", echoes(it)) }
    exit(0)
}

// 시험: `todo-pile --edit-script N` — N번째 할 일의 "AI 로 수정하기" 실행 스크립트만 써 보고 경로를 출력 (창 안 띄움)
if let i = CommandLine.arguments.firstIndex(of: "--edit-script"), i + 1 < CommandLine.arguments.count,
   let n = Int(CommandLine.arguments[i + 1]), loadItems().indices.contains(n) {
    print(writeClaudeScript(dir: vaultPath(), prompt: editPrompt(loadItems()[n])))
    exit(0)
}

let app = NSApplication.shared
app.setActivationPolicy(.accessory)
let delegate = App()
app.delegate = delegate
app.run()
