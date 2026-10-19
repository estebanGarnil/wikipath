param(
    [Parameter(Mandatory=$true)][string]$Nodes,
    [Parameter(Mandatory=$true)][string]$Articles,
    [Parameter(Mandatory=$true)][string]$ReferenceMetadata,
    [string]$Prepare = "$PSScriptRoot\prepare_text.py",
    [string]$Output = '.\semantic-full-output\vectors.sqlite',
    [string]$Python = '.\.venv-semantic\Scripts\python.exe',
    [int]$BatchSize = 16,
    [int]$CheckpointPages = 64,
    [int]$Workers = 4,
    [int]$MaxPages = 0
)
$ErrorActionPreference = 'Stop'
$arguments = @(
    "$PSScriptRoot\encode_full.py",
    '--nodes', $Nodes, '--articles', $Articles,
    '--reference-metadata', $ReferenceMetadata,
    '--prepare', $Prepare, '--output', $Output,
    '--device', 'cuda', '--batch-size', $BatchSize,
    '--checkpoint-pages', $CheckpointPages, '--workers', $Workers
)
if ($MaxPages -gt 0) { $arguments += @('--max-pages', $MaxPages) }
& $Python @arguments
if ($LASTEXITCODE -ne 0) {
    throw "Calcul arrete (code $LASTEXITCODE). Les lots deja valides sont conserves."
}
