# P2P VPN: целевая архитектура (SOLID + MVC)

## 0. Диагностика текущего состояния

Что не так с текущим кодом (`main.py`, `vpn_node.py`, `tap.py`, `stun_client.py`):

| Нарушение | Где | Почему плохо |
|---|---|---|
| **SRP** (класс-бог) | `VPNNode` в `vpn_node.py` | Один класс отвечает за: протокол encode-decode/декод, UDP-транспорт, таблицу пиров, heartbeat, hole punching, lifecycle TAP, логирование статуса. 6 ответственностей в одном месте. |
| **SRP** | `tap.py` | `_TAPLinux` одновременно открывает устройство, конфигурирует ОС (`iptables`, `ip`, `ethtool`, `netsh`) и читает/пишет фреймы. |
| **OCP закрыт** | Платформенные ветки `sys.platform == "win32"` внутри `main.py`, `tap.py` | Добавление macOS/BSD требует правки существующего кода, а не новой реализации. |
| **DIP отсутствует** | `VPNNode` напрямую знает про `TAPDevice`, `asyncio.DatagramProtocol`, конкретный UDP-сокет | Нет абстракций → невозможны тесты с моками и demo-режим без root. |
| **DRY / конфигурация через dict** | `cfg["local_ip"]`, `cfg.get(...)` повсюду | Нет типизации, опечатки не ловятся, нет валидации. |
| **Побочные эффекты на import** | `logging.basicConfig(...)` в `vpn_node.py` И в `main.py` | Конфигурация логирования — ответственность точки входа, не модуля. |
| **ID** | `Peer.is_alive()` сам считает время от `time.time()` | Модель знает про политики жизненного цикла; пороги hard-coded в константах модуля. |
| **Слепые зоны** | `main.py` делает STUN, banner, signal handlers, сборку конфига, запуск движка | CLI-«View» содержит контроллер и бизнес-логику сразу. |

Отдельный факт: попытка рефакторинга (`attempt2`) **потеряна** — каталоги `packages/` и `tests/` существуют, `.pyc`-файлы остались, но исходников `.py` нет и они не были закоммичены в git. План `plan/1.1–4.1` и 126 задач в `tasks/` описывают именно эту (незавершённую) работу.

---

## 1. Целевая структура (MVC)

```
p2pvpn/
├── packages/
│   ├── p2pvpn_common/              # общий контрактный слой
│   │   └── p2pvpn_common/
│   │       ├── constants.py        # leaf-модуль: MAGIC, TYPE_*, таймауты, MTU
│   │       ├── models/             # VPNConfig, PeerConfig, Peer, STUNResult, PacketType
│   │       ├── protocol/           # packet.py (encode/decode), stun.py, ipc.py (JSON-протокол)
│   │       └── errors/             # иерархика исключений: P2PVPNError, ConfigError, IPCError...
│   │
│   ├── p2pvpn_daemon/              # MODEL (домен + сервис)
│   │   └── p2pvpn_daemon/
│   │       ├── core/
│   │       │   ├── engine.py       # VPNEngine — только оркестрация lifecycle
│   │       │   ├── peer_manager.py # таблица пиров, статусы, пороги (DI-конфиг)
│   │       │   ├── heartbeat.py    # периодическая рассылка HELLO
│   │       │   └── hole_punch.py   # punch-логика
│   │       ├── transport/
│   │       │   ├── base.py         # ABC: Transport (send, on_datagram, close)
│   │       │   └── udp/udp_transport.py
│   │       ├── interfaces/
│   │       │   ├── base.py         # ABC: L2Interface (setup/write/read/teardown)
│   │       │   ├── linux_tap.py
│   │       │   ├── windows_tap.py
│   │       │   └── factory.py      # platform → конкретная реализация
│   │       ├── configurator/
│   │       │   ├── base.py         # ABC: SystemConfigurator
│   │       │   ├── linux.py        # ip/iptables/ethtool
│   │       │   └── windows.py      # netsh/PowerShell
│   │       ├── stun/               # STUN-клиент (или в common, см. п. 3.1)
│   │       ├── ipc/
│   │       │   ├── server.py       # UDS (Linux) / TCP loopback (Windows)
│   │       │   └── controller.py   # CONTROLLER: команды ↔ engine API
│   │       ├── config/loader.py    # JSON + CLI-парсер → VPNConfig (валидация)
│   │       └── main.py             # Assembler: DI-сборка + lifecycle + сигналы
│   │
│   └── p2pvpn_cli/                 # VIEW
│       └── cli/
│           ├── commands/           # status, connect, add-peer, stop, peers
│           ├── rendering/          # rich: таблицы пиров, banner, spinner
│           ├── ipc_client.py       # тонкий клиент IPC (ничего не знает про L2)
│           └── main.py             #точка входа: argparse/typer, exit codes
├── tests/                          # unit / integration / e2e
└── pyproject.toml                  # три пакета: common, daemon, cli
```

