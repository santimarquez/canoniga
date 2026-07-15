import { cpSync, existsSync, mkdirSync, readdirSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = dirname(fileURLToPath(import.meta.url))
const repoRoot = join(root, '../..')
const sourceDir = join(repoRoot, 'src/als_intel/i18n/locales')
const localeTarget = join(root, '../src/i18n/locales')
const assetsSource = join(repoRoot, 'assets')
const publicAssets = join(root, '../public/assets')

const BRAND_FILES = [
  'mtvl-ai-logo.svg',
  'mtvl-ai-logo-lettermark.png',
  'landing-dashboard-mockup.png',
]

if (!existsSync(sourceDir)) {
  console.error(`Locale source not found: ${sourceDir}`)
  process.exit(1)
}

mkdirSync(localeTarget, { recursive: true })
for (const name of readdirSync(sourceDir)) {
  if (!name.endsWith('.json')) continue
  cpSync(join(sourceDir, name), join(localeTarget, name))
}
console.log(`Synced locales to ${localeTarget}`)

if (!existsSync(assetsSource)) {
  console.error(`Assets source not found: ${assetsSource}`)
  process.exit(1)
}

mkdirSync(publicAssets, { recursive: true })
for (const name of BRAND_FILES) {
  const source = join(assetsSource, name)
  if (!existsSync(source)) {
    console.warn(`Skipping missing brand asset: ${name}`)
    continue
  }
  cpSync(source, join(publicAssets, name))
}
console.log(`Synced brand assets to ${publicAssets}`)
