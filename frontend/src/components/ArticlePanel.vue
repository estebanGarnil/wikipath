<script setup>
import { nextTick, onMounted, onBeforeUnmount, ref, watch } from 'vue'
const props = defineProps({ page: Object, fullscreen: Boolean })
const emit = defineEmits(['follow', 'layout', 'fullscreen'])
const open = ref(false), mode = ref('article'), height = ref(45), panel = ref(null), body = ref(null)
const html = ref(''), raw = ref(''), meta = ref(null), busy = ref(false), error = ref(''), notice = ref('')
const cache = new Map()
let panelObserver
let controller, version = 0, drag, followController, followVersion = 0
const following = ref(''), followError = ref('')
async function request(url, signal) {
  const response = await fetch(url, { signal, headers:{Accept:'application/json'} })
  if (!response.ok) {
    const data = await response.json().catch(() => ({}))
    throw new Error(data.detail || `Lecture impossible (${response.status}).`)
  }
  return response.json()
}
async function load() {
  controller?.abort(); const token = ++version
  busy.value = false; error.value = ''; html.value = ''; raw.value = ''; meta.value = null
  if (!open.value || !props.page) return
  const id = props.page.page_id, requestedMode = mode.value, key = `${id}:${requestedMode}`
  controller = new AbortController(); busy.value = true
  try {
    let data = cache.get(key)
    if (!data) {
      data = await request(`/api/articles/${id}/${requestedMode === 'article' ? 'render' : 'content'}/`, controller.signal)
      if (token !== version) return
      if (cache.size >= 6) cache.delete(cache.keys().next().value)
      cache.set(key,data)
    }
    if (token !== version) return
    if (requestedMode === 'article') { html.value = data.html; meta.value = data }
    else raw.value = data.wikitext
    await nextTick()
    if (token !== version) return
    body.value?.scrollTo(0,0)
    markLinks()
  } catch (err) {
    if (token === version && err.name !== 'AbortError') {
      if (requestedMode === 'article') {
        notice.value = `${err.message} Affichage du wikicode.`
        mode.value = 'wikicode'
      } else error.value = err.message
    }
  } finally { if (token === version) busy.value = false }
}
function markLinks() {
  for (const link of body.value?.querySelectorAll('[data-wiki-title]') || []) {
    link.classList.remove('unavailable-link')
    link.removeAttribute('aria-disabled')
    link.setAttribute('tabindex', '0')
    link.title = 'Suivre ce lien sortant'
  }
}
function cancelFollow() {
  followController?.abort(); ++followVersion
  following.value = ''; followError.value = ''
}
async function followTitle(title) {
  cancelFollow()
  const token = followVersion, sourceId = props.page.page_id
  followController = new AbortController(); following.value = title
  try {
    const data = await request(`/api/articles/${sourceId}/follow/?title=${encodeURIComponent(title)}`, followController.signal)
    if (token === followVersion && sourceId === props.page.page_id && open.value) emit('follow', data)
  } catch (err) {
    if (token === followVersion && err.name !== 'AbortError') followError.value = err.message
  } finally { if (token === followVersion) following.value = '' }
}
function articleClick(event) {
  const link = event.target.closest('a')
  if (!link || !body.value?.contains(link)) return
  if (link.hasAttribute('data-wiki-title')) {
    event.preventDefault()
    followTitle(link.dataset.wikiTitle)
    return
  }
  if (link.getAttribute('href')?.startsWith('#')) {
    event.preventDefault()
    const id = link.getAttribute('href').slice(1)
    const target = [...body.value.querySelectorAll('[id]')].find(el => el.id === id)
    target?.scrollIntoView({block:'start',behavior:'smooth'})
  }
}
function articleKey(event) { if (event.key === 'Enter' && event.target.closest('[data-wiki-title]')) articleClick(event) }
function resize(value) { height.value = Math.max(25,Math.min(85,value)) }
function startResize(event) {
  if (!open.value || props.fullscreen) return
  event.preventDefault()
  event.currentTarget.setPointerCapture(event.pointerId)
  drag = { y:event.clientY, height:height.value, available:panel.value.closest('.workspace').clientHeight }
}
function moveResize(event) { if (drag) resize(drag.height + (drag.y-event.clientY)/drag.available*100) }
function stopResize() { drag = null }
function toggleFullscreen() {
  drag = null
  if (props.fullscreen) {
    open.value = false
    emit('fullscreen', false)
  } else {
    open.value = true
    emit('fullscreen', true)
  }
}
function togglePanel() {
  if (props.fullscreen) emit('fullscreen', false)
  else open.value = !open.value
}
function retryArticle() { notice.value = ''; if (mode.value !== 'article') mode.value = 'article'; else load() }
function reportLayout() { emit('layout', { open: open.value, height: panel.value.getBoundingClientRect().height }) }
watch(() => props.fullscreen, value => { if (value) open.value = true })
onMounted(() => { panelObserver = new ResizeObserver(reportLayout); panelObserver.observe(panel.value) })
watch(open, async () => { await nextTick(); reportLayout() })
watch([open,mode,() => props.page?.page_id], load)
watch(() => props.page?.page_id, () => { notice.value = '' })
watch([open, mode, () => props.page?.page_id], cancelFollow, { flush: 'sync' })
onBeforeUnmount(() => { panelObserver?.disconnect(); controller?.abort(); ++version; cancelFollow() })
</script>
<template>
  <section ref="panel" class="article-panel reader-panel" :class="{expanded:open, 'reading-fullscreen':fullscreen}" :style="open && !fullscreen ? {height:height+'%'} : {}">
    <div v-if="open" class="reader-resize-bar">
    <div v-if="!fullscreen" class="panel-resizer" role="separator" aria-label="Hauteur du panneau de lecture" aria-orientation="horizontal" tabindex="0" :aria-valuenow="Math.round(height)" :aria-valuemin="25" :aria-valuemax="85" @pointerdown="startResize" @pointermove="moveResize" @pointerup="stopResize" @pointercancel="stopResize" @lostpointercapture="stopResize" @keydown.up.prevent="resize(height+5)" @keydown.down.prevent="resize(height-5)" @keydown.home.prevent="resize(25)" @keydown.end.prevent="resize(85)"><span></span></div>
      <button type="button" class="reader-fullscreen-toggle" :aria-label="fullscreen ? 'Fermer l’article et revenir au graphe' : 'Agrandir la lecture'" :title="fullscreen ? 'Fermer l’article et revenir au graphe' : 'Agrandir la lecture'" :aria-pressed="fullscreen" @click="toggleFullscreen">
        <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
          <path v-if="!fullscreen" d="M9 3H3v6m12-6h6v6M3 15v6h6m12-6v6h-6"/>
          <path v-else d="M3 9h6V3m6 0v6h6M9 21v-6H3m18 0h-6v6"/>
        </svg>
        <span v-if="fullscreen">Fermer l’article</span>
      </button>
    </div>
    <div class="reader-heading"><button class="article-toggle" :aria-label="fullscreen ? 'Revenir à la vue partagée : ' + page.title : undefined" :aria-expanded="open" aria-controls="reader-content" @click="togglePanel"><span class="toggle-arrow" aria-hidden="true">{{open?'↓':'↑'}}</span><span class="reader-title">{{page.title}}</span><span v-if="!fullscreen" class="read-label">{{open?'Réduire':'Lire l’article'}}</span></button></div>
    <template v-if="open">
      <div class="reader-tools"><div aria-label="Format de lecture"><button :aria-pressed="mode==='article'" @click="mode='article'">Article</button><button :aria-pressed="mode==='wikicode'" @click="mode='wikicode'">Wikicode</button></div></div>
      <p v-if="following || followError" class="reader-follow-status" :role="followError ? 'alert' : 'status'">{{followError || `Vérification du lien vers « ${following} »…`}}</p>
      <div ref="body" id="reader-content" class="reader-body" @click="articleClick" @keydown="articleKey">
        <p v-if="notice" class="reader-notice" role="status">{{notice}} <button @click="retryArticle">Réessayer le rendu</button></p>
        <p v-if="busy" role="status">{{mode==='article'?'Préparation de l’article… Le premier rendu peut prendre quelques secondes.':'Chargement du wikicode…'}}</p>
        <p v-else-if="error" role="alert">{{error}} <button @click="load">Réessayer</button></p>
        <template v-else-if="mode==='article'"><div class="wiki-content" v-html="html"></div><footer v-if="meta" class="reader-source">Texte issu de notre import ; modèles rendus à la demande. <a :href="meta.source_url" target="_blank" rel="noopener noreferrer">Source Wikipédia</a> · <a :href="meta.history_url" target="_blank" rel="noopener noreferrer">Contributeurs</a> · <a href="https://creativecommons.org/licenses/by-sa/4.0/" target="_blank" rel="noopener noreferrer">CC BY-SA 4.0</a>. Présentation adaptée.</footer></template>
        <pre v-else>{{raw}}</pre>
      </div>
    </template>
  </section>
</template>


<style scoped>
.reader-resize-bar{display:flex;align-items:center;min-height:32px;flex-shrink:0;background:#fafafa;border-bottom:1px solid #eaecf0}
.reader-resize-bar .panel-resizer{flex:1;height:32px}
.reader-fullscreen-toggle{display:flex;align-items:center;justify-content:center;gap:8px;min-width:40px;min-height:32px;padding:4px 8px;border:0;background:transparent;font-size:12px;margin-left:auto}
.reader-fullscreen-toggle:hover{background:#eaecf0}
.reading-fullscreen{display:flex;flex-direction:column;overflow:hidden}
.reading-fullscreen .reader-body{min-height:0;flex:1;overflow:auto}
</style>