MVC-разделение ответственности:

- **Model** = `p2pvpn_daemon` (движок, транспорты, интерфейсы, пиры) + `p2pvpn_common.models` (доменные типы).
- **Controller** = `p2pvpn_daemon/ipc/controller.py` (IPCController) — переводит команды клиента в вызовы движка; плюс `config/loader.py` как контроллер конфигурации.
- **View** = `p2pvpn_cli` — только отображение и ввод. Никакого знания про UDP-фреймы, TAP, NAT.

---

## 2. SOLID: конкретные решения

### S — Single Responsibility
- `VPNNode` → разделить на 5 классов:
  - `VPNEngine` — сборка/запуск/остановка компонентов (assembler).
  - `PeerManager` — реестр пиров, статусы `pending/alive/dead`, pruning.
  - `UDPTransport` — сокет, `sendto`, приём датаграмм.
  - `Heartbeat` / `HolePuncher` — две отдельные стратегии keepalive.
  - `ProtocolCodec` (в common) — encode/decode.
- `tap.py` → `L2Interface` (I/O устройства) + `SystemConfigurator` (команды ОС). Один класс — одна задача.

### O — Open/Closed
- Новая ОС = новая реализация `L2Interface`/`SystemConfigurator`, а не `if sys.platform` внутри существующих классов.
- Новый транспорт (QUIC, TCP-relay) = новая реализация `Transport`, engine не трогается.
- Новая команда CLI = новая регистрация в реестре команд, rendering не меняется.

### D — Dependency Inversion
- `VPNEngine.__init__(interface: L2Interface, transport: Transport, peers: PeerManager, codec: ProtocolCodec)` — всё через абстракции (ABC / Protocol-тип).
- `main.py` (Assembler) принимает решения о конкретных реализациях; engine — нет.
- Тесты: `FakeTransport`, `MockConfigurator`, `InMemoryL2Interface` → движок тестируется без root и без сети. Это же даёт **demo-режим** (п. 4).

### I — Interface Segregation
- Не один толстый `TAPDevice`, а три узких контракта:
  - `open()/close()` (lifecycle)
  - `write(frame)` (tx)
  - `start_reading(on_frame)` (rx)
  - `SystemConfigurator.configure(name, ip, prefix, mtu)` отдельно.
- Клиент IPC видит только `get_status/add_peer/stop`, а не всю модель движка.

### D — Don't repeat / Explicit dependencies (сопутствующее)
- Пороги `PEER_TIMEOUT`, `HEARTBEAT_INTERVAL` — инжектируются в `PeerManagerConfig` dataclass, а не read глобальных констант внутри методов.
- `logging.basicConfig` — только в точках входа (`daemon/main.py`, `cli/main.py`).

---

## 3. Порядок миграции (по этапам, каждый — рабочий MVP)

Этапы соответствуют уже написанным задачам `plan/1.1–4.1`; ниже — что к ним добавить.

### Этап 1 — Контракты и общие типы (`p2pvpn_common`)
1. `constants.py` (leaf): MAGIC, TYPE_DATA/HELLO, таймауты, TAP_MTU, DEFAULT_STUN_SERVERS.
2. `models/`: `Peer`, `PeerConfig`, `VPNConfig` (dataclass с `from_json()`/валидацией), `STUNResult`.
3. `protocol/packet.py`: `encode_data/encode_hello/decode` — перенос из `vpn_node.py`.
4. `protocol/ipc.py`: схема JSON-команд (`GET_STATUS`, `ADD_PEER`, `STOP`) — общий для CLI и daemon.
5. Тесты на все модели/кодек → `tests/`.
   **Проверка MVP:** `python -m pytest tests/p2pvpn_common` зелёные; старый код ещё работает.

