import { createHash } from 'node:crypto'
import fs from 'node:fs/promises'
import path from 'node:path'

// BAS Style Kit assets, taken from the BAS CDN rather than kept in the repository.
//
//  - dev server:  the stylesheet, logos and favicons are loaded straight from the CDN, nothing is downloaded.
//  - build:       only the assets the app needs are downloaded (once, into a cache under node_modules), checked
//                 against cdn-assets.lock.json, and bundled into the output so the deployed app doesn't depend on
//                 the CDN at runtime. Fonts that are not needed (see `fonts`) stay as CDN URLs.
//
// Application code imports:
//   import 'virtual:bas-style-kit-css'
//   import { roundel32, roundel64 } from 'virtual:bas-style-kit-assets'

const VIRTUAL_CSS = 'virtual:bas-style-kit-css'
const VIRTUAL_ASSETS = 'virtual:bas-style-kit-assets'

export const CSS_FILE = 'css/bas-style-kit.min.css'
export const IMAGES = {
  roundel32: 'images/bas-logo/bas-roundel-inverse-transparent-32.png',
  roundel64: 'images/bas-logo/bas-roundel-inverse-transparent-64.png',
}
// Emitted with fixed names (bas-favicon/<name>) so the Django template can reference them
export const FAVICONS = ['favicon.ico', 'favicon-16x16.png', 'favicon-32x32.png', 'apple-touch-icon.png', 'safari-pinned-tab.svg']
const FAVICON_DIR = 'images/bas-favicon'

export const cdnBase = (version) => `https://cdn.web.bas.ac.uk/bas-style-kit/${version}`
const sha256 = (buffer) => `sha256-${createHash('sha256').update(buffer).digest('base64')}`

