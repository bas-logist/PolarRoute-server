import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, cancelJob, getRoute, requestRoute } from './client'

const mockFetch = (status, body) => {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: body === undefined ? () => Promise.reject(new Error('no body')) : () => Promise.resolve(body),
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

afterEach(() => vi.unstubAllGlobals())

describe('api client', () => {
  it('returns parsed JSON for successful requests', async () => {
    const fetchMock = mockFetch(200, { routes: [] })
    await expect(getRoute(5)).resolves.toEqual({ routes: [] })
    expect(fetchMock).toHaveBeenCalledWith('/api/route/5', expect.objectContaining({ method: 'GET' }))
  })

  it('sends JSON bodies for POST requests', async () => {
    const fetchMock = mockFetch(202, { id: 'abc' })
    await requestRoute({ start_lat: 1 })
    const [, options] = fetchMock.mock.calls[0]
    expect(options.method).toBe('POST')
    expect(options.headers).toEqual({ 'Content-Type': 'application/json' })
    expect(options.body).toBe('{"start_lat":1}')
  })

  it('throws an ApiError carrying the server error message', async () => {
    mockFetch(404, { error: 'Job with id x not found.' })
    await expect(cancelJob('x')).rejects.toMatchObject({ name: 'ApiError', status: 404, message: 'Job with id x not found.' })
  })

  it('throws a generic ApiError when the error body is not JSON', async () => {
    mockFetch(502, undefined)
    const error = await getRoute(1).catch((e) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect(error.message).toContain('502')
  })
})
