# Chowder: Bookin' Cook - local launcher.
# Serves this folder on http://localhost:8642 and opens your browser.
# All game files are in .\game\. No internet connection is necessary.
#
#   -NoBrowser   do not open the browser (for tests)
#
# Debug: open http://localhost:8642/?debug. The page then sends its console
# output to POST /log, and this script writes it to ruffle-log.txt.

param([switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$port = 8642
$log  = Join-Path $root 'ruffle-log.txt'

$mime = @{
  '.html'='text/html; charset=utf-8'; '.js'='text/javascript'; '.wasm'='application/wasm';
  '.swf'='application/x-shockwave-flash'; '.xml'='text/xml'; '.txt'='text/plain';
  '.json'='application/json'; '.png'='image/png'; '.mp3'='audio/mpeg'
}

$listener = New-Object System.Net.HttpListener
$listener.Prefixes.Add("http://localhost:$port/")
try { $listener.Start() } catch {
    Write-Host "Port $port is busy. Is the game already running? Opening it." -ForegroundColor Yellow
    if (-not $NoBrowser) { Start-Process "http://localhost:$port/" }
    exit
}
Write-Host "Chowder: Bookin' Cook is running at http://localhost:$port/" -ForegroundColor Green
Write-Host "Close this window to stop."
if (-not $NoBrowser) { Start-Process "http://localhost:$port/" }

while ($listener.IsListening) {
    $ctx = $listener.GetContext()
    $res = $ctx.Response
    try {
        $rel = [Uri]::UnescapeDataString($ctx.Request.Url.AbsolutePath.TrimStart('/'))
        if ($ctx.Request.HttpMethod -eq 'POST' -and $rel -eq 'log') {
            $sr = New-Object IO.StreamReader($ctx.Request.InputStream)
            $line = $sr.ReadToEnd(); $sr.Close()
            Add-Content -Path $log -Value ((Get-Date -Format 'HH:mm:ss.fff') + ' ' + $line)
            $res.StatusCode = 204
            continue
        }
        if ($rel -eq '') { $rel = 'index.html' }
        $path = [IO.Path]::GetFullPath((Join-Path $root $rel))
        if (-not $path.StartsWith($root, [StringComparison]::OrdinalIgnoreCase)) { $res.StatusCode = 403; continue }
        if (Test-Path $path -PathType Leaf) {
            $bytes = [IO.File]::ReadAllBytes($path)
            $ext = [IO.Path]::GetExtension($path).ToLower()
            $res.ContentType = $(if ($mime.ContainsKey($ext)) { $mime[$ext] } else { 'application/octet-stream' })
            $res.Headers.Add('Cache-Control', 'no-cache')
            $res.ContentLength64 = $bytes.Length
            $res.OutputStream.Write($bytes, 0, $bytes.Length)
        } else {
            $res.StatusCode = 404
        }
    } catch { try { $res.StatusCode = 500 } catch {} }
    finally { try { $res.Close() } catch {} }
}
