const API_BASE = (import.meta.env.VITE_API_URL || 'http://localhost:8000/api').replace(/\/$/, '');

const TOKEN_KEY = 'work-os-access-token';

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) { super(message); this.status = status; }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = sessionStorage.getItem(TOKEN_KEY);
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(init?.headers || {}) },
  });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try { const body = await response.json(); message = body.error?.message || body.detail || body.message || message; } catch { /* plain error */ }
    // An expired or revoked session: drop the token and return to the login screen.
    if (response.status === 401 && token && !path.startsWith('/auth/')) {
      sessionStorage.removeItem(TOKEN_KEY);
      window.location.reload();
    }
    throw new ApiError(response.status, message);
  }
  return response.status === 204 ? (undefined as T) : response.json();
}

export type ApiProject = { id: string; name: string; code: string; client_name?: string; description?: string; status: string; color: string; start_date?: string; notes?: string; archived_at?: string; active_work_items?: number; completed_work_items?: number };
export type ApiWorkItem = { id: string; work_item_number: string; workspace_id: string; project_id: string; title: string; description?: string; type: string; priority: string; status: string; source?: string; due_date?: string; root_cause?: string; solution?: string; testing_notes?: string; current_blocker?: string; created_at: string; updated_at: string };

export const api = {
  health: () => request<{ status: string }>('/health'),
  projects: (includeArchived = false) => request<ApiProject[]>(`/projects?include_archived=${includeArchived}`),
  createProject: (data: Omit<ApiProject, 'id'>) => request<ApiProject>('/projects', { method: 'POST', body: JSON.stringify(data) }),
  updateProject: (id: string, data: Omit<ApiProject, 'id'>) => request<ApiProject>(`/projects/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  archiveProject: (id: string) => request<ApiProject>(`/projects/${id}/archive`, { method: 'PATCH' }),
  restoreProject: (id: string) => request<ApiProject>(`/projects/${id}/restore`, { method: 'PATCH' }),
  workItems: (params: Record<string, string | number | undefined> = {}) => { const query = new URLSearchParams(Object.entries(params).filter(([, value]) => value !== undefined).map(([key, value]) => [key, String(value)])); return request<{ items: ApiWorkItem[]; total: number; page: number; page_size: number }>(`/work-items?${query}`); },
  createWorkItem: (data: Partial<ApiWorkItem> & { project_id: string; title: string; type: string; priority: string }) => request<ApiWorkItem>('/work-items', { method: 'POST', body: JSON.stringify(data) }),
  updateWorkItem: (id: string, data: Partial<ApiWorkItem>) => request<ApiWorkItem>(`/work-items/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  changeStatus: (id: string, status: string) => request<ApiWorkItem>(`/work-items/${id}/status?status=${encodeURIComponent(status)}`, { method: 'PATCH' }),
  activities: (id: string) => request<any[]>(`/work-items/${id}/activities`),
  addActivity: (id: string, data: { activity_type: string; note: string }) => request<any>(`/work-items/${id}/activities`, { method: 'POST', body: JSON.stringify(data) }),
  communications: (id: string) => request<any[]>(`/work-items/${id}/communications`),
  addCommunication: (id: string, data: { communication_type: string; contact_id?: string; subject?: string; content: string }) => request<any>(`/work-items/${id}/communications`, { method: 'POST', body: JSON.stringify(data) }),
  contacts: () => request<any[]>('/contacts'),
  createContact: (data: any) => request<any>('/contacts', { method: 'POST', body: JSON.stringify(data) }),
  monthlyReport: () => request<any>('/reports/monthly'),
  analyzeMessage: (data: { content: string; channel: string; sender_name?: string; sender_email?: string }) => request<any>('/message-imports/analyze', { method: 'POST', body: JSON.stringify(data) }),
  commitMessage: (data: { content: string; channel: string; project_id: string; contact_id?: string; sender_name?: string; sender_email?: string; confirm: true }) => request<any>('/message-imports/commit', { method: 'POST', body: JSON.stringify(data) }),
  register: (data: { name: string; email: string; password: string }) => request<any>('/auth/register', { method: 'POST', body: JSON.stringify(data) }),
  login: (data: { email: string; password: string }) => request<any>('/auth/login', { method: 'POST', body: JSON.stringify(data) }),
  me: () => request<any>('/auth/me'),
  logout: () => request<void>('/auth/logout', { method: 'POST' }).finally(() => sessionStorage.removeItem(TOKEN_KEY)),
};
