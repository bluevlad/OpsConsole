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
