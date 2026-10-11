<script setup>
import { onMounted, onBeforeUnmount, ref, watch } from 'vue'
import * as d3 from 'd3'
const props = defineProps({ nodes: Array, edges: Array, selected: Number })
const emit = defineEmits(['select'])
const host = ref(null)
let svg, layer, nodeLayer, edgeLayer, simulation, zoom, observer
let positions = new Map()
let followFocus = true
let lastSelected
let lastWidth = 0, lastHeight = 0
function paintSelection() {
  nodeLayer?.selectAll('g.node').classed('selected', d => d.page_id === props.selected)
}
function update() {
  if (!simulation) return
  const changed = lastSelected !== props.selected
  if (changed) { followFocus = true; lastSelected = props.selected }
  const anchor = positions.get(props.selected)
  const nodes = props.nodes.map(n => Object.assign(positions.get(n.page_id) || { x: (anchor?.x || 0) + Math.cos(n.page_id)*80, y: (anchor?.y || 0) + Math.sin(n.page_id)*80 }, n))
  if (!nodes.length) positions.clear()
  nodes.forEach(n => positions.set(n.page_id, n))
  // Bound the position cache independently from the visible simulation.
  if (positions.size > 500) positions = new Map(nodes.map(n => [n.page_id, n]))
  const edges = props.edges.map(e => ({ ...e }))
  simulation.force('link').links([])
  simulation.nodes(nodes)
  simulation.force('link').links(edges)
  const lines = edgeLayer.selectAll('path').data(edges, d => `${d.source.page_id}:${d.target.page_id}:${d.type}`).join('path')
    .attr('class', d => d.active ? 'edge active-edge' : 'edge').attr('marker-end', 'url(#graph-arrow)').attr('opacity', d => d.opacity)
  const groups = nodeLayer.selectAll('g.node').data(nodes, d => d.page_id).join(enter => {
    const group = enter.append('g').attr('class', 'node').attr('tabindex', 0).attr('role', 'button')
    group.append('circle').attr('r', 9)
    group.append('rect').attr('class', 'node-label-bg').attr('rx', 3)
    group.append('text').attr('x', 16).attr('y', 4)
    group.append('title')
    return group
  })
  groups.attr('aria-label', d => d.navigable ? `Explorer ${d.title}` : d.title)
    .attr('tabindex', d => d.navigable ? 0 : -1)
    .attr('role', d => d.navigable ? 'button' : 'img')
    .classed('navigable', d => d.navigable)
    .attr('opacity', d => d.opacity)
    .on('click', (event, d) => { if (!event.defaultPrevented && d.navigable) emit('select', d) })
    .on('keydown', (event, d) => { if (d.navigable && ['Enter', ' '].includes(event.key)) { event.preventDefault(); emit('select', d) } })
    .call(d3.drag().clickDistance(5)
      .on('start', (event, d) => { followFocus = false; if (!event.active) simulation.alphaTarget(.22).restart(); d.fx = d.x; d.fy = d.y })
      .on('drag', (event, d) => { d.fx = event.x; d.fy = event.y })
      .on('end', (event, d) => { if (!event.active) simulation.alphaTarget(0); d.fx = null; d.fy = null }))
  groups.select('text').text(d => d.title.length > 38 ? d.title.slice(0, 37) + '…' : d.title)
  groups.select('title').text(d => d.navigable ? d.title : `${d.title} — utilisez le parcours pour revenir à une ancienne page`)
  groups.select('circle').attr('r', d => d.page_id === props.selected ? 15 : 8)
  groups.select('text').attr('x', 0).attr('y', d => d.page_id === props.selected ? 38 : 25).attr('text-anchor', 'middle')
  paintSelection()
  groups.select('rect.node-label-bg').attr('display', d => d.page_id === props.selected ? null : 'none')
  groups.filter(d => d.page_id === props.selected).each(function () {
    const box = d3.select(this).select('text').node().getBBox()
    d3.select(this).select('rect').attr('x', box.x - 9).attr('y', box.y - 5)
      .attr('width', box.width + 18).attr('height', box.height + 10)
  }).raise()
  simulation.on('tick', () => {
    if (followFocus) centerOnCurrent(false)
    groups.attr('transform', d => `translate(${d.x},${d.y})`)
    lines.attr('d', d => {
      const a = d.source, b = d.target
      if (a === b) return `M${a.x},${a.y-9} C${a.x+45},${a.y-50} ${a.x+45},${a.y+50} ${a.x+9},${a.y}`
      const dx = b.x-a.x, dy = b.y-a.y, len = Math.hypot(dx,dy) || 1
      const start = a.page_id === props.selected ? 19 : 11, end = b.page_id === props.selected ? 23 : 14
      return `M${a.x+dx/len*start},${a.y+dy/len*start} Q${(a.x+b.x)/2-dy*.07},${(a.y+b.y)/2+dx*.07} ${b.x-dx/len*end},${b.y-dy/len*end}`
    })
  })
  simulation.alpha(.5).restart()
  if (changed) centerOnCurrent(true)
}
function centerOnCurrent(resetScale) {
  const current = positions.get(props.selected)
  if (!svg || !current || !Number.isFinite(current.x)) return
  const w = host.value.clientWidth, h = host.value.clientHeight
  const transform = d3.zoomTransform(svg.node())
  const scale = resetScale ? 1 : transform.k
  svg.call(zoom.transform, d3.zoomIdentity
    .translate(w/2-scale*current.x, h/2-scale*current.y).scale(scale))
}
function fit() {
  // Focus on the current page instead of shrinking the entire exploration.
  followFocus = true
  centerOnCurrent(true)
}
onMounted(() => {
  svg = d3.select(host.value).append('svg').attr('aria-label', 'Graphe des pages Wikipédia')
  svg.append('defs').append('marker').attr('id','graph-arrow').attr('viewBox','0 -4 8 8').attr('refX',8).attr('markerWidth',6).attr('markerHeight',6).attr('orient','auto').append('path').attr('d','M0,-3L8,0L0,3').attr('fill','#aaa')
  layer = svg.append('g'); edgeLayer = layer.append('g'); nodeLayer = layer.append('g')
  zoom = d3.zoom().scaleExtent([.15, 4]).on('zoom', event => { if (event.sourceEvent) followFocus = false; layer.attr('transform', event.transform) })
  svg.call(zoom).on('dblclick.zoom', null)
  simulation = d3.forceSimulation().force('link',d3.forceLink().id(d => d.page_id).distance(185).strength(.25))
    .force('charge',d3.forceManyBody().strength(-350)).force('collision',d3.forceCollide(d => Math.min(95, Math.max(48, d.title.length * 2.5))).iterations(2))
    .force('x',d3.forceX(0).strength(.018)).force('y',d3.forceY(0).strength(.018))
    .on('end', () => { if (followFocus) centerOnCurrent(false); followFocus = false })
  let first = true
  observer = new ResizeObserver(() => {
    const w = host.value.clientWidth, h = host.value.clientHeight
    svg.attr('width',w).attr('height',h)
    if (first && w && h) { svg.call(zoom.transform,d3.zoomIdentity.translate(w/2,h/2)); first = false }
    else if (w && h) {
      const t = d3.zoomTransform(svg.node())
      svg.call(zoom.transform, d3.zoomIdentity.translate(t.x+(w-lastWidth)/2,t.y+(h-lastHeight)/2).scale(t.k))
    }
    lastWidth = w; lastHeight = h
  })
  observer.observe(host.value)
  update()
})
watch(() => [props.nodes,props.edges,props.selected], update)
watch(() => props.selected, paintSelection)
onBeforeUnmount(() => { observer?.disconnect(); simulation?.stop(); svg?.on('.zoom',null) })
defineExpose({ fit })
</script>
<template><div ref="host" class="graph-canvas"></div></template>
