# 🏗️ Jumeaux Chauds — Architecture & Layers Testing

> Comprendre l'architecture en couches et tester chaque couche indépendamment.

---

## 📊 Architecture Complète

```
┌─────────────────────────────────────────────────────────────────┐
│ Layer 8 : Visualization (optional)                             │
│  - Streamlit Dashboard (WebSocket client → API)                 │
│  - MQTT Explorer (Observer)                                     │
└─────────────────────────────────────────────────────────────────┘
                              ▲
                              │ REST / WebSocket
┌─────────────────────────────┼─────────────────────────────────┐
│ Layer 7 : API Gateway                                          │
│  - FastAPI (HTTP REST, WebSocket, OpenAPI)                     │
│  - Lifespan (bootstrap Simulator)                              │
└─────────────────────────────┬─────────────────────────────────┘
                              │ Depends on
┌─────────────────────────────┼─────────────────────────────────┐
│ Layer 6 : Simulation Core                                      │
│  - ClusterSimulator (orchestration)                            │
│  - MachineSimulator ×5 (thermal model)                         │
│  - ScenarioEngine (load profiles)                              │
│  - FaultScheduler (random faults)                              │
└─────────────────────────────┬─────────────────────────────────┘
                              │ Publishes via
┌─────────────────────────────┼─────────────────────────────────┐
│ Layer 5 : MQTT Publisher                                       │
│  - MqttPublisher (aiomqtt client)                              │
│  - Topic: dt/{cluster}/{machine}/{kind}                        │
│  - Payloads: Telemetry, Events, Summaries                      │
└─────────────────────────────┬─────────────────────────────────┘
                              │ Connects to
┌─────────────────────────────┼─────────────────────────────────┐
│ Layer 4 : MQTT Broker (optional)                               │
│  - Mosquitto (eclipse-mosquitto:2)                             │
│  - Port 1883 (TCP), 9001 (WebSocket)                           │
│  - Receives from: Publisher ×1                                 │
│  - Delivers to: Observer, Consumer                             │
└─────────────────────────────┬─────────────────────────────────┘
         ▲                     │
         │ Subscribe           │ Subscribe
    ┌────┴──────────┐      ┌───┴────────────┐
    │ Layer 3a      │      │ Layer 3b       │
    │ Consumer      │      │ Observer       │
    │ (TimescaleDB) │      │ (Display)      │
    └───────────────┘      └────────────────┘
         │                  mosquitto_sub
         │ Writes           mqtt_observer.py
    ┌────▼──────────┐      mqtt-explorer
    │ Layer 2       │
    │ TimescaleDB   │
    │ (optional)    │
    └───────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ Layer 1 : Physics & Configuration (Foundation)                 │
│  - Thermal model (equations, noise)                             │
│  - YAML config (OmegaConf merge 3 levels)                       │
│  - Machine state (temperature, power, fans)                     │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🧱 Couches et Tests Associés

### Layer 1 : Physics & Configuration (Foundation)

**Files:**
- `simulation/physics.py` — Équation thermique, bruit
- `simulation/noise.py` — Gaussian noise
- `config/base.yaml`, `scenarios/*.yaml` — Configuration
- `config/loader.py` — Merge OmegaConf

**Tests:**
```bash
pytest tests/test_physics.py -v                    # 35 tests
pytest tests/test_config.py -v                     # Config tests
pytest tests/test_machine*.py -v                   # Machine state
```

**Test without any dependencies:**
```python
from simulation.physics import compute_thermal_step

T = compute_thermal_step(
    T_current=22.0,
    load_factor=0.8,
    fan_rpm_mean=0,
    dt=0.1,
    params=DEFAULT_MASTER_THERMAL
)
assert T > 22.0  # Temperature increases
```

---

### Layer 2 : Simulation Core

**Files:**
- `simulation/machine.py` — MachineSimulator
- `simulation/cluster.py` — ClusterSimulator
- `simulation/scenarios.py` — ScenarioEngine, FaultScheduler

**Tests:**
```bash
pytest tests/test_machine_telemetry.py -v          # 50 tests
pytest tests/test_machine_commands.py -v           # 30 tests
pytest tests/test_energy_conformity.py -v          # 35 tests
```

**Test without any external service:**
```python
from simulation.cluster import ClusterSimulator
from config.loader import load_config

cfg = load_config("nominal")
simulator = ClusterSimulator(cfg)

# Simulate 10 ticks
for _ in range(10):
    for machine in simulator.machines.values():
        machine.tick(load_factor=0.5, dt=0.1)

assert simulator.machines["srv-master-01"].temperature_c > 22.0
```

---

### Layer 3 : MQTT Broker

**External service:** Mosquitto (Docker or native)

**Setup without Docker:**
```bash
# Native macOS
brew install mosquitto
mosquitto -v

# Native Linux
sudo apt install mosquitto
mosquitto -v

# Or Docker
docker run -d --name mosquitto -p 1883:1883 eclipse-mosquitto:2
```

**Verify connectivity:**
```bash
# Test publishing
mosquitto_pub -h localhost -t "test/topic" -m "hello"

# Test subscribing
mosquitto_sub -h localhost -t "test/topic"

# Check MQTT broker status
mosquitto_sub -h localhost -t '$SYS/#'
```

---

### Layer 3a : MQTT Publisher

**Files:**
- `mqtt/publisher.py` — MqttPublisher (aiomqtt client)

**Tests (without running broker):**
```bash
pytest tests/test_mqtt_integration.py -v           # 18 tests
```

**Tests validate:**
- Topic construction
- Payload structure
- QoS levels
- JSON serialization

**No broker needed because tests validate code paths only.**

---

### Layer 3b : MQTT Observer

**Tools for observing MQTT messages:**

| Tool | Command | Best For |
|------|---------|----------|
| **MQTT Explorer** | `mqtt-explorer` (GUI) | Visual inspection, learning |
| **mosquitto_sub** | `mosquitto_sub -h localhost -t "dt/#" -v` | Scripting, logging |
| **mqtt_observer.py** | `python scripts/mqtt_observer.py` | Python integration, JSON formatting |

**Start observing:**
```bash
# Option 1 : Our script (JSON pretty-print)
python scripts/mqtt_observer.py --host localhost --topics "dt/+/+/telemetry"

# Option 2 : Native mosquitto_sub (lightweight)
mosquitto_sub -h localhost -t "dt/#" -v

# Option 3 : MQTT Explorer (GUI)
mqtt-explorer
```

---

### Layer 4 : Consumer MQTT → TimescaleDB

**Files:**
- `consumer/mqtt_to_timescale.py` — Subscriber + writer
- `consumer/schema.sql` — Hypertable schema

**Tests (without broker or database):**
```bash
pytest tests/test_consumer_integration.py -v       # 28 tests
```

**Tests validate:**
- Topic parsing (regex)
- Payload parsing (JSON)
- Timestamp conversion (ISO 8601)
- Message dispatch logic

**No database needed because tests validate consumer logic only.**

---

### Layer 5 : API Gateway (FastAPI)

**Files:**
- `api/main.py` — FastAPI app with lifespan
- `api/routes/*.py` — Endpoint definitions
- `api/models.py` — Pydantic schemas

**Tests:**
```bash
pytest tests/test_api_integration.py -v            # 23 tests
```

**Run API server:**
```bash
# Without MQTT (faster)
export MQTT_ENABLED=0
uvicorn api.main:app --reload --port 8000

# With MQTT (if broker available)
uvicorn api.main:app --reload --port 8000
```

**Test endpoints:**
```bash
# Interactive docs
http://localhost:8000/docs

# REST API
curl http://localhost:8000/cluster/status
curl http://localhost:8000/machines/srv-master-01
curl -X POST http://localhost:8000/machines/srv-master-01/power -d '{"power_on": true}'

# WebSocket
wscat -c ws://localhost:8000/ws/cluster
```

---

### Layer 6 : Simulation with Publishing

**Combine Layers 1+2+3a:**

```bash
# Terminal 1 : Broker
docker run -d --name mosquitto -p 1883:1883 eclipse-mosquitto:2

# Terminal 2 : Simulator + Publisher
python scripts/run_simulator.py --scenario nominal --duration 1m

# Terminal 3 : Observer
python scripts/mqtt_observer.py --host localhost
```

**What's happening:**
1. ClusterSimulator ticks every ~100ms (10 Hz)
2. Each tick computes physics for all machines
3. Publisher sends snapshots to MQTT
4. Observer displays messages in real-time

---

### Layer 7 : API Gateway

**Combine Layers 1+2+3a+5:**

```bash
# Terminal 1 : Broker
docker run -d --name mosquitto -p 1883:1883 eclipse-mosquitto:2

# Terminal 2 : Simulator (publishes to MQTT)
python scripts/run_simulator.py --scenario nominal --duration 10m

# Terminal 3 : API (controls simulator via FastAPI)
uvicorn api.main:app --port 8000

# Terminal 4 : Test API
curl http://localhost:8000/cluster/status
curl -X POST http://localhost:8000/machines/srv-master-01/power -d '{"power_on": true}'

# Browser : Interactive docs
http://localhost:8000/docs
```

**API capabilities:**
- GET cluster status
- POST/PUT machine commands
- WebSocket real-time snapshots
- Scenario switching
- Fault injection

---

### Layer 8 : Full Stack with Visualization

**Combine all layers:**

```bash
# Terminal 1 : Broker
docker run -d --name mosquitto -p 1883:1883 eclipse-mosquitto:2

# Terminal 2 : Simulator
python scripts/run_simulator.py --scenario busy_weeks --duration 1h

# Terminal 3 : Observer (check MQTT publishing)
python scripts/mqtt_observer.py --host localhost

# Terminal 4 : API
uvicorn api.main:app --port 8000

# Terminal 5 : Dashboard
streamlit run dashboard/app.py

# Browser 1 : API docs
http://localhost:8000/docs

# Browser 2 : Dashboard
http://localhost:8501
```

---

## 🧪 Testing Strategy by Layer

### Layer 1 Only (No external services)
```bash
pytest tests/test_physics.py tests/test_config.py -v
# ✅ 35 physics + config tests
# Time : ~1 min
# Requirements : None
```

### Layer 2 Only (No external services)
```bash
pytest tests/test_machine*.py tests/test_energy*.py -v
# ✅ ~115 machine + energy tests
# Time : ~2 min
# Requirements : None
```

### Layer 3a (Publisher, no broker needed)
```bash
pytest tests/test_mqtt_integration.py -v
# ✅ 18 MQTT tests
# Time : ~30 sec
# Requirements : None (tests validate code paths)
```

### Layer 3b (Consumer, no broker/database needed)
```bash
pytest tests/test_consumer_integration.py -v
# ✅ 28 consumer tests
# Time : ~30 sec
# Requirements : None (tests validate parsing logic)
```

### Layer 5 (API, optional MQTT)
```bash
pytest tests/test_api_integration.py -v
# ✅ 23 API tests
# Time : ~2 min
# Requirements : FastAPI app running (MQTT optional)
```

### Layer 1+2+3a (Full simulation with MQTT)
```bash
# No pytest needed, manual test :
docker run -d --name mosquitto -p 1883:1883 eclipse-mosquitto:2
python scripts/run_simulator.py --scenario nominal --duration 1m
python scripts/mqtt_observer.py --host localhost
# ✅ Check MQTT messages publishing in real-time
# Time : ~2 min
# Requirements : Docker or native Mosquitto
```

### All Layers (Full stack)
```bash
# Requires all services running simultaneously
# See Layer 8 section above
# Time : Ongoing (run as long as desired)
# Requirements : All (Docker, MQTT, API, Streamlit)
```

---

## 📋 Quick Reference: Test Command for Each Layer

| Layer | Test Command | Time | Requires |
|-------|---|---|---|
| **1** | `pytest tests/test_physics.py` | 1 min | None |
| **2** | `pytest tests/test_machine*.py` | 2 min | None |
| **3a** | `pytest tests/test_mqtt_integration.py` | 30s | None |
| **3b** | `pytest tests/test_consumer_integration.py` | 30s | None |
| **5** | `pytest tests/test_api_integration.py` | 2 min | API running |
| **All** | `pytest tests/ --cov=simulation --cov=config` | 5 min | None |

---

## 🚀 Recommended Testing Flow

1. **Start with Layer 1** (5 min)
   ```bash
   pytest tests/test_physics.py tests/test_config.py -v
   ```

2. **Test Layer 2** (5 min)
   ```bash
   pytest tests/test_machine*.py tests/test_energy*.py -v
   ```

3. **Test Layer 3** (2 min)
   ```bash
   pytest tests/test_mqtt_integration.py tests/test_consumer_integration.py -v
   ```

4. **Test Layer 5** (2 min)
   ```bash
   pytest tests/test_api_integration.py -v
   ```

5. **Integration test (Layer 1+2+3a)** (5 min)
   ```bash
   docker run -d --name mosquitto -p 1883:1883 eclipse-mosquitto:2
   python scripts/run_simulator.py --scenario nominal --duration 1m
   python scripts/mqtt_observer.py --host localhost
   ```

6. **Full stack** (ongoing)
   ```bash
   # Launch all services (see Layer 8 above)
   ```

**Total time : ~20 min for full validation**

---

*Tristan Vanrullen — La Plateforme, Marseille — 2026*
