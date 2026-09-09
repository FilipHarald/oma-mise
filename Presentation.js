.pragma library

function age(timestamp, now) {
  var time = typeof timestamp === "string" ? Date.parse(timestamp) : NaN
  if (!isFinite(time)) return "Time unavailable"
  var seconds = Math.floor((now - time) / 1000)
  var value = Math.abs(seconds)
  var label = value + "s"
  for (var unit of [[86400, "d"], [3600, "h"], [60, "m"]]) {
    if (value >= unit[0]) {
      label = Math.floor(value / unit[0]) + unit[1]
      break
    }
  }
  return seconds < 0 ? "in " + label : label + " ago"
}

function fullDate(timestamp) {
  var time = typeof timestamp === "string" ? Date.parse(timestamp) : NaN
  if (!isFinite(time)) return "Date unavailable"
  var date = new Date(time)
  var months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
  function pad(value) { return value < 10 ? "0" + value : String(value) }
  return date.getDate() + " " + months[date.getMonth()] + " " + date.getFullYear()
    + ", " + pad(date.getHours()) + ":" + pad(date.getMinutes())
}

function duration(seconds) {
  var value = Math.max(0, Math.ceil(seconds))
  var hours = Math.floor(value / 3600)
  var minutes = Math.floor(value % 3600 / 60)
  return (hours ? hours + "h " : "") + (minutes || hours ? minutes + "m " : "") + value % 60 + "s"
}

function reviewCommand(kind) {
  var base = 'mise -C "$HOME" bootstrap dotfiles '
  if (["status", "conflicts", "changes"].indexOf(kind) === -1) return ""
  var commands = [base + "status"]
  if (kind === "changes") commands.push(base + "history diff")
  if (kind !== "status") commands.push(base + "pull --dry-run")
  return commands.join("; ")
}

function isReviewCommand(text) {
  return ["status", "conflicts", "changes"].some(function(kind) { return text === reviewCommand(kind) })
}

function watcher(text) {
  try {
    var data = parsePayload(text, 4096)
    if (keysOnly(data, ["state", "can_control", "error"])
        && ["running", "stopped", "unknown"].indexOf(data.state) !== -1
        && typeof data.can_control === "boolean" && safeString(data.error, 512, false)
        && !(data.state === "unknown" && data.can_control)) return data
  } catch (e) {}
  return {state: "unknown", can_control: false, error: "Watcher status unavailable"}
}

function decode(text) {
  try {
    var data = parsePayload(text, 65536)
    if (validStatus(data)) return data
  } catch (e) {}
  return {level: "yellow", summary: "Status unavailable", details: ["Could not read mise status. Try Refresh."],
    actions: [], needs_attention: true, history_available: false, checkpoints: [], recent_files: []}
}

function actionResult(text) {
  try {
    var data = parsePayload(text, 4096)
    if (keysOnly(data, ["ok", "error"]) && typeof data.ok === "boolean"
        && safeString(data.error, 512, false)
        && ((data.ok && !data.error) || (!data.ok && data.error))) return data
  } catch (e) {}
  return {ok: false, error: "Bootstrap result unavailable"}
}

// Bound nesting and reject duplicate/oversized object keys BEFORE JSON.parse.
// The protocol has only a root object and one details array/timestamps object.
function parsePayload(text, limit) {
  if (typeof text !== "string" || text.length > limit) throw new Error("limit")
  var stack = []
  var inString = false
  var begin = 0
  for (var i = 0; i < text.length; i++) {
    var c = text[i]
    if (inString) {
      if (c === "\\") { i++; continue }
      if (c !== '"') continue
      inString = false
      var next = i + 1
      while (next < text.length && /\s/.test(text[next])) next++
      if (text[next] === ":" && stack.length) {
        if (i - begin > 64) throw new Error("key limit")
        var key = JSON.parse(text.slice(begin, i + 1))
        var frame = stack[stack.length - 1]
        if (frame.indexOf(key) !== -1 || frame.length >= 11) throw new Error("keys")
        frame.push(key)
      }
    } else if (c === '"') { inString = true; begin = i }
    else if (c === "{" || c === "[") {
      if (stack.length >= 3) throw new Error("depth")
      stack.push([])
    } else if (c === "}" || c === "]") stack.pop()
  }
  return JSON.parse(text)
}

