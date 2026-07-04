import { useState } from 'react'
import { formatRM } from '../utils.js'

const SEVERITY_STYLES = {
  red: {
    row: 'bg-red-50 border-l-4 border-red-500',
    badge: 'bg-red-100 text-red-700',
    icon: '\u{1F534}',
  },
  yellow: {
    row: 'bg-yellow-50 border-l-4 border-yellow-400',
    badge: 'bg-yellow-100 text-yellow-800',
    icon: '\u{1F7E1}',
  },
}

const GRID_COLS = 'grid-cols-[2fr_1fr_2.8fr_1.6fr]'

/**
 * Flattens flagged_items (each carrying a "flags" list, since one item can
 * have multiple flags at different severities) into one row per flag --
 * Message and Source are per-flag values, not per-item ones, so a single
 * item with 3 flags renders as 3 rows. Flag type is shown only in the
 * expanded detail view, not as its own column.
 */
function flattenToRows(flaggedItems) {
  const rows = []
  for (const item of flaggedItems) {
    for (const flag of item.flags || []) {
      rows.push({ item, flag })
    }
  }
  // Red flags first, then yellow.
  return rows.sort((a, b) => (a.flag.severity === b.flag.severity ? 0 : a.flag.severity === 'red' ? -1 : 1))
}

export default function FlaggedItemsTable({ flaggedItems }) {
  const [expanded, setExpanded] = useState(() => new Set())

  const rows = flattenToRows(flaggedItems || [])

  const toggleRow = (key) => {
    setExpanded((prev) => {
      const next = new Set(prev)
      next.has(key) ? next.delete(key) : next.add(key)
      return next
    })
  }

  if (rows.length === 0) {
    return <p className="text-gray-500 text-sm">No flagged items.</p>
  }

  return (
    <div className="rounded-lg border border-gray-200 overflow-hidden">
      <div className={`grid ${GRID_COLS} gap-3 px-4 py-2 bg-gray-100 text-xs font-semibold text-gray-500 uppercase`}>
        <span>Item Name</span>
        <span>Billed (RM)</span>
        <span>Message</span>
        <span>Source</span>
      </div>

      <div className="divide-y divide-gray-200">
        {rows.map(({ item, flag }, i) => {
          const key = `${item.matched_id || item.item_name}-${flag.flag_type}-${i}`
          const style = SEVERITY_STYLES[flag.severity] || SEVERITY_STYLES.yellow
          const isOpen = expanded.has(key)

          return (
            <div key={key}>
              <button
                type="button"
                onClick={() => toggleRow(key)}
                className={`grid ${GRID_COLS} gap-3 px-4 py-3 w-full text-left text-sm items-start ${style.row}`}
              >
                <span className="font-medium text-gray-900">{item.item_name || 'Unknown item'}</span>
                <span className="text-gray-700">{formatRM(item.total_price)}</span>
                <span className="text-gray-700 truncate">{flag.message}</span>
                <span className="text-gray-500 text-xs">{flag.source}</span>
              </button>

              {isOpen && (
                <div className={`px-4 py-3 text-sm ${flag.severity === 'red' ? 'bg-red-50' : 'bg-yellow-50'} border-t border-gray-200`}>
                  <span className={`inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs font-medium mb-2 ${style.badge}`}>
                    {style.icon} {flag.flag_type}
                  </span>
                  <p className="text-gray-800 mb-2">
                    <span className="font-semibold">Full message: </span>
                    {flag.message}
                  </p>
                  <p className="text-gray-800">
                    <span className="font-semibold">What to do: </span>
                    {flag.action}
                  </p>
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
