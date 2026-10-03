import { useEffect, useReducer, useState } from 'react'
import { WS_URL } from './config.js'

// Folds the four frozen event types (CLAUDE.md) into dashboard state.
const initial = { drones: {}, detections: {}, map: null, lastTs: null }

function reduce(state, e) {
  switch (e.type) {
    case 'telemetry':
      return { ...state, lastTs: e.ts, drones: { ...state.drones, [e.drone]: e } }
    case 'detection':
      return { ...state, detections: { ...state.detections, [e.id]: { ...state.detections[e.id], ...e } } }
    case 'confirm': {
      const d = state.detections[e.id]
      return d ? { ...state, detections: { ...state.detections, [e.id]: { ...d, status: 'confirmed', by: e.by } } } : state
    }
    case 'map_update':
      return !state.map || e.version >= state.map.version ? { ...state, map: e } : state
    default:
      return state
  }
}

export function useEvents() {
  const [state, dispatch] = useReducer(reduce, initial)
  const [connected, setConnected] = useState(false)

  useEffect(() => {
    let ws, retry, closed = false
    const open = () => {
      ws = new WebSocket(WS_URL)
      ws.onopen = () => setConnected(true)
      ws.onmessage = (m) => dispatch(JSON.parse(m.data))
      ws.onclose = () => {
        setConnected(false)
        if (!closed) retry = setTimeout(open, 1500) // API restarts must not need a page reload
      }
    }
    open()
    return () => { closed = true; clearTimeout(retry); ws?.close() }
  }, [])

  return { ...state, connected }
}
