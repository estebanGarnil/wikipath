<script setup>
import { computed, onBeforeUnmount, ref, shallowRef, watch } from 'vue'
import GraphView from './components/GraphView.vue'
const query = ref(''), suggestions = ref([]), searching = ref(false), searchError = ref('')
const nodes = shallowRef([]), edges = shallowRef([]), selected = ref(null), history = ref([]), historyIndex = ref(-1)
const busy = ref(false), graphError = ref(''), direction = ref('out'), progress = ref({}), graph = ref(null)
const open = ref(false), content = ref(''), contentBusy = ref(false), contentError = ref('')
let searchController, graphController, contentController, timer, searchVersion = 0, graphVersion = 0, contentVersion = 0
const contentCache = new Map()
const pageProgress = computed(() => selected.value ? progress.value[`${selected.value.page_id}:${direction.value}`] : null)
async function json(url, signal) {
  const response = await fetch(url, { signal, headers: { Accept: 'application/json' } })
  if (!response.ok) throw new Error(response.status === 404 ? 'Cette page est absente de la base demandée.' : `La requête a échoué (${response.status}). Réessayez.`)
  return response.json()
}
watch(query, value => {
  clearTimeout(timer); searchController?.abort()
  const version = ++searchVersion
  suggestions.value = []; searchError.value = ''; searching.value = false
  if (value.trim().length < 3) return
  searching.value = true
  timer = setTimeout(async () => {
    searchController = new AbortController()
    try {
      const data = await json(`/api/articles/suggest/?q=${encodeURIComponent(value.trim())}&limit=8`, searchController.signal)
      if (version === searchVersion) suggestions.value = data.results
    } catch (error) { if (version === searchVersion && error.name !== 'AbortError') searchError.value = error.message }
    finally { if (version === searchVersion) searching.value = false }
  }, 300)
})
async function loadNeighbors(page = selected.value, dir = direction.value) {
  if (!page) return
  const key = `${page.page_id}:${dir}`, previous = progress.value[key]
  if (previous && !previous.has_more) return
  graphController?.abort(); graphController = new AbortController()
  const version = ++graphVersion
  busy.value = true; graphError.value = ''
  try {
    const after = previous?.next_cursor ?? 0
    const data = await json(`/api/graph/pages/${page.page_id}/neighbors/?direction=${dir}&limit=20&after=${after}`, graphController.signal)
    if (version !== graphVersion) return
    const mergedNodes = new Map(nodes.value.map(n => [n.page_id,n]))
    data.nodes.forEach(n => mergedNodes.set(n.page_id,n))
    if (mergedNodes.size > 400) throw new Error('Limite de 400 pages affichées atteinte. Lancez une nouvelle exploration depuis la recherche.')
    const mergedEdges = new Map(edges.value.map(e => [`${e.source}:${e.target}:${e.type}`,e]))
    data.edges.forEach(e => mergedEdges.set(`${e.source}:${e.target}:${e.type}`,e))
    nodes.value = [...mergedNodes.values()]; edges.value = [...mergedEdges.values()]
    progress.value = { ...progress.value, [key]: { has_more: data.has_more, next_cursor: data.next_cursor } }
  } catch (error) { if (version === graphVersion && error.name !== 'AbortError') graphError.value = error.message }
  finally { if (version === graphVersion) busy.value = false }
}
function selectPage(page, index = null) {
  graphController?.abort(); ++graphVersion; busy.value = false; graphError.value = ''
  selected.value = { page_id: page.page_id, title: page.title }
  if (index !== null) historyIndex.value = index
  else if (history.value[historyIndex.value]?.page_id !== page.page_id) {
    history.value = [...history.value.slice(0,historyIndex.value+1), selected.value]
    historyIndex.value = history.value.length-1
  }
  if (!progress.value[`${page.page_id}:${direction.value}`]) loadNeighbors(selected.value)
}
function start(page) {
  nodes.value = []; edges.value = []; progress.value = {}; history.value = []; historyIndex.value = -1
  query.value = ''; suggestions.value = []; open.value = false
  selectPage(page)
}
watch(direction, () => {
  graphController?.abort(); ++graphVersion; busy.value = false; graphError.value = ''
  if (selected.value && !pageProgress.value) loadNeighbors()
})
async function loadContent() {
  contentController?.abort(); const version = ++contentVersion
  content.value = ''; contentError.value = ''; contentBusy.value = false
  if (!open.value || !selected.value) return
  const id = selected.value.page_id
  if (contentCache.has(id)) { content.value = contentCache.get(id); return }
  contentBusy.value = true; contentController = new AbortController()
  try {
    const data = await json(`/api/articles/${id}/content/`,contentController.signal)
    if (version !== contentVersion) return
    content.value = data.wikitext
    if (contentCache.size >= 5) contentCache.delete(contentCache.keys().next().value)
    contentCache.set(id,data.wikitext)
  } catch (error) { if (version === contentVersion && error.name !== 'AbortError') contentError.value = error.message }
  finally { if (version === contentVersion) contentBusy.value = false }
}
watch([open, () => selected.value?.page_id], loadContent)
onBeforeUnmount(() => { clearTimeout(timer); searchController?.abort(); graphController?.abort(); contentController?.abort() })
</script>

