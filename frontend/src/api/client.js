import axios from 'axios';

const baseURL = import.meta.env.VITE_API_BASE_URL || '';

export const api = axios.create({
  baseURL,
  withCredentials: false,
  timeout: 10000,
});

// JWT 인터셉터 — P0 §2 auth 단계에서 활성화
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('opsconsole_jwt');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('opsconsole_jwt');
      // /login 리다이렉트는 §3에서 라우터 연결
    }
    return Promise.reject(err);
  },
);
