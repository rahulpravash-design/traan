// Scripted screen recording of the Find loop for the demo video (docs/demo/README.md).
//   NODE_PATH=$(npm root -g) node docs/demo/record.cjs <outdir> <scenario.json>
// scenario.json = {"alert": [lat, lon], "victims": [[lat, lon], ...], "max_s": 420}
// Plays the operator: drops the alert pin at the reported location, then for each detection
// confirms it if it is within 40 m of a hidden victim and rejects it otherwise (a false alarm).
const fs = require('fs')
const { chromium } = require('playwright')

const [outdir, scnPath] = process.argv.slice(2)
const scn = JSON.parse(fs.readFileSync(scnPath, 'utf8'))
const DASH = process.env.TRAAN_DASHBOARD ?? 'http://localhost:5173'
const API = process.env.TRAAN_API ?? 'http://localhost:8000'
const t0 = Date.now()
const log = (...a) => console.log(((Date.now() - t0) / 1000).toFixed(1).padStart(6), ...a)
const metres = ([a, b], [c, d]) => Math.hypot((a - c) * 111320, (b - d) * 111320 * Math.cos((a * Math.PI) / 180))

;(async () => {
  const browser = await chromium.launch({ args: ['--use-gl=swiftshader', '--enable-unsafe-swiftshader'] })
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 720 }, recordVideo: { dir: outdir, size: { width: 1280, height: 720 } } })
  const page = await ctx.newPage()
  await page.route('**/tile.openstreetmap.org/**', (r) => r.abort())   // offline basemap only
  await page.goto(DASH)
  await page.waitForFunction(() => window.__traanMap && window.__traanMap.getSource('basemap'), null, { timeout: 30000 })
  await page.waitForTimeout(4000)
  log('MARK intro')

  // operator drops the alert pin where the call came from
  await page.click('button.primary')
  await page.waitForTimeout(1200)
  const pt = await page.evaluate(([lat, lon]) => {
    const p = window.__traanMap.project([lon, lat])
    const r = window.__traanMap.getCanvas().getBoundingClientRect()
    return { x: r.left + p.x, y: r.top + p.y }
  }, scn.alert)
  await page.mouse.move(pt.x, pt.y, { steps: 15 })
  await page.mouse.click(pt.x, pt.y)
  log('MARK pin')

  const decided = new Set()
  let confirmed = 0, stopAt = null
  while ((Date.now() - t0) / 1000 < (scn.max_s ?? 420)) {
    await page.waitForTimeout(1000)
    const dets = await (await fetch(`${API}/events?type=detection&limit=5000`)).json()
    const latest = {}
    for (const d of dets) latest[d.id] = d
    for (const d of Object.values(latest)) {
      if (d.status !== 'pending' || decided.has(d.id)) continue
      decided.add(d.id)
      const real = scn.victims.some((v) => metres(v, [d.lat, d.lon]) < 40)
      await page.waitForTimeout(3500)                           // operator looks at the frame
      const card = page.locator('.det.pending').filter({ hasText: `#${d.id}` })
      await card.locator(real ? 'button.confirm' : 'button:not(.confirm)').click()
      log(`MARK ${real ? 'confirm' : 'reject'} #${d.id} conf=${d.conf}`)
      if (real && ++confirmed === 1) stopAt = Date.now() + 25000  // keep filming the search a little longer
    }
    if (stopAt && Date.now() > stopAt) break
  }
  log('MARK end')
  await ctx.close()
  await browser.close()
})()
