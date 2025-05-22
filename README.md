# Mahjong AI

This is a terminal-based Mahjong simulator with AI players designed to play 4-player Sichuan-style Mahjong (Chuan Ma) and evaluate fixed strategies like KoutsuAI (triplet-focused agent).

## Features

- 🀄 4-player full Mahjong game simulation
- 🤖 AI-controlled players with modular strategy (e.g., `KoutsuAI`)
- 🧠 KoutsuAI aims to win by forming **4 triplets and 1 pair**
- 🔁 Supports melds: Pon, Kan (open & closed), and optional meld display
- 🃏 Fully automatic draw/discard turns with turn display
- ✅ Detects win conditions (self-draw or Ron)
- ❌ Skips players who have already won
- 📦 Clean round structure with per-turn board output
- 🔚 Game ends with draw or when 3 players have won

## How to Run

```bash
python game_chuan.py
```

The board will print each turn’s status in the terminal.

## TODO

- [ ] 胡牌后的玩家不再摸打
- [ ] Add more AI strategies (e.g., pair-focused, hand-reading)
- [ ] Implement rule variations (e.g., Nanjing Mahjong)
- [ ] Add scoring and point display per hand
- [ ] Web or GUI interface for visualization
- [ ] Integrate logging / replay system
- [ ] Add discard pile tracking and better wall visualization
- [ ] Prevent multiple players from Ron on the same tile (implement head-bump)

## File Structure

```
.
├── agents/             # Contains AI classes like KoutsuAI
├── core/               # Tile, player, board logic
├── display.py          # Terminal output formatting
├── game_chuan.py       # Main entry point (Chuan Mahjong)
└── README.md           # This file
```

---

Contributions and improvements welcome!
