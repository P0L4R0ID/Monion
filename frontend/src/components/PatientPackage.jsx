import { useState } from 'react'
import { slugify, extractYear, downloadText } from '../utils.js'

export default function PatientPackage({ letter, hospitalName, billDate }) {
  const hospitalSlug = slugify(hospitalName)
  const year = extractYear(billDate)

  const tabs = [
    {
      id: 'letter_en',
      label: 'Letter (EN)',
      content: letter.hospital_letter?.english || '',
      filenameBase: `letter_english_${hospitalSlug}_${year}`,
    },
    {
      id: 'letter_bm',
      label: 'Letter (BM)',
      content: letter.hospital_letter?.bahasa_malaysia || '',
      filenameBase: `letter_bahasa_malaysia_${hospitalSlug}_${year}`,
    },
    {
      id: 'escalation',
      label: 'Escalation Guide',
      content: letter.escalation_guide || '',
      filenameBase: `escalation_guide_${hospitalSlug}_${year}`,
    },
    {
      id: 'script',
      label: 'Phone Script',
      content: letter.verbal_script || '',
      filenameBase: `phone_script_${hospitalSlug}_${year}`,
    },
  ]

  const [activeId, setActiveId] = useState(tabs[0].id)
  const [copied, setCopied] = useState(false)

  const active = tabs.find((t) => t.id === activeId)

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(active.content)
    } catch {
      // navigator.clipboard can reject under restrictive permissions
      // policies (some embedded/iframe contexts, older browsers) --
      // fall back to the legacy execCommand approach via a hidden textarea
      // so the button still works instead of silently doing nothing.
      const textarea = document.createElement('textarea')
      textarea.value = active.content
      textarea.style.position = 'fixed'
      textarea.style.opacity = '0'
      document.body.appendChild(textarea)
      textarea.select()
      document.execCommand('copy')
      document.body.removeChild(textarea)
    }
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const handleDownload = () => {
    downloadText(`${active.filenameBase}.txt`, active.content)
  }

  return (
    <div>
      <div className="flex gap-1 border-b border-gray-200 mb-4 overflow-x-auto">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            type="button"
            onClick={() => { setActiveId(tab.id); setCopied(false) }}
            className={`px-4 py-2 text-sm font-medium whitespace-nowrap border-b-2 transition-colors ${
              activeId === tab.id
                ? 'border-blue-600 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div className="rounded-lg bg-white shadow p-6">
        <div className="flex justify-end gap-2 mb-4">
          <button
            type="button"
            onClick={handleCopy}
            className="rounded-md bg-gray-100 px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-200"
          >
            {copied ? 'Copied!' : 'Copy'}
          </button>
          <button
            type="button"
            onClick={handleDownload}
            className="rounded-md bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700"
          >
            Download .txt
          </button>
        </div>

        <pre className="whitespace-pre-wrap font-sans text-sm text-gray-800 leading-relaxed">
          {active.content}
        </pre>
      </div>
    </div>
  )
}
