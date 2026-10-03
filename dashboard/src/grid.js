// Grid geometry from GET /world. Cell (row, col): row 0 = north edge, col 0 = west edge.
// Over 2 km a bilinear blend of the four UTM-derived corners is accurate to well under 1 m.
export function makeGrid(world) {
  const { nw, ne, sw, se } = world.corners
  const n = world.n_cells
  const at = (u, v) => {
    const lat = nw[0] * (1 - u) * (1 - v) + ne[0] * u * (1 - v) + sw[0] * (1 - u) * v + se[0] * u * v
    const lon = nw[1] * (1 - u) * (1 - v) + ne[1] * u * (1 - v) + sw[1] * (1 - u) * v + se[1] * u * v
    return [lon, lat]
  }
  const cellPolygon = (row, col) => {
    const ring = [at(col / n, row / n), at((col + 1) / n, row / n), at((col + 1) / n, (row + 1) / n), at(col / n, (row + 1) / n)]
    return [[...ring, ring[0]]]
  }
  const outline = { type: 'Feature', geometry: { type: 'Polygon', coordinates: [[at(0, 0), at(1, 0), at(1, 1), at(0, 1), at(0, 0)]] } }
  return { n, cellPolygon, outline }
}

export function heatmapGeoJSON(grid, map) {
  if (!grid || !map) return { type: 'FeatureCollection', features: [] }
  const pmax = map.top_cells.length ? map.top_cells[0][2] : 1
  return {
    type: 'FeatureCollection',
    features: map.top_cells.map(([r, c, p]) => ({
      type: 'Feature',
      properties: { p, rel: pmax > 0 ? p / pmax : 0, row: r, col: c },
      geometry: { type: 'Polygon', coordinates: grid.cellPolygon(r, c) },
    })),
  }
}