// Splits the stylesheet's url() references into fonts to bundle and everything else. References that are not
// bundled become absolute CDN URLs, so nothing in the CSS is left pointing at a file that isn't there.
export function processCss(css, cssUrl, wantFont = () => true) {
  const fonts = new Set()
  const out = css.replace(/url\(\s*(["']?)([^)"']+)\1\s*\)/g, (match, quote, ref) => {
    if (/^(data:|#)/.test(ref)) return match
    const isFont = /\.woff2?$/.test(ref) && !/^([a-z]+:|\/)/i.test(ref)
    if (isFont && wantFont(ref)) {
      fonts.add(ref)
      return match
    }
    return `url("${new URL(ref, cssUrl).href}")`
  })
  return { css: out, fonts: [...fonts] }
}

async function download(url, fetchFn, attempts = 3) {
  let lastError
  for (let i = 0; i < attempts; i++) {
    try {
      const response = await fetchFn(url)
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      return Buffer.from(await response.arrayBuffer())
    } catch (error) {
      lastError = error
    }
  }
  throw new Error(`Could not download ${url}: ${lastError.message}`)
}

// Downloads (or reads from the cache) every asset the build needs and checks it against the lock.
export async function prepareAssets({
  version,
  cacheDir,
  lock = { files: {} },
  fetchFn = fetch,
  refresh = false,
  updateLock = false,
  wantFont = () => true,
  log = () => {},
}) {
  const base = cdnBase(version)
  const files = { ...lock.files }
  const warnings = []

  const fetchCached = async (relative, transform) => {
    const target = path.join(cacheDir, relative)
    let buffer = null
    if (!refresh) buffer = await fs.readFile(target).catch(() => null)
    if (!buffer) {
      log(`downloading ${base}/${relative}`)
      buffer = await download(`${base}/${relative}`, fetchFn)
    }

    const hash = sha256(buffer)
    if (lock.files[relative] && lock.files[relative] !== hash) {
      await fs.rm(target, { force: true })
      throw new Error(`BAS Style Kit asset ${relative} does not match cdn-assets.lock.json (delete the cache and run with CDN_ASSETS_UPDATE_LOCK=1 if the change is expected)`)
    }
    if (!lock.files[relative]) {
      if (updateLock) files[relative] = hash
      else warnings.push(`${relative} is not in cdn-assets.lock.json (run with CDN_ASSETS_UPDATE_LOCK=1 to add it)`)
    }

    await fs.mkdir(path.dirname(target), { recursive: true })
    await fs.writeFile(target, buffer)
    return transform ? transform(buffer) : buffer
  }

  // Stylesheet: keep the original in the cache (its hash is what is locked), bundle a rewritten copy
  const cssBuffer = await fetchCached(CSS_FILE)
  const { css, fonts } = processCss(cssBuffer.toString('utf8'), `${base}/${CSS_FILE}`, wantFont)
  const cssPath = path.join(cacheDir, 'css', 'bundled.css')
  await fs.writeFile(cssPath, css)

  for (const font of fonts) await fetchCached(path.posix.normalize(path.posix.join('css', font)))
  const images = {}
  for (const [name, relative] of Object.entries(IMAGES)) {
    await fetchCached(relative)
    images[name] = path.join(cacheDir, relative)
  }
  const favicons = {}
  for (const name of FAVICONS) {
    await fetchCached(`${FAVICON_DIR}/${name}`)
    favicons[name] = path.join(cacheDir, FAVICON_DIR, name)
  }

  return { cssPath, images, favicons, fonts, files, warnings }
}

export default function basStyleKit({ version = '0.7.4', lockFile = 'cdn-assets.lock.json', fonts: wantFont = (file) => !/italic/.test(file) } = {}) {
  let config
  let assets = null
  const cdn = cdnBase(version)

  return {
    name: 'bas-style-kit',

    configResolved(resolved) {
      config = resolved
    },

    async buildStart() {
      if (config.command !== 'build') return
      const lockPath = path.resolve(config.root, lockFile)
      const lock = JSON.parse(await fs.readFile(lockPath, 'utf8').catch(() => '{"files":{}}'))
      const updateLock = Boolean(process.env.CDN_ASSETS_UPDATE_LOCK)

      assets = await prepareAssets({
        version,
        cacheDir: path.resolve(config.root, 'node_modules/.cache/bas-style-kit', version),
        lock,
        refresh: Boolean(process.env.BAS_STYLE_KIT_REFRESH),
        updateLock,
        wantFont,
        log: (message) => config.logger.info(`[bas-style-kit] ${message}`),
      })
      assets.warnings.forEach((warning) => config.logger.warn(`[bas-style-kit] ${warning}`))
      if (updateLock) {
        await fs.writeFile(lockPath, JSON.stringify({ version, files: Object.fromEntries(Object.entries(assets.files).sort()) }, null, 2) + '\n')
      }
    },

    resolveId(id) {
      if (id === VIRTUAL_CSS || id === VIRTUAL_ASSETS) return `\0${id}`
      return null
    },

    load(id) {
      if (id === `\0${VIRTUAL_CSS}`) {
        // Dev: the stylesheet is linked from the CDN in index.html instead
        return assets ? `import ${JSON.stringify(assets.cssPath)}` : 'export {}'
      }
      if (id === `\0${VIRTUAL_ASSETS}`) {
        return Object.entries(IMAGES)
          .map(([name, relative]) =>
            assets ? `import ${name} from ${JSON.stringify(assets.images[name])}\nexport { ${name} }` : `export const ${name} = ${JSON.stringify(`${cdn}/${relative}`)}`,
          )
          .join('\n')
      }
      return null
    },

    transformIndexHtml() {
      const href = (name) => (assets ? `${config.base}bas-favicon/${name}` : `${cdn}/${FAVICON_DIR}/${name}`)
      const tags = [
        { tag: 'meta', attrs: { name: 'theme-color', content: '#222222' }, injectTo: 'head' },
        { tag: 'link', attrs: { rel: 'shortcut icon', href: href('favicon.ico') }, injectTo: 'head' },
        { tag: 'link', attrs: { rel: 'apple-touch-icon', sizes: '180x180', href: href('apple-touch-icon.png') }, injectTo: 'head' },
        { tag: 'link', attrs: { rel: 'icon', type: 'image/png', sizes: '32x32', href: href('favicon-32x32.png') }, injectTo: 'head' },
        { tag: 'link', attrs: { rel: 'icon', type: 'image/png', sizes: '16x16', href: href('favicon-16x16.png') }, injectTo: 'head' },
        { tag: 'link', attrs: { rel: 'mask-icon', href: href('safari-pinned-tab.svg'), color: '#222222' }, injectTo: 'head' },
      ]
      if (!assets) tags.unshift({ tag: 'link', attrs: { rel: 'stylesheet', href: `${cdn}/${CSS_FILE}`, crossorigin: 'anonymous' }, injectTo: 'head-prepend' })
      return tags
    },

    async generateBundle() {
      if (!assets) return
      for (const name of FAVICONS) {
        this.emitFile({ type: 'asset', fileName: `bas-favicon/${name}`, source: await fs.readFile(assets.favicons[name]) })
      }
    },
  }
}
