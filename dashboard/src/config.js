export const API = import.meta.env.VITE_API ?? 'http://localhost:8000'
export const PERCEPTION = import.meta.env.VITE_PERCEPTION ?? 'http://localhost:8001'
export const WS_URL = API.replace(/^http/, 'ws') + '/ws'
