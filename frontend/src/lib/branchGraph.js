export function ancestorPath(visits, currentId) {
  const byId = new Map(visits.map(v => [v.id, v]))
  const path = [], seen = new Set()
  let current = byId.get(currentId)
  while (current && !seen.has(current.id)) {
    seen.add(current.id); path.push(current)
    current = byId.get(current.parent_id)
  }
  return path.reverse()
}

// Only these objects enter the SVG and the D3 simulation.
export function branchGraph(path, cache, direction = 'out', limit = 200) {
  const steps = path.slice(-4), current = steps.at(-1)?.page_id
  const nodes = new Map(), edges = new Map(), navigable = new Set()
  const edgeKey = e => `${e.source}:${e.target}:${e.type}`
  for (const step of steps) nodes.set(step.page_id, {page_id:step.page_id, title:step.title})
  for (const [age, step] of [...steps].reverse().entries()) {
    const entry = cache[`${step.page_id}:${direction}`]
    if (!entry) continue
    const available = new Map(entry.nodes.map(n => [n.page_id,n]))
    for (const edge of entry.edges) {
      const id = direction === 'out' ? edge.target : edge.source
      if (id === step.page_id || !available.has(id)) continue
      if (!nodes.has(id) && nodes.size >= limit) continue
      if (!nodes.has(id)) nodes.set(id, {...available.get(id), age})
      if (!edges.has(edgeKey(edge))) edges.set(edgeKey(edge), {...edge, age, active:step.page_id === current})
      if (step.page_id === current) navigable.add(id)
    }
  }
  const ages = new Map(steps.map((v,i) => [v.page_id,steps.length-1-i]))
  return {
    nodes:[...nodes.values()].map(n => ({...n, navigable:navigable.has(n.page_id),
      opacity:n.page_id === current || navigable.has(n.page_id) ? 1 : 3 ** -(Math.max(1,ages.get(n.page_id) ?? n.age ?? 1)),
    })),
    edges:[...edges.values()].filter(e => nodes.has(e.source) && nodes.has(e.target)).map(e => ({...e, opacity:e.active ? .8 : .3 * 3 ** -e.age})),
    navigable,
  }
}
