$ErrorActionPreference = 'Stop'
$base = 'http://localhost:8000/api/graph/pages/3/neighbors/?direction=out&limit=20'
$first = Invoke-RestMethod $base
if ($first.order -ne 'semantic') {
    throw "Page 3 : tri '$($first.order)' au lieu de 'semantic'."
}
if (-not $first.has_more -or -not $first.next_cursor) {
    throw 'Le premier lot devrait avoir une suite.'
}
$cursor = [uri]::EscapeDataString([string]$first.next_cursor)
$second = Invoke-RestMethod "$base&after=$cursor"
if ($second.order -ne 'semantic') { throw 'Le second lot a change de classement.' }
if (@($first.edges).Count -ne 20 -or @($second.edges).Count -ne 20) {
    throw 'Les deux premiers lots devraient contenir 20 voisins chacun.'
}
$allEdges = @($first.edges) + @($second.edges)
$unique = @($allEdges | Select-Object -ExpandProperty target -Unique)
if ($unique.Count -ne 40) { throw 'Doublons entre les deux lots.' }
for ($i = 1; $i -lt $allEdges.Count; $i++) {
    $previous = $allEdges[$i - 1]
    $current = $allEdges[$i]
    if ($null -eq $previous.semantic_score -or $null -eq $current.semantic_score) {
        throw 'Score absent.'
    }
    if ($current.semantic_score -gt $previous.semantic_score -or
        ($current.semantic_score -eq $previous.semantic_score -and $current.target -le $previous.target)) {
        throw 'Ordre incorrect entre deux voisins consecutifs.'
    }
}
Write-Host "OK : 40 voisins distincts, scores decroissants, total annonce : $($first.total_neighbors)."
$rank = 0
foreach ($batch in @($first, $second)) {
    $titles = @{}
    foreach ($node in $batch.nodes) { $titles[[string]$node.page_id] = $node.title }
    $display = foreach ($edge in $batch.edges) {
        $rank++
        [pscustomobject]@{
            Rang = $rank
            Page = $edge.target
            Titre = $titles[[string]$edge.target]
            Score = $edge.semantic_score
        }
    }
    $display | Format-Table -AutoSize
}
