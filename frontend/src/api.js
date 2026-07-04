const API_BASE = "http://localhost:8000";

/**
 * Upload a bill file to the backend for OCR -> match -> flag -> letter
 * generation. Throws an Error whose `.message` and `.hint` mirror the
 * backend's { status: "error", message, hint? } error shape so callers can
 * show both fields directly.
 */
export async function uploadBill(file) {
  const formData = new FormData();
  formData.append("file", file);

  let response;
  try {
    response = await fetch(`${API_BASE}/upload`, {
      method: "POST",
      body: formData,
    });
  } catch {
    const err = new Error(
      "Could not reach the server. Is the backend running on localhost:8000?"
    );
    err.hint = "Start the backend with: uvicorn main:app --reload --port 8000";
    throw err;
  }

  let body;
  try {
    body = await response.json();
  } catch {
    const err = new Error(`Server returned an unexpected response (HTTP ${response.status}).`);
    throw err;
  }

  if (!response.ok || body.status === "error") {
    const err = new Error(body.message || `Request failed (HTTP ${response.status}).`);
    err.hint = body.hint;
    err.step = body.step;
    throw err;
  }

  return body;
}
