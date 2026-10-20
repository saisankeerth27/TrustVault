let accessToken = null
const listeners = new Set()

export function getAccessToken() {
  return accessToken
}

export function setAccessToken(token) {
  accessToken = token
  for (const listener of listeners) {
    listener(token)
  }
}

export function subscribeToAccessToken(listener) {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}
