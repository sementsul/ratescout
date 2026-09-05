#!/usr/bin/env bash
# RateScout — интерактивный консольный монитор курсов (macOS/Linux, встроенные bash + curl).
# Клавиши: h — тепловая карта, w — watchlist, m — лидеры; период 1/2/3 = 24ч/7д/30д; r — обновить; q — выход.
# Скрипт только СКАЧИВАЕТ готовые текстовые страницы с ratescout.ru и печатает их. Ничего не ставит.
# Открытый исходник: https://ratescout.ru/cli/rs.sh
base="https://ratescout.ru/cli"; view="heat"; period="24h"
cleanup() { printf '\033[?25h'; clear; exit 0; }
trap cleanup INT
printf '\033[?25l'
while true; do
  if [ "$view" = "watch" ]; then p="watch"; else p="$view-$period"; fi
  clear
  curl -fsS --max-time 20 "$base/$p.txt" 2>/dev/null || echo "  нет связи — нажмите r, чтобы повторить"
  printf "\n [h]хитмап  [w]watchlist  [m]муверы    период: [1]24ч [2]7д [3]30д    [r]обновить  [q]выход\n"
  IFS= read -rsn1 k
  case "$k" in
    h) view="heat" ;; w) view="watch" ;; m) view="movers" ;;
    1) period="24h" ;; 2) period="7d" ;; 3) period="30d" ;;
    q) cleanup ;;
  esac
done
