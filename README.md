# Pac-Man ML: Smart Ghosts 🕹️👻

[![Status](https://img.shields.io/badge/Status-Beta--Testing-blue.svg)]()
[![Tech](https://img.shields.io/badge/Tech-Python_/_Pygame-green.svg)]()

This is a modern twist on the classic Pac-Man game, integrating **Machine Learning (ML)** mechanics. While traditional Pac-Man ghosts follow fixed algorithmic paths, the ghosts in this repository **learn and adapt to the specific playing habits of the user in real-time**.

> 📢 **Current Status: Beta Testing (Demo Available)**  
> The game is fully playable as a Demo! However, the project is currently in an experimental phase as we validate a core hypothesis: **Do ghosts driven by ML actually become smarter and more challenging than traditional AI?** Play the demo and let us know your thoughts!

---

## 🧠 Core Innovation: Adaptive Ghost AI

Instead of using hardcoded rules, the ML model in this project continuously tracks and analyzes player behavior data to predict your next move:
* **Turning Preferences:** At crossroads and intersections, the model analyzes whether you prefer to turn left, right, or continue straight based on past choices.
* **Motivation Prediction:** The ghosts estimate whether the player is currently in a "greedy state" (focusing on collecting dots) or a "panic state" (rushing towards exits/safety).
* **Dynamic Cornering:** Over time, the ghosts collaborate to trap you based on your personalized behavioral patterns, breaking away from predictable patrol routes.

---

## 🎮 Getting Started (Play the Demo)

### Prerequisites
Make sure you have Python 3.x installed along with the required dependencies (such as `pygame`):
```bash
pip install pygame
