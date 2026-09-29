import { api, ApiProject } from './client';

export type ImportResult = { projects: number; workItems: number; activities: number; failures: string[] };

/** Imports the prototype's actual localStorage shape into the API without deleting local data. */
export async function importExistingLocalData(): Promise<ImportResult> {
  const result: ImportResult = { projects: 0, workItems: 0, activities: 0, failures: [] };
  const rawItems = JSON.parse(localStorage.getItem('work-os-items') || '[]');
  const rawProjects = JSON.parse(localStorage.getItem('work-os-projects') || '[]');
  const existing = await api.projects(true);
  const byName = new Map(existing.map((project) => [project.name.toLowerCase(), project]));
  const projectRows = rawProjects.length ? rawProjects : [...new Set(rawItems.map((item: any) => item.project))].map((name) => [name, String(name).slice(0, 8).toUpperCase(), '#58745d']);
  for (const row of projectRows) {
    const name = row.name || row[0]; const code = row.code || row[1];
    if (!name || !code || byName.has(name.toLowerCase())) continue;
    try { const created = await api.createProject({ name, code, client_name: row.client || '', description: row.description || '', status: row.status || 'Active', color: row.color || row[2] || '#58745d' }); byName.set(name.toLowerCase(), created); result.projects++; } catch (error) { result.failures.push(`Project ${name}: ${error instanceof Error ? error.message : 'failed'}`); }
  }
  for (const item of rawItems) {
    const project: ApiProject | undefined = byName.get(String(item.project).toLowerCase());
    if (!project) { result.failures.push(`Work item ${item.id || item.title}: project not found`); continue; }
    try {
      const created = await api.createWorkItem({ project_id: project.id, title: item.title, type: item.type || 'Task', priority: item.priority || 'Medium', status: item.status || 'New', source: item.source || 'Other', description: item.description || '', root_cause: item.rootCause, solution: item.solution, testing_notes: item.testing, current_blocker: item.blocker });
      result.workItems++;
      for (const activity of item.activities || []) { await api.addActivity(created.id, { activity_type: activity.kind || 'Comment', note: activity.note || '' }); result.activities++; }
    } catch (error) { result.failures.push(`Work item ${item.id || item.title}: ${error instanceof Error ? error.message : 'failed'}`); }
  }
  return result;
}
