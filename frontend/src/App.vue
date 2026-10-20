<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import GraphView from './components/GraphView.vue'
import JourneyTree from './components/JourneyTree.vue'
import ArticlePanel from './components/ArticlePanel.vue'
import { ancestorPath, branchGraph } from './lib/branchGraph.js'
import { api, paginationPath } from './lib/api.js'

const journeyList = ref(null)
const accountMenu = ref(null), accountToggle = ref(null), accountMenuOpen = ref(false)
function dismissAccountMenu(event) {
  if (!accountMenu.value?.contains(event.target)) accountMenuOpen.value = false
}
function closeAccountMenu() {
  accountMenuOpen.value = false
  accountToggle.value?.focus()
}

const searchExpanded = ref(false), activeSearch = ref(null)
const headerSearch = ref(null), headerInput = ref(null), homeSearch = ref(null)
function openSearch(area) {
  accountMenuOpen.value = false
  activeSearch.value = area
  if (area === 'header') searchExpanded.value = true
}
function closeSearch() {
  searchExpanded.value = false; activeSearch.value = null
}
function dismissSearch(event) {
  const container = activeSearch.value === 'header' ? headerSearch.value : homeSearch.value
  if (!container?.contains(event.target)) closeSearch()
}
function escapeSearch() {
  closeSearch()
  headerInput.value?.blur()
}

