# P2P VPN Project Roadmap

## Core Philosophy
**Freedom-First (Stallman Compliance):** The software must respect the 4 freedoms. No telemetry, no data collection, no surveillance. The user is the sole owner of their connection and metadata.

---

## Strategic Vectors

### 1. The "Mesh Brain" (Decentralized Discovery - DHT)
*Moving from manual peer lists to an autonomous distributed mesh.*
- **Goal:** Implement a Kademlia-like Distributed Hash Table (DHT).
- **Core Components:** K-buckets routing, XOR distance metric, iterative node lookups.
- **Impact:** Automatic peer discovery, self-healing network, no central servers.

### 2. The "Operator's Dashboard" (Rich Observability TUI)
*A high-density, real-time interface for network administrators.*
- **Goal:** Build a TUI (using Textual) that provides a "Single Pane of Glass" view.
- **Features:**
    - Real-time bandwidth/latency monitoring.
    - Interactive mesh topology visualization.
    - Status of all active/discovered peers.
    - Command terminal (CLI-style) integrated into the dashboard.
- **Method:** Implement an asynchronous metrics stream from the Daemon to the TUI via IPC.

### 3. The "User Control Center" (Desktop GUI)
*A user-friendly interface for non-technical end-users.*
- **Goal:** Build a cross-platform Windows/macOS/Linux GUI (using PySide6).
- **Features:**
    - One-click Connect/Disconnect.
    - Connection status and simple bandwidth indicators.
    - Peer management (Add/Remove manually).
    - System tray integration and notifications.
- **Method:** Strict MVC separation. GUI (View) <-> IPC/Command API (Controller) <-> Daemon (Model).

---

## Development Principles
- **Modular (LEGO):** All components must be independent "bricks".
- **TDD Driven:** Red $\to$ Green $\to$ Refactor.
- **Asynchronous First:** Everything (networking, discovery, UI) must be non-blocking (asyncio).
- **Privacy by Design:** No data leaves the user's control without explicit intent.
