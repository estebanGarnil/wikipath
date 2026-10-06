<script setup>
import { onMounted, onBeforeUnmount, ref, watch } from 'vue'
import * as d3 from 'd3'
const props = defineProps({ nodes: Array, edges: Array, selected: Number })
const emit = defineEmits(['select'])
const host = ref(null)
let svg, layer, nodeLayer, edgeLayer, simulation, zoom, observer
let positions = new Map()
function paintSelection() {
  nodeLayer?.selectAll('g.node').classed('selected', d => d.page_id === props.selected)
}
function update() {
  if (!simulation) return
  const nodes = props.nodes.map(n => Object.assign(positions.get(n.page_id) || {}, n))
  positions = new Map(nodes.map(n => [n.page_id, n]))
  const edges = props.edges.map(e => ({ ...e }))
  simulation.force('link').links([])
  simulation.nodes(nodes)
  simulation.force('link').links(edges)
  const lines = edgeLayer.selectAll('path').data(edges, d => `${d.source.page_id}:${d.target.page_id}:${d.type}`).join('path')
    .attr('class', 'edge').attr('marker-end', 'url(#graph-arrow)')
  const groups = nodeLayer.selectAll('g.node').data(nodes, d => d.page_id).join(enter => {
    const group = enter.append('g').attr('class', 'node').attr('tabindex', 0).attr('role', 'button')
    group.append('circle').attr('r', 9)
    group.append('text').attr('x', 16).attr('y', 4)
    group.append('title')
    return group
  })
  groups.attr('aria-label', d => `Explorer ${d.title}`)
    .on('click', (event, d) => { if (!event.defaultPrevented) emit('select', d) })
    .on('keydown', (event, d) => { if (['Enter', ' '].includes(event.key)) { event.preventDefault(); emit('select', d) } })
    .call(d3.drag().clickDistance(5)
      .on('start', (event, d) => { if (!event.active) simulation.alphaTarget(.22).restart(); d.fx = d.x; d.fy = d.y })
      .on('drag', (event, d) => { d.fx = event.x; d.fy = event.y })
      .on('end', (event, d) => { if (!event.active) simulation.alphaTarget(0); d.fx = null; d.fy = null }))
  groups.select('text').text(d => d.title.length > 38 ? d.title.slice(0, 37) + '…' : d.title)
  groups.select('title').text(d => d.title)
  paintSelection()
  simulation.on('tick', () => {
    groups.attr('transform', d => `translate(${d.x},${d.y})`)
    lines.attr('d', d => {
      const a = d.source, b = d.target
      if (a === b) return `M${a.x},${a.y-9} C${a.x+45},${a.y-50} ${a.x+45},${a.y+50} ${a.x+9},${a.y}`
      const dx = b.x-a.x, dy = b.y-a.y, len = Math.hypot(dx,dy) || 1
      return `M${a.x+dx/len*11},${a.y+dy/len*11} Q${(a.x+b.x)/2-dy*.07},${(a.y+b.y)/2+dx*.07} ${b.x-dx/len*14},${b.y-dy/len*14}`
    })
  })
  simulation.alpha(.5).restart()
}
function fit() {
  if (!svg || !positions.size) return
  const nodes = [...positions.values()].filter(n => Number.isFinite(n.x))
  if (!nodes.length) return
  const w = host.value.clientWidth, h = host.value.clientHeight
  const x0 = d3.min(nodes, d => d.x)-35, x1 = d3.max(nodes, d => d.x)+220
  const y0 = d3.min(nodes, d => d.y)-35, y1 = d3.max(nodes, d => d.y)+35
  const scale = Math.max(.15, Math.min(1.4, (w-50)/(x1-x0), (h-50)/(y1-y0)))
  svg.call(zoom.transform, d3.zoomIdentity.translate(w/2-scale*(x0+x1)/2, h/2-scale*(y0+y1)/2).scale(scale))
}
onMounted(() => {
  svg = d3.select(host.value).append('svg').attr('aria-label', 'Graphe des pages Wikipédia')
  svg.append('defs').append('marker').attr('id','graph-arrow').attr('viewBox','0 -4 8 8').attr('refX',8).attr('markerWidth',6).attr('markerHeight',6).attr('orient','auto').append('path').attr('d','M0,-3L8,0L0,3').attr('fill','#aaa')
  layer = svg.append('g'); edgeLayer = layer.append('g'); nodeLayer = layer.append('g')
  zoom = d3.zoom().scaleExtent([.15, 4]).on('zoom', event => layer.attr('transform', event.transform))
  svg.call(zoom).on('dblclick.zoom', null)
  simulation = d3.forceSimulation().force('link',d3.forceLink().id(d => d.page_id).distance(150).strength(.25))
    .force('charge',d3.forceManyBody().strength(-350)).force('collision',d3.forceCollide(35))
    .force('x',d3.forceX(0).strength(.035)).force('y',d3.forceY(0).strength(.035))
  let first = true
  observer = new ResizeObserver(() => {
    const w = host.value.clientWidth, h = host.value.clientHeight
    svg.attr('width',w).attr('height',h)
    if (first && w && h) { svg.call(zoom.transform,d3.zoomIdentity.translate(w/2,h/2)); first = false }
  })
  observer.observe(host.value)
  update()
})
watch(() => [props.nodes,props.edges], update)
watch(() => props.selected, paintSelection)
onBeforeUnmount(() => { observer?.disconnect(); simulation?.stop(); svg?.on('.zoom',null) })
defineExpose({ fit })
</script>
<template><div ref="host" class="graph-canvas"></div></template>
