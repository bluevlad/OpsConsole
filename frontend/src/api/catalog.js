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

// -- P3: Content Blocks ----------------------------------------------------

export async function listSectionBlocks(serviceCode, sectionCode, locale = 'ko') {
  const { data } = await api.get(
    `/api/content/sections/${encodeURIComponent(serviceCode)}/${encodeURIComponent(sectionCode)}/blocks`,
    { params: { locale } },
  );
  return data;
}

export async function getContentBlock(blockId) {
  const { data } = await api.get(`/api/content/blocks/${blockId}`);
  return data;
}

export async function saveDraft(serviceCode, sectionCode, key, body, locale = 'ko') {
  const { data } = await api.put(
    `/api/content/sections/${encodeURIComponent(serviceCode)}/${encodeURIComponent(sectionCode)}/blocks/${encodeURIComponent(key)}/draft`,
    { body, locale },
  );
  return data;
}

export async function requestReview(blockId, reviewerEmail) {
  const { data } = await api.post(
    `/api/content/blocks/${blockId}/request-review`,
    reviewerEmail ? { reviewer_email: reviewerEmail } : {},
  );
  return data;
}

export async function approveBlock(blockId, note) {
  const { data } = await api.post(
    `/api/content/blocks/${blockId}/approve`,
    note ? { note } : {},
  );
  return data;
}

export async function rejectBlock(blockId, note) {
  const { data } = await api.post(
    `/api/content/blocks/${blockId}/reject`,
    note ? { note } : {},
  );
  return data;
}

export async function publishBlock(blockId) {
  const { data } = await api.post(`/api/content/blocks/${blockId}/publish`);
  return data;
}

export async function listVersions(blockId) {
  const { data } = await api.get(`/api/content/blocks/${blockId}/versions`);
  return data;
}

// -- P4: Device Code OAuth --------------------------------------------------

export async function lookupDeviceCode(userCode) {
  const { data } = await api.get('/api/auth/device/lookup', { params: { user_code: userCode } });
  return data;
}

export async function approveDeviceCode(userCode) {
  const { data } = await api.post('/api/auth/device/approve', { user_code: userCode });
  return data;
}
