import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import fs from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import { createHash } from 'node:crypto'
import basStyleKit, { CSS_FILE, FAVICONS, IMAGES, cdnBase, prepareAssets, processCss } from './basStyleKit.js'

const CSS_URL = `${cdnBase('1.2.3')}/${CSS_FILE}`
const CSS = `
@font-face{font-family:"Work Sans";src:url(../fonts/work-sans/regular.woff2) format("woff2")}
@font-face{font-family:"Work Sans";font-style:italic;src:url(../fonts/work-sans/italic.woff2) format("woff2")}
.a{background:url("../../images/icons/chevron.svg")}
.b{background:url(/images/grid.png)}
.c{background:url(data:image/png;base64,AAAA)}
`

describe('processCss', () => {
  it('keeps wanted fonts relative so they are bundled, and makes everything else an absolute CDN URL', () => {
    const { css, fonts } = processCss(CSS, CSS_URL, (file) => !/italic/.test(file))
    expect(fonts).toEqual(['../fonts/work-sans/regular.woff2'])
    expect(css).toContain('url(../fonts/work-sans/regular.woff2)')
    expect(css).toContain('url("https://cdn.web.bas.ac.uk/bas-style-kit/1.2.3/fonts/work-sans/italic.woff2")')
    expect(css).toContain('url("https://cdn.web.bas.ac.uk/bas-style-kit/images/icons/chevron.svg")')
    expect(css).toContain('url("https://cdn.web.bas.ac.uk/images/grid.png")')
    expect(css).toContain('url(data:image/png;base64,AAAA)')
  })

  it('bundles every font by default', () => {
    expect(processCss(CSS, CSS_URL).fonts).toHaveLength(2)
  })
})

describe('prepareAssets', () => {
  let cacheDir
  let fetchFn
  const sha = (text) => `sha256-${createHash('sha256').update(text).digest('base64')}`
  const body = (url) => (url.endsWith(CSS_FILE) ? CSS : `content of ${url}`)

  beforeEach(async () => {
    cacheDir = await fs.mkdtemp(path.join(os.tmpdir(), 'bas-kit-'))
    fetchFn = vi.fn(async (url) => ({ ok: true, arrayBuffer: async () => Buffer.from(body(url)) }))
  })

  afterEach(() => fs.rm(cacheDir, { recursive: true, force: true }))

  const options = (extra = {}) => ({ version: '1.2.3', cacheDir, fetchFn, wantFont: (file) => !/italic/.test(file), ...extra })

  it('downloads only what the app needs: the stylesheet, the wanted fonts, the logos and the favicons', async () => {
    const assets = await prepareAssets(options())
    const urls = fetchFn.mock.calls.map(([url]) => url.replace(`${cdnBase('1.2.3')}/`, ''))
    expect(urls.sort()).toEqual(
      [CSS_FILE, 'fonts/work-sans/regular.woff2', ...Object.values(IMAGES), ...FAVICONS.map((f) => `images/bas-favicon/${f}`)].sort(),
    )
    expect(assets.fonts).toEqual(['../fonts/work-sans/regular.woff2'])
    await expect(fs.readFile(assets.cssPath, 'utf8')).resolves.toContain('https://cdn.web.bas.ac.uk/bas-style-kit/images/icons/chevron.svg')
    await expect(fs.readFile(path.join(cacheDir, 'fonts/work-sans/regular.woff2'), 'utf8')).resolves.toContain('regular.woff2')
    expect(Object.keys(assets.images)).toEqual(['roundel32', 'roundel64'])
    expect(Object.keys(assets.favicons)).toEqual(FAVICONS)
  })

  it('uses the cache on the next run instead of downloading again, and downloads again when refreshing', async () => {
    await prepareAssets(options())
    fetchFn.mockClear()
    await prepareAssets(options())
    expect(fetchFn).not.toHaveBeenCalled()
    await prepareAssets(options({ refresh: true }))
    expect(fetchFn).toHaveBeenCalled()
  })

  it('retries a failed download and then reports the url', async () => {
    fetchFn.mockRejectedValueOnce(new Error('offline'))
    await expect(prepareAssets(options())).resolves.toBeDefined()
    fetchFn.mockReset()
    fetchFn.mockResolvedValue({ ok: false, status: 503 })
    await expect(prepareAssets(options({ refresh: true }))).rejects.toThrow(/Could not download .*HTTP 503/)
  })

  it('records hashes when asked to update the lock', async () => {
    const assets = await prepareAssets(options({ updateLock: true }))
    expect(assets.files[CSS_FILE]).toBe(sha(CSS))
    expect(Object.keys(assets.files)).toHaveLength(1 + 1 + 2 + FAVICONS.length)
    expect(assets.warnings).toEqual([])
  })

  it('accepts assets that match the lock', async () => {
    const lock = { files: { [CSS_FILE]: sha(CSS) } }
    const assets = await prepareAssets(options({ lock }))
    // everything else is not in the lock yet: reported, not fatal
    expect(assets.warnings.length).toBeGreaterThan(0)
  })

  it('refuses assets that differ from the lock', async () => {
    const lock = { files: { [CSS_FILE]: sha('something else') } }
    await expect(prepareAssets(options({ lock }))).rejects.toThrow(/does not match cdn-assets\.lock\.json/)
    await expect(fs.stat(path.join(cacheDir, CSS_FILE))).rejects.toThrow()
  })
})

describe('plugin in dev', () => {
  const plugin = basStyleKit({ version: '1.2.3' })
  plugin.configResolved({ command: 'serve', base: '/', root: '.' })

  it('serves the logos and stylesheet from the CDN without downloading anything', async () => {
    await plugin.buildStart()
    expect(plugin.resolveId('virtual:bas-style-kit-assets')).toBe('\0virtual:bas-style-kit-assets')
    expect(plugin.load('\0virtual:bas-style-kit-css')).toBe('export {}')
    const assetsModule = plugin.load('\0virtual:bas-style-kit-assets')
    expect(assetsModule).toContain('export const roundel32 = "https://cdn.web.bas.ac.uk/bas-style-kit/1.2.3/images/bas-logo/bas-roundel-inverse-transparent-32.png"')
    expect(plugin.resolveId('react')).toBeNull()
  })

  it('links the stylesheet and favicons from the CDN in index.html', () => {
    const tags = plugin.transformIndexHtml()
    expect(tags.find((t) => t.attrs.rel === 'stylesheet').attrs.href).toBe(`${cdnBase('1.2.3')}/${CSS_FILE}`)
    expect(tags.find((t) => t.attrs.rel === 'shortcut icon').attrs.href).toBe(`${cdnBase('1.2.3')}/images/bas-favicon/favicon.ico`)
  })
})
