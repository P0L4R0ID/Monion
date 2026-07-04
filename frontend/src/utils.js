export function slugify(text) {
  return (text || "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "") || "unknown";
}

/** Pull a 4-digit year out of a free-text date string; falls back to the current year. */
export function extractYear(dateText) {
  const match = (dateText || "").match(/\b(20\d{2})\b/);
  return match ? match[1] : String(new Date().getFullYear());
}

export function downloadText(filename, content) {
  const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

export function formatRM(value) {
  if (value === null || value === undefined || value === "") return "N/A";
  const num = typeof value === "number" ? value : parseFloat(value);
  if (Number.isNaN(num)) return String(value);
  return `RM${num.toFixed(2)}`;
}
