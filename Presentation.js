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

function duration(seconds) {
  var value = Math.max(0, Math.ceil(seconds))
  var hours = Math.floor(value / 3600)
  var minutes = Math.floor(value % 3600 / 60)
  return (hours ? hours + "h " : "") + (minutes || hours ? minutes + "m " : "") + value % 60 + "s"
}

function watcher(text) {
  try {
    var data = JSON.parse(text)
    if (["running", "stopped", "unknown"].indexOf(data.state) !== -1
        && typeof data.can_control === "boolean" && typeof data.error === "string") return data
  } catch (e) {}
  return {state: "unknown", can_control: false, error: "Watcher status unavailable"}
}

function decode(text) {
  try {
    var data = JSON.parse(text)
    if (["green", "yellow", "red", "blue"].indexOf(data.level) !== -1
        && typeof data.summary === "string" && Array.isArray(data.details)) return data
  } catch (e) {}
  return {level: "yellow", summary: "Status unavailable", details: ["Could not read mise status. Try Refresh."]}
}

function colorFor(level) {
  if (level === "blue") return "#7aa2f7"
  if (level === "green") return "#72c78b"
  if (level === "red") return "#ee7373"
  return "#e5bf69"
}
