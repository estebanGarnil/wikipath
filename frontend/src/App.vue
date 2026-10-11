<script setup>
import { computed, onBeforeUnmount, ref, shallowRef, watch } from 'vue'
import GraphView from './components/GraphView.vue'
import ArticlePanel from './components/ArticlePanel.vue'
import { graphVisibility } from './lib/graphVisibility.js'
const readerLayout = ref({ open: false, height: 0 })
const query = ref(''), suggestions = ref([]), searching = ref(false), searchError = ref('')
const nodes = shallowRef([]), edges = shallowRef([]), selected = ref(null), history = ref([]), historyIndex = ref(-1)
const busy = ref(false), graphError = ref(''), direction = ref('out'), progress = ref({}), graph = ref(null)
let searchController, graphController, timer, searchVersion = 0, graphVersion = 0
const pageProgress = computed(() => selected.value ? progress.value[`${selected.value.page_id}:${direction.value}`] : null)
const visibleGraph = computed(() => graphVisibility(nodes.value, edges.value, selected.value?.page_id, direction.value))
function navigateGraph(page) {
  if (visibleGraph.value.navigable.has(page.page_id)) selectPage(page)
}
function followArticle(data) {
  // Ignore any answer for a page the user has already left.
  if (!selected.value || data.source_id !== selected.value.page_id) return
  const page = data.node, edge = data.edge
  if (edge.source !== data.source_id || edge.target !== page.page_id || edge.type !== 'LINKS_TO') return
  if (!nodes.value.some(n => n.page_id === page.page_id)) {
    if (nodes.value.length >= 400) {
      graphError.value = 'Limite de 400 pages conservées atteinte. Démarrez une nouvelle exploration.'
      return
    }
    nodes.value = [...nodes.value, page]
  }
  if (!edges.value.some(e => e.source === edge.source && e.target === edge.target && e.type === edge.type)) {
    edges.value = [...edges.value, edge]
  }
  // Verified outgoing link: independent of the graph's in/out display filter.
  selectPage(page)
}
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
    if (mergedNodes.size > 400) throw new Error('Limite de 400 pages conservées pour cette exploration atteinte. Lancez une nouvelle exploration depuis la recherche.')
    const mergedEdges = new Map(edges.value.map(e => [`${e.source}:${e.target}:${e.type}`,e]))
    data.edges.forEach(e => mergedEdges.set(`${e.source}:${e.target}:${e.type}`,e))
    nodes.value = [...mergedNodes.values()]; edges.value = [...mergedEdges.values()]
    progress.value = { ...progress.value, [key]: { has_more: data.has_more, next_cursor: data.next_cursor, total_neighbors: data.total_neighbors } }
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
  nodes.value = [{ ...page }]; edges.value = []; progress.value = {}; history.value = []; historyIndex.value = -1
  query.value = ''; suggestions.value = []
  selectPage(page)
}
watch(direction, () => {
  graphController?.abort(); ++graphVersion; busy.value = false; graphError.value = ''
  if (selected.value && !pageProgress.value) loadNeighbors()
})
onBeforeUnmount(() => { clearTimeout(timer); searchController?.abort(); graphController?.abort() })
</script>

<template>
  <main class="app-shell">
    <header class="topbar">
      <a class="wordmark" href="/" aria-label="Wikipath, accueil">Wiki<span>path</span></a>
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
          <GraphView ref="graph" :nodes="visibleGraph.nodes" :edges="visibleGraph.edges" :selected="selected?.page_id" @select="navigateGraph" />
          <div v-if="!selected" class="welcome"><h1>Suivez le fil<br />de votre curiosité.</h1><p>Recherchez un article, puis explorez les pages qui lui sont reliées.</p><button @click="start({page_id:3,title:'Antoine Meillet'})">Commencer une exploration <span aria-hidden="true">↗</span></button></div>
          <div v-if="selected" class="graph-toolbar"><span class="neighbor-counter" role="status" aria-live="polite" title="Voisins directs présents dans le graphe / total disponible pour cette direction">{{ visibleGraph.navigable.size.toLocaleString('fr-FR') }} / {{ pageProgress?.total_neighbors == null ? '…' : pageProgress.total_neighbors.toLocaleString('fr-FR') }} voisins</span><button :disabled="busy || pageProgress?.has_more === false" @click="loadNeighbors()">{{ busy ? 'Chargement…' : pageProgress?.has_more === false ? 'Tous les voisins chargés' : pageProgress ? 'Charger 20 de plus' : 'Charger les voisins' }}</button><button @click="graph?.fit()">Recentrer</button></div>
          <div v-if="graphError" class="graph-error" role="alert">{{ graphError }} <button @click="loadNeighbors()">Réessayer</button></div>
          <div v-if="selected" class="graph-caption"><span>{{ visibleGraph.nodes.length }} pages visibles · {{ visibleGraph.edges.length }} liens</span><span>Glissez un nœud · Explorez les voisins directs · Zoomez à la molette</span></div>
        </div>
        <div v-if="selected" class="reader-space" :style="{height: readerLayout.height + 'px'}" aria-hidden="true"></div>
      </section>
      <ArticlePanel v-if="selected" :page="selected" @follow="followArticle" @layout="readerLayout = $event" />
    </div>
  </main>
</template>
