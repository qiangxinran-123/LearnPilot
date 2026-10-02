export interface HealthResponse {
  status: string;
  service: string;
}

export interface BackendErrorBody {
  error?: {
    code?: string;
    message?: string;
  };
  detail?: string;
}
