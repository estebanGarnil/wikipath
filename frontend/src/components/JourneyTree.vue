<script setup>
import { computed, nextTick, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { journeyTree } from '../lib/journeyTree.js'
import { ancestorPath } from '../lib/branchGraph.js'
const props = defineProps({visits:{type:Array,default:()=>[]},currentId:[Number,String],disabled:Boolean,compact:Boolean})
const emit = defineEmits(['select'])
const host = ref(null)
const heights = ref(new Map())
const layout = computed(() => journeyTree(props.visits, heights.value))
const active = computed(() => new Set(ancestorPath(props.visits,props.currentId).map(v=>v.id)))
// Scroll only the tree's own container, never the document or workspace.
function revealCurrent() {
  const container = host.value?.closest('[data-journey-scroll]')
  const current = host.value?.querySelector('[aria-current="step"]')
  if (!container || !current || !container.clientHeight) return
  const box = container.getBoundingClientRect(), row = current.getBoundingClientRect()
  const top = box.top + container.clientTop + 8
  const bottom = box.top + container.clientTop + container.clientHeight - 8
  if (row.bottom > bottom) container.scrollTop += row.bottom - bottom
  else if (row.top < top) container.scrollTop -= top - row.top
}
let resizeObserver, rowObserver
function measureRows() {
  const measured = new Map()
  host.value?.querySelectorAll('.visit-tree-row').forEach((element, index) => {
    const visit = layout.value.rows[index]?.visit
    if (visit) measured.set(visit.id, element.getBoundingClientRect().height)
  })
  if (measured.size !== heights.value.size || [...measured].some(([id, height]) => heights.value.get(id) !== height)) {
    heights.value = measured
    nextTick(revealCurrent)
  }
}
function observeRows() {
  rowObserver?.disconnect()
  host.value?.querySelectorAll('.visit-tree-row').forEach(element => rowObserver?.observe(element))
  measureRows()
}
onMounted(() => {
  rowObserver = new ResizeObserver(measureRows)
  observeRows()
  const container = host.value?.closest('[data-journey-scroll]')
  if (container) {
    resizeObserver = new ResizeObserver(revealCurrent)
    resizeObserver.observe(container)
  }
  revealCurrent()
})
onBeforeUnmount(() => { resizeObserver?.disconnect(); rowObserver?.disconnect() })
watch([() => props.currentId, () => props.visits, () => props.compact], async () => {
  await nextTick()
  observeRows()
  revealCurrent()
}, {deep:true})
</script>
<template>
  <div ref="host" class="visit-tree" :class="{compact}" role="list" aria-label="Visites et branches du parcours" :style="{'--tree-width':layout.width+'px', minHeight:layout.height+'px'}">
    <svg class="visit-tree-lines" :width="layout.width" :height="layout.height" :viewBox="'0 0 '+layout.width+' '+Math.max(1,layout.height)" preserveAspectRatio="none" aria-hidden="true">
      <path v-for="link in layout.links" :key="link.id" :d="link.d" :class="{'on-path':active.has(link.id) && active.has(link.parent)}" />
    </svg>
    <div v-for="row in layout.rows" :key="row.visit.id" class="visit-tree-row" role="listitem" :class="{'on-path':active.has(row.visit.id),'is-current':row.visit.id===currentId}">
      <button type="button" class="visit-tree-button" :disabled="disabled" :aria-current="row.visit.id===currentId ? 'step' : undefined" :title="row.visit.title || row.visit.page_title" :aria-label="row.visit.title || row.visit.page_title" @click="emit('select',row.visit)">
        <span class="visit-tree-dot" :style="{left:'min('+row.x+'px, '+(row.x/layout.width*(compact ? 100 : 40))+'%)'}" aria-hidden="true"></span>
        <span class="visit-tree-label">{{ row.visit.title || row.visit.page_title }}<small v-if="row.visit.id===currentId">Vous êtes ici</small></span>
      </button>
    </div>
  </div>
</template>
<style scoped>
.visit-tree{position:relative;min-width:0;width:100%;isolation:isolate}
.visit-tree-lines{position:absolute;left:0;top:0;pointer-events:none;width:min(var(--tree-width),40%);overflow:hidden}
.visit-tree-lines path{fill:none;stroke:#c8ccd1;stroke-width:1.5}
.visit-tree-lines path.on-path{stroke:#54595d}
.visit-tree-row{min-height:52px;position:relative}
.visit-tree .visit-tree-button{position:relative;left:auto;display:flex;align-items:flex-start;width:100%;min-height:52px;height:auto;border:0;background:transparent;text-align:left;padding:16px 8px 16px min(var(--tree-width),40%);min-width:0;max-width:100%;font:normal 12px/20px Arial,Helvetica,sans-serif;color:#72777d;gap:0;margin:0}
.visit-tree .visit-tree-button:hover .visit-tree-label{background:#fff;text-decoration:underline;text-underline-offset:3px}
.visit-tree .on-path .visit-tree-button{color:#202122}
.visit-tree .is-current .visit-tree-button{font-weight:bold}
.visit-tree-dot{position:absolute;top:26px;transform:translate(-50%,-50%);width:10px;height:10px;border:1.5px solid #a2a9b1;border-radius:50%;background:#fff}
.on-path .visit-tree-dot{border-color:#54595d}
.is-current .visit-tree-dot{background:#202122;border-color:#202122;width:12px;height:12px}
.visit-tree-label{display:block;min-width:0;max-width:100%;white-space:normal;overflow-wrap:anywhere;background:rgba(255,255,255,.94);border-radius:2px;box-shadow:4px 0 rgba(255,255,255,.94),-4px 0 rgba(255,255,255,.94)}
.visit-tree-label small{display:block;font:normal 10px/1.4 Arial,Helvetica,sans-serif;color:#54595d}
.visit-tree.compact .visit-tree-lines{width:min(var(--tree-width),100%)}
.visit-tree.compact .visit-tree-label{display:none}
.visit-tree.compact .visit-tree-button{height:52px;padding:0}
.visit-tree.compact .visit-tree-button:hover{background:transparent}
</style>