// Host-owned tooltip uses AutoText: strip markup metacharacters as well as controls.
function hostTooltip(value) {
  if (typeof value !== "string") return "Mise dotfiles — Status unavailable"
  return ("Mise dotfiles — " + value.slice(0, 256))
    .replace(/[<>&\u0000-\u001f\u007f-\u009f\u061c\u200e\u200f\u202a-\u202e\u2066-\u2069]/g, "").slice(0, 256)
}

function keysOnly(data, keys) {
  return data !== null && typeof data === "object" && !Array.isArray(data)
    && Object.keys(data).every(function(key) { return keys.indexOf(key) !== -1 })
}

function safeString(value, limit, multiline) {
  return typeof value === "string" && value.length <= limit
    && !(multiline ? /[\u0000-\u0009\u000b-\u001f\u007f-\u009f\u061c\u200e\u200f\u202a-\u202e\u2066-\u2069]/
                  : /[\u0000-\u001f\u007f-\u009f\u061c\u200e\u200f\u202a-\u202e\u2066-\u2069]/).test(value)
}

function timestamp(value) {
  if (typeof value !== "string" || value.length > 40) return false
  var m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d{1,6})?(?:Z|([+-])(\d{2}):(\d{2}))$/.exec(value)
  if (!m || +m[1] < 1 || +m[2] < 1 || +m[2] > 12 || +m[3] < 1
      || +m[3] > new Date(Date.UTC(+m[1], +m[2], 0)).getUTCDate()
      || +m[4] > 23 || +m[5] > 59 || +m[6] > 59
      || (m[7] && (+m[8] > 23 || +m[9] > 59))) return false
  return isFinite(Date.parse(value))
}

function validStatus(data) {
  return keysOnly(data, ["level", "summary", "details", "actions", "needs_attention", "history_available",
      "checkpoints", "recent_files", "checked_at", "checked_label", "timestamps"])
    && ["green", "yellow", "red", "blue"].indexOf(data.level) !== -1
    && safeString(data.summary, 256, false) && data.summary.length > 0 && Array.isArray(data.details)
    && data.details.length <= 32 && data.details.every(function(line) {
      if (!safeString(line, 1024, true)) return false
      var counts = /^Files: (\d+|unknown) \| Checkpoints: (\d+|unknown)$/.exec(line)
      return !counts || [counts[1], counts[2]].every(function(n) {
        return n === "unknown" || (n.length <= 16 && Number.isSafeInteger(Number(n)) && Number(n) >= 0)
      })
    })
    && (data.actions === undefined || (Array.isArray(data.actions) && data.actions.length <= 1
      && data.actions.every(function(action) { return action === "bootstrap" })))
    && (data.needs_attention === undefined || typeof data.needs_attention === "boolean")
    && (data.history_available === undefined || typeof data.history_available === "boolean")
    && (data.checkpoints === undefined || (Array.isArray(data.checkpoints) && data.checkpoints.length <= 10
      && data.checkpoints.every(function(item) {
        return keysOnly(item, ["message", "at"]) && safeString(item.message, 256, false)
          && item.message.length > 0 && timestamp(item.at)
      })))
    && (data.recent_files === undefined || (Array.isArray(data.recent_files) && data.recent_files.length <= 10
      && data.recent_files.every(function(item) {
        return keysOnly(item, ["path", "at"]) && safeString(item.path, 512, false)
          && item.path.length > 0 && timestamp(item.at)
      })))
    && (data.checked_at === undefined || timestamp(data.checked_at))
    && (data.checked_label === undefined || safeString(data.checked_label, 64, false))
    && (data.timestamps === undefined || (keysOnly(data.timestamps, ["publish", "fetch", "apply"])
      && ["publish", "fetch", "apply"].every(function(key) {
        return data.timestamps[key] === null || timestamp(data.timestamps[key])
      })))
}

function colorFor(level) {
  if (level === "blue") return "#7aa2f7"
  if (level === "green") return "#72c78b"
  if (level === "red") return "#ee7373"
  return "#e5bf69"
}
