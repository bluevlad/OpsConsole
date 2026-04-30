import { api } from './client';

export async function listServices() {
  const { data } = await api.get('/api/catalog/services');
  return data;
}

export async function getService(code) {
  const { data } = await api.get(`/api/catalog/services/${encodeURIComponent(code)}`);
  return data;
}

export async function listSections(code) {
  const { data } = await api.get(
    `/api/catalog/services/${encodeURIComponent(code)}/sections`,
  );
  return data;
}

export async function getSection(code, sectionCode) {
  const { data } = await api.get(
    `/api/catalog/services/${encodeURIComponent(code)}/sections/${encodeURIComponent(sectionCode)}`,
  );
  return data;
}

export async function syncCatalog(payload) {
  const { data } = await api.post('/api/catalog/sync', payload);
  return data;
}

// -- P1: My sections / Assignments / Health probe ---------------------------

export async function listMySections() {
  const { data } = await api.get('/api/my/sections');
  return data;
}

export async function listAssignments(sectionId) {
  const { data } = await api.get('/api/assignments', {
    params: sectionId ? { section_id: sectionId } : {},
  });
  return data;
}

export async function createOrUpdateAssignment(payload) {
  const { data } = await api.post('/api/assignments', payload);
  return data;
}

export async function revokeAssignment(assignmentId) {
  await api.delete(`/api/assignments/${assignmentId}`);
}

export async function triggerHealthProbe() {
  const { data } = await api.post('/api/health/probe/run');
  return data;
}

export async function getHealthSnapshots(serviceCode, sectionCode, limit = 50) {
  const { data } = await api.get(
    `/api/health/snapshots/${encodeURIComponent(serviceCode)}/${encodeURIComponent(sectionCode)}`,
    { params: { limit } },
  );
  return data;
}

// -- P2: Change Requests ---------------------------------------------------

export async function listChangeRequests(params = {}) {
  const { data } = await api.get('/api/change-requests', { params });
  return data;
}

export async function getChangeRequest(id) {
  const { data } = await api.get(`/api/change-requests/${id}`);
  return data;
}

export async function createChangeRequest(payload) {
  const { data } = await api.post('/api/change-requests', payload);
  return data;
}

export async function patchChangeRequest(id, payload) {
  const { data } = await api.patch(`/api/change-requests/${id}`, payload);
  return data;
}
