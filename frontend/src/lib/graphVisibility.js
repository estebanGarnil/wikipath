// Visual distance ignores arrow direction; navigation respects the chosen direction.
export function graphVisibility(nodes, edges, selected, direction = 'out') {
  const opacityAt = depth => 3 ** -Math.max(0, depth - 1)
  const minimumOpacity = 0.06
  const adjacency = new Map(nodes.map(n => [n.page_id, new Set()]))
  const navigable = new Set()
  for (const { source, target } of edges) {
    if (!adjacency.has(source) || !adjacency.has(target)) continue
    adjacency.get(source).add(target)
    adjacency.get(target).add(source)
    if (direction === 'out' && source === selected) navigable.add(target)
    if (direction === 'in' && target === selected) navigable.add(source)
  }
  navigable.delete(selected)
  const distances = new Map()
  if (adjacency.has(selected)) {
    distances.set(selected, 0)
    const queue = [selected]
    for (let i = 0; i < queue.length; i++) {
      const id = queue[i], depth = distances.get(id)
      if (opacityAt(depth + 1) < minimumOpacity) continue
      for (const next of adjacency.get(id)) if (!distances.has(next)) {
        distances.set(next, depth + 1)
        queue.push(next)
      }
    }
  }
  const visibleNodes = nodes.filter(n => distances.has(n.page_id)).map(n => ({
    ...n, depth: distances.get(n.page_id),
    opacity: n.page_id === selected || navigable.has(n.page_id) ? 1 : .30 / 2 ** Math.max(0, distances.get(n.page_id) - 2),
    navigable: navigable.has(n.page_id),
  }))
  const visibleEdges = edges.filter(e => distances.has(e.source) && distances.has(e.target)).map(e => ({
    ...e,
    active: direction === 'out' ? e.source === selected : e.target === selected,
    opacity: (direction === 'out' ? e.source === selected : e.target === selected)
      ? .8 : .32 / Math.sqrt(3) ** Math.max(0, Math.max(distances.get(e.source), distances.get(e.target)) - 1),
  }))
  return { nodes: visibleNodes, edges: visibleEdges, navigable }
}
