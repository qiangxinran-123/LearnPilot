import axios, { type AxiosInstance, type AxiosRequestConfig } from 'axios';

import type { BackendErrorBody, HealthResponse } from '@/types/api';

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || '/api';

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

function isBackendErrorBody(value: unknown): value is BackendErrorBody {
  if (!isRecord(value)) {
    return false;
  }

  const error = value.error;
  return error === undefined || isRecord(error);
}

export class ApiError extends Error {
  public readonly code?: string;
  public readonly status?: number;

  public constructor(message: string, options: { code?: string; status?: number } = {}) {
    super(message);
    this.name = 'ApiError';
    this.code = options.code;
    this.status = options.status;
  }
}

export function normalizeApiError(error: unknown): ApiError {
  if (error instanceof ApiError) {
    return error;
  }

  if (axios.isAxiosError<BackendErrorBody>(error)) {
    const response = error.response;
    const body = response?.data;
    if (isBackendErrorBody(body)) {
      const message = body.error?.message || body.detail || '请求未能完成，请稍后重试。';
      return new ApiError(message, {
        code: body.error?.code,
        status: response?.status,
      });
    }

    if (error.code === 'ECONNABORTED') {
      return new ApiError('请求超时，请稍后重试。');
    }

    if (!response) {
      return new ApiError('无法连接到服务，请确认后端已启动。');
    }

    return new ApiError('请求未能完成，请稍后重试。', { status: response.status });
  }

  return new ApiError('发生未知错误，请稍后重试。');
}

function createApiClient(): AxiosInstance {
  const client = axios.create({
    baseURL: apiBaseUrl,
    timeout: 45_000,
  });

  client.interceptors.response.use(
    (response) => response,
    (error: unknown) => Promise.reject(normalizeApiError(error)),
  );

  return client;
}

const client = createApiClient();

export const httpClient = {
  async get<T>(path: string, options?: Pick<AxiosRequestConfig, 'params'>): Promise<T> {
    const response = await client.get<T>(path, options);
    return response.data;
  },

  async post<T>(
    path: string,
    payload?: unknown,
    options?: Pick<AxiosRequestConfig, 'timeout'>,
  ): Promise<T> {
    const response = await client.post<T>(path, payload, options);
    return response.data;
  },

  async patch<T>(path: string, payload: unknown): Promise<T> {
    const response = await client.patch<T>(path, payload);
    return response.data;
  },

  async delete<T>(path: string): Promise<T> {
    const response = await client.delete<T>(path);
    return response.data;
  },

  async postForm<T>(path: string, formData: FormData): Promise<T> {
    const response = await client.post<T>(path, formData);
    return response.data;
  },
};

export async function requestHealth(): Promise<HealthResponse> {
  try {
    const response = await axios.get<HealthResponse>('/health', { timeout: 5_000 });
    return response.data;
  } catch (error: unknown) {
    throw normalizeApiError(error);
  }
}