const starterTrack = ref(null)
const home = computed(() => screen.value === 'graph' && !selected.value)
const recentJourney = ref(null), recentBusy = ref(false), recentError = ref('')
let recentVersion = 0
const starters = [
  {title:'France',description:'Géographie, histoire et société'},
  {page_id:7,title:'Algèbre linéaire',description:'Vecteurs, matrices et espaces'},
  {page_id:3,title:'Antoine Meillet',description:'Langues et linguistique'},
  {title:'Python (langage)',description:'Programmation et informatique'},
]
function slideStarters(direction) {
  const track = starterTrack.value
  if (track) track.scrollBy({left:direction * track.clientWidth * .85, behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'})
}
async function loadRecentJourney() {
  const version = ++recentVersion
  recentJourney.value = null; recentError.value = ''; recentBusy.value = false
  if (!user.value || !home.value) return
  recentBusy.value = true
  try {
    let next = '/api/explorations/', latest = null
    // L’API trie par création : parcourir la pagination pour retrouver la dernière activité.
    while (next && version === recentVersion) {
      const data = await api(next)
      for (const item of data.results) {
        if (!latest || new Date(item.updated_at) > new Date(latest.updated_at)) latest = item
      }
      next = paginationPath(data.next)
    }
    if (latest && version === recentVersion) {
      const info = await api(`/api/explorations/${latest.id}/`)
      if (version === recentVersion) recentJourney.value = info.last_visit ? info : null
    }
  } catch { if (version === recentVersion) recentError.value = 'Impossible de charger le dernier parcours.' }
  finally { if (version === recentVersion) recentBusy.value = false }
}
const readerLayout = ref({ open: false, height: 0 })
const query = ref(''), suggestions = ref([]), searching = ref(false), searchError = ref('')
const selected = ref(null), allVisits = ref([]), currentVisitId = ref(null)
const neighborhoods = shallowRef({})
let localVisitId = 0
const history = computed(() => ancestorPath(allVisits.value, currentVisitId.value))
const historyIndex = computed(() => history.value.length - 1)
const journeyDialog = ref(null)
function chooseTreeVisit(visit) {
  activateVisit(visit)
  journeyDialog.value?.close()
}
const busy = ref(false), graphError = ref(''), direction = ref('out'), progress = ref({}), graph = ref(null)
const user = ref(null), sessionReady = ref(false), accountError = ref(''), authBusy = ref(false)
const authDialog = ref(null), authMode = ref('login'), username = ref(''), password = ref(''), confirmation = ref(''), authError = ref('')
const screen = ref('graph'), explorationId = ref(null), visitPosition = ref(0)
const saving = ref(false), saveError = ref(''), pendingVisit = ref(null)
const journeys = ref([]), journeysNext = ref(null), historyBusy = ref(false), historyError = ref('')
const detail = ref(null), visits = ref([]), visitsNext = ref(null)
let searchController, graphController, timer, searchVersion = 0, graphVersion = 0, historyVersion = 0
const blocked = computed(() => saving.value || authBusy.value || !sessionReady.value)
const pageProgress = computed(() => selected.value ? progress.value[`${selected.value.page_id}:${direction.value}`] : null)
const visibleGraph = computed(() => branchGraph(history.value, neighborhoods.value, direction.value))
const date = value => new Date(value).toLocaleString('fr-FR', {dateStyle:'medium', timeStyle:'short'})

async function loadSession() {
  accountError.value = ''; sessionReady.value = false
  try { const data = await api('/api/auth/me/'); user.value = data.authenticated ? data.user : null; sessionReady.value = true }
  catch { accountError.value = 'Impossible de vérifier votre session.' }
}
function openAuth() {
  if (saving.value) return
  authError.value = ''; password.value = ''; confirmation.value = ''; authMode.value = 'login'
  authDialog.value.showModal()
}
function closeAuth() { if (!authBusy.value) { authDialog.value.close(); password.value = ''; confirmation.value = '' } }
async function submitAuth() {
  if (authBusy.value) return
  authBusy.value = true; authError.value = ''
  try {
    if (authMode.value === 'register') {
      await api('/api/auth/register/', { method:'POST', body:{username:username.value, password:password.value, password_confirm:confirmation.value} })
      authMode.value = 'login'; confirmation.value = ''
    }
    const data = await api('/api/auth/login/', {method:'POST', body:{username:username.value, password:password.value}})
    user.value = data.user; sessionReady.value = true; accountError.value = ''; password.value = ''; authDialog.value.close()
    // Une exploration commencée anonymement reste locale. La prochaine recherche sera sauvegardée.
  } catch (error) { authError.value = error.message }
  finally { authBusy.value = false }
}
async function signOut() {
  if (blocked.value || pendingVisit.value) return
  authBusy.value = true; accountError.value = ''
  try {
    await api('/api/auth/logout/', {method:'POST'})
    user.value = null; ++historyVersion; journeys.value = []; detail.value = null; visits.value = []
    explorationId.value = null; visitPosition.value = 0; screen.value = 'graph'; resetGraph()
  } catch (error) { accountError.value = error.message }
  finally { authBusy.value = false }
}
function goHome() {
  if (saving.value || authBusy.value) return
  if (pendingVisit.value) {
    saveError.value = 'Une visite reste à enregistrer. Réessayez son enregistrement ou reprenez le parcours depuis l’historique avant de revenir à l’accueil.'
    return
  }
  ++historyVersion
  historyBusy.value = false
  screen.value = 'graph'
  closeSearch()
  query.value = ''; suggestions.value = []; searchError.value = ''
  searchController?.abort(); clearTimeout(timer); ++searchVersion; searching.value = false
  explorationId.value = null; visitPosition.value = 0; saveError.value = ''
  detail.value = null; visits.value = []; visitsNext.value = null
  resetGraph()
}
function resetGraph() {
  graphController?.abort(); ++graphVersion; busy.value = false; graphError.value = ''
  selected.value = null; progress.value = {}; allVisits.value = []; currentVisitId.value = null; neighborhoods.value = {}
  readerLayout.value = {open:false,height:0}
}
watch(query, value => {
  clearTimeout(timer); searchController?.abort(); const version = ++searchVersion
  suggestions.value = []; searchError.value = ''; searching.value = false
  if (value.trim().length < 3) return
  searching.value = true
  timer = setTimeout(async () => {
    searchController = new AbortController()
    try { const data = await api(`/api/articles/suggest/?q=${encodeURIComponent(value.trim())}&limit=8`, {signal:searchController.signal}); if (version === searchVersion) suggestions.value = data.results }
    catch (error) { if (version === searchVersion && error.name !== 'AbortError') searchError.value = error.message }
    finally { if (version === searchVersion) searching.value = false }
  }, 300)
})
function cacheNeighborhood(key, entry) {
  const cache = {...neighborhoods.value}
  delete cache[key]; cache[key] = entry
  const protectedKeys = new Set(history.value.slice(-4).map(v => `${v.page_id}:${direction.value}`))
  for (const old of Object.keys(cache)) {
    if (Object.keys(cache).length <= 40) break
    if (!protectedKeys.has(old)) {
      delete cache[old]
      const remaining = {...progress.value}; delete remaining[old]; progress.value = remaining
    }
  }
  neighborhoods.value = cache
}
async function loadNeighbors(page = selected.value, dir = direction.value) {
  if (!page) return
  const key = `${page.page_id}:${dir}`, previous = progress.value[key]
  if (previous && (!previous.has_more || previous.capped)) return
  graphController?.abort(); graphController = new AbortController(); const version = ++graphVersion
  busy.value = true; graphError.value = ''
  try {
    const after = previous?.next_cursor ?? 0
    const data = await api(`/api/graph/pages/${page.page_id}/neighbors/?direction=${dir}&limit=20&after=${encodeURIComponent(after)}`, {signal:graphController.signal})
    if (version !== graphVersion) return
    const old = neighborhoods.value[key] || {nodes:[],edges:[]}
    const mergedNodes = new Map(old.nodes.map(n => [n.page_id,n])); data.nodes.forEach(n => mergedNodes.set(n.page_id,n))
    const mergedEdges = new Map(old.edges.map(e => [`${e.source}:${e.target}:${e.type}`,e])); data.edges.forEach(e => mergedEdges.set(`${e.source}:${e.target}:${e.type}`,e))
    cacheNeighborhood(key, {nodes:[...mergedNodes.values()], edges:[...mergedEdges.values()]})
    progress.value = {...progress.value,[key]:{has_more:data.has_more,next_cursor:data.next_cursor,total_neighbors:data.total_neighbors,capped:mergedEdges.size >= 80}}
  } catch (error) { if (version === graphVersion && error.name !== 'AbortError') graphError.value = error.status === 409 ? 'Le classement a changé. Relancez cette exploration.' : error.message }
  finally { if (version === graphVersion) busy.value = false }
}
function applyPage(page) {
  graphController?.abort(); ++graphVersion; busy.value = false; graphError.value = ''
  selected.value = {page_id:page.page_id,title:page.title}
  loadWindow()
}
async function loadWindow() {
  // Reload only absent neighborhoods, current page first.
  const current = currentVisitId.value
  for (const visit of [...history.value.slice(-4)].reverse()) {
    if (current !== currentVisitId.value || screen.value !== 'graph') return
    if (!neighborhoods.value[`${visit.page_id}:${direction.value}`]) await loadNeighbors(visit)
  }
}
function activateVisit(visit) {
  if (blocked.value || pendingVisit.value) return
  currentVisitId.value = visit.id
  applyPage(visit)
}
function recordVisit(visit) {
  const normalized = {...visit, title:visit.page_title ?? visit.title}
  allVisits.value = [...allVisits.value, normalized]
  currentVisitId.value = normalized.id
  applyPage(normalized)
}
async function start(page) {
  if (blocked.value || pendingVisit.value) return
  saving.value = true; saveError.value = ''
  try {
    // Valider la page avant de modifier l'exploration affichée.
    let pageId = page.page_id
    if (!pageId) {
      const matches = await api(`/api/articles/suggest/?q=${encodeURIComponent(page.title)}&limit=8`)
      pageId = matches.results.find(item => item.title === page.title)?.page_id
      if (!pageId) throw new Error('Cet article est indisponible. Essayez la recherche.')
    }
    const valid = await api(`/api/graph/pages/${pageId}/`)
    let created = null
    let root
    if (user.value) {
      created = await api('/api/explorations/', {method:'POST',body:{page_id:valid.page_id}})
      const batch = await api(`/api/explorations/${created.id}/visits/`)
      root = batch.results.find(v => v.position === 1)
      if (!root) throw new Error('Visite initiale introuvable.')
    } else root = {...valid,id:`local-${++localVisitId}`,parent_id:null}
    resetGraph(); explorationId.value = created?.id ?? null; visitPosition.value = created ? 1 : 0
    screen.value = 'graph'; ++historyVersion; closeSearch(); query.value = ''; suggestions.value = []; recordVisit(root)
  } catch (error) {
    saveError.value = `${error.message} Si la connexion a été interrompue, consultez l’historique avant de recommencer : le parcours a peut-être été créé.`
  } finally { saving.value = false }
}
async function selectPage(page) {
  const ancestor = [...history.value].reverse().find(v => v.page_id === page.page_id)
  if (ancestor) { activateVisit(ancestor); return }
  if (blocked.value || pendingVisit.value || selected.value?.page_id === page.page_id) return
  if (explorationId.value) {
    pendingVisit.value = {page:{...page}, exploration:explorationId.value, position:visitPosition.value + 1, parent_id:currentVisitId.value}
    await retryVisit()
  } else recordVisit({...page,id:`local-${++localVisitId}`,parent_id:currentVisitId.value})
}
async function retryVisit() {
  if (saving.value || !pendingVisit.value) return
  const pending = pendingVisit.value; saving.value = true; saveError.value = ''
  try {
    const saved = await api(`/api/explorations/${pending.exploration}/visits/`, {method:'POST',body:{page_id:pending.page.page_id,position:pending.position,parent_id:pending.parent_id}})
    visitPosition.value = saved.position; pendingVisit.value = null
    recordVisit(saved)
  } catch (error) { saveError.value = `${error.message} La navigation est suspendue pour préserver l’ordre des visites.` }
  finally { saving.value = false }
}
function navigateGraph(page) { if (visibleGraph.value.navigable.has(page.page_id)) selectPage(page) }
function followArticle(data) {
  if (blocked.value || pendingVisit.value || !selected.value || data.source_id !== selected.value.page_id) return
  const page = data.node, edge = data.edge
  if (edge.source !== data.source_id || edge.target !== page.page_id || edge.type !== 'LINKS_TO') return
  selectPage(page)
}
async function showHistory() {
  if (!user.value || blocked.value) return
  screen.value = 'history'; detail.value = null; visits.value = []; journeys.value = []; journeysNext.value = null
  const version = ++historyVersion; historyBusy.value = true; historyError.value = ''
  try { const data = await api('/api/explorations/'); if (version === historyVersion) {journeys.value = data.results; journeysNext.value = paginationPath(data.next)} }
  catch (error) { if (version === historyVersion) historyError.value = error.message }
  finally { if (version === historyVersion) historyBusy.value = false }
}
async function moreJourneys() {
  if (historyBusy.value || !journeysNext.value) return
  const version = historyVersion; historyBusy.value = true; historyError.value = ''
  try { const data = await api(journeysNext.value); if (version === historyVersion) {journeys.value.push(...data.results); journeysNext.value = paginationPath(data.next)} }
  catch(error) {if(version === historyVersion) historyError.value = error.message}
  finally {if(version === historyVersion) historyBusy.value = false}
}
async function openJourney(item) {
  const version = ++historyVersion; historyBusy.value = true; historyError.value = ''; detail.value = null; visits.value = []; visitsNext.value = null
  try {
    const [info, data] = await Promise.all([api(`/api/explorations/${item.id}/`),api(`/api/explorations/${item.id}/visits/`)])
    if (version === historyVersion) {detail.value = info; visits.value = data.results; visitsNext.value = paginationPath(data.next)}
  } catch(error) {if(version === historyVersion) historyError.value = error.message}
  finally {if(version === historyVersion) historyBusy.value = false}
}
async function moreVisits() {
  if(historyBusy.value || !visitsNext.value) return
  const version = historyVersion; historyBusy.value = true; historyError.value = ''
  try {const data = await api(visitsNext.value); if(version === historyVersion) {visits.value.push(...data.results); visitsNext.value = paginationPath(data.next)}}
  catch(error) {if(version === historyVersion) historyError.value = error.message}
  finally {if(version === historyVersion) historyBusy.value = false}
}
async function resume(item, targetVisit = null) {
  if(blocked.value) return
  saving.value = true; historyError.value = ''
  try {
    const info = await api(`/api/explorations/${item.id}/`)
    const restored = []
    let next = `/api/explorations/${info.id}/visits/`
    while (next) {
      const batch = await api(next); restored.push(...batch.results)
      next = paginationPath(batch.next)
    }
    const target = restored.find(v => v.id === (targetVisit?.id ?? info.last_visit?.id))
    if (!target) throw new Error('Visite introuvable.')
    const page = await api(`/api/graph/pages/${target.page_id}/`)
    resetGraph(); pendingVisit.value = null; saveError.value = ''; explorationId.value = info.id
    visitPosition.value = restored.reduce((maximum,v) => Math.max(maximum,v.position),0)
    allVisits.value = restored.map(v => ({...v,title:v.page_title}))
    currentVisitId.value = target.id
    query.value = ''; screen.value = 'graph'; ++historyVersion
    applyPage(page)
  } catch(error) {historyError.value = error.message}
  finally {saving.value = false}
}
watch(() => history.value.length, async () => {
  await nextTick()
  const list = journeyList.value
  if (list && window.matchMedia('(max-width: 650px)').matches) {
    list.scrollLeft = list.scrollWidth
  }
})
watch(direction, () => {graphController?.abort(); ++graphVersion; busy.value = false; graphError.value = ''; if(selected.value) loadWindow()})
watch([home, () => user.value?.id], loadRecentJourney)
watch([screen, () => user.value?.id], () => { accountMenuOpen.value = false })
onMounted(() => {
  loadSession()
  document.addEventListener('pointerdown', dismissAccountMenu, true)
  document.addEventListener('focusin', dismissAccountMenu)
  document.addEventListener('pointerdown', dismissSearch)
  document.addEventListener('focusin', dismissSearch)
})
onBeforeUnmount(() => {document.removeEventListener('pointerdown', dismissAccountMenu, true); document.removeEventListener('focusin', dismissAccountMenu);document.removeEventListener('pointerdown', dismissSearch); document.removeEventListener('focusin', dismissSearch); clearTimeout(timer); searchController?.abort(); graphController?.abort(); ++historyVersion; ++recentVersion})
</script>

<template>
  <main class="app-shell" :class="{'is-home': home, 'is-exploring': screen === 'graph' && !!selected}">
    <header class="topbar" :class="{'search-expanded': searchExpanded}">
      <a class="wordmark" href="/" @click.prevent="goHome">Wikipath</a>
      <div v-if="!home" ref="headerSearch" class="search header-search" @focusin="openSearch('header')" @keydown.esc.prevent="escapeSearch">
        <label class="sr-only" for="search">Rechercher une page Wikipédia</label>
        <div class="search-field" @click="openSearch('header'); headerInput?.focus()"><span aria-hidden="true">⌕</span><input ref="headerInput" id="search" @click="openSearch('header')" v-model="query" type="search" autocomplete="off" placeholder="Rechercher une page Wikipédia…" /></div>
        <div v-if="activeSearch === 'header' && query.trim().length >= 3" class="suggestions">
          <p v-if="searching" role="status">Recherche…</p><p v-else-if="searchError" role="alert">{{ searchError }}</p>
          <template v-else><button v-for="item in suggestions" :key="item.page_id" :disabled="blocked || !!pendingVisit" @click="start(item)">{{ item.title }} <span aria-hidden="true">↗</span></button><p v-if="!suggestions.length">Aucune page trouvée.</p></template>
        </div>
      </div>
      <nav ref="accountMenu" class="account-actions" aria-label="Compte" @keydown.esc.stop.prevent="closeAccountMenu">
        <template v-if="user">
          <button ref="accountToggle" class="account-toggle" :disabled="blocked" :aria-expanded="accountMenuOpen" aria-controls="account-dropdown" @click="accountMenuOpen = !accountMenuOpen">
            <span class="account-username" :title="user.username">{{ user.username }}</span><span aria-hidden="true">⌄</span>
          </button>
          <div v-if="accountMenuOpen" id="account-dropdown" class="account-dropdown">
            <button :disabled="blocked" @click="closeAccountMenu(); showHistory()">Historique</button>
            <button :disabled="blocked || !!pendingVisit" @click="closeAccountMenu(); signOut()">Se déconnecter</button>
          </div>
        </template>
        <button v-else :disabled="!sessionReady || authBusy" @click="openAuth">{{ sessionReady ? 'Se connecter' : 'Connexion…' }}</button>
      </nav>
    </header>
    <div v-if="accountError" class="app-notice" role="alert">{{ accountError }} <button @click="loadSession">Réessayer</button></div>
    <div v-if="saveError" class="app-notice" role="alert">{{ saveError }} <template v-if="pendingVisit"><button :disabled="saving" @click="retryVisit">Réessayer l’enregistrement</button><button :disabled="saving" @click="showHistory">Ouvrir l’historique pour reprendre</button><button :disabled="saving" @click="openAuth">Se reconnecter</button></template></div>
    <div v-if="saving" class="app-notice" role="status">Enregistrement / chargement du parcours…</div>

    <section v-if="screen === 'history'" class="saved-history">
      <div class="history-heading"><div><p class="history-eyebrow">VOTRE ESPACE</p><h1>Historique des explorations</h1></div><button @click="screen = 'graph'">Retour au graphe</button></div>
      <p v-if="historyError" class="app-notice" role="alert">{{ historyError }} <button @click="showHistory">Recharger</button></p>
      <div v-if="detail" class="journey-detail">
        <button @click="showHistory">← Tous les parcours</button><h2>{{ detail.start_page_title }}</h2><p class="muted">Commencé le {{ date(detail.created_at) }}</p>
        <JourneyTree :visits="visits" :current-id="detail.last_visit?.id" :disabled="blocked" @select="resume(detail, $event)" />
        <button v-if="visitsNext" :disabled="historyBusy" @click="moreVisits">Afficher la suite du parcours</button>
        <div class="resume-box"><p class="muted">Cliquez sur une visite pour reprendre sa branche. Le graphe recharge au maximum quatre étapes et leurs voisins.</p><p v-if="detail.last_visit">Reprendre depuis <strong>{{ detail.last_visit.page_title }}</strong></p><button :disabled="blocked || !detail.last_visit" @click="resume(detail)">Reprendre l’exploration →</button></div>
      </div>
      <template v-else>
        <p class="muted">Chaque recherche sélectionnée démarre un nouveau parcours.</p>
        <div class="journey-cards"><button v-for="item in journeys" :key="item.id" class="journey-card" :disabled="historyBusy || saving" @click="openJourney(item)"><span class="journey-card-title">{{ item.start_page_title }}</span><time :datetime="item.created_at">{{ date(item.created_at) }}</time><span class="journey-card-link">Voir le parcours →</span></button></div>
        <p v-if="!historyBusy && !journeys.length && !historyError" class="muted">Aucun parcours enregistré. Lancez une recherche pour commencer.</p>
        <button v-if="journeysNext" :disabled="historyBusy" @click="moreJourneys">Afficher les parcours suivants</button>
      </template>
      <p v-if="historyBusy" role="status">Chargement…</p>
    </section>

    <div v-show="screen === 'graph'" class="workspace" :class="{'home-workspace': home}">
      <aside v-if="selected" class="journey" aria-label="Parcours actuel"><h2>Parcours</h2><p v-if="!history.length" class="muted">Votre exploration commence ici.</p><p v-if="selected" class="journey-save-state">{{ explorationId ? 'Parcours enregistré' : user ? 'Parcours local. Une nouvelle recherche sera enregistrée.' : 'Connectez-vous pour enregistrer vos prochains parcours.' }}</p>
        <ol ref="journeyList" class="mobile-journey-trail"><li v-for="(page,index) in history" :key="index" :class="{active:index === historyIndex}"><button :disabled="blocked || !!pendingVisit" :aria-current="index === historyIndex ? 'step' : undefined" @click="activateVisit(page)"><span class="history-dot"></span><span>{{ page.title }}</span></button></li></ol>
        <div class="desktop-journey-tree"><JourneyTree :visits="allVisits" :current-id="currentVisitId" :disabled="blocked || !!pendingVisit" @select="activateVisit" /></div>
        <button class="open-journey-tree" @click="journeyDialog.showModal()">Voir le parcours ({{ allVisits.length }})</button>
      </aside>
      <section class="explorer" aria-label="Exploration du graphe"><div class="graph-area">
        <GraphView ref="graph" :nodes="visibleGraph.nodes" :edges="visibleGraph.edges" :selected="selected?.page_id" @select="navigateGraph" />
        <section v-if="!selected" class="home-content" aria-labelledby="home-title">
          <h1 id="home-title">Explorer Wikipédia par ses liens</h1>
          <p class="home-intro">Choisissez un article, puis suivez les liens vers les pages qui vous intéressent.</p>
          <div ref="homeSearch" class="search home-search" @focusin="openSearch('home')" @keydown.esc.prevent="closeSearch">
            <label for="home-search">Quel article souhaitez-vous explorer ?</label>
            <div class="search-field"><input id="home-search" @click="openSearch('home')" v-model="query" type="search" autocomplete="off" placeholder="Un lieu, une personne, une idée…" aria-describedby="search-help" /></div>
            <p id="search-help" class="search-help">Saisissez au moins trois caractères, puis choisissez un article.</p>
            <div v-if="activeSearch === 'home' && query.trim().length >= 3" class="suggestions">
              <p v-if="searching" role="status">Recherche…</p><p v-else-if="searchError" role="alert">{{ searchError }}</p>
              <template v-else><button v-for="item in suggestions" :key="item.page_id" :disabled="blocked || !!pendingVisit" @click="start(item)">{{ item.title }} <span aria-hidden="true">→</span></button><p v-if="!suggestions.length">Aucune page trouvée.</p></template>
            </div>
          </div>
          <section class="starting-points" aria-labelledby="starters-title">
            <div class="starters-heading"><h2 id="starters-title">Quelques points de départ</h2><div class="carousel-controls"><button aria-label="Points de départ précédents" aria-controls="starter-track" @click="slideStarters(-1)">←</button><button aria-label="Points de départ suivants" aria-controls="starter-track" @click="slideStarters(1)">→</button></div></div>
            <div id="starter-track" ref="starterTrack" class="starter-track" tabindex="0" aria-label="Points de départ, liste défilante">
              <button v-for="item in starters" :key="item.title" class="starter-card" :disabled="blocked || !!pendingVisit" @click="start(item)"><span class="starter-title">{{ item.title }}</span><span class="starter-description">{{ item.description }}</span><span class="starter-action">Explorer cet article <span aria-hidden="true">→</span></span></button>
            </div>
          </section>
          <section v-if="user" class="home-resume" aria-label="Reprendre une exploration">
            <p v-if="recentBusy" class="muted" role="status">Recherche du dernier parcours…</p>
            <template v-else-if="recentJourney"><div><h2>Reprendre mon dernier parcours</h2><p>{{ recentJourney.last_visit.page_title }}</p><time :datetime="recentJourney.updated_at">Dernière visite : {{ date(recentJourney.updated_at) }}</time></div><button :disabled="blocked" @click="resume(recentJourney)">Reprendre →</button></template>
            <p v-else-if="recentError" role="alert">{{ recentError }} <button @click="loadRecentJourney">Réessayer</button></p>
            <p v-else class="muted">Vos prochains parcours seront enregistrés dans votre historique.</p>
            <p v-if="historyError" role="alert">{{ historyError }}</p>
          </section>
          <p v-else class="home-account-note">Vous pouvez explorer sans compte. <button :disabled="!sessionReady" @click="openAuth">Connectez-vous</button> pour retrouver vos parcours.</p>
        </section>
        <div v-if="selected" class="graph-toolbar"><span class="neighbor-counter" role="status">{{ visibleGraph.navigable.size.toLocaleString('fr-FR') }} / {{ pageProgress?.total_neighbors == null ? '…' : pageProgress.total_neighbors.toLocaleString('fr-FR') }} voisins</span><button :disabled="busy || pageProgress?.has_more === false || pageProgress?.capped" @click="loadNeighbors()">{{ busy ? 'Chargement…' : pageProgress?.capped ? 'Limite de 80 voisins chargés' : pageProgress?.has_more === false ? 'Tous les voisins chargés' : pageProgress ? 'Charger 20 de plus' : 'Charger les voisins' }}</button><button @click="graph?.fit()">Recentrer</button></div>
        <div v-if="graphError" class="graph-error" role="alert">{{ graphError }} <button @click="loadNeighbors()">Réessayer</button></div>
        <div v-if="selected" class="graph-caption"><span>{{ visibleGraph.nodes.length }} pages visibles · {{ visibleGraph.edges.length }} liens</span><span>Cliquez sur une page voisine pour continuer. · Glissez pour déplacer, faites défiler pour zoomer.</span></div>
      </div><div v-if="selected" class="reader-space" :style="{height:readerLayout.height+'px'}" aria-hidden="true"></div></section>
      <ArticlePanel v-if="selected" :page="selected" @follow="followArticle" @layout="readerLayout = $event" />
    </div>

    <dialog ref="journeyDialog" class="journey-tree-dialog" aria-labelledby="journey-tree-title">
      <header><h2 id="journey-tree-title">Votre parcours</h2><button type="button" aria-label="Fermer le parcours" @click="journeyDialog.close()">Fermer</button></header>
      <p class="muted">Choisissez une visite pour revenir à cette étape.</p>
      <JourneyTree :visits="allVisits" :current-id="currentVisitId" :disabled="blocked || !!pendingVisit" @select="chooseTreeVisit" />
    </dialog>

    <dialog ref="authDialog" class="account-dialog" aria-labelledby="auth-title" @cancel.prevent="closeAuth">
      <div class="account-dialog-heading"><h2 id="auth-title">{{ authMode === 'login' ? 'Se connecter' : 'Créer un compte' }}</h2><button :disabled="authBusy" aria-label="Fermer" @click="closeAuth">×</button></div>
      <p class="muted">Retrouvez vos explorations et reprenez votre parcours.</p>
      <form @submit.prevent="submitAuth"><fieldset :disabled="authBusy"><label for="username">Nom d’utilisateur</label><input id="username" v-model="username" autocomplete="username" maxlength="150" required />
        <label for="password">Mot de passe</label><input id="password" v-model="password" type="password" :autocomplete="authMode === 'login' ? 'current-password' : 'new-password'" maxlength="128" required />
        <template v-if="authMode === 'register'"><p class="muted">Au moins 10 caractères, sans mot de passe courant ni uniquement des chiffres.</p><label for="confirmation">Confirmer le mot de passe</label><input id="confirmation" v-model="confirmation" type="password" autocomplete="new-password" maxlength="128" required /></template>
        <p v-if="authError" class="auth-error" role="alert">{{ authError }}</p><button class="account-submit" type="submit">{{ authBusy ? 'Veuillez patienter…' : authMode === 'login' ? 'Se connecter' : 'Créer mon compte' }}</button>
        <button class="account-switch" type="button" @click="authMode = authMode === 'login' ? 'register' : 'login'; authError = ''; password = ''; confirmation = ''">{{ authMode === 'login' ? 'Pas encore de compte ? S’inscrire' : 'Déjà un compte ? Se connecter' }}</button>
      </fieldset></form>
    </dialog>
  </main>
</template>


<style scoped>
.journey .mobile-journey-trail,.journey .open-journey-tree{display:none}
.journey-tree-dialog{width:min(540px,calc(100vw - 24px));max-height:85dvh;overflow:auto;padding:20px;border:1px solid #202122;color:#202122;background:#fff}
.journey-tree-dialog::backdrop{background:#0006}
.journey-tree-dialog header{display:flex;align-items:center;justify-content:space-between;gap:12px}
.journey-tree-dialog h2{font:normal 24px Georgia,'Times New Roman',serif;margin:0}
@media(max-width:650px){
 .journey .desktop-journey-tree{display:none}
 .journey .mobile-journey-trail{display:flex}
 .journey .open-journey-tree{display:block;position:static;width:auto;padding:7px 10px;margin:8px 0;border:1px solid #a2a9b1;font:12px Arial,Helvetica,sans-serif;background:#fff}
}
</style>
