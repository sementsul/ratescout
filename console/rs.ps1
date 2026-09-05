# RateScout — интерактивный консольный монитор курсов (Windows PowerShell).
# Клавиши: h — тепловая карта, w — watchlist, m — лидеры; период 1/2/3 = 24ч/7д/30д; r — обновить; q — выход.
# Скрипт только СКАЧИВАЕТ готовые текстовые страницы с ratescout.ru и печатает их. Ничего не ставит,
# не меняет файлы, не собирает данные. Открытый исходник: https://ratescout.ru/cli/rs.ps1
$base = "https://ratescout.ru/cli"; $view = "heat"; $period = "24h"
try { [Console]::CursorVisible = $false } catch {}
try {
  while ($true) {
    $p = if ($view -eq "watch") { "watch" } else { "$view-$period" }
    Clear-Host
    try { Write-Host (Invoke-RestMethod "$base/$p.txt" -TimeoutSec 20) }
    catch { Write-Host "  нет связи — нажмите r, чтобы повторить" }
    Write-Host "`n [h]хитмап  [w]watchlist  [m]муверы    период: [1]24ч [2]7д [3]30д    [r]обновить  [q]выход" -ForegroundColor DarkGray
    $k = [Console]::ReadKey($true).KeyChar
    switch ($k) {
      'h' { $view = "heat" } 'w' { $view = "watch" } 'm' { $view = "movers" }
      '1' { $period = "24h" } '2' { $period = "7d" } '3' { $period = "30d" }
      'q' { break }
    }
  }
} finally { try { [Console]::CursorVisible = $true } catch {} }
