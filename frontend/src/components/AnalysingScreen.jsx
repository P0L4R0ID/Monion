import { useEffect, useState } from 'react'

const STEPS = [
  { label: 'Reading your bill with OCR', delay: 0 },
  { label: 'Matching items against Schedule 13, MOH prices & PAC rules', delay: 4000 },
  { label: 'Checking for legal violations & unbundling', delay: 13000 },
  { label: 'Preparing your action plan & letters', delay: 24000 },
]

export default function AnalysingScreen({ fileName }) {
  const [stepIndex, setStepIndex] = useState(0)

  useEffect(() => {
    const timers = STEPS.slice(1).map((step, i) =>
      setTimeout(() => setStepIndex(i + 1), step.delay)
    )
    return () => timers.forEach(clearTimeout)
  }, [])

  return (
    <div className="max-w-lg mx-auto px-4 py-20 text-center">
      <div className="relative mx-auto mb-8 h-20 w-20">
        <div className="absolute inset-0 rounded-full border-4 border-blue-100" />
        <div className="absolute inset-0 rounded-full border-4 border-blue-600 border-t-transparent animate-spin" />
        <div className="absolute inset-0 flex items-center justify-center">
          <svg className="h-8 w-8 text-blue-600" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75 11.25 15 15 9.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
          </svg>
        </div>
      </div>

      <h2 className="text-xl font-semibold text-gray-900 mb-1">Analysing your bill</h2>
      <p className="text-sm text-gray-500 mb-8 truncate">{fileName}</p>

      <div className="space-y-3 text-left">
        {STEPS.map((step, i) => {
          const isDone = i < stepIndex
          const isActive = i === stepIndex
          return (
            <div
              key={step.label}
              className={`flex items-center gap-3 rounded-lg border px-4 py-3 transition-colors ${
                isActive
                  ? 'border-blue-200 bg-blue-50'
                  : isDone
                  ? 'border-green-100 bg-green-50'
                  : 'border-gray-100 bg-gray-50'
              }`}
            >
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full">
                {isDone ? (
                  <svg className="h-5 w-5 text-green-600" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
                  </svg>
                ) : isActive ? (
                  <span className="h-3 w-3 rounded-full bg-blue-600 animate-pulse" />
                ) : (
                  <span className="h-2 w-2 rounded-full bg-gray-300" />
                )}
              </span>
              <span
                className={`text-sm ${
                  isActive ? 'text-blue-900 font-medium' : isDone ? 'text-green-800' : 'text-gray-400'
                }`}
              >
                {step.label}
              </span>
            </div>
          )
        })}
      </div>

      <p className="text-xs text-gray-400 mt-8">
        This usually takes 30&ndash;60 seconds &mdash; hang tight.
      </p>
    </div>
  )
}
