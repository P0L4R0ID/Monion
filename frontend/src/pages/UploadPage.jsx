import { useCallback, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { uploadBill } from '../api.js'
import AnalysingScreen from '../components/AnalysingScreen.jsx'

const ALLOWED_EXTENSIONS = ['.pdf', '.jpg', '.jpeg', '.png']

function getExtension(filename) {
  const idx = filename.lastIndexOf('.')
  return idx === -1 ? '' : filename.slice(idx).toLowerCase()
}

function formatFileSize(bytes) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

const FEATURE_PILLS = [
  'PHFSA Schedule 13',
  'PAC-verified rules',
  'Free & instant',
]

export default function UploadPage({ setBillData }) {
  const navigate = useNavigate()
  const fileInputRef = useRef(null)

  const [file, setFile] = useState(null)
  const [fileError, setFileError] = useState('')
  const [isDragging, setIsDragging] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [apiError, setApiError] = useState(null)

  const validateAndSetFile = useCallback((candidate) => {
    if (!candidate) return
    const ext = getExtension(candidate.name)
    if (!ALLOWED_EXTENSIONS.includes(ext)) {
      setFile(null)
      setFileError(`File type "${ext || 'unknown'}" not supported. Upload PDF, JPG, or PNG.`)
      return
    }
    setFileError('')
    setApiError(null)
    setFile(candidate)
  }, [])

  const handleDrop = useCallback((e) => {
    e.preventDefault()
    setIsDragging(false)
    const dropped = e.dataTransfer.files?.[0]
    validateAndSetFile(dropped)
  }, [validateAndSetFile])

  const handleDragOver = useCallback((e) => {
    e.preventDefault()
    setIsDragging(true)
  }, [])

  const handleDragLeave = useCallback((e) => {
    e.preventDefault()
    setIsDragging(false)
  }, [])

  const handleFilePicked = useCallback((e) => {
    validateAndSetFile(e.target.files?.[0])
  }, [validateAndSetFile])

  const handleAnalyse = useCallback(async () => {
    if (!file) return
    setIsLoading(true)
    setApiError(null)
    try {
      const result = await uploadBill(file)
      setBillData(result)
      navigate('/results')
    } catch (err) {
      setApiError(err)
    } finally {
      setIsLoading(false)
    }
  }, [file, navigate, setBillData])

  if (isLoading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-blue-50 via-white to-indigo-50 flex items-center">
        <AnalysingScreen fileName={file?.name} />
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-white to-indigo-50">
      <div className="max-w-2xl mx-auto px-4 py-16 sm:py-20">
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center h-14 w-14 rounded-2xl bg-blue-600 shadow-lg shadow-blue-200 mb-4">
            <svg className="h-7 w-7 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75 11.25 15 15 9.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
            </svg>
          </div>
          <h1 className="text-4xl font-bold tracking-tight text-gray-900 mb-3">Monion</h1>
          <p className="text-gray-600 max-w-md mx-auto">
            Upload your Malaysian hospital bill to check for overcharges, unbundling, and
            legal fee violations.
          </p>
          <div className="flex flex-wrap justify-center gap-2 mt-5">
            {FEATURE_PILLS.map((pill) => (
              <span
                key={pill}
                className="inline-flex items-center rounded-full bg-white px-3 py-1 text-xs font-medium text-blue-700 border border-blue-100 shadow-sm"
              >
                {pill}
              </span>
            ))}
          </div>
        </div>

        <div className="bg-white rounded-2xl shadow-xl shadow-gray-200/60 p-6 sm:p-8">
          <div
            onDrop={handleDrop}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            className={`rounded-xl border-2 border-dashed p-10 text-center transition-all ${
              isDragging
                ? 'border-blue-500 bg-blue-50 scale-[1.01]'
                : 'border-gray-200 bg-gray-50/50 hover:border-blue-300 hover:bg-blue-50/30'
            }`}
          >
            <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-blue-50">
              <svg className="h-7 w-7 text-blue-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5M16.5 8.25 12 3.75m0 0L7.5 8.25M12 3.75v13.5" />
              </svg>
            </div>
            <p className="text-gray-600 mb-4">Drag and drop your bill here, or</p>
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              className="rounded-lg bg-blue-600 px-5 py-2.5 text-white font-medium shadow-sm hover:bg-blue-700 hover:shadow transition-all"
            >
              Choose File
            </button>
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.jpg,.jpeg,.png"
              onChange={handleFilePicked}
              className="hidden"
            />
            <p className="text-xs text-gray-400 mt-4">PDF, JPG, or PNG only &middot; max 10MB</p>
          </div>

          {fileError && (
            <div className="mt-4 rounded-lg bg-red-50 border-l-4 border-red-500 p-4 text-red-700 text-sm">
              {fileError}
            </div>
          )}

          {file && !fileError && (
            <div className="mt-4 rounded-lg bg-blue-50/60 border border-blue-100 p-4 flex items-center justify-between">
              <div className="flex items-center gap-3 min-w-0">
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-white shadow-sm">
                  <svg className="h-5 w-5 text-blue-600" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 0 0-3.375-3.375h-1.5A1.125 1.125 0 0 1 13.5 7.125v-1.5a3.375 3.375 0 0 0-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 0 0-9-9Z" />
                  </svg>
                </span>
                <div className="min-w-0">
                  <p className="font-medium text-gray-900 truncate">{file.name}</p>
                  <p className="text-sm text-gray-500">{formatFileSize(file.size)}</p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => { setFile(null); setApiError(null) }}
                className="text-sm text-gray-400 hover:text-gray-600 shrink-0 ml-3"
              >
                Remove
              </button>
            </div>
          )}

          {apiError && (
            <div className="mt-4 rounded-lg bg-red-50 border-l-4 border-red-500 p-4">
              <p className="text-red-700 font-medium">{apiError.message}</p>
              {apiError.hint && (
                <p className="text-red-600 text-sm mt-1">{apiError.hint}</p>
              )}
            </div>
          )}

          <button
            type="button"
            onClick={handleAnalyse}
            disabled={!file}
            className="mt-6 w-full rounded-lg bg-blue-600 px-4 py-3.5 text-white font-semibold shadow-sm hover:bg-blue-700 hover:shadow-md disabled:bg-gray-200 disabled:text-gray-400 disabled:shadow-none disabled:cursor-not-allowed transition-all"
          >
            Analyse Bill
          </button>
        </div>

        <p className="text-center text-xs text-gray-400 mt-6">
          Checks against 2,174 procedures under PHFSA Schedule 13, parliamentary PAC findings, and MOH drug price references.
        </p>
      </div>
    </div>
  )
}
