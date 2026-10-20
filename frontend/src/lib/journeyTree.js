// Iterative layout: a linear continuation stays in the same lane.
export function journeyTree(visits) {
  const byId = new Map(visits.map(v => [v.id, v]))
  const children = new Map(), roots = []
  for (const visit of visits) {
    if (visit.parent_id == null || !byId.has(visit.parent_id)) roots.push(visit)
    else {
      if (!children.has(visit.parent_id)) children.set(visit.parent_id, [])
      children.get(visit.parent_id).push(visit)
    }
  }
  const rows = [], seen = new Set(), positions = new Map()
  let maxLane = 0
  function walk(root) {
    const stack = [{visit:root, lane:0}]
    while (stack.length) {
      const {visit,lane} = stack.pop()
      if (seen.has(visit.id)) continue
      seen.add(visit.id)
      const row = {visit, lane, x:14+lane*18, y:26+rows.length*52}
      positions.set(visit.id,row); rows.push(row); maxLane=Math.max(maxLane,lane)
      const next = children.get(visit.id) || []
      for (let i=next.length-1;i>=0;i--) stack.push({visit:next[i],lane:lane+i})
    }
  }
  roots.forEach(walk)
  // Defensive: render malformed/cyclic data once instead of dropping it.
  visits.forEach(v => {if (!seen.has(v.id)) walk(v)})
  const links = rows.flatMap(row => {
    const parent = positions.get(row.visit.parent_id)
    if (!parent || parent.y >= row.y) return []
    return [{id:row.visit.id,parent:parent.visit.id,
      d:parent.x===row.x ? `M ${parent.x} ${parent.y} V ${row.y}` :
        `M ${parent.x} ${parent.y} C ${parent.x} ${parent.y+26}, ${row.x} ${parent.y+26}, ${row.x} ${parent.y+52} V ${row.y}`}]
  })
  return {rows,links,width:32+maxLane*18,height:rows.length*52}
}
