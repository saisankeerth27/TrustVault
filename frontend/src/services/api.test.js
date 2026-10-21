import { AxiosError } from 'axios'
import { describe, expect, it } from 'vitest'
import { getApiErrorMessage } from '@/services/api'

function axiosError({ status = 500, data = {}, code = 'ERR_BAD_REQUEST', response = true } = {}) {
  return new AxiosError(
    'Request failed',
    code,
    {},
    {},
    response
      ? {
          status,
          data,
          statusText: '',
          headers: {},
          config: {},
        }
      : undefined,
  )
}

describe('getApiErrorMessage', () => {
  it('includes safe validation field messages without raw input values', () => {
    const error = axiosError({
      status: 422,
      data: {
        error: {
          code: 'validation_error',
          message: 'Request validation failed.',
          details: [
            {
              loc: ['body', 'password'],
              msg: 'Password is too short.',
              input: 'secret-password',
            },
            {
              loc: ['body', 'password'],
              msg: 'Password is too short.',
              input: 'secret-password',
            },
            { loc: ['body', 'email'], msg: 'Enter a valid email address.' },
          ],
        },
      },
    })

    expect(getApiErrorMessage(error)).toBe(
      'Request validation failed. password: Password is too short. email: Enter a valid email address.',
    )
    expect(getApiErrorMessage(error)).not.toContain('secret-password')
  })

  it('returns the backend error message when there are no validation details', () => {
    const error = axiosError({
      status: 409,
      data: {
        error: {
          code: 'conflict',
          message: 'An account with this email cannot be created.',
        },
      },
    })

    expect(getApiErrorMessage(error)).toBe(
      'An account with this email cannot be created.',
    )
  })

  it('reports timeouts and network failures', () => {
    expect(getApiErrorMessage(axiosError({ code: 'ECONNABORTED' }))).toBe(
      'The request timed out. Please try again.',
    )
    expect(
      getApiErrorMessage(axiosError({ code: 'ERR_NETWORK', response: false })),
    ).toContain('Unable to reach the TrustVault API')
  })
})