<template>
  <main class="app-shell">
    <header class="topbar">
      <a class="wordmark" href="/" aria-label="Wikipath, accueil">Wiki<span>path</span><small>EXPLORER LES CONNEXIONS</small></a>
      <div class="search">
        <label class="sr-only" for="search">Rechercher une page Wikipédia</label>
        <div class="search-field"><span aria-hidden="true">⌕</span><input id="search" v-model="query" type="search" autocomplete="off" placeholder="Rechercher une page Wikipédia…" @keydown.esc="query = ''" /></div>
        <div v-if="query.trim().length >= 3" class="suggestions">
          <p v-if="searching" role="status">Recherche…</p>
          <p v-else-if="searchError" role="alert">{{ searchError }}</p>
          <template v-else><button v-for="item in suggestions" :key="item.page_id" @click="start(item)">{{ item.title }} <span aria-hidden="true">↗</span></button><p v-if="!suggestions.length">Aucune page trouvée.</p></template>
        </div>
      </div>
      <span class="edition">WIKIPÉDIA · FR</span>
    </header>
    <div class="workspace">
      <aside class="journey" aria-label="Historique du parcours"><h2>Parcours</h2><p v-if="!history.length" class="muted">Votre exploration commence ici.</p>
        <ol><li v-for="(page,index) in history" :key="index" :class="{ active: index === historyIndex }"><button :aria-current="index === historyIndex ? 'step' : undefined" @click="selectPage(page,index)"><span class="history-dot"></span><span>{{ page.title }}</span></button></li></ol>
      </aside>
      <section class="explorer" aria-label="Exploration du graphe">
        <div class="graph-area">
          <GraphView ref="graph" :nodes="nodes" :edges="edges" :selected="selected?.page_id" @select="selectPage" />
          <div v-if="!selected" class="welcome"><p class="eyebrow">UNE PAGE EN OUVRE UNE AUTRE</p><h1>Suivez le fil<br />de votre curiosité.</h1><p>Recherchez un article, puis explorez les pages qui lui sont reliées.</p><button @click="start({page_id:3,title:'Antoine Meillet'})">Commencer une exploration <span aria-hidden="true">↗</span></button></div>
          <div v-if="selected" class="graph-toolbar"><label>Liens <select v-model="direction"><option value="out">sortants</option><option value="in">entrants</option></select></label><button :disabled="busy || pageProgress?.has_more === false" @click="loadNeighbors()">{{ busy ? 'Chargement…' : pageProgress?.has_more === false ? 'Tous les voisins chargés' : pageProgress ? 'Charger 20 de plus' : 'Charger les voisins' }}</button><button @click="graph?.fit()">Recentrer</button></div>
          <div v-if="graphError" class="graph-error" role="alert">{{ graphError }} <button @click="loadNeighbors()">Réessayer</button></div>
          <div v-if="selected" class="graph-caption"><span>{{ nodes.length }} pages · {{ edges.length }} liens</span><span>Glissez un nœud · Cliquez pour explorer · Zoomez à la molette</span></div>
        </div>
        <section v-if="selected" class="article-panel" :class="{ expanded: open }">
          <button class="article-toggle" :aria-expanded="open" aria-controls="article-content" @click="open = !open"><span class="toggle-arrow" aria-hidden="true">{{ open ? '↓' : '↑' }}</span><h2>{{ selected.title }}</h2><span class="read-label">{{ open ? 'Réduire' : 'Lire le wikicode' }}</span></button>
          <div v-if="open" id="article-content" class="article-body"><p v-if="contentBusy" role="status">Chargement du wikicode…</p><p v-else-if="contentError" role="alert">{{ contentError }} <button @click="loadContent">Réessayer</button></p><template v-else><p class="muted">Wikicode original · contenu non mis en forme</p><pre>{{ content }}</pre></template></div>
        </section>
      </section>
    </div>
  </main>
</template>
