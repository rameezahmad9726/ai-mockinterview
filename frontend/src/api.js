// Backend API base URL. Override with REACT_APP_API_URL in .env (e.g. http://localhost:8000)
export const API_BASE = process.env.REACT_APP_API_URL || 'http://localhost:8000';

const TOKEN_KEY = 'interveux_token';

export function getToken() {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* ignore quota errors */
  }
}

export class ApiError extends Error {
  constructor(status, detail, body) {
    super(typeof detail === 'string' ? detail : `HTTP ${status}`);
    this.status = status;
    this.detail = detail;
    this.body = body;
  }
}

/**
 * Fetch helper that attaches the HR JWT (if present) and parses JSON errors
 * into ApiError. Pass `auth: false` to explicitly skip the Authorization header
 * (e.g. for candidate-facing routes that use a path token).
 */
export async function apiFetch(path, options = {}) {
  const { auth = true, headers = {}, body, ...rest } = options;
  const finalHeaders = { ...headers };

  if (auth) {
    const token = getToken();
    if (token) finalHeaders['Authorization'] = `Bearer ${token}`;
  }

  let finalBody = body;
  if (body && !(body instanceof FormData) && typeof body !== 'string') {
    finalHeaders['Content-Type'] = finalHeaders['Content-Type'] || 'application/json';
    finalBody = JSON.stringify(body);
  }

  const url = path.startsWith('http') ? path : `${API_BASE}${path}`;
  const timeoutMs = options.timeoutMs ?? 15000;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  let res;
  try {
    res = await fetch(url, {
      ...rest,
      headers: finalHeaders,
      body: finalBody,
      signal: controller.signal,
    });
  } catch (e) {
    if (e.name === 'AbortError') {
      throw new ApiError(0, 'Request timed out — is the backend running on port 8000?');
    }
    throw new ApiError(0, 'Cannot reach backend — start it with: python backend/main.py');
  } finally {
    clearTimeout(timer);
  }

  const contentType = res.headers.get('content-type') || '';
  const isJson = contentType.includes('application/json');
  const payload = isJson ? await res.json().catch(() => null) : await res.text();

  if (!res.ok) {
    const detail = isJson && payload ? (payload.detail || payload.message || payload) : payload;
    throw new ApiError(res.status, detail, payload);
  }
  return payload;
}
