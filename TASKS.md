# TASKS.md — Source of Truth

## Текущий статус рефакторинга (SOLID + MVC)

План архитектуры: `ARCHITECTURE.md`, этапы: `plan/1.1–4.1`.

| Этап | Что сделано | Статус |
|---|---|---|
| 1.1 STUN | `p2pvpn_common/protocol/stun.py` (sync + async), shim `stun_client.py` | ✅ |
| 1.2 Protocol | `protocol/packet.py` (MAGIC `P2PL2`, DATA/HELLO), `protocol/ipc.py` (JSON-протокол) + тесты | ✅ |
| 1.3 Models | `models/vpn_config.py` (VPNConfig, PeerConfig, валидация), `models/peer.py` + тесты | ✅ |
| 1.4 Constants | `constants.py` — leaf-модуль, IPC-путь/порт переопределяются через env | ✅ |
| 2.1 Interface | `interface/base.py` (ABC `L2Interface`), `linux_tap.py`, `windows_tap.py`, `factory.py` | ✅ |
| 2.2 Configurator | `configurator/base.py` + `linux.py`/`windows.py`, инъекция в TAP, `run_command` инъективен (тесты без root) | ✅ |
| 2.3 PeerManager | `core/peer_manager.py`: пороги `stale`/`dead`/`heartbeat` через `PeerManagerConfig` (два порога вместо одного `PEER_TIMEOUT`) | ✅ |
| 2.4 Engine | `core/engine.py` (`VPNEngine`), `heartbeat.py`, `hole_punch.py` + тесты на fake- collaborators | ✅ |
| 3.1 Daemon | `p2pvpn_daemon/main.py`: DI-сборка, логирование, сигналы SIGINT/SIGTERM, graceful shutdown, `--fake` без root | ✅ |
| 3.2 IPC | `ipc/server.py` (`UnixIPCServer` / `TcpIPCServer`), `ipc/controller.py`, e2e-тест | ✅ |
| 4.1 CLI | `p2pvpn_cli`: `connect/status/add-peer/remove-peer/stop/demo`, rich-рендер, exit-коды 0/1/2, demo без root | ✅ |
| Shim | `main.py`, `vpn_node.py`, `tap.py`, `stun_client.py` работают поверх новых пакетов | ✅ |

## Проверено

- `uv sync --dev` ставит три пакета (editable), `uv run pytest` — **37 тестов, 0 падений** (common, daemon, cli).
- `uv run p2pvpn-cli demo -d 4` — hole punch → peers alive → форвардинг кадров → приём.
- Реальный IPC: `p2pvpn-cli connect --config node_a.json --fake` + `status`/`add-peer`/`remove-peer`/`stop` (отдельный процесс daemon, UDS).
- Shim `python main.py --config node_a.json` корректно сообщает про отсутствие root; `main.py --fake` запускает daemon без privileges (graceful shutdown по SIGTERM).

## Осталось

1. [x] Тесты Windows-конфигуратора (`tests/daemon/test_windows_configurator.py`).
2. [x] README: раздел «как запускать» (daemon + CLI + demo), структура пакетов.
3. [x] `windows-run.bat`: примеры и упоминание `p2pvpn-cli`.
4. [ ] Commit ветки `attempt2` (весь новый код пока не закоммичен).
5. [ ] Реальный сетевой тест на двух машинах (TAP + STUN) — требует root/второго узла.
6. [ ] macOS-конфигуратор (в плане 2.2 не заявлен, OCP-слот есть).
