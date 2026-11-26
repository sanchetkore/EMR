import axios from 'axios';
import { useAuthStore } from '../store/authStore';

// API Base URL - use 192.168.1.199:9000 for testing
export const API_BASE_URL = 'http://192.168.1.199:9000';

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Concurrent 401 responses must share one refresh: refresh tokens are single-use.
let refreshInFlight: Promise<string> | null = null;

apiClient.interceptors.request.use((config) => {
  const { token } = useAuthStore.getState();
  if (token && config.headers) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    if (error.response?.status === 401 && originalRequest && !originalRequest._retry) {
      originalRequest._retry = true;

      const { refreshToken, updateTokens, logout } = useAuthStore.getState();

      if (refreshToken) {
        try {
          // A late response may belong to the token already replaced by a refresh.
          const currentToken = useAuthStore.getState().token;
          let accessToken = currentToken;
          if (!currentToken || originalRequest.headers.Authorization === `Bearer ${currentToken}`) {
            if (!refreshInFlight) {
              refreshInFlight = axios.post(`${API_BASE_URL}/api/auth/refresh`, {
                refresh_token: refreshToken,
              }).then(({ data }) => {
                if (useAuthStore.getState().refreshToken !== refreshToken) {
                  throw new Error('Session changed during refresh');
                }
                updateTokens(data.access_token, data.refresh_token);
                return data.access_token as string;
              }).finally(() => { refreshInFlight = null; });
            }
            accessToken = await refreshInFlight;
          }
          originalRequest.headers.Authorization = `Bearer ${accessToken}`;
          return apiClient(originalRequest);
        } catch (refreshError) {
          // If refresh token is invalid or expired
          if (useAuthStore.getState().refreshToken === refreshToken) logout();
          return Promise.reject(refreshError);
        }
      } else {
        logout();
      }
    }

    return Promise.reject(error);
  }
);
