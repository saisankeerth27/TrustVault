export type UserRole = 'ADMINISTRATOR' | 'DOCUMENT_OWNER' | 'VIEWER'

export type UserStatus = 'ACTIVE' | 'DISABLED'

export interface User {
  id: string
  name: string
  email: string
  role: UserRole
  status: UserStatus
  created_at: string
}

export interface AuthResponse {
  access_token: string
  token_type: 'bearer'
  expires_in: number
  user: User
}

export interface LoginRequest {
  email: string
  password: string
}
