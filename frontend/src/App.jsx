import { useState } from 'react'
import { Routes, Route } from 'react-router-dom'
import UploadPage from './pages/UploadPage.jsx'
import ResultsPage from './pages/ResultsPage.jsx'

function App() {
  // Full API response from POST /upload, lifted here so both routes can
  // read/write it without prop-drilling through a separate context provider.
  const [billData, setBillData] = useState(null)

  return (
    <div className="min-h-screen bg-gray-50">
      <Routes>
        <Route path="/" element={<UploadPage setBillData={setBillData} />} />
        <Route
          path="/results"
          element={<ResultsPage billData={billData} setBillData={setBillData} />}
        />
      </Routes>
    </div>
  )
}

export default App
