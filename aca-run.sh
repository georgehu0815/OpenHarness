export TERM=xterm-256color
export COLUMNS=$(tput cols 2>/dev/null || echo 220)
export LINES=$(tput lines 2>/dev/null || echo 50)
ohmo --workspace /data/ohmo --cwd /app
