export interface HealthResponse {
  status: string
  service: string
  version: string
}

export interface ApiErrorEnvelope {
  error?: {
    code?: string
    message?: string
  }
}
