let csrf = ''
export async function api(url, { method = 'GET', body, signal } = {}) {
  const target = new URL(url, location.origin)
  if (target.origin !== location.origin) throw new Error('Adresse API non autorisée.')
  const writing = !['GET', 'HEAD', 'OPTIONS'].includes(method)
  if (writing && !csrf) csrf = (await api('/api/auth/csrf/')).csrf_token
  const response = await fetch(target.pathname + target.search, {
    method, signal, credentials: 'same-origin',
    headers: { Accept: 'application/json', ...(writing ? {'X-CSRFToken': csrf} : {}), ...(body !== undefined ? {'Content-Type': 'application/json'} : {}) },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  const data = await response.json().catch(() => null)
  if (!response.ok) {
    if (response.status === 403) csrf = ''
    const flatten = value => typeof value === 'string' ? value : Array.isArray(value) ? value.map(flatten).join(' ') : value && typeof value === 'object' ? Object.entries(value).map(([k,v]) => `${k === 'detail' ? '' : k + ' : '}${flatten(v)}`).join('\n') : ''
    const error = new Error(flatten(data) || `La requête a échoué (${response.status}).`)
    error.status = response.status
    throw error
  }
  if (data?.csrf_token) csrf = data.csrf_token
  return data
}
// DRF peut construire ses URL avec l'hôte interne du proxy Vite.
export function paginationPath(url) {
  if (!url) return null
  const parsed = new URL(url, location.origin)
  if (!parsed.pathname.startsWith('/api/explorations/')) throw new Error('Pagination invalide.')
  return parsed.pathname + parsed.search
}
