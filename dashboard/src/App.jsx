import { useEffect, useMemo, useRef, useState } from 'react'
import maplibregl from 'maplibre-gl'
import { API, PERCEPTION } from './config.js'
import { heatmapGeoJSON, makeGrid } from './grid.js'
import { useEvents } from './useEvents.js'

const EMPTY = { type: 'FeatureCollection', features: [] }
const BASEMAP = {
  version: 8,
  glyphs: 'https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf',
  sources: {
    osm: {
      type: 'raster',
      tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
      tileSize: 256,
      attribution: '© OpenStreetMap contributors',
    },
  },
  layers: [{ id: 'osm', type: 'raster', source: 'osm', paint: { 'raster-saturation': -0.6, 'raster-opacity': 0.85 } }],
}

async function command(path, body) {
  const r = await fetch(`${API}/commands/${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ by: 'operator', ...body }),
  })
  if (!r.ok) alert(`${path} failed: ${r.status} ${await r.text()}`)
}

export default function App() {
  const { drones, detections, map: mapUpdate, connected } = useEvents()
  const [world, setWorld] = useState(null)
  const [pinMode, setPinMode] = useState(false)
  const pinModeRef = useRef(false)
  const mapRef = useRef(null)
  const containerRef = useRef(null)
  const [ready, setReady] = useState(false)
  const grid = useMemo(() => (world ? makeGrid(world) : null), [world])

  useEffect(() => {
    fetch(`${API}/world`).then((r) => r.json()).then(setWorld).catch(() => setTimeout(() => setWorld(null), 2000))
  }, [connected])

  useEffect(() => {
    pinModeRef.current = pinMode
    if (mapRef.current) mapRef.current.getCanvas().style.cursor = pinMode ? 'crosshair' : ''
  }, [pinMode])

  // create the map once
  useEffect(() => {
    const m = new maplibregl.Map({ container: containerRef.current, style: BASEMAP, center: [76.7, 11.41], zoom: 14 })
    m.addControl(new maplibregl.NavigationControl(), 'top-right')
    m.on('load', () => {
      for (const id of ['outline', 'nofly', 'heat', 'drones', 'detections']) m.addSource(id, { type: 'geojson', data: EMPTY })
      m.addLayer({
        id: 'heat', type: 'fill', source: 'heat',
        paint: {
          // sequential, one hue light -> dark
          'fill-color': ['interpolate', ['linear'], ['get', 'rel'], 0, '#fde3cf', 0.5, '#eb6834', 1, '#8a2a0b'],
          'fill-opacity': ['interpolate', ['linear'], ['get', 'rel'], 0, 0.15, 1, 0.7],
        },
      })
      m.addLayer({ id: 'outline', type: 'line', source: 'outline', paint: { 'line-color': '#52514e', 'line-width': 1.5, 'line-dasharray': [3, 2] } })
      m.addLayer({ id: 'nofly-fill', type: 'fill', source: 'nofly', paint: { 'fill-color': '#e34948', 'fill-opacity': 0.12 } })
      m.addLayer({ id: 'nofly-line', type: 'line', source: 'nofly', paint: { 'line-color': '#e34948', 'line-width': 2 } })
      m.addLayer({
        id: 'det', type: 'circle', source: 'detections',
        paint: {
          'circle-radius': 9,
          'circle-color': ['match', ['get', 'status'], 'confirmed', '#008300', 'rejected', '#8a8984', '#eda100'],
          'circle-stroke-color': '#ffffff', 'circle-stroke-width': 2,
        },
      })
      m.addLayer({
        id: 'drones', type: 'circle', source: 'drones',
        paint: { 'circle-radius': 7, 'circle-color': '#2a78d6', 'circle-stroke-color': '#ffffff', 'circle-stroke-width': 2 },
      })
      m.addLayer({
        id: 'drone-labels', type: 'symbol', source: 'drones',
        layout: { 'text-field': ['get', 'drone'], 'text-offset': [0, 1.3], 'text-size': 12, 'text-font': ['Open Sans Semibold'] },
        paint: { 'text-color': '#0b0b0b', 'text-halo-color': '#ffffff', 'text-halo-width': 1.5 },
      })
      setReady(true)
    })
    m.on('click', (e) => {
      if (!pinModeRef.current) return
      setPinMode(false)
      command('alert', { lat: e.lngLat.lat, lon: e.lngLat.lng })
    })
    mapRef.current = m
    return () => m.remove()
  }, [])

  useEffect(() => {
    if (!ready || !grid) return
    const m = mapRef.current
    m.getSource('outline').setData(grid.outline)
    m.getSource('nofly').setData(world.nofly)
    const [w, s] = world.corners.sw.slice().reverse(), [e, n] = world.corners.ne.slice().reverse()
    m.fitBounds([[w, s], [e, n]], { padding: 40, duration: 0 })
  }, [ready, grid, world])

  useEffect(() => {
    if (ready) mapRef.current.getSource('heat').setData(heatmapGeoJSON(grid, mapUpdate))
  }, [ready, grid, mapUpdate])

  useEffect(() => {
    if (!ready) return
    mapRef.current.getSource('drones').setData({
      type: 'FeatureCollection',
      features: Object.values(drones).map((d) => ({ type: 'Feature', properties: { drone: d.drone }, geometry: { type: 'Point', coordinates: [d.lon, d.lat] } })),
    })
  }, [ready, drones])

  useEffect(() => {
    if (!ready) return
    mapRef.current.getSource('detections').setData({
      type: 'FeatureCollection',
      features: Object.values(detections).map((d) => ({ type: 'Feature', properties: { status: d.status }, geometry: { type: 'Point', coordinates: [d.lon, d.lat] } })),
    })
  }, [ready, detections])

  const queue = Object.values(detections).sort((a, b) => (a.status === 'pending' ? -1 : 1) - (b.status === 'pending' ? -1 : 1) || b.ts - a.ts)
  const pending = queue.filter((d) => d.status === 'pending').length

  return (
    <div className="app">
      <div ref={containerRef} className="map" />
      <aside className="panel">
        <header>
          <h1>TRAAN</h1>
          <span className={connected ? 'pill ok' : 'pill bad'}>{connected ? 'live' : 'reconnecting…'}</span>
        </header>

        <button className={pinMode ? 'primary active' : 'primary'} onClick={() => setPinMode(!pinMode)}>
          {pinMode ? 'Click the map to drop the alert pin' : 'Drop alert pin'}
        </button>

        <section>
          <h2>Probability map</h2>
          <p className="muted">
            {mapUpdate ? <>version {mapUpdate.version} · top cell p = {mapUpdate.top_cells[0]?.[2].toFixed(4)}</> : 'no map yet — drop an alert pin'}
          </p>
        </section>

        <section>
          <h2>Fleet</h2>
          {Object.values(drones).length === 0 && <p className="muted">no telemetry yet</p>}
          <table>
            <tbody>
              {Object.values(drones).sort((a, b) => a.drone.localeCompare(b.drone)).map((d) => (
                <tr key={d.drone}>
                  <td><b>{d.drone}</b></td>
                  <td>{d.alt.toFixed(0)} m</td>
                  <td>
                    <span className="battery"><span style={{ width: `${d.battery * 100}%` }} className={d.battery < 0.25 ? 'low' : ''} /></span>
                    {(d.battery * 100).toFixed(0)}%
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        <section className="grow">
          <h2>Detections {pending > 0 && <span className="pill warn">{pending} to confirm</span>}</h2>
          <p className="muted small">Thermal frame replay (HIT-UAV), not a live camera.</p>
          {queue.map((d) => (
            <div key={d.id} className={`det ${d.status}`}>
              <div className="det-head">
                <b>{d.status === 'pending' ? 'Possible person' : d.status === 'confirmed' ? 'Confirmed' : 'Rejected'}</b>
                <span>#{d.id} · {d.drone} · {(d.conf * 100).toFixed(0)}%</span>
              </div>
              {!d.frame.startsWith('mock/') && <img src={`${PERCEPTION}/frames/${d.frame}`} alt={`thermal frame ${d.frame}`} />}
              <div className="muted small">{d.lat.toFixed(5)}, {d.lon.toFixed(5)} · {d.frame}</div>
              {d.status === 'pending' && (
                <div className="row">
                  <button className="confirm" onClick={() => command('confirm', { id: d.id })}>Confirm</button>
                  <button onClick={() => command('reject', { id: d.id })}>Reject</button>
                </div>
              )}
            </div>
          ))}
        </section>
      </aside>
    </div>
  )
}