### Этап 2 — Абстрации транспорта и L2 (`p2pvpn_daemon`)
1. ABC `Transport`, `L2Interface`, `SystemConfigurator`.
2. `UDPTransport` из `_make_udp_socket` + `_UDPProtocol`.
3. `LinuxTap`, `WindowsTap` из `tap.py`; конфигурация ОС вынесена в configurators (DI в Tap).
4. `PeerManager` с двумя порогами (stale/dead) и `PeerManagerConfig`.
5. `VPNEngine` — thin-оркестратор, использует вышеперечисленное.
   **Проверка MVP:** `vpn_node.py` переписывается как 5-строчный shim:
   `from p2pvpn_daemon.core.engine import VPNEngine as VPNNode`.
   Существующие интеграционные тесты (2 узла на LAN через tap0) проходят.

### Этап 3 — Daemon как сервис
1. `daemon/main.py` — assembler + signal handlers + graceful shutdown.
2. IPC-сервер (UDS `/tmp/p2pvpn.sock`, Windows: TCP 5678) + `IPCController` с API `get_status/add_peer/stop`.
3. Engine публикует метрики (peers, uptime, counters) через IPC.
   **Проверка MVP:** daemon запускается отдельно, на `curl`-подобный запрос по IPC отвечает статусом.

### Этап 4 — CLI-View (demo-готовый)
1. `p2pvpn_cli` с `pyproject.toml`, команда `p2pvpn`.
2. `rich`-отображение: banner, таблица пиров, статус-панель.
3. Команды:
   - `p2pvpn connect --config node_a.json` (или `--ip/--port/--peer` flags)
   - `p2pvpn status` — таблица пиров [alive/pending/dead], STUN-адрес, uptime
   - `p2pvpn add-peer host:port`, `p2pvpn remove-peer`, `p2pvpn stop`
   - `p2pvpn demo` — см. п. 4.
4. Exit codes: 0 ok, 1 daemon недоступен, 2 невалидный конфиг.
   **Проверка MVP:** CLI не содержит ни одного `import` из daemon/transport.

---

## 4. Демо-режим CLI («normal вид + демонстрация»)

Демонстрация должна работать **без root, без TAP и без сети** — иначе её невозможно показать.

- В `p2pvpn_daemon` реализовать `DemoRuntime`: `InMemoryL2Interface` + `FakeTransport` + seeded `PeerManager` (3–5 пиров с искусственной динамикой: статусы меняются, счётчики растут).
- CLI `p2pvpn demo` запускает этот runtime локально (или daemon с `--demo` флагом) и показывает:

```
╭────────────────────────────────────────────╮
│  P2P L2 VPN  ·  demo node                  │
│  Virtual IP  10.0.0.1   UDP 5555   tap0   │
╰────────────────────────────────────────────╯
 Peers               Status    Last seen   MAC
 192.168.1.5:5555   alive     2s          aa:bb:cc:dd:ee:ff
 203.0.113.7:5555   pending   —           —
 198.51.100.9:5555  dead      31s         —
 Traffic: 42 frames fwd · 1.2 KB
```

- Тот же rendering используется для реального `status` — демо и прод один и тот же View. Это и есть доказательство MVC: View не меняется, меняется только Model за IPC-границей.

---

## 5. Контрольный список «архитектура готова»

- [ ] Ни одного `if sys.platform` вне фабрик/точек входа.
- [ ] `VPNNode`/`tap.py`/`main.py` в корне — пустые shim'ы (для совместимости) или удалены.
- [ ] Конфиг — типизированный `VPNConfig`, не dict.
- [ ] `VPNEngine` тестируется с моками (<100 строк тестов на happy path).
- [ ] CLI устанавливается через `uv`/`pip` и работает без daemon в demo-режиме.
- [ ] IPC-протокол задокументирован в `common/protocol/ipc.py`.
- [ ] `pytest` покрывает common, core, ipc, cli-e2e.

## 6. Риски

- **Потерянный прогресс attempt2**: исходники `packages/` не в git. Перед миграцией стоит восстановить их из `.pyc` (`uncompyle6/decompyle`) или начать чисто — план в `plan/` и `tasks/` позволяет начать без кода.
- **Windows**: UDS недоступен → IPC-абстракция обязана иметь TCP-loopback fallback (уже в плане 3.2).
- **Совместимость**: `windows-run.bat` и README ссылаются на `main.py` — shim должен жить до релиза CLI.
