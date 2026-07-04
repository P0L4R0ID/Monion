import { Navigate, useNavigate } from 'react-router-dom'
import FlaggedItemsTable from '../components/FlaggedItemsTable.jsx'
import PatientPackage from '../components/PatientPackage.jsx'
import { formatRM } from '../utils.js'

function bulletsFromString(text) {
  return (text || '')
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => line.replace(/^[-•]\s*/, ''))
}

export default function ResultsPage({ billData, setBillData }) {
  const navigate = useNavigate()

  if (!billData) {
    return <Navigate to="/" replace />
  }

  const handleAnalyseAnother = () => {
    setBillData(null)
    navigate('/')
  }

  const { flags, letter, file_info: fileInfo } = billData
  const { summary, flagged_items: flaggedItems, clean_items: cleanItems } = flags
  const hospitalName = flags.hospital_name
  const billDate = flags.bill_date

  const rightsBullets = bulletsFromString(letter.your_rights)

  return (
    <div className="max-w-4xl mx-auto px-4 py-10 space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Bill Analysis Results</h1>
        <p className="text-gray-500 text-sm mt-1">
          {fileInfo.filename} &middot; {fileInfo.pages} page(s) &middot; {fileInfo.total_lines} line items scanned
        </p>
      </div>

      {/* Summary card */}
      <div className="bg-white shadow rounded-lg p-6">
        <div className="flex flex-wrap gap-6 items-center justify-center text-lg font-semibold">
          <span className="text-red-600">&#x1F534; {summary.red_flags} Serious Concerns</span>
          <span className="text-gray-300">|</span>
          <span className="text-yellow-600">&#x1F7E1; {summary.yellow_flags} Worth Querying</span>
          <span className="text-gray-300">|</span>
          <span className="text-green-600">&#x2705; {cleanItems.length} Clean Items</span>
        </div>
      </div>

      {/* Bill summary */}
      <div className="bg-blue-50 border border-blue-200 rounded-lg p-6">
        <h2 className="font-semibold text-blue-900 mb-2">Bill Summary</h2>
        <p className="text-blue-900 text-sm leading-relaxed">{letter.bill_summary}</p>
      </div>

      {/* Your rights */}
      <div className="bg-blue-50 border border-blue-200 rounded-lg p-6">
        <h2 className="font-semibold text-blue-900 mb-3">Your Rights</h2>
        <ul className="list-disc list-inside space-y-1 text-blue-900 text-sm">
          {rightsBullets.map((bullet, i) => (
            <li key={i}>{bullet}</li>
          ))}
        </ul>
      </div>

      {/* Flagged items table */}
      <div>
        <h2 className="font-semibold text-gray-900 mb-3">Flagged Items</h2>
        <FlaggedItemsTable flaggedItems={flaggedItems} />
      </div>

      {/* Clean items, collapsible */}
      <details className="bg-green-50 border-l-4 border-green-500 rounded-lg p-4">
        <summary className="cursor-pointer font-semibold text-green-800">
          &#x2705; Clean Items ({cleanItems.length}) — no issues found
        </summary>
        <ul className="mt-3 space-y-1 text-sm text-green-900">
          {cleanItems.map((item, i) => (
            <li key={i} className="flex justify-between">
              <span>{item.item_name || 'Unknown item'}</span>
              <span>{formatRM(item.total_price)}</span>
            </li>
          ))}
        </ul>
      </details>

      {/* Action steps */}
      <div className="bg-white shadow rounded-lg p-6">
        <h2 className="font-semibold text-gray-900 mb-3">Action Steps</h2>
        <ol className="list-decimal list-inside space-y-2 text-sm text-gray-800">
          {letter.action_steps.map((step, i) => (
            <li key={i}>{step}</li>
          ))}
        </ol>
      </div>

      {/* Patient package */}
      <div>
        <h2 className="font-semibold text-gray-900 mb-3">Patient Package</h2>
        <PatientPackage letter={letter} hospitalName={hospitalName} billDate={billDate} />
      </div>

      {/* Analyse another bill */}
      <div className="text-center pt-4">
        <button
          type="button"
          onClick={handleAnalyseAnother}
          className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-6 py-3 text-white font-semibold shadow-sm hover:bg-blue-700 hover:shadow-md transition-all"
        >
          <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
            <path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0 3.181 3.183a8.25 8.25 0 0 0 13.803-3.7M4.031 9.865a8.25 8.25 0 0 1 13.803-3.7l3.181 3.182m0-4.991v4.99" />
          </svg>
          Analyse Another Medical Bill
        </button>
      </div>
    </div>
  )
}
