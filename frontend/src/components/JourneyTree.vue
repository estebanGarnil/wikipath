<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { journeyTree } from '../lib/journeyTree.js'
import { ancestorPath } from '../lib/branchGraph.js'
const props = defineProps({visits:{type:Array,default:()=>[]},currentId:[Number,String],disabled:Boolean})
const emit = defineEmits(['select'])
const host = ref(null)
const layout = computed(() => journeyTree(props.visits))
const active = computed(() => new Set(ancestorPath(props.visits,props.currentId).map(v=>v.id)))
watch(() => props.currentId, async () => {
  await nextTick()
  host.value?.querySelector('[aria-current="step"]')?.scrollIntoView({block:'nearest',inline:'nearest'})
})
</script>
<template>
  <div ref="host" class="visit-tree" role="list" aria-label="Visites et branches du parcours" :style="{'--tree-width':layout.width+'px', minHeight:layout.height+'px'}">
    <svg class="visit-tree-lines" :width="layout.width" :height="layout.height" aria-hidden="true">
      <path v-for="link in layout.links" :key="link.id" :d="link.d" :class="{'on-path':active.has(link.id) && active.has(link.parent)}" />
    </svg>
    <div v-for="row in layout.rows" :key="row.visit.id" class="visit-tree-row" role="listitem" :class="{'on-path':active.has(row.visit.id),'is-current':row.visit.id===currentId}">
      <button type="button" class="visit-tree-button" :disabled="disabled" :aria-current="row.visit.id===currentId ? 'step' : undefined" :title="row.visit.title || row.visit.page_title" @click="emit('select',row.visit)">
        <span class="visit-tree-dot" :style="{left:row.x+'px'}" aria-hidden="true"></span>
        <span class="visit-tree-label">{{ row.visit.title || row.visit.page_title }}<small v-if="row.visit.id===currentId">Vous êtes ici</small></span>
      </button>
    </div>
  </div>
</template>
<style scoped>
.visit-tree{position:relative;min-width:180px;width:100%;isolation:isolate}
.visit-tree-lines{position:absolute;left:0;top:0;pointer-events:none;overflow:visible}
.visit-tree-lines path{fill:none;stroke:#c8ccd1;stroke-width:1.5}
.visit-tree-lines path.on-path{stroke:#54595d}
.visit-tree-row{height:52px;position:relative}
.visit-tree .visit-tree-button{position:relative;left:auto;display:flex;align-items:center;width:100%;height:52px;border:0;background:transparent;text-align:left;padding:0 6px 0 var(--tree-width);font:normal 12px/1.35 Arial,Helvetica,sans-serif;color:#72777d;gap:0;margin:0}
.visit-tree .visit-tree-button:hover{background:#00000005}
.visit-tree .on-path .visit-tree-button{color:#202122}
.visit-tree .is-current .visit-tree-button{font-weight:bold}
.visit-tree-dot{position:absolute;top:26px;transform:translate(-50%,-50%);width:10px;height:10px;border:1.5px solid #a2a9b1;border-radius:50%;background:#fff}
.on-path .visit-tree-dot{border-color:#54595d}
.is-current .visit-tree-dot{background:#202122;border-color:#202122;width:12px;height:12px}
.visit-tree-label{display:block;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.visit-tree-label small{display:block;font:normal 10px/1.4 Arial,Helvetica,sans-serif;color:#54595d}
</style>
