# TASKS.md — Source of Truth

## Текущий статус рефакторинга (SOLID + MVC)
- План архитектуры: `ARCHITECTURE.md`
- Потерян исходный код `packages/` (attempt2): только `.pyc`, нет `.py`, не закоммичено в git.
- Этапы 1–4 соответствуют `plan/1.1–4.1`.

## Ближайшие шаги
1. [ ] Решить: восстанавливать packages из .pyc или писать с нуля (рекомендую: с нуля по плану).
2. [ ] Этап 1: `p2pvpn_common` — constants.py, models (VPNConfig, Peer), protocol/packet.py, protocol/ipc.py + тесты.
3. [ ] Этап 2: абстракции Transport/L2Interface/SystemConfigurator, PeerManager, VPNEngine (assembler).
4. [ ] Этап 3: daemon/main.py + IPC-сервер (UDS/TCP) + IPCController (get_status/add_peer/stop).
5. [ ] Этап 4: CLI-View (`p2pvpn connect/status/add-peer/stop/demo`) с rich, exit codes, demo-режим без root.
6. [ ] Shim `main.py`, `vpn_node.py`, `tap.py` для совместимости до релиза CLI.
